"""GMGN 调度与全局限流。纯决策在这里，网络在 market_collect.gmgn。

K 线有保留名额：只要 gmgn_kline 到点，就先于 Trending / Hot / Trenches / Signal。
任何 GMGN 任务看到 429 / RATE_LIMIT_* 都进入 GLOBAL_GMGN_COOLDOWN，
冷却期内所有 GMGN 任务都不再发请求。Dex / 锚价 / Chainlink 不走这条冷却。
"""
import re
import time

import market_db as db


FALLBACK_SEC = (5, 10, 20, 40, 60)
RESERVED_SOURCES = ("gmgn_kline",)

_RESET_AT = re.compile(r"""reset_at["']?\s*[:=]\s*["']?(\d{10,})""")
_RETRY_AFTER = re.compile(r"retry-after[\"']?\s*[:=]\s*(\d+)", re.I)
_REMAINING = re.compile(r"~\s*(\d+)\s*s remaining", re.I)
_RESET_STAMP = re.compile(
    r"resets at (\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})\s+GMT([+-])(\d{2}):(\d{2})"
)
_LIMIT_MARKERS = ("RATE_LIMIT_EXCEEDED", "RATE_LIMIT_BANNED", "ERROR_RATE_LIMIT_BLOCKED")

# 进程内副本。启动时从 market_meta 装入，避免重启后立刻再打 GMGN。
_state = {"until": 0, "start": 0, "step": 0, "basis": "", "loaded": False}


class RateLimited(RuntimeError):
    """GMGN 处于冷却，或这一次响应本身就是限流。调用方不得再发请求。"""


def parse_rate_limit(message, now):
    """识别限流。返回 None 表示不是限流。

    until 的优先级：reset_at > Retry-After > 文案里的 remaining > fallback。
    fallback 的秒数由调用方按阶梯决定，这里 until 留空。
    """
    text = "" if message is None else str(message)
    is_http = "HTTP 429" in text or "code=429" in text or "HTTP/1.1 429" in text
    is_word = any(mark in text for mark in _LIMIT_MARKERS)
    if not is_http and not is_word:
        return None
    now = int(now)
    found = _RESET_AT.search(text)
    if found:
        reset_at = int(found.group(1))
        if reset_at > now:
            return {"basis": "reset_at", "until": reset_at, "reset_at": reset_at}
    stamp = _RESET_STAMP.search(text)
    if stamp:
        day, hms, sign, oh, om = stamp.groups()
        year, month, dom = (int(x) for x in day.split("-"))
        hour, minute, second = (int(x) for x in hms.split(":"))
        offset = (int(oh) * 3600 + int(om) * 60) * (1 if sign == "+" else -1)
        # 文案里的时间是带时区的本地钟，转成 Unix 秒。
        from datetime import datetime, timezone, timedelta
        tz = timezone(timedelta(seconds=offset))
        dt = datetime(year, month, dom, hour, minute, second, tzinfo=tz)
        reset_at = int(dt.timestamp())
        if reset_at > now:
            return {"basis": "reset_at", "until": reset_at, "reset_at": reset_at}
    retry = _RETRY_AFTER.search(text)
    if retry:
        return {"basis": "retry_after", "until": now + int(retry.group(1)), "reset_at": None}
    remaining = _REMAINING.search(text)
    if remaining:
        return {"basis": "reset_at", "until": now + int(remaining.group(1)), "reset_at": None}
    return {"basis": "fallback", "until": None, "reset_at": None}


def _persist(con):
    db.meta_set(con, "gmgn_cooldown_until", str(int(_state["until"])))
    db.meta_set(con, "gmgn_cooldown_start", str(int(_state["start"])))
    db.meta_set(con, "gmgn_cooldown_step", str(int(_state["step"])))
    db.meta_set(con, "gmgn_cooldown_basis", _state["basis"] or "")


def load_cooldown(con):
    until = int(db.meta_get(con, "gmgn_cooldown_until", "0") or 0)
    step = int(db.meta_get(con, "gmgn_cooldown_step", "0") or 0)
    _state["until"] = until
    _state["start"] = int(db.meta_get(con, "gmgn_cooldown_start", "0") or 0)
    _state["step"] = step
    _state["basis"] = db.meta_get(con, "gmgn_cooldown_basis", "") or ""
    _state["loaded"] = True
    return until


