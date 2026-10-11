"""Access Radar HTTP client. Stdlib urllib only, zero dependencies.

Why not `http.py`: a module named http.py next to the scripts shadows the stdlib `http` package
(urllib.request does `import http.client`), which breaks every request. Hence `access_http.py`.

Rules (same as rh_v2/sources.get_json, adapted for a long-running loop):
- Per-host rate limit (min gap = 1/rps), thread-safe: concurrent adapters sharing a host queue up.
- 404 and other 4xx: no retry (retrying won't help). 404 doesn't count toward the circuit breaker; other 4xx do.
- 429 / 5xx / timeout / connection errors: retry with exponential backoff (Retry-After is honoured, capped).
- Truncated bodies are transient too: http.client.IncompleteRead / RemoteDisconnected / ConnectionResetError /
  BadStatusLine, and a body shorter than Content-Length (http.client's read() silently returns short data at EOF)
  -> IncompleteBody -> retried like a connection error.  After the last try: TransportError
  "IncompleteBody: read N of M bytes ... after K attempts".
- Body is read in CHUNK-sized pieces until EOF and checked against Content-Length.  The timeout is per socket
  operation (connect / each read), never a total deadline, so a slow 600 KB body through a proxy is fine as long
  as bytes keep arriving (same as curl).  ACCESS_HTTP_TIMEOUT (default 20 s).
- Optional `deadline` (seconds, wall clock, per ATTEMPT) on top of the per-read timeout: connect, headers and
  every body read are bounded by what is left of it; a body still trickling in past the deadline aborts that attempt
  with DeadlineExceeded (a TimeoutError -> transient, counts as one try, retried if tries remain, stat "timeout").
  Default None = no total limit (previous behaviour).
- Sends "Accept-Encoding: gzip, deflate" and decodes it (a truncated gzip stream also counts as IncompleteBody).
- Per-host circuit breaker: CIRCUIT_FAILS consecutive failed calls open it for a cooldown (doubling up to
  CIRCUIT_MAX_COOLDOWN). While open, calls fail fast with CircuitOpen. After the cooldown one probe is let
  through (half-open); success closes it.
- Proxy: ACCESS_PROXY (e.g. http://127.0.0.1:7890) applies to http+https. ACCESS_PROXY="" disables proxies;
  when ACCESS_PROXY is unset, urllib's standard HTTP(S)_PROXY / NO_PROXY env vars apply.
- User agent: ACCESS_UA (default "access-radar/0.1").

Adapters never import this module directly: the runner passes an HttpClient instance to fetch(http).
"""
import gzip
import http.client
import json
import os
import threading
import zlib
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_UA = os.environ.get("ACCESS_UA", "access-radar/0.1 (+Crypto-Market-OS)")
DEFAULT_TIMEOUT = float(os.environ.get("ACCESS_HTTP_TIMEOUT", "20"))   # per socket op (connect / each read)
DEFAULT_TRIES = int(os.environ.get("ACCESS_HTTP_TRIES", "3"))
DEFAULT_RPS = float(os.environ.get("ACCESS_HTTP_RPS", "2"))
CIRCUIT_FAILS = int(os.environ.get("ACCESS_CIRCUIT_FAILS", "5"))
CIRCUIT_COOLDOWN = float(os.environ.get("ACCESS_CIRCUIT_COOLDOWN", "30"))
CIRCUIT_MAX_COOLDOWN = 600.0
MAX_RETRY_AFTER = 30.0
CHUNK = 64 * 1024
ACCEPT_ENCODING = "gzip, deflate"
# transport-level failures that are worth retrying (all transient on flaky proxies / fake-ip TUN)
TRANSIENT = (http.client.IncompleteRead, http.client.RemoteDisconnected, http.client.BadStatusLine,
             ConnectionResetError, ConnectionAbortedError, BrokenPipeError)

# Per-host request rate (requests / second). Documented limits from the design review; keep a margin.
HOST_RPS = {
    "api.upbit.com": 8.0,          # /v1/market/all: 10 req/s
    "api.bithumb.com": 1.0,        # /v1/notices: 1 req/s per IP (we poll every 2s)
    "api.coinone.co.kr": 5.0,
    "api.korbit.co.kr": 5.0,
    "api.ramp.network": 1.0,
    "api.xstocks.fi": 2.0,
    "api.circle.com": 1.0,
}


