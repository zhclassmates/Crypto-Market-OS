"""每个 source × chain 一条健康记录。状态只在读取时按时钟计算。

口径与 src/lib/rh/market-status.ts 保持一致。
失败只改 last_attempt / consecutive_errors / last_error，
不动 last_success、source_timestamp、db_written_at。
上游没有自己的时间时 source_timestamp 留空，禁止用落库时间填。
"""
import math
import sqlite3
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from market_chains import MARKET_CHAINS

FAIL_THRESHOLD = 3
DIVERGE_RATIO = 0.05

# (source, chain, period_sec)
# Trending 300s，避免 10s 扫榜占住调度。日 K 60s，并在调度里保留名额。
# Hot 120s，Trenches / Signal 300s。安全指标 600s。
# Dex 15s、锚价 15s、Chainlink 30s 不走 GMGN 冷却。
def catalog():
    rows = []
    for chain in MARKET_CHAINS:
        rows.append(("gmgn", chain, 300))
        rows.append(("gmgn_hot", chain, 120))
        rows.append(("gmgn_new_pair", chain, 300))
        rows.append(("gmgn_signal", chain, 300))
        rows.append(("gmgn_kline", chain, 60))
        rows.append(("gmgn_security", chain, 600))
        rows.append(("dexscreener", chain, 15))
    rows.append(("robinhood_anchor", "robinhood", 15))
    rows.append(("chainlink", "robinhood", 30))
    return rows


PERIOD = {(s, c): p for s, c, p in catalog()}
DB_LOCK = threading.Lock()

_NY = ZoneInfo("America/New_York")


def classify_status(now, last_attempt, last_success, consecutive_errors, has_display_rows, period_sec, round_ok, run_state=None):
    """时钟状态 LIVE / DELAYED / STALE / FAILED。

    run_state 为 cooldown / rate_limited / zero_write / unsupported / failed 时直接返回。
    请求成功但发现写入为 0 时不得再显示成 LIVE。
    本轮失败且还有旧数据 → STALE，即使 api_age 仍在周期内。
    consecutive_errors 到阈值且从未成功落过可展示数据 → FAILED。
    """
    if run_state in ("unsupported", "cooldown", "rate_limited", "zero_write", "failed"):
        return run_state
    errors = int(consecutive_errors or 0)
    period = int(period_sec or 60)
    has_old = bool(has_display_rows)
    if errors >= FAIL_THRESHOLD and not has_old:
        return "FAILED"
    if not last_success:
        return "STALE"
    if not round_ok:
        return "STALE"
    api_age = int(now) - int(last_success)
    if api_age > 2 * period:
        return "STALE"
    if api_age > period:
        return "DELAYED"
    return "LIVE"


def field_age_sec(now, last_success, source_timestamp, source_timestamp_missing):
    """年龄取 last_success 与字段自己的上游时间中更大的那个。

    上游没有时间时只用 last_success，不用 db_written_at。
    """
    ages = []
    if last_success:
        ages.append(int(now) - int(last_success))
    if source_timestamp and not source_timestamp_missing:
        ages.append(int(now) - int(source_timestamp))
    if not ages:
        return None
    return max(ages)


def token_is_stale(age_sec, period_sec, halt=False, market_closed=False):
    if halt or market_closed:
        return False
    if age_sec is None:
        return True
    return age_sec > 2 * int(period_sec)


def equity_session_closed(now):
    """美股代币 24/5：周五 20:00 ET 到周日 20:00 ET 为休市。"""
    dt = datetime.fromtimestamp(int(now), _NY)
    wd = dt.weekday()
    minutes = dt.hour * 60 + dt.minute
    if wd == 5:
        return True
    if wd == 6 and minutes < 20 * 60:
        return True
    if wd == 4 and minutes >= 20 * 60:
        return True
    return False


def num_changed(a, b):
    if a is None or a == "":
        return not (b is None or b == "")
    if b is None or b == "":
        return True
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return str(a) != str(b)
    if not math.isfinite(fa) or not math.isfinite(fb):
        return True
    scale = max(abs(fa), abs(fb), 1e-18)
    return abs(fa - fb) / scale > 1e-9


def diverge_flag(gmgn_price, ds_price, ratio=DIVERGE_RATIO):
    try:
        g = float(gmgn_price)
        d = float(ds_price)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(g) or not math.isfinite(d) or g <= 0 or d <= 0:
        return 0
    return 1 if abs(d - g) / g > ratio else 0


def adjusted_anchor(bid, ask, multiplier):
    """原始买卖价的中间价 × currentMultiplier。没有的一侧就用另一侧。"""
    def f(x):
        if x is None or x == "":
            return None
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(v):
            return None
        return v

    b, a, m = f(bid), f(ask), f(multiplier)
    if m is None:
        m = 1.0
    if b is not None and a is not None:
        mid = (b + a) / 2.0
    elif b is not None:
        mid = b
    elif a is not None:
        mid = a
    else:
        return None
    return mid * m


def parse_rfc3339(s):
    if not s or not isinstance(s, str):
        return None
    text = s.strip().replace("Z", "+00:00")
    if "." in text:
        head, tail = text.split(".", 1)
        frac = []
        rest = []
        for i, ch in enumerate(tail):
            if ch.isdigit() and not rest:
                frac.append(ch)
            else:
                rest = list(tail[i:])
                break
        text = head + "." + "".join(frac[:6]) + "".join(rest)
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except ValueError:
        return None


