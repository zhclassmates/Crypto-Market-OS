#!/usr/bin/env python3
"""六个字段的语义探针：buy_volume / sell_volume / unique_swap_traders / new_swap_traders / liquidity / holders。

GMGN：只发 6 次（token info ×4、token pool ×2），全部经 market_collect.gmgn()，复用
v1-verify-fetch.py 的共享冷却与生产车道静默检查；串行 ≥20s；任何限流立即停止；已有文件跳过。
每次 GMGN 成功后，立刻抓同一 token 的独立数据（GeckoTerminal pools、Blockscout token），
让两边时间尽量接近。独立数据源不是 GMGN，不受 GMGN 限流约束。
"""
import importlib.util
import json
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("v1_fetch", ROOT / "scripts" / "v1-verify-fetch.py")
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)

OUT = ROOT / "docs" / "gmgn-audit" / "raw" / "probe"
TOKENS = {
    "eth-wildebeest": ("eth", "0x57737ded3870e43fed7d80d31e0ced3d5fb0cccc"),
    "eth-sky": ("eth", "0x56072c95faa701256059aa122697b133aded9279"),
    "sol-www": ("sol", "GAwhcphCqCv5bKHmCiN4VDdNWfbXJL4npmkc8L3Q9S9H"),
    "base-toshi": ("base", "0xac1bd2486aaf3b5c0fc3fd868558b082a531b2b4"),
}
PLAN = [
    ("eth-wildebeest", "info"), ("eth-wildebeest", "pool"),
    ("sol-www", "info"), ("sol-www", "pool"),
    ("eth-sky", "info"), ("base-toshi", "info"),
]
GT_NET = {"eth": "eth", "sol": "solana", "base": "base"}
BLOCKSCOUT = {"eth": "https://eth.blockscout.com", "base": "https://base.blockscout.com"}


def http_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "field-probe"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def independent(chain, address):
    out = {"fetched_at": int(time.time())}
    try:
        out["geckoterminal_pools"] = http_json(
            f"https://api.geckoterminal.com/api/v2/networks/{GT_NET[chain]}/tokens/{address}/pools?page=1"
        )
    except Exception as e:  # 独立源失败只记录，不影响 GMGN 侧
        out["geckoterminal_error"] = str(e)[:200]
    if chain in BLOCKSCOUT:
        try:
            out["blockscout_token"] = http_json(f"{BLOCKSCOUT[chain]}/api/v2/tokens/{address}")
        except Exception as e:
            out["blockscout_error"] = str(e)[:200]
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log_path = OUT / "_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {"requests": []}
    last = 0.0
    for name, kind in PLAN:
        chain, address = TOKENS[name]
        target = OUT / f"{name}-{kind}.json"
        if target.exists():
            print(f"skip {target.name}", flush=True)
            continue
        wait = v1.SPACING_SEC - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        reason = v1.shared_block_reason(time.time())
        if reason:
            print(f"STOP before {target.name}: {reason}", flush=True)
            break
        args = ["token", kind, "--chain", chain, "--address", address]
        started = time.time()
        entry = {"name": target.stem, "args": args, "fetched_at": int(started), "via": "market_collect.gmgn"}
        try:
            data = v1.M.gmgn(args, timeout=60)
        except Exception as e:
            entry.update(rc="rate_limited" if isinstance(e, v1.sched.RateLimited) else "error", error=str(e)[:300])
            log["requests"].append(entry)
            log_path.write_text(json.dumps(log, indent=1))
            print(f"STOP {target.name}: {str(e)[:160]}", flush=True)
            break
        last = time.time()
        target.write_text(json.dumps(data))
        entry.update(rc=0, ms=int((last - started) * 1000))
        ind_path = OUT / f"{name}-{kind}-independent.json"
        ind_path.write_text(json.dumps(independent(chain, address)))
        entry["independent"] = ind_path.name
        log["requests"].append(entry)
        log_path.write_text(json.dumps(log, indent=1))
        print(f"ok {target.name} {entry['ms']}ms", flush=True)


if __name__ == "__main__":
    sys.exit(main())
