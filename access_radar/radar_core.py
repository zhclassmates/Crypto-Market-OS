#!/usr/bin/env python3
"""Recent Access Radar — core layer (Python 3 stdlib only).

Pipeline per snapshot:  validate -> health gate -> baseline | diff -> state machine -> canonical event merge.
Pipeline per announcement:  idempotency -> state machine (ANNOUNCED / REMOVED / SUSPENDED ...) -> merge.

All timestamps are UTC epoch milliseconds (int).  See STATE_MACHINE.md for the rules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

log = logging.getLogger("access_radar")

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "schema.sql")
DB_ENV = "ACCESS_DB"                      # the one env var for every entry point (access_db/access_run, resolve, CLI)
LEGACY_DB_ENV = "ACCESS_RADAR_DB"         # backwards-compatible fallback only (same order as resolve.py / ops/nightly.py)
DEFAULT_DB_PATH = os.path.join(HERE, "access.sqlite")   # access_radar/access.sqlite, independent of cwd


def default_db_path():
    """$ACCESS_DB, else legacy $ACCESS_RADAR_DB, else <access_radar>/access.sqlite (never cwd-relative)."""
    return os.environ.get(DB_ENV) or os.environ.get(LEGACY_DB_ENV) or DEFAULT_DB_PATH

# ----------------------------------------------------------------------------- constants
STATUSES = ("NONE", "ANNOUNCED", "LIVE", "SUSPENDED", "REMOVED")
SNAPSHOT_ITEM_STATUSES = ("LIVE", "SUSPENDED")
ACCESS_KINDS = ("SPOT", "PERP", "CATALOG", "ALPHA", "ROADMAP", "FIAT_ROUTE", "DEPOSIT_NETWORK",
                "WITHDRAW_NETWORK", "COLLATERAL", "LENDING", "CHAIN_DEPLOYMENT")
ASSET_TYPES = ("CRYPTO", "STABLECOIN", "TOKENIZED_STOCK", "ETF", "FUND", "TREASURY", "COMMODITY", "RWA_OTHER")
FIAT_TIERS = ("SUPPORTED", "QUOTABLE", "CONFIRMED")
FIAT_TIER_RANK = {None: 0, "": 0, "SUPPORTED": 1, "QUOTABLE": 2, "CONFIRMED": 3}
ANN_ACTIONS = ("LISTING", "DELISTING", "SUSPEND", "RESUME")

TIER_WEIGHTS = {
    "OFFICIAL_STRUCTURED": 0.95,     # exchange / issuer structured API (market list, asset list)
    "OFFICIAL_ANNOUNCEMENT": 0.85,   # official notices (Upbit notice WS, Bithumb /v1/notices ...)
    "THIRD_PARTY": 0.60,             # third-party relays such as NewListings
    "AGGREGATOR": 0.50,              # aggregators such as Onramper
    "LLM_EXTRACTED": 0.30,           # extracted from unstructured text
}
OFFICIAL_TIERS = ("OFFICIAL_STRUCTURED", "OFFICIAL_ANNOUNCEMENT")

ALLOWED_TRANSITIONS = {
    ("NONE", "ANNOUNCED"), ("NONE", "LIVE"), ("NONE", "SUSPENDED"),
    ("ANNOUNCED", "LIVE"), ("ANNOUNCED", "SUSPENDED"), ("ANNOUNCED", "REMOVED"),
    ("LIVE", "SUSPENDED"), ("LIVE", "REMOVED"),
    ("SUSPENDED", "LIVE"), ("SUSPENDED", "REMOVED"),
    ("REMOVED", "ANNOUNCED"), ("REMOVED", "LIVE"),
}

MERGE_WINDOW_MS = 72 * 3600 * 1000
SCHEMA_INVALID_MAX = 0.05     # >5% invalid items => schema check fails => DEGRADED, diff paused
SIZE_ACCEPT_AFTER = 3         # N consecutive consistent anomalous (non-empty) sizes => accept new size
ADD_RANK = {"ANNOUNCED": 1, "SUSPENDED": 2, "LIVE": 3}

KEY_FIELDS = ("asset_key", "platform_id", "access_kind", "quote", "country", "fiat", "payment_method", "network")
# quote-wildcard observation (DELISTING/SUSPEND/RESUME with quote ''): access_id NULL, matches every quote
_WILDCARD_DIMS = ("asset_key", "platform_id", "access_kind", "country", "fiat", "payment_method", "network")
_WILDCARD_OBS_SQL = ("o.access_id IS NULL AND o.quote='' AND o.obs_kind='ANNOUNCEMENT' AND "
                     + " AND ".join(f"o.{f}=?" for f in _WILDCARD_DIMS))


class IllegalTransition(Exception):
    pass


def now_ms() -> int:
    return int(time.time() * 1000)


# ----------------------------------------------------------------------------- db
def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db(path_or_conn) -> sqlite3.Connection:
    conn = connect(path_or_conn) if isinstance(path_or_conn, str) else path_or_conn
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = f.read()
    conn.executescript(schema)
    migrate(conn, schema)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# columns added after v0.1: (table, column, declaration). ALTER TABLE ADD COLUMN only if missing.
MIGRATION_COLUMNS = (
    ("access_event", "group_key", "TEXT"),
    ("source_observation", "url", "TEXT"),
)
FEED_VIEW = "v_recent_feed"
_GROUP_BACKFILL = """
UPDATE access_event SET group_key = COALESCE(
    (SELECT 'ann:' || o.source_id || ':' || o.source_event_id || ':' || o.asset_key
       FROM event_observation_link l JOIN source_observation o ON o.obs_id = l.obs_id
      WHERE l.event_id = access_event.event_id AND l.role = 'ORIGIN' AND o.obs_kind = 'ANNOUNCEMENT'
        AND o.source_event_id <> '' ORDER BY o.obs_id LIMIT 1),
    'ev:' || event_id)
