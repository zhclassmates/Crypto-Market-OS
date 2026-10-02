"""日 K 线采集器。通过 gmgn-cli 拉取 1d K 线并存入 SQLite。

由 launchd 周期触发（`python3 kline_run.py once`），跑完即退出。
"""
import json
import os
import subprocess
import time

import kline_db as db


GMGN_CLI = os.environ.get("GMGN_CLI", "gmgn-cli")
DEFAULT_DAYS = 30  # 每次回拉多少天


def gmgn_kline(chain, address, days=DEFAULT_DAYS):
    """调用 gmgn-cli 拉日 K，返回 list。"""
    now = int(time.time())
    frm = now - days * 86400
    cmd = [
        GMGN_CLI, "market", "kline",
        "--chain", chain,
        "--address", address,
        "--resolution", "1d",
        "--from", str(frm),
        "--to", str(now),
        "--raw",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"gmgn-cli failed: {r.stderr.strip() or r.stdout.strip()}")
    data = json.loads(r.stdout)
    rows = data.get("list") or []
    out = []
    for row in rows:
        t = int(row["time"])
        if t >= 10**12:
            t //= 1000  # ms -> s
        # 取当日 UTC 0 点
        t = t - t % 86400
        out.append((
            chain, address, t,
            str(row.get("open", row["close"])),
            str(row.get("high", row["close"])),
            str(row.get("low", row["close"])),
            str(row["close"]),
            str(row.get("volume", "")),
        ))
    return out


def run_once(days=DEFAULT_DAYS):
    con = db.connect()
    watch = con.execute("SELECT chain, address, label FROM kline_watch").fetchall()
    if not watch:
        print("watch 列表为空，先用 add 添加代币")
        return {"ok": False, "error": "empty watchlist"}

    started = int(time.time())
    log = {"ts": started, "fetched": [], "errors": []}
    for w in watch:
        chain, address, label = w["chain"], w["address"], w["label"]
        try:
            rows = gmgn_kline(chain, address, days)
            con.executemany(
                "INSERT OR REPLACE INTO daily_kline "
                "(chain,address,ts,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?,?)",
                rows,
            )
            con.commit()
            log["fetched"].append({"chain": chain, "address": address, "label": label, "rows": len(rows)})
            print(f"  [{chain}] {label or address[:12]}: {len(rows)} 根", flush=True)
        except Exception as e:
            log["errors"].append({"chain": chain, "address": address, "error": str(e)})
            print(f"  [{chain}] {label or address[:12]}: 错误 {e}", flush=True)

    finished = int(time.time())
    db.meta_set(con, "last_run_start", str(started))
    db.meta_set(con, "last_kline_update", str(finished))
    db.meta_set(con, "last_run", json.dumps(log, ensure_ascii=False))
    con.commit()
    con.close()
    return log


def add_token(chain, address, label=None):
    con = db.connect()
    con.execute(
        "INSERT OR REPLACE INTO kline_watch(chain,address,label,added_ts) VALUES(?,?,?,?)",
        (chain, address, label, int(time.time())),
    )
    con.commit()
    con.close()
    print(f"已添加 [{chain}] {address} ({label or '无标签'})")


def remove_token(chain, address):
    con = db.connect()
    con.execute("DELETE FROM kline_watch WHERE chain=? AND address=?", (chain, address))
    con.commit()
    con.close()
    print(f"已移除 [{chain}] {address}")


def list_tokens():
    con = db.connect()
    rows = con.execute("SELECT chain, address, label, added_ts FROM kline_watch ORDER BY added_ts").fetchall()
    for r in rows:
        print(f"  [{r['chain']}] {r['address']}  {r['label'] or ''}")
    con.close()