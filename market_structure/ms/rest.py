"""REST 轮询：K 线（含主动买额 → CVD）、OI、资金费率。

每根 bar 收盘后跑一轮；每轮都从库里最后一条往后补，所以断电/睡眠后重启会自动补齐
（强平除外——强平没有公开历史，只能靠 WS 实时收）。
"""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from . import normalize as N
from .config import BYBIT_OI_INTERVAL, Config, floor_ts, now_ms
from .db import Store

log = logging.getLogger("ms.rest")
DAY = 86_400_000
OI_HIST_STEP = 300_000            # Binance openInterestHist 用 5m，最细
OI_HIST_MAX_AGE = 29 * DAY        # 官方只保留约 1 个月


class HttpError(Exception):
    pass


class Poller:
    def __init__(self, cfg: Config, store: Store, session: aiohttp.ClientSession):
        self.cfg, self.store, self.s = cfg, store, session

    async def get(self, url: str, params: dict):
        last = None
        for attempt in range(4):
            try:
                async with self.s.get(url, params=params, proxy=self.cfg.proxy,
                                      timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 429 or r.status == 418:
                        wait = int(r.headers.get("Retry-After", "30"))
                        log.warning("限频 %s，等待 %ss", url, wait)
                        await asyncio.sleep(wait)
                        continue
                    body = await r.json(content_type=None)
                    if r.status != 200:
                        raise HttpError(f"{r.status} {url} {str(body)[:200]}")
                    await asyncio.sleep(self.cfg.request_gap_sec)
                    return body
            except (aiohttp.ClientError, asyncio.TimeoutError, HttpError) as e:
                last = e
                await asyncio.sleep(2 ** attempt)
        raise HttpError(f"重试耗尽: {url} {params} {last}")

    def _start(self, last: int | None, step: int, max_age: float | None = None) -> int:
        now = now_ms()
        earliest = now - int((max_age if max_age is not None else self.cfg.lookback_days * DAY))
        earliest = floor_ts(earliest, step)
        return earliest if last is None else max(last + step, earliest)

    # ---------- Binance ----------
    async def klines(self, market: str, symbol: str) -> int:
        cfg, iv, step = self.cfg, self.cfg.bar_interval, self.cfg.interval_ms
        if market == "perp":
            url, limit = f"{cfg.fapi}/fapi/v1/klines", 1500
        else:
            url, limit = f"{cfg.spot_api}/api/v3/klines", 1000
        last = self.store.last_ts("bars", "venue='binance' AND market=? AND symbol=? AND interval=?",
                                  (market, symbol, iv))
        start, total = self._start(last, step), 0
        while start < now_ms() - step:
            raw = await self.get(url, {"symbol": symbol, "interval": iv, "startTime": start, "limit": limit})
            if not raw:
                break
            total += self.store.upsert_bars(N.binance_klines(raw, "binance", market, symbol, iv, now_ms()))
            nxt = int(raw[-1][0]) + step
            if nxt <= start or len(raw) < limit:
                break
            start = nxt
        return total

    async def premium_and_oi(self, symbol: str) -> int:
        p = await self.get(f"{self.cfg.fapi}/fapi/v1/premiumIndex", {"symbol": symbol})
        prow = N.binance_premium(p, symbol)
        self.store.upsert_funding_live([prow])
        oi = await self.get(f"{self.cfg.fapi}/fapi/v1/openInterest", {"symbol": symbol})
        self.store.upsert_oi([N.binance_oi_snapshot(oi, symbol, prow[3])])
        return 2

    async def oi_hist(self, symbol: str) -> int:
        last = self.store.last_ts("oi", "venue='binance' AND symbol=? AND source='hist5m'", (symbol,))
        start = self._start(last, OI_HIST_STEP, max_age=min(self.cfg.lookback_days * DAY, OI_HIST_MAX_AGE))
        total = 0
        while start < now_ms() - OI_HIST_STEP:
            end = start + 500 * OI_HIST_STEP
            raw = await self.get(f"{self.cfg.fapi}/futures/data/openInterestHist",
                                 {"symbol": symbol, "period": "5m", "startTime": start,
                                  "endTime": end, "limit": 500})
            total += self.store.upsert_oi(N.binance_oi_hist(raw or [], symbol))
            start = end
        return total

    async def funding_hist(self, symbol: str) -> int:
        last = self.store.last_ts("funding_settled", "venue='binance' AND symbol=?", (symbol,))
        start = self._start(last, 1)
        raw = await self.get(f"{self.cfg.fapi}/fapi/v1/fundingRate",
                             {"symbol": symbol, "startTime": start, "limit": 1000})
        return self.store.upsert_funding_settled(N.binance_funding_hist(raw or [], symbol))

    # ---------- Bybit（交叉校验） ----------
    async def bybit_oi(self, symbol: str) -> int:
        iv = BYBIT_OI_INTERVAL.get(self.cfg.bar_interval, "15min")
        source = f"hist{iv.replace('min', 'm')}"
        step = {"5min": 300_000, "15min": 900_000, "30min": 1_800_000,
                "1h": 3_600_000, "4h": 14_400_000}[iv]
        last = self.store.last_ts("oi", "venue='bybit' AND symbol=? AND source=?", (symbol, source))
        start, total = self._start(last, step), 0
        while start < now_ms() - step:
            end = start + 200 * step
            raw = await self.get(f"{self.cfg.bybit_api}/v5/market/open-interest",
                                 {"category": "linear", "symbol": symbol, "intervalTime": iv,
                                  "startTime": start, "endTime": end, "limit": 200})
            if raw.get("retCode", 0) != 0:
                raise HttpError(f"bybit OI {symbol}: {raw.get('retMsg')}")
            total += self.store.upsert_oi(N.bybit_oi(raw, symbol, source))
            start = end
        return total

    async def bybit_ticker(self, symbol: str) -> int:
        raw = await self.get(f"{self.cfg.bybit_api}/v5/market/tickers",
                             {"category": "linear", "symbol": symbol})
        res = N.bybit_ticker(raw, symbol, now_ms())
        if not res:
            raise HttpError(f"bybit ticker 空: {symbol} {raw.get('retMsg')}")
        self.store.upsert_funding_live([res[0]])
        self.store.upsert_oi([res[1]])
        return 2

    # ---------- 调度 ----------
    async def _job(self, name: str, coro):
        try:
            n = await coro
            self.store.log(now_ms(), name, True, f"rows={n}")
            return True
        except Exception as e:  # noqa: BLE001 — 单项失败不影响其它项
            log.error("%s 失败: %s", name, e)
            self.store.log(now_ms(), name, False, str(e))
            return False

    async def run_once(self) -> tuple[int, int]:
        ok = fail = 0
        for sc in self.cfg.symbols:
            s = sc.symbol
            jobs = [(f"klines.perp.{s}", self.klines("perp", s)),
                    (f"premium_oi.{s}", self.premium_and_oi(s)),
                    (f"oi_hist.{s}", self.oi_hist(s)),
                    (f"funding_hist.{s}", self.funding_hist(s))]
            if sc.spot:
                jobs.append((f"klines.spot.{s}", self.klines("spot", s)))
            if self.cfg.bybit_enabled:
                jobs += [(f"bybit_oi.{s}", self.bybit_oi(s)), (f"bybit_ticker.{s}", self.bybit_ticker(s))]
            for name, coro in jobs:
                if await self._job(name, coro):
                    ok += 1
                else:
                    fail += 1
        log.info("轮询完成: 成功 %d 项, 失败 %d 项", ok, fail)
        return ok, fail

    async def loop(self):
        step = self.cfg.interval_ms
        while True:
            await self.run_once()
            nxt = floor_ts(now_ms(), step) + step + int(self.cfg.poll_delay_sec * 1000)
            await asyncio.sleep(max(1.0, (nxt - now_ms()) / 1000))