WHERE group_key IS NULL"""


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _view_sql(schema):
    m = re.search(r"CREATE VIEW IF NOT EXISTS v_recent_feed AS.*?;", schema, re.S)
    if not m:
        raise RuntimeError("v_recent_feed missing from schema.sql")
    return m.group(0)


def migrate(conn, schema=None):
    """Idempotent upgrade of an existing db: add missing columns, backfill group_key, index it, and rebuild
    v_recent_feed when it lacks any column of the current definition. Cheap no-op on an up-to-date db."""
    if schema is None:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = f.read()
    view_sql = _view_sql(schema)
    with _tx(conn):
        for table, col, decl in MIGRATION_COLUMNS:
            if col not in _columns(conn, table):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
                log.info("migrated: %s.%s added", table, col)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_event_group ON access_event(group_key)")
        if conn.execute("SELECT 1 FROM access_event WHERE group_key IS NULL LIMIT 1").fetchone():
            conn.execute(_GROUP_BACKFILL)
        if _view_columns(conn, "main", FEED_VIEW) != _definition_columns(conn, view_sql):
            conn.execute(f"DROP VIEW IF EXISTS {FEED_VIEW}")
            conn.execute(view_sql)
            log.info("migrated: %s rebuilt", FEED_VIEW)
    return conn


def _view_columns(conn, schema_name, view):
    return [r[1] for r in conn.execute(f"PRAGMA {schema_name}.table_info({view})")]


def _definition_columns(conn, view_sql):
    """Column list of the schema.sql view definition, compiled as a connection-private TEMP view."""
    conn.execute("DROP VIEW IF EXISTS temp._feed_probe")
    conn.execute(view_sql.replace(f"CREATE VIEW IF NOT EXISTS {FEED_VIEW}", "CREATE TEMP VIEW _feed_probe", 1))
    cols = _view_columns(conn, "temp", "_feed_probe")
    conn.execute("DROP VIEW temp._feed_probe")
    return cols


@contextmanager
def _tx(conn):
    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def _one(conn, sql, args=()):
    r = conn.execute(sql, args).fetchone()
    return dict(r) if r is not None else None


def _store_raw(conn, raw):
    if raw is None:
        return None
    js = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
    h = hashlib.sha256(js.encode("utf-8")).hexdigest()
    conn.execute("INSERT OR IGNORE INTO raw_blob(sha256, json) VALUES (?, ?)", (h, js))
    return conn.execute("SELECT raw_id FROM raw_blob WHERE sha256 = ?", (h,)).fetchone()[0]


# ----------------------------------------------------------------------------- registry
def register_platform(conn, platform_id, name=None, platform_type="CEX", country="", at=None):
    with _tx(conn):
        conn.execute(
            """INSERT INTO platform(platform_id, name, platform_type, country, created_at) VALUES (?,?,?,?,?)
               ON CONFLICT(platform_id) DO UPDATE SET name=excluded.name, platform_type=excluded.platform_type,
               country=excluded.country""",
            (platform_id, name or platform_id, platform_type, country, at or now_ms()))


def register_source(conn, source_id, *, name=None, kind="SNAPSHOT", tier="OFFICIAL_STRUCTURED",
                    independence_group=None, origin_platform_id=None, is_relay=False, tier_weight=None,
                    add_confirm_obs=None, remove_confirm_misses=3, size_tolerance=0.2, size_min_abs=3,
                    remove_min_elapsed_ms=0, at=None):
    """Register a source. Defaults:  independence_group = source_id;  add_confirm_obs = 1 for
    OFFICIAL_STRUCTURED (one healthy observation is enough) else 2 (provisional, confirm on 2nd)."""
    if tier not in TIER_WEIGHTS:
        raise ValueError(f"unknown tier {tier}")
    if add_confirm_obs is None:
        add_confirm_obs = 1 if tier == "OFFICIAL_STRUCTURED" else 2
    with _tx(conn):
        conn.execute(
            """INSERT INTO source(source_id, name, kind, tier, tier_weight, independence_group, origin_platform_id,
                   is_relay, add_confirm_obs, remove_confirm_misses, size_tolerance, size_min_abs,
                   remove_min_elapsed_ms, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source_id) DO UPDATE SET name=excluded.name, kind=excluded.kind, tier=excluded.tier,
                   tier_weight=excluded.tier_weight, independence_group=excluded.independence_group,
                   origin_platform_id=excluded.origin_platform_id, is_relay=excluded.is_relay,
                   add_confirm_obs=excluded.add_confirm_obs, remove_confirm_misses=excluded.remove_confirm_misses,
                   size_tolerance=excluded.size_tolerance, size_min_abs=excluded.size_min_abs,
                   remove_min_elapsed_ms=excluded.remove_min_elapsed_ms""",
            (source_id, name or source_id, kind, tier, tier_weight or TIER_WEIGHTS[tier],
             independence_group or source_id, origin_platform_id, int(bool(is_relay)), add_confirm_obs,
             remove_confirm_misses, size_tolerance, size_min_abs, remove_min_elapsed_ms, at or now_ms()))


def upsert_asset(conn, asset_key, asset_type, symbol, name="", issuer="", underlying="", product_id="", at=None):
    if asset_type not in ASSET_TYPES:
        raise ValueError(f"bad asset_type {asset_type}")
    with _tx(conn):
        conn.execute(
            """INSERT INTO asset(asset_key, asset_type, symbol, name, issuer, underlying, product_id, created_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(asset_key) DO UPDATE SET asset_type=excluded.asset_type, symbol=excluded.symbol,
                   name=excluded.name, issuer=excluded.issuer, underlying=excluded.underlying,
                   product_id=excluded.product_id""",
            (asset_key, asset_type, symbol, name, issuer, underlying, product_id, at or now_ms()))
        return conn.execute("SELECT asset_id FROM asset WHERE asset_key=?", (asset_key,)).fetchone()[0]


def _norm_contract(chain, contract):
    chain = (chain or "").strip().lower()
    contract = (contract or "").strip()
    if contract.startswith("0x"):
        contract = contract.lower()
    return chain, contract


def add_deployment(conn, asset_id, chain, contract, decimals=None, at=None):
    chain, contract = _norm_contract(chain, contract)
    with _tx(conn):
        conn.execute("""INSERT INTO asset_deployment(asset_id, chain, contract, decimals, created_at)
                        VALUES (?,?,?,?,?) ON CONFLICT(chain, contract) DO NOTHING""",
                     (asset_id, chain, contract, decimals, at or now_ms()))
        return conn.execute("SELECT deployment_id FROM asset_deployment WHERE chain=? AND contract=?",
                            (chain, contract)).fetchone()[0]


def resolve_ref(conn, ref_id, asset_id, status="CONFIRMED", resolution_source="manual", at=None):
    """Attach a source_asset_ref to a global asset. CONFIRMED propagates asset_id to access_state."""
    if status not in ("SUGGESTED", "CONFIRMED"):
        raise ValueError(status)
    at = at or now_ms()
    with _tx(conn):
        if status == "SUGGESTED":
            conn.execute("""UPDATE source_asset_ref SET suggested_asset_id=?, resolution_status='SUGGESTED',
                            resolution_source=?, resolved_at=? WHERE ref_id=? AND resolution_status<>'CONFIRMED'""",
                         (asset_id, resolution_source, at, ref_id))
        else:
            conn.execute("""UPDATE source_asset_ref SET asset_id=?, resolution_status='CONFIRMED',
                            resolution_source=?, resolved_at=? WHERE ref_id=?""",
                         (asset_id, resolution_source, at, ref_id))
            conn.execute("""UPDATE access_state SET asset_id=? WHERE ref_id=? OR access_id IN
                            (SELECT access_id FROM source_observation WHERE ref_id=? AND access_id IS NOT NULL)""",
                         (asset_id, ref_id, ref_id))
            # quote-wildcard announcements (access_id NULL) cover every quote of their (asset, platform, kind, dims)
            same = " AND ".join(f"o.{f}=access_state.{f}" for f in _WILDCARD_DIMS)
            conn.execute(f"""UPDATE access_state SET asset_id=? WHERE EXISTS (SELECT 1 FROM source_observation o
                             WHERE o.ref_id=? AND o.access_id IS NULL AND o.quote='' AND o.obs_kind='ANNOUNCEMENT'
                             AND {same})""", (asset_id, ref_id))


# ----------------------------------------------------------------------------- source health helpers
def _get_source(conn, source_id):
    s = _one(conn, "SELECT * FROM source WHERE source_id=?", (source_id,))
    if s is None:
        raise KeyError(f"unknown source {source_id}")
    return s


def _get_health(conn, source_id, scope, at):
    h = _one(conn, "SELECT * FROM source_health WHERE source_id=? AND scope=?", (source_id, scope))
    if h is None:
        conn.execute("""INSERT INTO source_health(source_id, scope, status, updated_at)
                        VALUES (?,?, 'HEALTHY', ?)""", (source_id, scope, at))
        h = _one(conn, "SELECT * FROM source_health WHERE source_id=? AND scope=?", (source_id, scope))
    return h


def _set_health(conn, source_id, scope, at, **fields):
    fields["updated_at"] = at
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE source_health SET {cols} WHERE source_id=? AND scope=?",
                 (*fields.values(), source_id, scope))


def report_fetch_error(conn, source_id, scope, error, at=None):
    """Adapter could not fetch/parse at all -> DOWN. No diff, no miss counting."""
    at = at or now_ms()
    with _tx(conn):
        _get_source(conn, source_id)
        _get_health(conn, source_id, scope, at)
        _set_health(conn, source_id, scope, at, status="DOWN", last_error=str(error)[:500], last_fetch_at=at)


def mark_disconnected(conn, source_id, scope="", at=None, reason=""):
    at = at or now_ms()
    with _tx(conn):
        open_ = _one(conn, "SELECT disconnect_id FROM source_disconnect WHERE source_id=? AND scope=? AND ended_at IS NULL",
                     (source_id, scope))
        if open_:
            return open_["disconnect_id"]
        cur = conn.execute("INSERT INTO source_disconnect(source_id, scope, started_at, reason) VALUES (?,?,?,?)",
                           (source_id, scope, at, reason))
        _get_health(conn, source_id, scope, at)
        _set_health(conn, source_id, scope, at, status="DOWN", last_error=f"disconnected: {reason}")
        return cur.lastrowid


def mark_reconnected(conn, source_id, scope="", at=None):
    """Close the open gap. Returns (started_at, ended_at) so the adapter can backfill via REST/History."""
    at = at or now_ms()
    with _tx(conn):
        row = _one(conn, "SELECT * FROM source_disconnect WHERE source_id=? AND scope=? AND ended_at IS NULL",
                   (source_id, scope))
        if not row:
            return None
        conn.execute("UPDATE source_disconnect SET ended_at=? WHERE disconnect_id=?", (at, row["disconnect_id"]))
        _set_health(conn, source_id, scope, at, status="HEALTHY", last_error="")
        return row["started_at"], at


def open_gaps(conn, source_id=None):
    sql = "SELECT * FROM source_disconnect WHERE backfilled=0"
    args = ()
    if source_id:
        sql += " AND source_id=?"
        args = (source_id,)
    return [dict(r) for r in conn.execute(sql, args)]


# ----------------------------------------------------------------------------- item normalisation
def _s(v):
    return "" if v is None else str(v).strip()


def _normalize(conn, src, item, *, for_snapshot=True, defaults=None, platforms=None):
    """Return (normalized dict, None) or (None, error)."""
    if not isinstance(item, dict):
        return None, "item is not an object"
    it = dict(defaults or {})
    it.update({k: v for k, v in item.items() if v is not None})
    platform_id = _s(it.get("platform_id")) or _s(src["origin_platform_id"])
    if not platform_id:
        return None, "missing platform_id"
    if platforms is not None:
        if platform_id not in platforms:
            return None, f"unknown platform {platform_id}"
    elif not conn.execute("SELECT 1 FROM platform WHERE platform_id=?", (platform_id,)).fetchone():
        return None, f"unknown platform {platform_id}"
    kind = _s(it.get("access_kind")).upper()
    if kind not in ACCESS_KINDS:
        return None, f"bad access_kind {kind!r}"
    symbol = _s(it.get("symbol")).upper()
    asset_key = _s(it.get("asset_key")) or (f"sym:{symbol}" if symbol else "")
    if not asset_key:
        return None, "missing symbol/asset_key"
    status = _s(it.get("status") or "LIVE").upper()
    if for_snapshot and status not in SNAPSHOT_ITEM_STATUSES:
        return None, f"bad status {status!r}"
    fiat = _s(it.get("fiat")).upper()
    quote = _s(it.get("quote")).upper()
    fiat_tier = None
    if kind == "FIAT_ROUTE":
        if not fiat:
            return None, "FIAT_ROUTE requires fiat"
        quote = quote or fiat
        fiat_tier = _s(it.get("fiat_tier") or "SUPPORTED").upper()
        if fiat_tier not in FIAT_TIERS:
            return None, f"bad fiat_tier {fiat_tier!r}"
    origin_group = src["independence_group"]
    if src["is_relay"] and _s(it.get("origin_group")):
        origin_group = _s(it.get("origin_group"))
    chain, contract = _norm_contract(it.get("chain"), it.get("contract"))
    n = {
        "asset_key": asset_key, "platform_id": platform_id, "access_kind": kind, "quote": quote,
        "country": _s(it.get("country")).upper(), "fiat": fiat,
        "payment_method": _s(it.get("payment_method")).lower(), "network": _s(it.get("network")).lower(),
        "status": status, "fiat_tier": fiat_tier, "symbol": symbol or asset_key,
        "native_id": _s(it.get("native_id")), "chain": chain, "contract": contract,
        "origin_group": origin_group, "raw": it.get("raw"),
        "announced_at": it.get("announced_at"), "source_detected_at": it.get("source_detected_at"),
        "url": _s(it.get("url") or it.get("pc_url")),
    }
    n["key"] = tuple(n[f] for f in KEY_FIELDS)
    return n, None


def _get_or_create_ref(conn, source_id, n, at):
    conn.execute("""INSERT INTO source_asset_ref(source_id, platform_id, platform_symbol, native_id, created_at)
                    VALUES (?,?,?,?,?) ON CONFLICT(source_id, platform_id, platform_symbol) DO NOTHING""",
                 (source_id, n["platform_id"], n["symbol"], n["native_id"], at))
    ref = _one(conn, "SELECT * FROM source_asset_ref WHERE source_id=? AND platform_id=? AND platform_symbol=?",
               (source_id, n["platform_id"], n["symbol"]))
    if ref["resolution_status"] != "CONFIRMED" and n["chain"] and n["contract"]:
        dep = _one(conn, "SELECT asset_id FROM asset_deployment WHERE chain=? AND contract=?", (n["chain"], n["contract"]))
        if dep:   # exact contract match -> deterministic resolution
            conn.execute("""UPDATE source_asset_ref SET asset_id=?, resolution_status='CONFIRMED',
                            resolution_source='contract', resolved_at=? WHERE ref_id=?""",
                         (dep["asset_id"], at, ref["ref_id"]))
            ref.update(asset_id=dep["asset_id"], resolution_status="CONFIRMED")
    return ref


def _get_access(conn, key):
    return _one(conn, "SELECT * FROM access_state WHERE " + " AND ".join(f"{f}=?" for f in KEY_FIELDS), key)


def _get_or_create_access(conn, n, ref, at):
    acc = _get_access(conn, n["key"])
    if acc:
        if acc["asset_id"] is None and ref and ref["asset_id"] is not None:
            conn.execute("UPDATE access_state SET asset_id=? WHERE access_id=?", (ref["asset_id"], acc["access_id"]))
            acc["asset_id"] = ref["asset_id"]
        return acc, False
    conn.execute(
        f"""INSERT INTO access_state({", ".join(KEY_FIELDS)}, asset_id, ref_id, status, first_seen_at, last_seen_at,
               status_since) VALUES ({", ".join("?" * len(KEY_FIELDS))}, ?, ?, 'NONE', ?, ?, ?)""",
        (*n["key"], ref["asset_id"] if ref else None, ref["ref_id"] if ref else None, at, at, at))
    return _get_access(conn, n["key"]), True


def _write_obs(conn, src, n, *, obs_kind, scope="", snapshot_id=None, ref=None, access_id=None, action="",
               observed_at, announced_at=None, source_detected_at=None, effective_at=None, poll_prev_at=None,
               source_event_id="", raw=None, reported_status=None):
    raw_id = _store_raw(conn, raw if raw is not None else n.get("raw"))
    cur = conn.execute(
        """INSERT INTO source_observation(source_id, scope, snapshot_id, obs_kind, platform_id, ref_id, access_id,
               asset_key, access_kind, quote, country, fiat, payment_method, network, reported_status, action,
               fiat_tier, origin_group, announced_at, source_detected_at, observed_at, effective_at, poll_prev_at,
               source_event_id, raw_id, url)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (src["source_id"], scope, snapshot_id, obs_kind, n["platform_id"], ref["ref_id"] if ref else None, access_id,
         n["asset_key"], n["access_kind"], n["quote"], n["country"], n["fiat"], n["payment_method"], n["network"],
         reported_status if reported_status is not None else (n["status"] if obs_kind != "ANNOUNCEMENT" else ""),
         action, n.get("fiat_tier"), n["origin_group"], announced_at, source_detected_at, observed_at, effective_at,
         poll_prev_at, source_event_id, raw_id, n.get("url") or None))
    return cur.lastrowid


