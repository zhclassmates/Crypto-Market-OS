#!/usr/bin/env python3
"""日 K 线采集器入口（launchd + --once 模式）。

  python3 kline_run.py once                    跑一轮后退出（launchd 周期启动）
  python3 kline_run.py add <chain> <addr> [label]
  python3 kline_run.py remove <chain> <addr>
  python3 kline_run.py list
  python3 kline_run.py status                  展示时间戳

不再提供 loop 模式：避免和 launchd 重复采集；
崩溃由 launchd 兜底，没有"幽灵进程"问题。
"""
import json
import sys
import time

import kline_db as db


def fmt_ts(ts):
    if not ts:
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))
    except (TypeError, OSError):
        return str(ts)


def status():
    con = db.connect()
    last_kline = db.meta_get(con, "last_kline_update")
    last_run_start = db.meta_get(con, "last_run_start")
    last_run = db.meta_get(con, "last_run")
    watch_count = con.execute("SELECT COUNT(*) AS n FROM kline_watch").fetchone()["n"]
    kline_count = con.execute("SELECT COUNT(*) AS n FROM daily_kline").fetchone()["n"]
    con.close()
    print("日 K 采集器状态")
    print(f"  最近一轮完成     : {fmt_ts(last_kline)}")
    print(f"  最近一轮开始     : {fmt_ts(last_run_start)}")
    print(f"  watch 数量       : {watch_count}")
    print(f"  日 K 总行数      : {kline_count}")
    if last_run:
        try:
            log = json.loads(last_run)
            print(f"  拉取 {len(log.get('fetched', []))} 个币，错误 {len(log.get('errors', []))} 个")
        except Exception:
            pass


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "once"

    if cmd == "once":
        import kline_collect as K
        print(f"[{time.strftime('%H:%M:%S')}] 开始拉取日 K...", flush=True)
        K.run_once()
        print(f"[{time.strftime('%H:%M:%S')}] 完成", flush=True)

    elif cmd == "add":
        if len(sys.argv) < 4:
            print("用法: add <chain> <address> [label]")
            return
        import kline_collect as K
        chain, address = sys.argv[2], sys.argv[3]
        label = sys.argv[4] if len(sys.argv) > 4 else None
        K.add_token(chain, address, label)

    elif cmd == "remove":
        if len(sys.argv) < 4:
            print("用法: remove <chain> <address>")
            return
        import kline_collect as K
        K.remove_token(sys.argv[2], sys.argv[3])

    elif cmd == "list":
        import kline_collect as K
        K.list_tokens()

    elif cmd == "status":
        status()

    else:
        print(__doc__)


if __name__ == "__main__":
    main()