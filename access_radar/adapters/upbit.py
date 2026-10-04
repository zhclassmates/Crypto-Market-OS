"""Upbit adapter — market list snapshot + announcement WebSocket (with REST backfill).

Sources (module-level SOURCES, native interface from README.md):
  * upbit_market  snapshot      GET https://api.upbit.com/v1/market/all?is_details=true   (public, 10 req/s/IP)
        -> one scope per quote currency (KRW / BTC / USDT, plus any new quote that appears as its own scope).
        Item: {"market": "KRW-BTC", "korean_name", "english_name", "market_event": {"warning": bool, "caution": {...}}}
        (legacy "market_warning": "NONE"|"CAUTION" is honoured too).  Warning stocks (market_event.warning /
        market_warning=CAUTION, 유의 종목) stay LIVE (lead decision, WARNING_AS_SUSPENDED=False): the flag is carried
        as item["warning"] (ignored by radar_core today) and in the stored raw.  'caution' (주의 종목) is ignored.
        A required quote with zero items => that scope is an
        IncompleteSnapshot (DOWN), never an empty list that could look like mass removals.
  * upbit_notice  stream        wss://api.upbit.com/websocket/v1/private, type "announcement" (since 2026-08-31).
        Private endpoint: HS256 JWT {access_key, nonce} in "Authorization: Bearer"; no permission scope needed.
        Credentials: env UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY.  Without them the WS is not attempted: a single
        WARNING is logged and run() falls back to REST polling of the announcement list every POLL_FALLBACK_SEC
        (env UPBIT_NOTICE_REST_FALLBACK=0 disables the fallback).  Realtime only (no replay): after every reconnect
        the runner calls backfill(http, since_ms, until_ms), which reads the web notice list
        GET https://api-manager.upbit.com/api/v1/announcements?os=web&page=N&per_page=20&category=all
        (unofficial web endpoint; shape assumed, see fixtures/upbit/announcements_rest.json).
        Every REST call uses timeout=REST_TIMEOUT_SEC, tries=REST_TRIES; a backfill is capped at
        BACKFILL_BUDGET_SEC.  A failed/timed-out list request RAISES (BackfillError / UpbitPollError): it is never
        turned into "no notices".  How it surfaces: backfill -> runner WARNING "upbit_notice backfill failed: ..."
        and the gap stays source_disconnect.backfilled=0; polling fallback -> run() raises, so the runner records
        source_run.last_error / connected=0, source_health('upbit_notice','') DOWN and source_disconnect.reason.

Notice link (announcement "url" -> source_observation.url): always built from the notice id as
NOTICE_PAGE_URL (https://upbit.com/service_center/notice?id=<id>), so WS (which sends a ?view=share variant) and
REST backfill (no url field) store the same link; only a notice without any id falls back to the message's url.

Stable announcement id: "upbit:notice:<notice id>"; an UPDATED notice whose listed_at moved gets
"upbit:notice:<id>:u<listed_at ms>" so a changed delisting date / action is ingested again, while the WS message
and the REST backfill of the same version always produce the same id.

Warning designations (유의 종목 지정 / 해제) are NOT access changes.  Because radar_core has no
non-state-changing announcement action yet, they are recorded as WARNING MARKER announcements (see
warning_announcement): targets use asset_key "warning:<SYMBOL>" (WARNING_ASSET_PREFIX), action SUSPEND (designated)
or RESUME (lifted), ann["warning"] / raw["warning"] = "DESIGNATED" | "LIFTED".  ingest_announcement then writes a
source_observation (obs_kind ANNOUNCEMENT) and a NONE-status access_state row for the marker key only: from NONE,
SUSPEND/RESUME never transition, and no episode ever exists under a "warning:" asset_key to merge into, so there
is no access_event, access_transition or rejected_transition and the real market keeps its status.

The Korean/English notice classifier at the bottom half of this file is shared with bithumb.py and korbit.py.
Stdlib has no WebSocket client, so WsClient is a minimal RFC 6455 client (TLS, masking, ping/pong,
fragmentation, close); recv() takes a timeout so run() polls ctx.should_stop() at least every RECV_TIMEOUT s.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import socket
import ssl
import sys
import time
import unicodedata
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from .chains import canonical_chain  # noqa: E402

log = logging.getLogger("access_radar.adapters.upbit")

PLATFORM_ID = "upbit"
MARKETS_URL = "https://api.upbit.com/v1/market/all"
WS_URL = "wss://api.upbit.com/websocket/v1/private"
NOTICE_LIST_URL = "https://api-manager.upbit.com/api/v1/announcements"
NOTICE_DETAIL_URL = "https://api-manager.upbit.com/api/v1/announcements/{id}"
NOTICE_PAGE_URL = "https://upbit.com/service_center/notice?id={id}"      # human page, stored in source_observation.url
ENV_ACCESS_KEY = "UPBIT_ACCESS_KEY"
ENV_SECRET_KEY = "UPBIT_SECRET_KEY"

REQUIRED_QUOTES = ("KRW", "BTC", "USDT")
WARNING_AS_SUSPENDED = False     # lead decision 2026-10-04: warning stocks stay LIVE
WARNING_ASSET_PREFIX = "warning:"
RELEVANT_CATEGORIES = {"trade", "wallet", "거래", "입출금", ""}

HEARTBEAT_SEC = 60          # runner watchdog; we ping every PING_EVERY so an idle-but-healthy socket stays alive
PING_EVERY = 25.0
RECV_TIMEOUT = 1.0
CONNECT_TIMEOUT = 10.0
MISSING_CREDS_WAIT = 300.0  # no credentials: idle this long before failing again (avoids 30s log spam)
REST_TIMEOUT_SEC = 10.0    # per request (access_http applies it to connect and to each socket read)
REST_TRIES = 1             # no transport retries inside a backfill/poll: the caller decides what happens next
BACKFILL_BUDGET_SEC = 30.0  # whole backfill (all pages + details); exceeding it raises BackfillError
POLL_FALLBACK_SEC = 30.0   # no-key REST polling interval (< HEARTBEAT_SEC so the watchdog stays quiet)
ENV_REST_FALLBACK = "UPBIT_NOTICE_REST_FALLBACK"
BACKFILL_MAX_PAGES = 5
BACKFILL_SLACK_MS = 5 * 60 * 1000
BODY_RAW_MAX = 4000

KST = timezone(timedelta(hours=9))


class BadResponse(Exception):
    pass


class IncompleteSnapshot(Exception):
    pass


class MissingCredentials(Exception):
    pass


class UpbitWsError(Exception):
    pass


class BackfillError(Exception):
    """REST backfill could not complete (timeout / HTTP error / bad shape / budget exceeded)."""


class UpbitPollError(Exception):
    """No-key REST polling fallback: one poll of the announcement list failed."""


# ----------------------------------------------------------------------------- http helper
def get_json(http, url, params=None, headers=None, timeout=None, tries=None, deadline=None):
    """Works with the shared access_http.HttpClient (get_json, honours timeout/tries/deadline; each is forwarded
    only when not None) or a plain fetch(url, headers=None) callable (which has no timeout parameter).
    deadline: wall-clock seconds per attempt (access_http raises DeadlineExceeded, a TimeoutError)."""
    if http is None:
        raise BadResponse("no http client injected")
    if hasattr(http, "get_json"):
        kw = {k: v for k, v in (("timeout", timeout), ("tries", tries), ("deadline", deadline)) if v is not None}
        return http.get_json(url, params=params, headers=headers, **kw)
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    return http(url, headers)


# ----------------------------------------------------------------------------- time helpers (all UTC ms)
def kst_ms(y, mo, d, h=0, mi=0, s=0):
    return int(datetime(y, mo, d, h, mi, s, tzinfo=KST).timestamp() * 1000)


def parse_ts_ms(v, naive_tz=KST):
    """ISO-8601 string (offset honoured; naive => KST), 'yyyy-MM-dd HH:mm:ss' (KST) or epoch ms/s -> UTC ms."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v if v > 1e11 else v * 1000)
    s = str(v).strip()
    if re.fullmatch(r"\d{10,13}", s):
        return parse_ts_ms(int(s))
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=naive_tz)
    return int(dt.timestamp() * 1000)