# ----------------------------------------------------------------------------- state machine & events
def derive_family(from_s, to_s):
    if to_s == "REMOVED":
        return "REMOVE"
    if to_s == "ANNOUNCED":
        return "ADD"
    if to_s == "LIVE":
        return "RESUME" if from_s == "SUSPENDED" else "ADD"
    if to_s == "SUSPENDED":
        return "SUSPEND" if from_s == "LIVE" else "ADD"
    raise ValueError((from_s, to_s))


_ADD_LIVE_NAMES = {"SPOT": "SPOT_LISTED", "PERP": "PERP_LISTED", "ALPHA": "ALPHA_LISTED",
                   "CATALOG": "CATALOG_ADDED", "ROADMAP": "ROADMAP_ADDED", "CHAIN_DEPLOYMENT": "CHAIN_DEPLOYED",
                   "DEPOSIT_NETWORK": "DEPOSIT_ENABLED", "WITHDRAW_NETWORK": "WITHDRAW_ENABLED",
                   "COLLATERAL": "COLLATERAL_ENABLED", "LENDING": "LENDING_ENABLED"}
_SHORT = {"DEPOSIT_NETWORK": "DEPOSIT", "WITHDRAW_NETWORK": "WITHDRAW"}


def derive_event_type(kind, from_s, to_s, fiat_tier=None, family=None):
    """event_type is a pure function of (access_kind, from_status, to_status[, fiat_tier])."""
    family = family or derive_family(from_s, to_s)
    short = _SHORT.get(kind, kind)
    if family == "TIER" or (kind == "FIAT_ROUTE" and family == "ADD" and to_s == "LIVE" and from_s != "REMOVED"):
        return f"FIAT_ROUTE_{fiat_tier or 'SUPPORTED'}"
    if family == "ADD":
        if to_s == "ANNOUNCED":
            return f"{kind}_ANNOUNCED"
        if to_s == "LIVE":
            return f"{kind}_RELISTED" if from_s == "REMOVED" else _ADD_LIVE_NAMES.get(kind, f"{kind}_LIVE")
        return f"{kind}_LISTED_SUSPENDED"
    if family == "SUSPEND":
        return f"{short}_SUSPENDED"
    if family == "RESUME":
        return f"{short}_RESUMED"
    if family == "REMOVE":
        if from_s == "ANNOUNCED":
            return f"{kind}_ANNOUNCEMENT_CANCELLED"
        return f"{kind}_DELISTED" if kind in ("SPOT", "PERP", "ALPHA") else f"{kind}_REMOVED"
    raise ValueError(family)


def _min(*vals):
    v = [x for x in vals if x is not None]
    return min(v) if v else None


def _recompute_confidence(conn, event_id):
    """confidence = 1 - prod(1 - w_g) over distinct independence groups g; w_g = max tier weight seen in g."""
    rows = conn.execute(
        """SELECT o.origin_group AS g, MAX(s.tier_weight) AS w FROM event_observation_link l
           JOIN source_observation o ON o.obs_id = l.obs_id JOIN source s ON s.source_id = o.source_id
           WHERE l.event_id=? AND l.role <> 'RETRACT' GROUP BY o.origin_group""", (event_id,)).fetchall()
    conf = 1.0 - math.prod(1.0 - r["w"] for r in rows) if rows else 0.0
    conn.execute("UPDATE access_event SET confidence=?, independent_source_count=? WHERE event_id=?",
                 (round(conf, 4), len(rows), event_id))


def _find_episode(conn, acc, families, t, quote=None):
    """Merge key (asset_key, platform_id, access_kind, quote) + family + 72h window around anchor_at or
    effective_at.  quote '' is a wildcard on either side."""
    quote = acc["quote"] if quote is None else quote
    fam_sql = ",".join("?" * len(families))
    return _one(conn,
                f"""SELECT * FROM access_event WHERE asset_key=? AND platform_id=? AND access_kind=?
                    AND family IN ({fam_sql}) AND retracted=0 AND (quote=? OR ?='' OR quote='')
                    AND (ABS(anchor_at-?) <= ? OR (effective_at IS NOT NULL AND ABS(effective_at-?) <= ?))
                    ORDER BY (quote=?) DESC, anchor_at DESC LIMIT 1""",
                (acc["asset_key"], acc["platform_id"], acc["access_kind"], *families, quote, quote,
                 t, MERGE_WINDOW_MS, t, MERGE_WINDOW_MS, quote))


