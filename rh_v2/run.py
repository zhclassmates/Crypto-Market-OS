"""命令行入口。
  python3 run.py once          跑一轮（cron / launchd 每小时调一次这个）
  python3 run.py once --force  强制刷新宇宙 + 交易所状态
  python3 run.py loop          不想配 cron：前台常驻，每小时第 3 分钟跑一次
  python3 run.py backfill      给当前观察池回填 7 天小时 K（一次性，约 10~20 分钟，GT 限速所致）
  python3 run.py rates         打印 ListingP 频率表（Alpha→永续 7/30/90 天）
  python3 run.py status        看上一轮运行日志
"""
import fcntl
import json
import os
import sys
import time

import collect
import config as C
import db
import listing_table as LT
import sources as S


def acquire_once_lock():
    """上一轮还在跑就跳过本轮（launchd 不重叠执行）。返回锁住的文件句柄，进程结束自动释放。"""
    f = open(C.LOCK_PATH, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    f.write(str(os.getpid()))
    f.flush()
    return f


def skip_because_locked():
    con = db.connect()
    log = {"ts": collect.hour_ts(), "phase": "skipped", "skipped": ["locked(上一轮未结束)"]}
    db.meta_set(con, "last_run", log)
    con.commit()
    con.close()
    print(f"[{time.strftime('%H:%M:%S')}] 上一轮还在跑，本轮跳过", flush=True)


def backfill():
    con = db.connect()
    ts = con.execute("SELECT MAX(ts) FROM snapshots").fetchone()[0]
    if not ts:
        print("先跑一次 once，才知道观察池里有谁")
        return
    obs = con.execute("SELECT s.address, t.top_pool FROM snapshots s JOIN tokens t USING(address) "
                      "WHERE s.ts=? AND s.in_obs=1", (ts,)).fetchall()
    for i, r in enumerate(obs, 1):
        if not r["top_pool"]:
            continue
        rows = S.gt_ohlcv_hourly(r["top_pool"])
        con.executemany("INSERT OR REPLACE INTO ohlcv VALUES(?,?,?,?,?,?,?)",
                        [(r["address"], *x) for x in rows])
        con.commit()
        print(f"[{i}/{len(obs)}] {r['address'][:10]} +{len(rows)} 根")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "once"
    force = "--force" in sys.argv
    if cmd == "once":
        lock = acquire_once_lock()
        if lock is None:
            skip_because_locked()
            return
        print(json.dumps(collect.run_once(force, force), ensure_ascii=False, indent=1, default=str))
    elif cmd == "loop":
        while True:
            print(json.dumps(collect.run_once(), ensure_ascii=False, default=str), flush=True)
            now = time.time()
            time.sleep(max(60, 3600 - now % 3600 + 180))
    elif cmd == "backfill":
        backfill()
    elif cmd == "rates":
        con = db.connect()
        if force or not con.execute("SELECT 1 FROM binance_events LIMIT 1").fetchone():
            print(LT.refresh_listings(con))
        print(LT.report(LT.base_rates(con)))
    elif cmd == "status":
        print(db.meta_get(db.connect(), "last_run", "还没跑过"))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
