"""Access Radar scheduler: CATALOG, adapter loading, one thread per source, stream supervision.

ADAPTER INTERFACE (authoritative copy is at the top of README.md)
------------------------------------------------------------------
An adapter is a module under access_radar/adapters/. It never touches the database: it returns
items / announcements and the runner writes them through the single Writer into radar_core.

Single-source module (module-level attributes):
    SOURCE_ID = "upbit_market"
    KIND      = "snapshot" | "announcement" | "stream"
    PERIOD_SEC = 30                 # optional; CATALOG period wins when the source is catalogued
    PLATFORMS = [{"platform_id": "upbit", "name": "Upbit", "platform_type": "CEX", "country": "KR"}]  # optional
    SOURCE    = {"tier": "OFFICIAL_STRUCTURED", "origin_platform_id": "upbit", ...}  # radar_core.register_source kwargs
    HEARTBEAT_SEC = 60              # streams: watchdog asks for reconnect if no ctx.heartbeat() for this long
    def fetch(http): ...            # snapshot / announcement
    def run(ctx): ...               # stream
    def backfill(http, since_ms, until_ms): ...   # optional: announcements for a disconnect gap; raise on failure.
        # Called on every reconnect for closed gaps with source_disconnect.backfilled=0 (oldest first, BACKFILL_BATCH
        # per round, gaps that ended < BACKFILL_MAX_AGE_SEC ago) and retried every BACKFILL_RETRY_SEC by the
        # access-backfill thread until it succeeds (backfilled=1). A failure is written to source_run.last_error and
        # source_health.last_error ("backfill failed for gap ...") and cleared once no gap is pending.

Multi-source module: SOURCES = {"upbit_market": {"kind": "snapshot", "fetch": fetch_markets, ...},
                                "upbit_notice": {"kind": "stream", "run": run_notice_ws, "backfill": ...}}
with the same keys in lower case (kind, fetch, run, backfill, period_sec, platforms, source, heartbeat_sec).

Return values:
    snapshot      fetch(http) -> {scope: [item, ...]}   (a plain list means scope "default")
                  each item is a radar_core snapshot item dict; a scope value may be an Exception instance
                  -> that scope is reported DOWN (radar_core.report_fetch_error) without touching others.
                  Each scope must be the COMPLETE list for that scope (missing items count as misses).
    announcement  fetch(http) -> [announcement dict, ...]   (radar_core.ingest_announcement format;
                  source_event_id must be stable -> re-polling the same notice is idempotent)
    stream        run(ctx) blocks while connected; return or raise when the connection is lost.
                  ctx.connected()            call once the connection/subscription is up
                  ctx.heartbeat()            call on every message / pong
                  ctx.should_stop()          poll in the receive loop (stop requested or heartbeat watchdog)
                  ctx.emit_announcement(ann) / ctx.emit_snapshot(scope, items)
                  ctx.http, ctx.source_id, ctx.log, ctx.stop_event
Raising from fetch() marks the run failed (source_run) and reports the source's scopes DOWN.

Conn-style adapters (also supported; this is what adapters/ramp.py and adapters/xstocks.py use):
    SOURCE_ID = "ramp_assets"                       (no KIND)
    def register(conn, at=None): ...                optional; registers platform + source
    def run_once(conn, fetch=None, fetched_at=None) -> {scope: ingest result | {"error": msg}}
  The runner passes fetch(url, headers=None) -> parsed JSON backed by the shared HttpClient. To keep the
  single writer free during network I/O, the runner first runs run_once against a throw-away in-memory DB
  in the source thread while recording every fetch (network happens here), then replays it on the real DB
  inside the writer with the recorded responses (no network in the writer). SOURCES entries may use the
  same "run_once" / "register" keys.

MAINTENANCE JOBS (CATALOG entries with kind="maintenance", e.g. identity resolution)
------------------------------------------------------------------
Not data sources: no `source` row, no radar source_health; runs are recorded in `maintenance_run` and shown
in a separate "maintenance" section of `access_run.py status`. One thread per job, period from start.
Two phases so the network never runs inside the single writer:
    prepare(http) -> payload        job thread: network only, no DB
    apply(conn, payload) -> dict    writer thread: all DB reads/writes
A module provides module-level prepare/apply, or access_sched.MAINTENANCE_SHIMS maps it (resolve.py is
mapped: prepare = resolve.fetch_alpha(http); apply = resolve.register_alpha + resolve.resolve_pending).
A result dict with a non-empty key ending in "error" counts as a failed run (the result is still stored).
Missing module -> skipped with a log line.  Manual run: `access_run.py maintenance [job ...]`.
"""
import importlib
import json
import importlib.util
import logging
import os
import pkgutil
import sys
import threading
import time
from dataclasses import dataclass, field

import radar_core as rc
import access_db

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

log = logging.getLogger("access_radar.sched")

