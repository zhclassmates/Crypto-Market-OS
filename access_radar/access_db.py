"""access.sqlite connection + single-writer path for the Access Radar runner.

- DB_PATH = env ACCESS_DB (legacy fallback ACCESS_RADAR_DB) or <this dir>/access.sqlite (not cwd-relative)
- connect(): WAL, busy_timeout, foreign keys, applies schema.sql (radar_core) + the runner tables below.
- Writer: ONE thread owns ONE write connection; every adapter thread submits write jobs to its queue,
  so all writes are serialized through one path (no "database is locked" between adapter threads).
  Reads (status / feed / UI) open their own connections; WAL lets them run concurrently.
- with_db(fn): lock-based one-shot helper for code outside the runner (CLI / ops scripts), same as
  rh_v2 market_lanes.with_db. Inside the runner always use the Writer.

Runner tables use UTC milliseconds like radar_core. They live here (not in schema.sql) so the core schema
stays the domain model; they are created by connect().
"""
import os
import queue
import sqlite3
import threading
import time
from concurrent.futures import Future

import logging

import radar_core as rc

log = logging.getLogger("access_radar.db")
SLOW_JOB_SEC = 5.0

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = rc.default_db_path()          # env ACCESS_DB (fallback ACCESS_RADAR_DB), else <access_radar>/access.sqlite
BUSY_TIMEOUT_MS = 30000

RUNNER_SCHEMA = """
-- One row per scheduled source (collector view: did the adapter run, did it succeed, how fresh is it).
-- Domain health (HEALTHY/DEGRADED/DOWN, baseline, snapshot size) stays in radar_core's source_health.
CREATE TABLE IF NOT EXISTS source_run (
    source_id           TEXT PRIMARY KEY,
    kind                TEXT NOT NULL DEFAULT '',     -- snapshot / announcement / stream
    module              TEXT NOT NULL DEFAULT '',
    period_sec          REAL NOT NULL DEFAULT 0,
    adapter_state       TEXT NOT NULL DEFAULT 'unknown', -- ok / missing / error / no_source / disabled
    adapter_note        TEXT NOT NULL DEFAULT '',
    collector_heartbeat INTEGER,
    last_attempt        INTEGER,                      -- request start
    last_success        INTEGER,                      -- request finish of last good run
    round_ok            INTEGER NOT NULL DEFAULT 0,
    latency_ms          INTEGER,
    consecutive_errors  INTEGER NOT NULL DEFAULT 0,
    last_error          TEXT NOT NULL DEFAULT '',
    attempts            INTEGER NOT NULL DEFAULT 0,
    successes           INTEGER NOT NULL DEFAULT 0,
    rows_received       INTEGER NOT NULL DEFAULT 0,
    events_written      INTEGER NOT NULL DEFAULT 0,
    last_event_at       INTEGER,
    connected           INTEGER NOT NULL DEFAULT 0,   -- streams only
    last_heartbeat      INTEGER,                      -- streams only
    heartbeat_sec       REAL NOT NULL DEFAULT 0,
    updated_at          INTEGER
) STRICT;

CREATE TABLE IF NOT EXISTS runner_meta (k TEXT PRIMARY KEY, v TEXT) STRICT;

-- Maintenance jobs (identity resolution ...). Not data sources: no source / source_health rows.
CREATE TABLE IF NOT EXISTS maintenance_run (
    job_id             TEXT PRIMARY KEY,
    module             TEXT NOT NULL DEFAULT '',
    period_sec         REAL NOT NULL DEFAULT 0,
    job_state          TEXT NOT NULL DEFAULT 'unknown',   -- ok / missing / error / disabled
    job_note           TEXT NOT NULL DEFAULT '',
    last_attempt       INTEGER,
    last_success       INTEGER,
    round_ok           INTEGER NOT NULL DEFAULT 0,
    latency_ms         INTEGER,
    consecutive_errors INTEGER NOT NULL DEFAULT 0,
    last_error         TEXT NOT NULL DEFAULT '',
    attempts           INTEGER NOT NULL DEFAULT 0,
    successes          INTEGER NOT NULL DEFAULT 0,
    last_result        TEXT NOT NULL DEFAULT '',          -- JSON of the last run's result (also on failure)
    updated_at         INTEGER
) STRICT;
"""

FAIL_THRESHOLD = 3


def now_ms():
    return int(time.time() * 1000)