# ----------------------------------------------------------------------------- JWT (HS256, stdlib only)
def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def make_jwt(access_key, secret_key, nonce=None):
    """Upbit auth token without query params: HS256 over {access_key, nonce}."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"access_key": access_key, "nonce": nonce or str(uuid.uuid4())}
    signing_input = (_b64url(json.dumps(header, separators=(",", ":")).encode()) + "." +
                     _b64url(json.dumps(payload, separators=(",", ":")).encode()))
    sig = hmac.new(secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return signing_input + "." + _b64url(sig)


def read_credentials(env=None):
    env = os.environ if env is None else env
    ak, sk = (env.get(ENV_ACCESS_KEY) or "").strip(), (env.get(ENV_SECRET_KEY) or "").strip()
    return (ak, sk) if ak and sk else None


# ----------------------------------------------------------------------------- upbit_market
def _slim_market(m):
    keep = {k: m.get(k) for k in ("market", "korean_name", "english_name", "market_warning") if k in m}
    ev = m.get("market_event")
    if isinstance(ev, dict):
        keep["market_event"] = {"warning": ev.get("warning"), "caution": ev.get("caution")}
    return keep


def market_warned(m):
    ev = m.get("market_event") if isinstance(m.get("market_event"), dict) else {}
    return bool(ev.get("warning")) or str(m.get("market_warning") or "").upper() == "CAUTION"


def market_status(m):
    return "SUSPENDED" if (market_warned(m) and WARNING_AS_SUSPENDED) else "LIVE"


def map_market(m):
    """-> SPOT item, or an intentionally invalid item (radar_core's schema gate counts it) for junk rows."""
    if not isinstance(m, dict) or not isinstance(m.get("market"), str) or m["market"].count("-") != 1 \
            or not all(m["market"].split("-")):
        return {"access_kind": "SPOT"}
    it = rc.map_upbit_market(m)
    it.update(status=market_status(m), warning=market_warned(m), raw=_slim_market(m))
    return it


def split_by_quote(items, required=REQUIRED_QUOTES):
    """{quote: [items]} for every quote present; required quotes with no items become IncompleteSnapshot."""
    scopes, invalid = {}, []
    for it in items:
        q = it.get("quote")
        if q:
            scopes.setdefault(q, []).append(it)
        else:
            invalid.append(it)
    for q in required:
        if not scopes.get(q):
            scopes[q] = IncompleteSnapshot(f"no {q} markets in response (partial list?)")
    # junk rows are attached to the largest scope so the schema gate sees them (and skips miss counting)
    if invalid:
        big = max((k for k, v in scopes.items() if isinstance(v, list)), key=lambda k: len(scopes[k]), default=None)
        if big:
            scopes[big].extend(invalid)
    return scopes


def fetch_markets(http):
    d = get_json(http, MARKETS_URL, params={"is_details": "true"})
    if not isinstance(d, list) or not d:
        raise BadResponse(f"unexpected /v1/market/all response: {type(d).__name__}")
    return split_by_quote([map_market(m) for m in d])


# ============================================================================= shared KR notice classifier
_IGNORE = ("이벤트", "에어드랍", "에어드롭", "airdrop", "event", "연기", "철회", "취소", "postpone", "withdrawn",
           "cancel", "유의촉구", "주의촉구", "caution")
_WARN_LIFT = ("유의종목지정해제", "유의종목해제", "투자유의종목지정해제", "투자유의해제", "유의지정해제",
              "investmentwarninglifted", "warningdesignationlifted", "warningreleased", "removalofinvestmentwarning")
_WARN = ("유의종목지정", "투자유의종목", "투자유의지정", "유의종목으로지정", "유의종목", "investmentwarning",
         "designatedasawarning", "warningdesignation")
_RESUME = ("입출금재개", "입금재개", "출금재개", "거래재개", "재개", "resum", "lifted",
           "reopen", "reinstat")
_DELIST = ("거래지원종료", "거래지원을종료", "상장폐지", "delist", "terminationoftradingsupport",
           "endoftradingsupport", "tradingsupporttermination")
_SUSPEND = ("유의종목지정", "투자유의종목", "투자유의지정", "유의종목으로지정", "입출금일시중단", "입출금중단",
            "입출금일시중지", "입출금중지", "입금일시중단", "출금일시중단", "입금중단", "출금중단", "입금중지", "출금중지",
            "거래일시중단", "거래중단", "거래일시중지", "거래정지", "suspension", "suspend", "halt")
_LIST = ("신규거래지원", "신규거래", "마켓추가", "마켓지원", "신규상장", "신규디지털자산", "newlisting",
         "newdigitalasset", "marketsupport", "marketaddition", "listingof", "listing")

_TICKER_RE = re.compile(r"\(\s*([A-Z0-9][A-Z0-9.\-]{0,14})\s*\)")
_QUOTE_WORD = {"KRW": "KRW", "원화": "KRW", "BTC": "BTC", "비트코인": "BTC", "USDT": "USDT", "테더": "USDT"}
_QUOTE_RE = re.compile(r"((?:KRW|BTC|USDT|원화|비트코인|테더)(?:\s*(?:,|/|·|및|&|and)\s*(?:KRW|BTC|USDT|원화|비트코인|테더))*)"
                       r"\s*(?:마켓|market)", re.I)
_NETWORK_RE = re.compile(r"(?:\(\s*([A-Z0-9]{2,15})\s*\)|([A-Za-z][A-Za-z0-9]{1,20}))\s*(?:네트워크|network)", re.I)


def compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or "")).lower()


