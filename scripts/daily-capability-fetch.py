#!/usr/bin/env python3
"""每日钱包 / 资金能力审计的最小 raw 请求。复用 v1-verify-fetch.py 的共享冷却保护。

只请求 5 次：token info ×2、token traders ×1、token holders ×1、track smartmoney ×1。
串行；每次请求前从库里重新加载共享冷却并检查生产车道；遇到任何限流立即停止；已有文件跳过。
"""
import importlib.util
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("v1_fetch", ROOT / "scripts" / "v1-verify-fetch.py")
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)  # 设置 sched.db = 只写 market_meta 的连接

OUT = ROOT / "docs" / "gmgn-audit" / "raw" / "daily"
SOL_TOKEN = "GAwhcphCqCv5bKHmCiN4VDdNWfbXJL4npmkc8L3Q9S9H"
ETH_TOKEN = "0x56072c95faa701256059aa122697b133aded9279"
PLAN = [
    ("sol-token-info", ["token", "info", "--chain", "sol", "--address", SOL_TOKEN]),
    ("eth-token-info", ["token", "info", "--chain", "eth", "--address", ETH_TOKEN]),
    ("sol-token-traders", ["token", "traders", "--chain", "sol", "--address", SOL_TOKEN, "--limit", "100"]),
    ("sol-token-holders", ["token", "holders", "--chain", "sol", "--address", SOL_TOKEN, "--limit", "100"]),
    ("sol-track-smartmoney", ["track", "smartmoney", "--chain", "sol", "--limit", "200"]),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log_path = OUT / "_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {"requests": []}
    last = 0.0
    for name, args in PLAN:
        target = OUT / f"{name}.json"
        if target.exists():
            print(f"skip {name}", flush=True)
            continue
        wait = v1.SPACING_SEC - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        reason = v1.shared_block_reason(time.time())
        if reason:
            print(f"STOP before {name}: {reason}", flush=True)
            break
        started = time.time()
        entry = {"name": name, "args": args, "fetched_at": int(started), "via": "market_collect.gmgn"}
        try:
            data = v1.M.gmgn(args, timeout=60)
        except Exception as e:
            entry.update(rc="rate_limited" if isinstance(e, v1.sched.RateLimited) else "error", error=str(e)[:300])
            log["requests"].append(entry)
            log_path.write_text(json.dumps(log, indent=1))
            print(f"STOP {name}: {str(e)[:160]}", flush=True)
            break
        last = time.time()
        target.write_text(json.dumps(data))
        entry.update(rc=0, ms=int((last - started) * 1000))
        log["requests"].append(entry)
        log_path.write_text(json.dumps(log, indent=1))
        print(f"ok {name} {entry['ms']}ms", flush=True)


if __name__ == "__main__":
    sys.exit(main())
