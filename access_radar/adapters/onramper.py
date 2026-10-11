"""Onramper adapter — global buy-side coverage from /supported (aggregator).

GET https://api.onramper.com/supported?type=buy&skipCountryCheck=true
    header 'Authorization: <key>' (pk_prod_..., verbatim — no Bearer prefix). Key comes from env
    ONRAMPER_API_KEY (dashboard.onramper.com); without it the run reports a clear error every
    cycle and nothing is ingested.

    skipCountryCheck=true returns the unfiltered global lists, so the crypto list is
    fiat-independent and the (crypto, fiat) cross product is uniform per fiat.

Response shape (documented by Onramper; not verifiable without a key — the mapper fails loudly
with BadResponse if the shape ever changes):
    {"crypto": [{"code"|"symbol"|"id", "network", "isSuspended", "contracts": [...], ...}, ...],
     "fiats":  [{"code", ...}, ...]}

One FIAT_ROUTE item per (crypto-network, fiat) at fiat_tier SUPPORTED (the lists say 'in the
catalog', not 'confirmed quoteable'), scope per fiat — same convention as ramp_assets.  Only
DEFAULT_FIATS are ingested (override with ONRAMPER_FIATS=comma,list): ingesting every fiat would
multiply identical rows without adding information.

Source tier AGGREGATOR (Onramper aggregates ramps): adds need a second observation to confirm,
per radar_core's add_confirm_obs rules.
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

PLATFORM_ID = "onramper"
SOURCE_ID = "onramper_routes"
SUPPORTED_URL = "https://api.onramper.com/supported"
DEFAULT_FIATS = ("USD", "EUR", "GBP")
ENV_KEY = "ONRAMPER_API_KEY"
ENV_FIATS = "ONRAMPER_FIATS"


class BadResponse(Exception):
    pass


def register(conn, at=None):
    rc.register_platform(conn, PLATFORM_ID, "Onramper", "ONRAMP", "", at=at)
    rc.register_source(conn, SOURCE_ID, name="Onramper /supported (global buy list)", kind="SNAPSHOT",
                       tier="AGGREGATOR", origin_platform_id=PLATFORM_ID, at=at)


def read_key(env=None):
    env = os.environ if env is None else env
    return (env.get(ENV_KEY) or "").strip()


def configured_fiats():
    raw = os.environ.get(ENV_FIATS, "")
    return tuple(s.strip().upper() for s in raw.split(",") if s.strip()) or DEFAULT_FIATS


def fetch_supported(fetch, key=None):
    """-> /supported payload dict. Raises MissingKey / BadResponse / transport."""
    key = key if key is not None else read_key()
    if not key:
        raise BadResponse(f"{ENV_KEY} not set: Onramper needs a production key "
                          f"(https://dashboard.onramper.com)")
    d = fetch(f"{SUPPORTED_URL}?type=buy&skipCountryCheck=true", headers={"Authorization": key})
    if not (isinstance(d, dict) and isinstance(d.get("crypto"), list) and isinstance(d.get("fiats"), list)):
        raise BadResponse("unexpected /supported shape (want {'crypto': [...], 'fiats': [...]})")
    return d


def _contract_for(c, chain):
    cs = c.get("contracts")
    if isinstance(cs, list):
        for e in cs:
            if isinstance(e, dict) and e.get("contract") and canonical_chain(e.get("chain") or "") == chain:
                return e["contract"]
    return c.get("contract") or c.get("address") or ""


def map_crypto(c):
    """-> item template without the fiat fields; no symbol -> invalid marker for the schema gate."""
    if not isinstance(c, dict):
        return {"access_kind": "FIAT_ROUTE"}
    sym = str(c.get("code") or c.get("symbol") or c.get("id") or "").strip().upper()
    if not sym:
        return {"access_kind": "FIAT_ROUTE"}
    chain = canonical_chain(c.get("network") or "")
    status = "SUSPENDED" if (c.get("isSuspended") or c.get("suspended")) else "LIVE"
    contract = _contract_for(c, chain)
    raw = {k: c[k] for k in ("id", "code", "name", "network") if c.get(k) is not None}
    return {"symbol": sym, "network": chain, "chain": chain, "contract": contract,
            "status": status, "native_id": f"{sym}:{chain}" if chain else sym, "raw": raw}


def map_items(d, fiats):
    """-> {fiat: [FIAT_ROUTE items]} for the configured fiats; a fiat missing from the response
    maps to a BadResponse instance (the caller turns it into a scope error)."""
    cryptos = [map_crypto(c) for c in d["crypto"]]
    listed = {str(f.get("code") or f.get("symbol") or "").upper()
              for f in d["fiats"] if isinstance(f, dict)}
    out = {}
    for fiat in fiats:
        fiat = str(fiat).upper()
        if fiat not in listed:
            out[fiat] = BadResponse(f"fiat {fiat} not in /supported fiat list")
            continue
        out[fiat] = [dict(t, platform_id=PLATFORM_ID, access_kind="FIAT_ROUTE", fiat=fiat, quote=fiat,
                          country="", fiat_tier="SUPPORTED") for t in cryptos]
    return out


def run_once(conn, fetch=None, fetched_at=None):
    fetched_at = fetched_at or rc.now_ms()
    fetch = fetch or default_fetch
    try:
        d = fetch_supported(fetch)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        return {"error": msg}
    out = {}
    for fiat, items in map_items(d, configured_fiats()).items():
        if isinstance(items, Exception):
            msg = f"{type(items).__name__}: {items}"
            rc.report_fetch_error(conn, SOURCE_ID, fiat, msg, at=fetched_at)
            out[fiat] = {"error": msg}
            continue
        out[fiat] = rc.ingest_snapshot(conn, SOURCE_ID, fiat, items, fetched_at=fetched_at)
    return out


if __name__ == "__main__":
    import json
    key = read_key()
    if not key:
        print(f"onramper: {ENV_KEY} not set — nothing to fetch")
    else:
        conn = rc.init_db(":memory:")
        print(json.dumps(run_once(conn), indent=1, default=str)[:600])
