#!/usr/bin/env python3
"""Access Radar collector entry point (launchd KeepAlive + manual modes).

  python3 access_run.py loop                    resident: one thread per source, streams with reconnect
  python3 access_run.py once                    every polling adapter once, then tick, then exit
  python3 access_run.py status [--json]         per source: adapter state, clock status, radar health, gaps
  python3 access_run.py feed --window 24h [--json]   recent canonical events (1h|6h|24h|3d|7d)
  python3 access_run.py tick                    apply official delistings whose effective_at has passed
  python3 access_run.py maintenance [job ...]   run maintenance jobs once (default: all, e.g. resolve)

Options: --db PATH (default env ACCESS_DB, legacy fallback ACCESS_RADAR_DB, else access_radar/access.sqlite).
loop/once hold a file lock (env ACCESS_LOCK, default logs/access_collector.lock): a second instance exits.
Logs go to logs/access.log (env ACCESS_LOG_DIR) and stderr.
"""
import argparse
import fcntl
import importlib.util
import json
import logging
import logging.handlers
import os
import signal
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import radar_core as rc          # noqa: E402
import access_db                 # noqa: E402
import access_sched              # noqa: E402

LOG_DIR = os.environ.get("ACCESS_LOG_DIR", os.path.join(HERE, "logs"))
LOCK_PATH = os.environ.get("ACCESS_LOCK", os.path.join(LOG_DIR, "access_collector.lock"))
LOCK_BUSY_SLEEP = float(os.environ.get("ACCESS_LOCK_BUSY_SLEEP", "20"))
WINDOWS = ("1h", "6h", "24h", "3d", "7d")

log = logging.getLogger("access_radar.run")


class LockBusy(Exception):
    """Another collector already holds the lock."""


def acquire_lock(path=None):
    """Non-blocking fcntl lock (rh_v2 market_collect.acquire_lock). Raises LockBusy."""
    path = path or LOCK_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = open(path, "a+")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fd.close()
        raise LockBusy(path)
    fd.seek(0)
    fd.truncate()
    fd.write(str(os.getpid()))
    fd.flush()
    return fd


def release_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        fd.close()


