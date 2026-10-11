"""NewListings adapter tests: classification/parse/idempotency + FakeWs run() end-to-end, no network."""
import json
import logging
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from adapters import newlistings as nl  # noqa: E402
from adapters import upbit  # noqa: E402

H = 3600 * 1000
T0 = 1_790_000_000_000


def feed_event(**over):
    msg = {"id": 1, "time": T0,
           "announcement": "$PIEVERSE listed on Upbit spot (KRW)",
           "original_title": "파이버스(PIEVERSE) 신규 거래지원 안내 (KRW, BTC, USDT 마켓)",
           "url": "https://example.com/notice", "exchange": "upbit", "type": "spot",
           "detections": [{"ticker": "PIEVERSE"}]}
    msg.update(over)
    return msg


class ParseTest(unittest.TestCase):
    def test_classify_action(self):
        self.assertEqual(nl.classify_action("$ABC listed on Bybit spot"), nl.LISTING)
        self.assertEqual(nl.classify_action("$OMG delisted from Upbit"), nl.DELISTING)
        self.assertEqual(nl.classify_action("$OMG was delisted"), nl.DELISTING)     # delist beats list
        self.assertEqual(nl.classify_action("피엔버스(ABC) 신규 거래지원 안내"), nl.LISTING)
        self.assertEqual(nl.classify_action("ABC 거래지원 종료 안내"), nl.DELISTING)
        self.assertEqual(nl.classify_action("ABC 상장폐지 안내"), nl.DELISTING)
        self.assertEqual(nl.classify_action("ABC deregistered from the exchange"), nl.DELISTING)
        self.assertEqual(nl.classify_action("ABC suspended deposits"), None)
        self.assertEqual(nl.classify_action(""), None)
        self.assertEqual(nl.classify_action(None), None)

    def test_extract_quotes(self):
        self.assertEqual(nl.extract_quotes("$X listed on Upbit spot (KRW)",
                                           "제목 (KRW, BTC, USDT 마켓)"), ["KRW", "BTC", "USDT"])
        self.assertEqual(nl.extract_quotes("$X listed (USDT)", ""), ["USDT"])
        self.assertEqual(nl.extract_quotes("$X listed (KRW) (USDT)", ""), ["KRW", "USDT"])
        self.assertEqual(nl.extract_quotes("$PIEVERSE listed", "파이버스(PIEVERSE) 신규 상장"), [""])
        self.assertEqual(nl.extract_quotes("", ""), [""])

    def test_parse_message_targets_and_relay(self):
        a = nl.parse_message(feed_event())
        self.assertEqual(a["action"], nl.LISTING)
        self.assertEqual(a["platform_id"], "upbit")
        self.assertEqual(a["origin_group"], "upbit_notice")
        self.assertEqual(a["announced_at"], T0)
        self.assertEqual([(t["symbol"], t["access_kind"], t["quote"]) for t in a["targets"]],
                         [("PIEVERSE", "SPOT", "KRW"), ("PIEVERSE", "SPOT", "BTC"), ("PIEVERSE", "SPOT", "USDT")])
        self.assertEqual(a["url"], "https://example.com/notice")
        self.assertEqual(a["raw"]["type"], "spot")

    def test_parse_message_kind_mapping(self):
        a = nl.parse_message(feed_event(announcement="$XYZ listed on Bybit futures (USDT)",
                                        original_title="XYZ 선물 상장", exchange="bybit", type="futures"))
        self.assertEqual([t["access_kind"] for t in a["targets"]], ["PERP"])
        self.assertEqual(a["origin_group"], "")                                   # not a mirrored exchange
        a = nl.parse_message(feed_event(type="pre-market"))
        self.assertEqual([t["access_kind"] for t in a["targets"]], ["ROADMAP"] * 3)

    def test_parse_message_delisting_id(self):
        a = nl.parse_message(feed_event(announcement="$OMG delisted from Upbit spot (KRW)",
                                        original_title="오염지 디리스팅 안내",
                                        detections=[{"ticker": "OMG"}]))
        self.assertEqual(a["action"], nl.DELISTING)
        self.assertEqual(a["source_event_id"], "nl:upbit:OMG:SPOT:DELISTING:KRW")

    def test_event_id_stable_across_delivery(self):
        a1 = nl.parse_message(feed_event(id=101, time=T0))
        a2 = nl.parse_message(feed_event(id=999, time=T0 + 7 * H))                # id/time not part of the id
        self.assertEqual(a1["source_event_id"], a2["source_event_id"])
        self.assertTrue(a1["source_event_id"].startswith("nl:upbit:SPOT:LISTING:"))   # multi-quote hash variant

    def test_event_id_doc_format_single_quote(self):
        a = nl.parse_message(feed_event(announcement="$ABC listed on Bithumb spot (KRW)",
                                        original_title="ABC 신규 거래지원 안내", exchange="bithumb",
                                        detections=[{"ticker": "ABC"}]))
        self.assertEqual(a["source_event_id"], "nl:bithumb:ABC:SPOT:LISTING:KRW")

    def test_parse_message_skips_unrecognized(self):
        self.assertIsNone(nl.parse_message(feed_event(type="airdrop")))           # unknown access kind
        self.assertIsNone(nl.parse_message(feed_event(announcement="$X wins award")))  # no keyword
        self.assertIsNone(nl.parse_message(feed_event(exchange="")))              # no exchange
        self.assertIsNone(nl.parse_message(feed_event(detections=[], announcement="$X wins award",
                                                      original_title="수상 안내")))   # no symbol anywhere
        self.assertIsNone(nl.parse_message("not a dict"))
        self.assertIsNone(nl.parse_message(None))

    def test_handle_ws_payload(self):
        self.assertEqual(nl.handle_ws_payload(json.dumps({"type": "success"})), [])
        self.assertEqual(nl.handle_ws_payload(json.dumps({"type": "pong"})), [])
        self.assertEqual(nl.handle_ws_payload(b"garbage {"), [])
        anns = nl.handle_ws_payload(json.dumps(feed_event()).encode())            # binary frame
        self.assertEqual(len(anns), 1)
        self.assertEqual(anns[0]["source_event_id"],
                         nl.parse_message(feed_event())["source_event_id"])
        with self.assertRaisesRegex(nl.NewListingsError, "invalid api key"):
            nl.handle_ws_payload(json.dumps({"type": "error", "message": "invalid api key"}))


