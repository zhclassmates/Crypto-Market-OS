#!/usr/bin/env python3
"""Radar engine 入口。只读 market.sqlite，只写 radar.sqlite。不发任何外部请求。

  python3 radar_run.py once                 跑一轮（as_of = 现在）
  python3 radar_run.py loop                 常驻，每 RUN_INTERVAL_SEC 一轮（文件锁，防重入）
  python3 radar_run.py status [--json]      最近一轮的漏斗计数
  python3 radar_run.py verify               用存下的 signal 原值离线重算 score / stage，逐行比对
  python3 radar_run.py recompute --as-of TS --out PATH
                                            在指定时刻离线重算（不用 TS 之后的数据），写到另一个库
"""
import fcntl
import json
import os
import sys
import time

import radar_config as C
import radar_db
import radar_engine as E

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK_PATH = os.path.join(HERE, "radar.lock")


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def once():
    return E.run_once(log=log)


def loop():
    fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another radar loop holds the lock; exiting")
        return 0
    while True:
        started = time.time()
        try:
            E.run_once(log=log)
        except Exception as e:  # 记进 radar_run.error 后继续
            log(f"run failed: {type(e).__name__}: {e}")
        time.sleep(max(5, C.RUN_INTERVAL_SEC - (time.time() - started)))


def status(as_json=False):
    con = radar_db.connect()
    row = con.execute("SELECT * FROM radar_run WHERE finished_at IS NOT NULL ORDER BY run_id DESC LIMIT 1").fetchone()
    if row is None:
        print("no radar run yet")
        return
    d = dict(row)
    d.pop("cross_list_coverage", None)
    d["age_sec"] = int(time.time()) - d["as_of"]
    if as_json:
        print(json.dumps(d))
        return
    for k, v in d.items():
        print(f"{k:18} {v}")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "once"
    if cmd == "once":
        once()
    elif cmd == "loop":
        return loop()
    elif cmd == "status":
        status("--json" in argv)
    elif cmd == "verify":
        print(json.dumps(E.verify()))
    elif cmd == "recompute":
        args = dict(zip(argv[2::2], argv[3::2]))
        as_of = int(args["--as-of"])
        out = args["--out"]
        if os.path.abspath(out) == os.path.abspath(radar_db.RADAR_DB_PATH):
            print("--out must not be the live radar.sqlite", file=sys.stderr)
            return 2
        E.run_once(radar_path=out, as_of=as_of, mode="recompute", log=log)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv) or 0)
