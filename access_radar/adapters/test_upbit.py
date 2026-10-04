"""Upbit adapter tests: fixed fixtures (adapters/fixtures/upbit), in-memory SQLite, no network.

The WebSocket client is exercised over a local socket.socketpair(); the stream loop with a fake transport.
"""
import base64
import copy
import hashlib
import hmac
import json
import logging
import os
import socket
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import radar_core as rc  # noqa: E402

from adapters import upbit  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "upbit")
H = 3600 * 1000
T0 = 1_790_000_000_000


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


class FakeHttp:
    """Routes by URL prefix; a value may be an Exception (raised) or a callable(url, params) -> body."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.kwargs = []

    def get_json(self, url, params=None, headers=None, **kw):
        self.calls.append((url, dict(params or {}), headers))
        self.kwargs.append(kw)
        for prefix in sorted(self.routes, key=len, reverse=True):
            if url.startswith(prefix):
                v = self.routes[prefix]
                v = v(url, params or {}) if callable(v) else v
                if isinstance(v, BaseException):
                    raise v
                return copy.deepcopy(v)
        raise AssertionError(f"unexpected url {url}")


def ingest(conn, source_id, out, at):
    """Mirror of the runner's write path: Exception scopes -> report_fetch_error, lists -> ingest_snapshot."""
    res = {}
    for scope, items in out.items():
        if isinstance(items, BaseException):
            rc.report_fetch_error(conn, source_id, scope, f"{type(items).__name__}: {items}", at=at)
            res[scope] = {"error": str(items)}
        else:
            res[scope] = rc.ingest_snapshot(conn, source_id, scope, items, fetched_at=at)
    return res


def announce(conn, source_id, anns, at):
    return [rc.ingest_announcement(conn, source_id, dict(a, observed_at=at)) for a in anns]


