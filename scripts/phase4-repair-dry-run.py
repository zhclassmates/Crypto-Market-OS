#!/usr/bin/env python3
"""Phase 4 read-only impact/rebuild plan. Never opens production SQLite writable."""
import argparse
import json
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

DAY = 86400
WINDOW = 100 * DAY


def proves(ts, observed):
    return observed is not None and observed >= ts + DAY and ts >= observed - WINDOW


def status(row, now):
    ts = int(row["ts"])
    if ts + DAY > now:
        return "OPEN"
    if proves(ts, row["finalized_at"]) or proves(ts, row["fetched_at"]):
        return "FINALIZED"
    return "PROVISIONAL"


def after_creation(ts, created):
    """Bars before the token's UTC creation day are not evidence for that token."""
    try:
        created = int(created)
    except (TypeError, ValueError):
        return True
    return created <= 0 or ts >= created - created % DAY


def oracle_metrics(rows, now, created=None):
    classified = [
        (int(r["ts"]), float(r["close"]), status(r, now))
        for r in rows
        if r["close"] is not None and float(r["close"]) > 0 and after_creation(int(r["ts"]), created)
    ]
    calendar = [r for r in classified if r[2] != "OPEN"]
    if calendar and calendar[-1][2] != "FINALIZED":
        return {"streak": None, "return_2d": None, "return_3d": None, "return_5d": None}
    closed = [r for r in classified if r[2] == "FINALIZED"]
    streak = None
    if len(closed) >= 2 and closed[-1][0] - closed[-2][0] == DAY:
        streak = 0
        for i in range(len(closed) - 1, 0, -1):
            if closed[i][0] - closed[i - 1][0] != DAY or closed[i][1] <= closed[i - 1][1]:
                break
            streak += 1

    def ret(days):
        if len(closed) < days + 1:
            return None
        tail = closed[-(days + 1):]
        if any(tail[i][0] - tail[i - 1][0] != DAY for i in range(1, len(tail))):
            return None
        return tail[-1][1] / tail[0][1] - 1

    return {"streak": streak, "return_2d": ret(2), "return_3d": ret(3), "return_5d": ret(5)}


def same(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= 1e-12 * max(1.0, abs(float(a)), abs(float(b)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(Path(__file__).resolve().parents[1] / "rh_v2" / "market.sqlite"))
    parser.add_argument("--now", type=int, default=int(time.time()))
    parser.add_argument("--sample", type=int, default=10)
    args = parser.parse_args()
    uri = Path(args.db).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]

    snapshots = {
        "rows": con.execute("SELECT COUNT(*) FROM token_snapshot").fetchone()[0],
        "blank_volume_24h": con.execute("SELECT COUNT(*) FROM token_snapshot WHERE volume_24h IS NULL OR volume_24h='' ").fetchone()[0],
        "null_swaps": con.execute("SELECT COUNT(*) FROM token_snapshot WHERE swaps IS NULL").fetchone()[0],
        "null_holders": con.execute("SELECT COUNT(*) FROM token_snapshot WHERE holders IS NULL").fetchone()[0],
    }
    latest_sources = con.execute(
        """WITH latest AS (
             SELECT chain,address,source,seen_at,
                    ROW_NUMBER() OVER (PARTITION BY chain,address ORDER BY seen_at DESC,id DESC) AS rn
             FROM discovery_event)
           SELECT source, COUNT(*) AS n FROM latest WHERE rn=1 GROUP BY source ORDER BY source"""
    ).fetchall()
    snapshots["latest_event_source"] = {r["source"]: r["n"] for r in latest_sources}
    samples = [dict(r) for r in con.execute(
        """SELECT chain,address,ts,price,volume_24h,swaps,liquidity,market_cap,holders
           FROM token_snapshot
           WHERE volume_24h IS NULL OR volume_24h='' OR swaps IS NULL OR holders IS NULL
           ORDER BY chain,address LIMIT ?""",
        (args.sample,),
    )]

    bars = defaultdict(list)
    for row in con.execute("SELECT chain,address,ts,close,fetched_at,finalized_at FROM daily_kline ORDER BY chain,address,ts"):
        bars[(row["chain"], row["address"])].append(row)
    created = {
        (r["chain"], r["address"]): r["created"]
        for r in con.execute(
            """SELECT g.chain, g.address,
                      COALESCE(NULLIF(t.token_created_at, 0), g.token_created_at) AS created
               FROM token_registry g
               LEFT JOIN tokens t ON t.chain = g.chain AND t.address = g.address"""
        )
    }
    stale = []
    for row in con.execute("SELECT * FROM daily_metrics"):
        key = (row["chain"], row["address"])
        expected = oracle_metrics(bars.get(key, []), args.now, created.get(key))
        mismatches = [key for key, value in expected.items() if not same(row[key], value)]
        fresh = row["calculated_at"] is not None and args.now - args.now % DAY <= int(row["calculated_at"]) <= args.now
        if mismatches or not fresh:
            stale.append({
                "chain": row["chain"], "address": row["address"],
                "calculated_at": row["calculated_at"], "fresh": fresh,
                "mismatches": mismatches,
                "before": {k: row[k] for k in expected}, "proposed_after": expected,
            })

    mismatch_rows = [row for row in stale if row["mismatches"]]
    stale.sort(key=lambda row: (not bool(row["mismatches"]), row["chain"], row["address"]))
    result = {
        "mode": "READ_ONLY_DRY_RUN",
        "database": str(Path(args.db).resolve()),
        "now": args.now,
        "integrity_check": integrity,
        "snapshot_impact": snapshots,
        "snapshot_samples_before": samples,
        "snapshot_proposed_after": {
            "future_writes": "endpoint-specific field patch with per-field source/updated_at",
            "historical_volume_swaps": "UNRECOVERABLE_FROM_CURRENT_DB: discovery_event did not retain these values; requires normal scheduled recollection after deployment",
            "historical_price_liquidity_market_cap_holders": "partially reconstructable from discovery_event, but not applied by this script",
        },
        "daily_metrics_impact": {
            "invalid_freshness_rows": len(stale),
            "value_mismatch_rows": len(mismatch_rows),
            "value_mismatch_fields": sum(len(r["mismatches"]) for r in stale),
            "sample_before_and_proposed_after": stale[:args.sample],
            "proposed_action": "run collector UTC-day refresh/rebuild only after deploying verified code",
        },
        "production_write_performed": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
