#!/usr/bin/env python3
"""Rebuild candle finalized status, daily_metrics, streak, N-day returns, qualified_at.

Independent oracle lives in audit-market-days.py (does not import TypeScript).
Repair goes through rh_v2/market_research.rebuild_research_facts — no hand UPDATE
of streak / returns / qualified_at.

Usage:
  python3 scripts/rebuild-market-finalized.py audit
  python3 scripts/rebuild-market-finalized.py repair
  python3 scripts/rebuild-market-finalized.py verify
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RH = os.path.join(ROOT, "rh_v2")
DB_PATH = os.path.join(RH, "market.sqlite")
sys.path.insert(0, RH)

import importlib.util

import market_research as R  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "audit_market_days", os.path.join(ROOT, "scripts", "audit-market-days.py")
)
oracle = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(oracle)

DAY = 86400
WINDOW = 100 * DAY
NS = (1, 2, 3, 5, 7, 10, 14)
MUST = [
    ("PUMPGU", "sol", "HppB5rMgVsUqua42N2TEDcjwy7gLuAm6dq5qMSLZpump"),
    ("HEARTH", "base", "0x2feb099d4cae58f8e54b513ecea4a5572a68a4ff"),
]


def utc_iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def utc_full(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: str, write: bool) -> sqlite3.Connection:
    uri = f"file:{path}" if write else f"file:{path}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


def old_rule_finalized(ts: int, fetched_at: int | None, finalized_at: int | None, is_closed: int | None, now: int) -> bool:
    """Bug: calendar closed at read/migration now counted as closed."""
    end = ts + DAY
    if finalized_at is not None and int(finalized_at) >= end:
        return True
    if fetched_at is not None and int(fetched_at) >= end:
        return True
    if is_closed:
        return True
    return end <= now


def candle_rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    cols = {r["name"] for r in con.execute("PRAGMA table_info(token_candle)")}
    extra = ", is_closed" if "is_closed" in cols else ", 0 AS is_closed"
    fin = ", finalized_at" if "finalized_at" in cols else ", NULL AS finalized_at"
    return list(
        con.execute(
            f"SELECT chain, address, candle_open_ts AS ts, close, fetched_at{fin}{extra} FROM token_candle"
        )
    )


def blast(con: sqlite3.Connection, now: int) -> dict:
    rows = candle_rows(con)
    hist_candles = 0
    curr_candles = 0
    hist_tokens: set[tuple[str, str]] = set()
    curr_tokens: set[tuple[str, str]] = set()
    dates: dict[str, int] = {}
    unknown = 0
    unknown_tokens: set[tuple[str, str]] = set()
    for row in rows:
        ts = int(row["ts"])
        fetched = None if row["fetched_at"] is None else int(row["fetched_at"])
        finalized = None if row["finalized_at"] is None else int(row["finalized_at"])
        is_closed = int(row["is_closed"] or 0)
        proved = R.observation_proves_final(ts, fetched) or R.observation_proves_final(ts, finalized)
        stored_final = bool(is_closed) or (
            finalized is not None and finalized >= ts + DAY
        )
        if old_rule_finalized(ts, fetched, finalized, is_closed, now) and not proved:
            hist_candles += 1
            hist_tokens.add((row["chain"], row["address"]))
            d = utc_iso(ts) or "?"
            dates[d] = dates.get(d, 0) + 1
        if stored_final and not proved:
            curr_candles += 1
            curr_tokens.add((row["chain"], row["address"]))
        if ts + DAY <= now and not proved:
            unknown += 1
            unknown_tokens.add((row["chain"], row["address"]))
    return {
        "historically_affected_candles": hist_candles,
        "historically_affected_tokens": len(hist_tokens),
        "currently_incorrect_candles": curr_candles,
        "currently_incorrect_tokens": len(curr_tokens),
        "unproven_calendar_closed_candles": unknown,
        "unproven_calendar_closed_tokens": len(unknown_tokens),
        "date_distribution": dict(sorted(dates.items())),
        "sample_incorrect_tokens": sorted(f"{c}:{a}" for c, a in list(curr_tokens)[:20]),
        "sample_unproven_tokens": sorted(f"{c}:{a}" for c, a in list(unknown_tokens)[:20]),
    }


def metrics_snapshot(con: sqlite3.Connection) -> dict:
    def one(sql: str, args=()):
        row = con.execute(sql, args).fetchone()
        return None if row is None else row[0]

    return {
        "token_candle": one("SELECT COUNT(*) FROM token_candle"),
        "finalized_is_closed": one("SELECT COUNT(*) FROM token_candle WHERE is_closed=1"),
        "finalized_at_set": one("SELECT COUNT(*) FROM token_candle WHERE finalized_at IS NOT NULL"),
        "daily_metrics": one("SELECT COUNT(*) FROM daily_metrics"),
        "streak_positive": one("SELECT COUNT(*) FROM daily_metrics WHERE streak >= 1"),
        "streak_zero": one("SELECT COUNT(*) FROM daily_metrics WHERE streak = 0"),
        "streak_null": one("SELECT COUNT(*) FROM daily_metrics WHERE streak IS NULL"),
        "return_1d_null": None,
        "return_2d_null": one("SELECT COUNT(*) FROM daily_metrics WHERE return_2d IS NULL"),
        "return_3d_null": one("SELECT COUNT(*) FROM daily_metrics WHERE return_3d IS NULL"),
        "return_5d_null": one("SELECT COUNT(*) FROM daily_metrics WHERE return_5d IS NULL"),
        "qualified_at_set": one("SELECT COUNT(*) FROM token_registry WHERE qualified_at IS NOT NULL"),
        "daily_metrics_qualified": one("SELECT COUNT(*) FROM daily_metrics WHERE qualified_at IS NOT NULL"),
    }


def dump_token(con: sqlite3.Connection, chain: str, address: str, now: int) -> dict:
    tok = con.execute(
        """SELECT COALESCE(t.symbol, r.symbol) AS symbol,
                  t.kline_fetched_at, t.token_created_at, r.token_created_at AS r_created,
                  r.qualified_at, r.kline_backfilled_at,
                  s.liquidity_num, s.liquidity, s.volume_24h, s.liquidity_updated_at
           FROM token_registry r
           LEFT JOIN tokens t ON t.chain=r.chain AND t.address=r.address
           LEFT JOIN token_snapshot s ON s.chain=r.chain AND s.address=r.address
           WHERE r.chain=? AND r.address=?""",
        (chain, address),
    ).fetchone()
    candles = list(
        con.execute(
            """SELECT candle_open_ts, open, high, low, close, volume, fetched_at, finalized_at, is_closed
               FROM token_candle WHERE chain=? AND address=? ORDER BY candle_open_ts""",
            (chain, address),
        )
    )
    dk = list(
        con.execute(
            """SELECT ts, close, fetched_at, finalized_at FROM daily_kline
               WHERE chain=? AND address=? ORDER BY ts""",
            (chain, address),
        )
    )
    dm = con.execute(
        """SELECT as_of_date, streak, return_2d, return_3d, return_5d, qualified_at, calculated_at
           FROM daily_metrics WHERE chain=? AND address=?
           ORDER BY as_of_date DESC LIMIT 1""",
        (chain, address),
    ).fetchone()
    created = None
    if tok:
        created = tok["token_created_at"] or tok["r_created"]
    bars = [
        {
            "ts": int(r["candle_open_ts"]),
            "close": float(r["close"]) if r["close"] is not None else None,
            "fetched_at": None if r["fetched_at"] is None else int(r["fetched_at"]),
            "finalized_at": None if r["finalized_at"] is None else int(r["finalized_at"]),
        }
        for r in candles
        if r["close"] is not None
    ]
    m = oracle.official_metrics([b for b in bars if b["close"] and b["close"] > 0], now, created, 5)
    finalized = m["finalized"]
    returns = {n: oracle.return_n(finalized, n) for n in NS}
    daily = []
    for r in candles:
        ts = int(r["candle_open_ts"])
        fetched = None if r["fetched_at"] is None else int(r["fetched_at"])
        finalized_at = None if r["finalized_at"] is None else int(r["finalized_at"])
        daily.append(
            {
                "date": utc_iso(ts),
                "open_ts": ts,
                "bar_end": ts + DAY,
                "close": r["close"],
                "fetched_at": utc_full(fetched),
                "fetched_at_unix": fetched,
                "finalized_at": utc_full(finalized_at),
                "is_closed": r["is_closed"],
                "finalized": R.bar_status(ts, fetched, now, finalized_at),
                "proved": R.observation_proves_final(ts, fetched) or R.observation_proves_final(ts, finalized_at),
                "source": "token_candle",
            }
        )
    return {
        "chain": chain,
        "address": address,
        "symbol": None if tok is None else tok["symbol"],
        "kline_fetched_at": None if tok is None else utc_full(tok["kline_fetched_at"]),
        "qualified_at": None if tok is None else utc_full(tok["qualified_at"]),
        "qualified_at_unix": None if tok is None else tok["qualified_at"],
        "liquidity": None if tok is None else tok["liquidity_num"] or tok["liquidity"],
        "volume_24h": None if tok is None else tok["volume_24h"],
        "daily_metrics": None if dm is None else dict(dm),
        "independent": {
            "streak": m["streak"],
            "streak_status": m.get("streak_status"),
            "change1d": m["change1d"],
            "returns": returns,
            "last_status": m["last_status"],
            "closed_finalized": m["closed"],
        },
        "daily": daily[-16:],
        "daily_kline_n": len(dk),
        "token_candle_n": len(candles),
    }


def find_symbol(con: sqlite3.Connection, symbol: str) -> list[tuple[str, str, str]]:
    rows = con.execute(
        """SELECT r.chain, r.address, COALESCE(t.symbol, r.symbol) AS symbol
           FROM token_registry r
           LEFT JOIN tokens t ON t.chain=r.chain AND t.address=r.address
           WHERE UPPER(COALESCE(t.symbol, r.symbol)) = ?""",
        (symbol.upper(),),
    ).fetchall()
    return [(r["chain"], r["address"], r["symbol"]) for r in rows]


def streak_counts(con: sqlite3.Connection, now: int) -> dict:
    rows = con.execute(
        """SELECT r.chain, r.address,
                  COALESCE(t.token_created_at, r.token_created_at) AS created
           FROM token_registry r
           LEFT JOIN tokens t ON t.chain=r.chain AND t.address=r.address"""
    ).fetchall()
    bars_map = oracle.load_bars(con)
    pos = zero = insuff = 0
    for row in rows:
        bars = bars_map.get((row["chain"], row["address"]), [])
        m = oracle.official_metrics(bars, now, row["created"], 1)
        st = m.get("streak_status") or oracle.streak_status(m["streak"])
        if st == "POSITIVE_STREAK":
            pos += 1
        elif st == "VALID_ZERO":
            zero += 1
        else:
            insuff += 1
    return {
        "POSITIVE_STREAK": pos,
        "VALID_ZERO": zero,
        "INSUFFICIENT_DATA": insuff,
        "registry": len(rows),
    }


def streak_set_diff(con: sqlite3.Connection, now: int) -> dict:
    """A=daily_metrics positive tokens, B=independent oracle positive tokens."""
    universe = list(
        con.execute(
            """SELECT r.chain, r.address, COALESCE(t.symbol, r.symbol) AS symbol,
                      COALESCE(t.token_created_at, r.token_created_at) AS created,
                      r.qualified_at,
                      d.streak, d.as_of_date, d.eligible
               FROM token_registry r
               LEFT JOIN tokens t ON t.chain=r.chain AND t.address=r.address
               LEFT JOIN daily_metrics d ON d.chain=r.chain AND d.address=r.address"""
        )
    )
    bars_map = oracle.load_bars(con)
    daily: dict[tuple[str, str], sqlite3.Row] = {}
    independent: dict[tuple[str, str], dict] = {}
    rows_by_key: dict[tuple[str, str], sqlite3.Row] = {}
    for row in universe:
        key = (row["chain"], row["address"])
        rows_by_key[key] = row
        if row["streak"] is not None and int(row["streak"]) >= 1:
            daily[key] = row
        metrics = oracle.official_metrics(bars_map.get(key, []), now, row["created"], 1)
        if metrics["streak_status"] == "POSITIVE_STREAK":
            independent[key] = metrics

    def detail(key: tuple[str, str]) -> dict:
        row = rows_by_key[key]
        metrics = oracle.official_metrics(bars_map.get(key, []), now, row["created"], 1)
        return {
            "chain": key[0],
            "address": key[1],
            "symbol": row["symbol"],
            "daily_metrics.streak": row["streak"],
            "daily_metrics.as_of_date": row["as_of_date"],
            "qualified_at": row["qualified_at"],
            "eligible": row["eligible"],
            "oracle_streak": metrics["streak"],
            "oracle_status": metrics["streak_status"],
        }

    a_minus_b = [detail(key) for key in sorted(set(daily) - set(independent))]
    b_minus_a = [detail(key) for key in sorted(set(independent) - set(daily))]
    return {
        "A_daily_positive": len(daily),
        "B_oracle_positive": len(independent),
        "A_minus_B": a_minus_b,
        "B_minus_A": b_minus_a,
        "diff": len(a_minus_b) + len(b_minus_a),
    }


def affected_metrics(con: sqlite3.Connection, now: int, before_bars: dict | None = None) -> dict:
    """Count tokens whose independent streak/N-day would change if using old vs new finalized set."""
    rows = con.execute(
        """SELECT r.chain, r.address,
                  COALESCE(t.token_created_at, r.token_created_at) AS created
           FROM token_registry r
           LEFT JOIN tokens t ON t.chain=r.chain AND t.address=r.address"""
    ).fetchall()
    bars_map = oracle.load_bars(con)
    out = {f"return_{n}d": 0 for n in NS}
    out["streak"] = 0
    out["tokens"] = 0
    for row in rows:
        key = (row["chain"], row["address"])
        bars = bars_map.get(key, [])
        new_m = oracle.official_metrics(bars, now, row["created"], 5)
        old_final = []
        for b in bars:
            if b["close"] is None or b["close"] <= 0:
                continue
            if not oracle.bar_eligible_by_creation(b["ts"], row["created"]):
                continue
            if old_rule_finalized(b["ts"], b.get("fetched_at"), b.get("finalized_at"), 0, now):
                if b["ts"] + DAY <= now:
                    old_final.append(b)
        old_streak = oracle.streak_of(old_final)
        new_streak = new_m["streak"]
        changed = old_streak != new_streak
        for n in NS:
            old_r = oracle.return_n(old_final, n)
            new_r = oracle.return_n(new_m["finalized"], n)
            if old_r != new_r:
                out[f"return_{n}d"] += 1
                changed = True
        if changed:
            out["streak"] += int(old_streak != new_streak)
            out["tokens"] += 1
    return out


def verify_targets(con: sqlite3.Connection, now: int, extra: list[tuple[str, str, str]]) -> dict:
    out = {}
    seen = set()
    for symbol, chain, address in MUST + extra:
        key = f"{chain}:{address}"
        if key in seen:
            continue
        seen.add(key)
        out[symbol if symbol not in out else f"{symbol}:{address[:6]}"] = dump_token(con, chain, address, now)
    homes = find_symbol(con, "HOME")
    for chain, address, symbol in homes:
        out[f"HOME:{chain}:{address[:8]}"] = dump_token(con, chain, address, now)
    return out


def pick_controls(con: sqlite3.Connection, n_affected: int = 5, n_control: int = 5) -> tuple[list, list]:
    now = int(time.time())
    rows = candle_rows(con)
    affected: set[tuple[str, str]] = set()
    clean: set[tuple[str, str]] = set()
    tokens: dict[tuple[str, str], list] = {}
    for row in rows:
        key = (row["chain"], row["address"])
        tokens.setdefault(key, []).append(row)
        proved = R.observation_proves_final(int(row["ts"]), None if row["fetched_at"] is None else int(row["fetched_at"]))
        stored = bool(row["is_closed"])
        if stored and not proved:
            affected.add(key)
    for key, bars in tokens.items():
        if key in affected:
            continue
        if any(R.observation_proves_final(int(b["ts"]), None if b["fetched_at"] is None else int(b["fetched_at"])) for b in bars):
            clean.add(key)
    rng = random.Random(20261002)
    aff = sorted(affected)
    ctl = sorted(clean)
    rng.shuffle(aff)
    rng.shuffle(ctl)
    def label(key):
        row = con.execute(
            "SELECT COALESCE(symbol,'') AS symbol FROM tokens WHERE chain=? AND address=?",
            key,
        ).fetchone()
        return (row["symbol"] if row else "", key[0], key[1])
    return [label(k) for k in aff[:n_affected]], [label(k) for k in ctl[:n_control]]


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "audit"
    now = int(time.time())
    if mode not in ("audit", "repair", "verify"):
        print("usage: rebuild-market-finalized.py [audit|repair|verify]", file=sys.stderr)
        return 2
    write = mode == "repair"
    if write:
        import market_db as mdb
        con = mdb.connect(DB_PATH)
    else:
        con = connect(DB_PATH, write=False)

    report = {
        "mode": mode,
        "now": now,
        "now_iso": utc_full(now),
        "db": DB_PATH,
    }
    report["blast"] = blast(con, now)
    report["metrics_before"] = metrics_snapshot(con)
    report["streak_counts_before"] = streak_counts(con, now)
    report["streak_set_diff_before"] = streak_set_diff(con, now)
    report["affected_metrics"] = affected_metrics(con, now)
    extra_a, extra_c = pick_controls(con)
    report["sample_affected"] = extra_a
    report["sample_controls"] = extra_c
    report["tokens_before"] = verify_targets(con, now, extra_a + extra_c)

    if mode == "repair":
        R.rebuild_research_facts(con, now)
        report["metrics_after"] = metrics_snapshot(con)
        report["blast_after"] = blast(con, now)
        report["streak_counts_after"] = streak_counts(con, now)
        report["streak_set_diff_after"] = streak_set_diff(con, now)
        report["tokens_after"] = verify_targets(con, now, extra_a + extra_c)

    if mode == "verify":
        report["tokens"] = report.pop("tokens_before")

    out_path = os.path.join(ROOT, "scripts", f"rebuild-market-finalized.{mode}.json")
    with open(out_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k: report[k] for k in report if k not in ("tokens_before", "tokens_after", "tokens")}, ensure_ascii=False, indent=2, default=str))
    print(f"wrote {out_path}", file=sys.stderr)
    if not write:
        con.close()
    else:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
