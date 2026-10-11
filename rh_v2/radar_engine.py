"""Radar engine：FAST GATE → 6 signals → score → stage 状态机（滞回）→ REVIVAL / BREAKOUT。

分两层：
  * 纯函数（本文件上半部分）：只吃已经读好的数据，返回结构化结果。可单测、可离线重放。
  * 运行层（run_once）：从 market.sqlite 只读批量取数，逐币调纯函数，结果写 radar.sqlite。

原则（Spec §2）：缺数据 → None（UNKNOWN），不当 0、不当 False、不猜、不造历史。
所有阈值来自 radar_config。
"""
import hashlib
import json
import math
import os
import statistics
import time
from datetime import datetime, timezone

import radar_config as C
import radar_db

DAY = C.DAY_SEC
STAGE_RANK = {s: i for i, s in enumerate(C.STAGES)}


# =====================================================================
# 时间基准 / 定稿日 K（Spec §4–5）
# =====================================================================

def utc_day_start(ts):
    return int(ts) - int(ts) % DAY


def latest_finalized_day(as_of):
    """项目统一的 latest finalized date：UTC 昨天（与 streak.ts canonicalWindowEndTs 一致）。
    只由日历决定，不看任何 token 自己的最后一根 K 线。"""
    return utc_day_start(as_of) - DAY


def day_key(ts):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def _ratio(v):
    """比率 / 增长率在打分前取 10 位小数，避免 1100/1000-1 = 0.1000000000009 这类浮点误差跨过档位边界。"""
    return round(v, 10)


def _num(v):
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def observation_proves_final(bar_ts, observed_at, as_of):
    """与 streak.ts observationProvesFinal 同口径，另加"不使用未来数据"：observed_at <= as_of。"""
    if observed_at is None:
        return False
    if observed_at > as_of:
        return False
    if observed_at < bar_ts + DAY:
        return False
    if bar_ts < observed_at - C.KLINE_FETCH_WINDOW_SEC:
        return False
    return True


def bar_eligible_by_creation(bar_ts, created_at):
    if created_at is None or created_at <= 0:
        return True
    return bar_ts >= utc_day_start(created_at)


def finalized_bars(rows, as_of, created_at):
    """rows: [{ts, high, close, volume, fetched_at, finalized_at}] → {ts: bar}，只留 FINALIZED。"""
    out = {}
    for r in rows:
        ts = int(r["ts"])
        close = _num(r.get("close"))
        if close is None or close <= 0:
            continue
        if ts + DAY > as_of:          # 当日未结束 → OPEN，不进入任何历史窗口
            continue
        if not bar_eligible_by_creation(ts, created_at):
            continue
        if not (observation_proves_final(ts, r.get("finalized_at"), as_of)
                or observation_proves_final(ts, r.get("fetched_at"), as_of)):
            continue
        high = _num(r.get("high"))
        vol = _num(r.get("volume"))
        out[ts] = {
            "ts": ts,
            "date": day_key(ts),
            "high": high if high is not None and high > 0 else close,
            "close": close,
            "volume": vol if vol is not None and vol >= 0 else None,
        }
    return out


# =====================================================================
# FAST GATE（Spec §6–10）
# =====================================================================

def fast_gate(snap, as_of):
    """→ (gate, low_liquidity, reasons)。gate ∈ PASS / REJECT / UNKNOWN；不参与 score。

    REJECT 只看明确证据：honeypot=1、halt=1（明确不可交易），或已确认的 liquidity < 10k。
    UNKNOWN：价格或流动性缺失 / 太旧，无法确认。
    """
    reasons = []

    def add(level, code, text):
        reasons.append({"level": level, "code": code, "text": text})

    price = _num(snap.get("price"))
    price_at = snap.get("price_updated_at")
    liq = _num(snap.get("liquidity"))
    liq_at = snap.get("liquidity_updated_at")
    honeypot = snap.get("security_is_honeypot")
    halt = snap.get("halt")
    sec_at = snap.get("security_updated_at")

    def fresh(at):
        return at is not None and at <= as_of and as_of - at <= C.GATE_MAX_INPUT_AGE_SEC

    untradeable = False
    if honeypot == 1:
        untradeable = True
        add("reject", "honeypot", "Honeypot (GMGN security)")
    if halt == 1:
        untradeable = True
        add("reject", "halt", "Trading halted")

    price_ok = price is not None and price > 0 and fresh(price_at)
    liq_ok = liq is not None and liq >= 0 and fresh(liq_at)

    if price_ok:
        add("ok", "price", "Price valid")
    elif price is None or price <= 0:
        add("unknown", "price_missing", "Price missing")
    else:
        add("unknown", "price_stale", "Price too old to confirm")

    if liq_ok:
        if liq < C.GATE_REJECT_LIQUIDITY_USD:
            add("reject", "liquidity_low", f"Liquidity ${liq:,.0f} < ${C.GATE_REJECT_LIQUIDITY_USD:,.0f}")
        else:
            add("ok", "liquidity", f"Liquidity ${liq:,.0f}")
            if liq < C.GATE_LOW_LIQUIDITY_USD:
                add("warn", "low_liquidity", "Low liquidity")
    elif liq is None:
        add("unknown", "liquidity_missing", "Liquidity missing")
    else:
        add("unknown", "liquidity_stale", "Liquidity too old to confirm")

    if sec_at is None:
        add("unknown", "security_missing", "Security data missing")

    if untradeable or (liq_ok and liq < C.GATE_REJECT_LIQUIDITY_USD):
        return "REJECT", None, reasons
    if not (price_ok and liq_ok):
        return "UNKNOWN", None, reasons
    return "PASS", liq < C.GATE_LOW_LIQUIDITY_USD, reasons