class HttpError(Exception):
    def __init__(self, status, url, body="", reason=""):
        self.status = status
        self.url = url
        self.body = body
        head = f"HTTP {status} {reason}" if status and status > 0 else str(reason)
        super().__init__(f"{head} {url} {body[:160]}".strip())


class CircuitOpen(HttpError):
    def __init__(self, host, until):
        self.host = host
        self.until = until
        super().__init__(0, host, reason=f"circuit open for {host} until {time.strftime('%H:%M:%S', time.localtime(until))}")


class TransportError(HttpError):
    """Timeout / DNS / connection reset / truncated body after all retries."""
    def __init__(self, url, err, attempts=None):
        self.cause = err
        self.attempts = attempts
        after = f" (after {attempts} attempt{'s' if attempts != 1 else ''})" if attempts else ""
        super().__init__(-1, url, reason=f"{type(err).__name__}: {err}{after}")


class IncompleteBody(Exception):
    """Connection closed before the full body arrived (or the compressed stream was cut)."""
    def __init__(self, got, expected, detail=""):
        self.got = got
        self.expected = expected
        exp = f"of {expected}" if expected is not None else "(length unknown)"
        super().__init__(f"read {got} {exp} bytes, connection closed early{': ' + detail if detail else ''}")


class DeadlineExceeded(TimeoutError):
    """Per-attempt wall-clock deadline passed (slow/trickling response)."""
    def __init__(self, deadline, got=None, expected=None):
        self.deadline = deadline
        where = "" if got is None else f" after {got}{'' if expected is None else f' of {expected}'} bytes"
        super().__init__(f"deadline {deadline:g}s exceeded{where}")


def _socket_of(resp):
    raw = getattr(getattr(resp, "fp", None), "raw", None)
    return getattr(raw, "_sock", None)


def read_body(resp, chunk=CHUNK, deadline_at=None, per_read=None, deadline=None):
    """Read an http.client response to EOF in chunks; verify Content-Length; undo gzip/deflate. -> bytes.
    deadline_at (time.monotonic() value): abort with DeadlineExceeded once passed; each socket read is limited to
    min(per_read, time left) when the socket is reachable."""
    expected = None
    te = (resp.headers.get("Transfer-Encoding") or "").lower()
    cl = resp.headers.get("Content-Length")
    if cl and "chunked" not in te:
        try:
            expected = int(cl)
        except ValueError:
            expected = None
    parts, got = [], 0
    sock = _socket_of(resp) if deadline_at is not None else None
    while True:
        if deadline_at is not None:
            left = deadline_at - time.monotonic()
            if left <= 0:
                raise DeadlineExceeded(deadline if deadline is not None else 0.0, got, expected)
            if sock is not None:
                try:
                    sock.settimeout(max(0.01, min(per_read, left) if per_read else left))
                except OSError:
                    sock = None
        try:
            b = resp.read(chunk)
        except http.client.IncompleteRead as e:          # chunked encoding cut mid-stream
            got += len(e.partial or b"")
            raise IncompleteBody(got, expected, "chunked stream truncated") from e
        except TimeoutError as e:
            if deadline_at is not None and time.monotonic() >= deadline_at - 0.005:
                raise DeadlineExceeded(deadline if deadline is not None else 0.0, got, expected) from e
            raise
        if not b:
            break
        parts.append(b)
        got += len(b)
    if expected is not None and got != expected:
        raise IncompleteBody(got, expected)
    data = b"".join(parts)
    enc = (resp.headers.get("Content-Encoding") or "").lower().strip()
    if enc in ("gzip", "x-gzip"):
        try:
            data = gzip.decompress(data)
        except (EOFError, OSError, zlib.error) as e:
            raise IncompleteBody(got, expected, f"gzip stream incomplete/corrupt ({e})") from e
    elif enc == "deflate":
        try:
            data = zlib.decompress(data)
        except zlib.error:
            try:
                data = zlib.decompress(data, -zlib.MAX_WBITS)   # raw deflate (some servers)
            except zlib.error as e:
                raise IncompleteBody(got, expected, f"deflate stream incomplete/corrupt ({e})") from e
    elif enc not in ("", "identity"):
        raise ValueError(f"unsupported Content-Encoding {enc!r}")
    return data


