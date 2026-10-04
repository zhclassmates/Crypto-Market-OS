"""Bithumb adapter tests: fixed fixtures (adapters/fixtures/bithumb), in-memory SQLite, no network."""
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

from adapters import bithumb, upbit  # noqa: E402
from adapters.test_upbit import FakeHttp, announce, ingest  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "bithumb")
H = 3600 * 1000
S = 1000


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


class Base(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        bithumb.register(self.conn, at=1)

    def tearDown(self):
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def events(self):
        return [(e["asset_key"], e["quote"], e["event_type"]) for e in self.q("SELECT * FROM access_event ORDER BY event_id")]


class MarketTest(Base):
    T0 = 1_790_000_000_000

    def poll(self, markets, at):
        http = FakeHttp({bithumb.MARKETS_URL: markets})
        return ingest(self.conn, "bithumb_market", bithumb.fetch_markets(http), at), http

    def test_baseline_scopes_and_caution_stays_live(self):
        self.assertFalse(bithumb.WARNING_AS_SUSPENDED)
        r, http = self.poll(load("market_all.json"), self.T0)
        self.assertEqual(http.calls[0][1], {"isDetails": "true"})
        self.assertEqual({k: v["outcome"] for k, v in r.items()}, {"KRW": "BASELINE", "BTC": "BASELINE"})
        st = self.q("SELECT status FROM access_state WHERE asset_key='sym:RFR' AND quote='KRW'")[0]
        self.assertEqual(st["status"], "LIVE")                           # market_warning CAUTION
        it = bithumb.map_market({"market": "KRW-RFR", "market_warning": "CAUTION"})
        self.assertEqual((it["status"], it["warning"]), ("LIVE", True))
        nxt = [dict(m, market_warning="CAUTION") if m["market"] == "KRW-BTC" else m for m in load("market_all.json")]
        self.poll(nxt, self.T0 + H)
        self.assertEqual(self.events(), [])

    def test_remove_min_elapsed_guards_fast_polls(self):
        src = self.q("SELECT remove_min_elapsed_ms, remove_confirm_misses FROM source WHERE source_id='bithumb_market'")[0]
        self.assertEqual(src["remove_min_elapsed_ms"], bithumb.REMOVE_MIN_ELAPSED_MS)
        self.assertGreaterEqual(bithumb.REMOVE_MIN_ELAPSED_MS, 60_000)
        base = load("market_all.json")
        self.poll(base, self.T0)
        gone = [m for m in base if m["market"] != "KRW-DOGE"]
        for i in range(1, 5):                                            # 4 misses within 8 seconds
            self.poll(gone, self.T0 + i * 2 * S)
        st = self.q("SELECT status FROM access_state WHERE asset_key='sym:DOGE' AND quote='KRW'")[0]
        self.assertEqual(st["status"], "LIVE")
        self.poll(gone, self.T0 + 2 * S + bithumb.REMOVE_MIN_ELAPSED_MS)
        self.assertIn(("sym:DOGE", "KRW", "SPOT_DELISTED"), self.events())

    def test_missing_btc_quote_is_down(self):
        base = load("market_all.json")
        self.poll(base, self.T0)
        r, _ = self.poll([m for m in base if m["market"].startswith("KRW-")], self.T0 + H)
        self.assertIn("error", r["BTC"])
        self.assertEqual(self.events(), [])

    def test_bad_shape_raises(self):
        with self.assertRaises(upbit.BadResponse):
            bithumb.fetch_markets(FakeHttp({bithumb.MARKETS_URL: {"status": "5600", "message": "x"}}))


class NoticeTest(Base):
    def fetch(self, rows):
        return bithumb.fetch_notices(FakeHttp({bithumb.NOTICES_URL: rows}))

    def test_request_and_parse(self):
        http = FakeHttp({bithumb.NOTICES_URL: load("notices.json")})
        anns = bithumb.fetch_notices(http)
        self.assertEqual(http.calls[0][1], {"count": 20})
        by = {a["title"]: a for a in anns}
        self.assertEqual(len(anns), 4)                                   # event + maintenance notices dropped
        lst = by["마이쉘(SHELL) 원화 마켓 추가"]
        self.assertEqual((lst["action"], lst["targets"]), ("LISTING", [{"symbol": "SHELL", "access_kind": "SPOT", "quote": "KRW"}]))
        self.assertEqual(lst["announced_at"], upbit.kst_ms(2025, 2, 28, 11, 12, 14))
        self.assertEqual(lst["announced_at"], 1740708734000)            # 2025-02-28 02:12:14 UTC
        d = by["리퍼리움(RFR) 거래지원 종료 안내 (3/14 15:00)"]
        self.assertEqual(d["action"], "DELISTING")
        self.assertEqual(d["effective_at"], upbit.kst_ms(2025, 3, 14, 15, 0))
        self.assertEqual([t["quote"] for t in d["targets"]], [""])               # radar_core quote wildcard
        wn = by["페페(PEPE) 투자유의 종목 지정 안내"]
        self.assertEqual((wn["action"], wn["warning"]), ("SUSPEND", "DESIGNATED"))         # marker only
        self.assertEqual([t["asset_key"] for t in wn["targets"]], ["warning:PEPE"])
        self.assertEqual(lst["source_event_id"], "bithumb:notice:1647199")
        self.assertEqual(lst["url"], "https://feed.bithumb.com/notice/1647199")              # pc_url as-is
        self.assertEqual(wn["url"], "https://feed.bithumb.com/notice/1647090")               # warning marker too
        w = by["트론(TRX) 네트워크 업그레이드에 따른 입출금 일시 중지 안내"]
        self.assertEqual({(t["access_kind"], t["network"]) for t in w["targets"]},
                         {("DEPOSIT_NETWORK", "tron"), ("WITHDRAW_NETWORK", "tron")})

    def test_notice_url_helper(self):
        self.assertEqual(bithumb.notice_url("/notice/1647199"), "https://feed.bithumb.com/notice/1647199")
        self.assertEqual(bithumb.notice_url("//feed.bithumb.com/notice/1"), "https://feed.bithumb.com/notice/1")
        self.assertIsNone(bithumb.notice_url(None))
        a = bithumb.parse_notice({"categories": ["마켓추가"], "title": "테스트(TST) 원화 마켓 추가",
                                  "published_at": "2025-02-28 11:00:00"})
        self.assertIsNone(a["url"])

    def test_id_from_pc_url(self):
        rows = load("notices.json")
        a1 = {a["title"]: a["source_event_id"] for a in self.fetch(rows)}
        self.assertEqual(sorted(a1.values()), ["bithumb:notice:1647080", "bithumb:notice:1647090",
                                               "bithumb:notice:1647100", "bithumb:notice:1647199"])
        rows2 = copy.deepcopy(rows)
        for r in rows2:
            r["title"] = "[수정] " + r["title"]                             # title edits keep the id
            r["modified_at"] = "2025-03-01 00:00:00"
        self.assertEqual(sorted(a["source_event_id"] for a in self.fetch(rows2)), sorted(a1.values()))
        self.assertEqual(bithumb.notice_event_id("t", "x", "https://feed.bithumb.com/notice/1647199?ref=a"),
                         "bithumb:notice:1647199")

    def test_hash_fallback_without_numeric_id(self):
        sev = bithumb.notice_event_id("마이쉘(SHELL) 원화 마켓 추가", "2025-02-28 11:12:14", "https://feed.bithumb.com/notice/")
        self.assertTrue(sev.startswith("bithumb:notice:h"))
        self.assertEqual(sev, bithumb.notice_event_id("  마이쉘(SHELL)  원화 마켓 추가 ", "2025-02-28 11:12:14", None))
        self.assertNotEqual(sev, bithumb.notice_event_id("마이쉘(SHELL) 원화 마켓 추가", "2025-02-28 11:12:15", None))
        rows = [dict(r, pc_url=None) for r in load("notices.json")]
        self.assertTrue(all(a["source_event_id"].startswith("bithumb:notice:h") for a in self.fetch(rows)))

    def test_idempotent_ingest_every_2s(self):
        anns = self.fetch(load("notices.json"))
        at = upbit.kst_ms(2025, 2, 28, 11, 13)
        first = announce(self.conn, "bithumb_notice", anns, at)
        for i in range(1, 4):
            again = announce(self.conn, "bithumb_notice", self.fetch(load("notices.json")), at + i * 2 * S)
            self.assertTrue(all(r["duplicate"] for r in again))
        self.assertGreater(sum(len(r["events"]) for r in first), 0)
        ev = {(e["asset_key"], e["event_type"]) for e in self.q("SELECT * FROM access_event")}
        self.assertIn(("sym:SHELL", "SPOT_ANNOUNCED"), ev)

    def test_quote_less_delisting_hits_existing_markets_only(self):
        at = upbit.kst_ms(2025, 2, 27, 17, 0)
        ingest(self.conn, "bithumb_market", bithumb.fetch_markets(FakeHttp({bithumb.MARKETS_URL: load("market_all.json")})), at)
        anns = [a for a in self.fetch(load("notices.json")) if a["action"] == "DELISTING"]
        r = announce(self.conn, "bithumb_notice", anns, at + H)
        self.assertEqual(r[0]["rejected"], 0)
        ev = self.q("SELECT quote, event_type FROM access_event WHERE asset_key='sym:RFR'")
        self.assertEqual([(e["quote"], e["event_type"]) for e in ev], [("KRW", "SPOT_DELISTED_SCHEDULED")])
        obs = self.q("SELECT obs_kind, url FROM source_observation WHERE source_id='bithumb_notice'")
        self.assertEqual([(o["obs_kind"], o["url"]) for o in obs], [("ANNOUNCEMENT", "https://feed.bithumb.com/notice/1647100")])
        nxt = load("market_all.json") + [{"market": "KRW-NEWB", "korean_name": "n", "english_name": "n", "market_warning": "NONE"}]
        ingest(self.conn, "bithumb_market", bithumb.fetch_markets(FakeHttp({bithumb.MARKETS_URL: nxt})), at + 2 * H)
        snap = self.q("SELECT url FROM source_observation WHERE source_id='bithumb_market'")
        self.assertTrue(snap and all(o["url"] is None for o in snap))

    def test_malformed_list_raises_not_partial(self):
        with self.assertRaises(upbit.BadResponse):
            self.fetch({"error": {"name": 400, "message": "x"}})
        rows = load("notices.json")
        for r in rows[:3]:
            r.pop("published_at")
        with self.assertRaises(upbit.BadResponse):
            self.fetch(rows)
        self.assertEqual(self.fetch([]), [])


class RunnerIntegrationTest(unittest.TestCase):
    def test_runner_once(self):
        import access_db
        import access_sched as S_
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        db = os.path.join(tempfile.mkdtemp(prefix="ar_bithumb_"), "a.sqlite")
        w = access_db.Writer(db).start()
        try:
            cat = [S_.Entry("bithumb_market", 30, "adapters.bithumb"), S_.Entry("bithumb_notice", 2, "adapters.bithumb")]
            http = FakeHttp({bithumb.MARKETS_URL: load("market_all.json"), bithumb.NOTICES_URL: load("notices.json")})
            r = S_.Runner(w, http, catalog=cat, discover_package=None)
            out = {o["source_id"]: o for o in r.run_once()}
            self.assertTrue(out["bithumb_market"]["ok"] and out["bithumb_notice"]["ok"], out)
            self.assertEqual(out["bithumb_notice"]["rows"], 4)
            conn = access_db.connect(db)
            try:
                kinds = dict(conn.execute("SELECT source_id, kind FROM source").fetchall())
                self.assertEqual(kinds, {"bithumb_market": "SNAPSHOT", "bithumb_notice": "ANNOUNCEMENT"})
            finally:
                conn.close()
        finally:
            w.stop()


if __name__ == "__main__":
    unittest.main()