def ensure_loaded():
    if _state["loaded"]:
        return
    con = db.connect()
    try:
        load_cooldown(con)
    finally:
        con.close()


def in_cooldown(now):
    ensure_loaded()
    return float(now) < float(_state["until"] or 0)


def cooldown_until():
    ensure_loaded()
    return int(_state["until"] or 0)


def cooldown_start():
    ensure_loaded()
    return int(_state["start"] or 0)


def arm_cooldown(now, decision, con=None):
    """进入或延长冷却。fallback 走 5→10→20→40→60，封顶 60 秒。

    服务端 reset_at / Retry-After 不被这个封顶截断。
    冷却到期后如果再次限流，重新计算并延长。
    """
    now = int(now)
    basis = decision.get("basis") or "fallback"
    if basis == "fallback" or not decision.get("until"):
        delay = FALLBACK_SEC[min(_state["step"], len(FALLBACK_SEC) - 1)]
        _state["step"] = min(_state["step"] + 1, len(FALLBACK_SEC))
        until = now + delay
        basis = "fallback"
    else:
        until = int(decision["until"])
        if until <= now:
            delay = FALLBACK_SEC[min(_state["step"], len(FALLBACK_SEC) - 1)]
            _state["step"] = min(_state["step"] + 1, len(FALLBACK_SEC))
            until = now + delay
            basis = "fallback"
    _state["until"] = until
    _state["start"] = now
    _state["basis"] = basis
    _state["loaded"] = True
    owned = con is None
    if owned:
        con = db.connect()
    try:
        _persist(con)
        if owned:
            con.commit()
    finally:
        if owned:
            con.close()
    print(
        f"[{time.strftime('%H:%M:%S')}] GLOBAL_GMGN_COOLDOWN "
        f"start={_state['start']} until={until} basis={basis}",
        flush=True,
    )
    return until


def observe_error(message, now=None, con=None):
    """如果 message 是限流，武装冷却并返回 True。"""
    now = int(time.time() if now is None else now)
    decision = parse_rate_limit(message, now)
    if not decision:
        return False
    arm_cooldown(now, decision, con=con)
    return True


def guard_or_raise(now=None):
    now = time.time() if now is None else now
    if in_cooldown(now):
        raise RateLimited(
            f"GLOBAL_GMGN_COOLDOWN start={cooldown_start()} until={cooldown_until()}"
        )


def pick_gmgn_job(nxt, now, periods, priority, reserved=RESERVED_SOURCES):
    """到点的保留车道（默认日 K）先于其它 GMGN 车道。

    没有保留车道到点时，按超期比例挑。返回 (source, chain, period) 或 None。
    """
    reserved_set = set(reserved)
    best_reserved = None
    best_other = None
    order = {name: i for i, name in enumerate(priority)}
    for (source, chain), period in periods.items():
        if source not in order:
            continue
        due = nxt.get((source, chain), 0)
        if due > now:
            continue
        late = (now - due) / max(int(period), 1)
        rank = (-late, order[source], due, str(chain))
        slot = (rank, source, chain, int(period))
        if source in reserved_set:
            if best_reserved is None or rank < best_reserved[0]:
                best_reserved = slot
        elif best_other is None or rank < best_other[0]:
            best_other = slot
    chosen = best_reserved or best_other
    if chosen is None:
        return None
    return chosen[1], chosen[2], chosen[3]


def discovery_run_state(rows_received, rows_parsed, rows_written, events_written, error=None, rate_limited=False, cooldown=False, unsupported=False):
    """请求成功不等于发现成功。发现任务没有写入时不得报 healthy。"""
    if unsupported:
        return "unsupported"
    if cooldown:
        return "cooldown"
    if rate_limited:
        return "rate_limited"
    if error:
        return "failed"
    wrote = int(rows_written or 0) > 0 or int(events_written or 0) > 0
    if wrote:
        return "healthy"
    if int(rows_received or 0) > 0 or int(rows_parsed or 0) > 0:
        return "zero_write"
    return "zero_write"