# =====================================================================
# 6 signals（Spec §11–27）
# =====================================================================

def volume_ratio(bars, d_ts):
    """latest finalized-day volume / 前 7 个 finalized-day 成交额中位数。"""
    ev = {"latest_date": day_key(d_ts), "horizon": f"D vs median(D-{C.VOLUME_BASELINE_DAYS}..D-1)"}
    latest = bars.get(d_ts)
    if latest is None or latest["volume"] is None:
        ev["reason"] = "latest finalized candle missing"
        return None, ev
    ev["latest_volume"] = latest["volume"]
    base_days = [d_ts - i * DAY for i in range(C.VOLUME_BASELINE_DAYS, 0, -1)]
    vols = [bars[t]["volume"] if t in bars else None for t in base_days]
    ev["baseline_dates"] = [day_key(t) for t in base_days]
    ev["baseline_volumes"] = vols
    have = sum(v is not None for v in vols)
    if have < C.VOLUME_BASELINE_DAYS:
        ev["reason"] = f"baseline insufficient ({have}/{C.VOLUME_BASELINE_DAYS} finalized days)"
        return None, ev
    med = statistics.median(vols)
    ev["baseline_median"] = med
    if med <= 0:
        ev["reason"] = "baseline median is 0 (ratio undefined)"
        return None, ev
    return _ratio(latest["volume"] / med), ev


def buy_share(buy_volume, sell_volume):
    ev = {"horizon": "24h", "buy_volume_24h": buy_volume, "sell_volume_24h": sell_volume}
    if buy_volume is None or sell_volume is None:
        ev["reason"] = "buy/sell volume not collected"
        return None, ev
    total = buy_volume + sell_volume
    if total <= 0:
        ev["reason"] = "no 24h volume"
        return None, ev
    return _ratio(buy_volume / total), ev


def growth(points):
    """points: 按时间倒序的 [(seen_at, value, bucket?)]，每个快照桶一项。最近两次快照比较。"""
    points = [p[:2] for p in points]
    ev = {"horizon": "last 2 snapshots"}
    if len(points) < 2:
        ev["reason"] = "no comparable history"
        if points:
            ev["cur_at"], ev["cur"] = points[0]
        return None, ev
    (cur_at, cur), (prev_at, prev) = points[0], points[1]
    ev.update(cur=cur, cur_at=cur_at, prev=prev, prev_at=prev_at, span_sec=cur_at - prev_at)
    if prev <= 0:
        ev["reason"] = "previous value is 0"
        return None, ev
    return _ratio(cur / prev - 1), ev


def cross_list_count(seen, reliable, coverage):
    """seen: {source: last_seen_at}（窗口内）。同一来源重复出现只算一次。"""
    ev = {"horizon": "60m", "sources": dict(sorted(seen.items())), "coverage": coverage}
    if not reliable:
        ev["reason"] = "discovery history not reliable for this chain in the window"
        return None, ev
    return len(seen), ev


def breakout_10d(bars, d_ts, price, price_at, as_of):
    """→ (breakout, near, distance, ev)。窗口 = 统一 D 及之前 10 个定稿日（日历连续）。"""
    days = [d_ts - i * DAY for i in range(C.BREAKOUT_WINDOW_DAYS - 1, -1, -1)]
    ev = {"horizon": f"{C.BREAKOUT_WINDOW_DAYS} finalized candles",
          "window": [day_key(days[0]), day_key(days[-1])]}
    have = [bars[t] for t in days if t in bars]
    ev["candles"] = len(have)
    if len(have) < C.BREAKOUT_WINDOW_DAYS:
        ev["reason"] = f"only {len(have)}/{C.BREAKOUT_WINDOW_DAYS} finalized candles"
        return None, None, None, ev
    high = max(b["high"] for b in have)
    ev["prev_10d_high"] = high
    p = _num(price)
    ev["price"], ev["price_at"] = p, price_at
    if p is None or p <= 0 or price_at is None or price_at > as_of \
            or as_of - price_at > C.BREAKOUT_PRICE_MAX_AGE_SEC:
        ev["reason"] = "no valid current price"
        return None, None, None, ev
    distance = _ratio(p / high - 1)
    ev["distance"] = distance
    confirmed = p > high
    near = (not confirmed) and C.NEAR_BREAKOUT_MIN_DISTANCE <= distance <= 0
    return confirmed, near, distance, ev


# =====================================================================
# Scoring（Spec §13–28）
# =====================================================================

def _tier(v, tiers):
    for lo, pts in tiers:
        if v >= lo:
            return pts
    return 0


def score_volume(v):
    return 0 if v is None else _tier(v, C.VOLUME_RATIO_TIERS)


