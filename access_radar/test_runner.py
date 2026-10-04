"""Runner tests: scheduling, single writer, skip-missing-adapter, streams, lock, feed/status, maintenance jobs
(incl. real resolve.py with fake HTTP), HTTP client.

Fake adapters are generated into a temp package per test; no external network (the HTTP client tests use
a local 127.0.0.1 server).
"""
import contextlib
import http.client
import http.server
import io
import itertools
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import radar_core as rc        # noqa: E402
import access_db               # noqa: E402
import access_http             # noqa: E402
import access_run              # noqa: E402
import access_sched as S       # noqa: E402

PLATFORM = '{"platform_id": "fakex", "name": "FakeX", "platform_type": "CEX", "country": "KR"}'

FAKE_MODULES = {
    "__init__": "",
    "snap": f'''
        import threading, time
        SOURCE_ID = "fake_snap"
        KIND = "snapshot"
        PLATFORMS = [{PLATFORM}]
        SOURCE = {{"tier": "OFFICIAL_STRUCTURED", "origin_platform_id": "fakex"}}
        STATE = {{"syms": ["S%02d" % i for i in range(10)], "calls": [], "sleep": 0.0, "fail": False}}
        def fetch(http):
            STATE["calls"].append((time.time(), threading.current_thread().name))
            if STATE["sleep"]:
                time.sleep(STATE["sleep"])
            if STATE["fail"]:
                raise RuntimeError("boom")
            http.get_json("https://fake.example/markets")
            return {{"KRW": [{{"symbol": s, "quote": "KRW", "access_kind": "SPOT"}} for s in STATE["syms"]]}}
    ''',
    "ann": f'''
        ANNS = []
        PLATFORMS = [{PLATFORM}]
        def fetch_notices(http):
            return list(ANNS)
        SOURCES = {{"fake_notice": {{"kind": "announcement", "fetch": fetch_notices, "period_sec": 0.2,
                                    "source": {{"kind": "ANNOUNCEMENT", "tier": "OFFICIAL_ANNOUNCEMENT",
                                               "origin_platform_id": "fakex"}}}}}}
    ''',
    "stream": f'''
        import time
        SOURCE_ID = "fake_stream"
        KIND = "stream"
        HEARTBEAT_SEC = 0.3
        PLATFORMS = [{PLATFORM}]
        SOURCE = {{"kind": "ANNOUNCEMENT", "tier": "OFFICIAL_ANNOUNCEMENT", "origin_platform_id": "fakex"}}
        STATE = {{"runs": 0, "mode": "drop", "backfills": [], "starts": [], "bf_fail": 0}}
        def run(ctx):
            STATE["runs"] += 1
            STATE["starts"].append(time.time())
            ctx.connected()
            ctx.heartbeat()
            ctx.emit_announcement({{"action": "LISTING", "platform_id": "fakex", "symbol": "WS1", "quote": "KRW",
                                   "source_event_id": "ws-1"}})
            if STATE["mode"] == "drop" and STATE["runs"] <= 2:
                raise ConnectionError("socket closed by peer")
            if STATE["mode"] == "silent":          # connected but no more heartbeats: watchdog must kick in
                while not ctx.should_stop():
                    time.sleep(0.01)
                return
            while not ctx.should_stop():
                ctx.heartbeat()
                time.sleep(0.01)
        def backfill(http, since_ms, until_ms):
            STATE["backfills"].append((since_ms, until_ms))
            if STATE["bf_fail"] > 0:
                STATE["bf_fail"] -= 1
                raise TimeoutError("history api timed out")
            return [{{"action": "LISTING", "platform_id": "fakex", "symbol": "GAP1", "quote": "KRW",
                     "source_event_id": "gap-1"}}]
    ''',
    "conn": f'''
        import threading
        import radar_core as rc
        SOURCE_ID = "fake_conn"
        STATE = {{"syms": ["C1", "C2", "C3", "C4"], "fetch_threads": []}}
        def register(conn, at=None):
            rc.register_platform(conn, "fakeramp", "FakeRamp", "ONRAMP", "")
            rc.register_source(conn, SOURCE_ID, kind="SNAPSHOT", tier="OFFICIAL_STRUCTURED", origin_platform_id="fakeramp")
        def run_once(conn, fetch=None, fetched_at=None):
            d = fetch("https://fake.example/conn")
            STATE["fetch_threads"].append(threading.current_thread().name)
            items = [{{"platform_id": "fakeramp", "symbol": s, "access_kind": "FIAT_ROUTE", "fiat": "EUR"}}
                     for s in STATE["syms"]]
            return {{"EUR": rc.ingest_snapshot(conn, SOURCE_ID, "EUR", items, fetched_at=fetched_at)}}
    ''',
    "discovered": f'''
        SOURCE_ID = "fake_discovered"
        KIND = "snapshot"
        PERIOD_SEC = 0.25
        PLATFORMS = [{PLATFORM}]
        def fetch(http):
            return [{{"symbol": "D1", "quote": "KRW", "access_kind": "SPOT"}}] * 1
    ''',
    "maint": '''
        import threading
        import radar_core as rc
        STATE = {"prepare_threads": [], "apply_threads": [], "mode": "ok"}
        def prepare(http):
            STATE["prepare_threads"].append(threading.current_thread().name)
            if STATE["mode"] == "raise":
                raise RuntimeError("prepare boom")
            http.get_json("https://fake.example/maint")
            return {"n": len(STATE["prepare_threads"])}
        def apply(conn, payload):
            STATE["apply_threads"].append(threading.current_thread().name)
            rc.upsert_asset(conn, "crypto:test:0xmaint", "CRYPTO", "MNT", name="Maint")
            out = {"n": payload["n"], "written": 1}
            if STATE["mode"] == "soft_error":
                out["error"] = "partial failure"
            return out
    ''',
    "broken": "import not_a_real_dependency_xyz_123\n",
    "helpers": "def util():\n    return 1\n",     # no SOURCE_ID: ignored silently by discovery
}


class FakeHttp:
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def get_json(self, url, params=None, headers=None, **kw):
        with self.lock:
            self.calls.append((url, threading.current_thread().name))
        return {"ok": True}


