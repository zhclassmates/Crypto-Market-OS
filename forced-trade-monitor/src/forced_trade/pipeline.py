"""Hourly pipeline stages. Frozen order: universe, ingest, features, states, outcomes."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import yaml

from forced_trade.align import HOUR_MS
from forced_trade.db import init_db
from forced_trade.features import build_feature
from forced_trade.http import BinanceClient
from forced_trade.ingest import IngestHour
from forced_trade.metrics import DAY_MS
from forced_trade.outcomes import fill_row
from forced_trade.quality import health_row
from forced_trade.states import evaluate, load_states
from forced_trade.universe import select_universe

ROOT = Path(__file__).resolve().parents[2]

_HEALTH_COLS = (
    "ts", "source", "symbol", "expected_ts", "actual_ts", "age_sec",
    "success", "http_status", "latency_ms", "rows_expected", "rows_got",
    "null_rate", "ts_semantics", "error",
)

_FEATURE_COLS = (
    "symbol", "bar_open_ts", "ret_1h", "ret_4h", "ret_24h",
    "oi_qty_chg_1h", "oi_qty_chg_4h", "oi_qty_chg_24h", "oi_z_7d",
    "oi_chg_1h_z", "abs_ret_1h_z", "funding_8h_equiv", "funding_pct_30d",
    "funding_interval_hours", "interval_source", "funding_rate_type",
    "taker_imbalance_1h", "taker_imbalance_4h", "kline_taker_imbalance_1h",
    "basis_bps", "mark_index_basis_bps", "basis_divergence_bps",
    "basis_z_7d", "btc_ret_1h", "btc_ret_4h", "ret_1h_vs_btc",
    "ret_4h_vs_btc", "volume_pct_30d", "flow_aligned_with_price",
    "data_quality_flag",
)

_OUTCOME_COLS = (
    "symbol", "bar_open_ts", "ret_fwd_1h", "ret_fwd_4h", "ret_fwd_24h",
    "ret_fwd_72h", "ret_fwd_4h_vs_btc", "ret_fwd_24h_vs_btc",
    "ret_fwd_72h_vs_btc", "in_universe", "price_def", "updated_at",
)


def load_settings(path: str | Path | None = None) -> dict:
    return yaml.safe_load((Path(path) if path else ROOT / "config" / "settings.yaml").read_text())


def open_db(cfg: dict, db_override: str | None = None) -> sqlite3.Connection:
    raw = Path(db_override or cfg["db_path"])
    path = raw if raw.is_absolute() else ROOT / raw
    return init_db(path)


def latest_closed_bar(now_ms: int, delay_ms: int) -> int:
    """The hourly bar whose close is at least delay_ms behind now."""
    close_boundary = (int(now_ms) - int(delay_ms)) // HOUR_MS * HOUR_MS
    return close_boundary - HOUR_MS


def _write_health(conn: sqlite3.Connection, rows: list[dict]) -> None:
    q = "INSERT INTO data_health ({0}) VALUES ({1})".format(
        ",".join(_HEALTH_COLS), ",".join("?" for _ in _HEALTH_COLS)
    )
    for row in rows:
        conn.execute(q, [row.get(c) for c in _HEALTH_COLS])


def _universe_symbols(conn: sqlite3.Connection, bar_open_ts: int) -> list[str]:
    rows = conn.execute(
        "SELECT symbol FROM universe_snapshot WHERE ts=? ORDER BY rank", (bar_open_ts,)
    ).fetchall()
    return [r["symbol"] for r in rows]


def refresh_universe(
    conn: sqlite3.Connection,
    client: BinanceClient,
    bar_open_ts: int,
    cfg: dict,
    now_ms: int | None = None,
) -> list[str]:
    """Snapshot the top-N universe for this bar. Existing snapshots are never rewritten."""
    existing = _universe_symbols(conn, bar_open_ts)
    if existing:
        return existing
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    info = client.exchange_info()
    _write_health(conn, [health_row(
        "exchange_info", success=info.error is None, http_status=info.status,
        latency_ms=info.latency_ms, error=info.error, ts_semantics="screener",
        rows_got=len((info.payload or {}).get("symbols", [])) if info.payload else 0,
        now_ms=now,
    )])
    tick = client.ticker_24hr()
    _write_health(conn, [health_row(
        "ticker_24hr", success=tick.error is None, http_status=tick.status,
        latency_ms=tick.latency_ms, error=tick.error, ts_semantics="screener",
        rows_got=len(tick.payload) if isinstance(tick.payload, list) else 0,
        now_ms=now,
    )])
    conn.commit()
    if info.error or tick.error or not info.payload:
        return []
    volumes = {
        row["symbol"]: row.get("quoteVolume")
        for row in (tick.payload if isinstance(tick.payload, list) else [])
    }
    merged = [
        {**sym, "quoteVolume": volumes.get(sym.get("symbol"))}
        for sym in info.payload.get("symbols", [])
    ]
    picked = select_universe(
        merged,
        asof_ms=bar_open_ts,
        top_n=cfg["top_n"],
        min_listing_days=cfg["min_listing_days"],
        quote_asset=cfg["quote_asset"],
        contract_type=cfg["contract_type"],
    )
    for row in picked:
        conn.execute(
            "INSERT OR IGNORE INTO universe_snapshot "
            "(ts, symbol, rank, quote_volume, listing_days, contract_type, status, quote_asset) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["ts"], row["symbol"], row["rank"], row["quote_volume"],
                row["listing_days"], row["contract_type"], row["status"], row["quote_asset"],
            ),
        )
    conn.commit()
    return [r["symbol"] for r in picked]


def ingest_hourly(
    conn: sqlite3.Connection,
    client: BinanceClient,
    symbols: list[str],
    bar_open_ts: int,
    cfg: dict,
    sleep=time.sleep,
) -> None:
    """Fetch every source for the universe plus BTCUSDT. Source failures stay isolated."""
    job = IngestHour(conn, client, bar_open_ts, symbols, cfg, sleep=sleep)
    job.run()
    conn.commit()


def _closes(conn: sqlite3.Connection, symbol: str, since: int, until: int | None = None) -> dict[int, float]:
    sql = "SELECT bar_open_ts, close FROM raw_klines_1h WHERE symbol=? AND bar_open_ts>=?"
    args: list = [symbol, since]
    if until is not None:
        sql += " AND bar_open_ts<=?"
        args.append(until)
    return {r["bar_open_ts"]: r["close"] for r in conn.execute(sql, args)}


def _feature_for(
    conn: sqlite3.Connection, symbol: str, bar_open_ts: int, cfg: dict, since: int, btc_closes: dict
) -> dict:
    krows = conn.execute(
        "SELECT bar_open_ts, close, volume, quote_volume, taker_buy_volume "
        "FROM raw_klines_1h WHERE symbol=? AND bar_open_ts>=?",
        (symbol, since),
    ).fetchall()
    closes = {r["bar_open_ts"]: r["close"] for r in krows}
    quote_volume = {r["bar_open_ts"]: r["quote_volume"] for r in krows}
    kline_taker = {
        r["bar_open_ts"]: (r["taker_buy_volume"], None if r["volume"] is None or r["taker_buy_volume"] is None else r["volume"] - r["taker_buy_volume"])
        for r in krows
    }
    oi = {
        r["bar_open_ts"]: r["oi_qty"]
        for r in conn.execute(
            "SELECT bar_open_ts, oi_qty FROM raw_oi_1h WHERE symbol=? AND bar_open_ts>=?",
            (symbol, since),
        )
    }
    taker = {
        r["bar_open_ts"]: (r["buy_vol"], r["sell_vol"])
        for r in conn.execute(
            "SELECT bar_open_ts, buy_vol, sell_vol FROM raw_taker_1h WHERE symbol=? AND bar_open_ts>=?",
            (symbol, since),
        )
    }
    basis_bps = {
        r["bar_open_ts"]: r["basis_rate"] * 1e4
        for r in conn.execute(
            "SELECT bar_open_ts, basis_rate FROM raw_basis_1h WHERE symbol=? AND bar_open_ts>=?",
            (symbol, since),
        )
        if r["basis_rate"] is not None
    }
    mark = conn.execute(
        "SELECT mark_price, index_price FROM raw_mark WHERE symbol=? AND observed_at<=? "
        "ORDER BY observed_at DESC LIMIT 1",
        (symbol, bar_open_ts + HOUR_MS),
    ).fetchone()
    mark_bps = {}
    if mark and mark["index_price"]:
        mark_bps[bar_open_ts] = (mark["mark_price"] / mark["index_price"] - 1) * 1e4
    events = [
        {"funding_time": r["funding_time"], "funding_rate": r["funding_rate"], "rate_type": r["rate_type"]}
        for r in conn.execute(
            "SELECT funding_time, funding_rate, rate_type FROM raw_funding WHERE symbol=?",
            (symbol,),
        )
    ]
    snapshots = [
        {"observed_at": r["observed_at"], "funding_interval_hours": r["funding_interval_hours"],
         "present_in_payload": r["present_in_payload"]}
        for r in conn.execute(
            "SELECT observed_at, funding_interval_hours, present_in_payload "
            "FROM funding_info_snapshot WHERE symbol=? ORDER BY observed_at",
            (symbol,),
        )
    ]
    return build_feature(
        symbol, bar_open_ts, closes, oi, taker, kline_taker, basis_bps, mark_bps,
        quote_volume, events, snapshots, btc_closes,
        z_window=cfg["zscore_window_hours"], z_min=cfg["zscore_min_obs"],
        funding_days=cfg["funding_lookback_days"],
        divergence_bps=cfg["basis_divergence_flag_bps"],
        default_interval=cfg["default_funding_interval_hours"],
    )


def build_features(conn: sqlite3.Connection, bar_open_ts: int, cfg: dict, out=print) -> int:
    symbols = _universe_symbols(conn, bar_open_ts)
    if not symbols:
        return 0
    since = bar_open_ts - cfg["funding_lookback_days"] * DAY_MS
    btc_closes = _closes(conn, cfg["btc_symbol"], since)
    written = 0
    q = "INSERT OR REPLACE INTO features_1h ({0}) VALUES ({1})".format(
        ",".join(_FEATURE_COLS), ",".join("?" for _ in _FEATURE_COLS)
    )
    for sym in symbols:
        try:
            row = _feature_for(conn, sym, bar_open_ts, cfg, since, btc_closes)
        except Exception as exc:  # one bad symbol must not stop the bar
            out(f"build_features {sym} {bar_open_ts}: {exc}")
            continue
        conn.execute(q, [row.get(c) for c in _FEATURE_COLS])
        written += 1
    conn.commit()
    return written


def label_states(conn: sqlite3.Connection, bar_open_ts: int, cfg: dict, now_ms: int | None = None, out=print) -> int:
    """Evaluate every state for the bar. S4 stays hit=0 reason=disabled.

    Hits go to alerts; a same-symbol same-state hit inside the cooldown window
    is kept but flagged cooldown_suppressed=1. States are never deleted.
    """
    symbols = _universe_symbols(conn, bar_open_ts)
    if not symbols:
        return 0
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    spec = load_states()
    cooldown_ms = int(spec.get("global", {}).get("cooldown_hours", 12)) * HOUR_MS
    written = 0
    for sym in symbols:
        feat = conn.execute(
            "SELECT * FROM features_1h WHERE symbol=? AND bar_open_ts=?",
            (sym, bar_open_ts),
        ).fetchone()
        if feat is None:
            continue
        try:
            results = evaluate(dict(feat), spec)
        except Exception as exc:
            out(f"label_states {sym} {bar_open_ts}: {exc}")
            continue
        for res in results:
            conn.execute(
                "INSERT OR REPLACE INTO states_1h (symbol, bar_open_ts, state, hit, reason) "
                "VALUES (?, ?, ?, ?, ?)",
                (sym, bar_open_ts, res["state"], res["hit"], res["reason"]),
            )
            written += 1
            if not res["hit"]:
                continue
            recent = conn.execute(
                "SELECT COUNT(*) AS c FROM alerts WHERE symbol=? AND state=? "
                "AND cooldown_suppressed=0 AND bar_open_ts>? AND bar_open_ts<?",
                (sym, res["state"], bar_open_ts - cooldown_ms, bar_open_ts),
            ).fetchone()["c"]
            conn.execute(
                "INSERT OR IGNORE INTO alerts (symbol, bar_open_ts, state, cooldown_suppressed, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (sym, bar_open_ts, res["state"], 1 if recent else 0, now),
            )
    conn.commit()
    return written


def fill_outcomes(conn: sqlite3.Connection, cfg: dict, now_close_floor: int | None = None) -> int:
    """Fill closed horizons only, for decision-time universe members only."""
    if now_close_floor is None:
        row = conn.execute("SELECT MAX(bar_open_ts) AS m FROM raw_klines_1h").fetchone()
        if row is None or row["m"] is None:
            return 0
        now_close_floor = row["m"]
    universe = {
        (r["symbol"], r["ts"]) for r in conn.execute("SELECT symbol, ts FROM universe_snapshot")
    }
    horizon_ms = 72 * HOUR_MS
    candidates = conn.execute(
        """
        SELECT f.symbol, f.bar_open_ts FROM features_1h f
        JOIN universe_snapshot u ON u.symbol = f.symbol AND u.ts = f.bar_open_ts
        WHERE f.bar_open_ts >= ?
           OR NOT EXISTS (
             SELECT 1 FROM outcomes o WHERE o.symbol = f.symbol AND o.bar_open_ts = f.bar_open_ts
           )
        """,
        (now_close_floor - horizon_ms,),
    ).fetchall()
    btc = cfg["btc_symbol"]
    now = int(time.time() * 1000)
    written = 0
    q = "INSERT OR REPLACE INTO outcomes ({0}) VALUES ({1})".format(
        ",".join(_OUTCOME_COLS), ",".join("?" for _ in _OUTCOME_COLS)
    )
    for cand in candidates:
        sym, ts = cand["symbol"], cand["bar_open_ts"]
        closes = {
            sym: _closes(conn, sym, ts, ts + horizon_ms),
            btc: _closes(conn, btc, ts, ts + horizon_ms),
        }
        row = fill_row(sym, ts, closes, universe, btc_symbol=btc, now_close_floor=now_close_floor)
        if row is None:
            continue
        row["updated_at"] = now
        conn.execute(q, [row.get(c) for c in _OUTCOME_COLS])
        written += 1
    conn.commit()
    return written


def run_hourly(
    conn: sqlite3.Connection,
    client: BinanceClient,
    cfg: dict,
    now_ms: int | None = None,
    bar_open_ts: int | None = None,
    sleep=time.sleep,
    out=print,
) -> dict:
    """One full hourly pass. Runs after the close plus decision_delay_sec, never on HH:00:00."""
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    if bar_open_ts is None:
        bar_open_ts = latest_closed_bar(now, int(cfg.get("decision_delay_sec", 120)) * 1000)
    symbols = refresh_universe(conn, client, bar_open_ts, cfg, now_ms=now)
    if not symbols:
        out(f"run_hourly: no universe for {bar_open_ts}; aborting")
        return {"bar_open_ts": bar_open_ts, "symbols": 0}
    ingest_symbols = list(symbols)
    if cfg["btc_symbol"] not in ingest_symbols:
        ingest_symbols.append(cfg["btc_symbol"])
    ingest_hourly(conn, client, ingest_symbols, bar_open_ts, cfg, sleep=sleep)
    n_feat = build_features(conn, bar_open_ts, cfg, out=out)
    n_states = label_states(conn, bar_open_ts, cfg, now_ms=now, out=out)
    n_out = fill_outcomes(conn, cfg, now_close_floor=bar_open_ts)
    summary = {
        "bar_open_ts": bar_open_ts,
        "symbols": len(symbols),
        "features": n_feat,
        "states": n_states,
        "outcomes": n_out,
    }
    out(f"run_hourly {summary}")
    return summary