class Base(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        upbit.register(self.conn, at=T0)

    def tearDown(self):
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def events(self):
        return [(e["asset_key"], e["quote"], e["event_type"]) for e in self.q("SELECT * FROM access_event ORDER BY event_id")]


class MarketTest(Base):
    def poll(self, markets, at):
        http = FakeHttp({upbit.MARKETS_URL: markets})
        return ingest(self.conn, "upbit_market", upbit.fetch_markets(http), at), http

    def test_url_and_scopes_baseline(self):
        r, http = self.poll(load("market_all.json"), T0)
        self.assertEqual(http.calls[0][:2], (upbit.MARKETS_URL, {"is_details": "true"}))
        self.assertNotIn("deadline", http.kwargs[0])                          # market endpoints: no deadline
        self.assertEqual(set(r), {"KRW", "BTC", "USDT"})
        self.assertEqual({k: v["outcome"] for k, v in r.items()}, {"KRW": "BASELINE", "BTC": "BASELINE", "USDT": "BASELINE"})
        self.assertEqual((r["KRW"]["valid"], r["BTC"]["valid"], r["USDT"]["valid"]), (20, 11, 8))
        self.assertEqual(self.events(), [])

    def test_warning_stays_live(self):
        self.assertFalse(upbit.WARNING_AS_SUSPENDED)
        self.poll(load("market_all.json"), T0)
        st = {(s["asset_key"], s["quote"]): s["status"] for s in self.q("SELECT * FROM access_state")}
        self.assertEqual(st[("sym:OMG", "KRW")], "LIVE")               # market_event.warning (유의 종목)
        self.assertEqual(st[("sym:DOGE", "KRW")], "LIVE")              # caution (주의 종목)
        self.assertEqual(set(st.values()), {"LIVE"})
        self.assertEqual(upbit.market_status({"market": "KRW-X", "market_warning": "CAUTION"}), "LIVE")
        it = upbit.map_market({"market": "KRW-X", "market_event": {"warning": True}})
        self.assertEqual((it["status"], it["warning"]), ("LIVE", True))
        self.assertTrue(it["raw"]["market_event"]["warning"])
        self.assertFalse(upbit.map_market({"market": "KRW-Y", "market_warning": "NONE"})["warning"])

    def test_listing_warning_and_release(self):
        base = load("market_all.json")
        self.poll(base, T0)
        nxt = copy.deepcopy(base) + [{"market": "KRW-ENA", "korean_name": "에테나", "english_name": "Ethena",
                                      "market_event": {"warning": False, "caution": {}}}]
        for m in nxt:
            if m["market"] == "KRW-SAND":
                m["market_event"]["warning"] = True
            if m["market"] == "KRW-OMG":
                m["market_event"]["warning"] = False
        self.poll(nxt, T0 + H)
        self.assertEqual(self.events(), [("sym:ENA", "KRW", "SPOT_LISTED")])   # warning flips are not events

    def test_missing_quote_scope_is_down_not_removed(self):
        base = load("market_all.json")
        self.poll(base, T0)
        no_usdt = [m for m in base if not m["market"].startswith("USDT-")]
        for i in range(4):
            r, _ = self.poll(no_usdt, T0 + (i + 1) * H)
            self.assertIn("error", r["USDT"])
            self.assertEqual(r["KRW"]["outcome"], "DIFF")
        self.assertEqual(self.events(), [])
        h = self.q("SELECT status FROM source_health WHERE source_id='upbit_market' AND scope='USDT'")[0]
        self.assertEqual(h["status"], "DOWN")

    def test_bad_shape_raises(self):
        for body in ({"error": {"name": 400, "message": "x"}}, [], None):
            with self.assertRaises(upbit.BadResponse):
                upbit.fetch_markets(FakeHttp({upbit.MARKETS_URL: body}))

    def test_junk_row_counts_invalid_and_skips_misses(self):
        base = load("market_all.json")
        self.poll(base, T0)
        nxt = [m for m in base if m["market"] != "KRW-ADA"] + [{"market": "garbage"}]
        r, _ = self.poll(nxt, T0 + H)
        self.assertEqual(r["KRW"]["invalid"], 1)
        self.assertIn("miss counting skipped", r["KRW"]["note"])
        miss = self.q("""SELECT s.miss_count AS miss_count FROM source_item_state s JOIN access_state a USING(access_id)
                         WHERE a.asset_key='sym:ADA' AND a.quote='KRW'""")[0]
        self.assertEqual(miss["miss_count"], 0)

    def test_new_quote_gets_its_own_silent_baseline(self):
        base = load("market_all.json")
        self.poll(base, T0)
        r, _ = self.poll(base + [{"market": "SGD-BTC", "korean_name": "x", "english_name": "x"}] * 1, T0 + H)
        self.assertEqual(r["SGD"]["outcome"], "BASELINE")
        self.assertEqual(self.events(), [])

    def test_fetch_callable_also_supported(self):
        calls = []

        def fetch(url, headers=None):
            calls.append(url)
            return load("market_all.json")
        out = upbit.fetch_markets(fetch)
        self.assertEqual(calls, [upbit.MARKETS_URL + "?is_details=true"])
        self.assertEqual(len(out["KRW"]), 20)


class JwtTest(unittest.TestCase):
    def test_hs256_token(self):
        tok = upbit.make_jwt("AK", "SK", nonce="n-1")
        h, p, s = tok.split(".")
        pad = lambda x: x + "=" * (-len(x) % 4)  # noqa: E731
        self.assertEqual(json.loads(base64.urlsafe_b64decode(pad(h))), {"alg": "HS256", "typ": "JWT"})
        self.assertEqual(json.loads(base64.urlsafe_b64decode(pad(p))), {"access_key": "AK", "nonce": "n-1"})
        sig = hmac.new(b"SK", f"{h}.{p}".encode(), hashlib.sha256).digest()
        self.assertEqual(base64.urlsafe_b64decode(pad(s)), sig)
        self.assertNotIn("=", tok)
        self.assertNotEqual(upbit.make_jwt("AK", "SK"), upbit.make_jwt("AK", "SK"))   # fresh uuid nonce

    def test_credentials_from_env(self):
        self.assertIsNone(upbit.read_credentials({}))
        self.assertIsNone(upbit.read_credentials({"UPBIT_ACCESS_KEY": "a"}))
        self.assertEqual(upbit.read_credentials({"UPBIT_ACCESS_KEY": "a", "UPBIT_SECRET_KEY": "b"}), ("a", "b"))
        self.assertEqual((upbit.ENV_ACCESS_KEY, upbit.ENV_SECRET_KEY), ("UPBIT_ACCESS_KEY", "UPBIT_SECRET_KEY"))


class ClassifierTest(unittest.TestCase):
    CASES = [
        ("[거래] 아이오넷(IO) 신규 거래지원 안내 (KRW, BTC, USDT 마켓)", "LISTING"),
        ("[거래] 신규 거래 지원 안내 - 레이어제로(ZRO) (KRW 마켓)", "LISTING"),
        ("마이쉘(SHELL) 원화 마켓 추가", "LISTING"),
        ("[Trade] New digital asset listing: Ethena (ENA) (KRW market)", "LISTING"),
        ("[거래] 거래지원 종료 안내 (OMG)", "DELISTING"),
        ("[거래지원종료] 리퍼리움(RFR) 거래지원 종료 안내 (3/14 15:00)", "DELISTING"),
        ("[Trade] Notice of termination of trading support (OMG)", "DELISTING"),
        ("[거래] 유의 종목 지정 안내 (SAND)", "WARNING"),
        ("페페(PEPE) 투자유의 종목 지정 안내", "WARNING"),
        ("[Trade] Designation of investment warning (SAND)", "WARNING"),
        ("[거래] 유의 종목 지정 및 거래지원 종료 안내 (SAND)", "DELISTING"),
        ("[입출금] 이더리움(ETH) 네트워크 업그레이드에 따른 입출금 일시 중단 안내", "SUSPEND"),
        ("Temporary suspension of deposits and withdrawals for Tron (TRX)", "SUSPEND"),
        ("[거래] 유의 종목 지정 해제 안내 (SAND)", "WARNING_LIFTED"),
        ("페페(PEPE) 투자유의 종목 지정 해제 안내", "WARNING_LIFTED"),
        ("[입출금] 이더리움(ETH) 입출금 재개 안내", "RESUME"),
        ("마이쉘(SHELL) 원화 마켓 추가 기념 에어드랍 이벤트", None),
        ("[거래] 거래 유의 촉구 안내 (XYZ)", None),
        ("[거래] 거래지원 종료 일정 연기 안내 (ABC)", None),
        ("[점검] 서버 점검 안내", None),
    ]

    def test_titles(self):
        for title, want in self.CASES:
            self.assertEqual(upbit.classify_title(title), want, title)

    def test_targets(self):
        t = upbit.build_targets("LISTING", "[거래] 아이오넷(IO) 신규 거래지원 안내 (KRW, BTC, USDT 마켓)")
        self.assertEqual([(x["symbol"], x["quote"]) for x in t], [("IO", "KRW"), ("IO", "BTC"), ("IO", "USDT")])
        t = upbit.build_targets("LISTING", "[거래] 에테나(ENA) 신규 거래지원 안내")
        self.assertEqual([(x["symbol"], x["quote"]) for x in t], [("ENA", "")])            # wildcard quote
        t = upbit.build_targets("DELISTING", "[거래] 거래지원 종료 안내 (OMG)")
        self.assertEqual([(x["symbol"], x["quote"]) for x in t], [("OMG", "")])             # radar_core wildcard
        t = upbit.build_targets("DELISTING", "[거래] 거래지원 종료 안내 (OMG) (BTC 마켓)")
        self.assertEqual([(x["symbol"], x["quote"]) for x in t], [("OMG", "BTC")])
        t = upbit.build_targets("SUSPEND", "[입출금] 이더리움(ETH) 네트워크 업그레이드에 따른 입출금 일시 중단 안내")
        self.assertEqual({(x["access_kind"], x["network"], x["quote"]) for x in t},
                         {("DEPOSIT_NETWORK", "ethereum", ""), ("WITHDRAW_NETWORK", "ethereum", "")})
        self.assertEqual(upbit.build_targets("LISTING", "신규 거래지원 안내"), [])               # no ticker -> nothing

    def test_datetimes_are_kst(self):
        ref = upbit.kst_ms(2026, 7, 15, 10, 0)
        self.assertEqual(upbit.find_datetime_kst("거래지원 종료 안내 (7/29 15:00)", ref), upbit.kst_ms(2026, 7, 29, 15, 0))
        self.assertEqual(upbit.find_datetime_kst("2026년 7월 29일 (수) 오후 3시", ref), upbit.kst_ms(2026, 7, 29, 15, 0))
        self.assertEqual(upbit.find_datetime_kst("2026-07-29 15:00", ref), upbit.kst_ms(2026, 7, 29, 6 + 9, 0))
        self.assertEqual(upbit.kst_ms(2026, 7, 29, 15, 0), 1785304800000)                    # 06:00 UTC
        ref_dec = upbit.kst_ms(2026, 12, 20, 10, 0)
        self.assertEqual(upbit.find_datetime_kst("(1/5 15:00)", ref_dec), upbit.kst_ms(2027, 1, 5, 15, 0))
        self.assertIsNone(upbit.find_datetime_kst("버전 1/2 업데이트", ref))                    # bare M/d ignored
        self.assertEqual(upbit.parse_ts_ms("2025-02-28 15:00:00"), upbit.kst_ms(2025, 2, 28, 15, 0))
        self.assertEqual(upbit.parse_ts_ms("2026-07-14T16:36:34+09:00"), upbit.kst_ms(2026, 7, 14, 16, 36, 34))


class NoticeParseTest(Base):
    def msgs(self):
        return load("ws_messages.json")["messages"]

    def test_ws_messages(self):
        m = self.msgs()
        a = upbit.handle_ws_payload(json.dumps(m[0]).encode())[0]
        self.assertEqual(a["action"], "LISTING")
        self.assertEqual(a["source_event_id"], "upbit:notice:562593104")
        self.assertEqual([(t["symbol"], t["quote"]) for t in a["targets"]], [("ZRO", "KRW"), ("ZRO", "BTC"), ("ZRO", "USDT")])
        self.assertEqual(a["announced_at"], upbit.kst_ms(2026, 7, 14, 16, 36, 34))
        self.assertEqual(a["effective_at"], upbit.kst_ms(2026, 7, 14, 18, 0))
        self.assertEqual(a["source_detected_at"], 1752478594123)
        self.assertEqual(a["url"], "https://upbit.com/service_center/notice?id=562593104")   # built from the id

        d = upbit.handle_ws_payload(json.dumps(m[1]))[0]
        self.assertEqual(d["action"], "DELISTING")
        self.assertEqual(d["effective_at"], upbit.kst_ms(2026, 7, 29, 15, 0))     # keyword window, not the 1st date
        self.assertEqual([t["quote"] for t in d["targets"]], [""])               # wildcard, no fan-out

        wn = upbit.handle_ws_payload(json.dumps(m[2]))[0]                         # 유의 종목 지정 -> marker only
        self.assertEqual((wn["action"], wn["warning"], wn["raw"]["warning"]), ("SUSPEND", "DESIGNATED", "DESIGNATED"))
        self.assertEqual(wn["targets"], [{"asset_key": "warning:SAND", "symbol": "SAND", "access_kind": "SPOT", "quote": ""}])
        self.assertEqual(wn["url"], "https://upbit.com/service_center/notice?id=562593300")
        w = upbit.handle_ws_payload(json.dumps(m[3]))[0]
        self.assertEqual({t["access_kind"] for t in w["targets"]}, {"DEPOSIT_NETWORK", "WITHDRAW_NETWORK"})
        self.assertEqual(upbit.handle_ws_payload(json.dumps(m[4])), [])           # event category / airdrop

        u = upbit.handle_ws_payload(json.dumps(m[5]))[0]                          # UPDATED with moved listed_at
        self.assertEqual(u["source_event_id"], f"upbit:notice:562593200:u{upbit.kst_ms(2026, 7, 16, 12, 0)}")
        self.assertEqual(u["effective_at"], upbit.kst_ms(2026, 8, 5, 15, 0))

        s = upbit.handle_ws_payload(json.dumps(m[6]))[0]                          # SIMPLE (abbreviated) format
        self.assertEqual((s["action"], s["warning"], s["source_event_id"]), ("RESUME", "LIFTED", "upbit:notice:562593600"))
        self.assertTrue(all(t["asset_key"].startswith(upbit.WARNING_ASSET_PREFIX) for t in s["targets"]))
        self.assertEqual(upbit.handle_ws_payload(b'{"status":"UP"}'), [])
        self.assertEqual(upbit.handle_ws_payload(b"not json"), [])
        with self.assertRaises(upbit.UpbitWsError):
            upbit.handle_ws_payload(json.dumps(load("ws_messages.json")["error"]))

    def test_raw_has_no_volatile_timestamp_and_body_is_capped(self):
        m = dict(self.msgs()[1], body="x" * 10000)
        a = upbit.parse_notice(m)
        self.assertNotIn("timestamp", a["raw"])
        self.assertEqual(len(a["raw"]["body"]), upbit.BODY_RAW_MAX)

    def test_ingest_flow_listing_then_market(self):
        t0 = upbit.kst_ms(2026, 7, 14, 16, 0)            # around the fixture notice (16:36 KST) so the 72h merge applies
        markets = [x for x in load("market_all.json") if not x["market"].endswith("-ZRO")]
        ingest(self.conn, "upbit_market", upbit.fetch_markets(FakeHttp({upbit.MARKETS_URL: markets})), t0)
        anns = upbit.handle_ws_payload(json.dumps(self.msgs()[0]))
        r = announce(self.conn, "upbit_notice", anns, t0 + H)
        self.assertEqual(len(r[0]["events"]), 3)          # one ADD episode per quote
        self.assertEqual(announce(self.conn, "upbit_notice", anns, t0 + 2 * H)[0]["duplicate"], True)
        st = self.q("SELECT status FROM access_state WHERE asset_key='sym:ZRO' AND quote='KRW'")[0]
        self.assertEqual(st["status"], "ANNOUNCED")
        ingest(self.conn, "upbit_market", upbit.fetch_markets(FakeHttp({upbit.MARKETS_URL: load("market_all.json")})),
               t0 + 3 * H)
        ev = self.q("SELECT event_type, to_status FROM access_event WHERE asset_key='sym:ZRO' AND quote='KRW'")
        self.assertEqual([(e["event_type"], e["to_status"]) for e in ev], [("SPOT_LISTED", "LIVE")])   # same episode
        urls = {(o["source_id"], o["obs_kind"], o["url"]) for o in self.q(
            "SELECT source_id, obs_kind, url FROM source_observation WHERE asset_key='sym:ZRO'")}
        self.assertEqual(urls, {("upbit_notice", "ANNOUNCEMENT", "https://upbit.com/service_center/notice?id=562593104"),
                                ("upbit_market", "SNAPSHOT_NEW", None)})            # snapshots carry no url

    def test_warning_marker_never_changes_state(self):
        t0 = upbit.kst_ms(2026, 7, 16, 8, 0)
        ingest(self.conn, "upbit_market", upbit.fetch_markets(FakeHttp({upbit.MARKETS_URL: load("market_all.json")})), t0)
        n_trans = len(self.q("SELECT * FROM access_transition"))
        m = self.msgs()
        for i, msg in enumerate((m[2], m[6])):                              # designated, then lifted
            anns = upbit.handle_ws_payload(json.dumps(msg))
            r = announce(self.conn, "upbit_notice", anns, t0 + (i + 1) * H)
            self.assertEqual((r[0]["events"], r[0]["rejected"]), ([], 0))
        self.assertEqual(self.q("SELECT * FROM access_event"), [])
        self.assertEqual(self.q("SELECT * FROM rejected_transition"), [])
        self.assertEqual(len(self.q("SELECT * FROM access_transition")), n_trans)
        real = self.q("SELECT status FROM access_state WHERE asset_key='sym:SAND'")
        self.assertEqual({r["status"] for r in real}, {"LIVE"})
        marker = self.q("SELECT status FROM access_state WHERE asset_key='warning:SAND'")
        self.assertEqual([r["status"] for r in marker], ["NONE"])
        obs = self.q("""SELECT o.action, o.obs_kind, b.json FROM source_observation o JOIN raw_blob b USING(raw_id)
                        WHERE o.asset_key='warning:SAND' ORDER BY o.obs_id""")
        self.assertEqual([(o["action"], o["obs_kind"], json.loads(o["json"])["warning"]) for o in obs],
                         [("SUSPEND", "ANNOUNCEMENT", "DESIGNATED"), ("RESUME", "ANNOUNCEMENT", "LIFTED")])
        marker_urls = [o["url"] for o in self.q("SELECT url FROM source_observation WHERE asset_key='warning:SAND' ORDER BY obs_id")]
        self.assertEqual(marker_urls, ["https://upbit.com/service_center/notice?id=562593300",
                                       "https://upbit.com/service_center/notice?id=562593600"])

    def _two_quote_omg(self, at):
        markets = load("market_all.json") + [{"market": "BTC-OMG", "korean_name": "오미세고", "english_name": "OMG",
                                              "market_event": {"warning": False, "caution": {}}}]
        ingest(self.conn, "upbit_market", upbit.fetch_markets(FakeHttp({upbit.MARKETS_URL: markets})), at)
        st = self.q("SELECT quote, status FROM access_state WHERE asset_key='sym:OMG' ORDER BY quote")
        self.assertEqual([(r["quote"], r["status"]) for r in st], [("BTC", "LIVE"), ("KRW", "LIVE")])

    def test_quote_less_delisting_schedules_every_live_market(self):
        """STATE_MACHINE.md 6.1: quote '' DELISTING = wildcard over existing markets; future effective_at ->
        per-quote pending_removal_at + SPOT_DELISTED_SCHEDULED episode (status unchanged until effective)."""
        t0 = upbit.kst_ms(2026, 7, 15, 9, 0)
        self._two_quote_omg(t0)
        ann = upbit.handle_ws_payload(json.dumps(self.msgs()[1]))[0]          # "[거래] 거래지원 종료 안내 (OMG)"
        self.assertEqual([t["quote"] for t in ann["targets"]], [""])
        eff = upbit.kst_ms(2026, 7, 29, 15, 0)
        r = rc.ingest_announcement(self.conn, "upbit_notice", dict(ann, observed_at=t0 + H))
        self.assertEqual(r["rejected"], 0)
        self.assertEqual(len(r["obs"]), 1)
        self.assertEqual(sorted(r["wildcard"][0]["quotes"]), ["BTC", "KRW"])
        ev = self.q("SELECT * FROM access_event WHERE asset_key='sym:OMG' ORDER BY quote")
        self.assertEqual([(e["quote"], e["family"], e["event_type"], e["effective_at"]) for e in ev],
                         [("BTC", "REMOVE", "SPOT_DELISTED_SCHEDULED", eff), ("KRW", "REMOVE", "SPOT_DELISTED_SCHEDULED", eff)])
        links = self.q("SELECT event_id, obs_id, role FROM event_observation_link WHERE event_id IN (?, ?)",
                       (ev[0]["event_id"], ev[1]["event_id"]))
        self.assertEqual({l["obs_id"] for l in links}, {r["obs"][0]})        # both episodes -> the same observation
        self.assertEqual({l["event_id"] for l in links}, {ev[0]["event_id"], ev[1]["event_id"]})
        obs = self.q("SELECT access_id, quote, action FROM source_observation WHERE obs_id=?", (r["obs"][0],))[0]
        self.assertEqual((obs["access_id"], obs["quote"], obs["action"]), (None, "", "DELISTING"))
        st = self.q("SELECT quote, status, pending_removal_at FROM access_state WHERE asset_key='sym:OMG' ORDER BY quote")
        self.assertEqual([(x["quote"], x["status"], x["pending_removal_at"]) for x in st],
                         [("BTC", "LIVE", eff), ("KRW", "LIVE", eff)])
        self.assertEqual(self.q("SELECT * FROM rejected_transition"), [])
        # reaching effective_at: both markets REMOVED inside their existing episodes
        rc.process_due(self.conn, at=eff + 1)
        st = self.q("SELECT quote, status FROM access_state WHERE asset_key='sym:OMG' ORDER BY quote")
        self.assertEqual([(x["quote"], x["status"]) for x in st], [("BTC", "REMOVED"), ("KRW", "REMOVED")])
        ev2 = self.q("SELECT quote, event_type FROM access_event WHERE asset_key='sym:OMG' ORDER BY quote")
        self.assertEqual([(e["quote"], e["event_type"]) for e in ev2], [("BTC", "SPOT_DELISTED"), ("KRW", "SPOT_DELISTED")])
        self.assertEqual(self.q("SELECT * FROM rejected_transition"), [])

    def test_quote_less_delisting_without_date_removes_every_market(self):
        t0 = upbit.kst_ms(2026, 7, 15, 9, 0)
        self._two_quote_omg(t0)
        msg = dict(self.msgs()[1])
        msg.pop("body")                                                        # no effective time -> immediate
        ann = upbit.handle_ws_payload(json.dumps(msg))[0]
        self.assertIsNone(ann["effective_at"])
        r = rc.ingest_announcement(self.conn, "upbit_notice", dict(ann, observed_at=t0 + H))
        self.assertEqual((len(r["events"]), r["rejected"], len(r["obs"])), (2, 0, 1))
        ev = self.q("SELECT quote, event_type, to_status FROM access_event WHERE asset_key='sym:OMG' ORDER BY quote")
        self.assertEqual([(e["quote"], e["event_type"], e["to_status"]) for e in ev],
                         [("BTC", "SPOT_DELISTED", "REMOVED"), ("KRW", "SPOT_DELISTED", "REMOVED")])
        tr = self.q("""SELECT DISTINCT t.obs_id FROM access_transition t JOIN access_state a USING(access_id)
                       WHERE a.asset_key='sym:OMG' AND t.to_status='REMOVED'""")
        self.assertEqual([x["obs_id"] for x in tr], r["obs"])
        self.assertEqual(self.q("SELECT * FROM rejected_transition"), [])

    def test_future_delisting_is_scheduled(self):
        ingest(self.conn, "upbit_market", upbit.fetch_markets(FakeHttp({upbit.MARKETS_URL: load("market_all.json")})),
               upbit.kst_ms(2026, 7, 15, 9, 0))
        anns = upbit.handle_ws_payload(json.dumps(self.msgs()[1]))
        announce(self.conn, "upbit_notice", anns, upbit.kst_ms(2026, 7, 15, 10, 1))
        ev = self.q("SELECT event_type, quote FROM access_event WHERE asset_key='sym:OMG' ORDER BY quote")
        self.assertEqual([(e["event_type"], e["quote"]) for e in ev], [("SPOT_DELISTED_SCHEDULED", "KRW")])
        self.assertEqual(self.q("SELECT * FROM rejected_transition"), [])     # no phantom BTC/USDT markets
        st = self.q("SELECT status, pending_removal_at FROM access_state WHERE asset_key='sym:OMG' AND quote='KRW'")[0]
        self.assertEqual((st["status"], st["pending_removal_at"]), ("LIVE", upbit.kst_ms(2026, 7, 29, 15, 0)))


class FakeCtx:
    def __init__(self, max_loops=50):
        self.stop_event = threading.Event()
        self.log = logging.getLogger("test.upbit.ctx")
        self.anns, self.hb, self.connected_calls, self.loops, self.max_loops = [], 0, 0, 0, max_loops

    def connected(self):
        self.connected_calls += 1

    def heartbeat(self):
        self.hb += 1

    def should_stop(self):
        self.loops += 1
        return self.stop_event.is_set() or self.loops > self.max_loops

    def emit_announcement(self, a):
        self.anns.append(a)


class FakeWs:
    def __init__(self, script):
        self.script = list(script)
        self.sent, self.pings, self.closed, self.connect_args = [], 0, False, None

    def send_text(self, t):
        self.sent.append(json.loads(t))

    def ping(self):
        self.pings += 1

    def recv(self, timeout=None):
        if not self.script:
            return None
        v = self.script.pop(0)
        if isinstance(v, BaseException):
            raise v
        return v

    def close(self):
        self.closed = True


class StreamTest(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        logging.getLogger("test.upbit.ctx").setLevel(logging.CRITICAL)

    def test_stream_emits_and_heartbeats(self):
        msgs = load("ws_messages.json")["messages"]
        ws = FakeWs([None, ("binary", json.dumps(msgs[0]).encode()), ("pong", b""),
                     ("text", json.dumps(msgs[4])), ("binary", json.dumps(msgs[2]).encode()),
                     upbit.WsClosed("close frame 1006")])
        ctx = FakeCtx()

        def connect(url, headers=None, timeout=None):
            ws.connect_args = (url, headers)
            return ws
        ticks = iter(range(0, 10000, 10))
        with self.assertRaises(upbit.WsClosed):
            upbit.run_notice_ws(ctx, connect=connect, credentials=("AK", "SK"), clock=lambda: next(ticks))
        self.assertEqual(ws.connect_args[0], "wss://api.upbit.com/websocket/v1/private")
        self.assertTrue(ws.connect_args[1]["Authorization"].startswith("Bearer ey"))
        self.assertEqual(ws.sent[0][1], {"type": "announcement", "include_body": True})
        self.assertEqual(ctx.connected_calls, 1)
        self.assertEqual([(a["action"], a.get("warning")) for a in ctx.anns], [("LISTING", None), ("SUSPEND", "DESIGNATED")])
        self.assertEqual(ctx.hb, 4)
        self.assertGreaterEqual(ws.pings, 1)          # fake clock advances 10s per call, PING_EVERY=25s
        self.assertTrue(ws.closed)

    def test_auth_error_raises_before_connected(self):
        ws = FakeWs([("text", json.dumps(load("ws_messages.json")["error"]))])
        ctx = FakeCtx()
        with self.assertRaises(upbit.UpbitWsError):
            upbit.run_notice_ws(ctx, connect=lambda *a, **k: ws, credentials=("AK", "SK"))
        self.assertEqual(ctx.connected_calls, 0)
        self.assertTrue(ws.closed)

    def test_stops_on_should_stop(self):
        ws = FakeWs([])
        ctx = FakeCtx(max_loops=3)
        upbit.run_notice_ws(ctx, connect=lambda *a, **k: ws, credentials=("AK", "SK"))
        self.assertEqual(ctx.connected_calls, 1)
        self.assertTrue(ws.closed)

    def _no_key_env(self, fallback="1"):
        old = {k: os.environ.pop(k, None) for k in (upbit.ENV_ACCESS_KEY, upbit.ENV_SECRET_KEY, upbit.ENV_REST_FALLBACK)}
        os.environ[upbit.ENV_REST_FALLBACK] = fallback
        upbit._no_key_warned = False

        def restore():
            os.environ.pop(upbit.ENV_REST_FALLBACK, None)
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v
            upbit._no_key_warned = False
        self.addCleanup(restore)

    def _patch(self, obj, name, value):
        old = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, old)

    def test_missing_credentials_fallback_disabled(self):
        self._no_key_env("0")
        ctx = FakeCtx()
        ctx.stop_event.set()                      # wait() returns immediately
        logging.getLogger("test.upbit.ctx").setLevel(logging.NOTSET)
        with self.assertLogs("test.upbit.ctx", "WARNING") as cm:
            for _ in range(2):
                with self.assertRaises(upbit.MissingCredentials):
                    upbit.run_notice_ws(ctx, connect=lambda *a, **k: self.fail("must not connect"))
        self.assertEqual(len(cm.records), 1)                                  # logged once, at WARNING
        self.assertEqual(cm.records[0].levelno, logging.WARNING)
        self.assertIn("needs an API key", cm.output[0])
        self.assertIn("fallback disabled", cm.output[0])

    def test_no_key_rest_polling_fallback(self):
        from datetime import datetime
        self._no_key_env("1")
        now_ms = rc.now_ms()
        iso = lambda ms: datetime.fromtimestamp(ms / 1000, upbit.KST).isoformat()  # noqa: E731
        old_row = {"id": 1, "title": "[거래] 신규 거래 지원 안내 - 옛날(OLD) (KRW 마켓)", "category": "거래",
                   "first_listed_at": iso(now_ms - 24 * H), "listed_at": iso(now_ms - 24 * H)}
        new_row = {"id": 2, "title": "[거래] 거래지원 종료 안내 (AXS)", "category": "거래",
                   "first_listed_at": iso(now_ms + 60_000), "listed_at": iso(now_ms + 60_000)}
        pages = [[old_row], [new_row, old_row], TimeoutError("timed out")]

        def notices(url, params):
            v = pages.pop(0)
            return v if isinstance(v, BaseException) else {"success": True, "data": {"total_pages": 1, "notices": v}}
        self._patch(upbit, "POLL_FALLBACK_SEC", 0)                           # poll on every fake-clock tick
        ctx = FakeCtx(max_loops=10_000)
        ctx.http = FakeHttp({upbit.NOTICE_LIST_URL: notices})
        ticks = iter(range(0, 10_000_000, 7))
        logging.getLogger("test.upbit.ctx").setLevel(logging.NOTSET)
        with self.assertLogs("test.upbit.ctx", "WARNING") as cm:
            with self.assertRaisesRegex(upbit.UpbitPollError, "REST announcement poll failed: TimeoutError"):
                upbit.run_notice_ws(ctx, connect=lambda *a, **k: self.fail("must not connect"),
                                    clock=lambda: next(ticks))
        self.assertIn("Falling back to REST polling", cm.output[0])
        self.assertEqual(ctx.connected_calls, 1)
        self.assertGreaterEqual(ctx.hb, 2)
        self.assertEqual([a["source_event_id"] for a in ctx.anns], ["upbit:notice:2"])   # old notice = backfill's job
        self.assertTrue(all(kw == {"timeout": upbit.REST_TIMEOUT_SEC, "tries": upbit.REST_TRIES,
                                   "deadline": upbit.REST_TIMEOUT_SEC} for kw in ctx.http.kwargs))

    def test_no_key_first_poll_failure_raises_before_connected(self):
        self._no_key_env("1")
        ctx = FakeCtx()
        ctx.http = FakeHttp({upbit.NOTICE_LIST_URL: TimeoutError("timed out")})
        with self.assertRaises(upbit.UpbitPollError):
            upbit.run_notice_ws(ctx, connect=lambda *a, **k: self.fail("must not connect"))
        self.assertEqual((ctx.connected_calls, ctx.anns), (0, []))


class WsClientTest(unittest.TestCase):
    """RFC 6455 framing over a local socketpair (no network)."""

    @staticmethod
    def server_frame(op, payload, fin=True):
        n = len(payload)
        head = bytes([(0x80 if fin else 0) | op])
        head += bytes([n]) if n < 126 else bytes([126]) + n.to_bytes(2, "big")
        return head + payload

    @staticmethod
    def read_client_frame(sock):
        def exact(n):
            b = b""
            while len(b) < n:
                b += sock.recv(n - len(b))
            return b
        b0, b1 = exact(2)
        n = b1 & 0x7F
        if n == 126:
            n = int.from_bytes(exact(2), "big")
        assert b1 & 0x80, "client frames must be masked"
        mask = exact(4)
        data = bytes(c ^ mask[i % 4] for i, c in enumerate(exact(n)))
        return b0 & 0x0F, data

    def test_handshake_frames_ping_close(self):
        cli, srv = socket.socketpair()
        got = {}

        def server():
            req = b""
            while b"\r\n\r\n" not in req:
                req += srv.recv(4096)
            lines = req.decode().split("\r\n")
            got["request_line"] = lines[0]
            hdr = {ln.split(":", 1)[0].lower(): ln.split(":", 1)[1].strip() for ln in lines[1:] if ":" in ln}
            got["auth"] = hdr.get("authorization")
            acc = base64.b64encode(hashlib.sha1((hdr["sec-websocket-key"] + upbit.WS_GUID).encode()).digest()).decode()
            srv.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                         f"Sec-WebSocket-Accept: {acc}\r\n\r\n").encode()
                        + self.server_frame(0x1, "안녕".encode()))       # first frame rides with the handshake
            got["sub"] = self.read_client_frame(srv)
            big = json.dumps({"type": "announcement", "title": "x" * 300}).encode()
            srv.sendall(self.server_frame(0x2, big[:100], fin=False) + self.server_frame(0x0, big[100:200], fin=False))
            srv.sendall(self.server_frame(0x0, big[200:]))
            srv.sendall(self.server_frame(0x9, b"hb"))
            got["pong"] = self.read_client_frame(srv)
            srv.sendall(self.server_frame(0x8, (1000).to_bytes(2, "big") + b"bye"))
            got["close"] = self.read_client_frame(srv)

        t = threading.Thread(target=server, daemon=True)
        t.start()
        ws = upbit.WsClient.connect("wss://api.upbit.com/websocket/v1/private", headers={"Authorization": "Bearer T"},
                                    timeout=5, sock=cli)
        self.assertEqual(ws.recv(timeout=2), ("text", "안녕".encode()))
        ws.send_text('[{"ticket":"t"}]')
        kind, data = ws.recv(timeout=2)
        self.assertEqual(kind, "binary")
        self.assertEqual(len(json.loads(data)["title"]), 300)
        self.assertEqual(ws.recv(timeout=2), ("ping", b"hb"))
        with self.assertRaises(upbit.WsClosed):
            ws.recv(timeout=2)
        t.join(5)
        self.assertEqual(got["request_line"], "GET /websocket/v1/private HTTP/1.1")
        self.assertEqual(got["auth"], "Bearer T")
        self.assertEqual(got["sub"], (0x1, b'[{"ticket":"t"}]'))
        self.assertEqual(got["pong"], (0xA, b"hb"))
        self.assertEqual(got["close"][0], 0x8)
        srv.close()
        cli.close()

    def test_recv_timeout_returns_none_and_bad_accept_fails(self):
        cli, srv = socket.socketpair()
        ws = upbit.WsClient(cli)
        self.assertIsNone(ws.recv(timeout=0.05))
        srv.sendall(b"\x81\x05hel")                  # partial frame: still None, bytes kept
        self.assertIsNone(ws.recv(timeout=0.05))
        srv.sendall(b"lo")
        self.assertEqual(ws.recv(timeout=1), ("text", b"hello"))
        cli.close()
        srv.close()

        cli, srv = socket.socketpair()

        def server():
            srv.recv(4096)
            srv.sendall(b"HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: nope\r\n\r\n")
        t = threading.Thread(target=server, daemon=True)
        t.start()
        with self.assertRaises(upbit.WsClosed):
            upbit.WsClient.connect("wss://api.upbit.com/websocket/v1/private", sock=cli, timeout=2)
        t.join(2)
        cli.close()
        cli, srv2 = socket.socketpair()

        def server401():
            srv2.recv(4096)
            srv2.sendall(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n")
        t = threading.Thread(target=server401, daemon=True)
        t.start()
        with self.assertRaisesRegex(upbit.WsClosed, "401"):
            upbit.WsClient.connect("wss://api.upbit.com/websocket/v1/private", sock=cli, timeout=2)
        t.join(2)
        for s in (srv, srv2, cli):
            s.close()


class BackfillTest(Base):
    def http(self):
        rest = load("announcements_rest.json")

        def notices(url, params):
            return rest["page1"] if params.get("page") == 1 else rest["page2"]
        return FakeHttp({upbit.NOTICE_LIST_URL: notices,
                         upbit.NOTICE_DETAIL_URL.format(id=562593650): rest["detail_562593650"]})

    def test_gap_backfill(self):
        http = self.http()
        since, until = upbit.kst_ms(2026, 7, 20, 0, 0), upbit.kst_ms(2026, 7, 22, 0, 0)
        anns = upbit.backfill_notices(http, since, until)
        self.assertEqual([(a["action"], a["source_event_id"]) for a in anns],
                         [("DELISTING", "upbit:notice:562593650"), ("LISTING", "upbit:notice:562593700")])
        self.assertEqual(anns[0]["effective_at"], upbit.kst_ms(2026, 8, 4, 15, 0))   # from the detail body
        self.assertEqual(anns[1]["targets"], [{"symbol": "ENA", "access_kind": "SPOT", "quote": "KRW"}])
        pages = [c[1].get("page") for c in http.calls if c[0] == upbit.NOTICE_LIST_URL]
        self.assertEqual(pages, [1, 2])                      # stopped after the page that went older than the gap
        self.assertEqual(http.calls[0][1], {"os": "web", "page": 1, "per_page": 20, "category": "all"})

    def test_backfill_ids_match_ws_ids(self):
        rest = load("announcements_rest.json")["page1"]["data"]["notices"][0]
        ws = {"type": "announcement", "event_type": "CREATED", "uuid": str(rest["id"]), "title": rest["title"],
              "category": "trade", "first_listed_at": rest["first_listed_at"], "listed_at": rest["listed_at"]}
        self.assertEqual(upbit.parse_notice(rest)["source_event_id"], upbit.parse_notice(ws)["source_event_id"])
        self.assertEqual(upbit.parse_notice(rest)["url"], upbit.parse_notice(ws)["url"])
        self.assertEqual(upbit.parse_notice(rest)["url"], f"https://upbit.com/service_center/notice?id={rest['id']}")

    def test_url_fallback_without_id(self):
        n = {"title": "[거래] 거래지원 종료 안내 (OMG)", "category": "trade", "first_listed_at": "2026-07-15T10:00:00+09:00",
             "url": "https://upbit.com/service_center/notice?view=share"}
        self.assertEqual(upbit.parse_notice(n)["url"], "https://upbit.com/service_center/notice?view=share")
        self.assertIsNone(upbit.notice_page_url({"title": "x", "url": "/relative"}))

    def test_detail_failure_falls_back_to_title(self):
        rest = load("announcements_rest.json")
        http = FakeHttp({upbit.NOTICE_LIST_URL: rest["page1"],
                         upbit.NOTICE_DETAIL_URL.format(id=562593650): RuntimeError("HTTP 500")})
        anns = upbit.backfill_notices(http, upbit.kst_ms(2026, 7, 21, 0, 0), upbit.kst_ms(2026, 7, 22, 0, 0))
        self.assertEqual(anns[0]["action"], "DELISTING")
        self.assertIsNone(anns[0]["effective_at"])

    def test_bad_shape_raises(self):
        with self.assertRaisesRegex(upbit.BackfillError, "BadResponse"):
            upbit.backfill_notices(FakeHttp({upbit.NOTICE_LIST_URL: {"success": False}}), 0, T0)

    def test_requests_use_short_timeout_without_retries(self):
        http = self.http()
        upbit.backfill_notices(http, upbit.kst_ms(2026, 7, 20, 0, 0), upbit.kst_ms(2026, 7, 22, 0, 0))
        self.assertTrue(http.kwargs)
        for kw in http.kwargs:
            self.assertEqual(kw["tries"], upbit.REST_TRIES)
            self.assertLessEqual(kw["timeout"], upbit.REST_TIMEOUT_SEC)
            self.assertEqual(kw["deadline"], kw["timeout"])                   # list pages AND detail requests
        self.assertIn(upbit.NOTICE_DETAIL_URL.split("{")[0], " ".join(c[0] for c in http.calls))

    def test_deadline_follows_remaining_budget(self):
        ticks = iter([0, 25] + [25] * 50)                                     # 5s of the 30s budget left
        http = self.http()
        upbit.backfill_notices(http, upbit.kst_ms(2026, 7, 20, 0, 0), upbit.kst_ms(2026, 7, 22, 0, 0),
                               clock=lambda: next(ticks))
        self.assertEqual((http.kwargs[0]["timeout"], http.kwargs[0]["deadline"]), (5, 5))

    def test_deadline_exceeded_is_backfill_error(self):
        import access_http
        http = FakeHttp({upbit.NOTICE_LIST_URL: access_http.DeadlineExceeded(10.0, got=1024)})
        with self.assertLogs("access_radar.adapters.upbit", "WARNING"):
            with self.assertRaisesRegex(upbit.BackfillError, "page 1 failed .*DeadlineExceeded"):
                upbit.backfill_notices(http, T0 - H, T0)
        self.assertEqual(http.kwargs[0]["deadline"], upbit.REST_TIMEOUT_SEC)
        with self.assertRaisesRegex(upbit.UpbitPollError, "REST announcement poll failed: DeadlineExceeded"):
            upbit.poll_latest(http)
        self.assertEqual(http.kwargs[-1]["deadline"], upbit.REST_TIMEOUT_SEC)

    def test_timeout_raises_never_empty(self):
        http = FakeHttp({upbit.NOTICE_LIST_URL: TimeoutError("The read operation timed out")})
        with self.assertLogs("access_radar.adapters.upbit", "WARNING") as cm:
            with self.assertRaisesRegex(upbit.BackfillError, "page 1 failed .*TimeoutError"):
                upbit.backfill_notices(http, T0 - H, T0)
        self.assertIn("timed out", "\n".join(cm.output))
        self.assertEqual(len(http.calls), 1)                                  # no retry loop inside the backfill
        rest = load("announcements_rest.json")

        def page(url, params):                                                # page 1 ok, page 2 times out
            return rest["page1"] if params.get("page") == 1 else TimeoutError("timed out")
        with self.assertRaisesRegex(upbit.BackfillError, "page 2"):
            upbit.backfill_notices(FakeHttp({upbit.NOTICE_LIST_URL: page}), upbit.kst_ms(2026, 7, 1, 0, 0),
                                   upbit.kst_ms(2026, 7, 22, 0, 0))

    def test_budget_exhausted_raises(self):
        ticks = iter([0, 0, 31, 31, 31])                                      # second page would start after 31s
        with self.assertRaisesRegex(upbit.BackfillError, "budget"):
            upbit.backfill_notices(self.http(), upbit.kst_ms(2026, 7, 1, 0, 0), upbit.kst_ms(2026, 7, 22, 0, 0),
                                   clock=lambda: next(ticks))


class RunnerIntegrationTest(unittest.TestCase):
    """The real access_sched.Runner loads this module and writes through the single writer."""

    def test_runner_once(self):
        import access_db
        import access_sched as S
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        tmp = tempfile.mkdtemp(prefix="ar_upbit_")
        db = os.path.join(tmp, "a.sqlite")
        w = access_db.Writer(db).start()
        try:
            cat = [S.Entry("upbit_market", 30, "adapters.upbit"), S.Entry("upbit_notice", 0, "adapters.upbit")]
            r = S.Runner(w, FakeHttp({upbit.MARKETS_URL: load("market_all.json")}), catalog=cat, discover_package=None)
            specs = {s.source_id: s for s in r.prepare()}
            self.assertEqual(specs["upbit_notice"].kind, "stream")
            self.assertEqual(specs["upbit_notice"].heartbeat_sec, upbit.HEARTBEAT_SEC)
            self.assertIs(specs["upbit_notice"].backfill, upbit.backfill_notices)
            out = {o["source_id"]: o for o in r.run_once()}
            self.assertTrue(out["upbit_market"]["ok"], out)
            # streams are skipped in once mode (reported inline or via Runner.once_skipped, depending on version)
            skipped = [x["source_id"] for x in getattr(r, "once_skipped", [])]
            self.assertTrue(out.get("upbit_notice", {}).get("skipped") == "stream" or skipped == ["upbit_notice"],
                            (out, skipped))
            self.assertNotIn("ok", out.get("upbit_notice", {}))
            conn = access_db.connect(db)
            try:
                src = {row["source_id"]: dict(row) for row in conn.execute("SELECT * FROM source")}
                self.assertEqual(src["upbit_notice"]["kind"], "ANNOUNCEMENT")
                self.assertEqual(src["upbit_market"]["tier"], "OFFICIAL_STRUCTURED")
                n = conn.execute("SELECT COUNT(*) FROM source_scope_baseline WHERE source_id='upbit_market'").fetchone()[0]
                self.assertEqual(n, 3)
            finally:
                conn.close()
        finally:
            w.stop()


    def test_runner_stream_backfills_gap_then_streams(self):
        import time as _time
        from datetime import datetime
        import access_db
        import access_sched as S
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        now_iso = datetime.fromtimestamp(_time.time(), upbit.KST).isoformat(timespec="seconds")
        rest = {"success": True, "data": {"total_pages": 1, "notices": [
            {"id": 900001, "title": "[거래] 신규 거래 지원 안내 - 갭코인(GAP) (KRW 마켓)", "category": "거래",
             "first_listed_at": now_iso, "listed_at": now_iso}]}}
        live = dict(load("ws_messages.json")["messages"][2], first_listed_at=now_iso, listed_at=now_iso)
        scripts = [[None, ("binary", json.dumps(live).encode()), upbit.WsClosed("bye")]]
        orig_connect, orig_creds = upbit.WsClient.connect, upbit.read_credentials
        upbit.WsClient.connect = classmethod(lambda cls, *a, **k: FakeWs(scripts.pop(0) if scripts else []))
        upbit.read_credentials = lambda env=None: ("AK", "SK")
        db = os.path.join(tempfile.mkdtemp(prefix="ar_upbit_stream_"), "a.sqlite")
        w = access_db.Writer(db).start()
        r = S.Runner(w, FakeHttp({upbit.NOTICE_LIST_URL: rest}), catalog=[S.Entry("upbit_notice", 0, "adapters.upbit")],
                     discover_package=None, stream_backoff=(0.05, 0.1))
        try:
            r.start()
            conn = access_db.connect(db)
            try:
                deadline = _time.time() + 5
                seen = set()
                while _time.time() < deadline and len(seen) < 2:
                    seen = {row[0] for row in conn.execute(
                        "SELECT source_event_id FROM source_observation WHERE source_id='upbit_notice'")}
                    _time.sleep(0.05)
                self.assertEqual(seen, {"upbit:notice:900001", "upbit:notice:562593300"})   # backfill + live
                gaps = conn.execute("SELECT backfilled FROM source_disconnect WHERE source_id='upbit_notice' "
                                    "AND ended_at IS NOT NULL").fetchall()
                self.assertTrue(gaps and gaps[0][0] == 1)
            finally:
                conn.close()
        finally:
            r.stop(timeout=3)
            w.stop()
            upbit.WsClient.connect, upbit.read_credentials = orig_connect, orig_creds

    def _runner(self, http, prefix):
        import access_db
        import access_sched as S
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        db = os.path.join(tempfile.mkdtemp(prefix=prefix), "a.sqlite")
        w = access_db.Writer(db).start()
        r = S.Runner(w, http, catalog=[S.Entry("upbit_notice", 0, "adapters.upbit")],
                     discover_package=None, stream_backoff=(0.05, 0.1))
        self.addCleanup(w.stop)
        self.addCleanup(r.stop, 3)
        return r, db

    @staticmethod
    def _wait(pred, timeout=5):
        import time as _time
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            v = pred()
            if v:
                return v
            _time.sleep(0.03)
        return pred()

    def test_runner_backfill_timeout_is_visible_and_changes_nothing(self):
        """With a key: WS connects, the REST backfill times out -> runner WARNING + source_run/source_health
        last_error 'backfill failed for gap ...', gap stays backfilled=0 (retried by the runner later),
        no observations/events/rejections, the stream keeps running."""
        import access_db
        orig_connect, orig_creds = upbit.WsClient.connect, upbit.read_credentials
        self.addCleanup(setattr, upbit, "read_credentials", orig_creds)
        self.addCleanup(setattr, upbit.WsClient, "connect", orig_connect)
        upbit.WsClient.connect = classmethod(lambda cls, *a, **k: FakeWs([None] * 200))
        upbit.read_credentials = lambda env=None: ("AK", "SK")
        http = FakeHttp({upbit.NOTICE_LIST_URL: TimeoutError("The read operation timed out")})
        r, db = self._runner(http, "ar_upbit_bf_timeout_")
        with self.assertLogs("access_radar.sched", "WARNING") as cm:
            r.start()
            self.assertTrue(self._wait(lambda: http.calls))
            conn = access_db.connect(db)
            self.addCleanup(conn.close)
            err = self._wait(lambda: conn.execute(
                "SELECT r.last_error, h.last_error FROM source_run r JOIN source_health h USING(source_id) "
                "WHERE source_id='upbit_notice' AND h.scope='' AND r.last_error LIKE 'backfill failed%'").fetchone())
        self.assertTrue(err)
        self.assertIn("TimeoutError", err[0])
        self.assertEqual(err[0][:200], err[1][:200])
        self.assertTrue(any("upbit_notice backfill failed" in m and "TimeoutError" in m for m in cm.output), cm.output)
        self.assertEqual(http.kwargs[0], {"timeout": upbit.REST_TIMEOUT_SEC, "tries": upbit.REST_TRIES,
                                          "deadline": upbit.REST_TIMEOUT_SEC})
        try:
            gaps = conn.execute("SELECT backfilled FROM source_disconnect WHERE source_id='upbit_notice' "
                                "AND ended_at IS NOT NULL").fetchall()
            self.assertEqual([g[0] for g in gaps], [0])                        # gap NOT marked as backfilled
            for t in ("source_observation", "access_event", "rejected_transition", "access_state"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], 0, t)
            self.assertEqual(conn.execute("SELECT connected FROM source_run WHERE source_id='upbit_notice'")
                             .fetchone()[0], 1)                                # no crash: stream still up
        finally:
            conn.close()

    def test_runner_no_key_polls_rest_and_surfaces_poll_timeout(self):
        """No key: REST polling fallback delivers notices; a timed-out poll raises -> source_run.last_error,
        source_health DOWN, source_disconnect.reason; next successful poll reconnects and backfills the gap."""
        import time as _time
        from datetime import datetime
        import access_db
        old = {k: os.environ.pop(k, None) for k in (upbit.ENV_ACCESS_KEY, upbit.ENV_SECRET_KEY, upbit.ENV_REST_FALLBACK)}
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) for k, v in old.items() if v is not None])
        orig_poll, orig_creds = upbit.POLL_FALLBACK_SEC, upbit.read_credentials
        self.addCleanup(setattr, upbit, "POLL_FALLBACK_SEC", orig_poll)
        self.addCleanup(setattr, upbit, "read_credentials", orig_creds)
        upbit.POLL_FALLBACK_SEC = 0.05
        upbit.read_credentials = lambda env=None: None
        upbit._no_key_warned = False
        self.addCleanup(setattr, upbit, "_no_key_warned", False)
        now_iso = datetime.fromtimestamp(_time.time() + 30, upbit.KST).isoformat(timespec="seconds")
        ok = {"success": True, "data": {"total_pages": 1, "notices": [
            {"id": 700001, "title": "[거래] 신규 거래 지원 안내 - 폴코인(POLL) (KRW 마켓)", "category": "거래",
             "first_listed_at": now_iso, "listed_at": now_iso}]}}
        state = {"fail": False, "n": 0}

        def notices(url, params):
            state["n"] += 1
            return TimeoutError("The read operation timed out") if state["fail"] else ok
        http = FakeHttp({upbit.NOTICE_LIST_URL: notices})
        r, db = self._runner(http, "ar_upbit_nokey_")
        r.start()
        conn = access_db.connect(db)
        self.addCleanup(conn.close)
        q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
        self.assertTrue(self._wait(lambda: q("SELECT 1 FROM source_observation WHERE "
                                             "source_event_id='upbit:notice:700001'")))
        self.assertEqual(q("SELECT connected FROM source_run WHERE source_id='upbit_notice'")[0][0], 1)
        state["fail"] = True
        err = self._wait(lambda: [x for x in q("SELECT last_error FROM source_run WHERE source_id='upbit_notice' "
                                                 "AND connected=0") if "REST announcement poll failed" in x[0]])
        self.assertTrue(err, q("SELECT * FROM source_run"))
        self.assertIn("TimeoutError", err[0][0])
        health = q("SELECT status, last_error FROM source_health WHERE source_id='upbit_notice' AND scope=''")
        self.assertEqual(health[0][0], "DOWN")
        self.assertIn("REST announcement poll failed", health[0][1])
        self.assertTrue(q("SELECT 1 FROM source_disconnect WHERE source_id='upbit_notice' "
                          "AND reason LIKE 'UpbitPollError: REST announcement poll failed%'"))
        n_obs = q("SELECT COUNT(*) FROM source_observation")[0][0]
        self.assertEqual(n_obs, 1)                                             # timeouts added nothing
        self.assertEqual(q("SELECT COUNT(*) FROM rejected_transition")[0][0], 0)
        state["fail"] = False                                                  # recovery: reconnect + backfill
        self.assertTrue(self._wait(lambda: q("SELECT 1 FROM source_run WHERE source_id='upbit_notice' "
                                             "AND connected=1")))
        self.assertTrue(self._wait(lambda: q("SELECT 1 FROM source_disconnect WHERE source_id='upbit_notice' "
                                             "AND reason LIKE 'UpbitPollError%' AND backfilled=1")))
        self.assertEqual(q("SELECT COUNT(*) FROM source_observation")[0][0], 1)  # idempotent re-polls
        self.assertTrue(self._wait(lambda: q("SELECT 1 FROM source_run WHERE source_id='upbit_notice' "
                                             "AND last_error=''")))             # errors cleared after recovery


if __name__ == "__main__":
    unittest.main()
