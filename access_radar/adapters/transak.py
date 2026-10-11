"""Transak adapter — global buy-side crypto catalog (public, no key).

GET https://api.transak.com/api/v2/currencies/crypto-currencies
    -> {"response": [{"symbol": "ETH", "name": "Ethereum", "network": {"name": "ethereum",
                      "chainId": "1"}, "address": "", "decimals": 18, "isAllowed": true,
                      "isSuspended": false, "uniqueId": "ETHethereum", "coinType": "NATIVE",
                      "regionsNotSupported": [...], ...}, ...]}
GET https://api.transak.com/api/v2/currencies/fiat-currencies
    -> {"response": [{"symbol": "USD", "name": "US Dollar", "isAllowed": true, ...}, ...]}

Both endpoints are public.  isSuspended or isAllowed=false -> SUSPENDED (in the list but not
currently buyable — mirrors ramp.py's enabled=false doctrine; REMOVED is left to miss counting).

One FIAT_ROUTE item per (crypto-network, fiat) at fiat_tier SUPPORTED, scope per fiat — same
convention as ramp_assets / onramper_routes.  The two lists are independent, so the cross product
is uniform per fiat: only DEFAULT_FIATS are ingested (override with TRANSAK_FIATS=comma,list).
A listed-but-disallowed fiat gets SUSPENDED routes; a fiat absent from the list is a scope error.
regionsNotSupported is kept in raw (country-level filtering happens at quote time on Transak's
side; the per-country source is a separate concern for this adapter).
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

PLATFORM_ID = "transak"
SOURCE_ID = "transak_routes"
CRYPTO_URL = "https://api.transak.com/api/v2/currencies/crypto-currencies"
FIAT_URL = "https://api.transak.com/api/v2/currencies/fiat-currencies"
DEFAULT_FIATS = ("USD", "EUR", "GBP")
ENV_FIATS = "TRANSAK_FIATS"


class BadResponse(Exception):
    pass


def register(conn, at=None):
    rc.register_platform(conn, PLATFORM_ID, "Transak", "ONRAMP", "", at=at)
    rc.register_source(conn, SOURCE_ID, name="Transak currencies API (public)", kind="SNAPSHOT",
                       tier="OFFICIAL_STRUCTURED", origin_platform_id=PLATFORM_ID, at=at)


def configured_fiats():
    raw = os.environ.get(ENV_FIATS, "")
    return tuple(s.strip().upper() for s in raw.split(",") if s.strip()) or DEFAULT_FIATS


def fetch_list(url, fetch):
    d = fetch(url)
    if not (isinstance(d, dict) and isinstance(d.get("response"), list) and d["response"]):
        raise BadResponse(f"unexpected shape from {url.split('/')[-1]} (want {{'response': [...]}})")
    return d["response"]


def map_crypto(c):
    """-> item template without the fiat fields; unmappable entries become invalid markers."""
    if not isinstance(c, dict):
        return {"access_kind": "FIAT_ROUTE"}
    sym = str(c.get("symbol") or "").strip().upper()
    net = c.get("network") or {}
    chain = canonical_chain(net.get("name") or "") if isinstance(net, dict) else ""
    if not sym or not chain:
        return {"access_kind": "FIAT_ROUTE"}
    status = "SUSPENDED" if (c.get("isSuspended") or c.get("isAllowed") is False) else "LIVE"
    raw = {k: c[k] for k in ("symbol", "name", "network", "isAllowed", "isSuspended", "coinType",
                             "regionsNotSupported") if c.get(k) is not None}
    return {"symbol": sym, "network": chain, "chain": chain, "contract": c.get("address") or "",
            "status": status, "native_id": c.get("uniqueId") or f"{sym}:{chain}", "raw": raw}


def map_items(cryptos, fiats):
    """-> {fiat: [FIAT_ROUTE items]}; a fiat absent from the fiat list maps to a BadResponse."""
    mapped = [map_crypto(c) for c in cryptos]
    listed = {str(f.get("symbol") or "").upper() for f in fiats if isinstance(f, dict)}
    allowed = {str(f.get("symbol") or "").upper()
               for f in fiats if isinstance(f, dict) and f.get("isAllowed", True)}
    out = {}
    for fiat in configured_fiats():
        fiat = str(fiat).upper()
        if fiat not in listed:
            out[fiat] = BadResponse(f"fiat {fiat} not in Transak fiat-currencies list")
            continue
        forced = None if fiat in allowed else "SUSPENDED"
        items = []
        for t in mapped:
            it = dict(t, platform_id=PLATFORM_ID, access_kind="FIAT_ROUTE", fiat=fiat, quote=fiat,
                      country="", fiat_tier="SUPPORTED")
            if forced and "symbol" in it:
                it["status"] = forced
            items.append(it)
        out[fiat] = items
    return out


def run_once(conn, fetch=None, fetched_at=None):
    fetched_at = fetched_at or rc.now_ms()
    fetch = fetch or default_fetch
    try:
        cryptos = fetch_list(CRYPTO_URL, fetch)
        fiats = fetch_list(FIAT_URL, fetch)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        return {"error": msg}
    out = {}
    for fiat, items in map_items(cryptos, fiats).items():
        if isinstance(items, Exception):
            msg = f"{type(items).__name__}: {items}"
            rc.report_fetch_error(conn, SOURCE_ID, fiat, msg, at=fetched_at)
            out[fiat] = {"error": msg}
            continue
        out[fiat] = rc.ingest_snapshot(conn, SOURCE_ID, fiat, items, fetched_at=fetched_at)
    return out


if __name__ == "__main__":
    import json
    from access_http import default_client
    conn = rc.init_db(":memory:")
    register(conn)
    print(json.dumps(run_once(conn, fetch=default_client().get_json), indent=1, default=str)[:600])
