#!/usr/bin/env python3
"""统一夜间报告：读取 rh_v2 + market_structure，输出 reports/YYYY-MM-DD.txt。

用法：
  python3 ops/nightly.py           # 用今天的日期
  python3 ops/nightly.py 2026-10-01
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RH_DB = ROOT / "rh_v2" / "rhv2.sqlite"
MS_DB = ROOT / "market_structure" / "data" / "market_structure.sqlite"
OUT_DIR = ROOT / "reports"
DAY_MS = 86_400_000


def _con(path: Path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def rh_v2_section(date: str) -> str:
    if not RH_DB.exists():
        return "[rh_v2] 库文件不存在"
    con = _con(RH_DB)
    con.row_factory = sqlite3.Row

    # 当天 0 点 UTC 边界
    dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    day_start = int(dt.timestamp())
    day_end = day_start + 86400

    # 1) 当天运行轮数（通过 meta.last_run 时间戳近似，更准确是查 snapshots 分 ts 计数）
    runs = con.execute(
        "SELECT ts, COUNT(*) c FROM snapshots WHERE ts >= ? AND ts < ? GROUP BY ts",
        (day_start, day_end),
    ).fetchall()
    total_rounds = len(runs)

    # 2) 失败轮数：最近一轮 phase != done
    last_run = con.execute("SELECT v FROM meta WHERE k='last_run'").fetchone()
    failed = 0
    if last_run:
        try:
            log = json.loads(last_run[0])
            if log.get("phase") != "done":
                failed = 1
        except Exception:
            pass

    # 3) 单轮最长用时
    max_secs = 0.0
    if last_run:
        try:
            max_secs = float(json.loads(last_run[0]).get("secs", 0))
        except Exception:
            pass

    # 4) 各状态币数
    states = con.execute("SELECT state, COUNT(*) c FROM state GROUP BY state").fetchall()
    state_str = ", ".join(f"{r['state']}={r['c']}" for r in states) or "无"

    # 5) 新进入 READY 的币
    ready = con.execute(
        """SELECT t.symbol, s.since_ts FROM state s JOIN tokens t USING(address)
           WHERE s.state='READY' AND s.since_ts >= ? AND s.since_ts < ?""",
        (day_start, day_end),
    ).fetchall()
    ready_str = ", ".join(f"{r['symbol'] or '?'}" for r in ready) or "无"

    con.close()
    return f"""[rh_v2] {date}
  运行轮数: {total_rounds}
  失败轮数: {failed}
  单轮最长: {max_secs:.1f}s
  状态分布: {state_str}
  新 READY: {ready_str}"""


def ms_section(date: str) -> str:
    if not MS_DB.exists():
        return "[market_structure] 库文件不存在"
    con = _con(MS_DB)
    con.row_factory = sqlite3.Row
    dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    day_start = int(dt.timestamp()) * 1000
    day_end = day_start + DAY_MS

    # 最近 24h 各类数据点数
    bars = con.execute(
        "SELECT COUNT(*) c FROM bars WHERE ts >= ? AND ts < ?", (day_start, day_end)
    ).fetchone()["c"]
    oi = con.execute(
        "SELECT COUNT(*) c FROM oi WHERE ts >= ? AND ts < ?", (day_start, day_end)
    ).fetchone()["c"]
    fund = con.execute(
        "SELECT COUNT(*) c FROM funding_live WHERE ts >= ? AND ts < ?", (day_start, day_end)
    ).fetchone()["c"]
    liq = con.execute(
        "SELECT COUNT(*) c FROM liq_prints WHERE ts >= ? AND ts < ?", (day_start, day_end)
    ).fetchone()["c"]
    hb = con.execute(
        "SELECT venue, COUNT(*) c FROM ws_heartbeat WHERE minute_ts >= ? AND minute_ts < ? GROUP BY venue",
        (day_start, day_end),
    ).fetchall()
    hb_str = ", ".join(f"{r['venue']}={r['c']}min" for r in hb) or "无"

    con.close()
    return f"""[market_structure] {date}
  K线 bar: {bars}
  OI 点: {oi}
  资金费率采样: {fund}
  强平笔数: {liq}
  WS 覆盖分钟: {hb_str}"""


def sync_section() -> str:
    """读取 config.toml 里 auto 条目数。"""
    cfg = ROOT / "market_structure" / "config.toml"
    if not cfg.exists():
        return "[sync] config.toml 不存在"
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    raw = tomllib.loads(cfg.read_text(encoding="utf-8"))
    auto = [s for s in raw.get("symbols", []) if s.get("auto")]
    manual = [s for s in raw.get("symbols", []) if not s.get("auto")]
    names = ", ".join(s["symbol"] for s in auto) or "无"
    return f"""[sync]
  manual 条目: {len(manual)}
  auto 条目: {len(auto)}  ({names})"""


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"{date}.txt"
    body = "\n\n".join([rh_v2_section(date), ms_section(date), sync_section()])
    out.write_text(body + "\n", encoding="utf-8")
    print(f"已写入 {out}")
    print("\n" + body)


if __name__ == "__main__":
    main()