KINDS = ("snapshot", "announcement", "stream")
STREAM_BACKOFF = (1.0, 30.0)          # reconnect backoff: 1s doubling, capped at 30s
STREAM_STABLE_SEC = 60.0              # a connection that lived this long resets the backoff
HEARTBEAT_WRITE_EVERY = 5.0           # at most one heartbeat DB write per stream every N seconds
BACKFILL_RETRY_SEC = 300.0            # retry failed gap backfills (source_disconnect.backfilled=0) every 5 min
BACKFILL_MAX_AGE_SEC = 7 * 86400      # gaps that ended longer ago than this are no longer retried
BACKFILL_BATCH = 3                    # at most N gaps per source per round, oldest first
BACKFILL_ERROR_PREFIX = "backfill failed"
DEFAULT_HEARTBEAT_SEC = 60.0


class AllScopesFailed(Exception):
    """Every scope of a snapshot source failed this round (run counted as failed)."""


@dataclass
class Entry:
    source_id: str
    period_sec: float          # polling period, measured from request start; streams: 0
    module: str                # import path relative to access_radar/, e.g. "adapters.upbit"
    note: str = ""
    enabled: bool = True
    kind: str = "source"       # "source" (adapter) or "maintenance" (job; source_id is then the job id)


# Periods per the agreed spec. Module files that don't exist yet are skipped with a log line.
CATALOG = [
    # --- Korea (step 2)
    Entry("upbit_market", 30, "adapters.upbit", "GET /v1/market/all, 10 req/s"),
    Entry("upbit_notice", 0, "adapters.upbit", "announcement WS (JWT, no replay) or REST poll"),
    Entry("bithumb_market", 30, "adapters.bithumb", "market list"),
    Entry("bithumb_notice", 2, "adapters.bithumb", "/v1/notices, 1 req/s/IP, 20 items, no id"),
    Entry("coinone_market", 30, "adapters.coinone", "/public/v2/markets/KRW trade_status/maintenance_status"),
    Entry("korbit_pairs", 60, "adapters.korbit", "/v2/currencyPairs launched/stopped"),
    Entry("korbit_networks", 60, "adapters.korbit", "/v2/currencies deposit/withdraw per network"),
    Entry("korbit_notice", 60, "adapters.korbit", "/v2/notices + /v2/marketAlerts"),
    # --- relay
    Entry("newlistings", 0, "adapters.newlistings", "WS; FREE = 3s delay, no history"),
    # --- tokenized stocks / RWA
    Entry("xstocks_assets", 600, "adapters.xstocks", "api.xstocks.fi v2 public, 5-15 min"),
    Entry("ondo_assets", 1800, "adapters.ondo", "needs onboarding"),
    Entry("superstate_funds", 21600, "adapters.superstate", "USTB/USCC public NAV"),
    # --- fiat routes
    Entry("ramp_assets", 1200, "adapters.ramp", "withDisabled+withHidden, 10-30 min"),
    Entry("onramper_routes", 1800, "adapters.onramper", "needs API key"),
    Entry("transak_routes", 1800, "adapters.transak", "needs partner key"),
    # --- chain deployments
    Entry("circle_chains", 21600, "adapters.circle", "USDC/EURC deployments, 6-24h"),
    # --- maintenance jobs (not data sources)
    Entry("resolve", 3600, "resolve", "identity resolution: Binance Alpha contract match, then symbol (SUGGESTED)",
          kind="maintenance"),
]


@dataclass
class AdapterSpec:
    source_id: str
    kind: str
    module: str
    period_sec: float = 60.0
    fetch: object = None
    run: object = None
    backfill: object = None
    platforms: list = field(default_factory=list)
    source: dict = None
    heartbeat_sec: float = DEFAULT_HEARTBEAT_SEC
    run_once: object = None        # conn-style adapter
    register: object = None        # conn-style adapter

    @property
    def mode(self):
        return "conn" if self.run_once else "native"


@dataclass
class LoadResult:
    entry: Entry
    spec: AdapterSpec = None
    state: str = "ok"        # ok / missing / error / no_source / disabled
    note: str = ""


def _import(module):
    """-> (module | None, state, note). Missing module file => 'missing'; module that fails to import => 'error'."""
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError):       # parent package missing
        spec = None
    if spec is None:
        return None, "missing", f"module {module} not found (adapter not written yet)"
    try:
        return importlib.import_module(module), "ok", ""
    except Exception as e:
        return None, "error", f"import {module} failed: {type(e).__name__}: {e}"


def _spec_from(mod, module, source_id, period):
    sources = getattr(mod, "SOURCES", None)
    if isinstance(sources, dict) and source_id in sources:
        d = {k.lower(): v for k, v in sources[source_id].items()}
    elif getattr(mod, "SOURCE_ID", None) == source_id:
        d = {"kind": getattr(mod, "KIND", None), "fetch": getattr(mod, "fetch", None),
             "run": getattr(mod, "run", None), "backfill": getattr(mod, "backfill", None),
             "period_sec": getattr(mod, "PERIOD_SEC", None), "platforms": getattr(mod, "PLATFORMS", None),
             "source": getattr(mod, "SOURCE", None), "heartbeat_sec": getattr(mod, "HEARTBEAT_SEC", None),
             "run_once": getattr(mod, "run_once", None), "register": getattr(mod, "register", None)}
    else:
        return None, "no_source"
    if not d.get("kind") and callable(d.get("run_once")):
        return AdapterSpec(
            source_id=source_id, kind="snapshot", module=module,
            period_sec=float(period if period else (d.get("period_sec") or 60)),
            platforms=list(d.get("platforms") or getattr(mod, "PLATFORMS", None) or []), source=d.get("source"),
            run_once=d["run_once"], register=d.get("register") if callable(d.get("register")) else None), "ok"
    kind = (d.get("kind") or "").lower()
    if kind not in KINDS:
        return None, f"bad KIND {d.get('kind')!r} (want one of {KINDS})"
    if kind == "stream" and not callable(d.get("run")):
        return None, "stream adapter without run(ctx)"
    if kind != "stream" and not callable(d.get("fetch")):
        return None, f"{kind} adapter without fetch(http)"
    # module-level PLATFORMS / SOURCE are shared defaults for SOURCES entries
    platforms = d.get("platforms") or getattr(mod, "PLATFORMS", None) or []
    return AdapterSpec(
        source_id=source_id, kind=kind, module=module,
        period_sec=float(period if period else (d.get("period_sec") or 60)),
        fetch=d.get("fetch"), run=d.get("run"), backfill=d.get("backfill"),
        platforms=list(platforms), source=d.get("source"),
        heartbeat_sec=float(d.get("heartbeat_sec") or DEFAULT_HEARTBEAT_SEC)), "ok"