def setup_logging(to_file=True, level=None):
    level = level or os.environ.get("ACCESS_LOG_LEVEL", "INFO")
    root = logging.getLogger("access_radar")
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s")
    if not any(isinstance(h, logging.StreamHandler) and getattr(h, "_access", False) for h in root.handlers):
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        sh._access = True
        root.addHandler(sh)
    if to_file and not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        os.makedirs(LOG_DIR, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(os.path.join(LOG_DIR, "access.log"), maxBytes=10 * 1024 * 1024,
                                                  backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)


def _make_runner(db, catalog=None, http=None, discover_package="adapters", stop_event=None):
    import access_http
    import access_sched
    writer = access_db.Writer(db).start()
    runner = access_sched.Runner(writer, http or access_http.HttpClient(), catalog=catalog,
                                 discover_package=discover_package, stop_event=stop_event)
    return writer, runner


def cmd_once(db, catalog=None, http=None, discover_package="adapters", lock_path=None, out=None):
    out = out or sys.stdout
    try:
        lock = acquire_lock(lock_path)
    except LockBusy:
        log.warning("another collector holds the lock; exiting")
        out.write(json.dumps({"skipped": True, "reason": "lock_busy"}) + "\n")
        return {"skipped": True, "reason": "lock_busy"}
    try:
        writer, runner = _make_runner(db, catalog, http, discover_package)
        try:
            runner.prepare()
            results = runner.run_once()
            due = writer.call(lambda conn: rc.process_due(conn))
            writer.call(access_db.touch_heartbeat)
            writer.call(access_db.meta_set, "last_once_at", rc.now_ms())
        finally:
            writer.stop()
        # streams are not failures in once mode: report them under "skipped" (state stream_loop_only)
        streams = [r for r in results if r.get("skipped") == "stream"]
        polled = [r for r in results if r.get("skipped") != "stream"]
        summary = {"ok": True, "ts": rc.now_ms(), "sources": polled, "scheduled_removals": len(due),
                   "skipped": [{"source_id": r.entry.source_id, "state": r.state, "note": r.note}
                               for r in runner.loaded if not r.spec]
                   + [{"source_id": r["source_id"], "state": "stream_loop_only",
                       "note": "streams only run in loop mode (access_run.py loop)"} for r in streams]}
        out.write(json.dumps(summary, ensure_ascii=False, default=str) + "\n")
        return summary
    finally:
        release_lock(lock)


def cmd_maintenance(db, jobs=None, catalog=None, http=None, lock_path=None, out=None):
    """Run maintenance jobs once. Takes the collector lock: if the loop is running it already runs them hourly."""
    out = out or sys.stdout
    try:
        lock = acquire_lock(lock_path)
    except LockBusy:
        msg = ("collector loop is running and owns the writer; it runs maintenance jobs on schedule. "
               "Stop it (launchctl bootout gui/$(id -u)/com.access.collector) to run them manually.")
        log.warning(msg)
        out.write(json.dumps({"skipped": True, "reason": "lock_busy", "message": msg}) + "\n")
        return {"skipped": True, "reason": "lock_busy"}
    try:
        writer, runner = _make_runner(db, catalog, http, None)
        try:
            runner.prepare_maintenance()
            known = {r.entry.source_id: r for r in runner.maint_loaded}
            wanted = list(jobs) if jobs else list(known)
            unknown = [j for j in wanted if j not in known]
            if unknown:
                raise SystemExit(f"unknown maintenance job(s): {', '.join(unknown)} (have: {', '.join(known) or 'none'})")
            results, skipped = [], []
            for j in wanted:
                r = known[j]
                if r.spec:
                    results.append(runner.run_maintenance(r.spec))
                else:
                    log.info("skip maintenance %s: %s", j, r.note)
                    skipped.append({"job_id": j, "state": r.state, "note": r.note})
        finally:
            writer.stop()
        summary = {"ok": all(r["ok"] for r in results), "ts": rc.now_ms(), "jobs": results, "skipped": skipped}
        out.write(json.dumps(summary, ensure_ascii=False, default=str) + "\n")
        return summary
    finally:
        release_lock(lock)


def cmd_loop(db, catalog=None, http=None, discover_package="adapters", lock_path=None, stop_event=None,
             heartbeat_every=5.0, tick_every=60.0, lock_busy_sleep=None):
    try:
        lock = acquire_lock(lock_path)
    except LockBusy:
        wait = LOCK_BUSY_SLEEP if lock_busy_sleep is None else lock_busy_sleep
        log.warning("another collector holds the lock; sleeping %ss so launchd does not spin", wait)
        time.sleep(wait)
        return {"skipped": True, "reason": "lock_busy"}
    stop_event = stop_event or threading.Event()

    def on_signal(signum, _frame):
        log.info("signal %s: stopping", signum)
        stop_event.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, on_signal)
        signal.signal(signal.SIGINT, on_signal)
    try:
        writer, runner = _make_runner(db, catalog, http, discover_package, stop_event)
        try:
            runner.prepare()
            writer.call(access_db.meta_set, "loop_started_at", rc.now_ms())
            log.info("loop started pid=%s db=%s", os.getpid(), db)
            runner.run_forever(heartbeat_every=heartbeat_every, tick_every=tick_every)
        finally:
            writer.stop()
        return {"stopped": True}
    finally:
        release_lock(lock)


def _age_s(now, ts):
    return None if not ts else round((now - ts) / 1000, 1)


