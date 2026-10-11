"""全市场 Token 采集器（多链）。

由 launchd 周期触发，每次 `python3 market_run.py once` 只跑一轮后退出。
launchd 每 5 分钟重新启动一次；崩溃由 launchd 兜底，不会出现"幽灵进程"。

每轮按链顺序：
  1. GMGN trending 拉榜单（price / vol24h / liq / mcap / holders / 24h 涨幅 / logo）
  2. 写 tokens + token_snapshot（当前市场数据）
  3. 每个币同步保存一次当前价到 hourly_price（5 分钟桶）
  4. 每个币首次回填 1h kline（最近 BACKFILL_DAYS 天，锚定价用）
  5. 每个币当日 UTC 日 K 只在缺当天数据时拉一次（连涨天数用）

文件锁保证两次运行重叠时直接退出，避免双写。
"""
import fcntl
import json
import os
import subprocess
import sys
import time

import market_db as db
from market_chains import MARKET_CHAINS


GMGN_CLI = os.environ.get("GMGN_CLI", "gmgn-cli")
CHAINS = MARKET_CHAINS
TOP_N = int(os.environ.get("MARKET_TOP_N", "100"))
BACKFILL_DAYS = int(os.environ.get("MARKET_BACKFILL_DAYS", "14"))

# 价格点桶大小（秒）。5 分钟桶：N×24h Change 的锚定价最迟 5 分钟前。
PRICE_BUCKET = int(os.environ.get("MARKET_PRICE_BUCKET", "300"))

# 基础币种子：不依赖 trending 榜单（SOL 本体永远不会进 meme 榜），
# 每轮保证 tokens 行存在且当日日 K 已抓。不写 token_snapshot，故不会混入市场榜。
SEED_TOKENS = {
    "sol": [("So11111111111111111111111111111111111111112", "SOL", "Wrapped SOL")],
}

LOCK_PATH = os.environ.get(
    "MARKET_LOCK",
    os.path.join(os.path.dirname(__file__), "market_collector.lock"),
)


class LockBusy(Exception):
    """已经有 collector 在跑，直接退出。"""


def acquire_lock():
    """非阻塞文件锁。占用则抛 LockBusy，launchd 下一个周期再试。"""
    fd = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fd.close()
        raise LockBusy(LOCK_PATH)
    fd.write(str(os.getpid()))
    fd.flush()
    return fd


def release_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        fd.close()


