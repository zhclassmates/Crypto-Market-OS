"""xStocks (Backed) adapter — public v2 API, no key.

GET https://api.xstocks.fi/api/v2/public/assets?pageSize=100&page=N  ->  {"nodes": [...100], "page": {"currentPage", "hasNextPage"}}
Each node: id, symbol ('AAPLx'), name, isin, underlyingSymbol, isTradingHalted, trading{...}, deployments[{network, address, ...}].

Two snapshot scopes on source `xstocks_assets` (OFFICIAL_STRUCTURED, platform `xstocks`, ISSUER):
  * scope "catalog"      one CATALOG item per asset          -> CATALOG_ADDED when a new xStock appears
  * scope "deployments"  one CHAIN_DEPLOYMENT item per (asset, chain) -> CHAIN_DEPLOYED when it lands on a new chain
isTradingHalted=true -> SUSPENDED on both (never REMOVED; removal is left to radar_core's miss counting).
Both scopes are kept as one list each so a whole-catalog rollout to a new chain is a size jump that radar_core
accepts after SIZE_ACCEPT_AFTER consistent polls and then diffs, instead of being swallowed by a fresh baseline.

The full list is paginated; a snapshot is only ingested when every page arrived and no asset id repeated
(pagination shifted mid-crawl). Otherwise report_fetch_error, so a partial list can never look like removals.
Each asset is also upserted as asset_key 'xstocks:<symbol>' (TOKENIZED_STOCK, issuer 'backed') with its
deployments, so other sources (GMGN, DEX lists) resolve to it by exact (chain, contract).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from .chains import canonical_chain  # noqa: E402
from ._fetch import default_fetch  # noqa: E402

BASE_URL = "https://api.xstocks.fi/api/v2/public/assets"
PLATFORM_ID = "xstocks"
SOURCE_ID = "xstocks_assets"
SCOPE_CATALOG = "catalog"
SCOPE_DEPLOY = "deployments"
PAGE_SIZE = 100          # API default; bodies are ~600 KB raw but ~35 KB gzipped via access_http
MAX_PAGES = 200          # hard stop (~20k assets); hitting it means the API changed -> fetch error
PAGE_PAUSE_S = 0.25      # be polite between pages when using the default fetcher


class IncompleteSnapshot(Exception):
    pass


def register(conn, at=None):
    rc.register_platform(conn, PLATFORM_ID, "xStocks", "ISSUER", "", at=at)
    rc.register_source(conn, SOURCE_ID, name="xStocks public assets v2", kind="SNAPSHOT",
                       tier="OFFICIAL_STRUCTURED", origin_platform_id=PLATFORM_ID, at=at)


def asset_key(node):
    return f"xstocks:{node['symbol']}"


def fetch_all(fetch=None, max_pages=MAX_PAGES, pause_s=None, page_size=PAGE_SIZE):
    """Crawl every page. Returns list of nodes; raises IncompleteSnapshot on any gap or duplicate."""
    fetch = fetch or default_fetch
    if pause_s is None:
        pause_s = PAGE_PAUSE_S if fetch is default_fetch else 0
    nodes, ids = [], set()
    for page in range(max_pages):
        d = fetch(f"{BASE_URL}?pageSize={page_size}&page={page}")
        if not isinstance(d, dict) or not isinstance(d.get("nodes"), list) or not isinstance(d.get("page"), dict):
            raise IncompleteSnapshot(f"unexpected response shape on page {page}")
        if d["page"].get("currentPage", page) != page:
            raise IncompleteSnapshot(f"asked page {page}, got {d['page'].get('currentPage')}")
        for n in d["nodes"]:
            nid = n.get("id") or n.get("symbol")
            if nid in ids:
                raise IncompleteSnapshot(f"duplicate asset {n.get('symbol')} on page {page}: pagination shifted")
            ids.add(nid)
            nodes.append(n)
        if not d["page"].get("hasNextPage"):
            return nodes
        if pause_s:
            time.sleep(pause_s)
    raise IncompleteSnapshot(f"more than {max_pages} pages")


def map_nodes(nodes):
    """-> (catalog_items, deployment_items). Pure; no DB access."""
    catalog, deploys = [], []
    for n in nodes:
        sym = (n.get("symbol") or "").strip()
        if not sym:
            catalog.append({"access_kind": "CATALOG"})   # counted as invalid by radar_core's schema gate
            continue
        halted = bool(n.get("isTradingHalted") or (n.get("trading") or {}).get("isTradingHalted"))
        status = "SUSPENDED" if halted else "LIVE"
        key = asset_key(n)
        slim = {k: n.get(k) for k in ("id", "symbol", "name", "isin", "underlyingSymbol", "isTradingHalted")}
        catalog.append({"platform_id": PLATFORM_ID, "asset_key": key, "symbol": sym, "access_kind": "CATALOG",
                        "status": status, "quote": "USD", "native_id": n.get("id") or "", "raw": slim})
        for dep in n.get("deployments") or []:
            chain = canonical_chain(dep.get("network"))
            if not chain:
                continue
            deploys.append({"platform_id": PLATFORM_ID, "asset_key": key, "symbol": sym,
                            "access_kind": "CHAIN_DEPLOYMENT", "status": status, "network": chain,
                            "chain": chain, "contract": dep.get("address") or "",
                            "native_id": f"{n.get('id') or sym}:{chain}",
                            "raw": {"symbol": sym, "network": dep.get("network"), "address": dep.get("address")}})
    return catalog, deploys


def upsert_assets(conn, nodes, at=None):
    """Register each xStock and its deployments in the global asset tables (one transaction)."""
    with rc._tx(conn):
        for n in nodes:
            sym = (n.get("symbol") or "").strip()
            if not sym:
                continue
            aid = rc.upsert_asset(conn, asset_key(n), "TOKENIZED_STOCK", sym, name=n.get("name") or "",
                                  issuer="backed", underlying=n.get("underlyingSymbol") or "",
                                  product_id=n.get("id") or "", at=at)
            for dep in n.get("deployments") or []:
                chain = canonical_chain(dep.get("network"))
                if chain and dep.get("address"):
                    rc.add_deployment(conn, aid, chain, dep["address"], at=at)


def run_once(conn, fetch=None, fetched_at=None):
    """One poll. Returns {'catalog': ingest result, 'deployments': ingest result} or {'error': msg}."""
    fetched_at = fetched_at or rc.now_ms()
    try:
        nodes = fetch_all(fetch)
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}: {e}"
        for scope in (SCOPE_CATALOG, SCOPE_DEPLOY):
            rc.report_fetch_error(conn, SOURCE_ID, scope, msg, at=fetched_at)
        return {"error": msg}
    upsert_assets(conn, nodes, at=fetched_at)
    catalog, deploys = map_nodes(nodes)
    return {
        "catalog": rc.ingest_snapshot(conn, SOURCE_ID, SCOPE_CATALOG, catalog, fetched_at=fetched_at,
                                      raw=[i["raw"] for i in catalog if "raw" in i]),
        "deployments": rc.ingest_snapshot(conn, SOURCE_ID, SCOPE_DEPLOY, deploys, fetched_at=fetched_at),
    }
