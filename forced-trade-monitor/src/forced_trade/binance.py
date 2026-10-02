"""Pure parsers. Network stays out of tests."""

from __future__ import annotations

from forced_trade.align import HOUR_MS, oi_bar_open, start_bar_open


def parse_kline(symbol: str, row: list) -> dict:
    open_ts = int(row[0])
    return {
        "symbol": symbol,
        "bar_open_ts": start_bar_open(open_ts),
        "open": float(row[1]),
        "high": float(row[2]),
        "low": float(row[3]),
        "close": float(row[4]),
        "volume": float(row[5]),
        "quote_volume": float(row[7]),
        "taker_buy_volume": float(row[9]),
        "taker_buy_quote_volume": float(row[10]),
        "source_close_ts": int(row[6]),
        "_payload": {"symbol": symbol, "kline": row},
    }


def parse_oi(row: dict, period_ms: int = HOUR_MS) -> dict:
    api_ts = int(row["timestamp"])
    return {
        "symbol": row["symbol"],
        "bar_open_ts": oi_bar_open(api_ts, period_ms),
        "api_ts": api_ts,
        "oi_qty": float(row["sumOpenInterest"]),
        "oi_value_usdt": float(row["sumOpenInterestValue"]),
        "_payload": row,
    }


def parse_taker(symbol: str, row: dict) -> dict:
    api_ts = int(row["timestamp"])
    return {
        "symbol": symbol,
        "bar_open_ts": start_bar_open(api_ts),
        "api_ts": api_ts,
        "buy_sell_ratio": float(row["buySellRatio"]),
        "buy_vol": float(row["buyVol"]),
        "sell_vol": float(row["sellVol"]),
        "_payload": {"symbol": symbol, **row},
    }


def parse_basis(symbol: str, row: dict) -> dict:
    api_ts = int(row["timestamp"])
    return {
        "symbol": symbol,
        "pair": row.get("pair") or symbol,
        "contract_type": row.get("contractType") or "PERPETUAL",
        "bar_open_ts": start_bar_open(api_ts),
        "api_ts": api_ts,
        "index_price": float(row["indexPrice"]),
        "futures_price": float(row["futuresPrice"]),
        "basis_rate": float(row["basisRate"]),
        "basis": float(row["basis"]),
        "_payload": {"symbol": symbol, **row},
    }


def parse_funding(row: dict) -> dict:
    return {
        "symbol": row["symbol"],
        "funding_time": int(row["fundingTime"]),
        "funding_rate": float(row["fundingRate"]),
        "mark_price": float(row["markPrice"]) if row.get("markPrice") not in (None, "") else None,
        "rate_type": row.get("rateType") or "Regular",
        "_payload": row,
    }


def parse_mark(row: dict) -> dict:
    """premiumIndex is an instant snapshot; observed_at is the payload time."""
    return {
        "symbol": row["symbol"],
        "observed_at": int(row["time"]),
        "mark_price": float(row["markPrice"]),
        "index_price": float(row["indexPrice"]),
        "last_funding_rate": float(row["lastFundingRate"]) if row.get("lastFundingRate") not in (None, "") else None,
        "next_funding_time": int(row["nextFundingTime"]) if row.get("nextFundingTime") else None,
        "_payload": row,
    }


def parse_funding_info(row: dict, observed_at: int) -> dict:
    return {
        "symbol": row["symbol"],
        "observed_at": int(observed_at),
        "funding_interval_hours": float(row["fundingIntervalHours"]),
        "cap": float(row["adjustedFundingRateCap"]) if row.get("adjustedFundingRateCap") else None,
        "floor": float(row["adjustedFundingRateFloor"]) if row.get("adjustedFundingRateFloor") else None,
        "present_in_payload": 1,
        "_payload": row,
    }


def default_funding_info(symbol: str, observed_at: int, hours: float = 8) -> dict:
    return {
        "symbol": symbol,
        "observed_at": int(observed_at),
        "funding_interval_hours": hours,
        "cap": None,
        "floor": None,
        "present_in_payload": 0,
        "_payload": {"symbol": symbol, "default": hours},
    }
