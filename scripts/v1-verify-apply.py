#!/usr/bin/env python3
"""V1 字段验证：把 docs/gmgn-audit/raw/v1 里已保存的真实 raw 走一遍 collector 代码，写入生产库的副本，
逐字段核对 raw → DB。不发任何 GMGN 请求，不写生产库。

副本中会删除"最早一次抓取所在 5 分钟桶"及之后的 discovery_event，避免生产 collector 同桶事件
（旧代码、不带 V1 元数据）因为去重键冲突把验证写入吞掉。这只发生在副本里。
"""
import argparse
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rh_v2"))

import market_collect as M  # noqa: E402
import market_db as db  # noqa: E402
import market_lanes as lanes  # noqa: E402
import market_research as R  # noqa: E402

RAW = ROOT / "docs" / "gmgn-audit" / "raw" / "v1"

TH = {  # Trending / Hot：DB 列 → raw key
    "swaps": "swaps", "buys_24h": "buys", "sells_24h": "sells",
    "pc_1h": "price_change_percent1h", "is_wash_trading": "is_wash_trading", "volume_24h": "volume",
}
TR = {
    "swaps": "swaps_24h", "buys_24h": "buys_24h", "sells_24h": "sells_24h",
    "is_wash_trading": "is_wash_trading", "volume_24h": "volume_24h",
}
SEC = {
    "security_is_honeypot": "is_honeypot", "security_renounced_mint": "renounced_mint",
    "security_renounced_freeze_account": "renounced_freeze_account", "security_sell_tax": "sell_tax",
}
EVENT_KEYS = {
    "trending": ("volume", "swaps", "buys", "sells", "price_change_percent1h"),
    "hot": ("volume", "swaps", "buys", "sells", "price_change_percent1h"),
    "trenches": ("volume_24h", "swaps_24h", "buys_24h", "sells_24h"),
}


def expected(col, value):
    if value is None:
        return None
    if col in ("swaps", "buys_24h", "sells_24h"):
        return int(value)
    if col in ("is_wash_trading", "security_is_honeypot", "security_renounced_mint", "security_renounced_freeze_account"):
        return int(value) if isinstance(value, bool) else None
    return str(value)


class Stat:
    def __init__(self):
        self.d = {}

    def add(self, key, col, raw_present, raw_value, ok, sample=None):
        s = self.d.setdefault(key, {}).setdefault(col, {
            "rows": 0, "raw_present": 0, "raw_null": 0, "raw_zero": 0, "raw_true": 0,
            "raw_eq_db": 0, "mismatch": [],
        })
        s["rows"] += 1
        if raw_present:
            s["raw_present"] += 1
            if raw_value is None:
                s["raw_null"] += 1
            elif raw_value is True:
                s["raw_true"] += 1
            elif raw_value == 0 or raw_value is False or raw_value == "0":
                s["raw_zero"] += 1
            if ok:
                s["raw_eq_db"] += 1
            elif len(s["mismatch"]) < 3:
                s["mismatch"].append(sample)


def snapshot(con, chain, address):
    return con.execute("SELECT * FROM token_snapshot WHERE chain=? AND address=?", (chain, address)).fetchone()