def connect(path=None):
    """Open access.sqlite, create/upgrade schema. Safe to call from any thread (one connection per thread)."""
    conn = rc.connect(path or DB_PATH)
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    rc.init_db(conn)
    conn.executescript(RUNNER_SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn


DB_LOCK = threading.Lock()


def with_db(fn, path=None):
    """One-shot locked write outside the runner (CLI, ops). fn(conn) -> result."""
    with DB_LOCK:
        conn = connect(path)
        try:
            return fn(conn)
        finally:
            conn.close()


class WriterStopped(RuntimeError):
    pass


class Writer:
    """Single writer thread. submit(fn, *a, **kw) -> Future; call(...) blocks for the result.

    fn receives the writer's connection as first argument: fn(conn, *a, **kw).
    Exceptions raised by fn are delivered to the caller through the Future; the writer keeps running.
    """

    _STOP = object()

    def __init__(self, path=None, name="access-writer"):
        self.path = path or DB_PATH
        self.name = name
        self._q = queue.Queue()
        self._thread = None
        self._ready = threading.Event()
        self._init_error = None
        self.thread_ident = None
        self.jobs_done = 0
        self.jobs_failed = 0

    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._init_error:
            raise self._init_error
        return self

    def _run(self):
        try:
            conn = connect(self.path)
        except Exception as e:      # surface schema / path errors to start()
            self._init_error = e
            self._ready.set()
            return
        self.thread_ident = threading.get_ident()
        self._ready.set()
        try:
            while True:
                job = self._q.get()
                if job is self._STOP:
                    break
                fut, fn, a, kw = job
                if not fut.set_running_or_notify_cancel():
                    continue
                t0 = time.monotonic()
                try:
                    res = fn(conn, *a, **kw)
                except BaseException as e:
                    if conn.in_transaction:
                        conn.rollback()
                    self.jobs_failed += 1
                    fut.set_exception(e)
                else:
                    if conn.in_transaction:
                        conn.commit()
                    self.jobs_done += 1
                    fut.set_result(res)
                held = time.monotonic() - t0
                if held > SLOW_JOB_SEC:
                    log.warning("writer job %s held the writer for %.1fs", getattr(fn, "__name__", fn), held)
        finally:
            conn.close()
            # fail anything still queued
            while True:
                try:
                    job = self._q.get_nowait()
                except queue.Empty:
                    break
                if job is not self._STOP:
                    job[0].set_exception(WriterStopped("writer stopped"))

    @property
    def alive(self):
        return bool(self._thread and self._thread.is_alive())

    def submit(self, fn, *a, **kw):
        if not self.alive:
            raise WriterStopped("writer not running")
        fut = Future()
        self._q.put((fut, fn, a, kw))
        return fut

    def call(self, fn, *a, timeout=None, **kw):
        if threading.get_ident() == self.thread_ident:      # re-entrant call from inside a job
            raise RuntimeError("Writer.call from the writer thread would deadlock; call fn(conn) directly")
        return self.submit(fn, *a, **kw).result(timeout)

    def stop(self, timeout=10):
        if self.alive:
            self._q.put(self._STOP)
            self._thread.join(timeout)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


# ----------------------------------------------------------------------------- runner bookkeeping
def meta_set(conn, k, v):
    conn.execute("INSERT INTO runner_meta(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


def meta_get(conn, k, default=None):
    r = conn.execute("SELECT v FROM runner_meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else default


def ensure_source_run(conn, source_id, kind="", module="", period_sec=0, adapter_state="unknown", note="",
                      heartbeat_sec=0):
    conn.execute(
        """INSERT INTO source_run(source_id, kind, module, period_sec, adapter_state, adapter_note, heartbeat_sec,
               updated_at) VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(source_id) DO UPDATE SET kind=excluded.kind, module=excluded.module,
               period_sec=excluded.period_sec, adapter_state=excluded.adapter_state,
               adapter_note=excluded.adapter_note, heartbeat_sec=excluded.heartbeat_sec, updated_at=excluded.updated_at""",
        (source_id, kind, module, float(period_sec or 0), adapter_state, note[:400], float(heartbeat_sec or 0), now_ms()))


def touch_heartbeat(conn, at=None):
    at = at or now_ms()
    conn.execute("UPDATE source_run SET collector_heartbeat=? WHERE adapter_state='ok'", (at,))
    meta_set(conn, "collector_heartbeat", at)


def record_run(conn, source_id, ok, started_ms, finished_ms, rows=0, events=0, error=None):
    """Same contract as rh_v2 market_health.record_result: failures touch only last_attempt /
    consecutive_errors / last_error, never last_success."""
    latency = max(0, int(finished_ms - started_ms))
    if ok:
        conn.execute(
            """UPDATE source_run SET last_attempt=?, last_success=?, round_ok=1, latency_ms=?,
                   consecutive_errors=0, last_error=?, attempts=attempts+1, successes=successes+1,
                   rows_received=?, events_written=events_written+?,
                   last_event_at=CASE WHEN ?>0 THEN ? ELSE last_event_at END, updated_at=?
               WHERE source_id=?""",
            (int(started_ms), int(finished_ms), latency, (str(error)[:400] if error else ""), int(rows), int(events),
             int(events), int(finished_ms), int(finished_ms), source_id))
    else:
        conn.execute(
            """UPDATE source_run SET last_attempt=?, round_ok=0, latency_ms=?, consecutive_errors=consecutive_errors+1,
                   last_error=?, attempts=attempts+1, updated_at=? WHERE source_id=?""",
            (int(started_ms), latency, (str(error or "error"))[:400], int(finished_ms), source_id))


def set_stream_state(conn, source_id, connected=None, heartbeat_at=None, events=0, error=None):
    at = now_ms()
    sets, args = ["updated_at=?"], [at]
    if connected is not None:
        sets.append("connected=?")
        args.append(1 if connected else 0)
        if connected:
            sets += ["last_success=?", "round_ok=1", "consecutive_errors=0", "successes=successes+1",
                     "attempts=attempts+1", "last_attempt=?"]
            args += [at, at]
        else:
            sets += ["round_ok=0", "consecutive_errors=consecutive_errors+1"]
    if heartbeat_at is not None:
        sets += ["last_heartbeat=?", "last_success=?"]
        args += [heartbeat_at, heartbeat_at]
    if events:
        sets += ["events_written=events_written+?", "last_event_at=?"]
        args += [int(events), at]
    if error is not None:
        sets.append("last_error=?")
        args.append(str(error)[:400])
    conn.execute(f"UPDATE source_run SET {', '.join(sets)} WHERE source_id=?", (*args, source_id))


def ensure_maintenance_run(conn, job_id, module="", period_sec=0, job_state="unknown", note=""):
    conn.execute(
        """INSERT INTO maintenance_run(job_id, module, period_sec, job_state, job_note, updated_at) VALUES (?,?,?,?,?,?)
           ON CONFLICT(job_id) DO UPDATE SET module=excluded.module, period_sec=excluded.period_sec,
               job_state=excluded.job_state, job_note=excluded.job_note, updated_at=excluded.updated_at""",
        (job_id, module, float(period_sec or 0), job_state, note[:400], now_ms()))


def record_maintenance(conn, job_id, ok, started_ms, finished_ms, error=None, result=None):
    import json
    res = json.dumps(result, ensure_ascii=False, default=str)[:4000] if result is not None else ""
    latency = max(0, int(finished_ms - started_ms))
    if ok:
        conn.execute(
            """UPDATE maintenance_run SET last_attempt=?, last_success=?, round_ok=1, latency_ms=?, consecutive_errors=0,
                   last_error='', attempts=attempts+1, successes=successes+1, last_result=?, updated_at=?
               WHERE job_id=?""", (int(started_ms), int(finished_ms), latency, res, int(finished_ms), job_id))
    else:
        conn.execute(
            """UPDATE maintenance_run SET last_attempt=?, round_ok=0, latency_ms=?, consecutive_errors=consecutive_errors+1,
                   last_error=?, attempts=attempts+1, last_result=CASE WHEN ?<>'' THEN ? ELSE last_result END,
                   updated_at=? WHERE job_id=?""",
            (int(started_ms), latency, str(error or "error")[:400], res, res, int(finished_ms), job_id))


def classify_maintenance(now, row):
    """Same clock rules as polling sources, keyed on job_state."""
    d = dict(row)
    d.update(adapter_state=d["job_state"], kind="maintenance", connected=0, heartbeat_sec=0)
    return classify_status(now, d)


def classify_status(now, row):
    """Clock status computed at read time (rh_v2 classify_status semantics + adapter states + streams).

    MISSING/ERROR/NO_SOURCE/DISABLED: adapter not runnable.  Polling: FAILED (>=3 errors, never succeeded),
    STALE (no success / last round failed / age > 2*period+2s), DELAYED (age > period+2s), LIVE.
    Streams: LIVE (connected, heartbeat fresh), DELAYED (connected, heartbeat late), DOWN (disconnected).
    """
    state = row["adapter_state"]
    if state != "ok":
        return state.upper()
    errors = int(row["consecutive_errors"] or 0)
    if row["kind"] == "stream":
        if not row["connected"]:
            return "FAILED" if errors >= FAIL_THRESHOLD and not row["successes"] else "DOWN"
        hb = row["last_heartbeat"] or row["last_success"]
        limit = (row["heartbeat_sec"] or 60) * 1000
        if hb and now - hb > limit:
            return "DELAYED"
        return "LIVE"
    period = (row["period_sec"] or 60) * 1000
    if errors >= FAIL_THRESHOLD and not row["successes"]:
        return "FAILED"
    if not row["last_success"] or not row["round_ok"]:
        return "STALE"
    age = now - row["last_success"]
    if age > 2 * period + 2000:
        return "STALE"
    if age > period + 2000:
        return "DELAYED"
    return "LIVE"