def gmgn(args, timeout=60):
    """发一次 GMGN CLI。冷却期内直接拒绝。429 / RATE_LIMIT_* 武装全局冷却。"""
    import market_sched as sched
    sched.guard_or_raise()
    cmd = [GMGN_CLI] + args + ["--raw"]
    import history_api_audit as audit
    ident,route=audit.start(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        audit.event(ident,route,'transport_error')
        raise
    if r.returncode != 0:
        audit.event(ident,route,'provider_error')
        msg = r.stderr.strip() or r.stdout.strip() or f"exit {r.returncode}"
        if sched.observe_error(msg):
            raise sched.RateLimited(msg)
        raise RuntimeError(msg)
    try:
        payload=json.loads(r.stdout)
    except ValueError:
        audit.event(ident,route,'malformed_response')
        raise
    audit.event(ident,route,'success')
    return payload


NET_ERR_HINTS = ("fetch failed", "socket", "tls", "econnreset", "etimedout", "other side closed", "network")


def fetch_trending(chain, limit=TOP_N, attempts=3):
    """榜单是发现源之一。网络类错误重试；429 和其它 4xx 不重试，限流进入全局冷却。"""
    import market_sched as sched
    args = ["market", "trending", "--chain", chain, "--interval", "24h", "--limit", str(limit)]
    for i in range(attempts):
        try:
            data = gmgn(args)
            return (data.get("data") or {}).get("rank", [])
        except sched.RateLimited:
            raise
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            msg = str(e).lower()
            if i == attempts - 1 or not (isinstance(e, subprocess.TimeoutExpired) or any(h in msg for h in NET_ERR_HINTS)):
                raise
            print(f"  榜单网络错误，{2 * (i + 1)}s 后重试 ({i + 1}/{attempts - 1}): {str(e)[:80]}", flush=True)
            time.sleep(2 * (i + 1))


def fetch_kline(chain, address, resolution, frm, to):
    return gmgn([
        "market", "kline", "--chain", chain, "--address", address,
        "--resolution", resolution, "--from", str(frm), "--to", str(to),
    ]).get("list", [])


def to_seconds(t):
    return db.unix_ts(t)


def today_utc_start(now):
    return now - now % 86400


def upsert_daily_kline(con, chain, address, now):
    """拉最近 100 天日 K。只有解析成功且至少写入一根 token_candle 才盖回填章。

    空响应、非法行、请求失败都不算完成。请求失败由调用方安排重试。
    """
    import market_research as research
    import history_growth as growth
    growth.ensure(con)
    start=now-research.KLINE_FETCH_WINDOW_SEC
    birth=con.execute('SELECT token_created_at FROM token_registry WHERE chain=? AND address=?',(chain,address)).fetchone()
    created=birth[0] if birth else None
    before=growth.H.valid_closes(growth.H.read_bars(con,chain,address,start,now),now,created)
    end=now-now%growth.DAY
    gaps=growth.H.missing_ranges(before,end-8*growth.DAY,end)
    cur=con.execute('INSERT INTO history_incremental_requests(chain,address,start,end,attempted_at) VALUES(?,?,?,?,?)',
      (chain,address,gaps[0][0] if gaps else end,gaps[-1][1] if gaps else end,now))
    request_id=cur.lastrowid
    con.execute('UPDATE history_incremental_requests SET target_gaps_json=? WHERE id=?',(json.dumps(gaps),request_id))
    con.commit()  # Persist request cost before I/O, including crashes and failures.
    try:
        rows = fetch_kline(chain, address, "1d", start, now)
        fetched=int(time.time())
        parsed_ok=isinstance(rows,list)
        raw=rows if parsed_ok else []
        accepted=growth.validated_incremental(raw,chain,address,created,start,end,fetched)
        con.execute('UPDATE history_incremental_requests SET response_json=?,fetched_at=? WHERE id=?',(json.dumps(raw),fetched,request_id))
        con.commit()
        written=research.commit_kline_fetch(con,chain,address,accepted,fetched,parsed_ok)
        after=growth.H.valid_closes(growth.H.read_bars(con,chain,address,start,end),fetched,created)
        added=set(after)-set(before)
        growth.record_prices(con,chain,address,added,fetched)
        growth.record_provenance(con,chain,address,[{'ts':d} for d in added],'incremental',request_id,fetched)
        old=growth.H.return_days(before,end-8*growth.DAY,end)
        new=growth.H.return_days(after,end-8*growth.DAY,end)
        dates=growth.returned_dates(raw)
        hits=sum(any(a<=d<b for a,b in gaps) for d in dates)
        con.execute('UPDATE history_incremental_requests SET outcome=?,inserted=?,new_returns=?,new_any=?,new_full=?,rejected=?,returned_dates_json=?,target_hits=? WHERE id=?',
          ('success' if added else 'no_new_data',len(added),len(set(new)-set(old)),int(not old and bool(new)),int(len(old)<7 and len(new)==7),len(raw)-len(accepted),json.dumps(dates),hits,request_id))
        return written
    except Exception as exc:
        con.execute("UPDATE history_incremental_requests SET outcome='failed',error=? WHERE id=?",(type(exc).__name__+': '+str(exc)[:300],request_id))
        con.commit()
        raise


def ensure_seed_tokens(con, chain, now, have_today):
    """保证基础币种子（如 SOL 本体）存在且日 K 已抓，独立于 trending 榜单。"""
    for address, symbol, name in SEED_TOKENS.get(chain, []):
        con.execute(
            "INSERT OR IGNORE INTO tokens(chain,address,symbol,name,first_seen_at) VALUES(?,?,?,?,?)",
            (chain, address, symbol, name, int(now)),
        )
        if address not in have_today:
            upsert_daily_kline(con, chain, address, now)
            have_today.add(address)
            print(f"  种子币 {symbol} 日 K 已更新", flush=True)


def bucket_floor(ts):
    return ts - ts % PRICE_BUCKET


def collect_chain(con, chain, now, backfill):
    print(f"[{time.strftime('%H:%M:%S')}] === {chain} Top {TOP_N} ===", flush=True)
    items = fetch_trending(chain)
    print(f"  获得 {len(items)} 个", flush=True)
    stats = {"got": 0, "errors": 0, "snapshot_ts": now}
    price_buckets_written = 0
    today = today_utc_start(now)

    # 当日已抓过日 K 的地址 → 跳过 kline API 调用
    have_today = {
        row["address"]
        for row in con.execute(
            "SELECT address FROM daily_kline WHERE chain=? AND ts=?",
            (chain, today),
        ).fetchall()
    }
    if have_today:
        print(f"  当日日 K 已抓过 {len(have_today)} 个，跳过", flush=True)

    # 基础币种子（SOL 本体等），不依赖 trending 是否返回
    ensure_seed_tokens(con, chain, now, have_today)
    con.commit()

    for i, it in enumerate(items, 1):
        address = it.get("address")
        if not address:
            continue
        try:
            token_created, pair_created = db.rank_times(it)
            db.upsert_token(
                con, chain, address, it.get("symbol"), it.get("name"),
                it.get("logo") or None, token_created, pair_created, now,
            )
            con.execute(
                "INSERT OR REPLACE INTO token_snapshot"
                "(chain,address,ts,price,pc_24h,volume_24h,liquidity,market_cap,holders) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (chain, address, now,
                 str(it.get("price", "")), str(it.get("price_change_percent", "")),  # 已是百分数：-12.3 = -12.3%
                 str(it.get("volume", "")), str(it.get("liquidity", "")),
                 str(it.get("market_cap", "")), it.get("holder_count")),
            )

            # 当前价 → 5 分钟桶，作为 N×24h Change 的锚定点
            price = it.get("price")
            if price is not None:
                cur = con.execute(
                    "INSERT OR REPLACE INTO hourly_price(chain,address,ts,price) VALUES(?,?,?,?)",
                    (chain, address, bucket_floor(now), str(price)),
                )
                if cur.rowcount > 0:
                    price_buckets_written += 1

            # 当日日 K：今天缺才拉
            if address not in have_today:
                upsert_daily_kline(con, chain, address, now)
                have_today.add(address)

            # 首次回填：仅首次，回填小时 K 线
            if backfill:
                done_key = f"backfill_1h_{chain}_{address}"
                if not db.meta_get(con, done_key):
                    n = backfill_1h(con, chain, address, now)
                    db.meta_set(con, done_key, "1")
                    if n and (i <= 10 or i % 25 == 0):
                        print(f"    [{i}/{len(items)}] {it.get('symbol') or address[:10]} +{n}h", flush=True)
            con.commit()
            stats["got"] += 1
        except Exception as e:
            stats["errors"] += 1
            if i <= 3 or i % 25 == 0:
                print(f"    [{i}/{len(items)}] {it.get('symbol') or address[:10]} 错误: {str(e)[:80]}", flush=True)
    stats["price_buckets_written"] = price_buckets_written
    print(f"  {chain} 完成 {stats['got']}/{len(items)}，错误 {stats['errors']}，新价格点 {price_buckets_written}", flush=True)
    return stats


