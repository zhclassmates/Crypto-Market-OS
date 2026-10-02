#!/usr/bin/env python3
"""全市场采集入口（launchd + --once 模式）。

  python3 market_run.py loop          常驻。热数据 10–30s，温 60s，冷 10min
  python3 market_run.py once          每条车道跑一轮后退出
  python3 market_run.py status        按 source × chain 看心跳 / 成功 / 落库
  python3 market_run.py status --json

loop 用文件锁。launchd 应 KeepAlive 拉起 loop，不要再用 StartInterval 整表打一轮。
"""
import json
import sys
import time

import market_db as db
import market_health as H


def fmt_ts(ts):
    if not ts:
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))
    except (TypeError, OSError):
        return str(ts)


def _age(now, ts):
    if not ts:
        return None
    return int(now) - int(ts)


def status():
    con = db.connect()
    H.ensure_catalog(con)
    con.commit()
    now = int(time.time())
    rows = con.execute(
        "SELECT * FROM source_health ORDER BY chain, source"
    ).fetchall()
    payload = []
    for r in rows:
        api_age = _age(now, r["last_success"])
        db_age = _age(now, r["db_written_at"])
        item = {
            "source": r["source"],
            "chain": r["chain"],
            "period_sec": r["period_sec"],
            "status": H.classify_status(
                now, r["last_attempt"], r["last_success"], r["consecutive_errors"],
                r["has_display_rows"], r["period_sec"], r["round_ok"],
            ),
            "collector_heartbeat": r["collector_heartbeat"],
            "last_attempt": r["last_attempt"],
            "last_success": r["last_success"],
            "source_timestamp": r["source_timestamp"],
            "source_timestamp_missing": bool(r["source_timestamp_missing"]),
            "db_written_at": r["db_written_at"],
            "ui_fetched_at": r["ui_fetched_at"],
            "last_change_at": r["last_change_at"],
            "api_age_sec": api_age,
            "db_age_sec": db_age,
            "rows_received": r["rows_received"],
            "hot_changed": r["hot_changed"],
            "cold_changed": r["cold_changed"],
            "latency_ms": r["latency_ms"],
            "p95_latency_ms": H.p95_for(con, r["source"], r["chain"], now),
            "consecutive_errors": r["consecutive_errors"],
            "last_error": r["last_error"],
            "attempts": r["attempts"],
            "successes": r["successes"],
        }
        payload.append(item)
    con.close()

    if "--json" in sys.argv:
        print(json.dumps({"now": now, "sources": payload}, ensure_ascii=False, indent=2))
        return

    print("市场采集器状态  每个 source × chain 的时钟分开，不合成一个 updated_at")
    print(f"{'source':<20} {'chain':<12} {'status':<8} {'api':>6} {'db':>6} {'hot':>5} {'err':>4}  last_error")
    for item in payload:
        err = (item["last_error"] or "").replace("\n", " ")[:60]
        api = "—" if item["api_age_sec"] is None else str(item["api_age_sec"])
        db_age = "—" if item["db_age_sec"] is None else str(item["db_age_sec"])
        print(
            f"{item['source']:<20} {item['chain']:<12} {item['status']:<8} "
            f"{api:>6} {db_age:>6} {item['hot_changed']:>5} {item['consecutive_errors']:>4}  {err}"
        )
        print(
            f"  心跳 {fmt_ts(item['collector_heartbeat'])}  "
            f"请求 {fmt_ts(item['last_attempt'])}  "
            f"成功 {fmt_ts(item['last_success'])}  "
            f"上游 {('缺失' if item['source_timestamp_missing'] else fmt_ts(item['source_timestamp']))}  "
            f"落库 {fmt_ts(item['db_written_at'])}  "
            f"变化 {fmt_ts(item['last_change_at'])}  "
            f"UI {fmt_ts(item['ui_fetched_at'])}"
        )


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "once"
    if cmd == "once":
        import market_collect as M
        print(json.dumps(M.run_once(), ensure_ascii=False, default=str))
    elif cmd == "loop":
        import market_collect as M
        M.run_loop()
    elif cmd == "status":
        status()
    elif cmd == "phase1":
        import market_research as research
        con = db.connect()
        try:
            print(json.dumps(research.evidence(con), ensure_ascii=False, indent=2, default=str))
        finally:
            con.close()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()