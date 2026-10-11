"""NewListings adapter — third-party listing/delisting relay (newlistings.pro New Listings Feed).

wss://ws.newlistings.pro/v1/feed   (FREE tier: feed channel only, ~3s delay, no history/backfill)
Auth: 'Authorization: Bearer <key>' on the upgrade request.  Key comes from env
NEWLISTINGS_API_KEY (free key: t.me/NLF_websocket_bot).  Without a key the socket is not
attempted: one WARNING, idle wait, then fail (the runner retries with backoff; nothing ingested).

The feed mixes listings and delistings on one channel; each event is classified from the text:
    {"id", "time" (ms epoch), "announcement": "$PIEVERSE listed on Upbit spot (KRW)",
     "original_title": "파이버스(PIEVERSE) 신규 거래지원 안내 (KRW, BTC, USDT 마켓)",
     "url", "exchange": "upbit", "type": "spot"|"futures"|"pre-market"|...,
     "detections": [{"ticker": "PIEVERSE", ...}]}

The upstream id is not stable across deliveries, so the announcement id is built from content:
'nl:<exchange>:<SYM>:<KIND>:<ACTION>:<quote>' (single symbol/quote) or, for multi-symbol/multi-
quote events, a content-hash variant.  type maps to access_kind: spot -> SPOT, futures -> PERP,
pre-market -> ROADMAP, anything else -> skipped.  Unrecognized announcements (no list/delist
keyword) are skipped rather than guessed.

Relay semantics (STATE_MACHINE.md §5/§9): source tier THIRD_PARTY with is_relay — LISTING lands as
ANNOUNCED+provisional until an official notice or structured observation confirms it; DELISTING
becomes a provisional REMOVE episode and never changes state by itself.  Messages for exchanges we
mirror officially carry origin_group (upbit_notice / bithumb_notice / korbit_notice) so relayed and
official announcements corroborate the same episode; unknown exchanges auto-register as platforms.

FREE has no REST history, so there is no backfill: disconnect gaps stay unbackfilled (max age 7d,
then dropped) and only realtime events are ingested.  The server pings every ~30s (WsClient answers
automatically); HEARTBEAT_SEC=60 means a stalled feed is reconnected within a minute.
"""
import hashlib
import json
import re
import sys
import unicodedata

if __package__ in (None, ""):                                    # direct script run
    sys.path.insert(0, __file__.rsplit("/", 2)[0])

try:
    from .upbit import WsClient, WsClosed
except ImportError:                                              # direct script run
    from adapters.upbit import WsClient, WsClosed  # noqa: E402

WS_URL = "wss://ws.newlistings.pro/v1/feed"
ENV_KEY = "NEWLISTINGS_API_KEY"
SOURCE_ID = "newlistings"
HEARTBEAT_SEC = 60
RECV_TIMEOUT = 1.0
CONNECT_TIMEOUT = 10.0
MISSING_CREDS_WAIT = 300.0   # no key: idle this long before failing again (avoids 30s log spam)
AUTH_FAIL_WAIT = 120.0       # bad key: slow the retry cadence (the docs warn about IP bans)
LISTING = "LISTING"
DELISTING = "DELISTING"
ORIGIN_GROUPS = {"upbit": "upbit_notice", "bithumb": "bithumb_notice", "korbit": "korbit_notice"}
KIND_BY_TYPE = {"spot": "SPOT", "futures": "PERP", "pre-market": "ROADMAP", "premarket": "ROADMAP"}
KNOWN_QUOTES = {
    "KRW", "BTC", "USDT", "USD", "USDC", "ETH", "BUSD", "FDUSD", "TUSD", "DAI", "EUR", "TRY",
    "BRL", "ARS", "MXN", "JPY", "VND", "IDR", "INR", "PHP", "GBP", "AUD", "CAD", "SGD", "AED",
    "COP", "PEN", "CLP", "NGN", "ZAR", "UAH", "PLN", "CZK", "HUF", "RON", "DKK", "SEK", "NOK",
    "CHF", "CNY", "HKD", "TWD", "MYR", "THB", "RUB", "EGP",
}
_QUOTE_RE = re.compile(r"\(([A-Z][A-Z0-9]{1,9})\)")              # '(KRW)' in the announcement summary
_MARKET_RE = re.compile(r"\(([^()]*마켓)")                        # Korean title: "(KRW, BTC, USDT 마켓)"
_SYMBOL_RE = re.compile(r"\$([A-Z0-9][A-Z0-9.\-]{0,14})")        # '$PIEVERSE' in the summary
_AUTH_MARKERS = ("401", "403", "unauthorized", "forbidden", "invalid key", "invalid api key",
                 "missing key", "authentication")