def _merge_event(conn, acc, family, from_s, to_s, ctx, *, create=True, families=None, role=None):
    """Attach the observation in ctx to a canonical episode, or create one (if create=True)."""
    t = _min(ctx.get("announced_at"), ctx.get("source_detected_at"), ctx["observed_at"])
    ev = _find_episode(conn, acc, families or [family], t)
    obs_id = ctx.get("obs_id")
    now = ctx["observed_at"]
    if ev is None:
        if not create:
            return None
        etype = ctx.get("event_type") or derive_event_type(acc["access_kind"], from_s, to_s, ctx.get("fiat_tier"), family)
        cur = conn.execute(
            """INSERT INTO access_event(access_id, asset_key, platform_id, access_kind, quote, family, from_status,
                   to_status, event_type, fiat_tier, anchor_at, announced_at, source_detected_at, observed_at,
                   effective_at, live_observed_at, poll_prev_at, confidence, independent_source_count, provisional,
                   first_source_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?,?,?)""",
            (acc["access_id"], acc["asset_key"], acc["platform_id"], acc["access_kind"], acc["quote"], family, from_s,
             to_s, etype, ctx.get("fiat_tier"), t, ctx.get("announced_at"), ctx.get("source_detected_at"),
             ctx["observed_at"], ctx.get("effective_at"), ctx.get("live_observed_at"), ctx.get("poll_prev_at"),
             int(bool(ctx.get("provisional"))), ctx["source_id"], now, now))
        event_id = cur.lastrowid
        # display group (STATE_MACHINE.md §9.1): one announcement + one asset -> shared key; otherwise the event itself
        conn.execute("UPDATE access_event SET group_key=? WHERE event_id=?",
                     (ctx.get("group_key") or f"ev:{event_id}", event_id))
        if obs_id:
            conn.execute("INSERT OR IGNORE INTO event_observation_link(event_id, obs_id, role) VALUES (?,?,'ORIGIN')",
                         (event_id, obs_id))
        _recompute_confidence(conn, event_id)
        return event_id

    event_id = ev["event_id"]
    upd = {}
    progressed = False
    if family == "ADD" and ev["family"] == "ADD" and ADD_RANK.get(to_s, 0) > ADD_RANK.get(ev["to_status"], 0):
        progressed = True
        upd["to_status"] = to_s
    elif ctx.get("transition") and ev["event_type"].endswith("_SCHEDULED"):
        progressed = True   # the scheduled delisting actually happened
    if progressed:
        upd["event_type"] = derive_event_type(acc["access_kind"], ev["from_status"], upd.get("to_status", ev["to_status"]),
                                              ctx.get("fiat_tier") or ev["fiat_tier"], ev["family"])
        if ctx.get("fiat_tier"):
            upd["fiat_tier"] = ctx["fiat_tier"]
    if ev["quote"] == "" and acc["quote"] != "":
        # wildcard episode (announcement without quote) gets bound to the concrete market
        upd["quote"] = acc["quote"]
        upd["access_id"] = acc["access_id"]
        sib = _one(conn, "SELECT * FROM access_state WHERE access_id=?", (ev["access_id"],))
        if sib and sib["quote"] == "" and sib["status"] == "ANNOUNCED" and to_s in ("LIVE", "SUSPENDED"):
            conn.execute("UPDATE access_state SET status=?, status_since=?, provisional=0 WHERE access_id=?",
                         (to_s, now, sib["access_id"]))
            conn.execute("""INSERT INTO access_transition(access_id, event_id, from_status, to_status, at, source_id,
                            obs_id, reason) VALUES (?,?,?,?,?,?,?,?)""",
                         (sib["access_id"], event_id, "ANNOUNCED", to_s, now, ctx["source_id"], obs_id,
                          f"wildcard placeholder promoted by quote {acc['quote']}"))
    upd["anchor_at"] = _min(ev["anchor_at"], t)
    upd["announced_at"] = _min(ev["announced_at"], ctx.get("announced_at"))
    upd["source_detected_at"] = _min(ev["source_detected_at"], ctx.get("source_detected_at"))
    if ev["effective_at"] is None and ctx.get("effective_at") is not None:
        upd["effective_at"] = ctx["effective_at"]
    if ctx.get("live_observed_at") is not None and (ev["live_observed_at"] is None
                                                     or ctx["live_observed_at"] < ev["live_observed_at"]):
        upd["live_observed_at"] = ctx["live_observed_at"]
        upd["poll_prev_at"] = ctx.get("poll_prev_at")
    if ev["provisional"] and not ctx.get("provisional"):
        upd["provisional"] = 0
        conn.execute("UPDATE access_state SET provisional=0 WHERE access_id=?", (upd.get("access_id", ev["access_id"]),))
    upd["updated_at"] = max(ev["updated_at"], now)
    cols = ", ".join(f"{k}=?" for k in upd)
    conn.execute(f"UPDATE access_event SET {cols} WHERE event_id=?", (*upd.values(), event_id))
    if obs_id:
        r = role or ("PROGRESS" if progressed else "CORROBORATE")
        conn.execute("INSERT OR IGNORE INTO event_observation_link(event_id, obs_id, role) VALUES (?,?,?)",
                     (event_id, obs_id, r))
    _recompute_confidence(conn, event_id)
    return event_id


def _reject(conn, acc, from_s, to_s, ctx, reason):
    conn.execute("""INSERT INTO rejected_transition(access_id, from_status, to_status, at, source_id, obs_id, reason)
                    VALUES (?,?,?,?,?,?,?)""",
                 (acc["access_id"] if acc else None, from_s, to_s, ctx["observed_at"], ctx["source_id"],
                  ctx.get("obs_id"), reason))
    log.warning("rejected transition %s -> %s for access %s (%s): %s", from_s, to_s,
                acc["access_id"] if acc else None, ctx["source_id"], reason)


REJECTED = object()


def _apply(conn, acc, to_s, ctx, reason=""):
    """Enforce the state machine, update access_state, merge into a canonical event, log the transition.
    Returns event_id, None (no-op) or REJECTED."""
    from_s = acc["status"]
    if to_s not in STATUSES:
        raise ValueError(to_s)
    if from_s == to_s:
        return None
    if (from_s, to_s) not in ALLOWED_TRANSITIONS:
        _reject(conn, acc, from_s, to_s, ctx, reason or "transition not allowed")
        return REJECTED
    at = ctx["observed_at"]
    fields = {"status": to_s, "status_since": at, "provisional": int(bool(ctx.get("provisional")))}
    if to_s == "LIVE":
        fields["miss_count"] = 0
    if to_s == "REMOVED":
        fields["pending_removal_at"] = None
    if ctx.get("fiat_tier"):
        fields["fiat_tier"] = ctx["fiat_tier"]
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE access_state SET {cols} WHERE access_id=?", (*fields.values(), acc["access_id"]))
    family = derive_family(from_s, to_s)
    event_id = _merge_event(conn, acc, family, from_s, to_s, dict(ctx, transition=True))
    conn.execute("""INSERT INTO access_transition(access_id, event_id, from_status, to_status, at, source_id, obs_id, reason)
                    VALUES (?,?,?,?,?,?,?,?)""",
                 (acc["access_id"], event_id, from_s, to_s, at, ctx["source_id"], ctx.get("obs_id"), reason))
    acc.update(fields)
    return event_id


def apply_transition(conn, access_id, to_status, source_id, at=None, reason="manual"):
    """Public, manual transition (ops / tests). Illegal transitions are logged in rejected_transition and raise."""
    at = at or now_ms()
    with _tx(conn):
        acc = _one(conn, "SELECT * FROM access_state WHERE access_id=?", (access_id,))
        if acc is None:
            raise KeyError(access_id)
        _get_source(conn, source_id)
        from_s = acc["status"]
        res = _apply(conn, acc, to_status, {"source_id": source_id, "observed_at": at}, reason)
    if res is REJECTED:
        raise IllegalTransition(f"{from_s} -> {to_status} not allowed (access {access_id})")
    return res


def _retract(conn, acc, src, ctx):
    """Provisional ADD that vanished before confirmation: roll back state, mark the episode retracted."""
    ev = _one(conn, """SELECT * FROM access_event WHERE access_id=? AND provisional=1 AND retracted=0
                       AND first_source_id=? ORDER BY event_id DESC LIMIT 1""", (acc["access_id"], src["source_id"]))
    back = ev["from_status"] if ev else "NONE"
    conn.execute("UPDATE access_state SET status=?, provisional=0, status_since=? WHERE access_id=?",
                 (back, ctx["observed_at"], acc["access_id"]))
    if ev:
        conn.execute("UPDATE access_event SET retracted=1, updated_at=? WHERE event_id=?", (ctx["observed_at"], ev["event_id"]))
        if ctx.get("obs_id"):
            conn.execute("INSERT OR IGNORE INTO event_observation_link(event_id, obs_id, role) VALUES (?,?,'RETRACT')",
                         (ev["event_id"], ctx["obs_id"]))
    conn.execute("""INSERT INTO access_transition(access_id, event_id, from_status, to_status, at, source_id, obs_id, reason)
                    VALUES (?,?,?,?,?,?,?, 'retract: provisional add not confirmed')""",
                 (acc["access_id"], ev["event_id"] if ev else None, acc["status"], back, ctx["observed_at"],
                  src["source_id"], ctx.get("obs_id")))
    return ev["event_id"] if ev else None