def score_buy(v):
    return 0 if v is None else _tier(v, C.BUY_SHARE_TIERS)


def _score_growth(v, tiers, positive):
    if v is None or v <= 0:
        return 0
    t = _tier(v, tiers)
    return t if t else positive


def score_holder(v):
    return _score_growth(v, C.HOLDER_GROWTH_TIERS, C.HOLDER_GROWTH_POSITIVE)


def score_liquidity(v):
    return _score_growth(v, C.LIQUIDITY_GROWTH_TIERS, C.LIQUIDITY_GROWTH_POSITIVE)


def score_cross(v):
    return 0 if v is None else _tier(v, C.CROSS_LIST_TIERS)


def score_breakout(confirmed, near):
    """confirmed 与 near 互斥，不叠加（§26）。"""
    if confirmed is True:
        return C.BREAKOUT_CONFIRMED_SCORE
    if near is True:
        return C.BREAKOUT_NEAR_SCORE
    return 0


def score_signals(sig):
    """sig: {volume_ratio, buy_share, holder_growth, liquidity_growth, cross_list_count_60m,
    breakout_10d, near_breakout_10d} → 分项、raw、final、known/unknown。"""
    parts = {
        "volume": score_volume(sig["volume_ratio"]),
        "buy": score_buy(sig["buy_share"]),
        "holder": score_holder(sig["holder_growth"]),
        "liquidity": score_liquidity(sig["liquidity_growth"]),
        "cross": score_cross(sig["cross_list_count_60m"]),
        "breakout": score_breakout(sig["breakout_10d"], sig["near_breakout_10d"]),
    }
    raw = sum(parts.values())
    known = sum(sig[name] is not None for name in C.SIGNAL_NAMES)
    return {
        "parts": parts,
        "raw_score": raw,
        "score": min(raw, C.SCORE_CAP),
        "known": known,
        "unknown": len(C.SIGNAL_NAMES) - known,
    }


# =====================================================================
# Stage（Spec §29–36）
# =====================================================================

def ready_check(score, sig, known):
    """READY 的全部硬条件，逐条给出真假与实际值（用于 transition reason）。"""
    vr, bs = sig["volume_ratio"], sig["buy_share"]
    bk, cl = sig["breakout_10d"], sig["cross_list_count_60m"]
    checks = [
        ("score", score >= C.READY_MIN_SCORE, f"score {score} ≥ {C.READY_MIN_SCORE}"),
        ("known", known >= C.READY_MIN_KNOWN_SIGNALS, f"known signals {known} ≥ {C.READY_MIN_KNOWN_SIGNALS}"),
        ("volume", vr is not None and vr >= C.READY_MIN_VOLUME_RATIO,
         f"volume_ratio {'?' if vr is None else f'{vr:.2f}'} ≥ {C.READY_MIN_VOLUME_RATIO}"),
        ("buy", bs is not None and bs >= C.READY_MIN_BUY_SHARE,
         f"buy_share {'?' if bs is None else f'{bs:.1%}'} ≥ {C.READY_MIN_BUY_SHARE:.0%}"),
        ("breakout_or_cross", bk is True or (cl is not None and cl >= C.READY_MIN_CROSS_LIST),
         f"breakout_10d {'?' if bk is None else bk} OR cross_list {'?' if cl is None else cl} ≥ {C.READY_MIN_CROSS_LIST}"),
    ]
    return [{"code": c, "ok": ok, "text": t} for c, ok, t in checks]


def entry_stage(score, checks):
    """本次 observation 单独达到的最高 stage（不含滞回）。"""
    if all(c["ok"] for c in checks):
        return "READY"
    if score >= C.EARLY_MIN_SCORE:
        return "EARLY"
    if score >= C.OBSERVE_MIN_SCORE:
        return "OBSERVE"
    return "NORMAL"


def new_state(now):
    return {
        "stage": "NORMAL",
        "stage_since": now,
        "below_streak": {k: 0 for k in C.DOWNGRADE_BELOW},
        "recent_valid_scores": [],
    }