def classify_title(title, categories=()):
    """-> 'LISTING' | 'DELISTING' | 'SUSPEND' | 'RESUME' (access changes), 'WARNING' | 'WARNING_LIFTED'
    (유의 종목 designation: recorded as a marker, never a state change), or None (not relevant / ambiguous)."""
    c = compact(title)
    cats = {compact(x) for x in categories or ()}
    if not c or cats & {"이벤트", "event"}:
        return None
    if any(k in c for k in _IGNORE):
        return None
    if any(k in c for k in _WARN_LIFT) or (("유의" in c or "warning" in c) and ("해제" in c or "lift" in c)):
        return "WARNING_LIFTED"
    for action, keys in (("DELISTING", _DELIST), ("WARNING", _WARN), ("RESUME", _RESUME), ("SUSPEND", _SUSPEND),
                         ("LISTING", _LIST)):
        if any(k in c for k in keys):
            return action
    # Category-only hints (Bithumb): '마켓추가' / '거래지원종료' / '투자유의'
    if cats & {"마켓추가", "신규상장"}:
        return "LISTING"
    if cats & {"거래지원종료"}:
        return "DELISTING"
    if cats & {"투자유의"}:
        return "WARNING"
    return None


def wallet_kinds(title):
    """Deposit/withdraw notices target DEPOSIT_NETWORK / WITHDRAW_NETWORK, never the SPOT market."""
    c = compact(title)
    if "입출금" in c or "deposit/withdraw" in c or ("deposit" in c and "withdraw" in c):
        return ["DEPOSIT_NETWORK", "WITHDRAW_NETWORK"]
    if "입금" in c or "deposit" in c:
        return ["DEPOSIT_NETWORK"]
    if "출금" in c or "withdraw" in c:
        return ["WITHDRAW_NETWORK"]
    return []


