#!/usr/bin/env python3
"""统一夜间报告：读取 rh_v2 + market_structure + access_radar，输出 reports/YYYY-MM-DD.txt。

用法：
  python3 ops/nightly.py           # 用今天的日期
  python3 ops/nightly.py 2026-10-01
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RH_DB = ROOT / "rh_v2" / "rhv2.sqlite"
MS_DB = ROOT / "market_structure" / "data" / "market_structure.sqlite"
ACCESS_DB = Path(os.environ.get("ACCESS_DB") or os.environ.get("ACCESS_RADAR_DB")   # 后者仅兼容旧名
                 or ROOT / "access_radar" / "access.sqlite")
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


def _has_table(con, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?", (name,)).fetchone() is not None


def _bj(ms) -> str:
    """UTC 毫秒 -> 'MM-DD HH:MM'（UTC+8）。"""
    if ms is None:
        return "-"
    return datetime.fromtimestamp(ms / 1000 + 8 * 3600, tz=timezone.utc).strftime("%m-%d %H:%M")


def access_section(date: str, db_path: Path | None = None, max_events: int = 15) -> str:
    """Access Radar 当天（UTC 日界）概况：事件、来源健康、断线缺口、身份解析进度。只读。"""
    db = Path(db_path or ACCESS_DB)
    if not db.exists():
        return "[access_radar] 库文件不存在"
    con = _con(db)
    con.row_factory = sqlite3.Row
    if not _has_table(con, "access_event"):
        con.close()
        return "[access_radar] 库未初始化（缺 access_event 表）"
    dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    day_start = int(dt.timestamp()) * 1000
    day_end = day_start + DAY_MS
    day = (day_start, day_end)

    # 1) 当天新事件（按 observed_at = 我方首次入库），按类型计数；撤回 / 临时单列。
    #    有 group_key 列时按它去重：同一公告同一币的多个 quote 只算一条（group_key 当不透明串用）。
    cols = {r[1] for r in con.execute("PRAGMA table_info(access_event)")}
    gk = "group_key" if "group_key" in cols else "event_id"
    live = "observed_at >= ? AND observed_at < ? AND retracted = 0"
    by_type = con.execute(
        f"""SELECT event_type, COUNT(DISTINCT {gk}) c, COUNT(*) n FROM access_event
           WHERE {live} GROUP BY event_type ORDER BY c DESC, event_type""",
        day).fetchall()
    type_str = ", ".join(f"{r['event_type']}={r['c']}" + (f"（{r['n']} 个市场）" if r['n'] != r['c'] else "")
                         for r in by_type) or "无"
    retracted = con.execute(
        f"SELECT COUNT(DISTINCT {gk}) FROM access_event WHERE retracted = 1 AND updated_at >= ? AND updated_at < ?",
        day).fetchone()[0]
    provisional = con.execute(
        f"SELECT COUNT(DISTINCT {gk}) FROM access_event WHERE provisional = 1 AND {live}", day).fetchone()[0]
    top = con.execute(
        f"""SELECT MAX(anchor_at) anchor_at, event_type, platform_id, asset_key,
                  GROUP_CONCAT(DISTINCT NULLIF(quote, '')) quotes, MAX(confidence) confidence,
                  MAX(independent_source_count) independent_source_count, MAX(provisional) provisional
           FROM access_event WHERE {live}
           GROUP BY {gk}, event_type, platform_id, asset_key
           ORDER BY confidence DESC, anchor_at DESC LIMIT ?""", (*day, max_events)).fetchall()
    top_lines = [f"    {_bj(r['anchor_at'])}  {r['event_type']:<20} {r['platform_id']:<10} {r['asset_key']}"
                 f"{('/' + r['quotes'].replace(',', '+')) if r['quotes'] else ''}  置信 {r['confidence']:.2f}×{r['independent_source_count']}"
                 f"{'  临时' if r['provisional'] else ''}" for r in top]

    # 2) 来源健康：非 HEALTHY 的 (source, scope)，当天降级快照数、被拒迁移数
    bad = con.execute(
        """SELECT source_id, scope, status, last_error FROM source_health
           WHERE status <> 'HEALTHY' ORDER BY status DESC, source_id, scope""").fetchall()
    bad_str = "; ".join(f"{r['source_id']}/{r['scope'] or '-'}={r['status']}"
                        f"{(' (' + r['last_error'][:60] + ')') if r['last_error'] else ''}" for r in bad) or "全部正常"
    n_health = con.execute("SELECT COUNT(*) FROM source_health").fetchone()[0]
    degraded = con.execute(
        "SELECT COUNT(*) FROM source_snapshot WHERE outcome = 'DEGRADED' AND fetched_at >= ? AND fetched_at < ?",
        day).fetchone()[0]
    rejected = con.execute("SELECT COUNT(*) FROM rejected_transition WHERE at >= ? AND at < ?", day).fetchone()[0]

    # 3) 断线缺口：仍断开的，和已恢复但还没补数的
    gaps = con.execute(
        """SELECT source_id, scope, started_at, ended_at FROM source_disconnect
           WHERE ended_at IS NULL OR backfilled = 0 ORDER BY started_at""").fetchall()
    gap_str = "; ".join(f"{r['source_id']}{('/' + r['scope']) if r['scope'] else ''} {_bj(r['started_at'])}→"
                        f"{_bj(r['ended_at']) if r['ended_at'] else '仍断开'}" for r in gaps) or "无"

    # 4) 采集进程视角（access_db 的 source_run 表，可能还没建）
    run_str = "（无 source_run 表）"
    if _has_table(con, "source_run"):
        errs = con.execute(
            "SELECT source_id, consecutive_errors, last_error FROM source_run WHERE consecutive_errors > 0 ORDER BY source_id"
        ).fetchall()
        run_str = "; ".join(f"{r['source_id']} 连续失败 {r['consecutive_errors']}" for r in errs) or "无连续失败"
    maint_str = "（无 maintenance_run 表）"
    if _has_table(con, "maintenance_run"):
        jobs = con.execute(
            "SELECT job_id, job_state, last_success, consecutive_errors FROM maintenance_run ORDER BY job_id").fetchall()
        maint_str = "; ".join(f"{r['job_id']}={r['job_state']} 上次成功 {_bj(r['last_success'])}"
                              f"{(' 连续失败 ' + str(r['consecutive_errors'])) if r['consecutive_errors'] else ''}"
                              for r in jobs) or "无"

    # 5) 身份解析进度
    res = {r[0]: r[1] for r in con.execute(
        "SELECT resolution_status, COUNT(*) FROM source_asset_ref GROUP BY resolution_status")}
    res_total = sum(res.values())
    res_str = (f"CONFIRMED={res.get('CONFIRMED', 0)}, SUGGESTED={res.get('SUGGESTED', 0)}, "
               f"UNRESOLVED={res.get('UNRESOLVED', 0)}（共 {res_total}）")
    con.close()

    lines = [f"[access_radar] {date}",
             f"  新事件: {type_str}",
             f"  撤回: {retracted}   临时(待确认): {provisional}",
             f"  来源健康: {bad_str}（共 {n_health} 个 source/scope）",
             f"  降级快照: {degraded}   被拒迁移: {rejected}",
             f"  断线缺口: {gap_str}",
             f"  采集进程: {run_str}",
             f"  维护任务: {maint_str}",
             f"  身份解析: {res_str}"]
    if top_lines:
        lines.append(f"  事件明细（按置信度，最多 {max_events} 条，时间 UTC+8）:")
        lines.extend(top_lines)
    return "\n".join(lines)


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
    body = "\n\n".join([rh_v2_section(date), ms_section(date), access_section(date), sync_section()])
    out.write_text(body + "\n", encoding="utf-8")
    print(f"已写入 {out}")
    print("\n" + body)


if __name__ == "__main__":
    main()
