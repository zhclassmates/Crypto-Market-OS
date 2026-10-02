#!/usr/bin/env python3
"""Independent Oracle for market ranking N-day return and consecutive-up streak.

Does not import collector streak helpers. Reads rh_v2/market.sqlite daily_kline
and recomputes from raw closed UTC daily candles.

Contract (user spec):
  ts is candle OPEN (UTC midnight).
  closed iff ts + 86400 <= now.
  return_N = last_closed_close / close_N_contiguous_daily_intervals_ago - 1
    requires N+1 closed candles with no calendar gap; else None.
  streak = count of adjacent closed days from the tail where close[t] > close[t-1];
    equal close or down day or calendar gap stops. Independent of selectedDays.
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
NS = (1, 2, 3, 5, 7, 10, 14, 30)
MUST = [
    "PUMPGU",
    "STOCKER",
    "SAPLING",
    "PRIORS",
    "UDR",
    "PARLEY",
    "SPIKE",
    "ATLAS",
    "DRMR",
    "CINEMA",
]


def utc_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=10000")
    return con


def closed_from_daily(bars: list[tuple[int, float]], now: int) -> list[tuple[int, float]]:
    """User-spec closed set: candle end <= now, close > 0. No fetch-time filter."""
    by_ts: dict[int, float] = {}
    for ts, close in bars:
        if close is None or close <= 0:
            continue
        ts = int(ts)
        if ts + DAY > now:
            continue
        by_ts[ts] = float(close)
    return sorted(by_ts.items())


def closed_current_code(
    bars: list[tuple[int, float]],
    now: int,
    kline_fetched_at: int | None,
    created_at: int | None,
) -> list[tuple[int, float]]:
    """Replay src/lib/rh/streak.ts closedBars."""
    if kline_fetched_at is None:
        return []
    by_ts: dict[int, float] = {}
    for ts, close in bars:
        if close is None or close <= 0:
            continue
        ts = int(ts)
        end = ts + DAY
        if end > now:
            continue
        if kline_fetched_at < end:
            continue
        if created_at is not None and end <= created_at:
            continue
        by_ts[ts] = float(close)
    return sorted(by_ts.items())


def return_n(closed: list[tuple[int, float]], n: int) -> float | None:
    if len(closed) < n + 1:
        return None
    window = closed[-(n + 1) :]
    for i in range(1, len(window)):
        if window[i][0] - window[i - 1][0] != DAY:
            return None
    base = window[0][1]
    last = window[-1][1]
    if base <= 0 or last <= 0:
        return None
    return last / base - 1


def streak_of(closed: list[tuple[int, float]]) -> int:
    streak = 0
    for i in range(len(closed) - 1, 0, -1):
        if closed[i][0] - closed[i - 1][0] != DAY:
            break
        if closed[i][1] > closed[i - 1][1]:
            streak += 1
        else:
            break
    return streak


def change1d(closed: list[tuple[int, float]]) -> float | None:
    if len(closed) < 2:
        return None
    prev, last = closed[-2], closed[-1]
    if last[0] - prev[0] != DAY or prev[1] <= 0:
        return None
    return last[1] / prev[1] - 1


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


def load_bars(con: sqlite3.Connection) -> dict[tuple[str, str], list[tuple[int, float]]]:
    out: dict[tuple[str, str], list[tuple[int, float]]] = {}
    for row in con.execute("SELECT chain, address, ts, close FROM daily_kline"):
        try:
            close = float(row["close"])
        except (TypeError, ValueError):
            continue
        out.setdefault((row["chain"], row["address"]), []).append((int(row["ts"]), close))
    return out


def display_created(token_created: int | None, pair_created: int | None) -> int | None:
    if token_created and token_created > 0:
        return int(token_created)
    if pair_created and pair_created > 0:
        return int(pair_created)
    return None


def token_payload(row: sqlite3.Row, bars: list[tuple[int, float]], now: int) -> dict:
    created = display_created(row["token_created_at"], row["pair_created_at"])
    fetched = row["kline_fetched_at"]
    fetched_i = int(fetched) if fetched is not None else None
    spec = closed_from_daily(bars, now)
    code = closed_current_code(bars, now, fetched_i, created)
    liq = row["liquidity_num"]
    if liq is None and row["liquidity"] not in (None, ""):
        try:
            liq = float(row["liquidity"])
        except (TypeError, ValueError):
            liq = None
    liq_age = None
    if row["liquidity_updated_at"] is not None:
        liq_age = now - int(row["liquidity_updated_at"])
    returns_spec = {n: return_n(spec, n) for n in NS}
    returns_code = {n: return_n(code, n) for n in NS}
    return {
        "chain": row["chain"],
        "address": row["address"],
        "symbol": row["symbol"],
        "kline_fetched_at": fetched_i,
        "created_at": created,
        "liquidity": liq,
        "liquidity_age_sec": liq_age,
        "raw_bars": len(bars),
        "unfinished": sum(1 for ts, _ in bars if ts + DAY > now),
        "closed_spec": len(spec),
        "closed_code": len(code),
        "spec_dates": [utc_iso(ts) for ts, _ in spec[-12:]],
        "spec_closes": [c for _, c in spec[-12:]],
        "code_dates": [utc_iso(ts) for ts, _ in code[-12:]],
        "code_closes": [c for _, c in code[-12:]],
        "streak_spec": streak_of(spec),
        "streak_code": streak_of(code),
        "change1d_spec": change1d(spec),
        "change1d_code": change1d(code),
        "returns_spec": returns_spec,
        "returns_code": returns_code,
        "pc_24h": row["pc_24h"],
        "kline_stale_today": fetched_i is None or fetched_i < (now - now % DAY),
        "liq_ok": liq is not None and liq >= 50_000,
        "liq_fresh": liq_age is not None and liq_age <= 300,
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
    today = now - now % DAY
    rng = random.Random(20261002)

    con = connect(db_path)
    rows = load_universe(con)
    bars_map = load_bars(con)
    registry_n = con.execute("SELECT COUNT(*) AS n FROM token_registry").fetchone()["n"]
    kline_tokens = con.execute("SELECT COUNT(DISTINCT chain || ':' || address) AS n FROM daily_kline").fetchone()["n"]
    meta = {r["k"]: r["v"] for r in con.execute("SELECT k, v FROM market_meta")}
    con.close()

    payloads = []
    for row in rows:
        payloads.append(token_payload(row, bars_map.get((row["chain"], row["address"]), []), now))

    # Eligibility waterfall for each N
    waterfall = {}
    for n in NS:
        enough = [p for p in payloads if p["returns_spec"][n] is not None]
        enough_code = [p for p in payloads if p["returns_code"][n] is not None]
        liq = [p for p in enough if p["liq_ok"]]
        fresh = [p for p in liq if p["liq_fresh"]]
        waterfall[n] = {
            "registry": registry_n,
            "enough_candle_history_spec": len(enough),
            "enough_candle_history_code": len(enough_code),
            "liquidity_qualified_among_enough": len(liq),
            "fresh_qualified_among_liq": len(fresh),
            "final_n_day_eligible_spec": len(enough),
        }

    named = []
    missing = []
    for name in MUST:
        hits = find_named(rows, name)
        if not hits:
            missing.append(name)
            continue
        for row in hits:
            named.append(token_payload(row, bars_map.get((row["chain"], row["address"]), []), now))

    # 20 random tokens that have at least one closed candle
    with_closed = [p for p in payloads if p["closed_spec"] >= 2]
    sample = rng.sample(with_closed, min(20, len(with_closed)))

    # Divergence between user-spec closed set and current closedBars
    diverge = []
    for p in payloads:
        if p["streak_spec"] != p["streak_code"] or p["returns_spec"] != p["returns_code"]:
            diverge.append(
                {
                    "symbol": p["symbol"],
                    "address": p["address"],
                    "streak_spec": p["streak_spec"],
                    "streak_code": p["streak_code"],
                    "closed_spec": p["closed_spec"],
                    "closed_code": p["closed_code"],
                    "kline_fetched_at": p["kline_fetched_at"],
                    "kline_stale_today": p["kline_stale_today"],
                    "ret5_spec": p["returns_spec"][5],
                    "ret5_code": p["returns_code"][5],
                }
            )

    def slim(p: dict) -> dict:
        return {
            "symbol": p["symbol"],
            "chain": p["chain"],
            "address": p["address"],
            "kline_fetched_at": p["kline_fetched_at"],
            "kline_stale_today": p["kline_stale_today"],
            "created_at": p["created_at"],
            "raw_bars": p["raw_bars"],
            "unfinished": p["unfinished"],
            "closed_spec": p["closed_spec"],
            "closed_code": p["closed_code"],
            "closed_dates": p["spec_dates"],
            "closed_closes": p["spec_closes"],
            "code_dates": p["code_dates"],
            "streak_spec": p["streak_spec"],
            "streak_code": p["streak_code"],
            "change1d_spec": p["change1d_spec"],
            "change1d_code": p["change1d_code"],
            "returns_spec": {str(k): v for k, v in p["returns_spec"].items()},
            "returns_code": {str(k): v for k, v in p["returns_code"].items()},
            "pc_24h": p["pc_24h"],
        }

    top_spec_5 = sorted(
        [p for p in payloads if p["returns_spec"][5] is not None],
        key=lambda p: p["returns_spec"][5],
        reverse=True,
    )[:10]
    top_code_5 = sorted(
        [p for p in payloads if p["returns_code"][5] is not None],
        key=lambda p: p["returns_code"][5],
        reverse=True,
    )[:10]

    report = {
        "now": now,
        "now_iso": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "today_utc": utc_iso(today),
        "meta": {
            "last_market_update": meta.get("last_market_update"),
            "last_kline_update": meta.get("last_kline_update"),
            "last_price_update": meta.get("last_price_update"),
        },
        "registry": registry_n,
        "kline_tokens": kline_tokens,
        "waterfall": waterfall,
        "diverge_count": len(diverge),
        "diverge_sample": diverge[:15],
        "named_missing": missing,
        "named": [slim(p) for p in named],
        "random20": [slim(p) for p in sample],
        "top10_5d_spec": [
            {"symbol": p["symbol"], "address": p["address"], "ret5": p["returns_spec"][5], "streak": p["streak_spec"]}
            for p in top_spec_5
        ],
        "top10_5d_code": [
            {"symbol": p["symbol"], "address": p["address"], "ret5": p["returns_code"][5], "streak": p["streak_code"]}
            for p in top_code_5
        ],
    }

    out_path = os.path.join(root, "scripts", "audit-market-days.out.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"now {report['now_iso']} today_utc {report['today_utc']}")
    print(f"registry {registry_n} kline_tokens {kline_tokens}")
    print(f"last_kline_update {meta.get('last_kline_update')}")
    print("waterfall:")
    for n in NS:
        w = waterfall[n]
        print(
            f"  {n}D spec={w['enough_candle_history_spec']} code={w['enough_candle_history_code']} "
            f"liq={w['liquidity_qualified_among_enough']} fresh={w['fresh_qualified_among_liq']}"
        )
    print(f"spec vs closedBars diverge: {len(diverge)}")
    print("named missing:", missing)
    print("\n=== MUST tokens ===")
    for p in named:
        print(
            f"{p['symbol']:12} {p['chain']:10} closed_spec={p['closed_spec']:2} closed_code={p['closed_code']:2} "
            f"streak_spec={p['streak_spec']} streak_code={p['streak_code']} "
            f"1D={pct(p['returns_spec'][1])} 5D={pct(p['returns_spec'][5])} 7D={pct(p['returns_spec'][7])} "
            f"stale={p['kline_stale_today']}"
        )
        print(f"  dates  {p['spec_dates']}")
        print(f"  closes {[round(c, 8) if c < 1 else round(c, 6) for c in p['spec_closes']]}")
        if p["spec_dates"] != p["code_dates"]:
            print(f"  CODE dates {p['code_dates']}")
    print("\n=== top10 5D spec ===")
    for i, p in enumerate(top_spec_5, 1):
        print(f"{i:2} {p['symbol']:12} ret5={pct(p['returns_spec'][5])} streak={p['streak_spec']}")
    print("\n=== top10 5D current-code closedBars ===")
    for i, p in enumerate(top_code_5, 1):
        print(f"{i:2} {p['symbol']:12} ret5={pct(p['returns_code'][5])} streak={p['streak_code']}")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
