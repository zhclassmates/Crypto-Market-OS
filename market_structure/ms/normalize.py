"""交易所原始返回 → 统一行格式。纯函数，便于测试。

强平方向统一：
- Binance forceOrder: o.S 是交易所挂出的强平单方向。SELL = 多头被强平 → long_liq；BUY → short_liq
- Bybit allLiquidation: S 是被强平仓位方向。Buy = 多头被强平 → long_liq；Sell → short_liq
"""
from __future__ import annotations


def _f(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# ---------- K 线（Binance spot / USD-M 同格式） ----------
# [openTime, o, h, l, c, volume, closeTime, quoteVolume, trades, takerBuyBase, takerBuyQuote, ignore]
def binance_klines(raw: list, venue: str, market: str, symbol: str, interval: str, now: int) -> list[tuple]:
    rows = []
    for k in raw:
        if int(k[6]) >= now:          # 未收盘的 bar 不入库
            continue
        vq, tbq = _f(k[7]), _f(k[10])
        rows.append((venue, market, symbol, interval, int(k[0]),
                     _f(k[1]), _f(k[2]), _f(k[3]), _f(k[4]),
                     _f(k[5]), vq, tbq, 2 * tbq - vq, int(k[8])))
    return rows


# ---------- Binance OI ----------
def binance_oi_hist(raw: list, symbol: str) -> list[tuple]:
    return [("binance", symbol, "hist5m", int(r["timestamp"]),
             _f(r["sumOpenInterest"]), _f(r["sumOpenInterestValue"])) for r in raw]


def binance_oi_snapshot(raw: dict, symbol: str, mark: float | None) -> tuple:
    base = _f(raw["openInterest"])
    return ("binance", symbol, "snapshot", int(raw["time"]), base, base * mark if mark else None)


# ---------- Binance funding ----------
def binance_premium(raw: dict, symbol: str) -> tuple:
    return ("binance", symbol, int(raw["time"]), _f(raw["markPrice"]), _f(raw["indexPrice"]),
            _f(raw["lastFundingRate"]), int(raw.get("nextFundingTime") or 0))


def binance_funding_hist(raw: list, symbol: str) -> list[tuple]:
    return [("binance", symbol, int(r["fundingTime"]), _f(r["fundingRate"])) for r in raw]


# ---------- Binance 强平 ----------
def binance_force_order(msg: dict) -> tuple | None:
    if "data" in msg:                  # combined stream 包了一层
        msg = msg["data"]
    if not isinstance(msg, dict) or msg.get("e") != "forceOrder":
        return None
    o = msg["o"]
    raw_side = o["S"]
    side = "long_liq" if raw_side == "SELL" else "short_liq"
    qty = _f(o.get("z")) or _f(o.get("q"))
    price = _f(o.get("ap")) or _f(o.get("p"))
    return ("binance", o["s"], int(o["T"]), side, price, qty, price * qty, raw_side)


# ---------- Bybit ----------
def bybit_oi(raw: dict, symbol: str, source: str) -> list[tuple]:
    lst = (raw.get("result") or {}).get("list") or []
    return [("bybit", symbol, source, int(r["timestamp"]), _f(r["openInterest"]), None) for r in lst]


def bybit_ticker(raw: dict, symbol: str, ts: int) -> tuple[tuple, tuple] | None:
    lst = (raw.get("result") or {}).get("list") or []
    if not lst:
        return None
    t = lst[0]
    mark = _f(t.get("markPrice"))
    oi_base = _f(t.get("openInterest"))
    funding = ("bybit", symbol, ts, mark, _f(t.get("indexPrice")), _f(t.get("fundingRate")),
               int(t.get("nextFundingTime") or 0))
    oi = ("bybit", symbol, "snapshot", ts, oi_base, oi_base * mark if mark else None)
    return funding, oi


def bybit_all_liq(msg: dict) -> list[tuple]:
    if not str(msg.get("topic", "")).startswith("allLiquidation."):
        return []
    out = []
    for d in msg.get("data") or []:
        raw_side = d["S"]
        side = "long_liq" if raw_side == "Buy" else "short_liq"
        qty, price = _f(d["v"]), _f(d["p"])
        out.append(("bybit", d["s"], int(d["T"]), side, price, qty, price * qty, raw_side))
    return out
