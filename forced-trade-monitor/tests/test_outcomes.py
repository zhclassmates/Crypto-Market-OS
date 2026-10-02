import unittest

from forced_trade.align import HOUR_MS
from forced_trade.outcomes import fill_row
from forced_trade.universe import select_universe


class OutcomeTest(unittest.TestCase):
    def test_open_horizon_and_off_universe_are_dropped(self):
        t0 = 10 * HOUR_MS
        closes = {
            "ETHUSDT": {t0: 100, t0 + HOUR_MS: 110, t0 + 4 * HOUR_MS: 80},
            "BTCUSDT": {t0: 50, t0 + HOUR_MS: 50, t0 + 4 * HOUR_MS: 55},
        }
        universe = {("ETHUSDT", t0)}
        early = fill_row("ETHUSDT", t0, closes, universe, now_close_floor=t0)
        self.assertIsNone(early)
        mid = fill_row("ETHUSDT", t0, closes, universe, now_close_floor=t0 + HOUR_MS)
        self.assertAlmostEqual(mid["ret_fwd_1h"], 0.1)
        self.assertIsNone(mid["ret_fwd_4h"])
        done = fill_row("ETHUSDT", t0, closes, universe, now_close_floor=t0 + 4 * HOUR_MS)
        self.assertAlmostEqual(done["ret_fwd_4h"], -0.2)
        self.assertAlmostEqual(done["ret_fwd_4h_vs_btc"], -0.2 - (55 / 50 - 1))
        self.assertIsNone(fill_row("ETHUSDT", t0 + HOUR_MS, closes, universe))

    def test_universe_snapshot_filters_listing_age(self):
        asof = 30 * 24 * HOUR_MS
        rows = [
            {
                "symbol": "NEWUSDT",
                "contractType": "PERPETUAL",
                "status": "TRADING",
                "quoteAsset": "USDT",
                "onboardDate": asof - 2 * 24 * HOUR_MS,
                "quoteVolume": 1e9,
            },
            {
                "symbol": "OLDUSDT",
                "contractType": "PERPETUAL",
                "status": "TRADING",
                "quoteAsset": "USDT",
                "onboardDate": asof - 40 * 24 * HOUR_MS,
                "quoteVolume": 10,
            },
            {
                "symbol": "BTCUSD_PERP",
                "contractType": "PERPETUAL",
                "status": "TRADING",
                "quoteAsset": "USD",
                "onboardDate": 0,
                "quoteVolume": 1e12,
            },
        ]
        picked = select_universe(rows, asof, top_n=80, min_listing_days=14)
        self.assertEqual([r["symbol"] for r in picked], ["OLDUSDT"])
        self.assertEqual(picked[0]["ts"], asof)


if __name__ == "__main__":
    unittest.main()