def step_state(state, score, entry, valid, checks):
    """状态机一步。→ (next_state, transition | None)。不修改入参。

    * valid=False（UNKNOWN observation / 没有新数据）：什么都不变，不计入降级连击（§36）。
    * 升级即时生效（§35）：entry 高于当前 stage → 直接升到 entry，连击清零。
    * 降级（§36）：每个 stage 各有 "score < 阈值" 的连续 valid 计数；当前 stage 的计数达到 2 →
      降一级，再看下一级的计数，直到某级不满足。
    """
    st = {
        "stage": state["stage"],
        "stage_since": state["stage_since"],
        "below_streak": dict(state["below_streak"]),
        "recent_valid_scores": list(state["recent_valid_scores"]),
    }
    if not valid:
        return st, None
    st["recent_valid_scores"] = (st["recent_valid_scores"] + [score])[-5:]
    cur = st["stage"]
    if STAGE_RANK[entry] > STAGE_RANK[cur]:
        st["stage"] = entry
        st["below_streak"] = {k: 0 for k in C.DOWNGRADE_BELOW}
        if entry == "READY":
            reason = "UPGRADE: " + "; ".join(c["text"] for c in checks)
        else:
            th = {"EARLY": C.EARLY_MIN_SCORE, "OBSERVE": C.OBSERVE_MIN_SCORE}[entry]
            reason = f"UPGRADE: score {score} ≥ {th} ({entry} threshold)"
            if score >= C.READY_MIN_SCORE:
                failed = [c["text"] for c in checks if not c["ok"]]
                reason += "; READY blocked: " + "; ".join(failed)
        return st, {"from": cur, "to": entry, "reason": reason}

    for stage, below in C.DOWNGRADE_BELOW.items():
        st["below_streak"][stage] = st["below_streak"][stage] + 1 if score < below else 0
    target = cur
    while target != "NORMAL" and st["below_streak"][target] >= C.DOWNGRADE_CONSECUTIVE:
        target = C.STAGES[STAGE_RANK[target] - 1]
    if target == cur:
        return st, None
    st["stage"] = target
    n = C.DOWNGRADE_CONSECUTIVE
    tail = st["recent_valid_scores"][-n:]
    reason = (f"DOWNGRADE: score < {C.DOWNGRADE_BELOW[cur]} for {n} consecutive valid observations "
              f"(scores {', '.join(map(str, tail))})")
    return st, {"from": cur, "to": target, "reason": reason}


# =====================================================================
# REVIVAL（Spec §37–38）
# =====================================================================

def age_days(created_at, first_bar_ts, as_of):
    """→ (days | None, basis)。created_at 缺失时，最早定稿日 K 只能证明"至少这么老"。"""
    if created_at is not None and created_at > 0 and created_at <= as_of:
        return (as_of - created_at) / DAY, "created_at"
    if first_bar_ts is not None and first_bar_ts <= as_of:
        return (as_of - first_bar_ts) / DAY, "first_candle_lower_bound"
    return None, None


def revival(age, bars, d_ts, sig):
    """→ (True | False | None, evidence)。三值逻辑：任一必要条件确定为假 → False；
    全部必要条件为真且支持项 ≥2 → True；其余（历史不足）→ None。"""
    ev = {"age_days": age}
    # 年龄
    age_ok = None if age is None else age >= C.REVIVAL_MIN_AGE_DAYS
    # 历史沉寂期：D 之前 7 个定稿日齐全，且每天成交额 ≤ D 成交额 × 1/3
    latest = bars.get(d_ts)
    w_days = [d_ts - i * DAY for i in range(C.REVIVAL_DORMANT_WINDOW_DAYS, 0, -1)]
    w_vols = [bars[t]["volume"] if t in bars else None for t in w_days]
    ev["dormant_window"] = {"dates": [day_key(t) for t in w_days], "volumes": w_vols}
    if latest is None or latest["volume"] is None or any(v is None for v in w_vols):
        dormant = None
        ev["dormant_reason"] = "dormant window incomplete"
    else:
        ev["latest_volume"] = latest["volume"]
        ev["dormant_window"]["max"] = max(w_vols)
        dormant = max(w_vols) <= latest["volume"] * C.REVIVAL_DORMANT_MAX_FRACTION_OF_LATEST
    vr = sig["volume_ratio"]
    vol_ok = None if vr is None else vr >= C.REVIVAL_MIN_VOLUME_RATIO
    support = {
        "buy_share": None if sig["buy_share"] is None else sig["buy_share"] >= C.REVIVAL_MIN_BUY_SHARE,
        "holder_growth": None if sig["holder_growth"] is None else sig["holder_growth"] > 0,
        "liquidity_growth": None if sig["liquidity_growth"] is None else sig["liquidity_growth"] > 0,
        "cross_list": None if sig["cross_list_count_60m"] is None
        else sig["cross_list_count_60m"] >= C.REVIVAL_MIN_CROSS_LIST,
        "breakout_10d": sig["breakout_10d"],
    }
    n_true = sum(v is True for v in support.values())
    n_unknown = sum(v is None for v in support.values())
    ev.update(age_ok=age_ok, dormant=dormant, volume_ok=vol_ok, support=support, support_true=n_true)
    required = (age_ok, dormant, vol_ok)
    if any(v is False for v in required) or n_true + n_unknown < C.REVIVAL_MIN_SUPPORTING:
        return False, ev
    if all(v is True for v in required) and n_true >= C.REVIVAL_MIN_SUPPORTING:
        return True, ev
    return None, ev


# =====================================================================
# 单币 evaluation（纯函数）
# =====================================================================