# ----------------------------------------------------------------------------- snapshot ingestion
def ingest_snapshot(conn, source_id, scope, items, fetched_at=None, poll_prev_at=None, raw=None):
    """Ingest one full snapshot of (source, scope).

    items: list of dicts with keys: platform_id (default: source.origin_platform_id), symbol or asset_key,
           access_kind, status ('LIVE'|'SUSPENDED', default LIVE), quote, country, fiat, payment_method, network,
           fiat_tier (FIAT_ROUTE), native_id, chain/contract (optional, for resolution), origin_group (relay
           sources only), source_detected_at, raw.
    Returns dict(outcome, events, health, valid, invalid, note).
    """
    fetched_at = fetched_at or now_ms()
    items = list(items or [])
    result = {"outcome": None, "events": [], "health": None, "valid": 0, "invalid": 0, "note": ""}
    with _tx(conn):
        src = _get_source(conn, source_id)
        if src["kind"] != "SNAPSHOT":
            raise ValueError(f"{source_id} is not a SNAPSHOT source")
        health = _get_health(conn, source_id, scope, fetched_at)
        if poll_prev_at is None:
            poll_prev_at = health["last_ok_at"]
        platforms = {r[0] for r in conn.execute("SELECT platform_id FROM platform")}
        valid, invalid, seen = [], [], set()
        for it in items:
            n, err = _normalize(conn, src, it, platforms=platforms)
            if err:
                invalid.append(err)
            elif n["key"] not in seen:
                seen.add(n["key"])
                valid.append(n)
        result.update(valid=len(valid), invalid=len(invalid))
        raw_id = _store_raw(conn, raw)
        snap_id = conn.execute(
            """INSERT INTO source_snapshot(source_id, scope, fetched_at, poll_prev_at, item_count, valid_count, outcome, raw_id)
               VALUES (?,?,?,?,?,?, 'DIFF', ?)""",
            (source_id, scope, fetched_at, poll_prev_at, len(items), len(valid), raw_id)).lastrowid

        def finish(outcome, note=""):
            conn.execute("UPDATE source_snapshot SET outcome=?, note=? WHERE snapshot_id=?", (outcome, note, snap_id))
            result.update(outcome=outcome, note=note)
            result["health"] = _one(conn, "SELECT status FROM source_health WHERE source_id=? AND scope=?",
                                    (source_id, scope))["status"]
            return result

        # 1) schema / validation gate
        if items and len(invalid) / len(items) > SCHEMA_INVALID_MAX:
            note = f"schema check failed: {len(invalid)}/{len(items)} invalid (e.g. {invalid[0]})"
            _set_health(conn, source_id, scope, fetched_at, status="DEGRADED", schema_ok=0, last_error=note,
                        last_fetch_at=fetched_at)
            return finish("DEGRADED", note)

        n_valid = len(valid)
        # 2) baseline per (source, scope): never emits events
        if not health["baseline_done"]:
            if n_valid == 0:
                note = "empty first snapshot; baseline deferred"
                _set_health(conn, source_id, scope, fetched_at, status="DEGRADED", last_error=note, last_fetch_at=fetched_at)
                return finish("DEGRADED", note)
            _baseline(conn, src, scope, valid, fetched_at)
            _set_health(conn, source_id, scope, fetched_at, status="HEALTHY", schema_ok=1, baseline_done=1,
                        last_snapshot_size=n_valid, consecutive_anomalies=0, anomaly_size=None, last_error="",
                        last_fetch_at=fetched_at, last_ok_at=fetched_at)
            conn.execute("""INSERT OR REPLACE INTO source_scope_baseline(source_id, scope, snapshot_id, completed_at, item_count)
                            VALUES (?,?,?,?,?)""", (source_id, scope, snap_id, fetched_at, n_valid))
            return finish("BASELINE", f"baseline {n_valid} items")

        # 3) size gate: |delta| > max(tolerance * last, size_min_abs) or empty => DEGRADED, diff paused
        last = health["last_snapshot_size"] or 0

        def tol(ref):
            return max(src["size_tolerance"] * ref, src["size_min_abs"])

        anomaly = None
        if n_valid == 0 and last > 0:
            anomaly = "empty snapshot"
        elif abs(n_valid - last) > tol(last):
            anomaly = f"size {last} -> {n_valid} outside ±{int(src['size_tolerance'] * 100)}%"
        outcome = "DIFF"
        if anomaly:
            prev = health["anomaly_size"]
            consistent = prev is not None and n_valid > 0 and abs(n_valid - prev) <= tol(prev)
            cons = health["consecutive_anomalies"] + 1 if consistent else 1
            if n_valid > 0 and cons >= SIZE_ACCEPT_AFTER:
                outcome = "SIZE_ACCEPTED"   # persistent, consistent new size (never for empty): accept and diff
                result["note"] = f"accepted new size {n_valid} after {cons} consistent snapshots"
            else:
                _set_health(conn, source_id, scope, fetched_at, status="DEGRADED", consecutive_anomalies=cons,
                            anomaly_size=n_valid, last_error=anomaly, last_fetch_at=fetched_at, schema_ok=1)
                return finish("DEGRADED", anomaly)

        # 4) diff
        result["events"] = _diff(conn, src, scope, valid, fetched_at, poll_prev_at, snap_id, skip_misses=bool(invalid))
        _set_health(conn, source_id, scope, fetched_at, status="HEALTHY", schema_ok=1, last_snapshot_size=n_valid,
                    consecutive_anomalies=0, anomaly_size=None, last_error="", last_fetch_at=fetched_at,
                    last_ok_at=fetched_at)
        note = result["note"] or (f"{len(invalid)} invalid items dropped; miss counting skipped" if invalid else "")
        return finish(outcome, note)