def extract_symbols(title):
    out = []
    for m in _TICKER_RE.finditer(unicodedata.normalize("NFKC", title or "")):
        sym = m.group(1).upper()
        if sym.isdigit() or sym in out:
            continue
        out.append(sym)
    return out


def extract_quotes(text):
    out = []
    for m in _QUOTE_RE.finditer(unicodedata.normalize("NFKC", text or "")):
        for tok in re.split(r"\s*(?:,|/|·|및|&|and)\s*", m.group(1), flags=re.I):
            q = _QUOTE_WORD.get(tok.strip().upper()) or _QUOTE_WORD.get(tok.strip())
            if q and q not in out:
                out.append(q)
    return out


def extract_network(title):
    m = _NETWORK_RE.search(unicodedata.normalize("NFKC", title or ""))
    if not m:
        return ""
    return canonical_chain(m.group(1) or m.group(2))


_DATE_FULL = re.compile(r"(20\d{2})\s*(?:년|[.\-/])\s*(\d{1,2})\s*(?:월|[.\-/])\s*(\d{1,2})\s*일?")
_DATE_SHORT = re.compile(r"(?<![\d.])(\d{1,2})\s*(?:월\s*(\d{1,2})\s*일|/(\d{1,2}))(?![\d/])")
_TIME = re.compile(r"\s*(?:\([^)]{1,6}\))?\s*(오전|오후|AM|PM)?\s*(\d{1,2})\s*(?::\s*(\d{2})|시(?:\s*(\d{1,2})\s*분)?)", re.I)
_EFFECTIVE_KEYS = {
    "DELISTING": ("거래지원종료일시", "종료일시", "종료시점", "종료예정", "delistingdate", "terminationdate"),
    "LISTING": ("거래지원개시", "개시시점", "거래개시", "거래시작", "오픈", "tradingopens", "tradingstarts"),
    "SUSPEND": ("중단일시", "중단시점", "지정일시"),
    "RESUME": ("재개일시", "재개시점", "해제일시"),
}


def _time_after(text, pos):
    m = _TIME.match(text, pos)
    if not m:
        return None
    h, mi = int(m.group(2)), int(m.group(3) or m.group(4) or 0)
    ampm = (m.group(1) or "").upper()
    if ampm in ("오후", "PM") and h < 12:
        h += 12
    if ampm in ("오전", "AM") and h == 12:
        h = 0
    if h > 24 or mi > 59:
        return None
    return min(h, 23), mi if h < 24 else 59


def find_datetime_kst(text, ref_ms):
    """First 'yyyy년 M월 d일 HH:MM' / 'yyyy-MM-dd HH:mm' / 'M/d HH:mm' / 'M월 d일 HH시' in text -> UTC ms (KST).
    Short dates take their year from ref_ms (rolled forward if that would land > 30 days before ref)."""
    if not text:
        return None
    text = unicodedata.normalize("NFKC", text)
    cands = []
    for m in _DATE_FULL.finditer(text):
        t = _time_after(text, m.end()) or (0, 0)
        try:
            cands.append((m.start(), kst_ms(int(m.group(1)), int(m.group(2)), int(m.group(3)), *t)))
        except ValueError:
            continue
    full_spans = [(m.start(), m.end()) for m in _DATE_FULL.finditer(text)]
    ref = datetime.fromtimestamp((ref_ms or rc.now_ms()) / 1000, KST)
    for m in _DATE_SHORT.finditer(text):
        if any(a <= m.start() < b for a, b in full_spans):
            continue
        t = _time_after(text, m.end())
        if t is None:            # a bare 'M/d' is too ambiguous without a time
            continue
        mo, d = int(m.group(1)), int(m.group(2) or m.group(3))
        try:
            ms = kst_ms(ref.year, mo, d, *t)
            if ms < (ref_ms or 0) - 30 * 86400 * 1000:
                ms = kst_ms(ref.year + 1, mo, d, *t)
        except ValueError:
            continue
        cands.append((m.start(), ms))
    return min(cands)[1] if cands else None


def parse_effective_at(action, title, body, ref_ms):
    """Effective/opening time: title first, then the body window after an action keyword, then the first body date."""
    t = find_datetime_kst(title, ref_ms)
    if t:
        return t
    if not body:
        return None
    nb = unicodedata.normalize("NFKC", body)
    flat = re.sub(r"\s+", "", nb).lower()
    for key in _EFFECTIVE_KEYS.get(action, ()):
        i = flat.find(key)
        if i >= 0:
            # map the compact index back to the original text approximately via a window on the compact string
            window = flat[i:i + 80]
            t = find_datetime_kst(_respace(window), ref_ms)
            if t:
                return t
    return find_datetime_kst(nb, ref_ms)


def _respace(s):
    """Compact text lost its spaces; re-insert separators around digits so the date/time regexes still match."""
    s = re.sub(r"(\d)(년|월|일|시|분)", r"\1\2 ", s)
    return re.sub(r"(일)(\()", r"\1 \2", s)