def latest_events(con, chain, address, source):
    return con.execute(
        "SELECT * FROM discovery_event WHERE chain=? AND address=? AND source=? ORDER BY id DESC",
        (chain, address, source),
    ).fetchall()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="副本路径（会被覆盖）")
    args = parser.parse_args()
    log = json.loads((RAW / "_log.json").read_text())
    fetched = {}
    for r in log["requests"]:
        if r.get("rc") == 0:
            fetched[(r["chain"], r["endpoint"])] = r["fetched_at"]
    files = sorted(p for p in RAW.glob("*-*.json") if p.stem.split("-", 1)[1] in ("trending", "hot", "trenches", "signal", "security"))
    runs = []
    for p in files:
        chain, endpoint = p.stem.split("-", 1)
        if (chain, endpoint) not in fetched:
            raise SystemExit(f"{p.name} has no successful request entry in _log.json")
        runs.append((fetched[(chain, endpoint)], chain, endpoint, json.loads(p.read_text())))
    runs.sort()

    dst_path = pathlib.Path(args.db)
    if dst_path.exists():
        dst_path.unlink()
    src = sqlite3.connect((ROOT / "rh_v2" / "market.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(dst_path)
    src.backup(dst)
    src.close()
    dst.close()
    con = db.connect(str(dst_path))
    first_bucket = R.time_bucket(min(r[0] for r in runs))
    removed = con.execute("DELETE FROM discovery_event WHERE time_bucket >= ?", (first_bucket,)).rowcount
    con.commit()

    stat = Stat()
    touched = set()
    for now, chain, endpoint, raw in runs:
        key = f"{chain}/{endpoint}"
        if endpoint in ("trending", "hot"):
            M.gmgn = lambda _args, timeout=60, _raw=raw: _raw
            if endpoint == "trending":
                items = M.fetch_trending(chain)
                lanes.write_gmgn_rows(con, chain, items, now, source="trending", source_variant="24h")
            else:
                items = lanes.fetch_hot(chain)
                lanes.apply_hot_items(con, chain, items, now)
            mapping, last = TH, {it["address"]: it for it in items if it.get("address")}
        elif endpoint == "trenches":
            lanes.apply_trench_payload(con, chain, raw, now)
            items = [row for _variant, row in R.parse_trench_items(raw)]
            mapping, last = TR, {it["address"]: it for it in items if it.get("address")}
        elif endpoint == "signal":
            lanes.apply_signal_items(con, chain, raw, now)
            mapping, last = None, {}
            # 同一 (address, signal_type) 在一个 5 分钟桶里只保留一条事件（去重键）。
            # GMGN 返回顺序是最新在前，所以落库的是第一次出现的那条；其余计为 collapsed。
            seen_pairs = set()
            for item in raw if isinstance(raw, list) else []:
                address = item.get("token_address")
                if not address:
                    continue
                pair = (address, str(item.get("signal_type")))
                if pair in seen_pairs:
                    stat.add(key, "event.collapsed_same_type_in_bucket", True, None, True)
                    continue
                seen_pairs.add(pair)
                touched.add(f"{chain}:{address}")
                ev = con.execute(
                    "SELECT metadata_json FROM discovery_event WHERE chain=? AND address=? AND source='signal' "
                    "AND source_variant=? ORDER BY id DESC LIMIT 1",
                    (chain, address, str(item.get("signal_type"))),
                ).fetchone()
                meta = json.loads(ev["metadata_json"]) if ev else {}
                for k in ("trigger_at", "trigger_mc"):
                    stat.add(key, f"event.{k}", k in item, item.get(k), ev is not None and meta.get(k) == item.get(k),
                             (address[:10], item.get(k), meta.get(k)))
        elif endpoint == "security":
            address = log["security_addresses"][chain]
            lanes.write_security_snapshot(con, chain, address, raw, now)
            touched.add(f"{chain}:{address}")
            row = snapshot(con, chain, address)
            for col, rk in SEC.items():
                stat.add(key, col, rk in raw, raw.get(rk), row[col] == expected(col, raw.get(rk)),
                         (address[:10], raw.get(rk), row[col]))
            mapping, last = None, {}
        con.commit()
        if mapping:
            for address, it in last.items():
                touched.add(f"{chain}:{address}")
                row = snapshot(con, chain, address)
                for col, rk in mapping.items():
                    if rk not in it:
                        stat.add(key, col, False, None, False)
                        continue
                    ok = row is not None and row[col] == expected(col, it[rk])
                    stat.add(key, col, True, it[rk], ok, (address[:10], it[rk], None if row is None else row[col]))
                    src_col = {"volume_24h": "volume_24h_source", "pc_1h": "pc_1h_source"}.get(col, col + "_source")
                    if col == "swaps":
                        src_col = "swaps_source"
                    if row is not None and src_col in row.keys():
                        stat.add(key, f"{col}.source", True, None, row[src_col] == endpoint)
            evs = {address: latest_events(con, chain, address, endpoint) for address in last}
            for address, it in last.items():
                ev = evs[address][0] if evs[address] else None
                meta = json.loads(ev["metadata_json"]) if ev else {}
                present = [k for k in EVENT_KEYS[endpoint] if k in it and it[k] is not None]
                stat.add(key, "event.activity_meta", True, None,
                         ev is not None and all(meta.get(k) == it[k] for k in present), address[:10])
                if endpoint in ("trending", "hot"):
                    stat.add(key, "event.rank", "rank" in it, it.get("rank"),
                             ev is not None and ev["rank"] == it.get("rank"), (address[:10], it.get("rank"), ev and ev["rank"]))

    result = {
        "copy": str(dst_path),
        "events_removed_from_copy": removed,
        "runs": [{"chain": c, "endpoint": e, "fetched_at": n} for n, c, e, _ in runs],
        "integrity": con.execute("PRAGMA integrity_check").fetchone()[0],
        "checks": stat.d,
    }
    con.close()
    (RAW / "verify_db.json").write_text(json.dumps(result, indent=1, default=str))
    (RAW / "verify_keys.json").write_text(json.dumps(sorted(touched)))
    for k, cols in stat.d.items():
        bad = {c: v for c, v in cols.items() if v["raw_eq_db"] != v["raw_present"]}
        print(k, "rows", max(v["rows"] for v in cols.values()), "ALL OK" if not bad else f"MISMATCH {list(bad)}")
    print("touched tokens", len(touched))


if __name__ == "__main__":
    main()