def status_payload(conn, now=None):
    now = now or rc.now_ms()
    health = {}
    for r in conn.execute("SELECT * FROM source_health ORDER BY source_id, scope"):
        health.setdefault(r["source_id"], []).append({
            "scope": r["scope"], "status": r["status"], "baseline_done": bool(r["baseline_done"]),
            "last_snapshot_size": r["last_snapshot_size"], "schema_ok": bool(r["schema_ok"]),
            "last_ok_age_sec": _age_s(now, r["last_ok_at"]), "last_error": r["last_error"]})
    gaps = {}
    for r in conn.execute("SELECT * FROM source_disconnect ORDER BY started_at DESC"):
        gaps.setdefault(r["source_id"], []).append({
            "started_at": r["started_at"], "ended_at": r["ended_at"], "reason": r["reason"],
            "backfilled": bool(r["backfilled"])})
    sources = []
    for r in conn.execute("SELECT * FROM source_run ORDER BY adapter_state <> 'ok', source_id"):
        sid = r["source_id"]
        sources.append({
            "source_id": sid, "kind": r["kind"], "module": r["module"], "period_sec": r["period_sec"],
            "adapter_state": r["adapter_state"], "adapter_note": r["adapter_note"],
            "status": access_db.classify_status(now, r),
            "last_attempt": r["last_attempt"], "last_success": r["last_success"],
            "api_age_sec": _age_s(now, r["last_success"]), "latency_ms": r["latency_ms"],
            "consecutive_errors": r["consecutive_errors"], "last_error": r["last_error"],
            "attempts": r["attempts"], "successes": r["successes"], "rows_received": r["rows_received"],
            "events_written": r["events_written"], "last_event_at": r["last_event_at"],
            "connected": bool(r["connected"]) if r["kind"] == "stream" else None,
            "radar_health": health.get(sid, []),
            "open_gaps": [g for g in gaps.get(sid, []) if g["ended_at"] is None],
            "recent_gaps": gaps.get(sid, [])[:5]})
    # catalogued sources the collector has not seen yet (never started): resolve without importing
    known = {s["source_id"] for s in sources}
    for e in access_sched.CATALOG:
        if e.source_id in known or e.kind == "maintenance":
            continue
        try:
            found = importlib.util.find_spec(e.module) is not None
        except (ImportError, ValueError):
            found = False
        state = "not_started" if found else "missing"
        sources.append({"source_id": e.source_id, "kind": "", "module": e.module, "period_sec": e.period_sec,
                        "adapter_state": state, "adapter_note": e.note if found else f"{e.module} not written yet",
                        "status": state.upper(), "last_attempt": None, "last_success": None, "api_age_sec": None,
                        "latency_ms": None, "consecutive_errors": 0, "last_error": "", "attempts": 0,
                        "successes": 0, "rows_received": 0, "events_written": 0, "last_event_at": None,
                        "connected": None, "radar_health": health.get(e.source_id, []), "open_gaps": [],
                        "recent_gaps": []})
    maintenance = []
    for r in conn.execute("SELECT * FROM maintenance_run ORDER BY job_id"):
        try:
            last_result = json.loads(r["last_result"]) if r["last_result"] else None
        except ValueError:
            last_result = r["last_result"]
        maintenance.append({
            "job_id": r["job_id"], "module": r["module"], "period_sec": r["period_sec"], "job_state": r["job_state"],
            "job_note": r["job_note"], "status": access_db.classify_maintenance(now, r),
            "last_attempt": r["last_attempt"], "last_success": r["last_success"],
            "age_sec": _age_s(now, r["last_success"]), "latency_ms": r["latency_ms"],
            "consecutive_errors": r["consecutive_errors"], "last_error": r["last_error"],
            "attempts": r["attempts"], "successes": r["successes"], "last_result": last_result})
    have = {m["job_id"] for m in maintenance}
    for e in access_sched.CATALOG:
        if e.kind != "maintenance" or e.source_id in have:
            continue
        try:
            found = importlib.util.find_spec(e.module) is not None
        except (ImportError, ValueError):
            found = False
        st = "not_started" if found else "missing"
        maintenance.append({"job_id": e.source_id, "module": e.module, "period_sec": e.period_sec, "job_state": st,
                            "job_note": e.note if found else f"{e.module} not found", "status": st.upper(),
                            "last_attempt": None, "last_success": None, "age_sec": None, "latency_ms": None,
                            "consecutive_errors": 0, "last_error": "", "attempts": 0, "successes": 0,
                            "last_result": None})
    hb = access_db.meta_get(conn, "collector_heartbeat")
    return {"now": now, "collector_heartbeat": int(hb) if hb else None,
            "collector_age_sec": _age_s(now, int(hb)) if hb else None, "sources": sources,
            "maintenance": maintenance}


