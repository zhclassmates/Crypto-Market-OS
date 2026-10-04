#!/usr/bin/env python3
"""Independent Phase 4 oracle comparison using only synthetic fixtures/temp SQLite."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rh_v2"))

import market_db as db  # noqa: E402
import market_lanes as lanes  # noqa: E402
import market_research as research  # noqa: E402

DAY = 86400


def oracle_trench(row):
    out = dict(row)
    if "volume_24h" in row:
        out["volume"] = row["volume_24h"]
    if "swaps_24h" in row:
        out["swaps"] = row["swaps_24h"]
    return out


def oracle_merge(current, patch):
    out = dict(current)
    for key, value in patch.items():
        out[key] = value
    return out


def oracle_metrics(bars, now, n):
    classified = []
    for bar in bars:
        if bar["ts"] + DAY > now:
            state = "OPEN"
        elif bar.get("observed") is not None and bar["observed"] >= bar["ts"] + DAY:
            state = "FINALIZED"
        else:
            state = "PROVISIONAL"
        classified.append({**bar, "state": state})
    calendar = [b for b in classified if b["state"] != "OPEN"]
    if calendar and calendar[-1]["state"] != "FINALIZED":
        return None, None
    final = [b for b in classified if b["state"] == "FINALIZED"]
    streak = None
    if len(final) >= 2 and final[-1]["ts"] - final[-2]["ts"] == DAY:
        streak = 0
        for i in range(len(final) - 1, 0, -1):
            if final[i]["ts"] - final[i - 1]["ts"] != DAY or final[i]["close"] <= final[i - 1]["close"]:
                break
            streak += 1
    ret = None
    if len(final) >= n + 1:
        tail = final[-(n + 1):]
        if all(tail[i]["ts"] - tail[i - 1]["ts"] == DAY for i in range(1, len(tail))):
            ret = tail[-1]["close"] / tail[0]["close"] - 1
    return streak, ret


def main():
    checks = {}
    fixture = {"address": "A", "volume_24h": 0, "swaps_24h": 0, "liquidity": 5}
    checks["trench_normalization"] = research.normalize_trench_row(fixture) == oracle_trench(fixture)

    with tempfile.TemporaryDirectory() as tmp:
        con = db.connect(str(Path(tmp) / "oracle.sqlite"))
        trench = {"new_creation": [{
            "address": "A", "price": 1, "volume_24h": 12, "swaps_24h": 3,
            "liquidity": 5, "holder_count": 4,
        }], "near_completion": [], "completed": []}
        signal = [{
            "token_address": "A", "market_cap": 99,
            "data": {"price": 888, "volume_24h": 0, "swaps_24h": 0},
            "cur_data": {"liquidity": 6, "holder_count": 7, "top_10_holder_rate": None},
        }]
        lanes.apply_trench_payload(con, "sol", trench, 100)
        lanes.apply_signal_items(con, "sol", signal, 101)
        actual = dict(con.execute(
            "SELECT price,volume_24h,swaps,liquidity,market_cap,holders,top10_holder_rate FROM token_snapshot"
        ).fetchone())
        expected = oracle_merge(
            {"price": "1", "volume_24h": "12", "swaps": 3, "liquidity": "5", "market_cap": None, "holders": 4, "top10_holder_rate": None},
            {"liquidity": "6", "market_cap": "99", "holders": 7, "top10_holder_rate": None},
        )
        checks["trench_then_signal_merge"] = actual == expected

        con.execute("DELETE FROM token_snapshot")
        con.execute("DELETE FROM token_registry")
        con.execute("DELETE FROM tokens")
        lanes.apply_signal_items(con, "sol", signal, 200)
        lanes.apply_trench_payload(con, "sol", trench, 201)
        actual_reverse = dict(con.execute(
            "SELECT price,volume_24h,swaps,liquidity,market_cap,holders,top10_holder_rate FROM token_snapshot"
        ).fetchone())
        expected_reverse = oracle_merge(
            {"price": None, "volume_24h": None, "swaps": None, "liquidity": "6", "market_cap": "99", "holders": 7, "top10_holder_rate": None},
            {"price": "1", "volume_24h": "12", "swaps": 3, "liquidity": "5", "holders": 4},
        )
        checks["signal_then_trench_merge"] = actual_reverse == expected_reverse

        base = 1_700_006_400 - (1_700_006_400 % DAY)
        before = base + 4 * DAY - 1
        midnight = base + 4 * DAY
        rows = [{"time": base + i * DAY, "close": i + 1, "high": i + 1} for i in range(4)]
        research.write_daily_candles(con, "sol", "A", rows, before)
        research.refresh_metrics(con, "sol", "A", before)
        prod_before = con.execute("SELECT streak,return_2d,calculated_at FROM daily_metrics WHERE address='A'").fetchone()
        oracle_before = oracle_metrics([
            {"ts": base + i * DAY, "close": i + 1, "observed": before} for i in range(4)
        ], before, 2)
        checks["utc_2359"] = (prod_before["streak"], prod_before["return_2d"]) == oracle_before
        research.refresh_daily_metrics_for_utc_day(con, midnight)
        prod_midnight = con.execute("SELECT streak,return_2d,calculated_at FROM daily_metrics WHERE address='A'").fetchone()
        oracle_midnight = oracle_metrics([
            {"ts": base + i * DAY, "close": i + 1, "observed": before} for i in range(4)
        ], midnight, 2)
        checks["utc_0000"] = (prod_midnight["streak"], prod_midnight["return_2d"]) == oracle_midnight
        checks["daily_metrics_freshness"] = research.daily_metrics_fresh(prod_midnight["calculated_at"], midnight)
        con.close()

    result = {"checks": checks, "production_equals_independent_oracle": all(checks.values())}
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["production_equals_independent_oracle"] else 1)


if __name__ == "__main__":
    main()