def build_targets(action, title, categories=()):
    """Targets for an access-change notice. A notice without an explicit market gets quote '' for every action:
    LISTING merges with the later concrete market; DELISTING/SUSPEND/RESUME are applied by radar_core to every
    existing market of the asset (quote wildcard, STATE_MACHINE.md 6.1)."""
    kinds = wallet_kinds(title)
    if action == "LISTING" and kinds:      # '입출금 지원' of an existing asset is not a market listing
        kinds = []
    syms = extract_symbols(title)
    if not syms:
        return []
    if kinds:
        net = extract_network(title)
        return [{"symbol": s, "access_kind": k, "network": net, "quote": ""} for s in syms for k in kinds]
    quotes = extract_quotes(title) or [""]
    syms = [s for s in syms if not (s in quotes and len(syms) > 1)]
    return [{"symbol": s, "access_kind": "SPOT", "quote": q} for s in syms for q in quotes if s != q]


def warning_announcement(platform_id, symbols, quotes, designated, source_event_id, announced_at, *, title="",
                         source_detected_at=None, raw=None, url=None):
    """Warning designation (유의 종목) as a NON-state-changing marker announcement (see module docstring):
    asset_key 'warning:<SYM>' + action SUSPEND (designated) / RESUME (lifted). Never touches the real market."""
    flag = "DESIGNATED" if designated else "LIFTED"
    raw = dict(raw or {}, warning=flag)
    return {
        "action": "SUSPEND" if designated else "RESUME", "platform_id": platform_id,
        "targets": [{"asset_key": WARNING_ASSET_PREFIX + s, "symbol": s, "access_kind": "SPOT", "quote": q}
                    for s in symbols for q in (quotes or [""])],
        "announced_at": announced_at, "source_detected_at": source_detected_at, "effective_at": None,
        "source_event_id": source_event_id, "title": title, "warning": flag, "raw": raw, "url": url or None,
    }


def notice_announcement(platform_id, title, source_event_id, announced_at, *, body=None, categories=(),
                        source_detected_at=None, raw=None, url=None):
    """Generic exchange notice -> radar_core announcement dict, or None if it is not relevant."""
    action = classify_title(title, categories)
    if action is None:
        return None
    if action in ("WARNING", "WARNING_LIFTED"):
        syms = extract_symbols(title)
        if not syms:
            return None
        return warning_announcement(platform_id, syms, extract_quotes(title), action == "WARNING", source_event_id,
                                    announced_at, title=title, source_detected_at=source_detected_at, raw=raw, url=url)
    targets = build_targets(action, title, categories)
    if not targets:
        return None
    return {
        "action": action, "platform_id": platform_id, "targets": targets,
        "announced_at": announced_at, "source_detected_at": source_detected_at,
        "effective_at": parse_effective_at(action, title, body, announced_at),
        "source_event_id": source_event_id, "title": title, "raw": raw, "url": url or None,
    }


# ============================================================================= upbit_notice parsing
_ABBR = {"ty": "type", "et": "event_type", "uid": "uuid", "tt": "title", "cat": "category", "url": "url",
         "flat": "first_listed_at", "lat": "listed_at", "tms": "timestamp", "st": "stream_type", "bd": "body"}


def expand_message(msg):
    """Accept DEFAULT and SIMPLE (abbreviated) formats."""
    return {_ABBR.get(k, k): v for k, v in msg.items()}


def _notice_id(n):
    nid = n.get("uuid") or n.get("id")
    if nid in (None, "") and n.get("url"):
        m = re.search(r"[?&]id=(\d+)", str(n["url"]))
        nid = m.group(1) if m else None
    return str(nid) if nid not in (None, "") else ""


def notice_page_url(n):
    nid = _notice_id(n)
    if nid:
        return NOTICE_PAGE_URL.format(id=nid)
    u = str(n.get("url") or "").strip()
    return u if u.startswith(("https://", "http://")) else None


def notice_event_id(n):
    nid = _notice_id(n)
    if not nid:
        basis = compact(n.get("title")) + "|" + str(n.get("first_listed_at") or n.get("listed_at") or "")
        nid = "h" + hashlib.sha256(basis.encode()).hexdigest()[:16]
    first, last = parse_ts_ms(n.get("first_listed_at")), parse_ts_ms(n.get("listed_at"))
    if first and last and last > first:
        return f"upbit:notice:{nid}:u{last}"
    return f"upbit:notice:{nid}"


def _slim_notice(n):
    out = {k: n.get(k) for k in ("event_type", "uuid", "id", "title", "category", "url", "first_listed_at",
                                 "listed_at") if n.get(k) is not None}
    if n.get("body"):
        out["body"] = str(n["body"])[:BODY_RAW_MAX]
    return out


def parse_notice(n):
    """Normalised Upbit notice (WS message or REST row) -> announcement dict or None."""
    n = expand_message(n)
    if n.get("type") not in (None, "announcement"):
        return None
    title = n.get("title") or ""
    if str(n.get("category") or "").strip().lower() not in RELEVANT_CATEGORIES:
        return None
    announced = parse_ts_ms(n.get("first_listed_at")) or parse_ts_ms(n.get("listed_at"))
    return notice_announcement(PLATFORM_ID, title, notice_event_id(n), announced, body=n.get("body"),
                               source_detected_at=parse_ts_ms(n.get("timestamp")),
                               raw=_slim_notice(n), url=notice_page_url(n))


