"""Feature math. Missing bars stay missing; they are not filled."""

from __future__ import annotations

import statistics
from typing import Iterable

from forced_trade.align import HOUR_MS, visible_at

DAY_MS = 24 * HOUR_MS


def _ret(series: dict[int, float], ts: int, hours: int) -> float | None:
    prev = ts - hours * HOUR_MS
    if ts not in series or prev not in series or series[prev] == 0:
        return None
    return series[ts] / series[prev] - 1


def _chg(series: dict[int, float], ts: int, hours: int) -> float | None:
    prev = ts - hours * HOUR_MS
    if ts not in series or prev not in series or series[prev] == 0:
        return None
    return series[ts] / series[prev] - 1


def zscore(value: float | None, window: Iterable[float], min_obs: int) -> float | None:
    sample = [x for x in window if x is not None]
    if value is None or len(sample) < min_obs:
        return None
    if len(sample) < 2:
        return None
    mu = statistics.fmean(sample)
    sigma = statistics.pstdev(sample)
    if sigma == 0:
        return 0.0
    return (value - mu) / sigma


def percentile(value: float | None, sample: Iterable[float]) -> float | None:
    xs = [x for x in sample if x is not None]
    if value is None or not xs:
        return None
    less = sum(1 for x in xs if x < value)
    equal = sum(1 for x in xs if x == value)
    return (less + 0.5 * equal) / len(xs)


def imbalance(buy: float | None, sell: float | None) -> float | None:
    if buy is None or sell is None:
        return None
    den = buy + sell
    if den == 0:
        return None
    return (buy - sell) / den


def funding_8h_equiv(rate: float, interval_hours: float) -> float:
    if interval_hours <= 0:
        raise ValueError("funding interval must be positive")
    return rate * 8 / interval_hours


def resolve_interval(
    snapshots: list[dict], funding_time: int, default_hours: float = 8
) -> tuple[float, str]:
    """Use the latest snapshot at or before the event. Never a future snapshot."""
    prior = [s for s in snapshots if s["observed_at"] <= funding_time]
    if not prior:
        return default_hours, "default"
    chosen = max(prior, key=lambda s: s["observed_at"])
    hours = chosen.get("funding_interval_hours")
    if hours is None:
        return default_hours, "default"
    source = "snapshot" if chosen.get("present_in_payload", 1) else "default"
    return float(hours), source


def visible_funding(events: list[dict], bar_open_ts: int) -> dict | None:
    visible = [e for e in events if visible_at(e["funding_time"], bar_open_ts)]
    if not visible:
        return None
    return max(visible, key=lambda e: e["funding_time"])


def trailing(series: dict[int, float], ts: int, hours: int) -> list[float]:
    out = []
    for step in range(hours):
        point = ts - step * HOUR_MS
        if point in series:
            out.append(series[point])
    return out
