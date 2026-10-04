"""Bithumb adapter — market list snapshot + /v1/notices polling (public, no key).

Sources (module-level SOURCES, native interface from README.md):
  * bithumb_market  snapshot      GET https://api.bithumb.com/v1/market/all?isDetails=true
        -> [{"market": "KRW-BTC", "korean_name", "english_name", "market_warning": "NONE"|"CAUTION"}]
        One scope per quote (KRW and BTC required; other quotes, e.g. USDT, become their own scope when present).
        market_warning=CAUTION (유의 종목) stays LIVE (lead decision; flag kept in item["warning"] + raw).  Registered with
        remove_min_elapsed_ms=REMOVE_MIN_ELAPSED_MS (env BITHUMB_REMOVE_MIN_ELAPSED_MS) so three misses inside a
        burst of fast polls can never confirm a delisting by themselves.
  * bithumb_notice  announcement  GET https://api.bithumb.com/v1/notices?count=20   (1 req/s per IP; polled every 2s)
        -> [{"categories": [..], "title", "pc_url", "published_at": "yyyy-MM-dd HH:mm:ss", "modified_at"}]
        The API has no id field, but pc_url carries the numeric notice id: source_event_id = "bithumb:notice:<id>"
        (feed.bithumb.com/notice/1647199 -> bithumb:notice:1647199).  Only when pc_url has no numeric id:
        "bithumb:notice:h" + sha256(normalised title + "|" + published_at)[:20].
        Notice link: announcement "url" = pc_url (made absolute against https://feed.bithumb.com if relative).  published_at has no zone -> interpreted as KST (UTC+9) -> UTC ms.

The whole notice list is validated first (a JSON list whose rows have a title and a parseable published_at);
anything else raises, so the runner records a failed run instead of a silently shorter list.
"""
import hashlib
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from .upbit import (BadResponse, compact, get_json, notice_announcement, parse_ts_ms,  # noqa: E402
                    split_by_quote)

log = logging.getLogger("access_radar.adapters.bithumb")

PLATFORM_ID = "bithumb"
MARKETS_URL = "https://api.bithumb.com/v1/market/all"
NOTICES_URL = "https://api.bithumb.com/v1/notices"
NOTICE_COUNT = 20                 # API max
REQUIRED_QUOTES = ("KRW", "BTC")
WARNING_AS_SUSPENDED = False     # lead decision 2026-10-04: warning stocks stay LIVE
REMOVE_MIN_ELAPSED_MS = int(os.environ.get("BITHUMB_REMOVE_MIN_ELAPSED_MS", str(120_000)))
MALFORMED_MAX = 0.25              # more than this share of unusable notice rows => treat the response as broken


# ----------------------------------------------------------------------------- bithumb_market
def map_market(m):
    if not isinstance(m, dict) or not isinstance(m.get("market"), str) or m["market"].count("-") != 1 \
            or not all(m["market"].split("-")):
        return {"access_kind": "SPOT"}           # counted invalid by radar_core's schema gate
    quote, sym = m["market"].upper().split("-", 1)
    warned = str(m.get("market_warning") or "").upper() == "CAUTION"
    return {"platform_id": PLATFORM_ID, "symbol": sym, "quote": quote, "access_kind": "SPOT",
            "status": "SUSPENDED" if (warned and WARNING_AS_SUSPENDED) else "LIVE", "warning": warned,
            "native_id": m["market"],
            "raw": {k: m.get(k) for k in ("market", "korean_name", "english_name", "market_warning") if k in m}}


def fetch_markets(http):
    d = get_json(http, MARKETS_URL, params={"isDetails": "true"})
    if not isinstance(d, list) or not d:
        raise BadResponse(f"unexpected /v1/market/all response: {type(d).__name__}")
    return split_by_quote([map_market(m) for m in d], required=REQUIRED_QUOTES)


# ----------------------------------------------------------------------------- bithumb_notice
FEED_BASE = "https://feed.bithumb.com"


def notice_url(pc_url):
    u = str(pc_url or "").strip()
    if not u:
        return None
    if u.startswith(("https://", "http://")):
        return u
    if u.startswith("//"):
        return "https:" + u
    return FEED_BASE + ("" if u.startswith("/") else "/") + u


_PC_URL_ID = re.compile(r"/notice/(\d+)(?:[/?#]|$)")


def notice_event_id(title, published_at, pc_url=None):
    m = _PC_URL_ID.search(str(pc_url or ""))
    if m:
        return f"bithumb:notice:{m.group(1)}"
    basis = compact(title) + "|" + str(published_at or "").strip()
    return "bithumb:notice:h" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]


def parse_notice(n):
    """One notice row -> announcement dict or None (not an access change)."""
    title = n.get("title") or ""
    announced = parse_ts_ms(n.get("published_at"))          # naive -> KST
    cats = n.get("categories") if isinstance(n.get("categories"), list) else []
    raw = {k: n.get(k) for k in ("categories", "title", "pc_url", "published_at") if k in n}
    return notice_announcement(PLATFORM_ID, title, notice_event_id(title, n.get("published_at"), n.get("pc_url")), announced,
                               categories=cats, raw=raw, url=notice_url(n.get("pc_url")))


def validate_notices(d):
    if not isinstance(d, list):
        if isinstance(d, dict) and d.get("error"):
            raise BadResponse(f"bithumb error: {d['error']}")
        raise BadResponse(f"unexpected /v1/notices response: {type(d).__name__}")
    good = [n for n in d if isinstance(n, dict) and (n.get("title") or "").strip()
            and parse_ts_ms(n.get("published_at")) is not None]
    if d and (len(d) - len(good)) / len(d) > MALFORMED_MAX:
        raise BadResponse(f"{len(d) - len(good)}/{len(d)} malformed notice rows")
    return good


def fetch_notices(http):
    rows = validate_notices(get_json(http, NOTICES_URL, params={"count": NOTICE_COUNT}))
    out = []
    for n in rows:
        a = parse_notice(n)
        if a:
            out.append(a)
    return out


# ----------------------------------------------------------------------------- registration
PLATFORMS = [{"platform_id": PLATFORM_ID, "name": "Bithumb", "platform_type": "CEX", "country": "KR"}]
SOURCES = {
    "bithumb_market": {
        "kind": "snapshot", "fetch": fetch_markets, "period_sec": 30,
        "source": {"name": "Bithumb /v1/market/all", "kind": "SNAPSHOT", "tier": "OFFICIAL_STRUCTURED",
                   "origin_platform_id": PLATFORM_ID, "remove_min_elapsed_ms": REMOVE_MIN_ELAPSED_MS},
    },
    "bithumb_notice": {
        "kind": "announcement", "fetch": fetch_notices, "period_sec": 2,
        "source": {"name": "Bithumb /v1/notices", "kind": "ANNOUNCEMENT", "tier": "OFFICIAL_ANNOUNCEMENT",
                   "origin_platform_id": PLATFORM_ID},
    },
}


def register(conn, at=None):
    for p in PLATFORMS:
        p = dict(p)
        rc.register_platform(conn, p.pop("platform_id"), at=at, **p)
    for sid, spec in SOURCES.items():
        rc.register_source(conn, sid, at=at, **spec["source"])
