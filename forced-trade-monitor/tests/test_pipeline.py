"""End-to-end hour over recorded fixtures. No network, all in tmp sqlite."""

import tempfile
import unittest
from pathlib import Path

from forced_trade.db import init_db
from forced_trade.http import BinanceClient, FixtureTransport
from forced_trade.pipeline import (
    build_features,
    fill_outcomes,
    ingest_hourly,
    label_states,
    latest_closed_bar,
    load_settings,
    refresh_universe,
    run_hourly,
)

FIXTURE = Path(__file__).parent / "fixtures" / "hour_responses.json"

BAR = 1_699_999_200_000          # hour open, UTC aligned
HOUR = 3_600_000
BAR_CLOSE = BAR + HOUR           # 1_700_002_800_000
DELAY_MS = 120_000
NOW1 = BAR_CLOSE + DELAY_MS      # first run moment
NOW2 = BAR_CLOSE + HOUR + DELAY_MS  # second run moment


def _cfg(tmp: str) -> dict:
    cfg = load_settings()
    cfg["db_path"] = str(Path(tmp) / "t.sqlite")
    cfg["top_n"] = 2
    cfg["request_sleep_ms"] = 0
    return cfg


def _client() -> BinanceClient:
    return BinanceClient("https://fixture.local", transport=FixtureTransport.from_file(FIXTURE))


def _counts(conn) -> dict:
    tables = (
        "raw_klines_1h", "raw_oi_1h", "raw_taker_1h", "raw_basis_1h", "raw_funding",
        "raw_mark", "funding_info_snapshot", "universe_snapshot", "features_1h",
        "states_1h", "alerts", "outcomes", "raw_revisions",
    )
    return {
        t: conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
        for t in tables
    }


