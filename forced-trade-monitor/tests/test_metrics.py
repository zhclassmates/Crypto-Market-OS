import unittest

from forced_trade.align import HOUR_MS, is_hour_aligned, oi_bar_open, start_bar_open, visible_at
from forced_trade.binance import parse_basis, parse_funding, parse_oi, parse_taker
from forced_trade.features import build_feature
from forced_trade.metrics import funding_8h_equiv, resolve_interval


class AlignTest(unittest.TestCase):
    def test_oi_end_maps_to_previous_open(self):
        start = 1_700_000_000_000 - (1_700_000_000_000 % HOUR_MS)
        end = start + HOUR_MS
        self.assertEqual(oi_bar_open(end), start)
        self.assertTrue(is_hour_aligned(oi_bar_open(end)))

    def test_basis_and_taker_keep_start(self):
        start = 1_700_000_000_000
        self.assertEqual(start_bar_open(start), start)

    def test_parsers_do_not_share_a_raw_clock(self):
        oi = parse_oi(
            {
                "symbol": "ETHUSDT",
                "sumOpenInterest": "10",
                "sumOpenInterestValue": "20000",
                "timestamp": 1_700_003_600_000,
            }
        )
        taker = parse_taker(
            "ETHUSDT",
            {"buySellRatio": "1", "buyVol": "3", "sellVol": "1", "timestamp": 1_700_000_000_000},
        )
        basis = parse_basis(
            "ETHUSDT",
            {
                "pair": "ETHUSDT",
                "contractType": "PERPETUAL",
                "indexPrice": "2000",
                "futuresPrice": "2001",
                "basisRate": "0.0005",
                "basis": "1",
                "timestamp": 1_700_000_000_000,
            },
        )
        self.assertEqual(oi["bar_open_ts"], taker["bar_open_ts"])
        self.assertEqual(basis["bar_open_ts"], 1_700_000_000_000)
        self.assertEqual(oi["oi_qty"], 10)
        self.assertNotIn("contracts", oi)

    def test_funding_after_close_is_invisible(self):
        bar = 1_700_000_000_000
        self.assertTrue(visible_at(bar + HOUR_MS, bar))
        self.assertFalse(visible_at(bar + HOUR_MS + 1, bar))

    def test_interval_does_not_use_future_snapshot(self):
        snaps = [
            {"observed_at": 100, "funding_interval_hours": 8, "present_in_payload": 1},
            {"observed_at": 500, "funding_interval_hours": 4, "present_in_payload": 1},
        ]
        hours, source = resolve_interval(snaps, 200)
        self.assertEqual((hours, source), (8, "snapshot"))
        self.assertEqual(funding_8h_equiv(0.0002, 4), 0.0004)

    def test_missing_interval_defaults(self):
        hours, source = resolve_interval([], 200)
        self.assertEqual((hours, source), (8, "default"))

    def test_special_funding_excluded_from_percentile(self):
        bar = 10 * HOUR_MS
        events = [
            {"funding_time": bar, "funding_rate": 0.001, "rate_type": "Special"},
            {"funding_time": bar - HOUR_MS, "funding_rate": 0.0001, "rate_type": "Regular"},
        ]
        row = build_feature(
            "X",
            bar,
            {bar: 1, bar - HOUR_MS: 1},
            {},
            {},
            {},
            {},
            {},
            {},
            events,
            [],
            {bar: 1, bar - HOUR_MS: 1},
            z_min=24,
        )
        self.assertIsNone(row["funding_pct_30d"])
        self.assertIn("funding_special", row["data_quality_flag"])
        self.assertEqual(parse_funding(events[0] | {"symbol": "X", "fundingTime": bar, "fundingRate": "0.001", "rateType": "Special"})["rate_type"], "Special")


if __name__ == "__main__":
    unittest.main()
