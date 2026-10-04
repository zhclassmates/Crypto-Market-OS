"""Korbit (rebranded DigitalX / 디지털엑스) adapter — public v2 API, no key.

Old host api.korbit.co.kr still works (and is the host access_http rate-limits); the new documented host is
api.digitalx.miraeasset.com.  Override with env KORBIT_BASE_URL.  Every response is {"success": true, "data": ...}.

Sources (module-level SOURCES, native interface from README.md):
  * korbit_pairs     snapshot      GET /v2/currencyPairs  -> data[{symbol 'btc_krw', status launched|stopped,
        baseCurrency, quoteCurrency, minOrderValue, maxOrderValue}]; radar_core.map_korbit_pair
        (stopped -> SUSPENDED); one scope per quote (KRW required).
  * korbit_networks  snapshot      GET /v2/currencies     -> data[{name 'eth', networkList[{name 'ETH', fullName,
        depositStatus, withdrawalStatus: launched|stopped, contractAddress, withdrawalTxFee, ...}]}]
        scope "deposit":  one DEPOSIT_NETWORK item per (currency, network)
        scope "withdraw": one WITHDRAW_NETWORK item per (currency, network)
        network = chains.canonical_chain(network name); launched -> LIVE, stopped -> SUSPENDED.  Fiat (no
        networkList) is skipped.  Fees / limits / confirmation counts are stripped from raw.
  * korbit_notice    announcement  GET /v2/notices (20 newest: title, createdAt ms, updatedAt, url ?noticeId=...)
        + GET /v2/marketAlerts (pairs with active 시장경보 alerts).  Stable ids:
        "korbit:notice:<noticeId>" (fallback: hash of title+createdAt) and
        "korbit:alert:<symbol>:<type>:<startAt>".  Notice link (announcement "url"): the API's absolute url field,
        else NOTICE_PAGE_URL built from noticeId; marketAlerts carry no link, so their markers have no url.  Only warning-designation alerts (유의/warning/designation) are
        kept, and only as non-state-changing WARNING MARKER announcements (upbit.warning_announcement: asset_key
        "warning:<SYM>", never SUSPENDED); price/volume monitoring alerts are dropped.  Real trading halts are
        covered by korbit_pairs status=stopped.
"""
import hashlib
import logging
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from .chains import canonical_chain  # noqa: E402
from .upbit import (BadResponse, compact, get_json, notice_announcement, parse_ts_ms, split_by_quote,  # noqa: E402
                    warning_announcement)

log = logging.getLogger("access_radar.adapters.korbit")

PLATFORM_ID = "korbit"
BASE_URL = os.environ.get("KORBIT_BASE_URL", "https://api.korbit.co.kr").rstrip("/")
REQUIRED_QUOTES = ("KRW",)
SCOPE_DEPOSIT, SCOPE_WITHDRAW = "deposit", "withdraw"
_NET_VOLATILE = ("withdrawalTxFee", "withdrawalMinAmount", "confirmationCount", "withdrawalPrecision",
                 "addressExplorerUrl", "withdrawalMaxAmountPerRequest")
NOTICE_PAGE_URL = "https://digitalx.miraeasset.com/notice/detail/?noticeId={id}"
_ALERT_DESIGNATION = ("유의", "warning", "designat")


def url(path):
    return f"{BASE_URL}{path}"


def _data(d, what):
    if not isinstance(d, dict) or d.get("success") is not True or not isinstance(d.get("data"), list):
        err = d.get("error") if isinstance(d, dict) else None
        raise BadResponse(f"unexpected {what} response{': ' + str(err) if err else ''}")
    return d["data"]


# ----------------------------------------------------------------------------- korbit_pairs
def map_pair(p):
    if not isinstance(p, dict) or not isinstance(p.get("symbol"), str) or p["symbol"].count("_") != 1 \
            or not all(p["symbol"].split("_")):
        return {"access_kind": "SPOT"}           # counted invalid by radar_core's schema gate
    it = rc.map_korbit_pair(p)
    it["raw"] = {k: p.get(k) for k in ("symbol", "status", "baseCurrency", "quoteCurrency") if k in p}
    return it


def fetch_pairs(http):
    rows = _data(get_json(http, url("/v2/currencyPairs")), "/v2/currencyPairs")
    if not rows:
        raise BadResponse("empty /v2/currencyPairs")
    return split_by_quote([map_pair(p) for p in rows], required=REQUIRED_QUOTES)


# ----------------------------------------------------------------------------- korbit_networks
def _net_status(v):
    return "LIVE" if str(v or "").lower() == "launched" else "SUSPENDED"


def map_currencies(rows):
    """-> (deposit_items, withdraw_items). Two Korbit networks that collapse onto one canonical chain keep the
    LIVE one (radar_core keeps the first duplicate)."""
    dep, wd = [], []
    idx = {SCOPE_DEPOSIT: {}, SCOPE_WITHDRAW: {}}
    for c in rows:
        if not isinstance(c, dict) or not c.get("name"):
            dep.append({"access_kind": "DEPOSIT_NETWORK"})
            wd.append({"access_kind": "WITHDRAW_NETWORK"})
            continue
        nets = c.get("networkList")
        if not nets:                                  # fiat (krw) or no on-chain transfer
            continue
        sym = str(c["name"]).upper()
        for n in nets:
            if not isinstance(n, dict) or not n.get("name"):
                continue
            chain = canonical_chain(n["name"])
            raw = {k: v for k, v in n.items() if k not in _NET_VOLATILE}
            raw["currency"] = c["name"]
            base = {"platform_id": PLATFORM_ID, "symbol": sym, "quote": "", "network": chain, "chain": chain,
                    "contract": n.get("contractAddress") or "", "native_id": f"{c['name']}:{n['name']}", "raw": raw}
            for scope, kind, field, items in ((SCOPE_DEPOSIT, "DEPOSIT_NETWORK", "depositStatus", dep),
                                              (SCOPE_WITHDRAW, "WITHDRAW_NETWORK", "withdrawalStatus", wd)):
                it = dict(base, access_kind=kind, status=_net_status(n.get(field)))
                key = (sym, chain)
                prev = idx[scope].get(key)
                if prev is None:
                    idx[scope][key] = len(items)
                    items.append(it)
                elif items[prev]["status"] != "LIVE" and it["status"] == "LIVE":
                    items[prev] = it
    return dep, wd