def _module_source_ids(mod):
    ids = []
    if isinstance(getattr(mod, "SOURCES", None), dict):
        ids += list(mod.SOURCES)
    if getattr(mod, "SOURCE_ID", None):
        ids.append(mod.SOURCE_ID)
    return ids


def load_catalog(catalog=None, discover_package="adapters"):
    """Resolve every catalog entry to an AdapterSpec (or a skip reason). With discover_package, adapter
    modules in that package declaring sources NOT in the catalog are scheduled too (module PERIOD_SEC)."""
    catalog = CATALOG if catalog is None else catalog
    results, seen_ids, mods = [], set(), {}
    for e in catalog:
        if e.kind == "maintenance":
            continue
        seen_ids.add(e.source_id)
        if not e.enabled:
            results.append(LoadResult(e, state="disabled", note="disabled in CATALOG"))
            continue
        if e.module not in mods:
            mods[e.module] = _import(e.module)
        mod, state, note = mods[e.module]
        if mod is None:
            results.append(LoadResult(e, state=state, note=note))
            continue
        spec, why = _spec_from(mod, e.module, e.source_id, e.period_sec)
        if spec is None:
            have = ", ".join(_module_source_ids(mod)) or "none"
            st = "no_source" if why == "no_source" else "error"
            results.append(LoadResult(e, state=st, note=f"{e.module} does not provide {e.source_id} ({why}; has: {have})"))
            continue
        results.append(LoadResult(e, spec=spec))
    if discover_package:
        try:
            pkg_spec = importlib.util.find_spec(discover_package)
        except (ImportError, ValueError):
            pkg_spec = None
        paths = list(pkg_spec.submodule_search_locations or []) if pkg_spec else []
        for info in sorted(pkgutil.iter_modules(paths), key=lambda i: i.name):
            if info.name.startswith("_") or info.name.startswith("test"):
                continue
            module = f"{discover_package}.{info.name}"
            if module not in mods:
                mods[module] = _import(module)
            mod, state, note = mods[module]
            if mod is None:
                if state == "error":
                    results.append(LoadResult(Entry(f"?{info.name}", 0, module), state="error", note=note))
                continue
            for sid in _module_source_ids(mod):
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                spec, why = _spec_from(mod, module, sid, None)
                e = Entry(sid, spec.period_sec if spec else 0, module, "discovered (not in CATALOG)")
                results.append(LoadResult(e, spec=spec) if spec else LoadResult(e, state="error", note=why))
    for r in results:
        if r.state == "missing":
            log.info("skip %s: %s", r.entry.source_id, r.note)
        elif r.state != "ok":
            log.warning("skip %s: %s", r.entry.source_id, r.note)
    return results


# ----------------------------------------------------------------------------- maintenance jobs
def _resolve_prepare(mod):
    def prepare(http):
        """Job thread, network only. Alpha failure is carried over: resolution still runs (resolve.run semantics)."""
        try:
            return {"tokens": mod.fetch_alpha(http), "alpha_error": ""}
        except Exception as e:
            return {"tokens": [], "alpha_error": f"{type(e).__name__}: {e}"}
    return prepare


def _resolve_apply(mod):
    def apply(conn, payload):
        """Writer thread, DB only."""
        tokens = payload["tokens"]
        out = {"alpha_error": payload["alpha_error"], "alpha_tokens": len(tokens)}
        if tokens:
            try:
                out.update(mod.register_alpha(conn, tokens))
            except Exception as e:  # same as resolve.run: the pass still runs against the existing registry
                out["alpha_error"] = f"{type(e).__name__}: {e}"
                tokens = []
        out.update(mod.resolve_pending(conn, alpha_tokens=tokens))
        return out
    return apply


# module path -> (prepare factory, apply factory) for modules that don't expose prepare/apply themselves
MAINTENANCE_SHIMS = {"resolve": (_resolve_prepare, _resolve_apply)}


@dataclass
class MaintSpec:
    job_id: str
    module: str
    period_sec: float
    prepare: object
    apply: object