def handle_ws_payload(payload):
    """Raw WS payload (bytes|str) -> list of announcements. Raises UpbitWsError on a server error object."""
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="replace")
    try:
        msg = json.loads(payload)
    except ValueError:
        log.warning("upbit ws: non-JSON payload %r", payload[:200])
        return []
    if isinstance(msg, dict) and "error" in msg:
        err = msg["error"] if isinstance(msg["error"], dict) else {"name": msg["error"]}
        raise UpbitWsError(f"{err.get('name')}: {err.get('message', '')}")
    if not isinstance(msg, dict) or msg.get("status") == "UP":
        return []
    ann = parse_notice(msg)
    return [ann] if ann else []


def subscribe_message(ticket=None, include_body=True):
    return [{"ticket": ticket or f"access-radar-{uuid.uuid4().hex[:12]}"},
            {"type": "announcement", "include_body": include_body},
            {"format": "DEFAULT"}]


# ----------------------------------------------------------------------------- minimal RFC 6455 client
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WsClosed(Exception):
    pass


class WsClient:
    """Minimal RFC 6455 client: handshake, masked client frames, ping/pong, fragmentation, close.
    recv(timeout) returns None on timeout so callers can poll a stop flag."""

    def __init__(self, sock):
        self.sock = sock
        self._buf = b""
        self._frag_op = None
        self._frag = []
        self.closed = False

    @classmethod
    def connect(cls, url, headers=None, timeout=CONNECT_TIMEOUT, sock=None):
        u = urllib.parse.urlsplit(url)
        secure = u.scheme == "wss"
        port = u.port or (443 if secure else 80)
        if sock is None:
            sock = socket.create_connection((u.hostname, port), timeout=timeout)
            if secure:
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=u.hostname)
        c = cls(sock)
        host = u.hostname if u.port in (None, 443 if secure else 80) else f"{u.hostname}:{port}"
        c.handshake(host, (u.path or "/") + (f"?{u.query}" if u.query else ""), headers or {}, timeout)
        return c

    def handshake(self, host, path, headers, timeout=CONNECT_TIMEOUT):
        key = base64.b64encode(os.urandom(16)).decode()
        lines = [f"GET {path} HTTP/1.1", f"Host: {host}", "Upgrade: websocket", "Connection: Upgrade",
                 f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
        lines += [f"{k}: {v}" for k, v in headers.items()]
        self.sock.settimeout(timeout)
        self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WsClosed("connection closed during handshake")
            data += chunk
            if len(data) > 65536:
                raise WsClosed("handshake response too large")
        head, self._buf = data.split(b"\r\n\r\n", 1)
        status, *hdr_lines = head.decode("latin-1").split("\r\n")
        parts = status.split(" ", 2)
        if len(parts) < 2 or parts[1] != "101":
            raise WsClosed(f"handshake rejected: {status}")
        hdrs = {}
        for ln in hdr_lines:
            if ":" in ln:
                k, v = ln.split(":", 1)
                hdrs[k.strip().lower()] = v.strip()
        expect = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        if hdrs.get("sec-websocket-accept") != expect:
            raise WsClosed("bad Sec-WebSocket-Accept")

    # -- sending
    def _send_frame(self, opcode, payload=b""):
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + n.to_bytes(2, "big")
        else:
            head += bytes([0x80 | 127]) + n.to_bytes(8, "big")
        mask = os.urandom(4)
        self.sock.sendall(head + mask + _xor(payload, mask))

    def send_text(self, text):
        self._send_frame(0x1, text)

    def ping(self, data=b""):
        self._send_frame(0x9, data)

    def close(self, code=1000):
        if self.closed:
            return
        self.closed = True
        try:
            self._send_frame(0x8, code.to_bytes(2, "big"))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    # -- receiving
    def _parse_frame(self):
        b = self._buf
        if len(b) < 2:
            return None
        fin, opcode = b[0] & 0x80, b[0] & 0x0F
        masked, n, pos = b[1] & 0x80, b[1] & 0x7F, 2
        if n == 126:
            if len(b) < 4:
                return None
            n, pos = int.from_bytes(b[2:4], "big"), 4
        elif n == 127:
            if len(b) < 10:
                return None
            n, pos = int.from_bytes(b[2:10], "big"), 10
        mask = b""
        if masked:
            if len(b) < pos + 4:
                return None
            mask, pos = b[pos:pos + 4], pos + 4
        if len(b) < pos + n:
            return None
        payload = b[pos:pos + n]
        if masked:
            payload = _xor(payload, mask)
        self._buf = b[pos + n:]
        return bool(fin), opcode, payload

    def recv(self, timeout=RECV_TIMEOUT):
        """-> ('text'|'binary'|'ping'|'pong', payload) or None on timeout. Raises WsClosed."""
        deadline = time.monotonic() + timeout
        while True:
            fr = self._parse_frame()
            if fr is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.sock.settimeout(remaining)
                try:
                    chunk = self.sock.recv(65536)
                except (socket.timeout, TimeoutError, ssl.SSLWantReadError):
                    return None
                if not chunk:
                    raise WsClosed("connection closed by peer")
                self._buf += chunk
                continue
            fin, op, payload = fr
            if op == 0x9:
                self._send_frame(0xA, payload)
                return "ping", payload
            if op == 0xA:
                return "pong", payload
            if op == 0x8:
                code = int.from_bytes(payload[:2], "big") if len(payload) >= 2 else 1005
                reason = payload[2:].decode("utf-8", errors="replace")
                self.close()
                raise WsClosed(f"close frame {code} {reason}".strip())
            if op in (0x1, 0x2):
                if fin:
                    return ("text" if op == 0x1 else "binary"), payload
                self._frag_op, self._frag = op, [payload]
                continue
            if op == 0x0 and self._frag_op is not None:
                self._frag.append(payload)
                if fin:
                    op, data = self._frag_op, b"".join(self._frag)
                    self._frag_op, self._frag = None, []
                    return ("text" if op == 0x1 else "binary"), data
                continue
            raise WsClosed(f"unexpected opcode {op}")


def _xor(data, mask):
    if not data:
        return b""
    m = (mask * (len(data) // 4 + 1))[:len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(m, "big")).to_bytes(len(data), "big")


# ----------------------------------------------------------------------------- stream + backfill
_no_key_warned = False


def rest_fallback_enabled(env=None):
    env = os.environ if env is None else env
    return (env.get(ENV_REST_FALLBACK) or "1").strip().lower() not in ("0", "false", "no", "off")


def _warn_no_key_once(ctx, fallback):
    global _no_key_warned
    if _no_key_warned:
        return
    _no_key_warned = True
    ctx.log.warning(
        "upbit_notice: %s / %s not set. The realtime announcement WebSocket (%s) is a private endpoint and needs an "
        "API key (JWT; no permission scope required), so it is not started. %s", ENV_ACCESS_KEY, ENV_SECRET_KEY,
        WS_URL, f"Falling back to REST polling of {NOTICE_LIST_URL} every {POLL_FALLBACK_SEC:g}s; disconnect gaps "
        "are backfilled over REST." if fallback else f"REST polling fallback disabled ({ENV_REST_FALLBACK}=0); only "
        "gap backfill over REST will run.")


def run_notice_ws(ctx, connect=None, credentials=None, clock=time.monotonic):
    """Blocks while connected; returns/raises on disconnect (the runner reconnects with backoff + backfill).
    Without credentials: one WARNING, then the REST polling fallback (run_rest_poll) under the same contract."""
    creds = credentials or read_credentials()
    if not creds:
        fallback = rest_fallback_enabled()
        _warn_no_key_once(ctx, fallback)
        if fallback:
            return run_rest_poll(ctx, clock=clock)
        ctx.stop_event.wait(MISSING_CREDS_WAIT)
        raise MissingCredentials(f"{ENV_ACCESS_KEY}/{ENV_SECRET_KEY} not set")
    ws = (connect or WsClient.connect)(WS_URL, headers={"Authorization": "Bearer " + make_jwt(*creds)},
                                       timeout=CONNECT_TIMEOUT)
    try:
        ws.send_text(json.dumps(subscribe_message()))
        early = ws.recv(timeout=RECV_TIMEOUT)          # auth / param errors arrive immediately
        if early and early[0] in ("text", "binary"):
            anns = handle_ws_payload(early[1])          # raises UpbitWsError before we claim "connected"
        else:
            anns = []
        ctx.connected()
        for a in anns:
            ctx.emit_announcement(a)
        last_ping = clock()
        while not ctx.should_stop():
            if clock() - last_ping >= PING_EVERY:
                ws.ping()
                last_ping = clock()
            m = ws.recv(timeout=RECV_TIMEOUT)
            if m is None:
                continue
            ctx.heartbeat()
            kind, payload = m
            if kind in ("ping", "pong"):
                continue
            for a in handle_ws_payload(payload):
                ctx.emit_announcement(a)
    finally:
        ws.close()


def _notice_rows(d):
    if not isinstance(d, dict) or d.get("success") is False or not isinstance(d.get("data"), dict):
        raise BadResponse("unexpected announcements response shape")
    rows = d["data"].get("notices")
    if not isinstance(rows, list):
        raise BadResponse("announcements response without 'notices' list")
    return rows, int(d["data"].get("total_pages") or 1)


def fetch_notice_detail(http, nid, timeout=REST_TIMEOUT_SEC):
    d = get_json(http, NOTICE_DETAIL_URL.format(id=nid), timeout=timeout, tries=REST_TRIES, deadline=timeout)
    if isinstance(d, dict) and isinstance(d.get("data"), dict):
        return d["data"].get("body")
    return None


def fetch_notice_page(http, page, timeout=REST_TIMEOUT_SEC):
    d = get_json(http, NOTICE_LIST_URL, params={"os": "web", "page": page, "per_page": 20, "category": "all"},
                 timeout=timeout, tries=REST_TRIES, deadline=timeout)
    return _notice_rows(d)


def backfill_notices(http, since_ms, until_ms, max_pages=BACKFILL_MAX_PAGES, detail_for=("DELISTING", "LISTING"),
                     budget_sec=None, clock=time.monotonic):
    """Announcements published (or updated) in [since_ms, until_ms] from the web notice list (newest first).
    DELISTING/LISTING notices get their body fetched so effective_at matches what the WS path would parse.
    Raises BackfillError if a list page fails or the time budget runs out: a timeout is never 'no notices'."""
    budget = BACKFILL_BUDGET_SEC if budget_sec is None else budget_sec
    t0 = clock()
    lo, hi = (since_ms or 0) - BACKFILL_SLACK_MS, (until_ms or rc.now_ms()) + BACKFILL_SLACK_MS
    out, seen = [], set()
    for page in range(1, max_pages + 1):
        left = budget - (clock() - t0)
        if left <= 0:
            raise BackfillError(f"backfill budget {budget:g}s exhausted before page {page} "
                                f"({len(out)} announcements found so far, discarded)")
        try:
            rows, total_pages = fetch_notice_page(http, page, timeout=min(REST_TIMEOUT_SEC, left))
        except Exception as e:  # noqa: BLE001 - timeout / DeadlineExceeded / HTTP / shape -> BackfillError, never []
            msg = (f"announcement list page {page} failed after {clock() - t0:.1f}s: {type(e).__name__}: {e}")
            log.warning("upbit_notice backfill %s..%s: %s", since_ms, until_ms, msg)
            raise BackfillError(msg) from e
        oldest = None
        for r in rows:
            if not isinstance(r, dict):
                continue
            listed = parse_ts_ms(r.get("listed_at")) or parse_ts_ms(r.get("first_listed_at"))
            oldest = listed if oldest is None else min(oldest, listed or oldest)
            if listed is None or not (lo <= listed <= hi):
                continue
            ann = parse_notice(r)
            if ann is None or ann["source_event_id"] in seen:
                continue
            left = budget - (clock() - t0)
            if ann["action"] in detail_for and ann["effective_at"] is None and _notice_id(r) and left > 1:
                try:
                    body = fetch_notice_detail(http, _notice_id(r), timeout=min(REST_TIMEOUT_SEC, left))
                    if body:
                        ann = parse_notice(dict(r, body=body)) or ann
                except Exception as e:  # noqa: BLE001 - title-only announcement is still useful
                    log.info("upbit backfill: detail %s failed: %s", _notice_id(r), e)
            seen.add(ann["source_event_id"])
            out.append(ann)
        if page >= total_pages or not rows or (oldest is not None and oldest < lo):
            break
    out.sort(key=lambda a: a["announced_at"] or 0)
    return out


def poll_latest(http):
    """One no-key poll: page 1 of the announcement list. Raises UpbitPollError on any failure."""
    try:
        rows, _ = fetch_notice_page(http, 1)
        return rows
    except Exception as e:  # noqa: BLE001 - timeout / DeadlineExceeded / HTTP / shape
        raise UpbitPollError(f"REST announcement poll failed: {type(e).__name__}: {e}") from e


def run_rest_poll(ctx, clock=time.monotonic, wall=None):
    """No-key fallback with the stream contract: first successful poll -> ctx.connected() (the runner closes the
    gap and backfills it via backfill_notices); then poll every POLL_FALLBACK_SEC, heartbeat after each success
    and emit notices listed since the connection (older ones belong to the backfill).  A failed poll raises, so
    the runner records the error (source_run.last_error, source_health DOWN, source_disconnect) and reconnects
    with backoff; the next successful connect backfills that gap."""
    wall = wall or rc.now_ms
    rows = poll_latest(ctx.http)
    ctx.connected()
    ctx.heartbeat()
    since = wall() - BACKFILL_SLACK_MS
    emitted = set()

    def emit(rows):
        for r in rows:
            if not isinstance(r, dict):
                continue
            listed = parse_ts_ms(r.get("listed_at")) or parse_ts_ms(r.get("first_listed_at"))
            if listed is None or listed < since:
                continue
            ann = parse_notice(r)
            if ann and ann["source_event_id"] not in emitted:
                emitted.add(ann["source_event_id"])
                ctx.emit_announcement(ann)

    emit(rows)
    next_at = clock() + POLL_FALLBACK_SEC
    while not ctx.should_stop():
        wait = next_at - clock()
        if wait > 0:
            ctx.stop_event.wait(min(1.0, wait))
            continue
        rows = poll_latest(ctx.http)
        ctx.heartbeat()
        emit(rows)
        next_at = clock() + POLL_FALLBACK_SEC


# ----------------------------------------------------------------------------- registration
PLATFORMS = [{"platform_id": PLATFORM_ID, "name": "Upbit", "platform_type": "CEX", "country": "KR"}]
SOURCES = {
    "upbit_market": {
        "kind": "snapshot", "fetch": fetch_markets, "period_sec": 30,
        "source": {"name": "Upbit /v1/market/all", "kind": "SNAPSHOT", "tier": "OFFICIAL_STRUCTURED",
                   "origin_platform_id": PLATFORM_ID},
    },
    "upbit_notice": {
        "kind": "stream", "run": run_notice_ws, "backfill": backfill_notices, "heartbeat_sec": HEARTBEAT_SEC,
        "source": {"name": "Upbit announcement WebSocket", "kind": "ANNOUNCEMENT", "tier": "OFFICIAL_ANNOUNCEMENT",
                   "origin_platform_id": PLATFORM_ID},
    },
}


def register(conn, at=None):
    """Register platform + every source (tests / ops; the runner registers from PLATFORMS + SOURCES itself)."""
    for p in PLATFORMS:
        p = dict(p)
        rc.register_platform(conn, p.pop("platform_id"), at=at, **p)
    for sid, spec in SOURCES.items():
        rc.register_source(conn, sid, at=at, **spec["source"])
