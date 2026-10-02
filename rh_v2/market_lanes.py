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

GMGN_GAP = 1.05
TOP_N = int(os.environ.get("MARKET_TOP_N", "100"))
DIVERGE_RATIO = float(os.environ.get("MARKET_DIVERGE_RATIO", str(H.DIVERGE_RATIO)))
RH_RPC = os.environ.get("MARKET_RH_RPC", "https://rpc.mainnet.chain.robinhood.com")
FEED_URL = os.environ.get(
    "MARKET_CHAINLINK_FEEDS",
    "https://reference-data-directory.vercel.app/feeds-robinhood-mainnet.json",
)
DS_CHAIN = {"sol": "solana", "base": "base", "eth": "ethereum", "robinhood": "robinhood"}
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
        price, vol, liq = _s(it.get("price")), _s(it.get("volume")), _s(it.get("liquidity"))
        holders = it.get("holder_count")
        smart = _i(it.get("smart_degen_count"))
        sniper = _i(it.get("sniper_count"))
        renowned = _i(it.get("renowned_count"))
        top10 = _s(it.get("top_10_holder_rate"))
        rat = _s(it.get("rat_trader_amount_rate"))
        bundler = _s(it.get("bundler_rate"))
        chg_p = 1 if old is None or H.num_changed(old["price"], price) else 0
        chg_v = 1 if old is None or H.num_changed(old["volume_24h"], vol) else 0
        chg_l = 1 if old is None or H.num_changed(old["liquidity"], liq) else 0
        if chg_p or chg_v or chg_l:
            hot += 1
        cold_hit = old is None or any((
            (old["holders"] or None) != (holders if isinstance(holders, int) else _i(holders)),
            (old["smart_degen_count"] or None) != smart,
            (old["sniper_count"] or None) != sniper,
            (old["renowned_count"] or None) != renowned,
            H.num_changed(old["top10_holder_rate"], top10),
            H.num_changed(old["rat_trader_rate"], rat),
            H.num_changed(old["bundler_rate"], bundler),
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
        con.execute(
            """INSERT INTO token_snapshot(
                 chain,address,ts,price,pc_24h,volume_24h,liquidity,market_cap,holders,
                 smart_degen_count,sniper_count,renowned_count,top10_holder_rate,
                 rat_trader_rate,bundler_rate,swaps,commit_ok,chg_price,chg_volume,chg_liquidity,
                 liquidity_num, liquidity_updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)
               ON CONFLICT(chain, address) DO UPDATE SET
                 ts=excluded.ts, price=excluded.price, pc_24h=excluded.pc_24h,
                 volume_24h=excluded.volume_24h, liquidity=excluded.liquidity,
                 market_cap=excluded.market_cap, holders=excluded.holders,
                 smart_degen_count=excluded.smart_degen_count,
                 sniper_count=excluded.sniper_count, renowned_count=excluded.renowned_count,
                 top10_holder_rate=excluded.top10_holder_rate,
                 rat_trader_rate=excluded.rat_trader_rate, bundler_rate=excluded.bundler_rate,
                 swaps=excluded.swaps, commit_ok=1,
                 chg_price=excluded.chg_price, chg_volume=excluded.chg_volume,
                 chg_liquidity=excluded.chg_liquidity,
                 liquidity_num=excluded.liquidity_num,
                 liquidity_updated_at=excluded.liquidity_updated_at""",
            (
                chain, address, int(now), price, _s(it.get("price_change_percent")),
                vol, liq, _s(it.get("market_cap") if it.get("market_cap") is not None else it.get("usd_market_cap")),
                holders if isinstance(holders, int) else _i(holders),
                smart, sniper, renowned, top10, rat, bundler, _i(it.get("swaps")),
                chg_p, chg_v, chg_l, R.as_real(it.get("liquidity")), int(now),
            ),
        )
        if it.get("price") is not None:
            con.execute(
                "INSERT OR REPLACE INTO hourly_price(chain,address,ts,price) VALUES(?,?,?,?)",
                (chain, address, M.bucket_floor(int(now)), price),
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
        item = dict(row)
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
# signal CLI 只接受这些链。base / eth 记 unsupported，不发请求，也不写成失败。
SIGNAL_CHAINS = {"sol", "robinhood"}


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
    """日 K 有保留名额。先补已观察到 50k 且尚未回填成功的地址，再轮转。

    空响应、解析失败、请求失败都不盖 kline_backfilled_at。
    """
    started = time.time()
    if _skip_if_cooling("gmgn_kline", chain, started):
        return
    M = _gmgn_mod()
    now = int(time.time())

    def pick(con):
        _remember_seed(con, chain, now)
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
            return pending["address"]
        today = M.today_utc_start(now)
        for address, _symbol, _name in M.SEED_TOKENS.get(chain, []):
            have = con.execute(
                "SELECT 1 FROM token_candle WHERE chain=? AND address=? AND candle_open_ts=?",
                (chain, address, today),
            ).fetchone()
            if not have:
                return address
        cursor = int(db.meta_get(con, "kline_cursor_" + chain, "0") or 0)
        rows = con.execute(
            "SELECT address FROM token_registry WHERE chain=? ORDER BY address",
            (chain,),
        ).fetchall()
        if not rows:
            rows = con.execute(
                "SELECT address FROM token_snapshot WHERE chain=? ORDER BY address",
                (chain,),
            ).fetchall()
        if not rows:
            return None
        addr = rows[cursor % len(rows)]["address"]
        db.meta_set(con, "kline_cursor_" + chain, str(cursor + 1))
        return addr

    try:
        address = with_db(pick)
    except Exception as e:
        _finish("gmgn_kline", chain, False, started, error=str(e), run_state="failed")
        return
    if not address:
        _finish("gmgn_kline", chain, False, started, error="还没有 token 可拉日 K", run_state="zero_write", request_ok=0)
        return
    try:
        def write(con):
            written = M.upsert_daily_kline(con, chain, address, now)
            if written:
                db.meta_set(con, "last_kline_update_" + chain, str(now))
            return written
        written = with_db(write)
    except Exception as e:
        def mark_retry(con):
            import market_research as R
            R.schedule_kline_retry(con, chain, address, now)
        try:
            with_db(mark_retry)
        except Exception:
            pass
        state = "rate_limited" if _rate_limited(e) else "failed"
        _finish("gmgn_kline", chain, False, started, error=str(e), rows_received=0, run_state=state, request_ok=0)
        return
    if not written:
        _finish(
            "gmgn_kline", chain, False, started,
            error="kline empty or unparsed",
            rows_received=0, rows_written=0, run_state="zero_write", request_ok=1,
        )
        return
    _finish(
        "gmgn_kline", chain, True, started,
        rows_received=written, rows_parsed=written, rows_written=written,
        hot_changed=0, cold_changed=1,
        source_timestamp_missing=True, wrote_db=True,
        run_state="healthy", request_ok=1,
    )


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
    blob = json.dumps(data, sort_keys=True, default=str)
    digest = hashlib.sha256(blob.encode()).hexdigest()[:16]
    note = digest

    def apply(con):
        old = con.execute(
            "SELECT security_note FROM token_snapshot WHERE chain=? AND address=?",
            (chain, address),
        ).fetchone()
        changed = 0 if old and old["security_note"] == note else 1
        con.execute(
            "UPDATE token_snapshot SET security_note=? WHERE chain=? AND address=?",
            (note, chain, address),
        )
        return changed

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
    with_db(H.ensure_catalog)
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
    try:
        while True:
            now = time.time()
            if now - last_hb >= 5:
                with_db(lambda con: H.touch_heartbeat(con, now))
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
    with_db(H.ensure_catalog)
    with_db(lambda con: H.touch_heartbeat(con, time.time()))
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