class NewListingsError(Exception):
    pass


# --------------------------------------------------------------------------- payload -> announcement
def _norm(text):
    return unicodedata.normalize("NFKC", text or "")


def classify_action(text):
    c = re.sub(r"\s+", "", _norm(text)).lower()
    if not c:
        return None
    if "delist" in c or "deregister" in c or "거래지원종료" in c or "상장폐지" in c:
        return DELISTING
    if "list" in c or "신규거래지원" in c or "신규상장" in c:
        return LISTING
    return None


def extract_quotes(announcement, title):
    """Quote currencies named in the text -> e.g. ['KRW', 'BTC'] or [''] when none is named."""
    out = []
    for tok in _QUOTE_RE.findall(_norm(announcement)):
        if tok in KNOWN_QUOTES and tok not in out:
            out.append(tok)
    m = _MARKET_RE.search(_norm(title))
    if m:
        for tok in re.split(r"[,/&·+]|및|마켓", m.group(1)):
            q = tok.strip().upper()
            if q in KNOWN_QUOTES and q not in out:
                out.append(q)
    return out or [""]


def extract_symbols(msg):
    out = []
    for d in msg.get("detections") or []:
        if isinstance(d, dict):
            t = str(d.get("ticker") or "").strip().upper()
            if t and t not in out:
                out.append(t)
    if not out:
        for t in _SYMBOL_RE.findall(_norm(msg.get("announcement"))):
            if not t.isdigit() and t not in out:
                out.append(t)
    return out


def event_id(exchange, kind, action, syms, quotes, text):
    if len(syms) == 1 and len(quotes) == 1:
        return f"nl:{exchange}:{syms[0]}:{kind}:{action}:{quotes[0]}"
    basis = f"{exchange}|{kind}|{action}|{','.join(syms)}|{','.join(quotes)}|{text}"
    return f"nl:{exchange}:{kind}:{action}:" + hashlib.sha1(basis.encode()).hexdigest()[:12]


def _ms(t):
    try:
        t = int(t)
    except (TypeError, ValueError):
        return None
    if t >= 10**12:                                              # ms epoch
        return t
    if t >= 10**9:                                               # seconds epoch
        return t * 1000
    return None


def parse_message(msg):
    """Feed event dict -> announcement dict, or None when it is not an access listing/delisting."""
    if not isinstance(msg, dict):
        return None
    exchange = str(msg.get("exchange") or "").strip().lower()
    text = msg.get("announcement") or msg.get("original_title") or ""
    action = classify_action(text)
    kind = KIND_BY_TYPE.get(str(msg.get("type") or "").strip().lower())
    syms = extract_symbols(msg)
    if not exchange or not action or not kind or not syms:
        return None
    quotes = extract_quotes(msg.get("announcement"), msg.get("original_title"))
    t = _ms(msg.get("time"))
    slim = {k: msg.get(k) for k in ("id", "time", "announcement", "original_title", "exchange",
                                    "type", "url") if msg.get(k) is not None}
    return {"action": action, "platform_id": exchange,
            "targets": [{"symbol": s, "access_kind": kind, "quote": q} for s in syms for q in quotes],
            "announced_at": t, "source_detected_at": t,
            "source_event_id": event_id(exchange, kind, action, syms, quotes, text),
            "title": text, "origin_group": ORIGIN_GROUPS.get(exchange, ""),
            "url": msg.get("url") or None, "raw": slim}


