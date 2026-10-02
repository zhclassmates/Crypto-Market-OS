#!/usr/bin/env python3
"""健康口径单测。不打外部接口。"""
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import market_db as db
import market_health as H

NY = ZoneInfo("America/New_York")


def ts(y, m, d, hh, mm):
    return int(datetime(y, m, d, hh, mm, tzinfo=NY).timestamp())


class ClassifyTest(unittest.TestCase):
    def test_four_statuses(self):
        now = 1000
        self.assertEqual(H.classify_status(now, 995, 995, 0, 1, 10, 1), "LIVE")
        self.assertEqual(H.classify_status(now, 985, 985, 0, 1, 10, 1), "DELAYED")
        self.assertEqual(H.classify_status(now, 970, 970, 0, 1, 10, 1), "STALE")
        self.assertEqual(H.classify_status(now, 995, 995, 0, 1, 10, 0), "STALE")
        self.assertEqual(H.classify_status(now, 995, None, 3, 0, 10, 0), "FAILED")
        self.assertEqual(H.classify_status(now, 995, 995, 3, 1, 10, 0), "STALE")

    def test_failure_does_not_refresh_clocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            con = db.connect(tmp + "/t.sqlite")
            H.ensure_catalog(con)
            H.record_result(
                con, "gmgn", "sol", True, 100.2, 101.4,
                rows_received=2, hot_changed=0, cold_changed=0,
                source_timestamp_missing=True, wrote_db=True,
            )
            H.record_result(
                con, "gmgn", "sol", False, 200.1, 201.8,
                error="timeout", rows_received=9, hot_changed=9,
            )
            row = con.execute(
                "SELECT * FROM source_health WHERE source='gmgn' AND chain='sol'"
            ).fetchone()
            self.assertEqual(row["last_success"], 101)
            self.assertEqual(row["db_written_at"], 101)
            self.assertIsNone(row["source_timestamp"])
            self.assertEqual(row["source_timestamp_missing"], 1)
            self.assertEqual(row["last_attempt"], 200)
            self.assertEqual(row["consecutive_errors"], 1)
            self.assertEqual(row["hot_changed"], 0)
            self.assertEqual(row["rows_received"], 2)
            self.assertEqual(row["successes"], 1)
            self.assertEqual(row["attempts"], 2)
            self.assertEqual(
                H.classify_status(
                    201, row["last_attempt"], row["last_success"],
                    row["consecutive_errors"], row["has_display_rows"],
                    row["period_sec"], row["round_ok"],
                ),
                "STALE",
            )
            con.close()

    def test_unchanged_price_is_still_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            con = db.connect(tmp + "/t.sqlite")
            H.ensure_catalog(con)
            H.record_result(
                con, "dexscreener", "base", True, 10, 11,
                rows_received=30, hot_changed=0, cold_changed=0,
                source_timestamp_missing=True, wrote_db=True,
            )
            row = con.execute(
                "SELECT * FROM source_health WHERE source='dexscreener' AND chain='base'"
            ).fetchone()
            self.assertEqual(row["successes"], 1)
            self.assertEqual(row["hot_changed"], 0)
            self.assertIsNone(row["last_change_at"])
            self.assertEqual(row["db_written_at"], 11)
            con.close()

    def test_partial_error_kept_on_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            con = db.connect(tmp + "/t.sqlite")
            H.ensure_catalog(con)
            H.record_result(
                con, "dexscreener", "eth", True, 10, 12,
                rows_received=10, hot_changed=1, wrote_db=True,
                source_timestamp_missing=True, error="HTTP 429 batch 2",
            )
            row = con.execute(
                "SELECT last_error, round_ok FROM source_health WHERE source='dexscreener' AND chain='eth'"
            ).fetchone()
            self.assertEqual(row["round_ok"], 1)
            self.assertIn("429", row["last_error"])
            con.close()


class MathTest(unittest.TestCase):
    def test_diverge(self):
        self.assertEqual(H.diverge_flag(100, 106), 1)
        self.assertEqual(H.diverge_flag(100, 104), 0)
        self.assertEqual(H.diverge_flag(0, 1), 0)

    def test_anchor(self):
        self.assertAlmostEqual(H.adjusted_anchor("10", "12", "2"), 22.0)
        self.assertAlmostEqual(H.adjusted_anchor("10", None, "1.5"), 15.0)
        self.assertIsNone(H.adjusted_anchor(None, None, "2"))

    def test_num_changed_epsilon(self):
        self.assertFalse(H.num_changed("1.0000000001", "1.0000000001"))
        self.assertTrue(H.num_changed("1", "1.0001"))

    def test_session(self):
        self.assertTrue(H.equity_session_closed(ts(2026, 10, 3, 12, 0)))
        self.assertTrue(H.equity_session_closed(ts(2026, 10, 2, 21, 0)))
        self.assertFalse(H.equity_session_closed(ts(2026, 10, 2, 15, 0)))
        self.assertFalse(H.equity_session_closed(ts(2026, 10, 4, 21, 0)))
        self.assertTrue(H.equity_session_closed(ts(2026, 10, 4, 19, 0)))

    def test_decode_and_symbol(self):
        def enc(n):
            return f"{n:064x}"
        hexdata = "0x" + enc(1) + enc(33240806311) + enc(0) + enc(1790839788)
        answer, updated = H.decode_latest_round(hexdata)
        self.assertEqual(updated, 1790839788)
        self.assertAlmostEqual(answer / 1e8, 332.40806311, places=6)
        self.assertEqual(H.feed_symbol("Robinhood AAPL / USD"), "AAPL")
        self.assertEqual(H.feed_symbol("Robinhood DELL-USD"), "DELL")
        self.assertIsNone(H.feed_symbol("ETH / USD"))

    def test_token_stale_halt(self):
        self.assertFalse(H.token_is_stale(10_000, 10, halt=True))
        self.assertFalse(H.token_is_stale(10_000, 10, market_closed=True))
        self.assertTrue(H.token_is_stale(21, 10))
        self.assertFalse(H.token_is_stale(20, 10))

    def test_field_age_ignores_db_time(self):
        self.assertEqual(H.field_age_sec(100, 90, None, True), 10)
        self.assertEqual(H.field_age_sec(100, 90, 80, False), 20)
        self.assertIsNone(H.field_age_sec(100, None, None, True))

    def test_rfc3339_nanos(self):
        got = H.parse_rfc3339("2026-10-01T12:00:00.123456789Z")
        self.assertIsInstance(got, int)


if __name__ == "__main__":
    unittest.main()