def evaluate_token(inp, as_of, d_ts):
    """inp: {chain, address, snap, bars(rows), first_bar_ts, created_at, buy_volume, sell_volume,
    holder_points, liquidity_points, cross_seen, cross_reliable, cross_coverage} → evaluation dict。"""
    snap = inp["snap"]
    gate, low_liq, gate_reasons = fast_gate(snap, as_of)
    bars = finalized_bars(inp["bars"], as_of, inp["created_at"])

    vr, ev_vol = volume_ratio(bars, d_ts)
    bs, ev_buy = buy_share(inp.get("buy_volume"), inp.get("sell_volume"))
    hg, ev_h = growth(inp["holder_points"])
    lg, ev_l = growth(inp["liquidity_points"])
    cl, ev_c = cross_list_count(inp["cross_seen"], inp["cross_reliable"], inp["cross_coverage"])
    bk, near, dist, ev_b = breakout_10d(bars, d_ts, snap.get("price"), snap.get("price_updated_at"), as_of)

    sig = {
        "volume_ratio": vr,
        "buy_share": bs,
        "holder_growth": hg,
        "liquidity_growth": lg,
        "cross_list_count_60m": cl,
        "breakout_10d": bk,
        "near_breakout_10d": near,
    }
    sc = score_signals(sig)
    checks = ready_check(sc["score"], sig, sc["known"])
    entry = entry_stage(sc["score"], checks)
    age, age_basis = age_days(inp["created_at"], inp.get("first_bar_ts"), as_of)
    rv, ev_r = revival(age, bars, d_ts, sig)
    ev_r["age_basis"] = age_basis

    return {
        "chain": inp["chain"],
        "address": inp["address"],
        "evaluated_at": as_of,
        "finalized_date": day_key(d_ts),
        "gate": gate,
        "low_liquidity": low_liq,
        "gate_reasons": gate_reasons,
        "signals": sig,
        "breakout_distance": dist,
        "score": sc,
        "ready_check": checks,
        "entry_stage": entry,
        "revival": rv,
        "evidence": {
            "volume": ev_vol, "buy": ev_buy, "holder": ev_h, "liquidity": ev_l,
            "cross": ev_c, "breakout": ev_b, "revival": ev_r,
            "gate": {
                "price": _num(snap.get("price")), "price_at": snap.get("price_updated_at"),
                "liquidity": _num(snap.get("liquidity")), "liquidity_at": snap.get("liquidity_updated_at"),
                "liquidity_source": snap.get("liquidity_source"),
                "security_at": snap.get("security_updated_at"),
            },
            "ready_check": checks,
        },
    }


def _round(v):
    if isinstance(v, float):
        return float(f"{v:.6g}")
    return v


def fingerprint(ev, snap):
    """新 observation 判定：signal 值、gate、以及驱动它们的源时间戳任一变化。"""
    payload = [
        ev["gate"], ev["low_liquidity"], ev["finalized_date"],
        [_round(ev["signals"][k]) for k in sorted(ev["signals"])],
        sorted(ev["evidence"]["cross"]["sources"].items()),
        ev["evidence"]["holder"].get("cur_at"), ev["evidence"]["liquidity"].get("cur_at"),
        snap.get("price_updated_at"), snap.get("liquidity_updated_at"),
    ]
    return hashlib.sha1(json.dumps(payload, default=str).encode()).hexdigest()[:20]


def outcome_key(ev, stage):
    s = ev["score"]
    return json.dumps([ev["gate"], ev["low_liquidity"], sorted(s["parts"].items()), s["known"],
                       ev["entry_stage"], stage, ev["revival"], ev["signals"]["breakout_10d"],
                       ev["signals"]["near_breakout_10d"]])


def is_relevant(stage, ev):
    return (stage != "NORMAL" or ev["entry_stage"] != "NORMAL" or ev["revival"] is True
            or ev["signals"]["breakout_10d"] is True or ev["signals"]["near_breakout_10d"] is True)


def is_candidate(stage, ev):
    """Spec §81：stage != NORMAL OR setup 含 REVIVAL / BREAKOUT；REJECT 不进候选区（§54）。"""
    if ev["gate"] == "REJECT":
        return False
    return stage != "NORMAL" or ev["revival"] is True or ev["signals"]["breakout_10d"] is True


# =====================================================================
# 批量读 market.sqlite（只读）
# =====================================================================

def _chains_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "market-chains.json")
    with open(path) as f:
        return json.load(f)["chains"]


def expected_sources(chain, chains_cfg):
    sig = {c["id"]: bool(c.get("signal")) for c in chains_cfg}
    return [s for s in C.CROSS_LIST_SOURCES if s != "signal" or sig.get(chain, False)]


