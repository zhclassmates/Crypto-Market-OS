"""WebSocket：只收强平（强平没有公开历史，必须实时收）。

- Binance: 全市场 !forceOrder@arr（每个品种每秒最多推一笔快照）
- Bybit: allLiquidation.{symbol}（交叉校验）
每分钟若 WS 全程在线，写一行 ws_heartbeat，用于事后计算每根 bar 的强平覆盖率。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

import aiohttp

from . import normalize as N
from .config import Config, floor_ts, now_ms
from .db import Store

log = logging.getLogger("ms.ws")
MIN = 60_000


class LiqStream:
    def __init__(self, venue: str, url: str, parse: Callable[[dict], list[tuple]],
                 store: Store, session: aiohttp.ClientSession, proxy: str | None,
                 subscribe: list[dict] | None = None, app_ping: dict | None = None):
        self.venue, self.url, self.parse = venue, url, parse
        self.store, self.s, self.proxy = store, session, proxy
        self.subscribe, self.app_ping = subscribe or [], app_ping
        self.connected_since: int | None = None
        self.msgs_this_minute = 0
        self.buf: list[tuple] = []
        self.reconnects = 0

    async def _pinger(self, ws):
        while True:
            await asyncio.sleep(20)
            await ws.send_str(json.dumps(self.app_ping))

    async def _session(self):
        async with self.s.ws_connect(self.url, proxy=self.proxy, heartbeat=30,
                                     timeout=aiohttp.ClientWSTimeout(ws_close=10)) as ws:
            for m in self.subscribe:
                await ws.send_str(json.dumps(m))
            self.connected_since = now_ms()
            log.info("%s WS 已连接", self.venue)
            pinger = asyncio.create_task(self._pinger(ws)) if self.app_ping else None
            try:
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        if msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                            break
                        continue
                    data = json.loads(msg.data)
                    if isinstance(data, dict) and data.get("op") == "subscribe" and not data.get("success", True):
                        log.error("%s 订阅失败: %s", self.venue, data)
                        self.store.log(now_ms(), f"ws_sub.{self.venue}", False, str(data))
                        continue
                    self.msgs_this_minute += 1
                    rows = self.parse(data)
                    if rows:
                        self.buf.extend(rows)
            finally:
                if pinger:
                    pinger.cancel()
                self.connected_since = None

    async def run(self):
        backoff = 1
        while True:
            t0 = now_ms()
            try:
                await self._session()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("%s WS 异常: %s", self.venue, e)
            self.connected_since = None
            self.reconnects += 1
            self.store.log(now_ms(), f"ws_reconnect.{self.venue}", False, "")
            backoff = 1 if now_ms() - t0 > 30_000 else min(backoff * 2, 60)   # 连得住就不累加退避
            await asyncio.sleep(backoff)

    def flush(self):
        if self.buf:
            rows, self.buf = self.buf, []
            self.store.insert_liqs(rows)

    async def housekeeping(self):
        """每 2 秒落盘；每分钟边界判断上一分钟是否全程在线。"""
        cur_min = floor_ts(now_ms(), MIN)
        while True:
            await asyncio.sleep(2)
            self.flush()
            m = floor_ts(now_ms(), MIN)
            if m != cur_min:
                if self.connected_since is not None and self.connected_since <= cur_min:
                    self.store.heartbeat(self.venue, cur_min, self.msgs_this_minute)
                self.msgs_this_minute = 0
                cur_min = m


def _one(fn):
    def w(msg):
        r = fn(msg)
        return [r] if r else []
    return w


def build_streams(cfg: Config, store: Store, session: aiohttp.ClientSession) -> list[LiqStream]:
    streams = [LiqStream("binance", cfg.force_order_ws, _one(N.binance_force_order),
                         store, session, cfg.proxy)]
    if cfg.bybit_enabled:
        topics = [f"allLiquidation.{s.symbol}" for s in cfg.symbols]
        # 每个 topic 单独订阅：一个品种 Bybit 没有，不会连累同批其它品种
        subs = [{"op": "subscribe", "args": [t]} for t in topics]
        streams.append(LiqStream("bybit", cfg.bybit_ws, N.bybit_all_liq, store, session, cfg.proxy,
                                 subscribe=subs, app_ping={"op": "ping"}))
    return streams
