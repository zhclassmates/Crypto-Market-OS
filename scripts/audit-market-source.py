#!/usr/bin/env python3
"""Oracle 2: re-fetch GMGN raw 1d kline and compare with SQLite per (chain, address).

Does not read production TypeScript. Writes back only when the last calendar-closed
close disagrees, so yesterday can become FINALIZED with the source close.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

DAY = 86400
SAMPLES = [
    ("PUMPGU", "sol", "HppB5rMgVsUqua42N2TEDcjwy7gLuAm6dq5qMSLZpump"),
    ("STOCKER", "eth", "0x75e2fc69ff2ac12af65ba7d321bbf4f878c535d2"),
    ("DRMR", "sol", "7Xgc5RacHtGzfhw2HukUBk5V986yBbvshr7rrCoopump"),
    ("HEARTH", "base", "0x2feb099d4cae58f8e54b513ecea4a5572a68a4ff"),
    ("SAPLING", "sol", "BZFYNPeQAEW3HWQ4DNsTVahC1n4ZjTgn6jB2nnBbB96W"),
]


def utc_full(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def gmgn_kline(chain: str, address: str, frm: int, to: int) -> list[dict]:
    cli = os.environ.get("GMGN_CLI", "gmgn-cli")
    cmd = [
        cli, "market", "kline",
        "--chain", chain, "--address", address,
        "--resolution", "1d", "--from", str(frm), "--to", str(to), "--raw",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip() or f"exit {r.returncode}")
    data = json.loads(r.stdout)
    if isinstance(data, dict):
        rows = data.get("list") or data.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("list") or []
        return rows if isinstance(rows, list) else []
    return data if isinstance(data, list) else []


def unix_ts(v) -> int | None:
    if v is None or v is False or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = int(v)
    else:
        s = str(v).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            n = int(float(s))
        except ValueError:
            try:
                n = int(datetime.fromisoformat(s).timestamp())
            except ValueError:
                return None
    if n >= 10**12:
        n = n // 1000
    return n


def parse_source(rows: list[dict]) -> list[dict]:
    out = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        ts = unix_ts(raw.get("time"))
        try:
            close = float(raw.get("close"))
        except (TypeError, ValueError):
            continue
        if ts is None or close <= 0:
            continue
        ts = ts - ts % DAY
        out.append({
            "ts": ts,
            "close": close,
            "open": raw.get("open"),
            "high": raw.get("high"),
            "low": raw.get("low"),
            "volume": raw.get("volume"),
            "amount": raw.get("amount"),
            "closed": raw.get("closed") or raw.get("is_closed") or raw.get("final"),
            "raw_keys": sorted(raw.keys()),
        })
    by = {row["ts"]: row for row in out}
    return [by[k] for k in sorted(by)]


def bar_status(ts: int, fetched_at: int | None, now: int, finalized_at: int | None) -> str:
    end = ts + DAY
    if finalized_at is not None and int(finalized_at) >= end:
        return "FINALIZED"
    if end > now:
        return "OPEN"
    if fetched_at is not None and int(fetched_at) >= end:
        return "FINALIZED"
    return "PROVISIONAL"


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(root, "rh_v2", "market.sqlite")
    now = int(time.time())
    today = now - now % DAY
    yesterday = today - DAY
    write_back = "--write" in sys.argv

    con = sqlite3.connect(db_path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=10000")

    results = []
    for symbol, chain, address in SAMPLES:
        db_rows = list(
            con.execute(
                """SELECT ts, close, fetched_at, finalized_at FROM daily_kline
                   WHERE chain=? AND address=? ORDER BY ts""",
                (chain, address),
            )
        )
        db_map = {int(r["ts"]): r for r in db_rows}
        try:
            src_raw = gmgn_kline(chain, address, now - 12 * DAY, now)
            src = parse_source(src_raw)
            err = None
        except Exception as e:
            src = []
            src_raw = []
            err = str(e)
        time.sleep(1.1)

        y_db = db_map.get(yesterday)
        y_src = next((r for r in src if r["ts"] == yesterday), None)
        db_close = None if y_db is None else float(y_db["close"])
        src_close = None if y_src is None else float(y_src["close"])
        diff = None
        if db_close is not None and src_close is not None:
            diff = src_close - db_close
        status = None
        if y_db is not None:
            status = bar_status(yesterday, y_db["fetched_at"], now, y_db["finalized_at"])
        close_match = (
            db_close is not None
            and src_close is not None
            and abs(db_close - src_close) / max(abs(src_close), 1e-18) < 1e-8
        )
        verdict = "FAIL" if err else ("PASS" if close_match and status == "FINALIZED" else "FAIL")
        wrote = False
        if write_back and src and err is None:
            sys.path.insert(0, os.path.join(root, "rh_v2"))
            import market_research as R
            payload = []
            for row in src:
                payload.append({
                    "time": row["ts"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                    "amount": row["amount"],
                })
            written = R.commit_kline_fetch(con, chain, address, payload, now, True)
            con.commit()
            wrote = written > 0
            y_db2 = con.execute(
                """SELECT close, fetched_at, finalized_at FROM daily_kline
                   WHERE chain=? AND address=? AND ts=?""",
                (chain, address, yesterday),
            ).fetchone()
            if y_db2 is not None:
                db_close = float(y_db2["close"])
                status = bar_status(yesterday, y_db2["fetched_at"], now, y_db2["finalized_at"])
                close_match = src_close is not None and abs(db_close - src_close) / max(abs(src_close), 1e-18) < 1e-8
                verdict = "PASS" if close_match and status == "FINALIZED" else "FAIL"
            db_rows = list(
                con.execute(
                    """SELECT ts, close, fetched_at, finalized_at FROM daily_kline
                       WHERE chain=? AND address=? ORDER BY ts""",
                    (chain, address),
                )
            )

        item = {
            "symbol": symbol,
            "chain": chain,
            "address": address,
            "error": err,
            "source_keys": src[0]["raw_keys"] if src else [],
            "yesterday": utc_iso(yesterday),
            "db_close": db_close,
            "source_close": src_close,
            "diff": diff,
            "db_status": status,
            "db_fetched_at": utc_full(y_db["fetched_at"]) if y_db else None,
            "close_match": close_match,
            "wrote": wrote,
            "verdict": verdict,
            "source_tail": [
                {"date": utc_iso(r["ts"]), "ts": r["ts"], "close": r["close"]}
                for r in src[-6:]
            ],
            "db_tail": [
                {
                    "date": utc_iso(int(r["ts"])),
                    "ts": int(r["ts"]),
                    "close": r["close"],
                    "fetched_at": utc_full(r["fetched_at"]),
                    "status": bar_status(int(r["ts"]), r["fetched_at"], now, r["finalized_at"]),
                }
                for r in db_rows[-6:]
            ],
        }
        results.append(item)
        print(
            f"{symbol:8} {chain:10} {address[:8]}…{address[-6:]} "
            f"db={db_close} src={src_close} status={status} match={close_match} {verdict}"
            + (f" err={err}" if err else "")
        )

    con.close()
    out_path = os.path.join(root, "scripts", "audit-market-source.out.json")
    with open(out_path, "w") as f:
        json.dump({"now": now, "yesterday": utc_iso(yesterday), "write_back": write_back, "results": results}, f, indent=2, default=str)
    print(f"wrote {out_path}")
    return 0 if all(r["verdict"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
