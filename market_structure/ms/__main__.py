"""用法（在 market_structure/ 目录下）：
  python -m ms run    [--config config.toml]      常驻：REST 轮询 + 强平 WS + 每晚健康报告
  python -m ms once   [--config config.toml]      只跑一轮 REST（首次回补 / 手动补数）
  python -m ms health [--config config.toml] [--hours 24]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import logging.handlers
import signal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp

from . import health
from .config import Config, load_config
from .db import Store, connect
from .rest import Poller
from .ws import build_streams

log = logging.getLogger("ms")


def setup_logging(cfg: Config):
    logdir = cfg.base_dir / "logs"
    logdir.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(logdir / "collector.log", maxBytes=5_000_000, backupCount=3,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = [fh, sh]


def write_health(cfg: Config) -> str:
    con = connect(cfg.db_path, readonly=True)
    try:
        text = health.report(cfg, con)
    finally:
        con.close()
    rdir = cfg.base_dir / "reports"
    rdir.mkdir(exist_ok=True)
    day = datetime.now(ZoneInfo(cfg.tz)).strftime("%Y-%m-%d")
    (rdir / f"health-{day}.txt").write_text(text + "\n", encoding="utf-8")
    return text


async def nightly(cfg: Config):
    tz = ZoneInfo(cfg.tz)
    hh, mm = map(int, cfg.health_at.split(":"))
    while True:
        now = datetime.now(tz)
        nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        await asyncio.sleep((nxt - now).total_seconds())
        try:
            text = write_health(cfg)
            log.info("健康报告:\n%s", text)
        except Exception as e:  # noqa: BLE001
            log.error("健康报告失败: %s", e)


def _session() -> aiohttp.ClientSession:
    # trust_env=True：proxy 留空时使用环境变量里的 HTTPS_PROXY
    return aiohttp.ClientSession(trust_env=True, headers={"User-Agent": "crypto_os-market_structure/0.1"})


async def run(cfg: Config):
    store = Store(cfg.db_path)
    async with _session() as s:
        poller = Poller(cfg, store, s)
        streams = build_streams(cfg, store, s)
        tasks = [asyncio.create_task(poller.loop(), name="poller"),
                 asyncio.create_task(nightly(cfg), name="nightly")]
        for st in streams:
            tasks += [asyncio.create_task(st.run(), name=f"ws.{st.venue}"),
                      asyncio.create_task(st.housekeeping(), name=f"hk.{st.venue}")]
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        log.info("采集器启动：%d 个品种，bar=%s，库=%s", len(cfg.symbols), cfg.bar_interval, cfg.db_path)
        waiter = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait([waiter, *tasks], return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            if t is not waiter and t.exception():
                log.error("任务 %s 意外退出: %r", t.get_name(), t.exception())
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for st in streams:
            st.flush()
        log.info("采集器已停止")


async def once(cfg: Config):
    store = Store(cfg.db_path)
    async with _session() as s:
        ok, fail = await Poller(cfg, store, s).run_once()
    print(f"完成：成功 {ok} 项，失败 {fail} 项")


def main():
    ap = argparse.ArgumentParser(prog="ms")
    ap.add_argument("cmd", choices=["run", "once", "health"])
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--hours", type=float, default=24)
    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.cmd == "health":
        con = connect(cfg.db_path, readonly=True)
        print(health.report(cfg, con, a.hours))
        return
    setup_logging(cfg)
    asyncio.run(run(cfg) if a.cmd == "run" else once(cfg))


if __name__ == "__main__":
    main()