def load_inputs(mcon, as_of):
    d_ts = latest_finalized_day(as_of)
    chains_cfg = _chains_config()

    snap_cols = {r[1] for r in mcon.execute("PRAGMA table_info(token_snapshot)")}
    has_bsv = "buy_volume_24h" in snap_cols and "sell_volume_24h" in snap_cols
    bsv = "s.buy_volume_24h, s.sell_volume_24h" if has_bsv else "NULL AS buy_volume_24h, NULL AS sell_volume_24h"
    snaps = mcon.execute(f"""
        SELECT s.chain, s.address, s.price, s.price_updated_at,
               s.liquidity_num AS liquidity, s.liquidity_updated_at, s.liquidity_source,
               s.security_is_honeypot, s.security_updated_at, s.halt, {bsv},
               t.token_created_at, t.pair_created_at
        FROM token_snapshot s LEFT JOIN tokens t ON t.chain=s.chain AND t.address=s.address
    """).fetchall()

    lo = d_ts - (max(C.BREAKOUT_WINDOW_DAYS, C.VOLUME_BASELINE_DAYS + 1,
                     C.REVIVAL_DORMANT_WINDOW_DAYS + 1) - 1) * DAY
    bars = {}
    for r in mcon.execute(
            "SELECT chain, address, ts, high, close, volume, fetched_at, finalized_at "
            "FROM daily_kline WHERE ts BETWEEN ? AND ?", (lo, d_ts)):
        bars.setdefault((r["chain"], r["address"]), []).append(dict(r))
    first_bar = {(r[0], r[1]): r[2] for r in mcon.execute(
        "SELECT chain, address, MIN(ts) FROM daily_kline GROUP BY chain, address")}

    src_list = ",".join(f"'{s}'" for s in C.CROSS_LIST_SOURCES)
    w_lo = as_of - C.CROSS_LIST_WINDOW_SEC
    cross = {}
    for r in mcon.execute(
            f"SELECT chain, address, source, MAX(seen_at) FROM discovery_event "
            f"WHERE seen_at > ? AND seen_at <= ? AND source IN ({src_list}) "
            f"GROUP BY chain, address, source", (w_lo, as_of)):
        cross.setdefault((r[0], r[1]), {})[r[2]] = r[3]
    seen_sources = {}
    for r in mcon.execute(
            f"SELECT chain, source, COUNT(*) FROM discovery_event "
            f"WHERE seen_at > ? AND seen_at <= ? AND source IN ({src_list}) GROUP BY chain, source",
            (w_lo, as_of)):
        seen_sources.setdefault(r[0], {})[r[1]] = r[2]
    first_event = mcon.execute("SELECT MIN(seen_at) FROM discovery_event").fetchone()[0]
    coverage = {}
    for c in chains_cfg:
        exp = expected_sources(c["id"], chains_cfg)
        got = seen_sources.get(c["id"], {})
        missing = [s for s in exp if not got.get(s)]
        reliable = first_event is not None and first_event <= w_lo and not missing
        coverage[c["id"]] = {"reliable": reliable, "expected": exp, "missing": missing,
                             "events": {s: got.get(s, 0) for s in exp}}

    holders, liqs = {}, {}
    for r in mcon.execute(
            f"SELECT chain, address, seen_at, json_extract(metadata_json, '$.holder_count') AS h, liquidity, "
            f"COALESCE(time_bucket, seen_at - seen_at % {C.SNAPSHOT_BUCKET_SEC}) AS bucket "
            f"FROM discovery_event WHERE seen_at > ? AND seen_at <= ? AND source IN ({src_list}) "
            f"ORDER BY chain, address, seen_at DESC",
            (as_of - C.SNAPSHOT_HISTORY_LOOKBACK_SEC, as_of)):
        # 一个快照 = 采集器的一个 300s time_bucket；桶内取最新一次看到的值（行已按 seen_at 倒序）
        key = (r[0], r[1])
        h, lq, bucket = _num(r[3]), _num(r[4]), r[5]
        for val, store in ((h, holders), (lq, liqs)):
            if val is None:
                continue
            pts = store.setdefault(key, [])
            if len(pts) < 2 and (not pts or pts[-1][2] != bucket):
                pts.append((r[2], val, bucket))

    for s in snaps:
        key = (s["chain"], s["address"])
        created = s["token_created_at"] or s["pair_created_at"]
        cov = coverage.get(s["chain"], {"reliable": False, "missing": ["unknown chain"]})
        yield {
            "chain": s["chain"],
            "address": s["address"],
            "snap": dict(s),
            "bars": bars.get(key, []),
            "first_bar_ts": first_bar.get(key),
            "created_at": created,
            "buy_volume": _num(s["buy_volume_24h"]),
            "sell_volume": _num(s["sell_volume_24h"]),
            "holder_points": holders.get(key, []),
            "liquidity_points": liqs.get(key, []),
            "cross_seen": cross.get(key, {}),
            "cross_reliable": cov["reliable"],
            "cross_coverage": {"reliable": cov["reliable"], "missing": cov.get("missing", [])},
        }, d_ts, coverage


# =====================================================================
# 一轮 run
# =====================================================================

def _b(v):
    return None if v is None else int(bool(v))


def _empty_counts():
    return dict(scanned=0, gate_pass=0, gate_reject=0, gate_unknown=0, stage_observe=0, stage_early=0,
                stage_ready=0, revival=0, breakout=0, candidates=0)


