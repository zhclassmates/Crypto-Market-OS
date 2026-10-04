"""Coinone adapter tests: fixed fixture (adapters/fixtures/coinone), in-memory SQLite, no network."""
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

from adapters import coinone  # noqa: E402
from adapters.test_upbit import FakeHttp, ingest  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "coinone")
H = 3600 * 1000
T0 = 1_790_000_000_000
URL = coinone.BASE_URL.format(quote="KRW")


def load():
    with open(os.path.join(FIX, "markets_krw.json"), encoding="utf-8") as f:
        return json.load(f)


class CoinoneTest(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        coinone.register(self.conn, at=T0)

    def tearDown(self):
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def poll(self, body, at):
        return ingest(self.conn, "coinone_market", coinone.fetch_markets(FakeHttp({URL: body})), at)

    def status(self, sym):
        return self.q("SELECT status FROM access_state WHERE asset_key=?", (f"sym:{sym}",))[0]["status"]

    def test_baseline_and_status_mapping(self):
        r = self.poll(load(), T0)
        self.assertEqual((r["KRW"]["outcome"], r["KRW"]["valid"]), ("BASELINE", 12))
        self.assertEqual(self.status("BTC"), "LIVE")
        self.assertEqual(self.status("KLAY"), "SUSPENDED")          # maintenance_status=1
        self.assertEqual(self.status("ATOM"), "SUSPENDED")          # trade_status=2 (buy disabled)
        for ts, want in ((0, "SUSPENDED"), (1, "LIVE"), (2, "SUSPENDED"), (3, "LIVE")):
            it = coinone.map_market({"quote_currency": "KRW", "target_currency": "x", "trade_status": ts, "maintenance_status": 0})
            self.assertEqual(it["status"], want, ts)
        self.assertEqual(it["symbol"], "X")

    def test_new_market_suspend_resume(self):
        self.poll(load(), T0)
        d = load()
        d["markets"].append(dict(d["markets"][0], target_currency="NEWT"))
        for m in d["markets"]:
            if m["target_currency"] == "ETH":
                m["trade_status"] = 0
            if m["target_currency"] == "KLAY":
                m["maintenance_status"] = 0
        self.poll(d, T0 + H)
        ev = sorted((e["asset_key"], e["event_type"]) for e in self.q("SELECT * FROM access_event"))
        self.assertEqual(ev, [("sym:ETH", "SPOT_SUSPENDED"), ("sym:KLAY", "SPOT_RESUMED"), ("sym:NEWT", "SPOT_LISTED")])
        obs = self.q("SELECT url FROM source_observation WHERE source_id='coinone_market'")
        self.assertTrue(obs and all(o["url"] is None for o in obs))                     # snapshots carry no url

    def test_volatile_fields_stripped(self):
        self.poll(load(), T0)
        d = load()
        for m in d["markets"]:
            m["order_book_units"] = ["1.0"]
            m["max_price"] = "1.0"
        d["server_time"] = 1
        self.poll(d, T0 + H)
        self.assertEqual(self.q("SELECT * FROM access_event"), [])
        blob = json.dumps([r["json"] for r in self.q("SELECT json FROM raw_blob")])
        self.assertNotIn("order_book_units", blob)
        self.assertNotIn("max_price", blob)

    def test_errors_are_down_not_partial(self):
        self.poll(load(), T0)
        bad = [{"result": "error", "error_code": "4", "errorMsg": "Blocked user access."},
               {"result": "success", "markets": []},
               dict(load(), markets=[dict(m, quote_currency="BTC") for m in load()["markets"]]),
               RuntimeError("HTTP 503")]
        for i, body in enumerate(bad):
            r = self.poll(body, T0 + (i + 1) * H)
            self.assertIn("error", r["KRW"], body)
        self.assertEqual(self.q("SELECT * FROM access_event"), [])
        self.assertEqual(self.q("SELECT status FROM source_health WHERE source_id='coinone_market'")[0]["status"], "DOWN")
        r = self.poll(load(), T0 + 9 * H)
        self.assertEqual(r["KRW"]["outcome"], "DIFF")

    def test_runner_once(self):
        import access_db
        import access_sched as S
        db = os.path.join(tempfile.mkdtemp(prefix="ar_coinone_"), "a.sqlite")
        w = access_db.Writer(db).start()
        try:
            r = S.Runner(w, FakeHttp({URL: copy.deepcopy(load())}),
                         catalog=[S.Entry("coinone_market", 30, "adapters.coinone")], discover_package=None)
            out = r.run_once()
            self.assertTrue(out[0]["ok"], out)
            self.assertEqual(out[0]["rows"], 12)
        finally:
            w.stop()


if __name__ == "__main__":
    unittest.main()
