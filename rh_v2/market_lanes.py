"""分源采集。GMGN 仍是主写；Dex / 锚价 / Chainlink 只写自己的列。

GMGN CLI 串行，相邻请求至少间隔 1.05s。
Dex、Robinhood 锚价、Chainlink 在另一条线程，不占这 1 req/s。
"""
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import market_db as db
import market_health as H
from market_chains import DEXSCREENER_CHAINS, SIGNAL_CHAINS

GMGN_GAP = 1.05
TOP_N = int(os.environ.get("MARKET_TOP_N", "100"))
DIVERGE_RATIO = float(os.environ.get("MARKET_DIVERGE_RATIO", str(H.DIVERGE_RATIO)))
RH_RPC = os.environ.get("MARKET_RH_RPC", "https://rpc.mainnet.chain.robinhood.com")
FEED_URL = os.environ.get(
    "MARKET_CHAINLINK_FEEDS",
    "https://reference-data-directory.vercel.app/feeds-robinhood-mainnet.json",
)
DS_CHAIN = DEXSCREENER_CHAINS
ROUND_SELECTOR = "0xfeaf968c"

_asset_cache = {"at": 0.0, "by_addr": {}}
_px_cache = {}
_feed_cache = {"at": 0.0, "by_symbol": {}}
_pace_lock = threading.Lock()
_pace_next = 0.0


def _pace(gap=0.03):
    """全局间隔，把并发报价压在约 30 req/s，低于官方 60 req/s。"""
    global _pace_next
    with _pace_lock:
        now = time.time()
        wait = _pace_next - now
        if wait > 0:
            time.sleep(wait)
        _pace_next = time.time() + gap


def _gmgn_mod():
    import market_collect as M
    return M