def load_maintenance(catalog=None):
    """Resolve kind="maintenance" catalog entries -> [LoadResult(entry, spec=MaintSpec | None, state, note)]."""
    catalog = CATALOG if catalog is None else catalog
    out = []
    for e in catalog:
        if e.kind != "maintenance":
            continue
        if not e.enabled:
            out.append(LoadResult(e, state="disabled", note="disabled in CATALOG"))
            continue
        mod, state, note = _import(e.module)
        if mod is None:
            out.append(LoadResult(e, state=state, note=note))
        elif e.module in MAINTENANCE_SHIMS:
            pf, af = MAINTENANCE_SHIMS[e.module]
            out.append(LoadResult(e, spec=MaintSpec(e.source_id, e.module, float(e.period_sec), pf(mod), af(mod))))
        elif callable(getattr(mod, "prepare", None)) and callable(getattr(mod, "apply", None)):
            out.append(LoadResult(e, spec=MaintSpec(e.source_id, e.module, float(e.period_sec), mod.prepare, mod.apply)))
        else:
            out.append(LoadResult(e, state="error", note=f"{e.module} has no prepare(http)/apply(conn, payload)"))
    for r in out:
        if r.state == "missing":
            log.info("skip maintenance %s: %s", r.entry.source_id, r.note)
        elif r.state != "ok":
            log.warning("skip maintenance %s: %s", r.entry.source_id, r.note)
    return out


def result_error(result):
    """Non-empty '*error' keys of a maintenance result -> message ('' if none)."""
    if not isinstance(result, dict):
        return ""
    return "; ".join(f"{k}: {v}" for k, v in result.items() if k.endswith("error") and v)


def backoff_delays(base=STREAM_BACKOFF[0], cap=STREAM_BACKOFF[1]):
    d = base
    while True:
        yield d
        d = min(d * 2, cap)


# ----------------------------------------------------------------------------- write jobs (run on the writer)
_RADAR_KIND = {"snapshot": "SNAPSHOT", "announcement": "ANNOUNCEMENT", "stream": "ANNOUNCEMENT"}


def _register(conn, spec):
    for p in spec.platforms or []:
        p = dict(p)
        rc.register_platform(conn, p.pop("platform_id"), **p)
    exists = conn.execute("SELECT 1 FROM source WHERE source_id=?", (spec.source_id,)).fetchone()
    kw = dict(spec.source or {})
    if kw or not exists:
        kw.setdefault("kind", _RADAR_KIND[spec.kind])
        kw.setdefault("tier", "OFFICIAL_STRUCTURED" if kw["kind"] == "SNAPSHOT" else "OFFICIAL_ANNOUNCEMENT")
        if "origin_platform_id" not in kw and len(spec.platforms or []) == 1:
            kw["origin_platform_id"] = spec.platforms[0]["platform_id"]
        if not spec.source and not exists:
            log.warning("%s: adapter has no SOURCE metadata, registering with defaults %s", spec.source_id, kw)
        rc.register_source(conn, spec.source_id, **kw)


def _ensure_platforms(conn, platform_ids):
    known = {r[0] for r in conn.execute("SELECT platform_id FROM platform")}
    for pid in sorted(set(platform_ids) - known - {"", None}):
        log.warning("auto-registering unknown platform %r (declare it in the adapter's PLATFORMS)", pid)
        rc.register_platform(conn, pid, pid, "OTHER")


def _write_snapshot(conn, source_id, scopes, fetched_at):
    events, rows, errors = [], 0, []
    pids = [it.get("platform_id") for items in scopes.values() if isinstance(items, list)
            for it in items if isinstance(it, dict)]
    _ensure_platforms(conn, pids)
    for scope, items in scopes.items():
        if isinstance(items, BaseException):
            rc.report_fetch_error(conn, source_id, scope, f"{type(items).__name__}: {items}", at=fetched_at)
            errors.append(f"{scope}: {items}")
            continue
        r = rc.ingest_snapshot(conn, source_id, scope, items, fetched_at=fetched_at)
        rows += len(items)
        events += r["events"]
        if r["outcome"] == "DEGRADED":
            errors.append(f"{scope}: DEGRADED {r['note']}")
    return {"rows": rows, "events": events, "errors": errors}


def _write_announcements(conn, source_id, anns, observed_at):
    events, errors, dup = [], [], 0
    _ensure_platforms(conn, [a.get("platform_id") for a in anns if isinstance(a, dict)])
    for a in anns:
        try:
            a = dict(a)
            a.setdefault("observed_at", observed_at)
            r = rc.ingest_announcement(conn, source_id, a)
            events += r["events"]
            dup += 1 if r["duplicate"] else 0
        except Exception as e:          # one bad notice must not drop the rest
            errors.append(f"{type(e).__name__}: {e}")
    return {"rows": len(anns), "events": events, "errors": errors, "duplicates": dup}


def _report_source_down(conn, source_id, error, at):
    scopes = [r[0] for r in conn.execute("SELECT scope FROM source_health WHERE source_id=?", (source_id,))]
    for scope in scopes or ["default"]:
        rc.report_fetch_error(conn, source_id, scope, error, at=at)


# ----------------------------------------------------------------------------- conn-style adapter support
def _fetch_key(url, headers):
    return (url, tuple(sorted((headers or {}).items())))


