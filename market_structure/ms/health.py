"""健康检查：最近 N 小时数据是否齐全。第一行是结论（OK / WARN），其余是明细。"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Config, floor_ts, now_ms

MIN = 60_000


def report(cfg: Config, con: sqlite3.Connection, hours: float = 24) -> str:
    # 只统计"按计划应该已经拉到"的 bar：扣掉收盘后的轮询延迟和 1 分钟余量
    end = floor_ts(now_ms() - int(cfg.poll_delay_sec * 1000) - MIN, cfg.interval_ms)
    start = end - int(hours * 3_600_000)
    iv, step = cfg.bar_interval, cfg.interval_ms
    exp_bars = (end - start) // step
    exp_min = (end - start) // MIN
    warns: list[str] = []
    lines: list[str] = []

    def one(sql, *p):
        return con.execute(sql, p).fetchone()[0] or 0

    cov = {}
    for venue in (["binance", "bybit"] if cfg.bybit_enabled else ["binance"]):
        n = one("SELECT COUNT(*) FROM ws_heartbeat WHERE venue=? AND minute_ts>=? AND minute_ts<?",
                venue, start, end)
        cov[venue] = n / exp_min if exp_min else 0
        if cov[venue] < 0.95:
            warns.append(f"{venue} 强平WS覆盖 {cov[venue]:.0%}")
    lines.append("强平WS覆盖率: " + "  ".join(f"{v} {c:.1%}" for v, c in cov.items()))

    lines.append(f"{'symbol':<10}{'perp':>6}{'spot':>6}{'oi5m':>6}{'byOI':>6}{'fund':>6}"
                 f"{'liqB':>6}{'liqY':>6}  可见强平(多/空, USD)")
    for sc in cfg.symbols:
        s = sc.symbol
        perp = one("SELECT COUNT(*) FROM bars WHERE venue='binance' AND market='perp' AND symbol=? "
                   "AND interval=? AND ts>=? AND ts<?", s, iv, start, end)
        spot = one("SELECT COUNT(*) FROM bars WHERE venue='binance' AND market='spot' AND symbol=? "
                   "AND interval=? AND ts>=? AND ts<?", s, iv, start, end) if sc.spot else None
        oi5 = one("SELECT COUNT(*) FROM oi WHERE venue='binance' AND source='hist5m' AND symbol=? "
                  "AND ts>=? AND ts<?", s, start, end)
        byoi = one("SELECT COUNT(*) FROM oi WHERE venue='bybit' AND source LIKE 'hist%' AND symbol=? "
                   "AND ts>=? AND ts<?", s, start, end)
        fund = one("SELECT COUNT(*) FROM funding_live WHERE venue='binance' AND symbol=? AND ts>=? AND ts<?",
                   s, start, end)
        lq = {}
        for v in ("binance", "bybit"):
            lq[v] = con.execute(
                "SELECT COUNT(*), SUM(CASE WHEN side='long_liq' THEN notional END), "
                "SUM(CASE WHEN side='short_liq' THEN notional END) FROM liq_prints "
                "WHERE venue=? AND symbol=? AND ts>=? AND ts<?", (v, s, start, end)).fetchone()
        n_b, lb, sb = lq["binance"]
        n_y = lq["bybit"][0]
        lines.append(f"{s:<10}{perp:>6}{'-' if spot is None else spot:>6}{oi5:>6}{byoi:>6}{fund:>6}"
                     f"{n_b or 0:>6}{n_y or 0:>6}  {(lb or 0)/1e6:.2f}M/{(sb or 0)/1e6:.2f}M")
        if perp < exp_bars:
            warns.append(f"{s} perp bar 缺 {exp_bars - perp}")
        if sc.spot and spot < exp_bars:
            warns.append(f"{s} spot bar 缺 {exp_bars - spot}")
        exp_oi = (end - start) // 300_000
        if oi5 < exp_oi * 0.95:
            warns.append(f"{s} OI 5m 只有 {oi5}/{exp_oi}")

    fails = con.execute("SELECT job, COUNT(*) FROM poll_log WHERE ok=0 AND ts>=? AND job NOT LIKE 'ws_reconnect%' "
                        "GROUP BY job ORDER BY 2 DESC LIMIT 5", (start,)).fetchall()
    recon = con.execute("SELECT job, COUNT(*) FROM poll_log WHERE job LIKE 'ws_reconnect%' AND ts>=? "
                        "GROUP BY job", (start,)).fetchall()
    if fails:
        warns.append("轮询失败: " + ", ".join(f"{j}×{n}" for j, n in fails))
    if recon:
        lines.append("WS 重连: " + ", ".join(f"{j.split('.')[-1]}×{n}" for j, n in recon))

    tz = ZoneInfo(cfg.tz)
    span = (f"{datetime.fromtimestamp(start/1000, tz):%m-%d %H:%M} → "
            f"{datetime.fromtimestamp(end/1000, tz):%m-%d %H:%M} ({cfg.tz})，期望每品种 {exp_bars} 根 {iv} bar")
    head = "OK" if not warns else "WARN: " + "；".join(warns)
    return "\n".join([head, span, *lines])