def decode_latest_round(hexdata):
    """AggregatorV3 latestRoundData()：answer, updatedAt。"""
    h = hexdata[2:] if isinstance(hexdata, str) and hexdata.startswith("0x") else hexdata
    if not isinstance(h, str) or len(h) < 64 * 4:
        raise ValueError("short latestRoundData")
    words = [int(h[i:i + 64], 16) for i in range(0, 64 * 4, 64)]
    answer = words[1]
    if answer >= 2 ** 255:
        answer -= 2 ** 256
    return answer, words[3]


def feed_symbol(name):
    """'Robinhood AAPL / USD' 或 'Robinhood DELL-USD' → AAPL / DELL。"""
    if not name or not str(name).startswith("Robinhood"):
        return None
    n = str(name)[len("Robinhood"):].strip()
    n = n.replace("/ USD", "").replace("-USD", "").strip()
    n = n.split()[0] if n else ""
    return n.upper() or None


def ensure_catalog(con):
    for source, chain, period in catalog():
        con.execute(
            "INSERT INTO source_health(source, chain, period_sec) VALUES(?,?,?) "
            "ON CONFLICT(source, chain) DO UPDATE SET period_sec=excluded.period_sec",
            (source, chain, period),
        )


def touch_heartbeat(con, now):
    con.execute("UPDATE source_health SET collector_heartbeat=?", (int(now),))


def mark_ui_fetched(con, now):
    """只由前端上报调用。采集器不写这一列。"""
    con.execute("UPDATE source_health SET ui_fetched_at=?", (int(now),))


_QUIET_STATES = ("cooldown", "rate_limited", "unsupported")


def record_result(
    con, source, chain, ok, started, finished,
    rows_received=0, hot_changed=0, cold_changed=0,
    source_timestamp=None, source_timestamp_missing=True,
    error=None, wrote_db=False,
    rows_parsed=0, rows_written=0, new_addresses=0, events_written=0,
    run_state=None, request_ok=None,
):
    row = con.execute(
        "SELECT attempts, successes, consecutive_errors, has_display_rows, last_change_at "
        "FROM source_health WHERE source=? AND chain=?",
        (source, chain),
    ).fetchone()
    if row is None:
        ensure_catalog(con)
        row = con.execute(
            "SELECT attempts, successes, consecutive_errors, has_display_rows, last_change_at "
            "FROM source_health WHERE source=? AND chain=?",
            (source, chain),
        ).fetchone()
    attempts = int(row["attempts"] or 0) + 1
    latency = max(0, int((finished - started) * 1000))
    state = run_state or ("healthy" if ok else "failed")
    req_ok = (1 if ok else 0) if request_ok is None else (1 if request_ok else 0)
    if ok:
        changed = int(hot_changed or 0) + int(cold_changed or 0)
        last_change = int(finished) if changed else row["last_change_at"]
        ts = None if source_timestamp_missing else source_timestamp
        con.execute(
            """UPDATE source_health SET
                 last_attempt=?, last_success=?, round_ok=1,
                 source_timestamp=?, source_timestamp_missing=?,
                 db_written_at=CASE WHEN ? THEN ? ELSE db_written_at END,
                 rows_received=?, rows_parsed=?, rows_written=?,
                 new_addresses=?, events_written=?, request_ok=?, run_state=?,
                 hot_changed=?, cold_changed=?, latency_ms=?,
                 consecutive_errors=0, last_error=?,
                 attempts=?, successes=?, has_display_rows=1, last_change_at=?
               WHERE source=? AND chain=?""",
            (
                int(started), int(finished),
                ts, 1 if source_timestamp_missing else 0,
                1 if wrote_db else 0, int(finished),
                int(rows_received), int(rows_parsed), int(rows_written),
                int(new_addresses), int(events_written), req_ok, state,
                int(hot_changed), int(cold_changed), latency,
                (str(error)[:400] if error else None),
                attempts, int(row["successes"] or 0) + 1, last_change,
                source, chain,
            ),
        )
        con.execute(
            "INSERT INTO source_latency(source, chain, ts, latency_ms) VALUES(?,?,?,?)",
            (source, chain, int(finished), latency),
        )
    else:
        # 冷却和不受支持不累加失败次数，避免把整条链打成 FAILED。
        if state in _QUIET_STATES:
            errors = int(row["consecutive_errors"] or 0)
        else:
            errors = int(row["consecutive_errors"] or 0) + 1
        # 传输失败不改写上一轮 rows_received。zero_write 是请求成功但没落账，要记下这次收到的行数。
        received_sql = "rows_received=?, " if state == "zero_write" else ""
        received_args = (int(rows_received),) if state == "zero_write" else ()
        con.execute(
            f"""UPDATE source_health SET
                 last_attempt=?, round_ok=0, latency_ms=?,
                 consecutive_errors=?, last_error=?, attempts=?,
                 {received_sql}rows_parsed=?, rows_written=?,
                 new_addresses=?, events_written=?, request_ok=?, run_state=?,
                 hot_changed=0, cold_changed=0
               WHERE source=? AND chain=?""",
            (
                int(started), latency,
                errors,
                (error or "error")[:400],
                attempts,
                *received_args,
                int(rows_parsed), int(rows_written),
                int(new_addresses), int(events_written), req_ok, state,
                source, chain,
            ),
        )


def prune_latency(con, now, keep_sec=3600):
    con.execute("DELETE FROM source_latency WHERE ts < ?", (int(now) - keep_sec,))


def p95(values):
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, math.ceil(0.95 * len(s)) - 1))
    return s[idx]


def p95_for(con, source, chain, now, window=120):
    rows = con.execute(
        "SELECT latency_ms FROM source_latency WHERE source=? AND chain=? AND ts>=?",
        (source, chain, int(now) - window),
    ).fetchall()
    return p95([r[0] if not isinstance(r, sqlite3.Row) else r["latency_ms"] for r in rows])
