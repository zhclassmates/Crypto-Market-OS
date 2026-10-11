"""Onramper adapter tests: fixed /supported fixtures, in-memory SQLite, no network."""
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from adapters import onramper as om  # noqa: E402

H = 3600 * 1000
T0 = 1_790_000_000_000
KEY = "pk_prod_test"


def supported(crypto=None, fiats=("USD", "EUR", "GBP")):
    crypto = crypto if crypto is not None else [
        {"id": "usd-coin", "code": "USDC", "name": "USD Coin", "network": "MATIC",
         "contracts": [{"chain": "MATIC", "contract": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"}]},
        {"id": "ethereum", "code": "ETH", "name": "Ethereum", "network": "ethereum"},
        {"id": "bitcoin", "code": "BTC", "name": "Bitcoin", "network": "bitcoin", "isSuspended": True},
    ]
    return {"message": "", "crypto": crypto, "fiats": [{"code": f} for f in fiats]}


def responder(body, calls=None):
    def fetch(url, headers=None):
        if calls is not None:
            calls.append((url, headers))
        if isinstance(body, Exception):
            raise body
        return body
    return fetch


class OnramperTest(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        om.register(self.conn, at=T0)
        os.environ[om.ENV_KEY] = KEY
        os.environ[om.ENV_FIATS] = "usd, eur"          # focus the cross product

    def tearDown(self):
        for k in (om.ENV_KEY, om.ENV_FIATS):
            os.environ.pop(k, None)
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def poll(self, body, at, calls=None):
        return om.run_once(self.conn, fetch=responder(body, calls), fetched_at=at)

    def test_missing_key_is_clear_error(self):
        os.environ.pop(om.ENV_KEY)
        r = self.poll(supported(), T0)
        self.assertIn(om.ENV_KEY, r["error"])
        self.assertIn("dashboard.onramper.com", r["error"])
        self.assertEqual(self.q("SELECT * FROM access_state"), [])

    def test_request_carries_key_without_bearer_prefix(self):
        calls = []
        self.poll(supported(), T0, calls)
        url, headers = calls[0]
        self.assertEqual(url, f"{om.SUPPORTED_URL}?type=buy&skipCountryCheck=true")
        self.assertEqual(headers, {"Authorization": KEY})

    def test_baseline_cross_product(self):
        r = self.poll(supported(), T0)
        self.assertEqual(set(r), {"USD", "EUR"})
        self.assertEqual(r["USD"]["outcome"], "BASELINE")
        self.assertEqual(r["USD"]["valid"], 3)
        st = self.q("SELECT asset_key, status, fiat, fiat_tier, network FROM access_state WHERE fiat='USD'")
        rows = {(s["asset_key"], s["network"]): (s["status"], s["fiat_tier"]) for s in st}
        self.assertEqual(rows[("sym:USDC", "polygon")], ("LIVE", "SUPPORTED"))     # 'MATIC'
        self.assertEqual(rows[("sym:ETH", "ethereum")], ("LIVE", "SUPPORTED"))
        self.assertEqual(rows[("sym:BTC", "bitcoin")], ("SUSPENDED", "SUPPORTED"))

    def test_contract_enables_resolution(self):
        aid = rc.upsert_asset(self.conn, "sym:USDC", "CRYPTO", "USDC", issuer="circle")
        rc.add_deployment(self.conn, aid, "polygon", "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359")
        self.poll(supported(), T0)
        ref = self.q("SELECT resolution_status, resolution_source FROM source_asset_ref "
                     "WHERE source_id='onramper_routes' AND platform_symbol='USDC'")[0]
        self.assertEqual((ref["resolution_status"], ref["resolution_source"]), ("CONFIRMED", "contract"))
        st = self.q("SELECT asset_id FROM access_state WHERE asset_key='sym:USDC' AND fiat='USD'")[0]
        self.assertEqual(st["asset_id"], aid)

    def test_unsuspend_produces_resume_event(self):
        self.poll(supported(), T0)
        crypto = [dict(c, isSuspended=False) if c["code"] == "BTC" else c for c in supported()["crypto"]]
        self.poll(supported(crypto=crypto), T0 + H)
        ev = self.q("SELECT asset_key, event_type FROM access_event")
        self.assertEqual([(e["asset_key"], e["event_type"]) for e in ev],
                         [("sym:BTC", "FIAT_ROUTE_RESUMED")] * 2)          # one per fiat scope (USD, EUR)

    def test_fiat_absent_is_scope_error(self):
        r = self.poll(supported(fiats=("USD",)), T0)
        self.assertIn("EUR", r["EUR"]["error"])
        self.assertEqual(r["USD"]["outcome"], "BASELINE")
        scopes = {(h["scope"], h["status"]) for h in self.q("SELECT scope, status FROM source_health")}
        self.assertIn(("EUR", "DOWN"), scopes)

    def test_shape_change_is_error(self):
        r = self.poll({"unexpected": 1}, T0)
        self.assertIn("error", r)
        self.assertEqual(self.q("SELECT * FROM access_state"), [])

    def test_default_fiats_without_env(self):
        os.environ.pop(om.ENV_FIATS)
        self.assertEqual(om.configured_fiats(), om.DEFAULT_FIATS)


if __name__ == "__main__":
    unittest.main()
