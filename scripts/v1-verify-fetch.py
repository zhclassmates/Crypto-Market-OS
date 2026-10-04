#!/usr/bin/env python3
"""V1 字段验证用的最小 GMGN 抓取。只走生产同一套 shared cooldown，不裸调 gmgn-cli。

规则：
- 每次请求都经过 market_collect.gmgn()：guard_or_raise() 拦冷却，429 时 observe_error()
  把全局冷却写入 market_meta，生产 collector 与本脚本共享。
- market_sched 的冷却状态是进程内缓存，只在首次加载时读库；本脚本每次请求前都从库里重新加载，
  这样能看到生产 collector 新武装的冷却。
- 生产任一 GMGN 车道在最近 LANE_QUIET_SEC 秒内 rate_limited，也视为冷却，不发请求。
- 串行执行，请求之间至少间隔 SPACING_SEC 秒。遇到任何限流立即停止，不重试。
- 已存在的 raw 文件直接跳过，成功的 payload 立即落盘。
"""
import argparse
import json
import pathlib
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rh_v2"))

import market_collect as M  # noqa: E402
import market_db as db  # noqa: E402
import market_sched as sched  # noqa: E402

class _MetaOnlyDb:
    """market_sched 写共享冷却时用的连接：只打开生产库写 market_meta，不跑 SCHEMA / migrate。

    market_db.connect() 会执行 migrate()；未部署的新列不能因为一次 429 被写进生产库。
    """

    def __getattr__(self, name):
        return getattr(db, name)

    @staticmethod
    def connect(path=None):
        con = sqlite3.connect(path or db.DB_PATH, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=10000")
        return con


sched.db = _MetaOnlyDb()

SPACING_SEC = 20
LANE_QUIET_SEC = 120
OUT = ROOT / "docs" / "gmgn-audit" / "raw" / "v1"
TRENCH_TYPES = ("new_creation", "near_completion", "completed")


def plan(security_addresses):
    """V1 缺失证据的最小请求集。Trending SOL 已有 raw，不在这里。"""
    out = [("sol", "hot", ["market", "hot-searches", "--chain", "sol", "--limit", "100"])]
    for chain in ("sol", "robinhood", "base", "eth"):
        out.append((chain, "trenches", ["market", "trenches", "--chain", chain, "--type", *TRENCH_TYPES, "--limit", "30"]))
    for chain in ("sol", "robinhood"):
        out.append((chain, "signal", ["market", "signal", "--chain", chain]))
    # pc_1h 只来自 Trending / Hot；补 RH / BASE / ETH 各一次 Trending，覆盖四链。
    for chain in ("robinhood", "base", "eth"):
        out.append((chain, "trending", ["market", "trending", "--chain", chain, "--interval", "24h", "--limit", "100"]))
    for chain in ("sol", "robinhood", "base", "eth"):
        out.append((chain, "security", ["token", "security", "--chain", chain, "--address", security_addresses[chain]]))
    return out


def ro():
    con = sqlite3.connect((ROOT / "rh_v2" / "market.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def shared_block_reason(now):
    """从库里重新加载共享冷却，并检查生产车道最近是否被限流。"""
    con = ro()
    try:
        sched.load_cooldown(con)
        if sched.in_cooldown(now):
            return f"GLOBAL_GMGN_COOLDOWN until={sched.cooldown_until()}"
        row = con.execute(
            "SELECT source, chain, last_attempt FROM source_health "
            "WHERE source LIKE 'gmgn%' AND run_state='rate_limited' AND last_attempt >= ? "
            "ORDER BY last_attempt DESC LIMIT 1",
            (int(now) - LANE_QUIET_SEC,),
        ).fetchone()
        if row:
            return f"production lane {row['source']}/{row['chain']} rate_limited at {row['last_attempt']}"
        return None
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    log_path = OUT / "_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {"requests": []}
    security_addresses = log["security_addresses"]
    last_request = 0.0
    for chain, endpoint, cli_args in plan(security_addresses):
        target = OUT / f"{chain}-{endpoint}.json"
        if target.exists():
            print(f"skip {chain}/{endpoint}: raw exists", flush=True)
            continue
        wait = SPACING_SEC - (time.time() - last_request)
        if wait > 0:
            time.sleep(wait)
        reason = shared_block_reason(time.time())
        if reason:
            print(f"STOP before {chain}/{endpoint}: {reason}", flush=True)
            break
        if args.dry_run:
            print(f"would request {chain}/{endpoint}", flush=True)
            last_request = time.time()
            continue
        started = time.time()
        entry = {"chain": chain, "endpoint": endpoint, "args": cli_args, "fetched_at": int(started), "via": "market_collect.gmgn"}
        try:
            data = M.gmgn(cli_args, timeout=60)
        except sched.RateLimited as e:
            entry.update(rc="rate_limited", error=str(e)[:300])
            log["requests"].append(entry)
            log_path.write_text(json.dumps(log, indent=1))
            print(f"STOP {chain}/{endpoint}: {str(e)[:160]}", flush=True)
            break
        except Exception as e:  # 非限流错误：记录并停止，避免盲目继续
            entry.update(rc="error", error=str(e)[:300])
            log["requests"].append(entry)
            log_path.write_text(json.dumps(log, indent=1))
            print(f"STOP {chain}/{endpoint}: error {str(e)[:160]}", flush=True)
            break
        last_request = time.time()
        target.write_text(json.dumps(data))
        entry.update(rc=0, ms=int((last_request - started) * 1000))
        log["requests"].append(entry)
        log_path.write_text(json.dumps(log, indent=1))
        print(f"ok {chain}/{endpoint} {entry['ms']}ms", flush=True)


if __name__ == "__main__":
    main()