def _upsert_sis(conn, source_id, scope, access_id, at, **f):
    row = _one(conn, "SELECT 1 AS x FROM source_item_state WHERE source_id=? AND scope=? AND access_id=?",
               (source_id, scope, access_id))
    if row is None:
        conn.execute("""INSERT INTO source_item_state(source_id, scope, access_id, present, reported_status, fiat_tier,
                        miss_count, seen_streak, first_miss_at, first_seen_at, last_seen_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                     (source_id, scope, access_id, f.get("present", 1), f.get("reported_status", ""),
                      f.get("fiat_tier"), f.get("miss_count", 0), f.get("seen_streak", 1), f.get("first_miss_at"),
                      at, f.get("last_seen_at", at)))
    else:
        cols = ", ".join(f"{k}=?" for k in f)
        conn.execute(f"UPDATE source_item_state SET {cols} WHERE source_id=? AND scope=? AND access_id=?",
                     (*f.values(), source_id, scope, access_id))


def _baseline(conn, src, scope, valid, at):
    for n in valid:
        ref = _get_or_create_ref(conn, src["source_id"], n, at)
        acc, created = _get_or_create_access(conn, n, ref, at)
        if created:
            conn.execute("""UPDATE access_state SET status=?, fiat_tier=?, created_via_baseline=1, status_since=?,
                            last_seen_at=? WHERE access_id=?""", (n["status"], n["fiat_tier"], at, at, acc["access_id"]))
            conn.execute("""INSERT INTO access_transition(access_id, event_id, from_status, to_status, at, source_id, reason)
                            VALUES (?, NULL, 'NONE', ?, ?, ?, 'baseline (no event)')""",
                         (acc["access_id"], n["status"], at, src["source_id"]))
        else:   # state already known from another source: leave it unchanged
            conn.execute("UPDATE access_state SET last_seen_at=? WHERE access_id=?", (at, acc["access_id"]))
        _upsert_sis(conn, src["source_id"], scope, acc["access_id"], at, present=1, reported_status=n["status"],
                    fiat_tier=n["fiat_tier"], miss_count=0, seen_streak=src["add_confirm_obs"], first_miss_at=None,
                    last_seen_at=at)


def _diff(conn, src, scope, valid, at, poll_prev_at, snap_id, skip_misses=False):
    sid = src["source_id"]
    events = []
    present_ids = set()

    def push(e):
        if e not in (None, REJECTED) and e not in events:
            events.append(e)

    for n in valid:
        ref = _get_or_create_ref(conn, sid, n, at)
        acc, _ = _get_or_create_access(conn, n, ref, at)
        present_ids.add(acc["access_id"])
        conn.execute("UPDATE access_state SET last_seen_at=?, miss_count=0 WHERE access_id=?", (at, acc["access_id"]))
        sis = _one(conn, "SELECT * FROM source_item_state WHERE source_id=? AND scope=? AND access_id=?",
                   (sid, scope, acc["access_id"]))
        if sis is None or not sis["present"]:
            view, streak = "NEW", 1
        elif sis["reported_status"] != n["status"]:
            view, streak = "CHANGE", sis["seen_streak"] + 1
        else:
            view, streak = "SAME", sis["seen_streak"] + 1
        old_tier = sis["fiat_tier"] if sis else None
        _upsert_sis(conn, sid, scope, acc["access_id"], at, present=1, reported_status=n["status"],
                    fiat_tier=n["fiat_tier"], miss_count=0, first_miss_at=None, seen_streak=streak, last_seen_at=at)
        provisional = src["add_confirm_obs"] > 1 and streak < src["add_confirm_obs"]
        cur = acc["status"]
        ctx = {"source_id": sid, "observed_at": at, "poll_prev_at": poll_prev_at, "live_observed_at": at,
               "source_detected_at": n["source_detected_at"], "announced_at": n["announced_at"],
               "provisional": provisional, "fiat_tier": n["fiat_tier"]}
        obs_kind = {"NEW": "SNAPSHOT_NEW", "CHANGE": "SNAPSHOT_CHANGE", "SAME": "SNAPSHOT_SEEN_AGAIN"}[view]

        def obs():
            return _write_obs(conn, src, n, obs_kind=obs_kind, scope=scope, snapshot_id=snap_id, ref=ref,
                              access_id=acc["access_id"], observed_at=at, poll_prev_at=poll_prev_at,
                              source_detected_at=n["source_detected_at"], announced_at=n["announced_at"])

        transitioned = False
        if cur != n["status"] and (view in ("NEW", "CHANGE") or cur in ("NONE", "ANNOUNCED")):
            # source view changed, or canonical is still only ANNOUNCED -> drive the state machine
            ctx["obs_id"] = obs()
            e = _apply(conn, acc, n["status"], ctx, reason=f"snapshot {view.lower()}")
            push(e)
            transitioned = e not in (None, REJECTED)
        elif cur == n["status"] and acc["provisional"] and not provisional:
            # second observation (or a non-provisional source) confirms a provisional add
            ctx["obs_id"] = obs()
            conn.execute("UPDATE access_state SET provisional=0 WHERE access_id=?", (acc["access_id"],))
            ev = _one(conn, """SELECT event_id FROM access_event WHERE access_id=? AND provisional=1 AND retracted=0
                               ORDER BY event_id DESC LIMIT 1""", (acc["access_id"],))
            if ev:
                conn.execute("UPDATE access_event SET provisional=0, updated_at=? WHERE event_id=?", (at, ev["event_id"]))
                conn.execute("INSERT OR IGNORE INTO event_observation_link(event_id, obs_id, role) VALUES (?,?,'CONFIRM')",
                             (ev["event_id"], ctx["obs_id"]))
                _recompute_confidence(conn, ev["event_id"])
                push(ev["event_id"])
        elif cur == n["status"] and view in ("NEW", "CHANGE"):
            # this source newly reports a state the canonical layer already has -> corroborate a recent episode
            fams = {"LIVE": ["ADD", "RESUME"], "SUSPENDED": ["SUSPEND", "ADD"]}[n["status"]]
            if _find_episode(conn, acc, fams, at):
                ctx["obs_id"] = obs()
                fam = "ADD" if n["status"] == "LIVE" else "SUSPEND"
                push(_merge_event(conn, acc, fam, "NONE", n["status"], ctx, create=False, families=fams))

        # fiat tier changes (FIAT_ROUTE only): upgrade => TIER event, downgrade => silent
        if (not transitioned and n["access_kind"] == "FIAT_ROUTE" and acc["status"] == "LIVE"
                and n["fiat_tier"] != (acc["fiat_tier"] or None)):
            if FIAT_TIER_RANK[n["fiat_tier"]] > FIAT_TIER_RANK[acc["fiat_tier"]]:
                ctx["obs_id"] = ctx.get("obs_id") or obs()
                conn.execute("UPDATE access_state SET fiat_tier=? WHERE access_id=?", (n["fiat_tier"], acc["access_id"]))
                e = _merge_event(conn, acc, "TIER", "LIVE", "LIVE", dict(ctx, transition=True))
                conn.execute("""INSERT INTO access_transition(access_id, event_id, from_status, to_status, at, source_id,
                                obs_id, reason) VALUES (?,?, 'LIVE', 'LIVE', ?, ?, ?, ?)""",
                             (acc["access_id"], e, at, sid, ctx["obs_id"],
                              f"fiat tier {acc['fiat_tier']} -> {n['fiat_tier']}"))
                push(e)
            elif old_tier != n["fiat_tier"]:
                conn.execute("UPDATE access_state SET fiat_tier=? WHERE access_id=?", (n["fiat_tier"], acc["access_id"]))

    if skip_misses:
        return events

    # missing items
    rows = conn.execute("SELECT * FROM source_item_state WHERE source_id=? AND scope=? AND present=1",
                        (sid, scope)).fetchall()
    for sis in rows:
        sis = dict(sis)
        if sis["access_id"] in present_ids:
            continue
        acc = _one(conn, "SELECT * FROM access_state WHERE access_id=?", (sis["access_id"],))
        miss = sis["miss_count"] + 1
        first_miss = sis["first_miss_at"] or at
        n = {f: acc[f] for f in KEY_FIELDS}
        n.update(status="", fiat_tier=acc["fiat_tier"], origin_group=src["independence_group"], raw=None)
        ctx = {"source_id": sid, "observed_at": at, "poll_prev_at": sis["last_seen_at"], "live_observed_at": first_miss,
               "effective_at": acc["pending_removal_at"], "provisional": False}

        def miss_obs():
            return _write_obs(conn, src, n, obs_kind="SNAPSHOT_MISS", scope=scope, snapshot_id=snap_id,
                              access_id=acc["access_id"], observed_at=at, poll_prev_at=sis["last_seen_at"],
                              effective_at=acc["pending_removal_at"], reported_status="MISSING")

        if acc["provisional"] and sis["seen_streak"] < src["add_confirm_obs"]:
            ctx["obs_id"] = miss_obs()
            _upsert_sis(conn, sid, scope, acc["access_id"], at, present=0, miss_count=miss, first_miss_at=first_miss)
            push(_retract(conn, acc, src, ctx))
            continue
        due_pending = acc["pending_removal_at"] is not None and acc["pending_removal_at"] <= at
        enough = miss >= src["remove_confirm_misses"] and (at - first_miss) >= src["remove_min_elapsed_ms"]
        if not (enough or due_pending):
            _upsert_sis(conn, sid, scope, acc["access_id"], at, miss_count=miss, first_miss_at=first_miss)
            conn.execute("UPDATE access_state SET miss_count=MAX(miss_count, ?) WHERE access_id=?", (miss, acc["access_id"]))
            continue
        _upsert_sis(conn, sid, scope, acc["access_id"], at, present=0, miss_count=miss, first_miss_at=first_miss)
        others = conn.execute("""SELECT COUNT(*) FROM source_item_state WHERE access_id=? AND present=1 AND miss_count=0
                                 AND NOT (source_id=? AND scope=?)""", (acc["access_id"], sid, scope)).fetchone()[0]
        conn.execute("UPDATE access_state SET miss_count=? WHERE access_id=?", (miss, acc["access_id"]))
        if others == 0 and acc["status"] in ("LIVE", "SUSPENDED"):
            ctx["obs_id"] = miss_obs()
            reason = "official delisting effective" if due_pending and not enough else f"{miss} consecutive healthy misses"
            push(_apply(conn, acc, "REMOVED", ctx, reason=reason))
    return events


WILDCARD_ACTIONS = ("DELISTING", "SUSPEND", "RESUME")


def _wildcard_matches(conn, n):
    """Existing (status <> NONE) access rows for a quote-less DELISTING/SUSPEND/RESUME target: same asset_key,
    platform, access_kind and other key dims, ANY quote. Concrete quotes first, the '' placeholder last."""
    return [dict(r) for r in conn.execute(
        """SELECT * FROM access_state WHERE asset_key=? AND platform_id=? AND access_kind=? AND country=? AND fiat=?
           AND payment_method=? AND network=? AND status<>'NONE' ORDER BY (quote=''), quote""",
        (n["asset_key"], n["platform_id"], n["access_kind"], n["country"], n["fiat"], n["payment_method"],
         n["network"]))]


def _announcement_step(conn, acc, action, ctx, official, note=""):
    """State-machine step of one announcement on one access row. Returns event_id, None or REJECTED."""
    cur = acc["status"]
    eff, observed_at = ctx["effective_at"], ctx["observed_at"]
    if action == "LISTING":
        if cur in ("NONE", "REMOVED"):
            return _apply(conn, acc, "ANNOUNCED", ctx, reason="listing announcement")
        e = _merge_event(conn, acc, "ADD", "NONE", "ANNOUNCED", ctx, create=False)
        if e is None and cur in ("LIVE", "SUSPENDED"):
            _reject(conn, acc, cur, "ANNOUNCED", ctx,
                    "listing announcement for an already-listed access with no ADD episode within 72h")
            return REJECTED
        return e
    if action == "DELISTING":
        future = eff is not None and eff > observed_at
        if cur == "NONE":
            _reject(conn, acc, "NONE", "REMOVED", ctx, "delisting for an access never seen")
            return REJECTED
        if cur == "REMOVED":
            return _merge_event(conn, acc, "REMOVE", cur, "REMOVED", ctx, create=False)
        if official and not future:
            return _apply(conn, acc, "REMOVED", ctx, reason="official delisting" + note)
        # official with future effective_at -> scheduled; third party -> provisional. No state change yet.
        if official:
            conn.execute("UPDATE access_state SET pending_removal_at=? WHERE access_id=?", (eff, acc["access_id"]))
        base = derive_event_type(acc["access_kind"], cur, "REMOVED", family="REMOVE")
        ctx["event_type"] = base + "_SCHEDULED" if future else base
        return _merge_event(conn, acc, "REMOVE", cur, "REMOVED", ctx)
    if action == "SUSPEND":
        if official and cur in ("LIVE", "ANNOUNCED"):
            return _apply(conn, acc, "SUSPENDED", ctx, reason="official suspension notice" + note)
        return _merge_event(conn, acc, "SUSPEND", "LIVE", "SUSPENDED", ctx, create=False)
    if action == "RESUME":
        if official and cur == "SUSPENDED":
            return _apply(conn, acc, "LIVE", ctx, reason="official resume notice" + note)
        return _merge_event(conn, acc, "RESUME", "SUSPENDED", "LIVE", ctx, create=False)
    raise ValueError(action)


# ----------------------------------------------------------------------------- announcement ingestion
def ingest_announcement(conn, source_id, ann):
    """Ingest one event-style message (exchange notice, NewListings event ...).

    ann: dict(action LISTING|DELISTING|SUSPEND|RESUME, platform_id, targets=[{symbol|asset_key, access_kind,
         quote, network, fiat, country, payment_method}] (or those keys at top level for a single target),
         announced_at, source_detected_at, observed_at, effective_at, source_event_id (must be STABLE; build one
         if the vendor id is not), origin_group (relay sources only), title, url (notice link; pc_url accepted;
         a target may carry its own url), raw).
    Empty/missing quote on DELISTING/SUSPEND/RESUME is a wildcard: the action applies to every existing (non-NONE)
    access_state of that (asset_key, platform_id, access_kind) across all quotes, one event per affected quote
    (STATE_MACHINE.md §6.1). With no existing state it behaves like a single quote-less target.
    Idempotent on (source_id, source_event_id).  Returns dict(events, duplicate, rejected, obs, wildcard).
    """
    observed_at = ann.get("observed_at") or now_ms()
    action = _s(ann.get("action")).upper()
    if action not in ANN_ACTIONS:
        raise ValueError(f"bad action {action!r}")
    targets = ann.get("targets") or [{k: ann[k] for k in ("symbol", "asset_key", "access_kind", "quote", "network",
                                                          "fiat", "country", "payment_method") if k in ann}]
    result = {"events": [], "duplicate": False, "rejected": 0, "obs": [], "wildcard": []}
    with _tx(conn):
        src = _get_source(conn, source_id)
        sev = _s(ann.get("source_event_id"))
        if not sev:
            basis = json.dumps([ann.get("platform_id"), action, targets, ann.get("announced_at"), ann.get("title")],
                               sort_keys=True, default=str)
            sev = "h:" + hashlib.sha256(basis.encode()).hexdigest()[:24]
        if conn.execute("SELECT 1 FROM source_observation WHERE source_id=? AND source_event_id=? LIMIT 1",
                        (source_id, sev)).fetchone():
            result["duplicate"] = True
            return result
        official = src["tier"] in OFFICIAL_TIERS
        defaults = {"platform_id": ann.get("platform_id"), "access_kind": "SPOT", "origin_group": ann.get("origin_group"),
                    "url": ann.get("url") or ann.get("pc_url")}
        raw = ann.get("raw") if ann.get("raw") is not None else {k: v for k, v in ann.items() if k != "raw"}
        eff = ann.get("effective_at")
        for t in targets:
            n, err = _normalize(conn, src, t, for_snapshot=False, defaults=defaults)
            if err:
                raise ValueError(f"bad announcement target: {err}")
            ref = _get_or_create_ref(conn, source_id, n, observed_at)
            # quote '' on DELISTING/SUSPEND/RESUME = every existing market of (asset, platform, kind[, other dims])
            accs = _wildcard_matches(conn, n) if action in WILDCARD_ACTIONS and n["quote"] == "" else []
            wildcard = bool(accs)
            if wildcard:
                result["wildcard"].append({"asset_key": n["asset_key"], "platform_id": n["platform_id"],
                                           "access_kind": n["access_kind"], "quotes": [a["quote"] for a in accs]})
                for acc in accs:
                    if acc["asset_id"] is None and ref["asset_id"] is not None:
                        conn.execute("UPDATE access_state SET asset_id=? WHERE access_id=?",
                                     (ref["asset_id"], acc["access_id"]))
                        acc["asset_id"] = ref["asset_id"]
            else:
                accs = [_get_or_create_access(conn, n, ref, observed_at)[0]]
            # one observation per target, as reported (quote ''); a wildcard observation has access_id NULL and is
            # linked to every per-quote episode it touches (access_transition.obs_id / event_observation_link)
            obs_id = _write_obs(conn, src, n, obs_kind="ANNOUNCEMENT", ref=ref,
                                access_id=None if wildcard else accs[0]["access_id"],
                                action=action, observed_at=observed_at, announced_at=ann.get("announced_at"),
                                source_detected_at=ann.get("source_detected_at"), effective_at=eff,
                                source_event_id=sev, raw=raw)
            result["obs"].append(obs_id)
            for acc in accs:
                ctx = {"source_id": source_id, "obs_id": obs_id, "observed_at": observed_at,
                       "announced_at": ann.get("announced_at"), "source_detected_at": ann.get("source_detected_at"),
                       "effective_at": eff, "provisional": not official, "fiat_tier": n["fiat_tier"],
                       "group_key": f"ann:{source_id}:{sev}:{n['asset_key']}"}
                e = _announcement_step(conn, acc, action, ctx, official, " (quote wildcard)" if wildcard else "")
                if e is REJECTED:
                    result["rejected"] += 1
                elif e is not None and e not in result["events"]:
                    result["events"].append(e)
    return result


def process_due(conn, at=None):
    """Apply official delistings whose effective time has passed (works without any snapshot source)."""
    at = at or now_ms()
    out = []
    with _tx(conn):
        rows = conn.execute("""SELECT * FROM access_state WHERE pending_removal_at IS NOT NULL AND pending_removal_at<=?
                               AND status IN ('ANNOUNCED','LIVE','SUSPENDED')""", (at,)).fetchall()
        for acc in rows:
            acc = dict(acc)
            o = _one(conn, f"""SELECT o.obs_id, o.source_id FROM source_observation o JOIN source s ON s.source_id=o.source_id
                               WHERE o.action='DELISTING' AND s.tier IN ('OFFICIAL_STRUCTURED','OFFICIAL_ANNOUNCEMENT')
                               AND (o.access_id=? OR ({_WILDCARD_OBS_SQL}))
                               ORDER BY o.obs_id DESC LIMIT 1""",
                     (acc["access_id"], *(acc[f] for f in _WILDCARD_DIMS)))
            if not o:
                continue
            ctx = {"source_id": o["source_id"], "observed_at": at, "effective_at": acc["pending_removal_at"],
                   "provisional": False}
            e = _apply(conn, acc, "REMOVED", ctx, reason="scheduled official delisting reached effective_at")
            if e not in (None, REJECTED):
                out.append(e)
    return out


# ----------------------------------------------------------------------------- adapter helper mappers
def map_upbit_market(m):
    """Upbit /v1/market/all item {'market': 'KRW-BTC', ...} -> SPOT item."""
    quote, sym = m["market"].split("-", 1)
    return {"platform_id": "upbit", "symbol": sym, "quote": quote, "access_kind": "SPOT", "status": "LIVE",
            "native_id": m["market"], "raw": m}


def map_coinone_market(m):
    """Coinone /public/v2/markets/{quote}: trade_status 1|3 -> LIVE, 0|2 -> SUSPENDED; maintenance_status 1 -> SUSPENDED.
    (Mapping as agreed in the design review; re-verify value meanings when the adapter is written.)"""
    ts = int(m.get("trade_status", 1))
    status = "LIVE" if ts in (1, 3) else "SUSPENDED"
    if int(m.get("maintenance_status", 0) or 0) == 1:
        status = "SUSPENDED"
    return {"platform_id": "coinone", "symbol": m["target_currency"], "quote": m["quote_currency"],
            "access_kind": "SPOT", "status": status, "native_id": f"{m['target_currency']}-{m['quote_currency']}",
            "raw": m}


def map_korbit_pair(p):
    """Korbit /v2/currencyPairs {'symbol': 'btc_krw', 'status': 'launched'|'stopped'}; stopped -> SUSPENDED."""
    sym, quote = p["symbol"].upper().split("_", 1)
    return {"platform_id": "korbit", "symbol": sym, "quote": quote, "access_kind": "SPOT",
            "status": "SUSPENDED" if p.get("status") == "stopped" else "LIVE", "native_id": p["symbol"], "raw": p}


def map_ramp_asset(a, fiat, country=""):
    """Ramp host-api assets, fetched WITH withDisabled=true&withHidden=true so disabled items stay visible.
    enabled=false -> SUSPENDED (not REMOVED); hidden=true -> SUSPENDED (judgment call, see STATE_MACHINE.md)."""
    chain = _s(a.get("chain")).lower()
    sym = _s(a.get("symbol"))
    if chain and sym.upper().startswith(chain.upper() + "_"):
        sym = sym[len(chain) + 1:]
    status = "LIVE" if a.get("enabled", True) and not a.get("hidden", False) else "SUSPENDED"
    return {"platform_id": "ramp", "symbol": sym, "access_kind": "FIAT_ROUTE", "fiat": fiat, "quote": fiat,
            "country": country, "network": chain, "fiat_tier": "SUPPORTED", "status": status,
            "chain": chain, "contract": a.get("address") or "", "raw": a}


# ----------------------------------------------------------------------------- feed / CLI
LOCAL_TZ = timezone(timedelta(hours=8))   # user timezone (Asia/Shanghai)
LOCAL_LABEL = "UTC+8"


def parse_since(s):
    m = re.fullmatch(r"\s*(\d+)\s*([smhdw])\s*", s or "")
    if not m:
        raise ValueError(f"bad --since {s!r} (use e.g. 90m, 24h, 3d)")
    return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[m.group(2)] * 1000


def fmt_ts(ms):
    if ms is None:
        return "-"
    return datetime.fromtimestamp(ms / 1000, LOCAL_TZ).strftime("%m-%d %H:%M:%S")


def recent_events(conn, since_ms, now=None, include_retracted=False):
    """Events whose episode started, or was last updated, within the window."""
    cutoff = (now or now_ms()) - since_ms
    sql = """SELECT f.* FROM v_recent_feed f JOIN access_event e ON e.event_id = f.event_id
             WHERE (e.anchor_at >= ? OR e.updated_at >= ?)"""
    if not include_retracted:
        sql += " AND e.retracted = 0"
    sql += " ORDER BY f.anchor_at DESC, f.event_id DESC"
    return [dict(r) for r in conn.execute(sql, (cutoff, cutoff))]


def print_feed(conn, since, out=None, as_json=False, include_retracted=False):
    out = out or sys.stdout
    evs = recent_events(conn, parse_since(since), include_retracted=include_retracted)
    if as_json:
        json.dump(evs, out, ensure_ascii=False, indent=1)
        out.write("\n")
        return evs
    out.write(f"Recent Access Radar — last {since}: {len(evs)} events (times in {LOCAL_LABEL})\n")
    hdr = (f"{'time':14} {'event_type':28} {'platform':9} {'asset':12} {'quote':5} {'from->to':19} "
           f"{'conf':>5} {'src':>3} {'flag':4} effective")
    out.write(hdr + "\n" + "-" * len(hdr) + "\n")
    for e in evs:
        flags = ("P" if e["provisional"] else "") + ("R" if e["retracted"] else "")
        eff = fmt_ts(e["effective_at"]) if e["effective_at"] else "-"
        out.write(f"{fmt_ts(e['anchor_at']):14} {e['event_type'][:28]:28} {e['platform_id'][:9]:9} "
                  f"{e['asset_key'][:12]:12} {e['quote'][:5]:5} {(e['from_status'] + '->' + e['to_status'])[:19]:19} "
                  f"{e['confidence']:5.2f} {e['independent_source_count']:3d} {flags:4} {eff}\n")
    out.write("flags: P=provisional R=retracted; src=independent source groups\n")
    return evs


def print_health(conn, out=None):
    out = out or sys.stdout
    out.write(f"{'source':16} {'scope':8} {'status':9} {'size':>5} {'baseline':8} last_error\n")
    for r in conn.execute("SELECT * FROM source_health ORDER BY source_id, scope"):
        out.write(f"{r['source_id'][:16]:16} {r['scope'][:8]:8} {r['status']:9} {str(r['last_snapshot_size']):>5} "
                  f"{'yes' if r['baseline_done'] else 'no':8} {r['last_error'][:60]}\n")


def run_demo(conn, base=None):
    """Populate a db with a simulated Korea + on-ramp scenario over the last ~30h (no network)."""
    H = 3600 * 1000
    now = base or now_ms()
    t0 = now - 30 * H
    for pid, ptype in (("upbit", "CEX"), ("bithumb", "CEX"), ("coinone", "CEX"), ("korbit", "CEX"),
                       ("ramp", "ONRAMP"), ("newlistings", "DATA_VENDOR")):
        register_platform(conn, pid, pid.capitalize(), ptype, "KR" if ptype == "CEX" else "")
    register_source(conn, "upbit_market", tier="OFFICIAL_STRUCTURED", origin_platform_id="upbit")
    register_source(conn, "upbit_notice", kind="ANNOUNCEMENT", tier="OFFICIAL_ANNOUNCEMENT", origin_platform_id="upbit")
    register_source(conn, "coinone_market", tier="OFFICIAL_STRUCTURED", origin_platform_id="coinone")
    register_source(conn, "korbit_pairs", tier="OFFICIAL_STRUCTURED", origin_platform_id="korbit")
    register_source(conn, "ramp_assets", tier="OFFICIAL_STRUCTURED", origin_platform_id="ramp")
    register_source(conn, "newlistings", kind="ANNOUNCEMENT", tier="THIRD_PARTY", is_relay=True)

    base_syms = ["BTC", "ETH", "XRP", "SOL", "DOGE", "ADA", "TRX", "LINK", "AVAX", "DOT", "SUI", "APT"]

    def upbit(syms):
        return [map_upbit_market({"market": f"KRW-{s}"}) for s in syms]

    def coin(over=None):
        return [map_coinone_market({"target_currency": s, "quote_currency": "KRW",
                                    "trade_status": (over or {}).get(s, 1), "maintenance_status": 0}) for s in base_syms]

    def korbit(stopped=()):
        return [map_korbit_pair({"symbol": f"{s.lower()}_krw", "status": "stopped" if s in stopped else "launched"})
                for s in base_syms]

    def ramp(dis=()):
        return [map_ramp_asset({"symbol": s, "chain": "SOLANA" if s in ("USDC", "SOL") else "ETHEREUM",
                                "enabled": s not in dis}, "EUR") for s in ("USDC", "USDT", "ETH", "SOL", "LINK")]

    ingest_snapshot(conn, "upbit_market", "KRW", upbit(base_syms), fetched_at=t0)
    ingest_snapshot(conn, "coinone_market", "KRW", coin(), fetched_at=t0)
    ingest_snapshot(conn, "korbit_pairs", "KRW", korbit(), fetched_at=t0)
    ingest_snapshot(conn, "ramp_assets", "EUR", ramp(), fetched_at=t0)

    # REZ: NewListings relays the Upbit notice (3s delay), the notice itself arrives, then the market appears.
    ta = now - 6 * H
    ingest_announcement(conn, "newlistings", {"action": "LISTING", "platform_id": "upbit", "symbol": "REZ", "quote": "KRW",
                                              "origin_group": "upbit_notice", "announced_at": ta,
                                              "source_detected_at": ta + 3000, "observed_at": ta + 3500,
                                              "source_event_id": "nl:upbit:REZ:LISTING:KRW"})
    ingest_announcement(conn, "upbit_notice", {"action": "LISTING", "platform_id": "upbit", "symbol": "REZ", "quote": "KRW",
                                               "announced_at": ta, "observed_at": ta + 900, "effective_at": ta + 2 * H,
                                               "source_event_id": "upbit:notice:5101",
                                               "title": "Renzo(REZ) KRW market listing"})
    ingest_snapshot(conn, "upbit_market", "KRW", upbit(base_syms + ["REZ"]), fetched_at=ta + 2 * H + 4000)
    # Announcement only (market not open yet): ZORA on Upbit, no quote given (wildcard).
    ingest_announcement(conn, "upbit_notice", {"action": "LISTING", "platform_id": "upbit", "symbol": "ZORA",
                                               "announced_at": now - 1 * H, "observed_at": now - 1 * H + 800,
                                               "effective_at": now + 3 * H, "source_event_id": "upbit:notice:5130"})
    # Coinone halts DOT (trade_status 0), Korbit stops APT.
    ingest_snapshot(conn, "coinone_market", "KRW", coin({"DOT": 0}), fetched_at=now - 4 * H)
    ingest_snapshot(conn, "korbit_pairs", "KRW", korbit(stopped=("APT",)), fetched_at=now - 4 * H)
    # Ramp disables LINK (SUSPENDED, not REMOVED) and a SUI/EUR route appears.
    items = ramp(dis=("LINK",)) + [map_ramp_asset({"symbol": "SUI", "chain": "SUI", "enabled": True}, "EUR")]
    ingest_snapshot(conn, "ramp_assets", "EUR", items, fetched_at=now - 3 * H)
    # Scheduled official delisting of TRX on Upbit, effective in 5 days.
    ingest_announcement(conn, "upbit_notice", {"action": "DELISTING", "platform_id": "upbit", "symbol": "TRX",
                                               "quote": "KRW", "announced_at": now - 2 * H,
                                               "observed_at": now - 2 * H + 700, "effective_at": now + 5 * 24 * H,
                                               "source_event_id": "upbit:notice:5122"})
    # A degraded snapshot (API returned 0 rows) must not remove anything; then recovery.
    ingest_snapshot(conn, "upbit_market", "KRW", [], fetched_at=now - 30 * 60 * 1000)
    ingest_snapshot(conn, "upbit_market", "KRW", upbit(base_syms + ["REZ"]), fetched_at=now - 10 * 60 * 1000)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="radar_core.py", description="Recent Access Radar core CLI")
    ap.add_argument("--db", default=default_db_path(),
                    help="default: $ACCESS_DB, else $ACCESS_RADAR_DB (legacy), else access_radar/access.sqlite")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create/upgrade the database from schema.sql")
    f = sub.add_parser("feed", help="print recent canonical events")
    f.add_argument("--since", default="24h")
    f.add_argument("--json", action="store_true")
    f.add_argument("--all", action="store_true", help="include retracted events")
    sub.add_parser("health", help="print source health per (source, scope)")
    sub.add_parser("tick", help="apply scheduled official delistings whose effective_at has passed")
    d = sub.add_parser("demo", help="build a demo db with simulated data, then print feed + health")
    d.add_argument("--reset", action="store_true", help="delete the db file first")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    if a.cmd == "demo" and a.reset:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(a.db + suffix):
                os.remove(a.db + suffix)
    conn = init_db(a.db)
    if a.cmd == "init":
        print(f"initialised {a.db}")
    elif a.cmd == "feed":
        print_feed(conn, a.since, as_json=a.json, include_retracted=a.all)
    elif a.cmd == "health":
        print_health(conn)
    elif a.cmd == "tick":
        print(f"applied {len(process_due(conn))} scheduled removals")
    elif a.cmd == "demo":
        if conn.execute("SELECT COUNT(*) FROM source").fetchone()[0]:
            print("db already has data; use --reset or another --db path", file=sys.stderr)
            conn.close()
            return 2
        run_demo(conn)
        print_feed(conn, "48h")
        print()
        print_health(conn)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