def http_json(url, timeout=20, body=None):
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if data is not None else "GET",
        headers={
            "user-agent": "market-health/1.0",
            "accept": "application/json",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")[:180]
        raise RuntimeError(f"HTTP {e.code} {raw}") from None


def with_db(fn):
    with H.DB_LOCK:
        con = db.connect()
        try:
            out = fn(con)
            con.commit()
            return out
        finally:
            con.close()


def _finish(source, chain, ok, started, **kw):
    finished = time.time()

    def apply(con):
        H.record_result(con, source, chain, ok, started, finished, **kw)

    with_db(apply)
    flag = kw.get("run_state") or ("ok" if ok else "fail")
    err = kw.get("error") or ""
    print(
        f"[{time.strftime('%H:%M:%S')}] {source}:{chain} {flag} "
        f"rows={kw.get('rows_received', 0)} parsed={kw.get('rows_parsed', 0)} "
        f"written={kw.get('rows_written', 0)} new={kw.get('new_addresses', 0)} "
        f"events={kw.get('events_written', 0)} hot={kw.get('hot_changed', 0)} "
        f"{str(err)[:160]}",
        flush=True,
    )


def fetch_hot(chain):
    """热搜榜。--raw 是数组，tokens 在每个元素里。"""
    data = _gmgn_mod().gmgn(
        ["market", "hot-searches", "--chain", chain, "--limit", str(TOP_N)],
        timeout=45,
    )
    rows = []
    blocks = data if isinstance(data, list) else [data]
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if isinstance(block.get("tokens"), list):
            rows.extend(block["tokens"])
        elif isinstance(block.get("rank"), list):
            rows.extend(block["rank"])
    return rows


def _s(v):
    if v is None:
        return ""
    return str(v)


def _i(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None


def _text(v):
    return None if v is None else str(v)


def _real(v):
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n and n not in (float("inf"), float("-inf")) else None


def _present(item, dest, *keys):
    """返回第一个实际存在的 key；显式 null 与缺失严格分开。"""
    for key in keys:
        if key in item:
            return dest, item[key]
    return None


def snapshot_patch(source, item):
    """按 endpoint ownership 生成 token_snapshot patch。

    dict 中没有 key = endpoint 不负责/未返回；key 存在且值为 None = API
    明确 null；数值 0 是有效值。Signal 的 activity/price 不属于可用字段。
    """
    if not isinstance(item, dict):
        return {}
    specs = {
        "trending": (
            ("price", "price"), ("pc_24h", "price_change_percent"),
            ("volume_24h", "volume"), ("liquidity", "liquidity"),
            ("market_cap", "market_cap", "usd_market_cap"),
            ("holders", "holder_count"), ("swaps", "swaps"),
            ("buys_24h", "buys"), ("sells_24h", "sells"),
            ("pc_1h", "price_change_percent1h"), ("is_wash_trading", "is_wash_trading"),
            ("smart_degen_count", "smart_degen_count"), ("sniper_count", "sniper_count"),
            ("renowned_count", "renowned_count"), ("top10_holder_rate", "top_10_holder_rate"),
            ("rat_trader_rate", "rat_trader_amount_rate"), ("bundler_rate", "bundler_rate"),
        ),
        "hot": (
            ("price", "price"), ("pc_24h", "price_change_percent"),
            ("volume_24h", "volume"), ("liquidity", "liquidity"),
            ("market_cap", "market_cap", "usd_market_cap"),
            ("holders", "holder_count"), ("swaps", "swaps"),
            ("buys_24h", "buys"), ("sells_24h", "sells"),
            ("pc_1h", "price_change_percent1h"), ("is_wash_trading", "is_wash_trading"),
            ("smart_degen_count", "smart_degen_count"), ("sniper_count", "sniper_count"),
            ("renowned_count", "renowned_count"), ("top10_holder_rate", "top_10_holder_rate"),
            ("rat_trader_rate", "rat_trader_amount_rate"), ("bundler_rate", "bundler_rate"),
        ),
        "trenches": (
            ("price", "price"), ("volume_24h", "volume"),
            ("liquidity", "liquidity"), ("market_cap", "market_cap", "usd_market_cap"),
            ("holders", "holder_count"), ("swaps", "swaps"),
            ("buys_24h", "buys_24h"), ("sells_24h", "sells_24h"),
            ("is_wash_trading", "is_wash_trading"),
            ("smart_degen_count", "smart_degen_count"), ("sniper_count", "sniper_count"),
            ("renowned_count", "renowned_count"), ("top10_holder_rate", "top_10_holder_rate"),
            ("rat_trader_rate", "rat_trader_amount_rate"), ("bundler_rate", "bundler_rate"),
        ),
        "signal": (
            ("liquidity", "liquidity"), ("market_cap", "market_cap"),
            ("holders", "holder_count"), ("top10_holder_rate", "top_10_holder_rate"),
        ),
    }
    out = {}
    for spec in specs.get(source, ()):
        found = _present(item, spec[0], *spec[1:])
        if found is not None:
            out[found[0]] = found[1]
    return out


_SNAPSHOT_COLUMNS = {
    "price": ("price", "price_source", "price_updated_at", "text"),
    "pc_24h": ("pc_24h", "pc_24h_source", "pc_24h_updated_at", "text"),
    "volume_24h": ("volume_24h", "volume_24h_source", "volume_24h_updated_at", "text"),
    "liquidity": ("liquidity", "liquidity_source", "liquidity_updated_at", "text"),
    "market_cap": ("market_cap", "market_cap_source", "market_cap_updated_at", "text"),
    "holders": ("holders", "holders_source", "holders_updated_at", "int"),
    "swaps": ("swaps", "swaps_source", "swaps_updated_at", "int"),
    # buys/sells 是 24h 交易笔数，不是独立买家/卖家人数。
    "buys_24h": ("buys_24h", "buys_24h_source", "buys_24h_updated_at", "int"),
    "sells_24h": ("sells_24h", "sells_24h_source", "sells_24h_updated_at", "int"),
    "pc_1h": ("pc_1h", "pc_1h_source", "pc_1h_updated_at", "text"),
    "is_wash_trading": ("is_wash_trading", "is_wash_trading_source", "is_wash_trading_updated_at", "bool"),
    "smart_degen_count": ("smart_degen_count", None, None, "int"),
    "sniper_count": ("sniper_count", None, None, "int"),
    "renowned_count": ("renowned_count", None, None, "int"),
    "top10_holder_rate": ("top10_holder_rate", None, None, "text"),
    "rat_trader_rate": ("rat_trader_rate", None, None, "text"),
    "bundler_rate": ("bundler_rate", None, None, "text"),
}


def _write_snapshot_patch(con, chain, address, now, source, patch, chg_p, chg_v, chg_l):
    con.execute(
        "INSERT OR IGNORE INTO token_snapshot(chain,address,ts) VALUES(?,?,?)",
        (chain, address, int(now)),
    )
    assignments = ["ts=?", "commit_ok=1", "chg_price=?", "chg_volume=?", "chg_liquidity=?"]
    values = [int(now), chg_p, chg_v, chg_l]
    for key, raw in patch.items():
        column, source_col, updated_col, kind = _SNAPSHOT_COLUMNS[key]
        if kind == "int":
            value = _i(raw)
        elif kind == "bool":
            value = _optional_bool(raw)
        else:
            value = _text(raw)
        assignments.append(f"{column}=?")
        values.append(value)
        if source_col:
            assignments.extend((f"{source_col}=?", f"{updated_col}=?"))
            values.extend((source, int(now)))
        if key == "liquidity":
            assignments.append("liquidity_num=?")
            values.append(_real(raw))
    values.extend((chain, address))
    con.execute(
        f"UPDATE token_snapshot SET {', '.join(assignments)} WHERE chain=? AND address=?",
        values,
    )


def write_gmgn_rows(con, chain, items, now, source="trending", source_variant="24h"):
    """同一事务写 discovery_event、token_registry 和 snapshot。

    新地址不会因为旧 snapshot 里没有而被丢掉。
    price_ds / anchor_* / oracle_* / dex_price 保持原值。
    """
    import market_research as R
    M = _gmgn_mod()
    now = int(now)
    stats = R.apply_source_items(con, chain, source, items, now, source_variant=source_variant)
    hot = cold = 0
    got = 0
    for it in items:
        address = it.get("address")
        if not address:
            continue
        old_tok = con.execute(
            "SELECT symbol, name, logo FROM tokens WHERE chain=? AND address=?",
            (chain, address),
        ).fetchone()
        old = con.execute(
            "SELECT price, volume_24h, liquidity, holders, smart_degen_count, sniper_count, "
            "renowned_count, top10_holder_rate, rat_trader_rate, bundler_rate "
            "FROM token_snapshot WHERE chain=? AND address=?",
            (chain, address),
        ).fetchone()
        patch = snapshot_patch(source, it)
        chg_p = 1 if "price" in patch and (old is None or H.num_changed(old["price"], patch["price"])) else 0
        chg_v = 1 if "volume_24h" in patch and (old is None or H.num_changed(old["volume_24h"], patch["volume_24h"])) else 0
        chg_l = 1 if "liquidity" in patch and (old is None or H.num_changed(old["liquidity"], patch["liquidity"])) else 0
        if chg_p or chg_v or chg_l:
            hot += 1
        cold_hit = old is None or any((
            "holders" in patch and old["holders"] != _i(patch["holders"]),
            "smart_degen_count" in patch and old["smart_degen_count"] != _i(patch["smart_degen_count"]),
            "sniper_count" in patch and old["sniper_count"] != _i(patch["sniper_count"]),
            "renowned_count" in patch and old["renowned_count"] != _i(patch["renowned_count"]),
            "top10_holder_rate" in patch and H.num_changed(old["top10_holder_rate"], patch["top10_holder_rate"]),
            "rat_trader_rate" in patch and H.num_changed(old["rat_trader_rate"], patch["rat_trader_rate"]),
            "bundler_rate" in patch and H.num_changed(old["bundler_rate"], patch["bundler_rate"]),
            old_tok is None or (old_tok["symbol"] or "") != (it.get("symbol") or ""),
            old_tok is None or (old_tok["name"] or "") != (it.get("name") or ""),
            old_tok is None or (old_tok["logo"] or "") != (it.get("logo") or ""),
        ))
        if cold_hit:
            cold += 1
        token_created, pair_created = db.rank_times(it)
        db.upsert_token(
            con, chain, address, it.get("symbol"), it.get("name"), it.get("logo") or None,
            token_created, pair_created, int(now),
        )
        _write_snapshot_patch(con, chain, address, now, source, patch, chg_p, chg_v, chg_l)
        if "price" in patch and patch["price"] is not None:
            con.execute(
                "INSERT OR REPLACE INTO hourly_price(chain,address,ts,price) VALUES(?,?,?,?)",
                (chain, address, M.bucket_floor(int(now)), str(patch["price"])),
            )
        R.refresh_metrics(con, chain, address, now)
        got += 1
    if got:
        db.meta_set(con, "last_market_update_" + chain, str(int(now)))
        db.meta_set(con, "last_price_update_" + chain, str(M.bucket_floor(int(now))))
    return got, hot, cold, stats


def _skip_if_cooling(source, chain, started):
    """冷却期内不发 GMGN。Dex / 锚价 / Chainlink 不走这里。"""
    import market_sched as sched
    if not sched.in_cooldown(time.time()):
        return False
    _finish(
        source, chain, False, started,
        error=f"GLOBAL_GMGN_COOLDOWN until={sched.cooldown_until()}",
        run_state="cooldown", request_ok=0, wrote_db=False,
    )
    return True


def _rate_limited(exc):
    import market_sched as sched
    return isinstance(exc, sched.RateLimited)


def _finish_discovery(source, chain, started, stats, hot=0, cold=0, request_ok=1):
    import market_sched as sched
    state = sched.discovery_run_state(
        stats.get("rows_received", 0), stats.get("rows_parsed", 0),
        stats.get("rows_written", 0), stats.get("events_written", 0),
    )
    _finish(
        source, chain, state == "healthy", started,
        rows_received=stats.get("rows_received", 0),
        rows_parsed=stats.get("rows_parsed", 0),
        rows_written=stats.get("rows_written", 0),
        new_addresses=stats.get("new_addresses", 0),
        events_written=stats.get("events_written", 0),
        hot_changed=hot, cold_changed=cold,
        source_timestamp_missing=True,
        wrote_db=state == "healthy",
        run_state=state, request_ok=request_ok,
        error=None if state == "healthy" else "discovery write failed / zero-write",
    )


def apply_hot_items(con, chain, items, now):
    """热搜是发现源。registry 里没有的地址也写入 event、registry 和 snapshot。

    显式 --limit 由 fetch_hot 传入。不传 --filter；relaxed/filter 未验证。
    """
    return write_gmgn_rows(con, chain, items, now, source="hot", source_variant="24h")


def apply_trench_payload(con, chain, data, now):
    """三类都写。响应键 near_completion，旧键 pump 也收。

    不传 --launchpad-platform。平台范围取决于 GMGN 服务端默认，未逐个验证。
    """
    import market_research as R
    items = []
    for variant, row in R.parse_trench_items(data):
        item = R.normalize_trench_row(row)
        item["_variant"] = variant
        if item.get("market_cap") is None and item.get("usd_market_cap") is not None:
            item["market_cap"] = item.get("usd_market_cap")
        items.append(item)
    return write_gmgn_rows(con, chain, items, now, source="trenches", source_variant="")


def apply_signal_items(con, chain, data, now):
    import market_research as R
    items = R.parse_signal_items(data)
    return write_gmgn_rows(con, chain, items, now, source="signal", source_variant="")


def job_gmgn(chain):
    """Trending 发现源，周期 300s。新地址写 event + registry + snapshot。"""
    started = time.time()
    if _skip_if_cooling("gmgn", chain, started):
        return
    try:
        items = _gmgn_mod().fetch_trending(chain, limit=TOP_N)
    except Exception as e:
        state = "rate_limited" if _rate_limited(e) else "failed"
        _finish("gmgn", chain, False, started, error=str(e), rows_received=0, run_state=state, request_ok=0)
        return
    now = int(time.time())

    def apply(con):
        return write_gmgn_rows(con, chain, items, now, source="trending", source_variant="24h")

    try:
        got, hot, cold, stats = with_db(apply)
    except Exception as e:
        _finish("gmgn", chain, False, started, error=str(e), rows_received=len(items), run_state="failed", request_ok=1)
        return
    _ = got
    _finish_discovery("gmgn", chain, started, stats, hot=hot, cold=cold, request_ok=1)


def job_gmgn_hot(chain):
    """热搜发现源。limit 显式等于 TOP_N。不传未验证的 --filter。"""
    started = time.time()
    if _skip_if_cooling("gmgn_hot", chain, started):
        return
    try:
        items = fetch_hot(chain)
    except Exception as e:
        state = "rate_limited" if _rate_limited(e) else "failed"
        _finish("gmgn_hot", chain, False, started, error=str(e), run_state=state, request_ok=0)
        return
    now = int(time.time())
    try:
        _got, hot, _cold, stats = with_db(lambda con: apply_hot_items(con, chain, items, now))
    except Exception as e:
        _finish("gmgn_hot", chain, False, started, error=str(e), rows_received=len(items), run_state="failed", request_ok=1)
        return
    _finish_discovery("gmgn_hot", chain, started, stats, hot=hot, request_ok=1)


def _count_list(data, key):
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return data[key]
    return []


# 显式请求三类。不传 --launchpad-platform：CLI 不带该字段，覆盖取决于服务端默认，未验证。
TRENCH_TYPES = ("new_creation", "near_completion", "completed")
# signal CLI 只对共享链配置中标记支持的链发请。


def job_new_pair(chain):
    """Trenches 发现源。type coverage = new_creation + near_completion + completed。"""
    started = time.time()
    if _skip_if_cooling("gmgn_new_pair", chain, started):
        return
    try:
        data = _gmgn_mod().gmgn(
            ["market", "trenches", "--chain", chain,
             "--type", *TRENCH_TYPES, "--limit", "30"],
            timeout=45,
        )
    except Exception as e:
        state = "rate_limited" if _rate_limited(e) else "failed"
        _finish("gmgn_new_pair", chain, False, started, error=str(e), run_state=state, request_ok=0)
        return
    now = int(time.time())
    try:
        _got, hot, _cold, stats = with_db(lambda con: apply_trench_payload(con, chain, data, now))
    except Exception as e:
        _finish("gmgn_new_pair", chain, False, started, error=str(e), run_state="failed", request_ok=1)
        return
    _finish_discovery("gmgn_new_pair", chain, started, stats, hot=hot, request_ok=1)


def job_signal(chain):
    """Signal 发现源。只对 CLI 实际支持的链发请求。"""
    started = time.time()
    if chain not in SIGNAL_CHAINS:
        _finish(
            "gmgn_signal", chain, False, started,
            error="signal unsupported on this chain",
            run_state="unsupported", request_ok=0,
        )
        return
    if _skip_if_cooling("gmgn_signal", chain, started):
        return
    try:
        data = _gmgn_mod().gmgn(["market", "signal", "--chain", chain], timeout=45)
    except Exception as e:
        state = "rate_limited" if _rate_limited(e) else "failed"
        _finish("gmgn_signal", chain, False, started, error=str(e), run_state=state, request_ok=0)
        return
    now = int(time.time())
    try:
        _got, hot, _cold, stats = with_db(lambda con: apply_signal_items(con, chain, data, now))
    except Exception as e:
        _finish("gmgn_signal", chain, False, started, error=str(e), run_state="failed", request_ok=1)
        return
    _finish_discovery("gmgn_signal", chain, started, stats, hot=hot, request_ok=1)


def _remember_seed(con, chain, now):
    """种子币进入 registry。不在这里打 K 线接口。"""
    import market_research as R
    M = _gmgn_mod()
    for address, symbol, name in M.SEED_TOKENS.get(chain, []):
        con.execute(
            "INSERT OR IGNORE INTO tokens(chain,address,symbol,name,first_seen_at) VALUES(?,?,?,?,?)",
            (chain, address, symbol, name, int(now)),
        )
        R.ingest_discovery(con, chain, address, "seed", int(now), symbol=symbol, name=name)


def job_kline(chain):
    """日 K 有保留名额。UTC 日切后先修昨日未 FINALIZED 的研究币，再补首次回填，再轮转。

    空响应、解析失败、请求失败都不盖 kline_backfilled_at。
    """
    started = time.time()
    if _skip_if_cooling("gmgn_kline", chain, started):
        return
    M = _gmgn_mod()
    import market_research as R
    now = int(time.time())
    growth_item = None

    def pick(con):
        nonlocal growth_item
        _remember_seed(con, chain, now)
        repair = R.pick_kline_repair(con, chain, now, R.KLINE_REPAIR_BATCH)
        if repair:
            return repair
        pending = con.execute(
            """SELECT address FROM token_registry
               WHERE chain=? AND first_liquidity_50k_at IS NOT NULL
                 AND kline_backfilled_at IS NULL
                 AND (kline_retry_after IS NULL OR kline_retry_after <= ?)
               ORDER BY first_liquidity_50k_at
               LIMIT 1""",
            (chain, now),
        ).fetchone()
        if pending:
            return [pending["address"]]
        today = M.today_utc_start(now)
        for address, _symbol, _name in M.SEED_TOKENS.get(chain, []):
            have = con.execute(
                "SELECT 1 FROM token_candle WHERE chain=? AND address=? AND candle_open_ts=?",
                (chain, address, today),
            ).fetchone()
            if not have:
                return [address]
        # Normal rotation remains independent of the idle supplementation budget.
        cursor = int(db.meta_get(con, "kline_cursor_" + chain, "0") or 0)
        rows = con.execute(
            "SELECT address FROM token_registry WHERE chain=? AND COALESCE(kline_retry_after,0)<=? ORDER BY address",
            (chain, now),
        ).fetchall()
        if not rows:
            rows = con.execute(
                "SELECT address FROM token_snapshot WHERE chain=? ORDER BY address",
                (chain,),
            ).fetchall()
        if not rows:
            return []
        addr = rows[cursor % len(rows)]["address"]
        db.meta_set(con, "kline_cursor_" + chain, str(cursor + 1))
        return [addr]

    try:
        addresses = with_db(pick)
    except Exception as e:
        _finish("gmgn_kline", chain, False, started, error=str(e), run_state="failed")
        return
    if not addresses:
        _finish("gmgn_kline", chain, False, started, error="还没有 token 可拉日 K", run_state="zero_write", request_ok=0)
        return

    written_total = 0
    last_err = None
    last_state = "failed"
    any_request = False
    for address in addresses:
        try:
            def write(con, addr=address):
                if growth_item is not None:
                    import history_growth as growth
                    result=growth.attempt(con,growth_item,now,growth.fetch_standard)
                    written=result.get('inserted',0)
                else:
                    written = M.upsert_daily_kline(con, chain, addr, now)
                if written:
                    db.meta_set(con, "last_kline_update_" + chain, str(now))
                    db.meta_set(con, "last_kline_update", str(now))
                return written
            written = with_db(write)
            any_request = True
            written_total += written or 0
            if not written:
                def mark_empty(con, addr=address):
                    R.schedule_kline_retry(con, chain, addr, now, 86400)
                with_db(mark_empty)
        except Exception as e:
            last_err = e
            last_state = "rate_limited" if _rate_limited(e) else "failed"
            def mark_retry(con, addr=address):
                R.schedule_kline_retry(con, chain, addr, now, R.kline_repair_delay(now))
            try:
                with_db(mark_retry)
            except Exception:
                pass
            if last_state == "rate_limited":
                break

    if written_total:
        _finish(
            "gmgn_kline", chain, True, started,
            rows_received=written_total, rows_parsed=written_total, rows_written=written_total,
            hot_changed=0, cold_changed=1,
            source_timestamp_missing=True, wrote_db=True,
            run_state="healthy", request_ok=1,
        )
        return
    if last_err is not None:
        _finish(
            "gmgn_kline", chain, False, started,
            error=str(last_err), rows_received=0, run_state=last_state, request_ok=0,
        )
        return
    _finish(
        "gmgn_kline", chain, False, started,
        error="kline empty or unparsed",
        rows_received=0, rows_written=0, run_state="zero_write", request_ok=1 if any_request else 0,
    )


def _optional_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    return None


def write_security_snapshot(con, chain, address, data, now):
    """保留 security endpoint 的原始语义，不折叠 boolean/number aliases。"""
    if not isinstance(data, dict):
        raise ValueError("security payload must be an object")
    blob = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(blob.encode()).hexdigest()[:16]
    old = con.execute(
        "SELECT security_note FROM token_snapshot WHERE chain=? AND address=?",
        (chain, address),
    ).fetchone()
    changed = 0 if old and old["security_note"] == digest else 1
    con.execute(
        """UPDATE token_snapshot SET
             security_note=?, security_json=?, security_updated_at=?,
             security_is_honeypot=?, security_is_blacklist=?,
             security_is_open_source=?, security_is_renounced=?,
             security_top10_holder_rate=?,
             security_renounced_mint=?, security_renounced_freeze_account=?,
             security_sell_tax=?
           WHERE chain=? AND address=?""",
        (
            digest, blob, int(now),
            _optional_bool(data.get("is_honeypot")) if "is_honeypot" in data else None,
            _optional_bool(data.get("is_blacklist")) if "is_blacklist" in data else None,
            _optional_bool(data.get("is_open_source")) if "is_open_source" in data else None,
            _optional_bool(data.get("is_renounced")) if "is_renounced" in data else None,
            _text(data.get("top_10_holder_rate")) if "top_10_holder_rate" in data else None,
            _optional_bool(data.get("renounced_mint")) if "renounced_mint" in data else None,
            _optional_bool(data.get("renounced_freeze_account")) if "renounced_freeze_account" in data else None,
            # sell_tax 刻度（0–1 还是百分数）未编码，原样保存字符串。
            _text(data.get("sell_tax")) if "sell_tax" in data else None,
            chain, address,
        ),
    )
    return changed


def job_security(chain):
    started = time.time()
    if _skip_if_cooling("gmgn_security", chain, started):
        return

    def pick(con):
        cursor = int(db.meta_get(con, "sec_cursor_" + chain, "0") or 0)
        rows = con.execute(
            "SELECT address FROM token_snapshot WHERE chain=? ORDER BY address",
            (chain,),
        ).fetchall()
        if not rows:
            return None
        addr = rows[cursor % len(rows)]["address"]
        db.meta_set(con, "sec_cursor_" + chain, str(cursor + 1))
        return addr

    try:
        address = with_db(pick)
    except Exception as e:
        _finish("gmgn_security", chain, False, started, error=str(e))
        return
    if not address:
        _finish("gmgn_security", chain, False, started, error="还没有 token 可拉安全指标")
        return
    try:
        data = _gmgn_mod().gmgn(
            ["token", "security", "--chain", chain, "--address", address],
            timeout=40,
        )
    except Exception as e:
        state = "rate_limited" if _rate_limited(e) else "failed"
        _finish("gmgn_security", chain, False, started, error=str(e), run_state=state, request_ok=0)
        return
    def apply(con):
        return write_security_snapshot(con, chain, address, data, int(time.time()))

    try:
        changed = with_db(apply)
    except Exception as e:
        _finish("gmgn_security", chain, False, started, error=str(e), rows_received=1)
        return
    _finish(
        "gmgn_security", chain, True, started,
        rows_received=1, hot_changed=0, cold_changed=changed,
        source_timestamp_missing=True, wrote_db=True,
    )


def _addr_key(address):
    if not address:
        return ""
    text = str(address).strip()
    return text.lower() if text.lower().startswith("0x") else text


def job_dex(chain):
    """DexScreener /tokens/v1，每请求 ≤30 地址。只写 price_ds / volume_ds / liquidity_ds / dex_price。"""
    started = time.time()
    ds_chain = DS_CHAIN.get(chain)
    if not ds_chain:
        _finish("dexscreener", chain, False, started, error="未知链")
        return

    def addrs(con):
        return [r["address"] for r in con.execute(
            "SELECT address FROM token_snapshot WHERE chain=? AND address!=''",
            (chain,),
        ).fetchall()]

    try:
        addresses = with_db(addrs)
    except Exception as e:
        _finish("dexscreener", chain, False, started, error=str(e))
        return
    if not addresses:
        _finish("dexscreener", chain, False, started, error="没有地址可校验")
        return
    best = {}
    errors = []
    received = 0
    for i in range(0, len(addresses), 30):
        batch = addresses[i:i + 30]
        url = f"https://api.dexscreener.com/tokens/v1/{ds_chain}/{','.join(batch)}"
        try:
            payload = http_json(url, timeout=20)
        except Exception as e:
            errors.append(str(e))
            time.sleep(0.25)
            continue
        pairs = payload if isinstance(payload, list) else payload.get("pairs") or []
        received += len(pairs) if isinstance(pairs, list) else 0
        if isinstance(pairs, list):
            for pair in pairs:
                base = (pair.get("baseToken") or {}).get("address")
                key = _addr_key(base)
                if not key:
                    continue
                liq = ((pair.get("liquidity") or {}).get("usd")) or 0
                try:
                    liq_n = float(liq)
                except (TypeError, ValueError):
                    liq_n = 0
                prev = best.get(key)
                if prev is None or liq_n > prev[0]:
                    vol = (pair.get("volume") or {}).get("h24")
                    best[key] = (liq_n, pair.get("priceUsd"), vol, liq)
        time.sleep(0.25)
    if not best and errors:
        _finish("dexscreener", chain, False, started, error=errors[0], rows_received=0)
        return

    def apply(con):
        hot = 0
        for address in addresses:
            picked = best.get(_addr_key(address))
            if not picked:
                continue
            _, price, vol, liq = picked
            old = con.execute(
                "SELECT price, price_ds, volume_ds, liquidity_ds FROM token_snapshot WHERE chain=? AND address=?",
                (chain, address),
            ).fetchone()
            if old is None:
                continue
            if old and (
                H.num_changed(old["price_ds"], price)
                or H.num_changed(old["volume_ds"], vol)
                or H.num_changed(old["liquidity_ds"], liq)
            ):
                hot += 1
            flag = H.diverge_flag(old["price"] if old else None, price, DIVERGE_RATIO)
            con.execute(
                """UPDATE token_snapshot
                   SET price_ds=?, volume_ds=?, liquidity_ds=?, dex_price=?, diverge=?
                   WHERE chain=? AND address=?""",
                (_s(price), _s(vol), _s(liq), _s(price), flag, chain, address),
            )
        return hot

    try:
        hot = with_db(apply)
    except Exception as e:
        _finish("dexscreener", chain, False, started, error=str(e), rows_received=received)
        return
    err = errors[0] if errors else None
    _finish(
        "dexscreener", chain, True, started,
        rows_received=received or len(best), hot_changed=hot, cold_changed=0,
        source_timestamp_missing=True, wrote_db=True, error=err,
    )


def _load_assets():
    now = time.time()
    if _asset_cache["by_addr"] and now - _asset_cache["at"] < 60:
        return _asset_cache["by_addr"]
    payload = http_json("https://api.robinhood.com/rhj/assets", timeout=20)
    assets = payload.get("assets") if isinstance(payload, dict) else payload
    by_addr = {}
    for asset in assets or []:
        mult = asset.get("currentMultiplier") or "1"
        symbol = asset.get("tokenSymbol")
        for dep in asset.get("deployments") or []:
            if dep.get("chainId") not in (4663, "4663"):
                continue
            key = _addr_key(dep.get("contractAddress"))
            if key:
                by_addr[key] = {"symbol": symbol, "multiplier": str(mult)}
    _asset_cache["at"] = now
    _asset_cache["by_addr"] = by_addr
    return by_addr


def _price_one(symbol):
    hit = _px_cache.get(symbol)
    if hit and time.time() - hit[0] < 15:
        return hit[1]
    payload = http_json(f"https://api.robinhood.com/rhj/prices/{symbol}", timeout=15)
    _px_cache[symbol] = (time.time(), payload)
    return payload


def job_anchor():
    """官方 /rhj/prices。存原始 bid/ask，不乘乘数，不覆盖 GMGN 价。"""
    chain = "robinhood"
    started = time.time()
    try:
        by_addr = _load_assets()
    except Exception as e:
        _finish("robinhood_anchor", chain, False, started, error=f"assets {e}")
        return

    def wanted(con):
        return [r["address"] for r in con.execute(
            "SELECT address FROM token_snapshot WHERE chain='robinhood'"
        ).fetchall()]

    try:
        addresses = with_db(wanted)
    except Exception as e:
        _finish("robinhood_anchor", chain, False, started, error=str(e))
        return
    symbols = []
    for address in addresses:
        meta = by_addr.get(_addr_key(address))
        if meta and meta.get("symbol"):
            symbols.append(meta["symbol"])
    symbols = list(dict.fromkeys(symbols))
    quotes = {}
    errors = []

    def pull(symbol):
        try:
            _pace(0.03)
            return symbol, _price_one(symbol), None
        except Exception as e:
            return symbol, None, str(e)

    with ThreadPoolExecutor(max_workers=6) as pool:
        for symbol, payload, err in pool.map(pull, symbols):
            if err:
                errors.append(err)
            elif payload:
                quotes[symbol] = payload
    if symbols and not quotes:
        _finish("robinhood_anchor", chain, False, started, error=errors[0] if errors else "无报价")
        return
    closed = H.equity_session_closed(time.time())
    stamps = []

    def apply(con):
        hot = 0
        for address in addresses:
            meta = by_addr.get(_addr_key(address))
            if not meta:
                continue
            payload = quotes.get(meta["symbol"])
            if not payload:
                continue
            qlist = payload.get("quotes") if isinstance(payload, dict) else None
            q = (qlist or [None])[0] or {}
            bid, ask = q.get("bid"), q.get("ask")
            gen = H.parse_rfc3339(q.get("generatedAt"))
            if gen:
                stamps.append(gen)
            halt = 1 if q.get("isTradingHalt") else 0
            old = con.execute(
                "SELECT anchor_bid, anchor_ask FROM token_snapshot WHERE chain='robinhood' AND address=?",
                (address,),
            ).fetchone()
            if old and (H.num_changed(old["anchor_bid"], bid) or H.num_changed(old["anchor_ask"], ask)):
                hot += 1
            con.execute(
                """UPDATE token_snapshot SET
                     anchor_bid=?, anchor_ask=?, anchor_generated_at=?,
                     anchor_multiplier=?, halt=?, market_closed=?
                   WHERE chain='robinhood' AND address=?""",
                (_s(bid), _s(ask), gen, meta["multiplier"], halt, 1 if closed else 0, address),
            )
        return hot

    try:
        hot = with_db(apply)
    except Exception as e:
        _finish("robinhood_anchor", chain, False, started, error=str(e))
        return
    missing = not stamps
    _finish(
        "robinhood_anchor", chain, True, started,
        rows_received=len(quotes), hot_changed=hot, cold_changed=0,
        source_timestamp=min(stamps) if stamps else None,
        source_timestamp_missing=missing, wrote_db=True,
        error=errors[0] if errors else None,
    )


def _load_feeds():
    now = time.time()
    if _feed_cache["by_symbol"] and now - _feed_cache["at"] < 3600:
        return _feed_cache["by_symbol"]
    payload = http_json(FEED_URL, timeout=20)
    by_symbol = {}
    for feed in payload if isinstance(payload, list) else []:
        symbol = H.feed_symbol(feed.get("name"))
        proxy = feed.get("proxyAddress")
        if not symbol or not proxy:
            continue
        decimals = feed.get("decimals")
        try:
            decimals = int(decimals) if decimals is not None else 8
        except (TypeError, ValueError):
            decimals = 8
        by_symbol[symbol] = {"proxy": proxy, "decimals": decimals}
    _feed_cache["at"] = now
    _feed_cache["by_symbol"] = by_symbol
    return by_symbol


def _eth_calls(calls):
    """calls: [(proxy, data)] → result hex list。失败则逐个重试。"""
    body = [
        {"jsonrpc": "2.0", "id": i, "method": "eth_call",
         "params": [{"to": proxy, "data": data}, "latest"]}
        for i, (proxy, data) in enumerate(calls)
    ]
    try:
        payload = http_json(RH_RPC, timeout=25, body=body)
        if isinstance(payload, list):
            by_id = {item.get("id"): item for item in payload}
            return [((by_id.get(i) or {}).get("result")) for i in range(len(calls))]
    except Exception:
        pass
    out = []
    for proxy, data in calls:
        try:
            one = http_json(RH_RPC, timeout=15, body={
                "jsonrpc": "2.0", "id": 1, "method": "eth_call",
                "params": [{"to": proxy, "data": data}, "latest"],
            })
            out.append(one.get("result") if isinstance(one, dict) else None)
        except Exception:
            out.append(None)
    return out


def job_chainlink():
    """latestRoundData()。answer 已是乘数调整后的代币价，不再乘 currentMultiplier。"""
    chain = "robinhood"
    started = time.time()
    try:
        by_addr = _load_assets()
        feeds = _load_feeds()
    except Exception as e:
        _finish("chainlink", chain, False, started, error=str(e))
        return

    def wanted(con):
        return [r["address"] for r in con.execute(
            "SELECT address FROM token_snapshot WHERE chain='robinhood'"
        ).fetchall()]

    try:
        addresses = with_db(wanted)
    except Exception as e:
        _finish("chainlink", chain, False, started, error=str(e))
        return
    jobs = []
    for address in addresses:
        meta = by_addr.get(_addr_key(address))
        if not meta:
            continue
        feed = feeds.get((meta.get("symbol") or "").upper())
        if not feed:
            continue
        jobs.append((address, feed))
    if not jobs:
        _finish("chainlink", chain, False, started, error="没有可对上的 Chainlink feed")
        return
    calls = [(feed["proxy"], ROUND_SELECTOR) for _, feed in jobs]
    results = _eth_calls(calls)
    updates = []
    stamps = []
    for (address, feed), result in zip(jobs, results):
        if not result:
            continue
        try:
            answer, updated = H.decode_latest_round(result)
        except ValueError:
            continue
        price = answer / (10 ** int(feed["decimals"]))
        updates.append((address, price, updated))
        if updated:
            stamps.append(int(updated))
    if not updates:
        _finish("chainlink", chain, False, started, error="latestRoundData 无返回")
        return

    def apply(con):
        hot = 0
        for address, price, updated in updates:
            old = con.execute(
                "SELECT oracle_price FROM token_snapshot WHERE chain='robinhood' AND address=?",
                (address,),
            ).fetchone()
            if old and H.num_changed(old["oracle_price"], price):
                hot += 1
            con.execute(
                "UPDATE token_snapshot SET oracle_price=?, oracle_updated_at=? WHERE chain='robinhood' AND address=?",
                (_s(price), int(updated), address),
            )
        return hot

    try:
        hot = with_db(apply)
    except Exception as e:
        _finish("chainlink", chain, False, started, error=str(e), rows_received=len(updates))
        return
    _finish(
        "chainlink", chain, True, started,
        rows_received=len(updates), hot_changed=hot, cold_changed=0,
        source_timestamp=min(stamps) if stamps else None,
        source_timestamp_missing=not stamps, wrote_db=True,
    )


GMGN_JOBS = {
    "gmgn": job_gmgn,
    "gmgn_hot": job_gmgn_hot,
    "gmgn_new_pair": job_new_pair,
    "gmgn_signal": job_signal,
    "gmgn_kline": job_kline,
    "gmgn_security": job_security,
}
# 日 K 在 pick_gmgn_job 里还有保留名额，这里的顺序只作用于非保留车道。
GMGN_PRIORITY = ["gmgn_kline", "gmgn", "gmgn_hot", "gmgn_new_pair", "gmgn_signal", "gmgn_security"]
SIDE_JOBS = {
    "dexscreener": job_dex,
    "robinhood_anchor": lambda chain: job_anchor(),
    "chainlink": lambda chain: job_chainlink(),
}


def _due_key(nxt, now, order):
    """按超期比例挑车道。否则 10 秒的 GMGN 会一直占住 1 req/s，日 K 永远排不上。"""
    best = None
    for source in order:
        for chain, period in ((c, p) for (s, c), p in H.PERIOD.items() if s == source):
            due = nxt.get((source, chain), 0)
            if due > now:
                continue
            late = (now - due) / max(period, 1)
            rank = (-late, order.index(source), due)
            if best is None or rank < best[0]:
                best = (rank, source, chain, period)
    return None if best is None else best[1:]


def run_loop():
    import market_sched as sched
    import market_research as R
    with_db(H.ensure_catalog)
    with_db(lambda con: R.refresh_daily_metrics_for_utc_day(con, time.time()))
    nxt = {(s, c): 0 for (s, c) in H.PERIOD}
    stop = {"v": False}

    def side_chain(source, chain):
        """一条链一个线程。周期从请求开始算，避免“跑完再等一个周期”把 api_age 顶出 LIVE。"""
        while not stop["v"]:
            started = time.time()
            try:
                SIDE_JOBS[source](chain)
            except Exception as e:
                _finish(source, chain, False, started, error=str(e))
            wait = H.PERIOD[(source, chain)] - (time.time() - started)
            if wait > 0:
                time.sleep(wait)

    for source, chain in H.PERIOD:
        if source not in SIDE_JOBS:
            continue
        threading.Thread(
            target=side_chain, args=(source, chain), name=f"market-{source}-{chain}", daemon=True,
        ).start()
    last_hb = 0
    last_prune = 0
    last_history = 0
    try:
        while True:
            now = time.time()
            if now - last_hb >= 5:
                def heartbeat(con):
                    H.touch_heartbeat(con, now)
                    R.refresh_daily_metrics_for_utc_day(con, now)
                with_db(heartbeat)
                last_hb = now
            if now - last_prune >= 600:
                with_db(lambda con: H.prune_latency(con, now))
                last_prune = now
            # 冷却期内所有 GMGN 车道停手。日 K 到点时先于 Trending。
            if sched.in_cooldown(now):
                time.sleep(min(1.0, max(0.2, sched.cooldown_until() - now)))
                continue
            periods = {(s, c): p for (s, c), p in H.PERIOD.items() if s in GMGN_JOBS}
            picked = sched.pick_gmgn_job(nxt, now, periods, GMGN_PRIORITY)
            if not picked:
                import history_growth as growth
                if now-last_history>=60 and growth.idle_allowed(nxt,now,periods):
                    last_history=now
                    try:
                        with_db(lambda con: growth.idle_tick(con,int(now)))
                    except Exception as error:
                        print('history_growth:',type(error).__name__,str(error)[:200],flush=True)
                time.sleep(0.2)
                continue
            source, chain, period = picked
            t0 = time.time()
            try:
                GMGN_JOBS[source](chain)
            except Exception as e:
                _finish(source, chain, False, t0, error=str(e))
            elapsed = time.time() - t0
            if elapsed < GMGN_GAP:
                time.sleep(GMGN_GAP - elapsed)
            nxt[(source, chain)] = t0 + period
    finally:
        stop["v"] = True


def run_pass():
    """单轮：每条车道各跑一次。给 `market_run.py once` 用。冷却期内不发 GMGN。"""
    import market_sched as sched
    import market_research as R
    with_db(H.ensure_catalog)
    def prepare(con):
        now = time.time()
        H.touch_heartbeat(con, now)
        R.refresh_daily_metrics_for_utc_day(con, now)
    with_db(prepare)
    for source, chain in list(H.PERIOD):
        if source in GMGN_JOBS and sched.in_cooldown(time.time()):
            _finish(
                source, chain, False, time.time(),
                error=f"GLOBAL_GMGN_COOLDOWN until={sched.cooldown_until()}",
                run_state="cooldown", request_ok=0,
            )
            continue
        fn = GMGN_JOBS.get(source) or SIDE_JOBS.get(source)
        if not fn:
            continue
        try:
            fn(chain)
        except Exception as e:
            _finish(source, chain, False, time.time(), error=str(e), run_state="failed")
        if source in GMGN_JOBS:
            time.sleep(GMGN_GAP)
    return {"ok": True, "ts": int(time.time())}