class PipelineTest(unittest.TestCase):
    def test_full_hour_then_next_hour(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp)
            conn = init_db(cfg["db_path"])
            client = _client()
            sleep = lambda _s: None

            # SOLUSDT has a snapshot observed BEFORE the funding event at BAR:
            # it must be used. This run's own fundingInfo (observed after the
            # event) must NOT leak into it.
            conn.execute(
                "INSERT INTO funding_info_snapshot "
                "(symbol, observed_at, funding_interval_hours, cap, floor, present_in_payload, payload_hash) "
                "VALUES ('SOLUSDT', ?, 4, NULL, NULL, 1, 'seed')",
                (BAR - 3 * HOUR,),
            )
            conn.commit()

            # --- hour 1 -------------------------------------------------
            summary = run_hourly(conn, client, cfg, now_ms=NOW1, sleep=sleep, out=lambda *_: None)
            self.assertEqual(summary["bar_open_ts"], BAR)
            self.assertEqual(summary["symbols"], 2)  # ETHUSDT, SOLUSDT

            uni = conn.execute(
                "SELECT symbol, rank FROM universe_snapshot WHERE ts=? ORDER BY rank", (BAR,)
            ).fetchall()
            self.assertEqual([r["symbol"] for r in uni], ["ETHUSDT", "SOLUSDT"])

            # OI end-of-period timestamp must land on bar_open_ts.
            oi = conn.execute(
                "SELECT bar_open_ts, api_ts, oi_qty FROM raw_oi_1h WHERE symbol='ETHUSDT'"
            ).fetchone()
            self.assertEqual(oi["bar_open_ts"], BAR)
            self.assertEqual(oi["api_ts"], BAR_CLOSE)
            self.assertEqual(oi["oi_qty"], 5000.0)

            # Off-universe symbols are never fetched.
            for path, params in client.transport.calls:
                self.assertNotEqual(params.get("symbol"), "BNBUSDT")

            # kline taker is stored but never substituted into official taker.
            feat = conn.execute(
                "SELECT * FROM features_1h WHERE symbol='ETHUSDT' AND bar_open_ts=?", (BAR,)
            ).fetchone()
            self.assertIsNotNone(feat)
            self.assertAlmostEqual(feat["taker_imbalance_1h"], (600 - 400) / 1000)
            self.assertAlmostEqual(feat["kline_taker_imbalance_1h"], (600 - 400) / 1000)

            # funding: event at BAR uses only snapshots observed before it.
            # ETHUSDT has a fundingInfo snapshot observed NOW1 (> event), so default 8h.
            self.assertEqual(feat["funding_interval_hours"], 8.0)
            self.assertEqual(feat["interval_source"], "default")

            # SOLUSDT: the seed snapshot (observed before the event) wins over
            # this hour's snapshot (observed after the event). No future data.
            feat_sol = conn.execute(
                "SELECT * FROM features_1h WHERE symbol='SOLUSDT' AND bar_open_ts=?", (BAR,)
            ).fetchone()
            self.assertEqual(feat_sol["funding_interval_hours"], 4.0)
            self.assertEqual(feat_sol["interval_source"], "snapshot")
            self.assertAlmostEqual(feat_sol["funding_8h_equiv"], 0.0003 * 8 / 4)

            # states: S4 stays disabled; all five states labelled.
            states = {
                r["state"]: (r["hit"], r["reason"])
                for r in conn.execute(
                    "SELECT state, hit, reason FROM states_1h WHERE symbol='ETHUSDT' AND bar_open_ts=?",
                    (BAR,),
                )
            }
            self.assertEqual(len(states), 5)
            self.assertEqual(states["delever_done"], (0, "disabled"))

            # health rows per source, not one global flag.
            sources = {
                r["source"] for r in conn.execute("SELECT DISTINCT source FROM data_health")
            }
            self.assertTrue({"exchange_info", "ticker_24hr", "klines", "oi", "taker",
                             "basis", "funding", "funding_info", "mark"} <= sources)

            # --- idempotent re-run of the same hour ---------------------
            before = _counts(conn)
            run_hourly(conn, client, cfg, now_ms=NOW1 + 60_000, sleep=sleep, out=lambda *_: None)
            after = _counts(conn)
            for table, n in before.items():
                if table == "funding_info_snapshot":
                    continue  # a new observed_at row per run is expected
                self.assertEqual(after[table], n, f"{table} grew on re-run")

            # --- hour 2 ---------------------------------------------------
            summary2 = run_hourly(conn, client, cfg, now_ms=NOW2, sleep=sleep, out=lambda *_: None)
            self.assertEqual(summary2["bar_open_ts"], BAR + HOUR)

            # outcomes for hour-1 bars: only 1h horizon closed by hour-2 close.
            out = conn.execute(
                "SELECT * FROM outcomes WHERE symbol='ETHUSDT' AND bar_open_ts=?", (BAR,)
            ).fetchone()
            self.assertIsNotNone(out)
            self.assertAlmostEqual(out["ret_fwd_1h"], 110 / 100 - 1)
            self.assertIsNone(out["ret_fwd_4h"])  # not closed yet
            self.assertEqual(out["in_universe"], 1)

            # SOLUSDT was in universe at BAR: outcome exists.
            out_sol = conn.execute(
                "SELECT * FROM outcomes WHERE symbol='SOLUSDT' AND bar_open_ts=?", (BAR,)
            ).fetchone()
            self.assertIsNotNone(out_sol)
            self.assertAlmostEqual(out_sol["ret_fwd_1h"], 190 / 200 - 1)

            # BTCUSDT was ingested but NOT in universe: no outcomes row.
            out_btc = conn.execute(
                "SELECT COUNT(*) AS c FROM outcomes WHERE symbol='BTCUSDT'"
            ).fetchone()["c"]
            self.assertEqual(out_btc, 0)

            # vs_btc uses the same bar_open_ts BTCUSDT close (flat here).
            self.assertAlmostEqual(out["ret_fwd_1h"], 0.1)

    def test_repeated_ingest_same_hour_no_new_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp)
            conn = init_db(cfg["db_path"])
            client = _client()
            sleep = lambda _s: None
            run_hourly(conn, client, cfg, now_ms=NOW1, sleep=sleep, out=lambda *_: None)
            k1 = conn.execute("SELECT COUNT(*) AS c FROM raw_klines_1h").fetchone()["c"]
            o1 = conn.execute("SELECT COUNT(*) AS c FROM raw_oi_1h").fetchone()["c"]
            a1 = conn.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"]
            ingest_hourly(conn, client, ["ETHUSDT", "SOLUSDT", "BTCUSDT"], BAR, cfg, sleep=sleep)
            k2 = conn.execute("SELECT COUNT(*) AS c FROM raw_klines_1h").fetchone()["c"]
            o2 = conn.execute("SELECT COUNT(*) AS c FROM raw_oi_1h").fetchone()["c"]
            a2 = conn.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"]
            self.assertEqual((k1, o1, a1), (k2, o2, a2))

    def test_latest_closed_bar_delay(self):
        # 60s after close with 120s delay: this bar is not ready, decide on the previous one.
        self.assertEqual(latest_closed_bar(BAR_CLOSE + 60_000, DELAY_MS), BAR - HOUR)
        # 120s after close: this bar becomes the decision bar.
        self.assertEqual(latest_closed_bar(BAR_CLOSE + DELAY_MS, DELAY_MS), BAR)
        # exactly on the hour: still the previous bar, never scheduled on HH:00:00.
        self.assertEqual(latest_closed_bar(BAR_CLOSE, DELAY_MS), BAR - HOUR)

    def test_cooldown_marks_suppressed_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp)
            conn = init_db(cfg["db_path"])
            # universe membership at both bars
            for ts in (BAR, BAR + 6 * HOUR, BAR + 13 * HOUR):
                conn.execute(
                    "INSERT OR IGNORE INTO universe_snapshot "
                    "(ts, symbol, rank, quote_volume, listing_days, contract_type, status, quote_asset) "
                    "VALUES (?, 'ETHUSDT', 1, 1, 30, 'PERPETUAL', 'TRADING', 'USDT')",
                    (ts,),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO features_1h "
                    "(symbol, bar_open_ts, funding_pct_30d, ret_4h_vs_btc, oi_qty_chg_4h, "
                    " taker_imbalance_4h, funding_rate_type) VALUES ('ETHUSDT', ?, 0.95, -0.01, 0.02, -0.2, 'Regular')",
                    (ts,),
                )
            conn.commit()
            label_states(conn, BAR, cfg, now_ms=NOW1, out=lambda *_: None)
            a1 = conn.execute(
                "SELECT cooldown_suppressed FROM alerts WHERE symbol='ETHUSDT' AND bar_open_ts=? AND state='crowded_long_under_pressure'",
                (BAR,),
            ).fetchone()
            self.assertEqual(a1["cooldown_suppressed"], 0)

            # +6h: inside 12h cooldown -> suppressed flag set, state row kept.
            label_states(conn, BAR + 6 * HOUR, cfg, now_ms=NOW1 + 6 * HOUR * 1000, out=lambda *_: None)
            a2 = conn.execute(
                "SELECT cooldown_suppressed FROM alerts WHERE symbol='ETHUSDT' AND bar_open_ts=? AND state='crowded_long_under_pressure'",
                (BAR + 6 * HOUR,),
            ).fetchone()
            self.assertEqual(a2["cooldown_suppressed"], 1)
            s2 = conn.execute(
                "SELECT hit FROM states_1h WHERE symbol='ETHUSDT' AND bar_open_ts=? AND state='crowded_long_under_pressure'",
                (BAR + 6 * HOUR,),
            ).fetchone()
            self.assertEqual(s2["hit"], 1)

            # +13h: cooldown expired -> not suppressed.
            label_states(conn, BAR + 13 * HOUR, cfg, now_ms=NOW1 + 13 * HOUR * 1000, out=lambda *_: None)
            a3 = conn.execute(
                "SELECT cooldown_suppressed FROM alerts WHERE symbol='ETHUSDT' AND bar_open_ts=? AND state='crowded_long_under_pressure'",
                (BAR + 13 * HOUR,),
            ).fetchone()
            self.assertEqual(a3["cooldown_suppressed"], 0)

    def test_funding_info_dict_and_list_forms(self):
        # /fapi/v1/fundingInfo may answer one dict or a list; both are accepted.
        from forced_trade.ingest import _to_list
        self.assertEqual(_to_list({"symbol": "ETHUSDT"}), [{"symbol": "ETHUSDT"}])
        self.assertEqual(_to_list([{"symbol": "ETHUSDT"}]), [{"symbol": "ETHUSDT"}])
        self.assertEqual(_to_list(None), [])

    def test_outcomes_skip_off_universe_and_open_horizons(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp)
            conn = init_db(cfg["db_path"])
            client = _client()
            sleep = lambda _s: None
            run_hourly(conn, client, cfg, now_ms=NOW1, sleep=sleep, out=lambda *_: None)
            run_hourly(conn, client, cfg, now_ms=NOW2, sleep=sleep, out=lambda *_: None)
            # outcomes only for universe members at that bar
            rows = conn.execute("SELECT symbol, bar_open_ts FROM outcomes").fetchall()
            self.assertTrue(all(r["symbol"] in ("ETHUSDT", "SOLUSDT") for r in rows))
            # unclosed 72h horizon stays NULL, not fabricated
            row = conn.execute(
                "SELECT ret_fwd_72h FROM outcomes WHERE symbol='ETHUSDT' AND bar_open_ts=?", (BAR,)
            ).fetchone()
            self.assertIsNone(row["ret_fwd_72h"])


if __name__ == "__main__":
    unittest.main()
