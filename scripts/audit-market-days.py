#!/usr/bin/env python3
"""Oracle 1: DB oracle for market ranking.

Independent of TypeScript production functions and collector streak helpers.
Reads rh_v2/market.sqlite raw daily_kline / token_candle and recomputes
OPEN / PROVISIONAL / FINALIZED, N-day return, and streak.
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import sys
import time
from datetime import datetime, timezone

DAY = 86400
KLINE_FETCH_WINDOW_SEC = 100 * DAY
NS = (1, 2, 3, 5, 7, 10, 14, 30)
MUST = [
    "PUMPGU",
    "STOCKER",
    "DRMR",
    "HEARTH",
    "SAPLING",
    "PRIORS",
    "UDR",
    "PARLEY",
    "SPIKE",
    "ATLAS",
    "CINEMA",
]
LOW_BASE_CLOSE = 1e-8
EXTREME_ABS_RETURN = 50


def utc_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def utc_full(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=10000")
    return con


def utc_day_start(now: int) -> int:
    return now - now % DAY


def bar_end(ts: int) -> int:
    return int(ts) + DAY


def bar_eligible_by_creation(bar_ts: int, created_at: int | None) -> bool:
    if created_at is None or created_at <= 0:
        return True
    return int(bar_ts) >= utc_day_start(int(created_at))


def observation_proves_final(bar_open: int, observed_at: int | None) -> bool:
    if observed_at is None:
        return False
    obs = int(observed_at)
    opened = int(bar_open)
    if obs < opened + DAY:
        return False
    if opened < obs - KLINE_FETCH_WINDOW_SEC:
        return False
    return True


def bar_status(ts: int, fetched_at: int | None, now: int, finalized_at: int | None = None) -> str:
    if bar_end(ts) > now:
        return "OPEN"
    if observation_proves_final(ts, finalized_at) or observation_proves_final(ts, fetched_at):
        return "FINALIZED"
    return "PROVISIONAL"


def classify(bars: list[dict], now: int, created_at: int | None) -> list[dict]:
    by_ts: dict[int, dict] = {}
    for bar in bars:
        ts = int(bar["ts"])
        close = bar["close"]
        if close is None or close <= 0:
            continue
        if not bar_eligible_by_creation(ts, created_at):
            continue
        status = bar_status(ts, bar.get("fetched_at"), now, bar.get("finalized_at"))
        by_ts[ts] = {
            "ts": ts,
            "close": float(close),
            "end": bar_end(ts),
            "fetched_at": bar.get("fetched_at"),
            "finalized_at": bar.get("finalized_at"),
            "status": status,
        }
    return [by_ts[k] for k in sorted(by_ts)]


def return_n(finalized: list[dict], n: int) -> float | None:
    if len(finalized) < n + 1:
        return None
    window = finalized[-(n + 1) :]
    for i in range(1, len(window)):
        if window[i]["ts"] - window[i - 1]["ts"] != DAY:
            return None
    base = window[0]["close"]
    last = window[-1]["close"]
    if base <= 0 or last <= 0:
        return None
    return last / base - 1


def streak_of(finalized: list[dict]) -> int | None:
    if len(finalized) < 2 or finalized[-1]["ts"] - finalized[-2]["ts"] != DAY:
        return None
    streak = 0
    for i in range(len(finalized) - 1, 0, -1):
        if finalized[i]["ts"] - finalized[i - 1]["ts"] != DAY:
            break
        if finalized[i]["close"] > finalized[i - 1]["close"]:
            streak += 1
        else:
            break
    return streak


def streak_status(streak: int | None) -> str:
    if streak is None:
        return "INSUFFICIENT_DATA"
    if streak >= 1:
        return "POSITIVE_STREAK"
    return "VALID_ZERO"


def change1d(finalized: list[dict]) -> float | None:
    if len(finalized) < 2:
        return None
    prev, last = finalized[-2], finalized[-1]
    if last["ts"] - prev["ts"] != DAY or prev["close"] <= 0:
        return None
    return last["close"] / prev["close"] - 1


def official_metrics(bars: list[dict], now: int, created_at: int | None, n: int) -> dict:
    classified = classify(bars, now, created_at)
    calendar = [b for b in classified if b["status"] != "OPEN"]
    finalized = [b for b in classified if b["status"] == "FINALIZED"]
    last_status = calendar[-1]["status"] if calendar else None
    if not calendar or calendar[-1]["status"] != "FINALIZED":
        return {
            "streak": None,
            "streak_status": "INSUFFICIENT_DATA",
            "change1d": None,
            "changeNd": None,
            "closed": len(finalized),
            "last_status": last_status,
            "classified": classified,
            "finalized": finalized,
            "calendar": calendar,
        }
    ret = return_n(finalized, n)
    chg = change1d(finalized)
    flags = []
    if len(finalized) >= 2 and finalized[-1]["ts"] - finalized[-2]["ts"] == DAY:
        if 0 < finalized[-2]["close"] < LOW_BASE_CLOSE:
            flags.append("LOW_BASE")
    if chg is not None and abs(chg) >= EXTREME_ABS_RETURN:
        flags.append("EXTREME_RETURN")
    if ret is not None and abs(ret) >= EXTREME_ABS_RETURN and "EXTREME_RETURN" not in flags:
        flags.append("EXTREME_RETURN")
    streak = streak_of(finalized)
    return {
        "streak": streak,
        "streak_status": streak_status(streak),
        "change1d": chg,
        "changeNd": ret,
        "closed": len(finalized),
        "last_status": last_status,
        "classified": classified,
        "finalized": finalized,
        "calendar": calendar,
        "quality_flags": flags,
    }


def pct(v: float | None) -> str:
    if v is None:
        return "null"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.4f}%"


def load_universe(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        con.execute(
            """
            SELECT r.chain, r.address,
                   COALESCE(t.symbol, r.symbol) AS symbol,
                   COALESCE(t.token_created_at, r.token_created_at) AS token_created_at,
                   t.pair_created_at,
                   t.kline_fetched_at,
                   s.liquidity_num, s.liquidity, s.liquidity_updated_at, s.ts AS snap_ts,
                   s.pc_24h
            FROM token_registry r
            LEFT JOIN tokens t ON t.chain = r.chain AND t.address = r.address
            LEFT JOIN token_snapshot s ON s.chain = r.chain AND s.address = r.address
            """
        )
    )


def table_cols(con: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}


def load_bars(con: sqlite3.Connection) -> dict[tuple[str, str], list[dict]]:
    cols = table_cols(con, "daily_kline")
    has_fetched = "fetched_at" in cols
    sql = (
        "SELECT chain, address, ts, close, fetched_at, finalized_at FROM daily_kline"
        if has_fetched
        else "SELECT chain, address, ts, close, NULL AS fetched_at, NULL AS finalized_at FROM daily_kline"
    )
    out: dict[tuple[str, str], list[dict]] = {}
    for row in con.execute(sql):
        try:
            close = float(row["close"])
        except (TypeError, ValueError):
            continue
        out.setdefault((row["chain"], row["address"]), []).append(
            {
                "ts": int(row["ts"]),
                "close": close,
                "fetched_at": None if row["fetched_at"] is None else int(row["fetched_at"]),
                "finalized_at": None if row["finalized_at"] is None else int(row["finalized_at"]),
            }
        )
    return out


def display_created(token_created: int | None, pair_created: int | None) -> int | None:
    if token_created and token_created > 0:
        return int(token_created)
    if pair_created and pair_created > 0:
        return int(pair_created)
    return None


def token_payload(row: sqlite3.Row, bars: list[dict], now: int) -> dict:
    created = display_created(row["token_created_at"], row["pair_created_at"])
    fetched = row["kline_fetched_at"]
    fetched_i = int(fetched) if fetched is not None else None
    m5 = official_metrics(bars, now, created, 5)
    returns = {n: official_metrics(bars, now, created, n)["changeNd"] for n in NS}
    classified = m5["classified"]
    last_bars = classified[-8:]
    return {
        "chain": row["chain"],
        "address": row["address"],
        "symbol": row["symbol"],
        "kline_fetched_at": fetched_i,
        "created_at": created,
        "raw_bars": len(bars),
        "last_status": m5["last_status"],
        "closed_finalized": m5["closed"],
        "streak": m5["streak"],
        "change1d": m5["change1d"],
        "returns": returns,
        "quality_flags": m5.get("quality_flags", []),
        "bar_detail": [
            {
                "date": utc_iso(b["ts"]),
                "ts": b["ts"],
                "barEnd": b["end"],
                "close": b["close"],
                "fetched_at": utc_full(b["fetched_at"]),
                "finalized_at": utc_full(b["finalized_at"]),
                "status": b["status"],
            }
            for b in last_bars
        ],
        "kline_stale_today": fetched_i is None or fetched_i < utc_day_start(now),
    }


def find_named(rows: list[sqlite3.Row], name: str) -> list[sqlite3.Row]:
    up = name.upper()
    hits = [r for r in rows if (r["symbol"] or "").upper() == up]
    if hits:
        return hits
    return [r for r in rows if (r["symbol"] or "").upper().startswith(up)]


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(root, "rh_v2", "market.sqlite")
    now = int(time.time())
    today = utc_day_start(now)
    rng = random.Random(20261002)

    con = connect(db_path)
    rows = load_universe(con)
    bars_map = load_bars(con)
    registry_n = con.execute("SELECT COUNT(*) AS n FROM token_registry").fetchone()["n"]
    kline_tokens = con.execute("SELECT COUNT(DISTINCT chain || ':' || address) AS n FROM daily_kline").fetchone()["n"]
    y_open = today - DAY
    y_stats = con.execute(
        """SELECT COUNT(*) AS n,
                  SUM(CASE WHEN fetched_at IS NOT NULL AND fetched_at >= ? THEN 1 ELSE 0 END) AS fin
           FROM token_candle WHERE candle_open_ts=?""",
        (today, y_open),
    ).fetchone()
    meta = {r["k"]: r["v"] for r in con.execute("SELECT k, v FROM market_meta")}
    con.close()

    payloads = []
    for row in rows:
        payloads.append(token_payload(row, bars_map.get((row["chain"], row["address"]), []), now))

    waterfall = {}
    for n in NS:
        enough = [p for p in payloads if p["returns"][n] is not None]
        waterfall[n] = {"registry": registry_n, "enough_finalized": len(enough)}

    named = []
    missing = []
    for name in MUST:
        hits = find_named(rows, name)
        if not hits:
            missing.append(name)
            continue
        for row in hits:
            named.append(token_payload(row, bars_map.get((row["chain"], row["address"]), []), now))

    with_final = [p for p in payloads if p["closed_finalized"] >= 2]
    sample = rng.sample(with_final, min(20, len(with_final))) if with_final else []

    top5 = sorted(
        [p for p in payloads if p["returns"][5] is not None],
        key=lambda p: p["returns"][5],
        reverse=True,
    )[:10]

    report = {
        "now": now,
        "now_iso": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "today_utc": utc_iso(today),
        "yesterday_utc": utc_iso(y_open),
        "meta": {
            "last_market_update": meta.get("last_market_update"),
            "last_kline_update": meta.get("last_kline_update"),
        },
        "registry": registry_n,
        "kline_tokens": kline_tokens,
        "yesterday_bars": y_stats["n"],
        "yesterday_finalized": y_stats["fin"],
        "waterfall": waterfall,
        "named_missing": missing,
        "named": named,
        "random20": sample,
        "top10_5d": [
            {
                "symbol": p["symbol"],
                "chain": p["chain"],
                "address": p["address"],
                "ret5": p["returns"][5],
                "streak": p["streak"],
                "last_status": p["last_status"],
                "quality_flags": p["quality_flags"],
            }
            for p in top5
        ],
    }

    out_path = os.path.join(root, "scripts", "audit-market-days.out.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"now {report['now_iso']} today_utc {report['today_utc']}")
    print(f"registry {registry_n} kline_tokens {kline_tokens}")
    print(f"yesterday bars {y_stats['n']} finalized {y_stats['fin']}")
    print("waterfall:")
    for n in NS:
        print(f"  {n}D finalized-complete={waterfall[n]['enough_finalized']}")
    print("named missing:", missing)
    print("\n=== MUST tokens ===")
    for p in named:
        print(
            f"{p['symbol']:12} {p['chain']:10} {p['address'][:8]}…{p['address'][-6:]} "
            f"status={p['last_status']} finalized={p['closed_finalized']:2} "
            f"streak={p['streak']} 1D={pct(p['returns'][1])} 5D={pct(p['returns'][5])} "
            f"flags={p['quality_flags']}"
        )
        for b in p["bar_detail"]:
            print(
                f"  {b['date']} ts={b['ts']} end={b['barEnd']} close={b['close']} "
                f"fetched={b['fetched_at']} status={b['status']}"
            )
    print("\n=== top10 5D finalized ===")
    for i, p in enumerate(top5, 1):
        print(f"{i:2} {p['symbol']:12} {p['address'][:10]} ret5={pct(p['returns'][5])} streak={p['streak']} {p['last_status']}")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
