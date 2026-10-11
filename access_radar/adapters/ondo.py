"""Ondo Finance adapter — tokenized treasuries (USDY, OUSG, ...).

Ondo has no public asset-list API: the issuer API needs onboarding (allow-listed key), so this
adapter is wired for it in advance.  Enable it with two environment variables:

    ONDO_API_URL   asset-list endpoint returning JSON (list, or {"assets": [...]})
    ONDO_API_KEY   sent as 'Authorization: Bearer <key>'

Without credentials the run reports a clear error every cycle (source_run.last_error carries the
env var names; nothing is ingested, nothing is removed).

Expected item shape (unverified until onboarding — adjust the mapper when the real schema is known;
the mapper is deliberately tolerant of the usual variants):
    {"symbol": "USDY", "name": "Ondo US Dollar Yield", "status": "live",
     "deployments": [{"chain": "ethereum", "address": "0x..."}]}
with fallbacks: chains/networks + contract/address instead of deployments; isSuspended or
status in (suspended|paused|closed|halted) -> SUSPENDED.

Two scopes on source ondo_assets (OFFICIAL_STRUCTURED, platform ondo, ISSUER):
  * "catalog"      one CATALOG item per asset, quote USD
  * "deployments"  one CHAIN_DEPLOYMENT item per (asset, chain); the global asset tables are
                   upserted too (asset_key ondo:<SYM>, TREASURY) so contracts resolve cross-source.
"""
import os
import sys

if __package__ in (None, ""):                                    # direct script run
    sys.path.insert(0, __file__.rsplit("/", 2)[0])

import radar_core as rc

try:
    from .chains import canonical_chain
except ImportError:                                              # direct script run
    from chains import canonical_chain  # noqa: E402
try:
    from ._fetch import default_fetch
except ImportError:                                              # direct script run
    from _fetch import default_fetch  # noqa: E402

PLATFORM_ID = "ondo"
SOURCE_ID = "ondo_assets"
SCOPE_CATALOG = "catalog"
SCOPE_DEPLOY = "deployments"
ENV_URL = "ONDO_API_URL"
ENV_KEY = "ONDO_API_KEY"
SUSPENDED_STATES = ("suspended", "paused", "closed", "halted", "disabled")


class BadResponse(Exception):
    pass


def asset_key(sym):
    return f"ondo:{sym}"


def register(conn, at=None):
    rc.register_platform(conn, PLATFORM_ID, "Ondo Finance", "ISSUER", "", at=at)
    rc.register_source(conn, SOURCE_ID, name="Ondo issuer API (needs onboarding)", kind="SNAPSHOT",
                       tier="OFFICIAL_STRUCTURED", origin_platform_id=PLATFORM_ID, at=at)


def read_credentials(env=None):
    """-> (url, key) or None. env override for tests."""
    env = os.environ if env is None else env
    url = (env.get(ENV_URL) or "").strip().rstrip("/")
    key = (env.get(ENV_KEY) or "").strip()
    return (url, key) if url and key else None


def fetch_assets(url, key, fetch):
    d = fetch(url, headers={"Authorization": f"Bearer {key}"})
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ("assets", "data", "products", "items", "result"):
            if isinstance(d.get(k), list):
                return d[k]
    raise BadResponse("unexpected response shape: no asset list found")


def map_item(n):
    """-> (catalog_item, [deploy_items]). An item without a symbol becomes an invalid marker."""
    if not isinstance(n, dict):
        return {"access_kind": "CATALOG"}, []
    sym = str(n.get("symbol") or n.get("ticker") or "").strip().upper()
    if not sym:
        return {"access_kind": "CATALOG"}, []
    st = str(n.get("status") or "").strip().lower()
    status = "SUSPENDED" if (n.get("isSuspended") or st in SUSPENDED_STATES) else "LIVE"
    slim = {k: n[k] for k in ("symbol", "name", "status") if n.get(k) is not None}
    catalog = {"platform_id": PLATFORM_ID, "asset_key": asset_key(sym), "symbol": sym,
               "access_kind": "CATALOG", "status": status, "quote": "USD", "native_id": sym,
               "raw": slim}
    deploys = []
    deps = list(n.get("deployments") or [])
    addr = n.get("contract") or n.get("address") or ""
    if not deps and addr:
        chains = n.get("chains") or n.get("networks")
        cl = [c for c in chains if isinstance(c, str) and c] if isinstance(chains, list) else []
        if cl:                                                       # chains: ["ethereum", "solana"]
            deps = [{"chain": c, "address": addr} for c in cl]
        else:
            deps = [{"chain": n.get("chain") or n.get("network") or "", "address": addr}]
    for d in deps:
        if not isinstance(d, dict):
            continue
        chain = canonical_chain(d.get("chain") or d.get("network") or "")
        addr = d.get("address") or d.get("contract") or ""
        if not chain or not addr:
            continue
        deploys.append({"platform_id": PLATFORM_ID, "asset_key": asset_key(sym), "symbol": sym,
                        "access_kind": "CHAIN_DEPLOYMENT", "status": status, "network": chain,
                        "chain": chain, "contract": addr, "native_id": f"{sym}:{chain}",
                        "raw": {"symbol": sym, "chain": chain, "address": addr}})
    return catalog, deploys


def upsert_assets(conn, mapped, at=None):
    """Global assets + deployments for every mapped item (one transaction)."""
    with rc._tx(conn):
        for catalog, deps in mapped:
            if "symbol" not in catalog:
                continue
            aid = rc.upsert_asset(conn, catalog["asset_key"], "TREASURY", catalog["symbol"], issuer="ondo",
                                  at=at)
            for d in deps:
                rc.add_deployment(conn, aid, d["chain"], d["contract"], at=at)


def run_once(conn, fetch=None, fetched_at=None):
    fetched_at = fetched_at or rc.now_ms()
    creds = read_credentials()
    if not creds:
        msg = (f"{ENV_URL}/{ENV_KEY} not set: Ondo has no public asset-list API (issuer key needs "
               f"onboarding). Set both env vars to enable this source.")
        rc.report_fetch_error(conn, SOURCE_ID, SCOPE_CATALOG, msg, at=fetched_at)
        rc.report_fetch_error(conn, SOURCE_ID, SCOPE_DEPLOY, msg, at=fetched_at)
        return {"error": msg}
    url, key = creds
    try:
        nodes = fetch_assets(url, key, fetch or default_fetch)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        for scope in (SCOPE_CATALOG, SCOPE_DEPLOY):
            rc.report_fetch_error(conn, SOURCE_ID, scope, msg, at=fetched_at)
        return {"error": msg}
    mapped = [map_item(n) for n in nodes]
    upsert_assets(conn, mapped, at=fetched_at)
    catalog = [c for c, _ in mapped]
    deploys = [d for _, ds in mapped for d in ds]
    return {
        SCOPE_CATALOG: rc.ingest_snapshot(conn, SOURCE_ID, SCOPE_CATALOG, catalog, fetched_at=fetched_at),
        SCOPE_DEPLOY: rc.ingest_snapshot(conn, SOURCE_ID, SCOPE_DEPLOY, deploys, fetched_at=fetched_at),
    }


if __name__ == "__main__":
    import json
    creds = read_credentials()
    if not creds:
        print(f"ondo: {ENV_URL}/{ENV_KEY} not set — nothing to fetch")
    else:
        conn = rc.init_db(":memory:")
        print(json.dumps(run_once(conn), indent=1, default=str)[:600])
