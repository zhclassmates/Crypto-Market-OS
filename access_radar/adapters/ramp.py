"""Ramp Network adapter — public host API v3, no key.

GET https://api.ramp.network/api/host-api/v3/assets?currencyCode=EUR&withDisabled=true&withHidden=true
  -> {"currencyCode", "assets": [{symbol, chain, type, address, enabled, hidden, price{...}, ...}], ...}

withDisabled / withHidden are mandatory: without them Ramp silently drops disabled and hidden assets
(EUR on 2026-10-04: 214 assets with both flags vs 125 without), and a pause would look like a removal.
Mapping goes through radar_core.map_ramp_asset (enabled=false or hidden=true -> SUSPENDED, never REMOVED);
this adapter then rewrites network/chain to the shared canonical names so contracts match other sources.

One snapshot scope per fiat on source `ramp_assets` (OFFICIAL_STRUCTURED, platform `ramp`, ONRAMP).
This endpoint has no country parameter, so items carry country '' (a per-fiat, global route list);
per-country coverage needs a different source (Onramper with an explicit country).
The response is refused (fetch error, no ingest) if `withDisabled`/`withHidden` looks ignored, i.e. no
disabled or hidden asset at all, or if currencyCode does not match the requested fiat.
Prices are stripped from stored raw JSON so identical polls dedupe in raw_blob.
"""
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from .chains import canonical_chain  # noqa: E402
from ._fetch import default_fetch  # noqa: E402

BASE_URL = "https://api.ramp.network/api/host-api/v3/assets"
PLATFORM_ID = "ramp"
SOURCE_ID = "ramp_assets"
DEFAULT_FIATS = ("USD", "EUR", "GBP")
_VOLATILE = ("price", "networkFee", "minPurchaseCryptoAmount")


class BadResponse(Exception):
    pass


def register(conn, at=None):
    rc.register_platform(conn, PLATFORM_ID, "Ramp Network", "ONRAMP", "", at=at)
    rc.register_source(conn, SOURCE_ID, name="Ramp host-api v3 assets", kind="SNAPSHOT",
                       tier="OFFICIAL_STRUCTURED", origin_platform_id=PLATFORM_ID, at=at)


def assets_url(fiat):
    q = {"currencyCode": fiat.upper(), "withDisabled": "true", "withHidden": "true"}
    return f"{BASE_URL}?{urllib.parse.urlencode(q)}"


def configured_fiats():
    raw = os.environ.get("RAMP_FIATS", "")
    fiats = tuple(f.strip().upper() for f in raw.split(",") if f.strip())
    return fiats or DEFAULT_FIATS


def _slim(a):
    return {k: v for k, v in a.items() if k not in _VOLATILE}


def fetch_assets(fiat, fetch=None):
    d = (fetch or default_fetch)(assets_url(fiat))
    if not isinstance(d, dict) or not isinstance(d.get("assets"), list):
        raise BadResponse("unexpected response shape (no 'assets' list)")
    if d.get("currencyCode") and str(d["currencyCode"]).upper() != fiat.upper():
        raise BadResponse(f"asked {fiat}, got currencyCode {d['currencyCode']}")
    assets = d["assets"]
    if assets and not any((a.get("enabled") is False) or a.get("hidden") for a in assets):
        raise BadResponse("no disabled/hidden assets returned: withDisabled/withHidden probably ignored")
    return d


def map_assets(assets, fiat):
    """If two Ramp rows collapse onto one (symbol, canonical chain) key, keep the LIVE one: radar_core keeps
    the first duplicate, and a disabled legacy row listed first would otherwise mask a working route."""
    items, by_key = [], {}
    for a in assets:
        if not isinstance(a, dict) or not a.get("symbol"):
            items.append({"access_kind": "FIAT_ROUTE"})   # counted as invalid by radar_core's schema gate
            continue
        it = rc.map_ramp_asset(a, fiat.upper())
        chain = canonical_chain(a.get("chain"))
        it.update(network=chain, chain=chain, native_id=f"{a.get('chain')}:{a.get('symbol')}", raw=_slim(a))
        key = (it["symbol"].upper(), chain)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = len(items)
            items.append(it)
        elif items[prev]["status"] != "LIVE" and it["status"] == "LIVE":
            items[prev] = it
    return items


def run_once(conn, fiats=None, fetch=None, fetched_at=None):
    """One poll over every fiat. Returns {fiat: ingest result | {'error': msg}}."""
    fetched_at = fetched_at or rc.now_ms()
    out = {}
    for fiat in (fiats or configured_fiats()):
        fiat = fiat.upper()
        try:
            d = fetch_assets(fiat, fetch)
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {e}"
            rc.report_fetch_error(conn, SOURCE_ID, fiat, msg, at=fetched_at)
            out[fiat] = {"error": msg}
            continue
        raw = {k: v for k, v in d.items() if k != "assets"}
        raw["assets"] = [_slim(a) for a in d["assets"] if isinstance(a, dict)]
        out[fiat] = rc.ingest_snapshot(conn, SOURCE_ID, fiat, map_assets(d["assets"], fiat),
                                       fetched_at=fetched_at, raw=raw)
    return out
