"""Coinone adapter — KRW market list snapshot (public, no key).

Source (module-level SOURCES, native interface from README.md):
  * coinone_market  snapshot  GET https://api.coinone.co.kr/public/v2/markets/KRW
        -> {"result": "success", "error_code": "0", "server_time": ms,
            "markets": [{"quote_currency": "KRW", "target_currency": "BTC", "trade_status": 1,
                         "maintenance_status": 0, "order_types": [...], "price_unit", "min/max_*", ...}]}
        Documented values: trade_status 0 = buy+sell disabled, 1 = enabled, 2 = buy disabled, 3 = sell disabled;
        maintenance_status 0 = normal, 1 = under maintenance.  Mapping via radar_core.map_coinone_market:
        1|3 -> LIVE, 0|2 -> SUSPENDED, maintenance 1 -> SUSPENDED (never REMOVED).
Coinone's public WebSocket has no listing channel, so this snapshot is the only Coinone source.
Price-derived fields (price_unit, order_book_units, min/max price/qty/amount, server_time) are stripped from
stored raw so identical polls dedupe.  A response with result != success, a non-list 'markets', or rows of a
different quote currency raises (fetch failure -> DOWN), never a partial ingest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from .upbit import BadResponse, get_json  # noqa: E402

PLATFORM_ID = "coinone"
BASE_URL = "https://api.coinone.co.kr/public/v2/markets/{quote}"
QUOTES = ("KRW",)
_KEEP = ("quote_currency", "target_currency", "trade_status", "maintenance_status", "order_types")


def map_market(m):
    if not isinstance(m, dict) or not m.get("target_currency") or not m.get("quote_currency"):
        return {"access_kind": "SPOT"}           # counted invalid by radar_core's schema gate
    try:
        it = rc.map_coinone_market(m)
    except (TypeError, ValueError):
        return {"access_kind": "SPOT"}
    it.update(symbol=str(m["target_currency"]).upper(), quote=str(m["quote_currency"]).upper(),
              native_id=f"{str(m['target_currency']).upper()}-{str(m['quote_currency']).upper()}",
              raw={k: m.get(k) for k in _KEEP if k in m})
    return it


def fetch_quote(http, quote):
    d = get_json(http, BASE_URL.format(quote=quote))
    if not isinstance(d, dict) or str(d.get("result", "")).lower() != "success":
        raise BadResponse(f"coinone error: {(d or {}).get('error_code') if isinstance(d, dict) else d!r}")
    markets = d.get("markets")
    if not isinstance(markets, list) or not markets:
        raise BadResponse("coinone response without a non-empty 'markets' list")
    wrong = {str(m.get("quote_currency", "")).upper() for m in markets if isinstance(m, dict)} - {quote}
    if wrong:
        raise BadResponse(f"asked {quote}, got quote_currency {sorted(wrong)}")
    return [map_market(m) for m in markets]


def fetch_markets(http):
    out = {}
    for q in QUOTES:
        try:
            out[q] = fetch_quote(http, q)
        except Exception as e:  # noqa: BLE001 - per-scope failure -> only this scope DOWN
            out[q] = e
    return out


PLATFORMS = [{"platform_id": PLATFORM_ID, "name": "Coinone", "platform_type": "CEX", "country": "KR"}]
SOURCES = {
    "coinone_market": {
        "kind": "snapshot", "fetch": fetch_markets, "period_sec": 30,
        "source": {"name": "Coinone /public/v2/markets", "kind": "SNAPSHOT", "tier": "OFFICIAL_STRUCTURED",
                   "origin_platform_id": PLATFORM_ID},
    },
}


def register(conn, at=None):
    for p in PLATFORMS:
        p = dict(p)
        rc.register_platform(conn, p.pop("platform_id"), at=at, **p)
    for sid, spec in SOURCES.items():
        rc.register_source(conn, sid, at=at, **spec["source"])