def fetch_networks(http):
    rows = _data(get_json(http, url("/v2/currencies")), "/v2/currencies")
    if not rows:
        raise BadResponse("empty /v2/currencies")
    dep, wd = map_currencies(rows)
    if not dep:
        raise BadResponse("/v2/currencies has no networkList at all (shape changed?)")
    return {SCOPE_DEPOSIT: dep, SCOPE_WITHDRAW: wd}


# ----------------------------------------------------------------------------- korbit_notice
def _notice_id(n):
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(str(n.get("url") or "")).query)
    nid = (q.get("noticeId") or [""])[0]
    if not nid:
        m = re.search(r"/notice/(?:detail/)?([A-Za-z0-9_-]{6,})", str(n.get("url") or ""))
        nid = m.group(1) if m else ""
    return nid


def notice_url(n):
    u = str(n.get("url") or "").strip()
    if u.startswith(("https://", "http://")):
        return u
    nid = _notice_id(n) or str(n.get("noticeId") or n.get("id") or "")
    return NOTICE_PAGE_URL.format(id=nid) if nid else None


def notice_event_id(n):
    nid = _notice_id(n)
    if not nid:
        basis = compact(n.get("title")) + "|" + str(n.get("createdAt") or "")
        nid = "h" + hashlib.sha256(basis.encode()).hexdigest()[:16]
    return f"korbit:notice:{nid}"


def parse_notice(n):
    title = n.get("title") or ""
    raw = {k: n.get(k) for k in ("title", "createdAt", "url") if k in n}
    return notice_announcement(PLATFORM_ID, title, notice_event_id(n), parse_ts_ms(n.get("createdAt")),
                               raw=raw, url=notice_url(n))


def parse_alerts(rows):
    out = []
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("symbol"), str) or r["symbol"].count("_") != 1:
            continue
        base, quote = r["symbol"].upper().split("_", 1)
        for a in r.get("alerts") or []:
            if not isinstance(a, dict):
                continue
            label = compact(" ".join(str(a.get(k) or "") for k in ("type", "typeKorean", "level", "levelKorean")))
            if not any(k in label for k in _ALERT_DESIGNATION):
                continue
            out.append(warning_announcement(
                PLATFORM_ID, [base], [quote], True,
                f"korbit:alert:{r['symbol'].lower()}:{a.get('type')}:{a.get('startAt') or 0}",
                parse_ts_ms(a.get("startAt")), title=f"market alert {r['symbol']} {a.get('typeKorean') or a.get('type')}",
                raw={"symbol": r["symbol"], **{k: a.get(k) for k in ("type", "typeKorean", "level", "levelKorean",
                                                                     "startAt", "endAt")}}))
    return out


def fetch_notices(http):
    """Notices are the primary feed (a failure raises -> failed run); a marketAlerts failure is logged only."""
    rows = _data(get_json(http, url("/v2/notices")), "/v2/notices")
    out = []
    for n in rows:
        if isinstance(n, dict) and (n.get("title") or "").strip():
            a = parse_notice(n)
            if a:
                out.append(a)
    try:
        out += parse_alerts(_data(get_json(http, url("/v2/marketAlerts")), "/v2/marketAlerts"))
    except Exception as e:  # noqa: BLE001
        log.warning("korbit_notice: /v2/marketAlerts failed: %s", e)
    return out


# ----------------------------------------------------------------------------- registration
PLATFORMS = [{"platform_id": PLATFORM_ID, "name": "Korbit (DigitalX)", "platform_type": "CEX", "country": "KR"}]
SOURCES = {
    "korbit_pairs": {
        "kind": "snapshot", "fetch": fetch_pairs, "period_sec": 60,
        "source": {"name": "Korbit /v2/currencyPairs", "kind": "SNAPSHOT", "tier": "OFFICIAL_STRUCTURED",
                   "origin_platform_id": PLATFORM_ID},
    },
    "korbit_networks": {
        "kind": "snapshot", "fetch": fetch_networks, "period_sec": 60,
        "source": {"name": "Korbit /v2/currencies networks", "kind": "SNAPSHOT", "tier": "OFFICIAL_STRUCTURED",
                   "origin_platform_id": PLATFORM_ID},
    },
    "korbit_notice": {
        "kind": "announcement", "fetch": fetch_notices, "period_sec": 60,
        "source": {"name": "Korbit /v2/notices + /v2/marketAlerts", "kind": "ANNOUNCEMENT",
                   "tier": "OFFICIAL_ANNOUNCEMENT", "origin_platform_id": PLATFORM_ID},
    },
}


def register(conn, at=None):
    for p in PLATFORMS:
        p = dict(p)
        rc.register_platform(conn, p.pop("platform_id"), at=at, **p)
    for sid, spec in SOURCES.items():
        rc.register_source(conn, sid, at=at, **spec["source"])