class RecordingFetch:
    """fetch(url, headers=None) -> parsed JSON via the shared HttpClient; remembers results and exceptions."""

    def __init__(self, http):
        self.http = http
        self.cache = {}

    def __call__(self, url, headers=None, **_ignored):
        key = _fetch_key(url, headers)
        try:
            out = self.http.get_json(url, headers=headers)
        except Exception as e:
            self.cache[key] = e
            raise
        self.cache[key] = out
        return out

    def replayer(self):
        return ReplayFetch(self.http, self.cache)


class ReplayFetch:
    """Serves recorded responses (re-raising recorded errors); a miss falls back to a live request."""

    def __init__(self, http, cache):
        self.http = http
        self.cache = cache
        self.live_misses = 0

    def __call__(self, url, headers=None, **_ignored):
        key = _fetch_key(url, headers)
        if key in self.cache:
            v = self.cache[key]
            if isinstance(v, BaseException):
                raise v
            return v
        self.live_misses += 1
        return self.http.get_json(url, headers=headers)


def summarize_conn_result(out):
    """Best-effort {rows, events, errors, all_failed} from a conn adapter's run_once() return value
    ({scope: ingest result | {"error": msg}} or a single ingest result / {"error": msg})."""
    rows, events, errors, scopes, failed = 0, [], [], 0, 0

    def visit(name, v):
        nonlocal rows, scopes, failed
        if not isinstance(v, dict):
            return
        if "error" in v and "outcome" not in v:
            scopes += 1
            failed += 1
            errors.append(f"{name}: {v['error']}" if name else str(v["error"]))
        elif "outcome" in v:
            scopes += 1
            rows += int(v.get("valid") or 0)
            events.extend(v.get("events") or [])
            if v.get("outcome") == "DEGRADED":
                errors.append(f"{name}: DEGRADED {v.get('note', '')}".strip())
        else:
            for k, sub in v.items():
                visit(f"{name}.{k}" if name else str(k), sub)

    visit("", out)
    return {"rows": rows, "events": events, "errors": errors, "all_failed": scopes > 0 and failed == scopes}


# ----------------------------------------------------------------------------- gap backfill helpers (writer)
def _pending_gaps(conn, source_id, cutoff_ms, limit):
    return [dict(r) for r in conn.execute(
        """SELECT disconnect_id, started_at, ended_at FROM source_disconnect
           WHERE source_id=? AND scope='' AND backfilled=0 AND ended_at IS NOT NULL AND ended_at>=?
           ORDER BY started_at, disconnect_id LIMIT ?""", (source_id, cutoff_ms, int(limit)))]


def _report_backfill_error(conn, source_id, msg):
    access_db.set_stream_state(conn, source_id, error=msg)
    conn.execute("UPDATE source_health SET last_error=?, updated_at=? WHERE source_id=? AND scope=''",
                 (msg[:500], rc.now_ms(), source_id))


def _clear_backfill_error(conn, source_id, cutoff_ms):
    """Clear a backfill error only when no retryable gap is left (other errors are left alone)."""
    if conn.execute("""SELECT 1 FROM source_disconnect WHERE source_id=? AND scope='' AND backfilled=0
                       AND ended_at IS NOT NULL AND ended_at>=? LIMIT 1""", (source_id, cutoff_ms)).fetchone():
        return
    like = BACKFILL_ERROR_PREFIX + "%"
    conn.execute("UPDATE source_run SET last_error='' WHERE source_id=? AND last_error LIKE ?", (source_id, like))
    conn.execute("UPDATE source_health SET last_error='' WHERE source_id=? AND scope='' AND last_error LIKE ?",
                 (source_id, like))


# ----------------------------------------------------------------------------- stream context
class StreamCtx:
    def __init__(self, runner, spec):
        self.runner = runner
        self.spec = spec
        self.source_id = spec.source_id
        self.http = runner.http
        self.stop_event = runner.stop_event
        self.log = logging.getLogger(f"access_radar.stream.{spec.source_id}")
        self._reconnect = threading.Event()
        self.is_connected = False
        self.connected_at = None
        self.last_heartbeat = None
        self._last_hb_write = 0.0
        self.events = 0

    # adapter-facing API
    def connected(self):
        now = time.time()
        self.is_connected = True
        self.connected_at = now
        self.last_heartbeat = now
        self._reconnect.clear()
        self.runner._stream_connected(self)

    def heartbeat(self):
        now = time.time()
        self.last_heartbeat = now
        if now - self._last_hb_write >= HEARTBEAT_WRITE_EVERY:
            self._last_hb_write = now
            self.runner.writer.submit(access_db.set_stream_state, self.source_id, heartbeat_at=int(now * 1000))

    def should_stop(self):
        return self.stop_event.is_set() or self._reconnect.is_set()

    def emit_announcement(self, ann):
        res = self.runner.writer.call(_write_announcements, self.source_id, [ann], rc.now_ms())
        n = len(res["events"])
        if n:
            self.events += n
            self.runner.writer.submit(access_db.set_stream_state, self.source_id, events=n)
        for err in res["errors"]:
            self.log.warning("%s: bad announcement: %s", self.source_id, err)
        return res

    def emit_snapshot(self, scope, items):
        return self.runner.writer.call(_write_snapshot, self.source_id, {scope: items}, rc.now_ms())

    def request_reconnect(self, why=""):
        self.log.warning("%s: reconnect requested %s", self.source_id, why)
        self._reconnect.set()