class FakeCtx:
    def __init__(self, conn, max_loops=50):
        self.stop_event = threading.Event()
        self.log = logging.getLogger("test.nl.ctx")
        self.conn = conn
        self.anns, self.results = [], []
        self.hb, self.connected_calls, self.loops, self.max_loops = 0, 0, 0, max_loops

    def connected(self):
        self.connected_calls += 1

    def heartbeat(self):
        self.hb += 1

    def should_stop(self):
        self.loops += 1
        return self.stop_event.is_set() or self.loops > self.max_loops

    def emit_announcement(self, a):
        self.anns.append(a)
        self.results.append(rc.ingest_announcement(self.conn, "newlistings", dict(a, observed_at=T0 + H)))


class FakeWs:
    def __init__(self, script):
        self.script = list(script)
        self.closed, self.connect_args = False, None

    @staticmethod
    def connect(url, headers=None, timeout=None, sock=None):
        ws = _CURRENT_WS[0]
        ws.connect_args = (url, headers, timeout)
        return ws

    def recv(self, timeout=None):
        if not self.script:
            return None
        v = self.script.pop(0)
        if isinstance(v, BaseException):
            raise v
        return v

    def close(self):
        self.closed = True


_CURRENT_WS = [None]


class RunTest(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        logging.getLogger("test.nl.ctx").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        rc.register_platform(self.conn, "upbit", "Upbit", at=T0)
        rc.register_platform(self.conn, "bybit", "Bybit", at=T0)
        rc.register_source(self.conn, "newlistings", name=nl.SOURCE["name"], kind="ANNOUNCEMENT",
                           tier="THIRD_PARTY", is_relay=True, at=T0)
        self.addCleanup(setattr, nl, "_no_key_warned", False)

    def tearDown(self):
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def test_run_emits_and_ingests(self):
        ws = FakeWs([("text", json.dumps({"type": "success"})),                    # handshake ack (early frame)
                     ("text", json.dumps(feed_event())),
                     ("binary", json.dumps(feed_event(id=2, time=T0 + H,
                                                      announcement="$XYZ listed on Bybit futures (USDT)",
                                                      original_title="XYZ 선물 상장",
                                                      exchange="bybit", type="futures",
                                                      detections=[{"ticker": "XYZ"}])).encode()),
                     ("ping", b""),
                     upbit.WsClosed("close frame 1006")])
        _CURRENT_WS[0] = ws
        ctx = FakeCtx(self.conn)
        with self.assertRaises(upbit.WsClosed):
            nl.run(ctx, connect=FakeWs.connect, key="test-key")
        self.assertEqual(ws.connect_args, (nl.WS_URL, {"Authorization": "Bearer test-key"}, nl.CONNECT_TIMEOUT))
        self.assertEqual(ctx.connected_calls, 1)
        self.assertEqual(ctx.hb, 3)                                               # text + binary + ping
        self.assertTrue(ws.closed)
        self.assertEqual([a["platform_id"] for a in ctx.anns], ["upbit", "bybit"])
        ev = self.q("SELECT asset_key, event_type, quote FROM access_event")
        self.assertEqual(sorted((e["asset_key"], e["event_type"], e["quote"]) for e in ev),
                         sorted([("sym:PIEVERSE", "SPOT_ANNOUNCED", "KRW"),
                                 ("sym:PIEVERSE", "SPOT_ANNOUNCED", "BTC"),
                                 ("sym:PIEVERSE", "SPOT_ANNOUNCED", "USDT"),
                                 ("sym:XYZ", "PERP_ANNOUNCED", "USDT")]))
        st = self.q("SELECT status FROM access_state WHERE asset_key='sym:PIEVERSE' AND quote='KRW'")
        self.assertEqual(st[0]["status"], "ANNOUNCED")                            # relay: provisional, not LIVE

    def test_run_ingest_is_idempotent_on_redelivery(self):
        ws = FakeWs([("text", json.dumps({"type": "success"})),
                     ("text", json.dumps(feed_event(id=7))),
                     ("text", json.dumps(feed_event(id=88))),                     # same content, new vendor id
                     upbit.WsClosed("close frame 1006")])
        _CURRENT_WS[0] = ws
        ctx = FakeCtx(self.conn)
        with self.assertRaises(upbit.WsClosed):
            nl.run(ctx, connect=FakeWs.connect, key="test-key")
        self.assertEqual(len(ctx.results), 2)
        self.assertFalse(ctx.results[0]["duplicate"])
        self.assertTrue(ctx.results[1]["duplicate"])                              # redelivery: idempotent
        self.assertEqual(len(self.q("SELECT * FROM access_event")), 3)
        self.assertEqual(len(ctx.results[0]["events"]), 3)
        self.assertEqual(ctx.results[1]["events"], [])

    def test_error_frame_is_auth_failure(self):
        ws = FakeWs([("text", json.dumps({"type": "error", "message": "HTTP 401 invalid api key"}))])
        _CURRENT_WS[0] = ws
        ctx = FakeCtx(self.conn)
        ctx.stop_event.set()                                                      # skip the 120s backoff wait
        logging.getLogger("test.nl.ctx").setLevel(logging.NOTSET)
        with self.assertLogs("test.nl.ctx", "WARNING") as cm:
            with self.assertRaisesRegex(nl.NewListingsError, "invalid api key"):
                nl.run(ctx, connect=FakeWs.connect, key="bad-key")
        self.assertEqual(ctx.connected_calls, 0)
        self.assertIn("auth rejected", cm.output[0])
        self.assertEqual(ctx.anns, [])

    def test_connect_auth_rejection(self):
        ctx = FakeCtx(self.conn)
        ctx.stop_event.set()                                                      # skip AUTH_FAIL_WAIT

        def connect(url, headers=None, timeout=None, sock=None):
            raise upbit.WsClosed("handshake rejected: HTTP/1.1 401 Unauthorized")

        logging.getLogger("test.nl.ctx").setLevel(logging.NOTSET)
        with self.assertLogs("test.nl.ctx", "WARNING") as cm:
            with self.assertRaises(upbit.WsClosed):
                nl.run(ctx, connect=connect, key="bad-key")
        self.assertIn("auth rejected", cm.output[0])

    def test_non_auth_disconnect_raises_without_backoff_log(self):
        ws = FakeWs([("text", json.dumps({"type": "success"})), upbit.WsClosed("close frame 1006")])
        _CURRENT_WS[0] = ws
        ctx = FakeCtx(self.conn)
        with self.assertRaises(upbit.WsClosed):
            nl.run(ctx, connect=FakeWs.connect, key="test-key")
        self.assertEqual(ctx.connected_calls, 1)

    def _no_key(self):
        old = os.environ.pop(nl.ENV_KEY, None)

        def restore():
            if old is not None:
                os.environ[nl.ENV_KEY] = old
        self.addCleanup(restore)

    def test_missing_key_never_connects(self):
        self._no_key()
        ctx = FakeCtx(self.conn)
        ctx.stop_event.set()                                                      # wait() returns immediately
        logging.getLogger("test.nl.ctx").setLevel(logging.NOTSET)
        with self.assertLogs("test.nl.ctx", "WARNING") as cm:
            with self.assertRaisesRegex(nl.NewListingsError, "t.me/NLF_websocket_bot"):
                nl.run(ctx, connect=lambda *a, **k: self.fail("must not connect"))
        self.assertIn(nl.ENV_KEY, cm.output[0])

    def test_missing_key_warning_logged_once(self):
        self._no_key()
        ctx = FakeCtx(self.conn)
        ctx.stop_event.set()
        logging.getLogger("test.nl.ctx").setLevel(logging.NOTSET)
        with self.assertLogs("test.nl.ctx", "WARNING") as cm:
            for _ in range(2):
                with self.assertRaises(nl.NewListingsError):
                    nl.run(ctx, connect=lambda *a, **k: self.fail("must not connect"))
        self.assertEqual(len(cm.records), 1)

    def test_source_registration_shape(self):
        src = self.q("SELECT kind, tier, is_relay FROM source WHERE source_id='newlistings'")[0]
        self.assertEqual((src["kind"], src["tier"], src["is_relay"]), ("ANNOUNCEMENT", "THIRD_PARTY", 1))


if __name__ == "__main__":
    unittest.main()