def handle_ws_payload(payload):
    """Raw WS payload (bytes|str) -> [announcement, ...]. Raises NewListingsError on error objects."""
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="replace")
    try:
        msg = json.loads(payload)
    except ValueError:
        return []
    if isinstance(msg, dict) and msg.get("type") in ("success", "pong"):   # handshake / status
        return []
    if isinstance(msg, dict) and msg.get("type") == "error":
        raise NewListingsError(str(msg.get("message") or msg)[:200])
    ann = parse_message(msg)
    return [ann] if ann else []


# --------------------------------------------------------------------------- stream
_no_key_warned = False


def read_key(env=None):
    env = __import__("os").environ if env is None else env
    return (env.get(ENV_KEY) or "").strip()


def _warn_no_key_once(ctx):
    global _no_key_warned
    if _no_key_warned:
        return
    _no_key_warned = True
    ctx.log.warning("newlistings: %s not set — the newlistings.pro feed needs a key (free: "
                    "t.me/NLF_websocket_bot). Not connecting; nothing will be ingested.", ENV_KEY)


def _is_auth_error(e):
    s = str(e).lower()
    return any(m in s for m in _AUTH_MARKERS)


def run(ctx, connect=None, key=None):
    """Blocks while connected; returns/raises on disconnect (the runner reconnects with backoff)."""
    key = key if key is not None else read_key()
    if not key:
        _warn_no_key_once(ctx)
        ctx.stop_event.wait(MISSING_CREDS_WAIT)
        raise NewListingsError(f"{ENV_KEY} not set — get a free key at t.me/NLF_websocket_bot")
    ws = None
    try:
        ws = (connect or WsClient.connect)(WS_URL, headers={"Authorization": f"Bearer {key}"},
                                           timeout=CONNECT_TIMEOUT)
        early = ws.recv(timeout=RECV_TIMEOUT)          # success / error arrives immediately
        if early and early[0] in ("text", "binary"):
            anns = handle_ws_payload(early[1])         # raises NewListingsError on an error object
        else:
            anns = []
        ctx.connected()
        for a in anns:
            ctx.emit_announcement(a)
        while not ctx.should_stop():
            m = ws.recv(timeout=RECV_TIMEOUT)
            if m is None:
                continue
            ctx.heartbeat()
            kind, payload = m
            if kind in ("ping", "pong"):
                continue
            for a in handle_ws_payload(payload):
                ctx.emit_announcement(a)
    except (WsClosed, NewListingsError) as e:
        if _is_auth_error(e):
            ctx.log.warning("newlistings: auth rejected (%s) — check %s. Backing off %gs before retrying.",
                            str(e)[:120], ENV_KEY, AUTH_FAIL_WAIT)
            ctx.stop_event.wait(AUTH_FAIL_WAIT)
        raise
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


KIND = "stream"
PLATFORMS = []          # announcements carry their own exchange platform_id (auto-registered when unknown)
SOURCE = {"name": "NewListings feed (newlistings.pro)", "kind": "ANNOUNCEMENT", "tier": "THIRD_PARTY",
          "is_relay": True}


if __name__ == "__main__":                                       # offline parse demo (no key needed)
    demo = {"id": 1, "time": 1776661200556,
            "announcement": "$PIEVERSE listed on Upbit spot (KRW)",
            "original_title": "파이버스(PIEVERSE) 신규 거래지원 안내 (KRW, BTC, USDT 마켓)",
            "url": "https://example.com/notice", "exchange": "upbit", "type": "spot",
            "detections": [{"ticker": "PIEVERSE"}]}
    print(json.dumps(parse_message(demo), indent=1, ensure_ascii=False))
