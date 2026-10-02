"""Hourly ingest pipeline: fetch, parse, upsert, health. One source failing never stops the others."""

from __future__ import annotations

import sqlite3
import time
from typing import Any, Callable, NamedTuple

from forced_trade.align import HOUR_MS
from forced_trade.binance import (
    default_funding_info,
    parse_basis,
    parse_funding,
    parse_funding_info,
    parse_kline,
    parse_mark,
    parse_oi,
    parse_taker,
)
from forced_trade.db import upsert_fact
from forced_trade.http import BinanceClient, HttpResponse
from forced_trade.quality import health_row

_HEALTH_COLS = (
    "ts", "source", "symbol", "expected_ts", "actual_ts", "age_sec",
    "success", "http_status", "latency_ms", "rows_expected", "rows_got",
    "null_rate", "ts_semantics", "error",
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _to_list(payload: Any) -> list:
    # fundingInfo may answer a single dict or a list; both are accepted here.
    if payload is None:
        return []
    if isinstance(payload, dict):
        return [payload]
    return list(payload)


class _Stat:
    def __init__(self, expected: int | None):
        self.expected = expected
        self.got = 0
        self.nulls = 0
        self.errors: list[str] = []
        self.statuses: list[int | None] = []
        self.latencies: list[float] = []
        self.actual_ts: int | None = None

    def note(self, resp: HttpResponse) -> None:
        self.statuses.append(resp.status)
        self.latencies.append(resp.latency_ms)
        if resp.error:
            self.errors.append(resp.error)


class IngestHour:
    """One hour of raw ingest for one bar_open_ts over the given symbols."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        client: BinanceClient,
        bar_open_ts: int,
        symbols: list[str],
        settings: dict,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.conn = conn
        self.client = client
        self.bar_open_ts = bar_open_ts
        self.bar_close = bar_open_ts + HOUR_MS
        self.symbols = symbols
        self.settings = settings
        # OI/taker share a ~1000 calls / 5 min budget; stay serial and polite.
        self.sleep_s = float(settings.get("request_sleep_ms", 200)) / 1000
        self.sleep = sleep
        self.health_rows: list[dict] = []

    # -- health ---------------------------------------------------------

    def _flush(self, source: str, stat: _Stat, ts_semantics: str, expected_ts: int | None, require_rows: bool = True) -> None:
        bad = [s for s in stat.statuses if s and s != 200]
        status = bad[0] if bad else (200 if stat.statuses else None)
        latency = round(sum(stat.latencies) / len(stat.latencies), 2) if stat.latencies else None
        null_rate = (stat.nulls / stat.expected) if stat.expected else None
        error = ";".join(dict.fromkeys(stat.errors))[:500] or None
        # Per-symbol sources returning 0 rows (endpoint lag/empty) are not "ok":
        # a live HTTP page is not a live series. funding_info writes default
        # rows for missing payload entries, so it opts out of this rule.
        success = not stat.errors
        if require_rows and stat.expected and stat.got == 0:
            success = False
            error = error or "rows_got=0 (source lag or empty)"
        self.health_rows.append(health_row(
            source,
            expected_ts=expected_ts,
            actual_ts=stat.actual_ts,
            success=success,
            http_status=status,
            latency_ms=latency,
            rows_expected=stat.expected,
            rows_got=stat.got,
            null_rate=null_rate,
            ts_semantics=ts_semantics,
            error=error,
        ))

    def _write_health(self) -> None:
        if not self.health_rows:
            return
        q = "INSERT INTO data_health ({0}) VALUES ({1})".format(
            ",".join(_HEALTH_COLS), ",".join("?" for _ in _HEALTH_COLS)
        )
        for row in self.health_rows:
            self.conn.execute(q, [row.get(c) for c in _HEALTH_COLS])

    # -- per-source fetchers --------------------------------------------

    def _klines(self) -> None:
        stat = _Stat(len(self.symbols))
        for sym in self.symbols:
            resp = self.client.klines(sym, self.bar_open_ts, self.bar_close - 1, limit=1)
            stat.note(resp)
            if resp.error:
                continue
            for item in _to_list(resp.payload):
                parsed = parse_kline(sym, item)
                if parsed["bar_open_ts"] != self.bar_open_ts:
                    continue
                stat.actual_ts = parsed["source_close_ts"]
                body = parsed.pop("_payload")
                upsert_fact(self.conn, "raw_klines_1h", ["symbol", "bar_open_ts"], parsed, body)
                stat.got += 1
        self._flush("klines", stat, "period_start", self.bar_close)

    def _oi(self) -> None:
        stat = _Stat(len(self.symbols))
        for sym in self.symbols:
            self.sleep(self.sleep_s)
            # OI timestamps are period END: the point for this bar carries timestamp == bar_close.
            resp = self.client.open_interest_hist(sym, self.bar_close, self.bar_close, limit=1)
            stat.note(resp)
            if resp.error:
                continue
            for item in _to_list(resp.payload):
                parsed = parse_oi(item)
                if parsed["bar_open_ts"] != self.bar_open_ts:
                    continue
                stat.actual_ts = parsed["api_ts"]
                body = parsed.pop("_payload")
                upsert_fact(self.conn, "raw_oi_1h", ["symbol", "bar_open_ts"], parsed, body)
                stat.got += 1
                if parsed["oi_qty"] is None:
                    stat.nulls += 1
        self._flush("oi", stat, "period_end", self.bar_close)

    def _taker(self) -> None:
        stat = _Stat(len(self.symbols))
        for sym in self.symbols:
            self.sleep(self.sleep_s)
            # NOTE: takerlongshortRatio misbehaves when endTime is supplied
            # (it returns a point before the window). startTime-only returns
            # the latest points; we keep only the exact target bar.
            resp = self.client.taker_ratio(sym, self.bar_open_ts, None, limit=5)
            stat.note(resp)
            if resp.error:
                continue
            for item in _to_list(resp.payload):
                parsed = parse_taker(sym, item)
                if parsed["bar_open_ts"] != self.bar_open_ts:
                    continue
                stat.actual_ts = parsed["api_ts"]
                body = parsed.pop("_payload")
                upsert_fact(self.conn, "raw_taker_1h", ["symbol", "bar_open_ts"], parsed, body)
                stat.got += 1
                if parsed["buy_vol"] is None or parsed["sell_vol"] is None:
                    stat.nulls += 1
        self._flush("taker", stat, "period_start", self.bar_close)

    def _basis(self) -> None:
        stat = _Stat(len(self.symbols))
        for sym in self.symbols:
            self.sleep(self.sleep_s)
            # pair + contractType=PERPETUAL, per contract.
            resp = self.client.basis(sym, self.bar_open_ts, self.bar_close - 1, limit=1)
            stat.note(resp)
            if resp.error:
                continue
            for item in _to_list(resp.payload):
                parsed = parse_basis(sym, item)
                if parsed["bar_open_ts"] != self.bar_open_ts:
                    continue
                stat.actual_ts = parsed["api_ts"]
                body = parsed.pop("_payload")
                upsert_fact(self.conn, "raw_basis_1h", ["symbol", "bar_open_ts"], parsed, body)
                stat.got += 1
                if parsed["basis_rate"] is None:
                    stat.nulls += 1
        self._flush("basis", stat, "period_start", self.bar_close)

    def _funding(self) -> None:
        stat = _Stat(None)
        start = self.bar_open_ts - int(self.settings.get("funding_lookback_days", 30)) * 24 * HOUR_MS
        for sym in self.symbols:
            resp = self.client.funding_rate(sym, start, self.bar_close, limit=1000)
            stat.note(resp)
            if resp.error:
                continue
            for item in _to_list(resp.payload):
                parsed = parse_funding(item)
                stat.actual_ts = parsed["funding_time"]
                body = parsed.pop("_payload")
                upsert_fact(
                    self.conn, "raw_funding", ["symbol", "funding_time"], parsed, body,
                    event_ts_col="funding_time",
                )
                stat.got += 1
        self._flush("funding", stat, "event", self.bar_close)

    def _funding_info(self) -> None:
        now = _now_ms()
        stat = _Stat(len(self.symbols))
        resp = self.client.funding_info()
        stat.note(resp)
        if resp.error:
            self._flush("funding_info", stat, "snapshot", now)
            return
        items = _to_list(resp.payload)
        seen = set()
        for item in items:
            parsed = parse_funding_info(item, observed_at=now)
            seen.add(parsed["symbol"])
            body = parsed.pop("_payload")
            upsert_fact(
                self.conn, "funding_info_snapshot", ["symbol", "observed_at"], parsed, body,
                track_ingested=False,
            )
            if parsed["symbol"] in self.symbols:
                stat.got += 1
        for sym in self.symbols:
            if sym in seen:
                continue
            parsed = default_funding_info(
                sym, now, hours=float(self.settings.get("default_funding_interval_hours", 8))
            )
            body = parsed.pop("_payload")
            upsert_fact(
                self.conn, "funding_info_snapshot", ["symbol", "observed_at"], parsed, body,
                track_ingested=False,
            )
        stat.actual_ts = now
        self._flush("funding_info", stat, "snapshot", now, require_rows=False)

    def _mark(self) -> None:
        stat = _Stat(len(self.symbols))
        for sym in self.symbols:
            resp = self.client.premium_index(sym)
            stat.note(resp)
            if resp.error or not isinstance(resp.payload, dict):
                continue
            parsed = parse_mark(resp.payload)
            stat.actual_ts = parsed["observed_at"]
            body = parsed.pop("_payload")
            upsert_fact(
                self.conn, "raw_mark", ["symbol", "observed_at"], parsed, body,
                event_ts_col="observed_at",
            )
            stat.got += 1
            if parsed["mark_price"] is None or parsed["index_price"] is None:
                stat.nulls += 1
        self._flush("mark", stat, "snapshot", self.bar_close)

    # -- entry -----------------------------------------------------------

    def run(self) -> None:
        for step in (
            self._klines, self._oi, self._taker, self._basis,
            self._funding, self._funding_info, self._mark,
        ):
            try:
                step()
            except Exception as exc:  # never let one source kill the hour
                self.health_rows.append(health_row(
                    step.__name__.lstrip("_"), success=False, error=f"crash:{exc}",
                    expected_ts=self.bar_close,
                ))
        self._write_health()