class RunnerTestBase(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.tmp = tempfile.mkdtemp(prefix="ar_runner_")
        self.pkg = "fakead_" + uuid.uuid4().hex[:8]
        os.makedirs(os.path.join(self.tmp, self.pkg))
        for name, src in FAKE_MODULES.items():
            with open(os.path.join(self.tmp, self.pkg, name + ".py"), "w") as f:
                f.write(textwrap.dedent(src))
        sys.path.insert(0, self.tmp)
        self.db = os.path.join(self.tmp, "access.sqlite")
        self.lock_path = os.path.join(self.tmp, "logs", "access.lock")
        self.http = FakeHttp()
        P = self.pkg
        self.catalog = [
            S.Entry("fake_snap", 0.3, f"{P}.snap"),
            S.Entry("fake_notice", 0.2, f"{P}.ann"),
            S.Entry("fake_stream", 0, f"{P}.stream"),
            S.Entry("fake_missing", 1, f"{P}.not_written"),
            S.Entry("fake_broken", 1, f"{P}.broken"),
            S.Entry("fake_conn", 0.3, f"{P}.conn"),
            S.Entry("fake_wrongid", 1, f"{P}.snap"),
        ]
        self.runners, self.writers = [], []

    def tearDown(self):
        for r in self.runners:
            r.stop(timeout=3)
        for w in self.writers:
            w.stop()
        sys.path.remove(self.tmp)
        for m in [m for m in sys.modules if m == self.pkg or m.startswith(self.pkg + ".")]:
            del sys.modules[m]
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mod(self, name):
        return sys.modules[f"{self.pkg}.{name}"]

    def make_runner(self, catalog=None, **kw):
        w = access_db.Writer(self.db).start()
        self.writers.append(w)
        kw.setdefault("discover_package", self.pkg)
        r = S.Runner(w, self.http, catalog=self.catalog if catalog is None else catalog, **kw)
        self.runners.append(r)
        return w, r

    def once(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return access_run.cmd_once(self.db, catalog=self.catalog, http=self.http,
                                       discover_package=self.pkg, lock_path=self.lock_path)

    def q(self, sql, args=()):
        conn = access_db.connect(self.db)
        try:
            return [dict(r) for r in conn.execute(sql, args)]
        finally:
            conn.close()

    def wait_for(self, cond, timeout=5.0, step=0.02):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(step)
        return cond()


class TestAdapterLoading(RunnerTestBase):
    def test_states_and_skip_missing_with_log_line(self):
        with self.assertLogs("access_radar.sched", level="INFO") as cm:
            res = S.load_catalog(self.catalog, discover_package=self.pkg)
        states = {r.entry.source_id: r.state for r in res}
        self.assertEqual(states["fake_snap"], "ok")
        self.assertEqual(states["fake_notice"], "ok")
        self.assertEqual(states["fake_stream"], "ok")
        self.assertEqual(states["fake_conn"], "ok")
        self.assertEqual(states["fake_missing"], "missing")
        self.assertEqual(states["fake_broken"], "error")
        self.assertEqual(states["fake_wrongid"], "no_source")
        self.assertEqual(states["fake_discovered"], "ok")          # not in catalog, found by discovery
        spec = {r.entry.source_id: r.spec for r in res if r.spec}
        self.assertEqual(spec["fake_discovered"].period_sec, 0.25)
        self.assertEqual(spec["fake_notice"].kind, "announcement")
        self.assertEqual(spec["fake_conn"].mode, "conn")
        self.assertEqual(spec["fake_snap"].period_sec, 0.3)        # catalog period wins
        logs = "\n".join(cm.output)
        self.assertIn("skip fake_missing", logs)
        self.assertIn("not found", logs)
        self.assertIn("skip fake_broken", logs)

    def test_real_catalog_loads_today(self):
        # The production CATALOG must load even though most adapters are not written yet.
        res = S.load_catalog(discover_package=None)
        self.assertEqual(len(res), len([e for e in S.CATALOG if e.kind != "maintenance"]))
        self.assertNotIn("resolve", {r.entry.source_id for r in res})          # maintenance is not a source
        self.assertTrue(all(r.state in ("ok", "missing", "error", "no_source") for r in res))

    def test_backoff_sequence(self):
        self.assertEqual(list(itertools.islice(S.backoff_delays(1, 30), 7)), [1, 2, 4, 8, 16, 30, 30])


class TestOnceFeedStatus(RunnerTestBase):
    def test_once_baseline_then_events_feed_and_status(self):
        s1 = self.once()
        self.assertTrue(s1["ok"])
        by = {r["source_id"]: r for r in s1["sources"]}
        self.assertTrue(by["fake_snap"]["ok"])
        self.assertEqual(by["fake_snap"]["events"], [])            # first snapshot = baseline
        self.assertNotIn("fake_stream", by)                          # not reported as a (failed) source
        skipped = {x["source_id"]: x["state"] for x in s1["skipped"]}
        self.assertEqual(skipped["fake_stream"], "stream_loop_only")
        self.assertTrue(all(r.get("ok") for r in s1["sources"] if r["source_id"] != "fake_broken"))
        self.assertEqual(skipped["fake_missing"], "missing")
        snap, ann = self.mod("snap"), self.mod("ann")
        snap.STATE["syms"].append("NEW1")
        ann.ANNS.append({"action": "LISTING", "platform_id": "fakex", "symbol": "ANN1", "quote": "KRW",
                         "source_event_id": "n-1"})
        s2 = self.once()
        by = {r["source_id"]: r for r in s2["sources"]}
        self.assertEqual(len(by["fake_snap"]["events"]), 1)
        self.assertEqual(len(by["fake_notice"]["events"]), 1)
        s3 = self.once()                                           # re-polling the same notice is idempotent
        self.assertEqual({r["source_id"]: r for r in s3["sources"]}["fake_notice"]["events"], [])

        buf = io.StringIO()
        evs = access_run.cmd_feed(self.db, "1h", out=buf)
        out = buf.getvalue()
        self.assertIn("SPOT_LISTED", out)
        self.assertIn("SPOT_ANNOUNCED", out)
        self.assertIn("fakex", out)
        self.assertIn("UTC+8", out)
        self.assertEqual(len(evs), 2)
        buf = io.StringIO()
        access_run.cmd_feed(self.db, "7d", as_json=True, out=buf)
        types = sorted(e["event_type"] for e in json.loads(buf.getvalue()))
        self.assertEqual(types, ["SPOT_ANNOUNCED", "SPOT_LISTED"])
        with self.assertRaises(SystemExit):
            access_run.cmd_feed(self.db, "2h", out=io.StringIO())
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            access_run.main(["--db", self.db, "feed", "--window", "5h"])

        buf = io.StringIO()
        p = access_run.cmd_status(self.db, as_json=True, out=buf)
        st = {s["source_id"]: s for s in json.loads(buf.getvalue())["sources"]}
        self.assertEqual(st["fake_snap"]["status"], "LIVE")
        self.assertEqual(st["fake_snap"]["successes"], 3)
        self.assertEqual(st["fake_missing"]["status"], "MISSING")
        self.assertEqual(st["fake_broken"]["status"], "ERROR")
        self.assertEqual(st["fake_snap"]["radar_health"][0]["status"], "HEALTHY")
        self.assertIn("upbit_market", st)                          # production catalog shown as never started
        self.assertIsNotNone(p["collector_heartbeat"])
        buf = io.StringIO()
        access_run.cmd_status(self.db, out=buf)
        self.assertIn("MISSING", buf.getvalue())
        self.assertIn("scope KRW", buf.getvalue())

    def test_fetch_error_reports_down_without_touching_last_success(self):
        self.once()
        before = self.q("SELECT * FROM source_run WHERE source_id='fake_snap'")[0]
        self.mod("snap").STATE["fail"] = True
        self.once()
        after = self.q("SELECT * FROM source_run WHERE source_id='fake_snap'")[0]
        self.assertEqual(after["consecutive_errors"], 1)
        self.assertEqual(after["last_success"], before["last_success"])
        self.assertIn("boom", after["last_error"])
        h = self.q("SELECT * FROM source_health WHERE source_id='fake_snap' AND scope='KRW'")[0]
        self.assertEqual(h["status"], "DOWN")
        self.assertEqual(self.q("SELECT COUNT(*) n FROM access_event WHERE family='REMOVE'")[0]["n"], 0)

    def test_conn_adapter_network_outside_writer_and_replayed(self):
        self.once()
        conn_calls = [c for c in self.http.calls if c[0].endswith("/conn")]
        self.assertEqual(len(conn_calls), 1)                       # recorded once, replayed in the writer
        self.assertNotEqual(conn_calls[0][1], "access-writer")
        threads = self.mod("conn").STATE["fetch_threads"]
        self.assertIn("access-writer", threads)                    # replay pass ran on the writer
        self.mod("conn").STATE["syms"].append("C5")
        s = self.once()
        self.assertEqual(len({r["source_id"]: r for r in s["sources"]}["fake_conn"]["events"]), 1)
        self.assertEqual(self.q("SELECT event_type FROM access_event WHERE platform_id='fakeramp'")[0]["event_type"],
                         "FIAT_ROUTE_SUPPORTED")

    def test_tick_cli(self):
        buf = io.StringIO()
        access_run.cmd_tick(self.db, out=buf)
        self.assertIn("applied 0 scheduled removals", buf.getvalue())


class TestLoopScheduling(RunnerTestBase):
    def test_one_thread_per_source_period_from_request_start(self):
        self.mod_snap_sleep = 0.15
        w, r = self.make_runner()
        r.prepare()
        self.mod("snap").STATE["sleep"] = 0.15                     # request takes half the period
        r.start()
        time.sleep(1.45)
        r.stop()
        calls = self.mod("snap").STATE["calls"]
        starts = [t for t, _ in calls]
        self.assertGreaterEqual(len(starts), 4)
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        mean = sum(gaps) / len(gaps)
        # measured from request start: ~0.30s, not 0.30 + 0.15
        self.assertGreater(mean, 0.27)
        self.assertLess(mean, 0.40)
        self.assertEqual({n for _, n in calls}, {"access-fake_snap"})
        names = {n for _, _, _, _, n in r.poll_log}
        self.assertIn("access-fake_notice", names)
        self.assertIn("access-fake_discovered", names)
        self.assertNotIn("access-fake_missing", names)
        self.assertNotIn("access-fake_broken", names)

    def test_single_writer_all_writes_on_writer_thread(self):
        seen, active, maxc = [], [0], [0]
        lock = threading.Lock()
        originals = {n: getattr(rc, n) for n in ("ingest_snapshot", "ingest_announcement", "report_fetch_error",
                                                 "mark_disconnected", "mark_reconnected")}

        real_db = os.path.realpath(self.db)

        def wrap(fn):
            def inner(*a, **kw):
                # conn-style adapters also run a scratch pass on a private :memory: DB in their own thread
                # (network capture); only writes to the real access.sqlite must go through the writer.
                if os.path.realpath(a[0].execute("PRAGMA database_list").fetchone()[2] or ":memory:") != real_db:
                    return fn(*a, **kw)
                with lock:
                    active[0] += 1
                    maxc[0] = max(maxc[0], active[0])
                    seen.append(threading.get_ident())
                try:
                    time.sleep(0.002)
                    return fn(*a, **kw)
                finally:
                    with lock:
                        active[0] -= 1
            return inner

        for n, f in originals.items():
            setattr(rc, n, wrap(f))
        try:
            w, r = self.make_runner(stream_backoff=(0.05, 0.1))
            r.prepare()
            self.mod("ann").ANNS.extend({"action": "LISTING", "platform_id": "fakex", "symbol": f"A{i}",
                                         "source_event_id": f"a{i}"} for i in range(5))
            r.start()
            time.sleep(1.0)
            r.stop()
        finally:
            for n, f in originals.items():
                setattr(rc, n, f)
        self.assertGreater(len(seen), 10)
        self.assertEqual(set(seen), {w.thread_ident})
        self.assertEqual(maxc[0], 1)

    def test_writer_serializes_many_threads_and_propagates_errors(self):
        w = access_db.Writer(self.db).start()
        self.writers.append(w)
        w.call(lambda c: c.execute("CREATE TABLE t (n INTEGER) STRICT"))
        w.call(lambda c: c.execute("INSERT INTO t VALUES (0)"))
        state = {"active": 0, "max": 0, "idents": set()}

        def inc(conn):
            state["active"] += 1
            state["max"] = max(state["max"], state["active"])
            state["idents"].add(threading.get_ident())
            conn.execute("UPDATE t SET n = n + 1")
            state["active"] -= 1

        def worker():
            for _ in range(50):
                w.call(inc)

        ts = [threading.Thread(target=worker) for _ in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(w.call(lambda c: c.execute("SELECT n FROM t").fetchone()[0]), 400)
        self.assertEqual(state["max"], 1)
        self.assertEqual(state["idents"], {w.thread_ident})
        with self.assertRaises(ZeroDivisionError):
            w.call(lambda c: 1 / 0)
        self.assertEqual(w.call(lambda c: 42), 42)                 # still alive after a failed job
        w.stop()
        with self.assertRaises(access_db.WriterStopped):
            w.submit(lambda c: 1)

    def test_loop_command_heartbeat_lock_and_clean_stop(self):
        stop = threading.Event()
        t = threading.Thread(target=access_run.cmd_loop, kwargs=dict(
            db=self.db, catalog=self.catalog, http=self.http, discover_package=self.pkg,
            lock_path=self.lock_path, stop_event=stop, heartbeat_every=0.2, tick_every=0.2))
        t.start()
        try:
            self.assertTrue(self.wait_for(lambda: os.path.exists(self.db) and
                                          self.q("SELECT v FROM runner_meta WHERE k='collector_heartbeat'"), 5))
            with self.assertRaises(access_run.LockBusy):           # loop holds the lock
                access_run.acquire_lock(self.lock_path)
            r = access_run.cmd_loop(self.db, catalog=self.catalog, http=self.http, discover_package=self.pkg,
                                    lock_path=self.lock_path, lock_busy_sleep=0)
            self.assertEqual(r, {"skipped": True, "reason": "lock_busy"})
        finally:
            stop.set()
            t.join(10)
        self.assertFalse(t.is_alive())
        access_run.release_lock(access_run.acquire_lock(self.lock_path))   # released after stop


class TestStreams(RunnerTestBase):
    def stream_only(self):
        return [S.Entry("fake_stream", 0, f"{self.pkg}.stream")]

    def test_disconnect_reconnect_backoff_gaps_and_backfill(self):
        w, r = self.make_runner(catalog=self.stream_only(), discover_package=None, stream_backoff=(0.05, 0.2))
        r.prepare()
        st = self.mod("stream").STATE
        r.start()
        self.assertTrue(self.wait_for(lambda: st["runs"] >= 3 and r.streams["fake_stream"].is_connected, 5))
        time.sleep(0.1)
        status = self.q("SELECT * FROM source_run WHERE source_id='fake_stream'")[0]
        self.assertEqual(status["connected"], 1)
        self.assertEqual(access_db.classify_status(rc.now_ms(), status), "LIVE")
        r.stop()
        gaps = self.q("SELECT * FROM source_disconnect WHERE source_id='fake_stream' ORDER BY disconnect_id")
        reasons = [g["reason"] for g in gaps]
        self.assertEqual(reasons[0], "process start")
        self.assertEqual(sum("socket closed" in x for x in reasons), 2)
        self.assertEqual(reasons[-1], "runner stopping")
        self.assertTrue(all(g["ended_at"] is not None for g in gaps[:-1]))
        self.assertIsNone(gaps[-1]["ended_at"])
        self.assertEqual(len(st["backfills"]), 3)                  # every closed gap was backfilled
        self.assertTrue(all(a <= b for a, b in st["backfills"]))
        self.assertTrue(all(g["backfilled"] for g in gaps[:-1]))
        # backoff grows: 0.05 then 0.1
        d1, d2 = st["starts"][1] - st["starts"][0], st["starts"][2] - st["starts"][1]
        self.assertGreaterEqual(d1, 0.045)
        self.assertGreaterEqual(d2, 0.095)
        # idempotent announcements across reconnects / backfills
        self.assertEqual(self.q("SELECT COUNT(*) n FROM source_observation WHERE source_event_id='ws-1'")[0]["n"], 1)
        self.assertEqual(self.q("SELECT COUNT(*) n FROM source_observation WHERE source_event_id='gap-1'")[0]["n"], 1)
        self.assertEqual(self.q("SELECT COUNT(*) n FROM access_event WHERE event_type='SPOT_ANNOUNCED'")[0]["n"], 2)
        down = self.q("SELECT * FROM source_run WHERE source_id='fake_stream'")[0]
        self.assertEqual(access_db.classify_status(rc.now_ms(), down), "DOWN")

    def test_heartbeat_watchdog_forces_reconnect(self):
        w, r = self.make_runner(catalog=self.stream_only(), discover_package=None, stream_backoff=(0.05, 0.1),
                                watchdog_every=0.05)
        r.prepare()
        st = self.mod("stream").STATE
        st["mode"] = "silent"
        r.start()
        self.assertTrue(self.wait_for(lambda: st["runs"] >= 2, 5))
        r.stop()
        reasons = [g["reason"] for g in self.q("SELECT reason FROM source_disconnect WHERE source_id='fake_stream'")]
        self.assertIn("heartbeat timeout", reasons)


class TestBackfillRetry(RunnerTestBase):
    def stream_only(self):
        return [S.Entry("fake_stream", 0, f"{self.pkg}.stream")]

    def run_row(self):
        return self.q("SELECT * FROM source_run WHERE source_id='fake_stream'")[0]

    def health_row(self):
        return self.q("SELECT * FROM source_health WHERE source_id='fake_stream' AND scope=''")[0]

    def test_failed_backfill_is_reported_then_retried_until_success(self):
        w, r = self.make_runner(catalog=self.stream_only(), discover_package=None, stream_backoff=(0.05, 0.2),
                                backfill_retry_sec=0.15)
        r.prepare()
        st = self.mod("stream").STATE
        st["mode"], st["bf_fail"] = "stay", 3                       # stays connected; history fails 3 times
        r.start()
        self.assertTrue(self.wait_for(lambda: len(st["backfills"]) >= 2, 5))
        self.assertIn("backfill failed for gap", self.run_row()["last_error"])
        self.assertIn("TimeoutError: history api timed out", self.health_row()["last_error"])
        self.assertEqual(self.run_row()["connected"], 1)           # the stream itself stays connected
        gap = self.q("SELECT * FROM source_disconnect WHERE source_id='fake_stream' ORDER BY disconnect_id")[0]
        self.assertEqual(gap["backfilled"], 0)
        self.assertTrue(self.wait_for(lambda: self.q(
            "SELECT backfilled FROM source_disconnect WHERE disconnect_id=?", (gap["disconnect_id"],))[0]["backfilled"]
            == 1, 5))
        self.assertTrue(self.wait_for(lambda: self.run_row()["last_error"] == "", 2))
        self.assertEqual(self.health_row()["last_error"], "")
        self.assertEqual(len(st["backfills"]), 4)                  # 3 failures + 1 success, same gap each time
        self.assertEqual(len(set(st["backfills"])), 1)
        self.assertEqual(self.q("SELECT COUNT(*) n FROM source_observation WHERE source_event_id='gap-1'")[0]["n"], 1)
        time.sleep(0.4)
        self.assertEqual(len(st["backfills"]), 4)                  # nothing pending -> no more calls
        self.assertIn("access-backfill", {t.name for t in r.threads})

    def test_pending_order_batch_age_cap_and_stop_on_failure(self):
        w, r = self.make_runner(catalog=self.stream_only(), discover_package=None, backfill_batch=2,
                                backfill_max_age_sec=7 * 86400)
        r.prepare()
        spec = r.specs[0]
        now, day = rc.now_ms(), 86400 * 1000
        rows = [(now - 10 * day, now - 9 * day), (now - 3 * day, now - 3 * day + 5000),
                (now - 2 * day, now - 2 * day + 5000), (now - day, now - day + 5000)]

        def seed(conn):
            for a, b in rows:
                conn.execute("INSERT INTO source_disconnect(source_id, scope, started_at, ended_at, reason) "
                             "VALUES ('fake_stream', '', ?, ?, 'test')", (a, b))
            conn.execute("INSERT INTO source_disconnect(source_id, scope, started_at, reason) "
                         "VALUES ('fake_stream', '', ?, 'still open')", (now,))
        w.call(seed)
        st = self.mod("stream").STATE
        st["bf_fail"] = 1
        res = r.backfill_pending(spec)                              # oldest eligible fails -> round stops
        self.assertEqual([ok for _, ok in res], [False])
        self.assertEqual(st["backfills"], [rows[1]])                # 10-day-old gap skipped (age cap)
        self.assertIn("backfill failed", self.run_row()["last_error"])
        res = r.backfill_pending(spec)                              # batch of 2, oldest first
        self.assertEqual([ok for _, ok in res], [True, True])
        self.assertEqual(st["backfills"][1:], [rows[1], rows[2]])
        self.assertIn("backfill failed", self.run_row()["last_error"])   # one gap still pending -> keep the error
        r.backfill_pending(spec)
        self.assertEqual(st["backfills"][3:], [rows[3]])
        self.assertEqual(self.run_row()["last_error"], "")
        left = self.q("SELECT backfilled FROM source_disconnect WHERE source_id='fake_stream' ORDER BY started_at")
        self.assertEqual([x["backfilled"] for x in left], [0, 1, 1, 1, 0])   # too old + still open stay 0
        self.assertEqual(r.backfill_pending(spec), [])


class TestLock(RunnerTestBase):
    def test_lock_in_process_and_across_processes(self):
        fd = access_run.acquire_lock(self.lock_path)
        try:
            with self.assertRaises(access_run.LockBusy):
                access_run.acquire_lock(self.lock_path)
            s = self.once()
            self.assertEqual(s, {"skipped": True, "reason": "lock_busy"})
            code = ("import fcntl,sys; f=open(sys.argv[1],'a+')\n"
                    "try:\n fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB); print('got')\n"
                    "except OSError: print('busy')")
            out = subprocess.run([sys.executable, "-c", code, self.lock_path], capture_output=True, text=True).stdout
            self.assertEqual(out.strip(), "busy")
            with open(self.lock_path) as f:
                self.assertEqual(f.read().strip(), str(os.getpid()))
        finally:
            access_run.release_lock(fd)
        access_run.release_lock(access_run.acquire_lock(self.lock_path))


# ----------------------------------------------------------------------------- maintenance jobs
class TestMaintenance(RunnerTestBase):
    def setUp(self):
        super().setUp()
        P = self.pkg
        self.mcat = self.catalog + [
            S.Entry("fake_maint", 0.2, f"{P}.maint", kind="maintenance"),
            S.Entry("fake_maint_missing", 1, f"{P}.no_such_maint", kind="maintenance"),
            S.Entry("fake_maint_bad", 1, f"{P}.helpers", kind="maintenance"),      # no prepare/apply
        ]

    def mrow(self, job_id):
        rows = self.q("SELECT * FROM maintenance_run WHERE job_id=?", (job_id,))
        return rows[0] if rows else None

    def spec(self, r, job_id="fake_maint"):
        return [s for s in r.maint_specs if s.job_id == job_id][0]

    def test_load_skips_missing_and_bad_and_is_not_a_source(self):
        with self.assertLogs("access_radar", level="INFO") as cm:
            res = S.load_maintenance(self.mcat)
        states = {r.entry.source_id: r.state for r in res}
        self.assertEqual(states, {"fake_maint": "ok", "fake_maint_missing": "missing", "fake_maint_bad": "error"})
        self.assertIn("skip maintenance fake_maint_missing", "\n".join(cm.output))
        self.assertTrue(all(not r.entry.source_id.startswith("fake_maint")
                            for r in S.load_catalog(self.mcat, discover_package=None)))
        real = {r.entry.source_id: r.state for r in S.load_maintenance()}
        self.assertEqual(real.get("resolve"), "ok")

    def test_run_two_phase_threads_and_no_source_rows(self):
        w, r = self.make_runner(self.mcat)
        r.prepare()
        out = {}
        t = threading.Thread(target=lambda: out.update(r.run_maintenance(self.spec(r))), name="maint-caller")
        t.start()
        t.join(5)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["result"], {"n": 1, "written": 1})
        m = self.mod("maint")
        self.assertEqual(m.STATE["prepare_threads"], ["maint-caller"])              # network off the writer
        self.assertEqual(m.STATE["apply_threads"], ["access-writer"])               # DB write in the writer
        self.assertIn(("https://fake.example/maint", "maint-caller"), self.http.calls)
        self.assertEqual(len(self.q("SELECT * FROM asset WHERE asset_key='crypto:test:0xmaint'")), 1)
        for tbl in ("source", "source_health", "source_run"):
            self.assertEqual(self.q(f"SELECT * FROM {tbl} WHERE source_id LIKE 'fake_maint%'"), [], tbl)
        row = self.mrow("fake_maint")
        self.assertEqual((row["job_state"], row["attempts"], row["successes"], row["consecutive_errors"]),
                         ("ok", 1, 1, 0))
        self.assertEqual(json.loads(row["last_result"]), {"n": 1, "written": 1})
        self.assertEqual(self.mrow("fake_maint_missing")["job_state"], "missing")
        self.assertEqual(self.mrow("fake_maint_bad")["job_state"], "error")

    def test_error_key_and_exception_count_as_failures(self):
        w, r = self.make_runner(self.mcat)
        r.prepare()
        m = self.mod("maint")
        m.STATE["mode"] = "soft_error"
        res = r.run_maintenance(self.spec(r))
        self.assertFalse(res["ok"])
        self.assertIn("partial failure", res["error"])
        m.STATE["mode"] = "raise"
        res = r.run_maintenance(self.spec(r))
        self.assertFalse(res["ok"])
        self.assertIn("prepare boom", res["error"])
        row = self.mrow("fake_maint")
        self.assertEqual((row["consecutive_errors"], row["attempts"], row["successes"]), (2, 2, 0))
        self.assertIn("prepare boom", row["last_error"])
        m.STATE["mode"] = "ok"
        self.assertTrue(r.run_maintenance(self.spec(r))["ok"])
        row = self.mrow("fake_maint")
        self.assertEqual((row["consecutive_errors"], row["successes"]), (0, 1))

    def test_loop_runs_in_own_thread_and_once_skips_it(self):
        s = None
        with contextlib.redirect_stdout(io.StringIO()):
            s = access_run.cmd_once(self.db, catalog=self.mcat, http=self.http, discover_package=self.pkg,
                                    lock_path=self.lock_path)
        self.assertTrue(s["ok"])
        self.assertEqual(self.mod("maint").STATE["apply_threads"], [])           # `once` = data sources only
        self.assertNotIn("fake_maint", {x["source_id"] for x in s["sources"]})
        w, r = self.make_runner(self.mcat)
        r.prepare()
        r.start()
        self.assertTrue(self.wait_for(lambda: sum(1 for x in r.maint_log if x[0] == "fake_maint") >= 3))
        runs = [x for x in r.maint_log if x[0] == "fake_maint"]
        self.assertEqual({x[4] for x in runs}, {"access-maint-fake_maint"})
        self.assertEqual({x[5] for x in runs}, {"access-writer"})
        self.assertTrue(all(x[3] for x in runs))
        self.assertGreaterEqual(runs[2][1] - runs[0][1], 0.3)                      # period respected (0.2 s)

    def test_status_has_separate_maintenance_section(self):
        w, r = self.make_runner(self.mcat)
        r.prepare()
        r.run_maintenance(self.spec(r))
        w.stop()
        conn = access_db.connect(self.db)
        try:
            p = access_run.status_payload(conn)
        finally:
            conn.close()
        self.assertNotIn("fake_maint", {s["source_id"] for s in p["sources"]})
        self.assertNotIn("resolve", {s["source_id"] for s in p["sources"]})
        mt = {m["job_id"]: m for m in p["maintenance"]}
        self.assertEqual(mt["fake_maint"]["status"], "LIVE")
        self.assertEqual(mt["fake_maint"]["last_result"], {"n": 1, "written": 1})
        self.assertEqual(mt["fake_maint_missing"]["job_state"], "missing")
        self.assertIn("resolve", mt)                                               # real CATALOG job, never run here
        buf = io.StringIO()
        access_run.cmd_status(self.db, out=buf)
        txt = buf.getvalue()
        self.assertIn("maintenance (not data sources)", txt)
        self.assertIn("fake_maint", txt.split("maintenance (not data sources)")[1])

    def test_cli_runs_once_rejects_unknown_and_refuses_when_locked(self):
        buf = io.StringIO()
        res = access_run.cmd_maintenance(self.db, ["fake_maint"], catalog=self.mcat, http=self.http,
                                         lock_path=self.lock_path, out=buf)
        self.assertTrue(res["ok"])
        self.assertEqual(json.loads(buf.getvalue())["jobs"][0]["job_id"], "fake_maint")
        res = access_run.cmd_maintenance(self.db, None, catalog=self.mcat, http=self.http,
                                         lock_path=self.lock_path, out=io.StringIO())
        self.assertEqual([j["job_id"] for j in res["jobs"]], ["fake_maint"])
        self.assertEqual({x["job_id"] for x in res["skipped"]}, {"fake_maint_missing", "fake_maint_bad"})
        self.assertEqual(self.mrow("fake_maint")["attempts"], 2)
        with self.assertRaises(SystemExit):
            access_run.cmd_maintenance(self.db, ["nope"], catalog=self.mcat, http=self.http,
                                       lock_path=self.lock_path, out=io.StringIO())
        access_run.release_lock(access_run.acquire_lock(self.lock_path))          # lock released after the error
        fd = access_run.acquire_lock(self.lock_path)
        try:
            res = access_run.cmd_maintenance(self.db, ["fake_maint"], catalog=self.mcat, http=self.http,
                                             lock_path=self.lock_path, out=io.StringIO())
            self.assertEqual(res, {"skipped": True, "reason": "lock_busy"})
        finally:
            access_run.release_lock(fd)
        self.assertEqual(self.mrow("fake_maint")["attempts"], 2)


class AlphaHttp:
    """Fake shared HTTP client for resolve.fetch_alpha: records (url, thread)."""
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def get_json(self, url, params=None, headers=None, **kw):
        self.calls.append((url, threading.current_thread().name))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


REZ_CA = "0xAbCdEf0000000000000000000000000000000001"
ALPHA = {"code": "000000", "data": [
    {"alphaId": "ALPHA_1", "symbol": "REZ", "name": "Renzo", "chainId": "56", "contractAddress": REZ_CA,
     "decimals": "18"}]}


class TestResolveMaintenance(RunnerTestBase):
    """Integration with the real resolve.py through the maintenance path (fake HTTP, temp DB)."""
    def setUp(self):
        super().setUp()
        self.rcat = [S.Entry("resolve", 3600, "resolve", kind="maintenance")]
        import resolve
        self.rs = resolve
        w = access_db.Writer(self.db).start()

        def seed(conn):
            rc.register_platform(conn, "upbit", "Upbit", "CEX", "KR")
            rc.register_source(conn, "upbit_market", kind="SNAPSHOT", tier="OFFICIAL_STRUCTURED",
                               origin_platform_id="upbit")
            rc.ingest_snapshot(conn, "upbit_market", "KRW",
                               [{"symbol": s, "quote": "KRW", "access_kind": "SPOT"} for s in ("REZ", "ZZNOPE")])
        w.call(seed)
        w.stop()

    def ref(self, sym):
        return self.q("SELECT * FROM source_asset_ref WHERE platform_id='upbit' AND platform_symbol=?", (sym,))[0]

    def test_resolve_job_fetches_off_writer_and_writes_in_writer(self):
        http = AlphaHttp(ALPHA)
        buf = io.StringIO()
        res = access_run.cmd_maintenance(self.db, ["resolve"], catalog=self.rcat, http=http,
                                         lock_path=self.lock_path, out=buf)
        self.assertTrue(res["ok"], res)
        job = res["jobs"][0]["result"]
        self.assertEqual((job["alpha_error"], job["alpha_tokens"], job["new_assets"], job["suggested"]), ("", 1, 1, 1))
        self.assertEqual(len(http.calls), 1)
        self.assertEqual(http.calls[0][0], self.rs.ALPHA_URL)
        self.assertNotEqual(http.calls[0][1], "access-writer")
        key = "crypto:bsc:" + REZ_CA.lower()
        aid = self.q("SELECT asset_id FROM asset WHERE asset_key=?", (key,))[0]["asset_id"]
        r = self.ref("REZ")
        self.assertEqual((r["resolution_status"], r["resolution_source"], r["suggested_asset_id"]),
                         ("SUGGESTED", "symbol", aid))
        self.assertIsNone(r["asset_id"])                                           # SUGGESTED is not CONFIRMED
        self.assertEqual(self.ref("ZZNOPE")["resolution_status"], "UNRESOLVED")
        self.assertEqual(self.q("SELECT * FROM source WHERE source_id='resolve'"), [])
        self.assertEqual(self.q("SELECT * FROM source_health WHERE source_id='resolve'"), [])
        row = self.q("SELECT * FROM maintenance_run WHERE job_id='resolve'")[0]
        self.assertEqual((row["job_state"], row["successes"], row["module"]), ("ok", 1, "resolve"))
        # second run is idempotent
        res2 = access_run.cmd_maintenance(self.db, ["resolve"], catalog=self.rcat, http=http,
                                          lock_path=self.lock_path, out=io.StringIO())
        self.assertEqual((res2["jobs"][0]["result"]["new_assets"], res2["jobs"][0]["result"]["already_suggested"]),
                         (0, 1))

    def test_alpha_failure_is_a_failed_run_but_pass_still_runs(self):
        w, r = self.make_runner(self.rcat)
        r.prepare_maintenance()
        w.call(lambda conn: self.rs.register_alpha(conn, self.rs.parse_alpha(ALPHA)))   # registry from earlier run
        r.http = AlphaHttp(ConnectionError("alpha down"))
        res = r.run_maintenance(r.maint_specs[0])
        self.assertFalse(res["ok"])
        self.assertIn("alpha down", res["error"])
        self.assertEqual((res["result"]["checked"], res["result"]["suggested"]), (2, 1))   # pass ran anyway
        self.assertEqual(self.ref("REZ")["resolution_status"], "SUGGESTED")
        row = self.q("SELECT * FROM maintenance_run WHERE job_id='resolve'")[0]
        self.assertEqual((row["consecutive_errors"], row["successes"]), (1, 0))
        self.assertIn("ConnectionError", row["last_error"])
        self.assertEqual(r.maint_log[-1][4], "MainThread")
        self.assertEqual(r.maint_log[-1][5], "access-writer")


# ----------------------------------------------------------------------------- HTTP client (local server)
class _Handler(http.server.BaseHTTPRequestHandler):
    script = {}      # path -> list of (status, body); last entry repeats
    hits = {}
    seen_headers = {}

    def _serve(self):
        path = self.path.split("?")[0]
        _Handler.hits[path] = _Handler.hits.get(path, 0) + 1
        _Handler.seen_headers[path] = dict(self.headers)
        seq = _Handler.script.get(path, [(200, {"ok": True})])
        status, body = seq.pop(0) if len(seq) > 1 else seq[0]
        if self.command == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            body = {"echo": json.loads(self.rfile.read(n) or b"null")}
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _serve
    do_POST = _serve

    def log_message(self, *a):
        pass


class TestHttpClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        _Handler.script.clear()
        _Handler.hits.clear()
        self.c = access_http.HttpClient(proxy="", backoff_base=0.01, default_rps=1000, tries=3,
                                        circuit_fails=3, circuit_cooldown=0.3, user_agent="ar-test/1")

    def test_5xx_retried_then_success_and_user_agent(self):
        _Handler.script["/flaky"] = [(503, {}), (500, {}), (200, {"v": 1})]
        self.assertEqual(self.c.get_json(self.base + "/flaky", params={"a": 1}), {"v": 1})
        self.assertEqual(_Handler.hits["/flaky"], 3)
        self.assertEqual(_Handler.seen_headers["/flaky"].get("User-Agent"), "ar-test/1")
        st = self.c.host_stats()["127.0.0.1"]
        self.assertEqual((st["http5xx"], st["retries"], st["ok"]), (2, 2, 1))

    def test_4xx_not_retried(self):
        _Handler.script["/nf"] = [(404, {"e": 1})]
        _Handler.script["/bad"] = [(400, {"e": 1})]
        with self.assertRaises(access_http.HttpError) as cm:
            self.c.get_json(self.base + "/nf")
        self.assertEqual(cm.exception.status, 404)
        with self.assertRaises(access_http.HttpError):
            self.c.get_json(self.base + "/bad")
        self.assertEqual((_Handler.hits["/nf"], _Handler.hits["/bad"]), (1, 1))

    def test_circuit_breaker_opens_then_half_open_probe(self):
        _Handler.script["/down"] = [(403, {})]
        for _ in range(3):
            with self.assertRaises(access_http.HttpError):
                self.c.get_json(self.base + "/down")
        with self.assertRaises(access_http.CircuitOpen):
            self.c.get_json(self.base + "/down")
        self.assertEqual(_Handler.hits["/down"], 3)               # fail fast: no 4th request
        time.sleep(0.35)
        _Handler.script["/up"] = [(200, {"ok": 1})]
        self.assertEqual(self.c.get_json(self.base + "/up"), {"ok": 1})   # probe succeeds, circuit closes
        self.assertEqual(self.c.circuit_state("127.0.0.1")["fails"], 0)

    def test_per_host_rate_limit_shared_across_threads(self):
        c = access_http.HttpClient(proxy="", host_rps={"127.0.0.1": 10})
        t0 = time.monotonic()
        ts = [threading.Thread(target=c.get_json, args=(self.base + "/x",)) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertGreaterEqual(time.monotonic() - t0, 0.29)       # 4 requests at 10 rps => >= 0.3s

    def test_post_json_and_timeout_transport_error(self):
        self.assertEqual(self.c.post_json(self.base + "/p", {"a": 1}), {"echo": {"a": 1}})
        c = access_http.HttpClient(proxy="", tries=2, backoff_base=0.01, timeout=0.5)
        with self.assertRaises(access_http.TransportError):
            c.get_json("http://127.0.0.1:9/nothing-listens-here")

    def test_proxy_configuration(self):
        c = access_http.HttpClient(proxy="http://127.0.0.1:7890")
        handlers = [h for h in c._opener.handlers if h.__class__.__name__ == "ProxyHandler"]
        self.assertEqual(handlers[0].proxies, {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"})


BIG = {"data": [{"id": i, "symbol": f"X{i:05d}", "name": "Tokenized asset " * 3} for i in range(9000)]}
BIG_BYTES = json.dumps(BIG).encode()                  # ~600 KB, like api.xstocks.fi/api/v2/public/assets


class _FlakyHandler(http.server.BaseHTTPRequestHandler):
    """Per-path list of modes; the last one repeats. Simulates a proxy cutting large bodies."""
    protocol_version = "HTTP/1.1"
    script = {}
    hits = {}
    seen_headers = {}

    def do_GET(self):
        path = self.path.split("?")[0]
        _FlakyHandler.hits[path] = _FlakyHandler.hits.get(path, 0) + 1
        _FlakyHandler.seen_headers[path] = dict(self.headers)
        seq = _FlakyHandler.script.get(path, ["ok"])
        mode = seq.pop(0) if len(seq) > 1 else seq[0]
        data = BIG_BYTES
        self.close_connection = True
        if mode == "disconnect":                       # no status line at all -> RemoteDisconnected
            return
        if mode == "reset":                            # RST instead of FIN -> ConnectionResetError
            import socket, struct
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            return
        if mode in ("gzip", "gzip_trunc"):
            import gzip as _gz
            data = _gz.compress(BIG_BYTES)
            if mode == "gzip_trunc":
                data = data[: len(data) // 2]          # Content-Length matches, but the gzip stream is cut
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if mode.startswith("gzip"):
            self.send_header("Content-Encoding", "gzip")
        if mode == "chunked_trunc":
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b"%x\r\n" % len(data) + data[:40000])     # chunk announced, then EOF
            return
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if mode == "trunc":
            self.wfile.write(data[:32768])                               # IncompleteRead(32768 bytes read, ...)
        elif mode == "zero":
            pass                                                         # 0 bytes read, N more expected
        elif mode == "stall":                                            # first bytes, then one long silence
            self.wfile.write(data[:1000])
            self.wfile.flush()
            time.sleep(1.5)
            try:
                self.wfile.write(data[1000:])
            except OSError:
                pass
        elif mode == "slow":                                             # each piece < timeout, total > timeout
            try:
                for i in range(0, len(data), len(data) // 4 + 1):
                    self.wfile.write(data[i:i + len(data) // 4 + 1])
                    self.wfile.flush()
                    time.sleep(0.25)
            except OSError:                                              # client gave up (deadline tests)
                pass
        else:
            self.wfile.write(data)

    def log_message(self, *a):
        pass


class TestHttpLargeBodies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FlakyHandler)
        cls.srv.daemon_threads = True
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        _FlakyHandler.script.clear()
        _FlakyHandler.hits.clear()
        self.sleeps = []
        self.c = access_http.HttpClient(proxy="", backoff_base=0.01, default_rps=1000, tries=3, timeout=2,
                                        circuit_fails=50, sleep=self.sleeps.append)

    def get(self, path):
        return self.c.get_json(self.base + path)

    def backoffs(self):
        return [x for x in self.sleeps if x >= 0.005]            # drop rate-limit waits (1000 rps -> <= 1 ms)

    def stats(self):
        return self.c.host_stats()["127.0.0.1"]

    def test_truncated_once_then_full_body(self):
        _FlakyHandler.script["/assets"] = ["trunc", "ok"]
        self.assertEqual(self.get("/assets"), BIG)
        self.assertEqual(_FlakyHandler.hits["/assets"], 2)
        st = self.stats()
        self.assertEqual((st["incomplete"], st["retries"], st["ok"]), (1, 1, 1))
        self.assertEqual(self.backoffs(), [0.01])                                # bounded backoff

    def test_zero_bytes_and_chunked_cut_and_disconnect_and_reset_are_retried(self):
        for mode in ("zero", "chunked_trunc", "disconnect", "reset"):
            _FlakyHandler.script["/" + mode] = [mode, "ok"]
            self.assertEqual(self.get("/" + mode), BIG, mode)
            self.assertEqual(_FlakyHandler.hits["/" + mode], 2, mode)
        self.assertEqual(self.stats()["incomplete"], 4)

    def test_always_truncated_gives_clear_error_after_bounded_tries(self):
        _FlakyHandler.script["/cut"] = ["trunc"]
        with self.assertRaises(access_http.TransportError) as cm:
            self.get("/cut")
        msg = str(cm.exception)
        self.assertIn(f"IncompleteBody: read 32768 of {len(BIG_BYTES)} bytes", msg)
        self.assertIn("after 3 attempts", msg)
        self.assertEqual(_FlakyHandler.hits["/cut"], 3)
        self.assertEqual(self.backoffs(), [0.01, 0.02])
        self.assertIsInstance(cm.exception.cause, access_http.IncompleteBody)

    def test_gzip_requested_and_decoded_truncated_gzip_retried(self):
        _FlakyHandler.script["/gz"] = ["gzip_trunc", "gzip"]
        self.assertEqual(self.get("/gz"), BIG)
        self.assertEqual(_FlakyHandler.seen_headers["/gz"].get("Accept-Encoding"), "gzip, deflate")
        self.assertEqual(_FlakyHandler.hits["/gz"], 2)

    def test_slow_large_body_not_cut_by_timeout(self):
        c = access_http.HttpClient(proxy="", tries=1, timeout=0.5, default_rps=1000)    # per-read timeout only
        _FlakyHandler.script["/slow"] = ["slow"]
        t0 = time.monotonic()
        self.assertEqual(c.get_json(self.base + "/slow"), BIG)
        self.assertGreater(time.monotonic() - t0, 0.75)                                  # total > timeout: fine

    def test_deadline_aborts_trickling_body_and_counts_as_one_try(self):
        _FlakyHandler.script["/slow"] = ["slow"]                                  # ~1 s total, pieces every 0.25 s
        c = access_http.HttpClient(proxy="", tries=1, timeout=2, default_rps=1000, circuit_fails=50)
        t0 = time.monotonic()
        with self.assertRaises(access_http.TransportError) as cm:
            c.get_json(self.base + "/slow", deadline=0.4)
        self.assertLess(time.monotonic() - t0, 0.9)
        self.assertIn("DeadlineExceeded", str(cm.exception))
        self.assertIn("after 1 attempt", str(cm.exception))
        self.assertEqual(_FlakyHandler.hits["/slow"], 1)
        self.assertEqual(c.host_stats()["127.0.0.1"]["timeout"], 1)
        # transient: retried when tries remain, each attempt gets its own deadline
        _FlakyHandler.script["/slow2"] = ["slow", "ok"]
        c2 = access_http.HttpClient(proxy="", tries=2, timeout=2, default_rps=1000, backoff_base=0.01)
        self.assertEqual(c2.get_json(self.base + "/slow2", deadline=0.4), BIG)
        self.assertEqual(_FlakyHandler.hits["/slow2"], 2)
        # generous deadline: unchanged behaviour
        _FlakyHandler.script["/slow3"] = ["slow"]
        self.assertEqual(c.get_json(self.base + "/slow3", deadline=5), BIG)

    def test_deadline_bounds_a_single_stalled_read(self):
        _FlakyHandler.script["/stall"] = ["stall"]
        c = access_http.HttpClient(proxy="", tries=1, timeout=5, default_rps=1000, circuit_fails=50)
        t0 = time.monotonic()
        with self.assertRaises(access_http.TransportError) as cm:
            c.get_text(self.base + "/stall", deadline=0.5)
        self.assertLess(time.monotonic() - t0, 1.2)                               # not the 5 s per-read timeout
        self.assertIn("DeadlineExceeded", str(cm.exception))

    def test_read_body_unit(self):
        class Resp:
            def __init__(self, data, headers, cut=None):
                self.data, self.headers, self.cut, self.pos = data, headers, cut, 0
            def read(self, n):
                end = min(self.pos + n, self.cut if self.cut is not None else len(self.data))
                b, self.pos = self.data[self.pos:end], end
                return b
        h = http.client.HTTPMessage()
        h["Content-Length"] = str(len(BIG_BYTES))
        self.assertEqual(access_http.read_body(Resp(BIG_BYTES, h), chunk=1000), BIG_BYTES)
        with self.assertRaises(access_http.IncompleteBody) as cm:
            access_http.read_body(Resp(BIG_BYTES, h, cut=179784))
        self.assertEqual((cm.exception.got, cm.exception.expected), (179784, len(BIG_BYTES)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
