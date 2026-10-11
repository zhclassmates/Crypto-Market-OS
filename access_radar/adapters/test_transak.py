"""Transak adapter tests: fixed currencies fixtures, in-memory SQLite, no network."""
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from adapters import transak as tk  # noqa: E402

H = 3600 * 1000
T0 = 1_790_000_000_000


def crypto_rows(extra=()):
    rows = [
        {"symbol": "ETH", "name": "Ethereum", "network": {"name": "ethereum", "chainId": "1"},
         "address": "", "decimals": 18, "isAllowed": True, "isSuspended": False,
         "uniqueId": "ETHethereum", "coinType": "NATIVE", "regionsNotSupported": []},
        {"symbol": "USDC", "name": "USD Coin", "network": {"name": "polygon", "chainId": "137"},
         "address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "decimals": 6, "isAllowed": True,
         "isSuspended": False, "uniqueId": "USDCpolygon", "coinType": "ERC20",
         "regionsNotSupported": []},
        {"symbol": "BTC", "name": "Bitcoin", "network": {"name": "bitcoin"},
         "address": "", "isAllowed": True, "isSuspended": True, "uniqueId": "BTCbitcoin",
         "coinType": "NATIVE", "regionsNotSupported": []},
    ]
    rows += list(extra)
    return {"response": rows}


def fiat_rows(fiats=("USD", "EUR", "GBP"), disallow=()):
    return {"response": [{"symbol": f, "name": f, "isAllowed": f not in disallow} for f in fiats]}


def responder(by_url, calls=None):
    def fetch(url, headers=None):
        if calls is not None:
            calls.append(url)
        body = by_url[url.rsplit("/", 1)[1]]
        if isinstance(body, Exception):
            raise body
        return body
    return fetch


class TransakTest(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        tk.register(self.conn, at=T0)
        os.environ.pop(tk.ENV_FIATS, None)

    def tearDown(self):
        os.environ.pop(tk.ENV_FIATS, None)
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def poll(self, crypto=None, fiats=None, at=T0, calls=None, disallow=()):
        crypto = crypto if crypto is not None else crypto_rows()
        fiats = fiats if fiats is not None else fiat_rows(disallow=disallow)
        return tk.run_once(self.conn, fetch=responder({"crypto-currencies": crypto,
                                                       "fiat-currencies": fiats}, calls), fetched_at=at)

    def test_baseline_three_fiat_scopes(self):
        r = self.poll(at=T0)
        self.assertEqual(set(r), {"USD", "EUR", "GBP"})
        self.assertEqual(r["USD"]["outcome"], "BASELINE")
        self.assertEqual(r["USD"]["valid"], 3)
        self.assertEqual(self.q("SELECT * FROM access_event"), [])

    def test_routes_map_networks_and_native_id(self):
        self.poll(at=T0)
        st = self.q("SELECT asset_key, network, status, fiat_tier FROM access_state WHERE fiat='USD' ORDER BY asset_key")
        rows = {s["asset_key"]: s for s in st}
        self.assertEqual(rows["sym:USDC"]["network"], "polygon")
        self.assertEqual(rows["sym:USDC"]["status"], "LIVE")
        self.assertEqual(rows["sym:BTC"]["status"], "SUSPENDED")
        self.assertTrue(all(s["fiat_tier"] == "SUPPORTED" for s in st))
        refs = {r["platform_symbol"]: r for r in
                self.q("SELECT platform_symbol, native_id FROM source_asset_ref WHERE source_id='transak_routes'")}
        self.assertEqual(refs["USDC"]["native_id"], "USDCpolygon")
        self.assertEqual(refs["ETH"]["native_id"], "ETHethereum")

    def test_suspend_then_resume(self):
        self.poll(at=T0)
        self.poll(crypto=crypto_rows(extra=[]), at=T0 + H)
        # BTC stays suspended -> no events; flip it allowed+unsuspended -> RESUMED
        rows = crypto_rows()["response"]
        rows[2] = dict(rows[2], isSuspended=False)
        r = self.poll(crypto={"response": rows}, at=T0 + 2 * H)
        ev = self.q("SELECT asset_key, event_type FROM access_event")
        self.assertEqual([(e["asset_key"], e["event_type"]) for e in ev],
                         [("sym:BTC", "FIAT_ROUTE_RESUMED")] * 3)   # one per fiat scope

    def test_disallowed_fiat_gets_suspended_routes(self):
        r = self.poll(disallow=("GBP",), at=T0)
        st = self.q("SELECT DISTINCT status FROM access_state WHERE fiat='GBP'")
        self.assertEqual({s["status"] for s in st}, {"SUSPENDED"})
        usd = self.q("SELECT DISTINCT status FROM access_state WHERE fiat='USD'")
        self.assertEqual({s["status"] for s in usd}, {"LIVE", "SUSPENDED"})   # BTC starts suspended

    def test_fiat_absent_is_scope_error(self):
        r = self.poll(fiats=fiat_rows(fiats=("USD", "EUR")), at=T0)
        self.assertIn("GBP", r["GBP"]["error"])
        self.assertEqual(r["USD"]["outcome"], "BASELINE")
        scopes = {(h["scope"], h["status"]) for h in self.q("SELECT scope, status FROM source_health")}
        self.assertIn(("GBP", "DOWN"), scopes)

    def test_bad_shape_is_error(self):
        r = self.poll(crypto={"foo": 1}, at=T0)
        self.assertIn("error", r)
        self.assertEqual(self.q("SELECT * FROM access_state"), [])

    def test_env_fiats(self):
        os.environ[tk.ENV_FIATS] = "usd, krw"
        try:
            self.assertEqual(tk.configured_fiats(), ("USD", "KRW"))
        finally:
            os.environ.pop(tk.ENV_FIATS)
        self.assertEqual(tk.configured_fiats(), tk.DEFAULT_FIATS)


if __name__ == "__main__":
    unittest.main()
