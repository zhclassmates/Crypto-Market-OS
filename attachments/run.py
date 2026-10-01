"""命令行入口。
  python3 run.py once          跑一轮（cron / launchd 每小时调一次这个）
  python3 run.py once --force  强制刷新宇宙 + 交易所状态
  python3 run.py loop          不想配 cron：前台常驻，每小时第 3 分钟跑一次
  python3 run.py backfill      给当前观察池回填 7 天小时 K（一次性，约 10~20 分钟，GT 限速所致）
  python3 run.py rates         打印 ListingP 频率表（Alpha→永续 7/30/90 天）
  python3 run.py status        看上一轮运行日志
"""
import json
import sys
import time

import collect
import db
import listing_table as LT
import sources as S


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
