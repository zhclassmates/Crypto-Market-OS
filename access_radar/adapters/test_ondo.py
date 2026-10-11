"""Ondo adapter tests: credential handling + tolerant mapper, in-memory SQLite, no network."""
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from adapters import ondo  # noqa: E402

H = 3600 * 1000
T0 = 1_790_000_000_000
ENV = {ondo.ENV_URL: "https://api.ondo.example/assets", ondo.ENV_KEY: "k-123"}


def usdy(**over):
    d = {"symbol": "USDY", "name": "Ondo US Dollar Yield", "status": "live",
         "deployments": [{"chain": "Ethereum", "address": "0xABC0000000000000000000000000000000000001"},
                         {"chain": "solana", "address": "USDY111111111111111111111111111111111111111"}]}
    d.update(over)
    return d


class OndoTest(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        ondo.register(self.conn, at=T0)
        self._saved = {k: os.environ.get(k) for k in (ondo.ENV_URL, ondo.ENV_KEY)}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def test_missing_credentials_report_clearly(self):
        r = ondo.run_once(self.conn, fetch=None, fetched_at=T0)
        self.assertIn("error", r)
        self.assertIn(ondo.ENV_URL, r["error"])
        self.assertIn(ondo.ENV_KEY, r["error"])
        self.assertEqual(self.q("SELECT * FROM access_state"), [])
        scopes = {(h["scope"], h["status"]) for h in self.q("SELECT scope, status FROM source_health")}
        self.assertEqual(scopes, {("catalog", "DOWN"), ("deployments", "DOWN")})

    def test_baseline_with_credentials(self):
        def fetch(url, headers=None):
            self.assertEqual(url, ENV[ondo.ENV_URL])
            self.assertEqual(headers, {"Authorization": "Bearer k-123"})
            return [usdy(), {"symbol": "OUSG", "chains": ["ethereum"], "contract": "0xDEF0000000000000000000000000000000000002"}]
        os.environ.update(ENV)
        r = ondo.run_once(self.conn, fetch=fetch, fetched_at=T0)
        self.assertEqual(r["catalog"]["outcome"], "BASELINE")
        self.assertEqual(r["catalog"]["valid"], 2)
        self.assertEqual(r["deployments"]["outcome"], "BASELINE")
        self.assertEqual(r["deployments"]["valid"], 3)
        st = self.q("SELECT status FROM access_state WHERE asset_key='ondo:USDY' AND access_kind='CATALOG'")
        self.assertEqual(st[0]["status"], "LIVE")

    def test_global_assets_registered(self):
        os.environ.update(ENV)
        ondo.run_once(self.conn, fetch=lambda url, headers=None: [usdy()], fetched_at=T0)
        a = self.q("SELECT * FROM asset WHERE asset_key='ondo:USDY'")[0]
        self.assertEqual((a["asset_type"], a["issuer"]), ("TREASURY", "ondo"))
        deps = {(d["chain"], d["contract"]) for d in
                self.q("SELECT * FROM asset_deployment WHERE asset_id=?", (a["asset_id"],))}
        self.assertEqual(deps, {("ethereum", "0xabc0000000000000000000000000000000000001"),
                                ("solana", "USDY111111111111111111111111111111111111111")})

    def test_suspended_status(self):
        os.environ.update(ENV)
        ondo.run_once(self.conn, fetch=lambda url, headers=None: [usdy()], fetched_at=T0)
        ondo.run_once(self.conn, fetch=lambda url, headers=None: [usdy(status="halted")], fetched_at=T0 + H)
        st = self.q("SELECT status FROM access_state WHERE asset_key='ondo:USDY' AND access_kind='CATALOG'")
        self.assertEqual(st[0]["status"], "SUSPENDED")
        types = {e["event_type"] for e in self.q("SELECT * FROM access_event")}
        self.assertEqual(types, {"CATALOG_SUSPENDED", "CHAIN_DEPLOYMENT_SUSPENDED"})

    def test_bad_shape_is_error(self):
        os.environ.update(ENV)
        r = ondo.run_once(self.conn, fetch=lambda url, headers=None: {"nope": 1}, fetched_at=T0)
        self.assertIn("unexpected response shape", r["error"])
        self.assertEqual(self.q("SELECT * FROM access_state"), [])

    def test_map_item_variants(self):
        cat, deps = ondo.map_item({"ticker": "OUSG", "chain": "polygon", "contract": "0x1", "isSuspended": True})
        self.assertEqual(cat["symbol"], "OUSG")
        self.assertEqual(cat["status"], "SUSPENDED")
        self.assertEqual(deps[0]["network"], "polygon")
        cat, deps = ondo.map_item({"name": "no symbol"})
        self.assertNotIn("symbol", cat)          # invalid marker for the schema gate
        self.assertEqual(deps, [])


if __name__ == "__main__":
    unittest.main()