def run_once(market_path=None, radar_path=None, as_of=None, mode="live", log=print):
    t0 = time.time()
    as_of = int(as_of if as_of is not None else t0)
    d_ts = latest_finalized_day(as_of)
    rcon = radar_db.connect(radar_path)
    mcon = radar_db.connect_market_ro(market_path)
    cur = rcon.execute(
        "INSERT INTO radar_run(mode, started_at, as_of, finalized_date) VALUES (?,?,?,?)",
        (mode, int(t0), as_of, day_key(d_ts)))
    run_id = cur.lastrowid
    rcon.commit()

    states = {}
    for r in rcon.execute("SELECT * FROM radar_state"):
        states[(r["chain"], r["address"])] = dict(r)

    totals = dict(scanned=0, gate_pass=0, gate_reject=0, gate_unknown=0, stage_normal=0, stage_observe=0,
                  stage_early=0, stage_ready=0, revival_true=0, revival_null=0, breakout_true=0,
                  near_breakout=0, new_observations=0, evals_written=0, transitions=0)
    per_chain = {"all": _empty_counts()}
    coverage = {}
    try:
        rcon.execute("BEGIN")
        for inp, _d, coverage in load_inputs(mcon, as_of):
            ev = evaluate_token(inp, as_of, d_ts)
            key = (ev["chain"], ev["address"])
            prev = states.get(key)
            fp = fingerprint(ev, inp["snap"])
            new_obs = prev is None or prev["last_fingerprint"] != fp
            valid = new_obs and ev["gate"] != "UNKNOWN"
            base = new_state(as_of) if prev is None else {
                "stage": prev["stage"], "stage_since": prev["stage_since"],
                "below_streak": json.loads(prev["below_streak"]),
                "recent_valid_scores": json.loads(prev["recent_valid_scores"]),
            }
            st, tr = step_state(base, ev["score"]["score"], ev["entry_stage"], valid, ev["ready_check"])
            stage = st["stage"]
            outcome = outcome_key(ev, stage)
            persist = new_obs and (prev is None or tr is not None or is_relevant(stage, ev)
                                   or prev["last_outcome"] != outcome)

            eval_id = prev["last_eval_id"] if prev else None
            if persist:
                eval_id = _insert_eval(rcon, run_id, ev, stage, valid, fp)
                totals["evals_written"] += 1
            if tr is not None:
                st["stage_since"] = as_of
                rcon.execute(
                    "INSERT INTO radar_transition(run_id, eval_id, chain, address, from_stage, to_stage, reason, "
                    "score, signals, occurred_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (run_id, eval_id, ev["chain"], ev["address"], tr["from"], tr["to"], tr["reason"],
                     ev["score"]["score"], json.dumps(_signal_snapshot(ev)), as_of))
                totals["transitions"] += 1
            if new_obs:
                totals["new_observations"] += 1
                rcon.execute(
                    "INSERT INTO radar_state(chain, address, stage, stage_since, below_streak, recent_valid_scores, "
                    "last_fingerprint, last_outcome, last_eval_id, last_evaluated_at, last_valid_at, "
                    "last_change_at, first_evaluated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(chain, address) DO UPDATE SET stage=excluded.stage, "
                    "stage_since=excluded.stage_since, below_streak=excluded.below_streak, "
                    "recent_valid_scores=excluded.recent_valid_scores, last_fingerprint=excluded.last_fingerprint, "
                    "last_outcome=CASE WHEN ? THEN excluded.last_outcome ELSE radar_state.last_outcome END, "
                    "last_eval_id=excluded.last_eval_id, last_evaluated_at=excluded.last_evaluated_at, "
                    "last_valid_at=COALESCE(excluded.last_valid_at, radar_state.last_valid_at), "
                    "last_change_at=CASE WHEN ? THEN excluded.last_change_at ELSE radar_state.last_change_at END",
                    (ev["chain"], ev["address"], stage, st["stage_since"], json.dumps(st["below_streak"]),
                     json.dumps(st["recent_valid_scores"]), fp, outcome, eval_id, as_of,
                     as_of if valid else None, as_of, as_of, int(persist), int(tr is not None)))

            # 计数
            g = ev["gate"]
            totals["scanned"] += 1
            totals[{"PASS": "gate_pass", "REJECT": "gate_reject", "UNKNOWN": "gate_unknown"}[g]] += 1
            totals["stage_" + stage.lower()] += 1
            totals["revival_true"] += ev["revival"] is True
            totals["revival_null"] += ev["revival"] is None
            totals["breakout_true"] += ev["signals"]["breakout_10d"] is True
            totals["near_breakout"] += ev["signals"]["near_breakout_10d"] is True
            for ck in ("all", ev["chain"]):
                c = per_chain.setdefault(ck, _empty_counts())
                c["scanned"] += 1
                c[{"PASS": "gate_pass", "REJECT": "gate_reject", "UNKNOWN": "gate_unknown"}[g]] += 1
                if g != "REJECT":
                    if stage != "NORMAL":
                        c["stage_" + stage.lower()] += 1
                    c["revival"] += ev["revival"] is True
                    c["breakout"] += ev["signals"]["breakout_10d"] is True
                c["candidates"] += is_candidate(stage, ev)

        for ck, c in per_chain.items():
            rcon.execute(
                "INSERT INTO radar_run_summary(run_id, chain, scanned, gate_pass, gate_reject, gate_unknown, "
                "stage_observe, stage_early, stage_ready, revival, breakout, candidates) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, ck, c["scanned"], c["gate_pass"], c["gate_reject"], c["gate_unknown"],
                 c["stage_observe"], c["stage_early"], c["stage_ready"], c["revival"], c["breakout"],
                 c["candidates"]))
        sets = ", ".join(f"{k}=?" for k in totals)
        rcon.execute(f"UPDATE radar_run SET {sets}, finished_at=?, cross_list_coverage=? WHERE run_id=?",
                     (*totals.values(), int(time.time()), json.dumps(coverage), run_id))
        rcon.commit()
    except Exception as e:
        rcon.rollback()
        rcon.execute("UPDATE radar_run SET finished_at=?, error=? WHERE run_id=?",
                     (int(time.time()), f"{type(e).__name__}: {e}", run_id))
        rcon.commit()
        raise
    finally:
        mcon.close()
    prune(rcon, as_of)
    rcon.close()
    totals["run_id"] = run_id
    totals["seconds"] = round(time.time() - t0, 1)
    totals["finalized_date"] = day_key(d_ts)
    log(json.dumps(totals))
    return totals


