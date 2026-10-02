"""HTTP boundary. Only this module talks to the network; parsers stay pure."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, NamedTuple


class HttpResponse(NamedTuple):
    status: int | None
    latency_ms: float
    payload: Any
    error: str | None


Transport = Callable[[str, dict], HttpResponse]


def _ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 2)


def urllib_transport(url: str, params: dict, timeout: float = 10.0) -> HttpResponse:
    query = urllib.parse.urlencode(params)
    full = f"{url}?{query}" if query else url
    started = time.monotonic()
    try:
        with urllib.request.urlopen(full, timeout=timeout) as resp:
            body = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        # 429 and 5xx land here; the health row keeps the status code.
        return HttpResponse(exc.code, _ms(started), None, f"http_{exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return HttpResponse(None, _ms(started), None, f"transport:{exc}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return HttpResponse(status, _ms(started), None, f"bad_json:{exc}")
    return HttpResponse(status, _ms(started), payload, None)


class FixtureTransport:
    """Replay recorded responses. An entry matches when the path equals and
    the entry's params are a subset of the request params. Keeps tests
    offline; every call is logged in .calls."""

    def __init__(self, entries: list[dict]):
        self.entries = entries
        self.calls: list[tuple[str, dict]] = []

    @classmethod
    def from_file(cls, path: str | Path) -> "FixtureTransport":
        return cls(json.loads(Path(path).read_text()))

    def __call__(self, url: str, params: dict) -> HttpResponse:
        path = urllib.parse.urlparse(url).path
        self.calls.append((path, dict(params)))
        got = {k: str(v) for k, v in params.items()}
        for entry in self.entries:
            if entry["path"] != path:
                continue
            want = {k: str(v) for k, v in entry.get("params", {}).items()}
            if all(got.get(k) == v for k, v in want.items()):
                status = entry.get("status", 200)
                error = None if status == 200 else f"http_{status}"
                return HttpResponse(status, 0.0, entry.get("body"), error)
        return HttpResponse(None, 0.0, None, f"no_fixture:{path}:{got}")


class BinanceClient:
    """USDⓈ-M futures endpoints used by the hourly pipeline. ADL is not called."""

    def __init__(self, base_url: str, transport: Transport = urllib_transport):
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    def _get(self, path: str, params: dict | None = None) -> HttpResponse:
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        return self.transport(f"{self.base_url}{path}", clean)

    def exchange_info(self) -> HttpResponse:
        return self._get("/fapi/v1/exchangeInfo")

    def ticker_24hr(self) -> HttpResponse:
        return self._get("/fapi/v1/ticker/24hr")

    def klines(self, symbol: str, start_time: int, end_time: int, interval: str = "1h", limit: int = 1) -> HttpResponse:
        return self._get("/fapi/v1/klines", {
            "symbol": symbol, "interval": interval,
            "startTime": int(start_time), "endTime": int(end_time), "limit": limit,
        })

    def open_interest_hist(self, symbol: str, start_time: int, end_time: int, period: str = "1h", limit: int = 5) -> HttpResponse:
        return self._get("/futures/data/openInterestHist", {
            "symbol": symbol, "period": period,
            "startTime": int(start_time), "endTime": int(end_time), "limit": limit,
        })

    def taker_ratio(self, symbol: str, start_time: int, end_time: int | None, period: str = "1h", limit: int = 5) -> HttpResponse:
        return self._get("/futures/data/takerlongshortRatio", {
            "symbol": symbol, "period": period,
            "startTime": int(start_time), **({"endTime": int(end_time)} if end_time is not None else {}), "limit": limit,
        })

    def basis(self, pair: str, start_time: int, end_time: int, contract_type: str = "PERPETUAL", period: str = "1h", limit: int = 5) -> HttpResponse:
        # pair + contractType=PERPETUAL, never symbol=
        return self._get("/futures/data/basis", {
            "pair": pair, "contractType": contract_type, "period": period,
            "startTime": int(start_time), "endTime": int(end_time), "limit": limit,
        })

    def funding_rate(self, symbol: str, start_time: int, end_time: int, limit: int = 1000) -> HttpResponse:
        return self._get("/fapi/v1/fundingRate", {
            "symbol": symbol,
            "startTime": int(start_time), "endTime": int(end_time), "limit": limit,
        })

    def funding_info(self) -> HttpResponse:
        return self._get("/fapi/v1/fundingInfo")

    def premium_index(self, symbol: str) -> HttpResponse:
        return self._get("/fapi/v1/premiumIndex", {"symbol": symbol})
