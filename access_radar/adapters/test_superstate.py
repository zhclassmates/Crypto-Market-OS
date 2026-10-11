"""Superstate adapter tests: fixed NAV fixtures, in-memory SQLite, no network."""
import logging
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from adapters import superstate as ss  # noqa: E402

H = 3600 * 1000
T0 = 1_790_000_000_000

USTB_ETH = "0x43415eB6ff9DB7E26A15b704e7A3eDCe97d31C4e"


def nav(fund_id, date="10/09/2026", value="11.24"):
    return [{"fund_id": fund_id, "net_asset_value_date": date, "net_asset_value": value,
             "subscription_nav_per_share": None, "assets_under_management": "796673401.1600",
             "outstanding_shares": "70892601.300741", "net_income_expenses": "78319.95084200"}]


def responder(by_fund):
    def fetch(url, headers=None):
        fund_id = int(url.rsplit("/", 2)[1])
        body = by_fund[fund_id]
        if isinstance(body, Exception):
            raise body
        return body
    return fetch


class SuperstateTest(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        ss.register(self.conn, at=T0)

    def tearDown(self):
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def poll(self, by_fund, at):
        return ss.run_once(self.conn, fetch=responder(by_fund), fetched_at=at)

    def test_baseline_two_funds(self):
        r = self.poll({1: nav(1), 2: nav(2)}, T0)
        self.assertEqual(r["catalog"]["outcome"], "BASELINE")
        self.assertEqual(r["catalog"]["valid"], 2)
        self.assertEqual(r["deployments"]["outcome"], "BASELINE")
        self.assertEqual(r["deployments"]["valid"], 4)
        self.assertEqual(self.q("SELECT * FROM access_event"), [])

    def test_global_assets_and_deployments_registered(self):
        self.poll({1: nav(1), 2: nav(2)}, T0)
        a = self.q("SELECT * FROM asset WHERE asset_key='superstate:USTB'")[0]
        self.assertEqual((a["asset_type"], a["issuer"], a["product_id"]), ("TREASURY", "superstate", "1"))
        deps = {(d["chain"], d["contract"]) for d in
                self.q("SELECT * FROM asset_deployment WHERE asset_id=?", (a["asset_id"],))}
        self.assertEqual(deps, {("ethereum", USTB_ETH.lower())})
        uscc = self.q("SELECT asset_id FROM asset WHERE asset_key='superstate:USCC'")[0]
        chains = {d["chain"] for d in self.q("SELECT * FROM asset_deployment WHERE asset_id=?",
                                             (uscc["asset_id"],))}
        self.assertEqual(chains, {"ethereum", "solana", "plume"})

    def test_new_fund_is_catalog_added(self):
        self.poll({1: nav(1), 2: nav(2)}, T0)
        extra = {3: ("TEST", "Superstate Test Fund", "FUND", "", [("ethereum", "0xAbC0000000000000000000000000000000000009")])}
        with mock.patch.dict(ss.FUNDS, extra):
            r = self.poll({1: nav(1), 2: nav(2), 3: nav(3)}, T0 + H)
        self.assertEqual(r["catalog"]["outcome"], "DIFF")
        ev = {(e["asset_key"], e["event_type"]) for e in self.q("SELECT * FROM access_event")}
        self.assertIn(("superstate:TEST", "CATALOG_ADDED"), ev)
        self.assertIn(("superstate:TEST", "CHAIN_DEPLOYED"), ev)

    def test_nav_update_is_not_an_event(self):
        self.poll({1: nav(1), 2: nav(2)}, T0)
        self.poll({1: nav(1, date="10/10/2026", value="11.31"), 2: nav(2)}, T0 + H)
        self.assertEqual(self.q("SELECT * FROM access_event"), [])

    def test_fund_failure_fails_both_scopes(self):
        self.poll({1: nav(1), 2: nav(2)}, T0)
        r = self.poll({1: nav(1), 2: ss.BadResponse("HTTP 503")}, T0 + H)
        self.assertIn("503", r["error"])
        scopes = {(h["scope"], h["status"]) for h in self.q("SELECT scope, status FROM source_health")}
        self.assertIn(("catalog", "DOWN"), scopes)
        self.assertEqual(len(self.q("SELECT * FROM source_snapshot")), 2)   # only the baselines

    def test_bad_shape_is_refused(self):
        r = self.poll({1: {"foo": 1}, 2: nav(2)}, T0)
        self.assertIn("unexpected nav-daily response", r["error"])
        self.assertEqual(self.q("SELECT * FROM access_state"), [])

    def test_fund_id_mismatch_is_refused(self):
        r = self.poll({1: nav(99), 2: nav(2)}, T0)
        self.assertIn("fund_id", r["error"])

    def test_bad_nav_date_is_refused(self):
        r = self.poll({1: nav(1, date="2026-10-09"), 2: nav(2)}, T0)
        self.assertIn("net_asset_value_date", r["error"])


if __name__ == "__main__":
    unittest.main()
