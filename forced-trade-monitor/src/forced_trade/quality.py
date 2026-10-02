"""Per-source health. A live page is not a live series."""

from __future__ import annotations

import time


def health_row(
    source: str,
    *,
    symbol: str | None = None,
    expected_ts: int | None = None,
    actual_ts: int | None = None,
    success: bool,
    http_status: int | None = None,
    latency_ms: float | None = None,
    rows_expected: int | None = None,
    rows_got: int | None = None,
    null_rate: float | None = None,
    ts_semantics: str | None = None,
    error: str | None = None,
    now_ms: int | None = None,
) -> dict:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    age = None
    if actual_ts is not None:
        age = (now - actual_ts) / 1000
    return {
        "ts": now,
        "source": source,
        "symbol": symbol,
        "expected_ts": expected_ts,
        "actual_ts": actual_ts,
        "age_sec": age,
        "success": int(success),
        "http_status": http_status,
        "latency_ms": latency_ms,
        "rows_expected": rows_expected,
        "rows_got": rows_got,
        "null_rate": null_rate,
        "ts_semantics": ts_semantics,
        "error": error,
    }


def divergence_flag(official_bps: float | None, mark_bps: float | None, limit: float) -> str | None:
    if official_bps is None or mark_bps is None:
        return None
    if abs(official_bps - mark_bps) >= limit:
        return "basis_divergence"
    return None
