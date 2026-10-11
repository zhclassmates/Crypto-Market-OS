"""Superstate adapter — USTB / USCC public NAV + the funds' chain deployments.

GET https://api.superstate.com/v1/funds/{1|2}/nav-daily
    -> [{"fund_id": 1, "net_asset_value_date": "10/09/2026", "net_asset_value": "11.23775100",
         "subscription_nav_per_share": null, "assets_under_management": "796673401.1600",
         "outstanding_shares": "70892601.300741", "net_income_expenses": "..."}, ...]
Public, no key, newest record first (USTB ~1000 daily records, USCC ~800).

Conn-style adapter on source superstate_funds (OFFICIAL_STRUCTURED, platform superstate, ISSUER).
Two scopes:
  * "catalog"      one CATALOG item per fund, quote USD, latest NAV/AUM in raw -> a new fund
                   (Superstate launches a third vehicle) produces a CATALOG_ADDED event.
  * "deployments"  one CHAIN_DEPLOYMENT item per (fund, chain) from the static contract registry
                   below; the same contracts are written to the global asset tables via
                   upsert_asset + add_deployment so other sources resolve them by exact contract.

Any fund endpoint failing -> both scopes DOWN (a partial list must never look like a removal).
The registry below is the only hardcoded part: NAV data is live, contract additions by Superstate
surface as a code change here (the public NAV API does not expose token addresses).
"""
import sys
from datetime import datetime, timezone

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

BASE_URL = "https://api.superstate.com/v1/funds/{fund_id}/nav-daily"
PLATFORM_ID = "superstate"
SOURCE_ID = "superstate_funds"
SCOPE_CATALOG = "catalog"
SCOPE_DEPLOY = "deployments"

# fund_id -> (symbol, name, asset_type, underlying, [(chain, contract), ...])
FUNDS = {
    1: ("USTB", "Superstate USTB", "TREASURY", "UST",
        [("ethereum", "0x43415eB6ff9DB7E26A15b704e7A3eDCe97d31C4e")]),
    2: ("USCC", "Superstate USCC", "FUND", "",
        [("ethereum", "0x14d60e7fdc0d71d8611742720e4c50e7a974020c"),
         ("solana", "BTRR3sj1Bn2ZjuemgbeQ6SCtf84iXS81CS7UDTSxUCaK"),
         ("plume", "0x4c21b7577c8fe8b0b0669165ee7c8f67fa1454cf")]),
}


class BadResponse(Exception):
    pass


def asset_key(sym):
    return f"superstate:{sym}"


def register(conn, at=None):
    rc.register_platform(conn, PLATFORM_ID, "Superstate", "ISSUER", "", at=at)
    rc.register_source(conn, SOURCE_ID, name="Superstate public NAV (nav-daily)", kind="SNAPSHOT",
                       tier="OFFICIAL_STRUCTURED", origin_platform_id=PLATFORM_ID, at=at)


def _nav_date_ms(s):
    try:
        return int(datetime.strptime(str(s).strip(), "%m/%d/%Y")
                   .replace(tzinfo=timezone.utc).timestamp() * 1000)
    except ValueError:
        return None


def fetch_nav(fund_id, fetch):
    """-> daily NAV records (list). Raises BadResponse / transport."""
    d = fetch(BASE_URL.format(fund_id=fund_id))
    if not isinstance(d, list) or not d:
        raise BadResponse(f"fund {fund_id}: unexpected nav-daily response ({type(d).__name__})")
    first = d[0] if isinstance(d[0], dict) else {}
    if first.get("fund_id") not in (None, fund_id):
        raise BadResponse(f"fund {fund_id}: response fund_id is {first.get('fund_id')!r}")
    if _nav_date_ms(first.get("net_asset_value_date")) is None:
        raise BadResponse(f"fund {fund_id}: first record has no parsable net_asset_value_date")
    return d


def _num(rec, *keys):
    for k in keys:
        v = rec.get(k)
        if v not in (None, ""):
            return v
    return ""


def map_items(nav_by_fund):
    """-> (catalog_items, deploy_items). Pure: FUNDS + fetched NAVs -> snapshot items."""
    catalog, deploys = [], []
    for fund_id, (sym, name, _atype, _underlying, contracts) in FUNDS.items():
        navs = nav_by_fund.get(fund_id) or []
        latest = navs[0] if navs and isinstance(navs[0], dict) else {}
        catalog.append({"platform_id": PLATFORM_ID, "asset_key": asset_key(sym), "symbol": sym,
                        "access_kind": "CATALOG", "status": "LIVE", "quote": "USD",
                        "native_id": f"superstate:{fund_id}",
                        "raw": {"fund_id": fund_id, "name": name,
                                "nav_date": latest.get("net_asset_value_date") or "",
                                "nav": _num(latest, "net_asset_value"),
                                "sub_nav": _num(latest, "subscription_nav_per_share"),
                                "aum": _num(latest, "assets_under_management"),
                                "outstanding_shares": _num(latest, "outstanding_shares")}})
        for chain, contract in contracts:
            deploys.append({"platform_id": PLATFORM_ID, "asset_key": asset_key(sym), "symbol": sym,
                            "access_kind": "CHAIN_DEPLOYMENT", "status": "LIVE",
                            "network": canonical_chain(chain), "chain": canonical_chain(chain),
                            "contract": contract, "native_id": f"{sym}:{chain}",
                            "raw": {"symbol": sym, "chain": chain, "address": contract}})
    return catalog, deploys


def upsert_assets(conn, at=None):
    """Register every fund + its contracts in the global asset tables (one transaction)."""
    with rc._tx(conn):
        for _fund_id, (sym, name, atype, underlying, contracts) in FUNDS.items():
            aid = rc.upsert_asset(conn, asset_key(sym), atype, sym, name=name, issuer="superstate",
                                  underlying=underlying, product_id=str(_fund_id), at=at)
            for chain, contract in contracts:
                rc.add_deployment(conn, aid, canonical_chain(chain), contract, at=at)


def run_once(conn, fetch=None, fetched_at=None):
    """-> {scope: ingest 结果}，任一 fund 失败 -> {"error": msg}（两个 scope 都记 DOWN）。"""
    fetched_at = fetched_at or rc.now_ms()
    fetch = fetch or default_fetch
    nav_by_fund, errors = {}, []
    for fund_id in FUNDS:
        try:
            nav_by_fund[fund_id] = fetch_nav(fund_id, fetch)
        except Exception as e:
            errors.append(f"fund {fund_id}: {type(e).__name__}: {e}")
    if errors:
        msg = "; ".join(errors)
        for scope in (SCOPE_CATALOG, SCOPE_DEPLOY):
            rc.report_fetch_error(conn, SOURCE_ID, scope, msg, at=fetched_at)
        return {"error": msg}
    upsert_assets(conn, at=fetched_at)
    catalog, deploys = map_items(nav_by_fund)
    return {
        SCOPE_CATALOG: rc.ingest_snapshot(conn, SOURCE_ID, SCOPE_CATALOG, catalog, fetched_at=fetched_at),
        SCOPE_DEPLOY: rc.ingest_snapshot(conn, SOURCE_ID, SCOPE_DEPLOY, deploys, fetched_at=fetched_at),
    }


if __name__ == "__main__":
    import json
    conn = rc.init_db(":memory:")
    register(conn)
    print(json.dumps(run_once(conn), indent=1, default=str)[:600])
    conn.close()