def _host(url):
    return (urllib.parse.urlsplit(url).hostname or "").lower()


class HttpClient:
    def __init__(self, host_rps=None, default_rps=DEFAULT_RPS, timeout=DEFAULT_TIMEOUT, tries=DEFAULT_TRIES,
                 proxy=None, user_agent=DEFAULT_UA, backoff_base=1.0, circuit_fails=CIRCUIT_FAILS,
                 circuit_cooldown=CIRCUIT_COOLDOWN, sleep=time.sleep):
        self.host_rps = dict(HOST_RPS)
        self.host_rps.update(host_rps or {})
        self.default_rps = default_rps
        self.timeout = timeout
        self.tries = max(1, tries)
        self.user_agent = user_agent
        self.backoff_base = backoff_base
        self.circuit_fails = circuit_fails
        self.circuit_cooldown = circuit_cooldown
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_slot = {}       # host -> earliest monotonic time for the next request
        self._circuit = {}         # host -> {"fails", "open_until", "cooldown"}
        self.stats = {}            # host -> counters
        if proxy is None:
            proxy = os.environ.get("ACCESS_PROXY")
        self.proxy = proxy
        if proxy is None:
            handler = urllib.request.ProxyHandler()            # standard env proxies
        elif proxy == "":
            handler = urllib.request.ProxyHandler({})          # explicitly no proxy
        else:
            handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        self._opener = urllib.request.build_opener(handler)

    # ------------------------------------------------------------------ public
    def get_json(self, url, params=None, headers=None, timeout=None, tries=None, deadline=None):
        return json.loads(self.request("GET", url, params=params, headers=headers, timeout=timeout, tries=tries,
                                       deadline=deadline))

    def post_json(self, url, body=None, params=None, headers=None, timeout=None, tries=None, deadline=None):
        return json.loads(self.request("POST", url, params=params, body=body, headers=headers,
                                       timeout=timeout, tries=tries, deadline=deadline))

    def get_text(self, url, params=None, headers=None, timeout=None, tries=None, deadline=None):
        return self.request("GET", url, params=params, headers=headers, timeout=timeout, tries=tries,
                            deadline=deadline)

    def host_stats(self):
        with self._lock:
            return {h: dict(v) for h, v in self.stats.items()}

    def circuit_state(self, host):
        with self._lock:
            c = self._circuit.get(host)
            return dict(c) if c else {"fails": 0, "open_until": 0.0, "cooldown": self.circuit_cooldown}

    # ------------------------------------------------------------------ internals
    def _stat(self, host, key, n=1):
        with self._lock:
            st = self.stats.setdefault(host, {"calls": 0, "ok": 0, "http429": 0, "http4xx": 0, "http5xx": 0,
                                              "timeout": 0, "other_err": 0, "incomplete": 0, "retries": 0,
                                              "short_circuited": 0,
                                              "last_latency_ms": None})
            if key == "last_latency_ms":
                st[key] = n
            else:
                st[key] += n

    def _throttle(self, host):
        rps = self.host_rps.get(host, self.default_rps)
        gap = 1.0 / rps if rps and rps > 0 else 0.0
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot.get(host, 0.0))
            self._next_slot[host] = slot + gap
        wait = slot - time.monotonic()
        if wait > 0:
            self._sleep(wait)

    def _check_circuit(self, host):
        with self._lock:
            c = self._circuit.get(host)
            if not c or not c["open_until"]:
                return
            now = time.time()
            if now < c["open_until"]:
                raise CircuitOpen(host, c["open_until"])
            c["open_until"] = 0.0          # half-open: let one probe through; a failure re-opens immediately
            c["fails"] = self.circuit_fails - 1

    def _record(self, host, ok):
        with self._lock:
            c = self._circuit.setdefault(host, {"fails": 0, "open_until": 0.0, "cooldown": self.circuit_cooldown})
            if ok:
                c.update(fails=0, open_until=0.0, cooldown=self.circuit_cooldown)
                return
            c["fails"] += 1
            if c["fails"] >= self.circuit_fails:
                c["open_until"] = time.time() + c["cooldown"]
                c["cooldown"] = min(c["cooldown"] * 2, CIRCUIT_MAX_COOLDOWN)

    def request(self, method, url, params=None, body=None, headers=None, timeout=None, tries=None, deadline=None):
        """timeout: per socket operation (s). deadline: optional wall-clock cap per attempt (s); None = unlimited."""
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        host = _host(url)
        tries = self.tries if tries is None else max(1, tries)
        timeout = self.timeout if timeout is None else timeout
        try:
            self._check_circuit(host)
        except CircuitOpen:
            self._stat(host, "short_circuited")
            raise
        hdrs = {"User-Agent": self.user_agent, "Accept": "application/json", "Accept-Encoding": ACCEPT_ENCODING}
        hdrs.update(headers or {})
        data = None
        if body is not None:
            data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        self._stat(host, "calls")
        last_exc = None
        for attempt in range(tries):
            self._throttle(host)
            t0 = time.monotonic()
            try:
                req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
                deadline_at = (t0 + deadline) if deadline else None
                op_timeout = min(timeout, deadline) if deadline else timeout
                with self._opener.open(req, timeout=op_timeout) as r:
                    if deadline_at is not None and time.monotonic() >= deadline_at:
                        raise DeadlineExceeded(deadline)
                    text = read_body(r, deadline_at=deadline_at, per_read=timeout, deadline=deadline).decode(
                        r.headers.get_content_charset() or "utf-8", errors="replace")
                self._stat(host, "ok")
                self._stat(host, "last_latency_ms", int((time.monotonic() - t0) * 1000))
                self._record(host, True)
                return text
            except urllib.error.HTTPError as e:
                raw = ""
                try:
                    raw = read_body(e).decode(errors="replace")[:400]
                except Exception:
                    pass
                last_exc = HttpError(e.code, url, raw, getattr(e, "reason", "") or "")
                if e.code == 429:
                    self._stat(host, "http429")
                    if attempt + 1 >= tries:
                        break
                    ra = e.headers.get("Retry-After") if e.headers else None
                    try:
                        delay = min(float(ra), MAX_RETRY_AFTER) if ra else self.backoff_base * 4 * (2 ** attempt)
                    except ValueError:
                        delay = self.backoff_base * 4 * (2 ** attempt)
                    self._stat(host, "retries")
                    self._sleep(min(delay, MAX_RETRY_AFTER))
                    continue
                if 400 <= e.code < 500:
                    self._stat(host, "http4xx")
                    if e.code != 404:
                        self._record(host, False)
                    raise last_exc
                self._stat(host, "http5xx")
            except (IncompleteBody,) + TRANSIENT as e:
                self._stat(host, "incomplete")
                last_exc = TransportError(url, e, attempt + 1)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, http.client.HTTPException) as e:
                reason = getattr(e, "reason", None)
                if isinstance(reason, TRANSIENT):              # urlopen wraps errors raised while connecting
                    self._stat(host, "incomplete")
                    last_exc = TransportError(url, reason, attempt + 1)
                else:
                    timed_out = "timed out" in str(e).lower() or isinstance(e, TimeoutError)
                    self._stat(host, "timeout" if timed_out else "other_err")
                    last_exc = TransportError(url, e, attempt + 1)
            if attempt + 1 < tries:
                self._stat(host, "retries")
                self._sleep(min(self.backoff_base * (2 ** attempt), MAX_RETRY_AFTER))
        self._record(host, False)
        raise last_exc


_default = None
_default_lock = threading.Lock()


def default_client():
    global _default
    with _default_lock:
        if _default is None:
            _default = HttpClient()
        return _default


def get_json(url, **kw):
    """Module-level convenience on a shared default client (same per-host limits for all callers)."""
    return default_client().get_json(url, **kw)


def post_json(url, body=None, **kw):
    return default_client().post_json(url, body=body, **kw)