def _signal_snapshot(ev):
    return {
        "gate": ev["gate"], "low_liquidity": ev["low_liquidity"],
        "signals": {k: _round(v) for k, v in ev["signals"].items()},
        "parts": ev["score"]["parts"], "raw_score": ev["score"]["raw_score"],
        "known": ev["score"]["known"], "entry_stage": ev["entry_stage"], "revival": ev["revival"],
        "ready_check": ev["ready_check"],
    }


def compact_evidence(ev, relevant):
    """relevant（候选 / 有分数 / 有 setup）保留完整证据；其余只留 gate 输入和每个 null signal 的原因。
    revival 的沉寂窗口与 volume baseline 是同一窗口，不重复存。"""
    e = ev["evidence"]
    if relevant:
        full = {k: dict(v) if isinstance(v, dict) else v for k, v in e.items()}
        full["cross"].pop("coverage", None)
        rv = dict(full["revival"])
        rv["dormant_window"] = {k: v for k, v in rv["dormant_window"].items() if k == "max"}
        full["revival"] = rv
        return full
    out = {"compact": True, "gate": e["gate"]}
    for k in ("volume", "buy", "holder", "liquidity", "cross", "breakout"):
        if e[k].get("reason"):
            out[k] = {"reason": e[k]["reason"]}
    if e["revival"].get("dormant_reason"):
        out["revival"] = {"dormant_reason": e["revival"]["dormant_reason"]}
    return out


def _insert_eval(rcon, run_id, ev, stage, valid, fp):
    s, p, sig = ev["score"], ev["score"]["parts"], ev["signals"]
    evidence = compact_evidence(ev, is_relevant(stage, ev))
    cur = rcon.execute(
        "INSERT INTO radar_eval(run_id, chain, address, evaluated_at, finalized_date, gate, low_liquidity, "
        "gate_reasons, volume_ratio, buy_share, holder_growth, liquidity_growth, cross_list_count, "
        "breakout_distance, breakout_10d, near_breakout_10d, score_volume, score_buy, score_holder, "
        "score_liquidity, score_cross, score_breakout, raw_score, score, known_signal_count, "
        "unknown_signal_count, entry_stage, stage, revival, observation_valid, fingerprint, evidence) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, ev["chain"], ev["address"], ev["evaluated_at"], ev["finalized_date"], ev["gate"],
         _b(ev["low_liquidity"]), json.dumps(ev["gate_reasons"]), sig["volume_ratio"], sig["buy_share"],
         sig["holder_growth"], sig["liquidity_growth"], sig["cross_list_count_60m"], ev["breakout_distance"],
         _b(sig["breakout_10d"]), _b(sig["near_breakout_10d"]), p["volume"], p["buy"], p["holder"],
         p["liquidity"], p["cross"], p["breakout"], s["raw_score"], s["score"], s["known"], s["unknown"],
         ev["entry_stage"], stage, _b(ev["revival"]), int(valid), fp,
         json.dumps(evidence, default=str, separators=(",", ":"))))
    return cur.lastrowid


def prune(rcon, as_of):
    """只删超出保留期、且没被 transition / 当前 state 引用的 evaluation。transition 永久保留。"""
    cutoff = as_of - C.EVAL_RETENTION_DAYS * DAY
    rcon.execute(
        "DELETE FROM radar_eval WHERE evaluated_at < ? "
        "AND eval_id NOT IN (SELECT eval_id FROM radar_transition) "
        "AND eval_id NOT IN (SELECT last_eval_id FROM radar_state WHERE last_eval_id IS NOT NULL)",
        (cutoff,))
    rcon.commit()


def verify(radar_path=None):
    """离线重放：用存下的六个 signal 原值重算分项、raw/final、known、entry_stage，逐行比对。"""
    rcon = radar_db.connect(radar_path)
    bad = 0
    n = 0
    for r in rcon.execute("SELECT * FROM radar_eval"):
        n += 1
        sig = {
            "volume_ratio": r["volume_ratio"], "buy_share": r["buy_share"],
            "holder_growth": r["holder_growth"], "liquidity_growth": r["liquidity_growth"],
            "cross_list_count_60m": r["cross_list_count"],
            "breakout_10d": None if r["breakout_10d"] is None else bool(r["breakout_10d"]),
            "near_breakout_10d": None if r["near_breakout_10d"] is None else bool(r["near_breakout_10d"]),
        }
        sc = score_signals(sig)
        entry = entry_stage(sc["score"], ready_check(sc["score"], sig, sc["known"]))
        got = (r["score_volume"], r["score_buy"], r["score_holder"], r["score_liquidity"], r["score_cross"],
               r["score_breakout"], r["raw_score"], r["score"], r["known_signal_count"], r["entry_stage"])
        want = (*sc["parts"].values(), sc["raw_score"], sc["score"], sc["known"], entry)
        if tuple(got) != tuple(want):
            bad += 1
    rcon.close()
    return {"evals": n, "mismatches": bad}
