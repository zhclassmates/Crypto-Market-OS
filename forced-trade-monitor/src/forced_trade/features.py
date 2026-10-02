"""Assemble one feature row. Official taker is not replaced by kline taker."""

from __future__ import annotations

from forced_trade.align import HOUR_MS, is_hour_aligned
from forced_trade.metrics import (
    DAY_MS,
    _chg,
    _ret,
    funding_8h_equiv,
    imbalance,
    percentile,
    resolve_interval,
    trailing,
    visible_funding,
    zscore,
)
from forced_trade.quality import divergence_flag
from forced_trade.states import flow_aligned


def _window_imbalance(taker: dict[int, tuple[float, float]], ts: int, hours: int):
    buy = sell = 0.0
    for step in range(hours):
        point = ts - step * HOUR_MS
        if point not in taker:
            return None
        b, s = taker[point]
        buy += b
        sell += s
    return imbalance(buy, sell)


def build_feature(
    symbol: str,
    bar_open_ts: int,
    closes: dict[int, float],
    oi: dict[int, float],
    taker: dict[int, tuple[float, float]],
    kline_taker: dict[int, tuple[float, float]],
    basis_bps: dict[int, float],
    mark_index_bps: dict[int, float],
    quote_volume: dict[int, float],
    funding_events: list[dict],
    funding_snapshots: list[dict],
    btc_closes: dict[int, float],
    *,
    z_window: int = 168,
    z_min: int = 24,
    funding_days: int = 30,
    divergence_bps: float = 5.0,
    default_interval: float = 8,
) -> dict:
    flags = []
    if not is_hour_aligned(bar_open_ts):
        flags.append("ts_unaligned")

    ret_1h = _ret(closes, bar_open_ts, 1)
    ret_4h = _ret(closes, bar_open_ts, 4)
    ret_24h = _ret(closes, bar_open_ts, 24)
    btc_1 = _ret(btc_closes, bar_open_ts, 1)
    btc_4 = _ret(btc_closes, bar_open_ts, 4)

    oi_chg_1 = _chg(oi, bar_open_ts, 1)
    oi_chg_4 = _chg(oi, bar_open_ts, 4)
    oi_chg_24 = _chg(oi, bar_open_ts, 24)
    oi_z = zscore(oi.get(bar_open_ts), trailing(oi, bar_open_ts, z_window), z_min)
    chg_series = {
        ts: _chg(oi, ts, 1) for ts in oi if _chg(oi, ts, 1) is not None
    }
    oi_chg_z = zscore(oi_chg_1, trailing(chg_series, bar_open_ts, z_window), z_min)
    ret_series = {
        ts: _ret(closes, ts, 1) for ts in closes if _ret(closes, ts, 1) is not None
    }
    ret_z = zscore(ret_1h, trailing(ret_series, bar_open_ts, z_window), z_min)

    event = visible_funding(funding_events, bar_open_ts)
    equiv = pct = interval = None
    interval_source = None
    rate_type = None
    if event is not None:
        rate_type = event.get("rate_type") or "Regular"
        interval, interval_source = resolve_interval(
            funding_snapshots, event["funding_time"], default_interval
        )
        equiv = funding_8h_equiv(event["funding_rate"], interval)
        if interval_source == "default":
            flags.append("funding_interval_default")
        if rate_type == "Regular":
            cutoff = event["funding_time"] - funding_days * DAY_MS
            sample = []
            for item in funding_events:
                if item.get("rate_type", "Regular") != "Regular":
                    continue
                if not (cutoff < item["funding_time"] <= event["funding_time"]):
                    continue
                hours, _ = resolve_interval(
                    funding_snapshots, item["funding_time"], default_interval
                )
                sample.append(funding_8h_equiv(item["funding_rate"], hours))
            pct = percentile(equiv, sample)
        else:
            flags.append("funding_special")

    taker_1 = _window_imbalance(taker, bar_open_ts, 1)
    taker_4 = _window_imbalance(taker, bar_open_ts, 4)
    if taker_1 is None:
        flags.append("taker_missing")
    k_buy, k_sell = kline_taker.get(bar_open_ts, (None, None))
    k_imb = imbalance(k_buy, k_sell)

    official = basis_bps.get(bar_open_ts)
    mark_bps = mark_index_bps.get(bar_open_ts)
    div = None
    if official is not None and mark_bps is not None:
        div = official - mark_bps
    div_flag = divergence_flag(official, mark_bps, divergence_bps)
    if div_flag:
        flags.append(div_flag)
    basis_z = zscore(official, trailing(basis_bps, bar_open_ts, z_window), z_min)
    vol_pct = percentile(
        quote_volume.get(bar_open_ts),
        trailing(quote_volume, bar_open_ts, funding_days * 24),
    )
    aligned = flow_aligned(ret_1h, taker_1)

    return {
        "symbol": symbol,
        "bar_open_ts": bar_open_ts,
        "ret_1h": ret_1h,
        "ret_4h": ret_4h,
        "ret_24h": ret_24h,
        "oi_qty_chg_1h": oi_chg_1,
        "oi_qty_chg_4h": oi_chg_4,
        "oi_qty_chg_24h": oi_chg_24,
        "oi_z_7d": oi_z,
        "oi_chg_1h_z": oi_chg_z,
        "abs_ret_1h_z": None if ret_z is None else abs(ret_z),
        "funding_8h_equiv": equiv,
        "funding_pct_30d": pct,
        "funding_interval_hours": interval,
        "interval_source": interval_source,
        "funding_rate_type": rate_type,
        "taker_imbalance_1h": taker_1,
        "taker_imbalance_4h": taker_4,
        "kline_taker_imbalance_1h": k_imb,
        "basis_bps": official,
        "mark_index_basis_bps": mark_bps,
        "basis_divergence_bps": div,
        "basis_z_7d": basis_z,
        "btc_ret_1h": btc_1,
        "btc_ret_4h": btc_4,
        "ret_1h_vs_btc": None if ret_1h is None or btc_1 is None else ret_1h - btc_1,
        "ret_4h_vs_btc": None if ret_4h is None or btc_4 is None else ret_4h - btc_4,
        "volume_pct_30d": vol_pct,
        "flow_aligned_with_price": aligned,
        "data_quality_flag": ",".join(flags) if flags else None,
    }
