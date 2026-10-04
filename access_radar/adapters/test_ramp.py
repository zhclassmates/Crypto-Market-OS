"""Ramp adapter tests: fixed fixture responses, in-memory SQLite, no network."""
import logging
import os
import sys
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from adapters import ramp  # noqa: E402

H = 3600 * 1000
T0 = 1_790_000_000_000


def asset(sym, chain="ETH", enabled=True, hidden=False, address=None, price=1.0):
    return {"symbol": sym, "chain": chain, "type": "ERC20" if address else "NATIVE", "name": sym, "decimals": 18,
            "address": address, "enabled": enabled, "hidden": hidden, "price": {"USD": price, "EUR": price * 0.9},
            "networkFee": 0.1, "minPurchaseAmount": 5, "maxPurchaseAmount": 10000}


def catalog(extra=(), disable=(), price=1.0):
    items = [asset(f"T{i:02d}", chain="BSC" if i % 3 else "ETH", price=price) for i in range(20)]
    items += [asset("OLD", chain="TEZOS", enabled=False), asset("HID", chain="RONIN", hidden=True)]
    items += list(extra)
    for a in items:
        if a["symbol"] in disable:
            a["enabled"] = False
    return items


def responder(by_fiat, calls=None):
    def fetch(url, headers=None):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        if calls is not None:
            calls.append(q)
        body = by_fiat[q["currencyCode"]]
        if isinstance(body, Exception):
            raise body
        return body
    return fetch


def resp(fiat, assets):
    return {"currencyCode": fiat, "minFeePercent": 0.99, "assets": assets}


class RampTest(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        ramp.register(self.conn, at=T0)

    def tearDown(self):
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def poll(self, by_fiat, at, calls=None):
        return ramp.run_once(self.conn, fiats=list(by_fiat), fetch=responder(by_fiat, calls), fetched_at=at)

    def test_url_always_asks_for_disabled_and_hidden(self):
        calls = []
        self.poll({"EUR": resp("EUR", catalog())}, T0, calls)
        self.assertEqual(calls[0], {"currencyCode": "EUR", "withDisabled": "true", "withHidden": "true"})

    def test_baseline_then_new_route(self):
        r = self.poll({"EUR": resp("EUR", catalog())}, T0)
        self.assertEqual(r["EUR"]["outcome"], "BASELINE")
        self.assertEqual(r["EUR"]["valid"], 22)
        r = self.poll({"EUR": resp("EUR", catalog(extra=[asset("SUI", chain="SUI")]))}, T0 + H)
        ev = self.q("SELECT * FROM access_event")
        self.assertEqual([(e["asset_key"], e["event_type"], e["quote"]) for e in ev],
                         [("sym:SUI", "FIAT_ROUTE_SUPPORTED", "EUR")])

    def test_disable_is_suspend_not_remove(self):
        self.poll({"EUR": resp("EUR", catalog())}, T0)
        self.poll({"EUR": resp("EUR", catalog(disable=("T04",)))}, T0 + H)
        st = self.q("SELECT status FROM access_state WHERE asset_key='sym:T04' AND fiat='EUR'")
        self.assertEqual(st[0]["status"], "SUSPENDED")
        types = [e["event_type"] for e in self.q("SELECT * FROM access_event")]
        self.assertEqual(types, ["FIAT_ROUTE_SUSPENDED"])

    def test_flags_ignored_response_is_refused(self):
        self.poll({"EUR": resp("EUR", catalog())}, T0)
        only_enabled = [a for a in catalog() if a["enabled"] and not a["hidden"]]
        for i in range(4):
            r = self.poll({"EUR": resp("EUR", only_enabled)}, T0 + (i + 1) * H)
            self.assertIn("withDisabled", r["EUR"]["error"])
        self.assertEqual(self.q("SELECT * FROM access_event"), [])
        self.assertEqual(len(self.q("SELECT * FROM source_snapshot")), 1)

    def test_currency_mismatch_is_refused(self):
        r = self.poll({"EUR": resp("USD", catalog())}, T0)
        self.assertIn("currencyCode", r["EUR"]["error"])
        self.assertEqual(self.q("SELECT * FROM source_snapshot"), [])

    def test_fiats_are_separate_scopes_and_fail_independently(self):
        r = self.poll({"EUR": resp("EUR", catalog()), "GBP": ramp.BadResponse("HTTP 503")}, T0)
        self.assertEqual(r["EUR"]["outcome"], "BASELINE")
        self.assertIn("503", r["GBP"]["error"])
        scopes = {(h["scope"], h["status"]) for h in self.q("SELECT scope, status FROM source_health")}
        self.assertIn(("EUR", "HEALTHY"), scopes)
        self.assertEqual({s for s, _ in scopes}, {"EUR", "GBP"})

    def test_canonical_chain_and_contract(self):
        usdc = asset("USDC", chain="MATIC", address="0xAbC0000000000000000000000000000000000001")
        self.poll({"EUR": resp("EUR", catalog(extra=[usdc]))}, T0)
        st = self.q("SELECT network FROM access_state WHERE asset_key='sym:USDC'")
        self.assertEqual(st[0]["network"], "polygon")
        bsc = self.q("SELECT DISTINCT network FROM access_state WHERE asset_key='sym:T01'")
        self.assertEqual(bsc[0]["network"], "bsc")

    def test_collapsed_rows_prefer_live(self):
        rows = [asset("ARB", chain="ARB", enabled=False), asset("ARB", chain="ARBITRUM", enabled=True)]
        self.poll({"EUR": resp("EUR", catalog(extra=rows))}, T0)
        st = self.q("SELECT network, status FROM access_state WHERE asset_key='sym:ARB'")
        self.assertEqual([(r["network"], r["status"]) for r in st], [("arbitrum", "LIVE")])

    def test_prices_stripped_so_identical_polls_dedupe_raw(self):
        self.poll({"EUR": resp("EUR", catalog(price=1.0))}, T0)
        self.poll({"EUR": resp("EUR", catalog(price=2.0))}, T0 + H)
        blobs = self.q("SELECT json FROM raw_blob")
        self.assertEqual(len(blobs), 1)
        self.assertNotIn('"price"', blobs[0]["json"])
        self.assertEqual(self.q("SELECT * FROM access_event"), [])

    def test_env_fiats(self):
        os.environ["RAMP_FIATS"] = "usd, krw"
        try:
            self.assertEqual(ramp.configured_fiats(), ("USD", "KRW"))
        finally:
            del os.environ["RAMP_FIATS"]
        self.assertEqual(ramp.configured_fiats(), ramp.DEFAULT_FIATS)


if __name__ == "__main__":
    unittest.main()
