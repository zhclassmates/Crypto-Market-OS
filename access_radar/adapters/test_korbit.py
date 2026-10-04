"""Korbit (DigitalX) adapter tests: fixed fixtures (adapters/fixtures/korbit), in-memory SQLite, no network."""
import copy
import json
import logging
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import radar_core as rc  # noqa: E402

from adapters import korbit, upbit  # noqa: E402
from adapters.test_upbit import FakeHttp, announce, ingest  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "korbit")
H = 3600 * 1000
T0 = 1_790_000_000_000


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def routes(**over):
    r = {korbit.url("/v2/currencyPairs"): load("currency_pairs.json"),
         korbit.url("/v2/currencies"): load("currencies.json"),
         korbit.url("/v2/notices"): load("notices.json"),
         korbit.url("/v2/marketAlerts"): load("market_alerts.json")}
    r.update({korbit.url(k): v for k, v in over.items()})
    return r


class Base(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        korbit.register(self.conn, at=T0)

    def tearDown(self):
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def events(self):
        return sorted((e["asset_key"], e["access_kind"], e["network"], e["event_type"])
                      for e in self.q("SELECT e.*, s.network FROM access_event e JOIN access_state s USING(access_id)"))


class PairsTest(Base):
    def poll(self, body, at):
        return ingest(self.conn, "korbit_pairs", korbit.fetch_pairs(FakeHttp({korbit.url("/v2/currencyPairs"): body})), at)

    def test_baseline_stopped_and_changes(self):
        r = self.poll(load("currency_pairs.json"), T0)
        self.assertEqual((r["KRW"]["outcome"], r["KRW"]["valid"]), ("BASELINE", 12))
        st = self.q("SELECT status FROM access_state WHERE asset_key='sym:XRP'")[0]
        self.assertEqual(st["status"], "SUSPENDED")
        d = load("currency_pairs.json")
        d["data"].append(dict(d["data"][0], symbol="ena_krw", baseCurrency="ena"))
        for p in d["data"]:
            if p["symbol"] == "xrp_krw":
                p["status"] = "launched"
        self.poll(d, T0 + H)
        self.assertEqual(self.events(), [("sym:ENA", "SPOT", "", "SPOT_LISTED"), ("sym:XRP", "SPOT", "", "SPOT_RESUMED")])

    def test_errors(self):
        for body in ({"success": False, "error": {"code": "X"}}, {"success": True, "data": []}, [1, 2]):
            with self.assertRaises(upbit.BadResponse):
                korbit.fetch_pairs(FakeHttp({korbit.url("/v2/currencyPairs"): body}))
        self.assertTrue(korbit.url("/v2/x").startswith(korbit.BASE_URL))


class NetworksTest(Base):
    def poll(self, body, at):
        return ingest(self.conn, "korbit_networks", korbit.fetch_networks(FakeHttp({korbit.url("/v2/currencies"): body})), at)

    def test_baseline_items_and_canonical_networks(self):
        r = self.poll(load("currencies.json"), T0)
        self.assertEqual((r["deposit"]["outcome"], r["deposit"]["valid"]), ("BASELINE", 14))
        self.assertEqual(r["withdraw"]["valid"], 14)
        rows = {(s["asset_key"], s["access_kind"], s["network"]): s["status"] for s in self.q("SELECT * FROM access_state")}
        self.assertEqual(rows[("sym:USDT", "DEPOSIT_NETWORK", "tron")], "LIVE")
        self.assertEqual(rows[("sym:USDT", "WITHDRAW_NETWORK", "ethereum")], "LIVE")
        self.assertEqual(rows[("sym:ETH", "DEPOSIT_NETWORK", "base")], "LIVE")
        self.assertEqual(rows[("sym:DOT", "DEPOSIT_NETWORK", "polkadot")], "SUSPENDED")  # depositStatus stopped
        self.assertEqual(rows[("sym:DOT", "WITHDRAW_NETWORK", "polkadot")], "LIVE")
        self.assertEqual(rows[("sym:AVAX", "DEPOSIT_NETWORK", "avalanche")], "LIVE")     # 'AVAX' network code
        self.assertEqual(rows[("sym:ADA", "DEPOSIT_NETWORK", "cardano")], "LIVE")
        self.assertNotIn("sym:KRW", {k[0] for k in rows})                                # fiat skipped

    def test_deposit_stop_new_network_and_fee_change(self):
        self.poll(load("currencies.json"), T0)
        d = load("currencies.json")
        for c in d["data"]:
            for n in c.get("networkList") or []:
                n["withdrawalTxFee"] = "9.99"                                            # volatile: ignored
                if c["name"] == "sol":
                    n["depositStatus"] = "stopped"
            if c["name"] == "usdt":
                c["networkList"].append(dict(c["networkList"][0], name="SOL", fullName="Solana",
                                             contractAddress="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"))
        self.poll(d, T0 + H)
        self.assertEqual(self.events(), [
            ("sym:SOL", "DEPOSIT_NETWORK", "solana", "DEPOSIT_SUSPENDED"),
            ("sym:USDT", "DEPOSIT_NETWORK", "solana", "DEPOSIT_ENABLED"),
            ("sym:USDT", "WITHDRAW_NETWORK", "solana", "WITHDRAW_ENABLED")])

    def test_collapsed_networks_prefer_live(self):
        dep, wd = korbit.map_currencies([{"name": "arb", "networkList": [
            {"name": "ARB", "depositStatus": "stopped", "withdrawalStatus": "stopped"},
            {"name": "ARBITRUM", "depositStatus": "launched", "withdrawalStatus": "stopped"}]}])
        self.assertEqual([(i["network"], i["status"]) for i in dep], [("arbitrum", "LIVE")])
        self.assertEqual([(i["network"], i["status"]) for i in wd], [("arbitrum", "SUSPENDED")])

    def test_bad_shape(self):
        with self.assertRaises(upbit.BadResponse):
            korbit.fetch_networks(FakeHttp({korbit.url("/v2/currencies"): {"success": True, "data": [{"name": "krw"}]}}))


class NoticeTest(Base):
    def test_notices_and_alerts(self):
        anns = korbit.fetch_notices(FakeHttp(routes()))
        by = {a["source_event_id"]: a for a in anns}
        self.assertEqual(set(by), {"korbit:notice:4Oy9q6ALiM7jABzMt32ul5", "korbit:notice:7Abc9q6ALiM7jABzMt32xx",
                                   "korbit:alert:doge_krw:warning:1790000500000"})
        lst = by["korbit:notice:4Oy9q6ALiM7jABzMt32ul5"]
        self.assertEqual((lst["action"], lst["announced_at"]), ("LISTING", 1790000000000))
        self.assertEqual(lst["targets"], [{"symbol": "SUI", "access_kind": "SPOT", "quote": ""}])
        self.assertEqual(lst["url"], "https://digitalx.miraeasset.com/notice/detail/?noticeId=4Oy9q6ALiM7jABzMt32ul5")
        d = by["korbit:notice:7Abc9q6ALiM7jABzMt32xx"]
        self.assertEqual((d["action"], d["effective_at"]), ("DELISTING", upbit.kst_ms(2026, 10, 20, 15, 0)))
        a = by["korbit:alert:doge_krw:warning:1790000500000"]                         # marker only, never SUSPENDED
        self.assertEqual((a["action"], a["warning"]), ("SUSPEND", "DESIGNATED"))
        self.assertEqual(a["targets"], [{"asset_key": "warning:DOGE", "symbol": "DOGE", "access_kind": "SPOT", "quote": "KRW"}])
        self.assertIsNone(a["url"])                                                       # marketAlerts have no link

    def test_alert_failure_keeps_notices(self):
        anns = korbit.fetch_notices(FakeHttp(routes(**{"/v2/marketAlerts": RuntimeError("HTTP 500")})))
        self.assertEqual(len(anns), 2)
        with self.assertRaises(RuntimeError):
            korbit.fetch_notices(FakeHttp(routes(**{"/v2/notices": RuntimeError("HTTP 500")})))
        with self.assertRaises(upbit.BadResponse):
            korbit.fetch_notices(FakeHttp(routes(**{"/v2/notices": {"success": False}})))

    def test_url_fallback(self):
        self.assertEqual(korbit.notice_url({"url": "/notice/detail/?noticeId=AbC123xyz"}),
                         "https://digitalx.miraeasset.com/notice/detail/?noticeId=AbC123xyz")
        self.assertEqual(korbit.notice_url({"noticeId": "ZZZ999"}),
                         "https://digitalx.miraeasset.com/notice/detail/?noticeId=ZZZ999")
        self.assertIsNone(korbit.notice_url({"title": "x"}))

    def test_id_fallback(self):
        self.assertEqual(korbit.notice_event_id({"url": "https://www.korbit.co.kr/notice/detail/AbCdEf123"}),
                         "korbit:notice:AbCdEf123")
        h1 = korbit.notice_event_id({"title": "제목", "createdAt": 1})
        self.assertEqual(h1, korbit.notice_event_id({"title": " 제목 ", "createdAt": 1}))
        self.assertTrue(h1.startswith("korbit:notice:h"))

    def test_ingest_idempotent_and_suspend(self):
        pairs = load("currency_pairs.json")
        no_sui = dict(pairs, data=[p for p in pairs["data"] if p["symbol"] != "sui_krw"])
        ingest(self.conn, "korbit_pairs", korbit.fetch_pairs(FakeHttp({korbit.url("/v2/currencyPairs"): no_sui})),
               1_790_000_400_000)
        anns = korbit.fetch_notices(FakeHttp(routes()))
        announce(self.conn, "korbit_notice", anns, 1_790_000_600_000)
        again = announce(self.conn, "korbit_notice", korbit.fetch_notices(FakeHttp(routes())), 1_790_000_660_000)
        self.assertTrue(all(r["duplicate"] for r in again))
        ev = {(e["asset_key"], e["quote"], e["event_type"]) for e in self.q("SELECT * FROM access_event")}
        self.assertFalse(any(k.startswith("warning:") or t.endswith("SUSPENDED") for k, _, t in ev), ev)
        self.assertEqual(self.q("SELECT status FROM access_state WHERE asset_key='sym:DOGE'")[0]["status"], "LIVE")
        self.assertEqual(self.q("SELECT status FROM access_state WHERE asset_key='warning:DOGE'")[0]["status"], "NONE")
        self.assertEqual(self.q("SELECT * FROM rejected_transition"), [])
        self.assertIn(("sym:SUI", "", "SPOT_ANNOUNCED"), ev)          # quote-less listing notice = wildcard
        self.assertIn(("sym:DOT", "KRW", "SPOT_DELISTED_SCHEDULED"), ev)
        ingest(self.conn, "korbit_pairs", korbit.fetch_pairs(FakeHttp({korbit.url("/v2/currencyPairs"): pairs})),
               1_790_003_600_000)
        sui = self.q("SELECT quote, event_type, to_status FROM access_event WHERE asset_key='sym:SUI'")
        self.assertEqual([(e["quote"], e["event_type"], e["to_status"]) for e in sui], [("KRW", "SPOT_LISTED", "LIVE")])
        urls = {(o["source_id"], o["asset_key"], o["url"]) for o in self.q(
            "SELECT source_id, asset_key, url FROM source_observation WHERE asset_key IN ('sym:SUI', 'warning:DOGE')")}
        self.assertEqual(urls, {
            ("korbit_notice", "sym:SUI", "https://digitalx.miraeasset.com/notice/detail/?noticeId=4Oy9q6ALiM7jABzMt32ul5"),
            ("korbit_notice", "warning:DOGE", None),                                     # alert marker: no url
            ("korbit_pairs", "sym:SUI", None)})                                          # snapshot: no url


class RunnerIntegrationTest(unittest.TestCase):
    def test_runner_once(self):
        import access_db
        import access_sched as S
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        db = os.path.join(tempfile.mkdtemp(prefix="ar_korbit_"), "a.sqlite")
        w = access_db.Writer(db).start()
        try:
            cat = [S.Entry(sid, 60, "adapters.korbit") for sid in ("korbit_pairs", "korbit_networks", "korbit_notice")]
            r = S.Runner(w, FakeHttp(copy.deepcopy(routes())), catalog=cat, discover_package=None)
            out = {o["source_id"]: o for o in r.run_once()}
            self.assertTrue(all(o["ok"] for o in out.values()), out)
            self.assertEqual(out["korbit_networks"]["rows"], 28)
        finally:
            w.stop()


if __name__ == "__main__":
    unittest.main()
