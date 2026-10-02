"""Timestamp contract. Raw stays factual; this only names the bar."""

HOUR_MS = 3_600_000

OI_TS = "period_end"
START_TS = "period_start"
EVENT_TS = "event"


def is_hour_aligned(ts: int) -> bool:
    return int(ts) % HOUR_MS == 0


def oi_bar_open(api_ts: int, period_ms: int = HOUR_MS) -> int:
    """OI timestamp is the end of the period."""
    return int(api_ts) - int(period_ms)


def start_bar_open(api_ts: int) -> int:
    """basis, taker, and kline open time are the start of the period."""
    return int(api_ts)


def bar_close(bar_open_ts: int, period_ms: int = HOUR_MS) -> int:
    return int(bar_open_ts) + int(period_ms)


def visible_at(event_ts: int, bar_open_ts: int, period_ms: int = HOUR_MS) -> bool:
    """Event is visible to the decision taken after this bar closes."""
    return int(event_ts) <= bar_close(bar_open_ts, period_ms)