# ----------------------------------------------------------------------------- runner
class Runner:
    def __init__(self, writer, http, catalog=None, discover_package="adapters", stop_event=None,
                 stream_backoff=STREAM_BACKOFF, stream_stable_sec=STREAM_STABLE_SEC, watchdog_every=1.0,
                 backfill_retry_sec=BACKFILL_RETRY_SEC, backfill_max_age_sec=BACKFILL_MAX_AGE_SEC,
                 backfill_batch=BACKFILL_BATCH):
        self.writer = writer
        self.http = http
        self.catalog = CATALOG if catalog is None else catalog
        self.discover_package = discover_package
        self.stop_event = stop_event or threading.Event()
        self.stream_backoff = stream_backoff
        self.stream_stable_sec = stream_stable_sec
        self.watchdog_every = watchdog_every
        self.loaded = []
        self.specs = []
        self.threads = []
        self.streams = {}
        self.backfill_retry_sec = backfill_retry_sec
        self.backfill_max_age_sec = backfill_max_age_sec
        self.backfill_batch = backfill_batch
        self._backfill_locks = {}
        self.poll_log = []          # (source_id, started, finished, ok, thread name) for diagnostics/tests
        self.maint_loaded = []
        self.maint_specs = []
        self.maint_log = []         # (job_id, started, finished, ok, prepare thread, apply thread)
        self._prepared = False

    # -- setup
    def prepare(self):
        self.loaded = load_catalog(self.catalog, self.discover_package)
        self.specs = [r.spec for r in self.loaded if r.spec]

        def job(conn):
            for r in self.loaded:
                e = r.entry
                access_db.ensure_source_run(conn, e.source_id, r.spec.kind if r.spec else "", e.module,
                                            r.spec.period_sec if r.spec else e.period_sec, r.state, r.note,
                                            r.spec.heartbeat_sec if r.spec and r.spec.kind == "stream" else 0)
            for s in self.specs:
                if s.register:
                    s.register(conn)
                else:
                    _register(conn, s)
            access_db.meta_set(conn, "runner_prepared_at", rc.now_ms())
        self.writer.call(job)
        ok = [s.source_id for s in self.specs]
        skipped = [(r.entry.source_id, r.state) for r in self.loaded if not r.spec]
        log.info("adapters ready: %s; skipped: %s", ok or "none", skipped or "none")
        self.prepare_maintenance()
        self._prepared = True
        return self.specs

    def prepare_maintenance(self):
        self.maint_loaded = load_maintenance(self.catalog)
        self.maint_specs = [r.spec for r in self.maint_loaded if r.spec]

        def job(conn):
            for r in self.maint_loaded:
                access_db.ensure_maintenance_run(conn, r.entry.source_id, r.entry.module, r.entry.period_sec,
                                                 r.state, r.note)
        self.writer.call(job)
        return self.maint_specs

    # -- maintenance
    def run_maintenance(self, spec):
        """prepare(http) in this thread (network), apply(conn, payload) in the writer (DB). Never raises."""
        started = time.time()
        apply_thread = {}
        result, err = None, ""
        try:
            payload = spec.prepare(self.http)

            def apply(conn):
                apply_thread["name"] = threading.current_thread().name
                return spec.apply(conn, payload)
            result = self.writer.call(apply)
            err = result_error(result)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        finished = time.time()
        ok = not err
        try:
            self.writer.call(access_db.record_maintenance, spec.job_id, ok, int(started * 1000), int(finished * 1000),
                             error=err or None, result=result)
        except Exception as e2:
            log.error("maintenance %s: could not record run: %s", spec.job_id, e2)
        (log.info if ok else log.warning)("maintenance %s %s %s", spec.job_id, "ok" if ok else "fail",
                                          json.dumps(result, default=str)[:300] if ok else err[:300])
        self.maint_log.append((spec.job_id, started, finished, ok, threading.current_thread().name,
                               apply_thread.get("name")))
        return {"job_id": spec.job_id, "ok": ok, "error": err, "result": result,
                "latency_ms": int((finished - started) * 1000)}

    def _maint_loop(self, spec):
        while not self.stop_event.is_set():
            started = time.time()
            self.run_maintenance(spec)
            wait = spec.period_sec - (time.time() - started)
            if wait > 0 and self.stop_event.wait(wait):
                break

    # -- polling
    def poll_once(self, spec):
        started = time.time()
        try:
            if spec.mode == "conn":
                res = self._poll_conn_adapter(spec)
            else:
                res = self._poll_native(spec)
            finished = time.time()
            err = "; ".join(res["errors"])[:400] or None
            if res.get("all_failed"):
                raise AllScopesFailed(err or "all scopes failed")
            self.writer.call(access_db.record_run, spec.source_id, True, int(started * 1000), int(finished * 1000),
                             rows=res["rows"], events=len(res["events"]), error=err)
            ok = True
            log.info("%s ok rows=%s events=%s %s", spec.source_id, res["rows"], len(res["events"]), err or "")
        except Exception as e:
            finished = time.time()
            msg = f"{type(e).__name__}: {e}"
            res = {"rows": 0, "events": [], "errors": [msg]}
            ok = False
            try:
                if spec.mode != "conn":       # conn adapters report their own scopes
                    self.writer.call(_report_source_down, spec.source_id, msg, int(finished * 1000))
                self.writer.call(access_db.record_run, spec.source_id, False, int(started * 1000),
                                 int(finished * 1000), error=msg)
            except Exception as e2:
                log.error("%s: could not record failure: %s", spec.source_id, e2)
            log.warning("%s fail %s", spec.source_id, msg[:300])
        self.poll_log.append((spec.source_id, started, finished, ok, threading.current_thread().name))
        return {"source_id": spec.source_id, "ok": ok, "rows": res["rows"], "events": res["events"],
                "errors": res["errors"], "latency_ms": int((finished - started) * 1000)}

    def _poll_native(self, spec):
        out = spec.fetch(self.http)
        fetched_ms = rc.now_ms()
        if spec.kind == "snapshot":
            scopes = out if isinstance(out, dict) else {"default": list(out or [])}
            res = self.writer.call(_write_snapshot, spec.source_id, scopes, fetched_ms)
            res["all_failed"] = bool(scopes) and all(isinstance(v, BaseException) for v in scopes.values())
            return res
        return self.writer.call(_write_announcements, spec.source_id, list(out or []), fetched_ms)

    def _poll_conn_adapter(self, spec):
        """Record network in this thread against a scratch DB, replay on the real DB in the writer."""
        fetched_ms = rc.now_ms()
        rec = RecordingFetch(self.http)
        try:
            scratch = rc.init_db(":memory:")
            try:
                if spec.register:
                    spec.register(scratch)
                else:
                    _register(scratch, spec)
                spec.run_once(scratch, fetch=rec, fetched_at=fetched_ms)
            finally:
                scratch.close()
        except Exception as e:     # the replay below still runs; misses fall back to live fetches
            log.debug("%s: scratch pass failed (%s); replay will fetch live", spec.source_id, e)
        replay = rec.replayer()
        out = self.writer.call(lambda conn: spec.run_once(conn, fetch=replay, fetched_at=fetched_ms))
        if replay.live_misses:
            log.info("%s: %d fetches were not prefetched and ran inside the writer", spec.source_id, replay.live_misses)
        return summarize_conn_result(out)

    def _poll_loop(self, spec):
        """One thread per source. Period measured from request start (rh_v2 side_chain convention)."""
        while not self.stop_event.is_set():
            started = time.time()
            self.poll_once(spec)
            wait = spec.period_sec - (time.time() - started)
            if wait > 0 and self.stop_event.wait(wait):
                break

    # -- streams
    def _stream_connected(self, ctx):
        gap = self.writer.call(lambda conn: rc.mark_reconnected(conn, ctx.source_id, "", at=rc.now_ms()))
        self.writer.call(access_db.set_stream_state, ctx.source_id, connected=True, error="")
        log.info("%s connected (gap closed: %s)", ctx.source_id, gap)
        if ctx.spec.backfill:
            self.backfill_pending(ctx.spec)        # the gap just closed + any earlier ones still backfilled=0

    # -- gap backfill (initial attempt on reconnect + periodic retry)
    def backfill_pending(self, spec, limit=None):
        """Backfill closed gaps of a stream with backfilled=0, oldest first, at most `limit` (default
        backfill_batch), ended within backfill_max_age_sec. A failure stops the round and is reported as
        source_run.last_error / source_health.last_error; success sets backfilled=1 and clears that error once
        nothing is pending. Returns [(disconnect_id, ok)], or None if another thread is already backfilling."""
        if not spec.backfill:
            return []
        lock = self._backfill_locks.setdefault(spec.source_id, threading.Lock())
        if not lock.acquire(blocking=False):
            return None
        try:
            cutoff = rc.now_ms() - int(self.backfill_max_age_sec * 1000)
            gaps = self.writer.call(_pending_gaps, spec.source_id, cutoff, limit or self.backfill_batch)
            done = []
            for g in gaps:
                if self.stop_event.is_set():
                    break
                since, until = g["started_at"], g["ended_at"]
                try:
                    anns = spec.backfill(self.http, since, until) or []
                    res = self.writer.call(_write_announcements, spec.source_id, list(anns), rc.now_ms())
                    if res["events"]:
                        self.writer.submit(access_db.set_stream_state, spec.source_id, events=len(res["events"]))
                    self.writer.call(lambda conn: conn.execute(
                        "UPDATE source_disconnect SET backfilled=1 WHERE disconnect_id=?", (g["disconnect_id"],)))
                    log.info("%s backfilled gap %s..%s: %d announcements", spec.source_id, rc.fmt_ts(since),
                             rc.fmt_ts(until), len(anns))
                    done.append((g["disconnect_id"], True))
                except Exception as e:
                    msg = (f"{BACKFILL_ERROR_PREFIX} for gap {rc.fmt_ts(since)}..{rc.fmt_ts(until)} {rc.LOCAL_LABEL}: "
                           f"{type(e).__name__}: {e}")
                    log.warning("%s %s (retry every %.0fs)", spec.source_id, msg, self.backfill_retry_sec)
                    self.writer.call(_report_backfill_error, spec.source_id, msg)
                    done.append((g["disconnect_id"], False))
                    break                          # history endpoint is likely down: try the rest next round
            if done and all(ok for _, ok in done):
                self.writer.call(_clear_backfill_error, spec.source_id, cutoff)
            return done
        finally:
            lock.release()

    def _backfill_retry_loop(self):
        while not self.stop_event.wait(self.backfill_retry_sec):
            for spec in self.specs:
                if spec.kind != "stream" or not spec.backfill:
                    continue
                try:
                    self.backfill_pending(spec)
                except Exception as e:             # never let the retry thread die
                    log.error("%s backfill retry round failed: %s", spec.source_id, e)

    def _stream_loop(self, spec):
        ctx = StreamCtx(self, spec)
        self.streams[spec.source_id] = ctx

        def open_gap(conn, reason, at):
            rc.mark_disconnected(conn, spec.source_id, "", at=at, reason=reason)
            access_db.set_stream_state(conn, spec.source_id, connected=False, error=reason)

        # The time since our last activity is a gap too (process was down): start it at the last heartbeat.
        last = self.writer.call(lambda conn: conn.execute(
            "SELECT COALESCE(last_heartbeat, last_success) FROM source_run WHERE source_id=?",
            (spec.source_id,)).fetchone())
        self.writer.call(open_gap, "process start", (last[0] if last and last[0] else rc.now_ms()))
        delays = backoff_delays(*self.stream_backoff)
        while not self.stop_event.is_set():
            ctx._reconnect.clear()
            reason = "run() returned"
            try:
                spec.run(ctx)
            except Exception as e:
                reason = f"{type(e).__name__}: {e}"
            was_connected, lived = ctx.is_connected, (time.time() - ctx.connected_at) if ctx.connected_at else 0
            ctx.is_connected = False
            if ctx._reconnect.is_set():
                reason = "heartbeat timeout" if not self.stop_event.is_set() else reason
            if self.stop_event.is_set():
                reason = "runner stopping"
            self.writer.call(open_gap, reason[:300], rc.now_ms())
            if was_connected and lived >= self.stream_stable_sec:
                delays = backoff_delays(*self.stream_backoff)
            delay = next(delays)
            log.warning("%s disconnected (%s); reconnect in %.1fs", spec.source_id, reason[:200], delay)
            if self.stop_event.wait(delay):
                break

    def _watchdog(self):
        while not self.stop_event.wait(self.watchdog_every):
            now = time.time()
            for ctx in list(self.streams.values()):
                if ctx.is_connected and ctx.last_heartbeat and now - ctx.last_heartbeat > ctx.spec.heartbeat_sec \
                        and not ctx._reconnect.is_set():
                    ctx.request_reconnect(f"(no heartbeat for {now - ctx.last_heartbeat:.1f}s)")

    # -- lifecycle
    def start(self):
        if not self._prepared:
            self.prepare()
        for spec in self.specs:
            target = self._stream_loop if spec.kind == "stream" else self._poll_loop
            t = threading.Thread(target=target, args=(spec,), name=f"access-{spec.source_id}", daemon=True)
            t.start()
            self.threads.append(t)
        if any(s.kind == "stream" for s in self.specs):
            t = threading.Thread(target=self._watchdog, name="access-watchdog", daemon=True)
            t.start()
            self.threads.append(t)
        if any(s.kind == "stream" and s.backfill for s in self.specs) and self.backfill_retry_sec:
            t = threading.Thread(target=self._backfill_retry_loop, name="access-backfill", daemon=True)
            t.start()
            self.threads.append(t)
        for m in self.maint_specs:
            t = threading.Thread(target=self._maint_loop, args=(m,), name=f"access-maint-{m.job_id}", daemon=True)
            t.start()
            self.threads.append(t)
        return self.threads

    def stop(self, timeout=10):
        self.stop_event.set()
        deadline = time.time() + timeout
        for t in self.threads:
            t.join(max(0.0, deadline - time.time()))

    def run_once(self):
        """Every polling source once (sequentially); streams and maintenance jobs are skipped in once mode."""
        if not self._prepared:
            self.prepare()
        out = []
        for spec in self.specs:
            if spec.kind == "stream":
                log.info("once: skip stream source %s (streams only run in loop mode)", spec.source_id)
                # marker kept for direct callers; access_run.cmd_once moves it to summary["skipped"]
                out.append({"source_id": spec.source_id, "skipped": "stream"})
                continue
            out.append(self.poll_once(spec))
        return out

    def run_forever(self, heartbeat_every=5.0, tick_every=60.0):
        """Main thread: start source threads, write collector heartbeat, run tick (scheduled delistings)."""
        self.start()
        last_hb = last_tick = 0.0
        try:
            while not self.stop_event.is_set():
                now = time.time()
                if now - last_hb >= heartbeat_every:
                    self.writer.call(access_db.touch_heartbeat, int(now * 1000))
                    last_hb = now
                if now - last_tick >= tick_every:
                    n = self.writer.call(lambda conn: rc.process_due(conn))
                    if n:
                        log.info("tick: applied %d scheduled removals", len(n))
                    last_tick = now
                self.stop_event.wait(0.5)
        finally:
            self.stop()