def cmd_status(db, as_json=False, out=None):
    out = out or sys.stdout
    conn = access_db.connect(db)
    try:
        p = status_payload(conn)
    finally:
        conn.close()
    if as_json:
        out.write(json.dumps(p, ensure_ascii=False, indent=2) + "\n")
        return p
    hb = "—" if p["collector_heartbeat"] is None else f"{rc.fmt_ts(p['collector_heartbeat'])} {rc.LOCAL_LABEL} ({p['collector_age_sec']}s ago)"
    out.write(f"Access Radar collector  heartbeat {hb}\n")
    out.write(f"{'source':<18} {'kind':<12} {'status':<9} {'period':>7} {'api':>7} {'err':>4} {'events':>6}  note\n")
    for s in p["sources"]:
        api = "—" if s["api_age_sec"] is None else f"{s['api_age_sec']:.0f}"
        note = (s["last_error"] or s["adapter_note"] or "").replace("\n", " ")[:70]
        out.write(f"{s['source_id'][:18]:<18} {(s['kind'] or '-')[:12]:<12} {s['status'][:9]:<9} "
                  f"{s['period_sec']:>7g} {api:>7} {s['consecutive_errors']:>4} {s['events_written']:>6}  {note}\n")
        for h in s["radar_health"]:
            out.write(f"    scope {h['scope']:<12} {h['status']:<9} size={h['last_snapshot_size']} "
                      f"baseline={'yes' if h['baseline_done'] else 'no'} {h['last_error'][:60]}\n")
        for g in s["open_gaps"]:
            out.write(f"    DISCONNECTED since {rc.fmt_ts(g['started_at'])} {rc.LOCAL_LABEL}: {g['reason'][:60]}\n")
    out.write("\nmaintenance (not data sources)\n")
    out.write(f"{'job':<18} {'status':<11} {'period':>7} {'age':>7} {'err':>4}  last result / error\n")
    for m in p["maintenance"]:
        age = "—" if m["age_sec"] is None else f"{m['age_sec']:.0f}"
        res = m["last_error"] or (json.dumps(m["last_result"], ensure_ascii=False, default=str)
                                  if m["last_result"] is not None else m["job_note"])
        out.write(f"{m['job_id'][:18]:<18} {m['status'][:11]:<11} {m['period_sec']:>7g} {age:>7} "
                  f"{m['consecutive_errors']:>4}  {str(res).replace(chr(10), ' ')[:90]}\n")
    return p


def cmd_feed(db, window="24h", as_json=False, out=None):
    if window not in WINDOWS:
        raise SystemExit(f"--window must be one of {', '.join(WINDOWS)}")
    conn = access_db.connect(db)
    try:
        return rc.print_feed(conn, window, out=out or sys.stdout, as_json=as_json)
    finally:
        conn.close()


def cmd_tick(db, out=None):
    out = out or sys.stdout
    done = access_db.with_db(lambda conn: rc.process_due(conn), db)
    out.write(f"applied {len(done)} scheduled removals\n")
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(prog="access_run.py", description="Access Radar collector")
    ap.add_argument("--db", default=None, help="database path (default env ACCESS_DB, fallback ACCESS_RADAR_DB, else access_radar/access.sqlite)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("once")
    sub.add_parser("loop")
    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true")
    fd = sub.add_parser("feed")
    fd.add_argument("--window", default="24h", choices=WINDOWS)
    fd.add_argument("--json", action="store_true")
    sub.add_parser("tick")
    mt = sub.add_parser("maintenance", help="run maintenance jobs once (default: all)")
    mt.add_argument("jobs", nargs="*", help="job ids, e.g. resolve")
    a = ap.parse_args(argv)
    db = a.db or rc.default_db_path()
    if a.cmd in ("once", "loop", "tick", "maintenance"):
        setup_logging(to_file=True)
    else:
        setup_logging(to_file=False, level="WARNING")
    if a.cmd == "once":
        cmd_once(db)
    elif a.cmd == "loop":
        cmd_loop(db)
    elif a.cmd == "status":
        cmd_status(db, as_json=a.json)
    elif a.cmd == "feed":
        cmd_feed(db, a.window, as_json=a.json)
    elif a.cmd == "tick":
        cmd_tick(db)
    elif a.cmd == "maintenance":
        try:
            res = cmd_maintenance(db, a.jobs)
        except SystemExit as e:
            if isinstance(e.code, str):
                sys.stderr.write(e.code + "\n")
                return 2
            raise
        if res.get("skipped"):
            return 3
        return 0 if res.get("ok") else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
