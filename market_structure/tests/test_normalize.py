"""normalize 单元测试：样例按交易所文档里的字段格式构造。运行：python -m unittest discover tests"""
import unittest

from ms import normalize as N


class T(unittest.TestCase):
    def test_kline_cvd_and_unclosed(self):
        raw = [[1000, "1", "2", "0.5", "1.5", "10", 1899, "1000", 5, "6", "600", "0"],
               [1900, "1", "2", "0.5", "1.5", "10", 2799, "1000", 5, "6", "600", "0"]]
        rows = N.binance_klines(raw, "binance", "perp", "BTCUSDT", "15m", now=2000)
        self.assertEqual(len(rows), 1)                      # 第二根未收盘，丢弃
        self.assertAlmostEqual(rows[0][12], 200.0)          # cvd = 2*600 - 1000

    def test_binance_force_order_side(self):
        msg = {"e": "forceOrder", "E": 1568014460893, "o": {
            "s": "BTCUSDT", "S": "SELL", "o": "LIMIT", "f": "IOC", "q": "0.014", "p": "9910",
            "ap": "9910", "X": "FILLED", "l": "0.014", "z": "0.014", "T": 1568014460893}}
        r = N.binance_force_order(msg)
        self.assertEqual(r[3], "long_liq")                  # SELL 强平单 = 多头被爆
        self.assertAlmostEqual(r[6], 9910 * 0.014)
        self.assertEqual(N.binance_force_order({"data": msg})[3], "long_liq")
        msg["o"]["S"] = "BUY"
        self.assertEqual(N.binance_force_order(msg)[3], "short_liq")
        self.assertIsNone(N.binance_force_order({"e": "other"}))

    def test_bybit_all_liq_side(self):
        msg = {"topic": "allLiquidation.ROSEUSDT", "type": "snapshot", "ts": 1739502303204,
               "data": [{"T": 1739502302929, "s": "ROSEUSDT", "S": "Sell", "v": "20000", "p": "0.04499"},
                        {"T": 1739502302930, "s": "ROSEUSDT", "S": "Buy", "v": "100", "p": "0.045"}]}
        rows = N.bybit_all_liq(msg)
        self.assertEqual([r[3] for r in rows], ["short_liq", "long_liq"])   # Buy = 多头被爆
        self.assertEqual(N.bybit_all_liq({"op": "pong"}), [])

    def test_oi_and_funding(self):
        r = N.binance_oi_snapshot({"openInterest": "10", "symbol": "BTCUSDT", "time": 5}, "BTCUSDT", 100.0)
        self.assertEqual(r[5], 1000.0)
        h = N.binance_oi_hist([{"symbol": "BTCUSDT", "sumOpenInterest": "1", "sumOpenInterestValue": "2",
                                "timestamp": 7}], "BTCUSDT")
        self.assertEqual(h[0][2:], ("hist5m", 7, 1.0, 2.0))
        p = N.binance_premium({"markPrice": "1", "indexPrice": "1", "lastFundingRate": "-0.0002",
                               "nextFundingTime": 9, "time": 8}, "BTCUSDT")
        self.assertEqual(p[5], -0.0002)
        t = N.bybit_ticker({"result": {"list": [{"markPrice": "2", "indexPrice": "2", "fundingRate": "0.0001",
                                                 "openInterest": "3", "nextFundingTime": "10"}]}}, "BTCUSDT", 1)
        self.assertEqual(t[1][5], 6.0)


if __name__ == "__main__":
    unittest.main()
