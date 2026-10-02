"""Forward returns for every in-universe bar. Closed horizons only."""

from __future__ import annotations

from forced_trade.align import HOUR_MS

HORIZONS = (1, 4, 24, 72)
VS_BTC = (4, 24, 72)


def forward_return(closes: dict[int, float], bar_open_ts: int, hours: int) -> float | None:
    nxt = bar_open_ts + hours * HOUR_MS
    if bar_open_ts not in closes or nxt not in closes or closes[bar_open_ts] == 0:
        return None
    return closes[nxt] / closes[bar_open_ts] - 1


def fill_row(
    symbol: str,
    bar_open_ts: int,
    closes: dict[str, dict[int, float]],
    universe: set[tuple[str, int]],
    btc_symbol: str = "BTCUSDT",
    now_close_floor: int | None = None,
) -> dict | None:
    """now_close_floor is the latest bar_open whose close is already known."""
    if (symbol, bar_open_ts) not in universe:
        return None
    if symbol not in closes:
        return None
    row = {
        "symbol": symbol,
        "bar_open_ts": bar_open_ts,
        "in_universe": 1,
        "price_def": "kline_close",
    }
    wrote = False
    for hours in HORIZONS:
        target = bar_open_ts + hours * HOUR_MS
        if now_close_floor is not None and target > now_close_floor:
            row[f"ret_fwd_{hours}h"] = None
            continue
        value = forward_return(closes[symbol], bar_open_ts, hours)
        row[f"ret_fwd_{hours}h"] = value
        wrote = wrote or value is not None
    btc = closes.get(btc_symbol, {})
    for hours in VS_BTC:
        target = bar_open_ts + hours * HOUR_MS
        key = f"ret_fwd_{hours}h_vs_btc"
        if now_close_floor is not None and target > now_close_floor:
            row[key] = None
            continue
        a = row.get(f"ret_fwd_{hours}h")
        b = forward_return(btc, bar_open_ts, hours)
        row[key] = None if a is None or b is None else a - b
        wrote = wrote or row[key] is not None
    if not wrote:
        return None
    return row