def backfill_1h(con, chain, address, now):
    """首次回填：用 1h K 线填充过去 BACKFILL_DAYS 天的小时桶。"""
    total = 0
    end = now
    pages = (BACKFILL_DAYS + 3) // 4
    for _ in range(pages):
        frm = end - 4 * 86400
        try:
            rows = fetch_kline(chain, address, "1h", frm, end)
        except Exception:
            break
        if not rows:
            break
        for r in rows:
            t = to_seconds(r["time"])
            t = t - t % 3600  # 历史数据仍是整点小时
            close = r.get("close")
            if close is None:
                continue
            con.execute(
                "INSERT OR IGNORE INTO hourly_price(chain,address,ts,price) VALUES(?,?,?,?)",
                (chain, address, t, str(close)),
            )
            total += 1
        end = frm
    return total


def run_loop():
    """常驻分速循环。文件锁由本函数持有到进程退出。"""
    try:
        lock_fd = acquire_lock()
    except LockBusy:
        print(f"[{time.strftime('%H:%M:%S')}] 已有 collector 在跑，20s 后再让 launchd 拉起", flush=True)
        time.sleep(20)
        return {"skipped": True, "reason": "lock_busy"}
    try:
        import market_lanes
        market_lanes.run_loop()
    finally:
        release_lock(lock_fd)


def run_once(backfill=True):
    try:
        lock_fd = acquire_lock()
    except LockBusy:
        print(f"[{time.strftime('%H:%M:%S')}] 已有 collector 在跑，退出", flush=True)
        return {"skipped": True, "reason": "lock_busy"}

    try:
        import market_lanes
        # 回填小时 K 不再塞进这一轮：它会按币打满 GMGN，并把整表拖回分钟级。
        # 历史锚点仍留在 hourly_price；新价格由 gmgn 车道按桶写入。
        _ = backfill
        log = market_lanes.run_pass()
        con = db.connect()
        db.meta_set(con, "last_run_start", str(int(time.time())))
        db.meta_set(con, "last_run", json.dumps(log, ensure_ascii=False))
        con.commit()
        con.close()
        return log
    finally:
        release_lock(lock_fd)


if __name__ == "__main__":
    out = run_once()
    print(json.dumps(out, ensure_ascii=False, default=str))
    sys.exit(0)
