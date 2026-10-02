"""Phase 1 研究账本。

event 是事实，registry 是状态。一次观察在同一个 SQLite 事务里写
discovery_event，再 UPSERT token_registry。首次字段只向前锁定。

Legacy token_snapshot did not preserve liquidity history. Historical
first-liquidity-$50k timestamps before Phase 1 deployment cannot be
reconstructed reliably.

first_liquidity_50k_at 的含义是：本管线第一次观测到该 token 的流动性
已经 >= $50k 的时间，不一定是它历史上第一次穿过 $50k。
"""
import json
import time

import market_db as db


LIQUIDITY_THRESHOLD = 50000
LIQUIDITY_FRESHNESS_SEC = 300
DISCOVERY_BUCKET_SEC = 300
DAY_SEC = 86400
OBS_CROSSING = "observed_crossing"
OBS_FIRST_ABOVE = "first_observed_above"
LEGACY_SOURCE = "legacy_snapshot"
LEGACY_NOTE = (
    "Legacy token_snapshot did not preserve liquidity history. "
    "Historical first-liquidity-$50k timestamps before Phase 1 deployment "
    "cannot be reconstructed reliably."
)

# 去重：同一 (chain, address, source, source_variant, 300 秒桶) 只保留一行。
# 不同 source、不同 variant、或下一个桶，都会再写一行。这不是最后状态快照。


def as_real(v):
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return n


def parse_sources(text):
    if not text:
        return []
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, str) and item and item not in out:
            out.append(item)
    return out


def add_source(text, source):
    items = parse_sources(text)
    if source and source not in items:
        items.append(source)
    return json.dumps(items, ensure_ascii=False)


def time_bucket(seen_at, size=DISCOVERY_BUCKET_SEC):
    seen = int(seen_at)
    return seen - seen % int(size)


def _field(row, key):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def apply_liquidity_observation(row, liquidity, seen_at, source):
    """返回要写入 registry 的字段。已锁定的首次 50k 观察不会被覆盖。

    earliest time this pipeline observed the token at or crossing
    liquidity >= $50k; not necessarily the token's historical first crossing.

    - 先见过 < 50000，再见到 >= 50000：observed_crossing
    - 第一次见到就已经 >= 50000：first_observed_above
      这不能当成刚刚突破。
    """
    liq = as_real(liquidity)
    if liq is None:
        return {}
    if liq < LIQUIDITY_THRESHOLD:
        if int(_field(row, "seen_liquidity_below_50k") or 0):
            return {}
        return {"seen_liquidity_below_50k": 1}
    if _field(row, "first_liquidity_50k_at"):
        return {}
    kind = OBS_CROSSING if int(_field(row, "seen_liquidity_below_50k") or 0) else OBS_FIRST_ABOVE
    return {
        "first_liquidity_50k_at": int(seen_at),
        "liquidity_50k_observation_type": kind,
        "source_at_50k": source,
    }


def formal_eligible(liquidity, age_sec):
    """正式连涨榜：流动性 >= 50000 且年龄 <= 300 秒。缺年龄不合格。"""
    liq = as_real(liquidity)
    if liq is None or liq < LIQUIDITY_THRESHOLD:
        return False
    if age_sec is None:
        return False
    try:
        age = int(age_sec)
    except (TypeError, ValueError):
        return False
    return age <= LIQUIDITY_FRESHNESS_SEC


def _created_from_item(item):
    """只用上游的创建时间。不用 open_timestamp、first_seen、第一根 K。"""
    if not isinstance(item, dict):
        return None
    created = db.unix_ts(item.get("creation_timestamp"))
    if created is None:
        created = db.unix_ts(item.get("created_timestamp"))
    return created


def compact_metadata(item, extra=None):
    keep = (
        "symbol", "name", "rank", "liquidity", "price", "market_cap", "usd_market_cap",
        "signal_type", "trigger_at", "creation_timestamp", "created_timestamp",
        "launchpad_platform", "holder_count",
    )
    out = {}
    if isinstance(item, dict):
        for key in keep:
            if key in item and item.get(key) is not None:
                out[key] = item.get(key)
    if extra:
        out.update(extra)
    return out


def ingest_discovery(
    con, chain, address, source, seen_at,
    source_variant="", liquidity=None, price=None, market_cap=None, rank=None,
    symbol=None, name=None, token_created_at=None, token_created_at_source=None,
    metadata=None,
):
    """同一事务内：INSERT discovery_event，再 UPSERT registry。调用方负责 commit。

    去重键是 (chain, address, source, source_variant, time_bucket)，桶长 300 秒。
    桶内重复不再插 event，但仍更新 last_seen_at。
    first_seen_at / first_source / 首次 50k 字段只在为空时写入。
    """
    if not chain or not address or not source:
        return {"event_inserted": 0, "registry_inserted": 0, "registry_updated": 0}
    seen = int(seen_at)
    variant = source_variant or ""
    bucket = time_bucket(seen)
    liq = as_real(liquidity)
    px = as_real(price)
    mcap = as_real(market_cap)
    try:
        rank_i = None if rank is None or rank == "" else int(rank)
    except (TypeError, ValueError):
        rank_i = None
    meta_json = json.dumps(compact_metadata(metadata, {"source_variant": variant or None}), ensure_ascii=False)
    cur = con.execute(
        """INSERT INTO discovery_event(
             chain, address, source, source_variant, seen_at, time_bucket,
             liquidity, price, market_cap, rank, metadata_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(chain, address, source, source_variant, time_bucket) DO NOTHING""",
        (chain, address, source, variant, seen, bucket, liq, px, mcap, rank_i, meta_json),
    )
    event_inserted = 1 if cur.rowcount else 0
    row = con.execute(
        "SELECT * FROM token_registry WHERE chain=? AND address=?",
        (chain, address),
    ).fetchone()
    obs = apply_liquidity_observation(row, liq, seen, source)
    created = db.unix_ts(token_created_at) if token_created_at is not None else None
    if row is None:
        sources = json.dumps([source], ensure_ascii=False)
        con.execute(
            """INSERT INTO token_registry(
                 chain, address, symbol, name, first_seen_at, last_seen_at,
                 first_source, sources_seen, first_liquidity_50k_at,
                 liquidity_50k_observation_type, source_at_50k,
                 seen_liquidity_below_50k, token_created_at, token_created_at_source, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                chain, address, symbol, name, seen, seen, source, sources,
                obs.get("first_liquidity_50k_at"),
                obs.get("liquidity_50k_observation_type"),
                obs.get("source_at_50k"),
                1 if obs.get("seen_liquidity_below_50k") else 0,
                created,
                token_created_at_source if created else None,
                seen,
            ),
        )
        return {"event_inserted": event_inserted, "registry_inserted": 1, "registry_updated": 1}
    sources = add_source(row["sources_seen"], source)
    con.execute(
        """UPDATE token_registry SET
             symbol=COALESCE(?, symbol),
             name=COALESCE(?, name),
             last_seen_at=?,
             sources_seen=?,
             updated_at=?,
             seen_liquidity_below_50k=CASE WHEN ? THEN 1 ELSE seen_liquidity_below_50k END,
             first_liquidity_50k_at=COALESCE(first_liquidity_50k_at, ?),
             liquidity_50k_observation_type=COALESCE(liquidity_50k_observation_type, ?),
             source_at_50k=COALESCE(source_at_50k, ?),
             token_created_at=COALESCE(token_created_at, ?),
             token_created_at_source=COALESCE(token_created_at_source, ?)
           WHERE chain=? AND address=?""",
        (
            symbol, name, seen, sources, seen,
            1 if obs.get("seen_liquidity_below_50k") else 0,
            obs.get("first_liquidity_50k_at"),
            obs.get("liquidity_50k_observation_type"),
            obs.get("source_at_50k"),
            created,
            token_created_at_source if created else None,
            chain, address,
        ),
    )
    return {"event_inserted": event_inserted, "registry_inserted": 0, "registry_updated": 1}


def _num_text(v):
    n = as_real(v)
    if n is None:
        return None
    return repr(n) if False else str(n)


def write_daily_candles(con, chain, address, rows, now):
    """解析并写入 token_candle，同时镜像 daily_kline 给现有页面。

    至少写入一根才返回正数。单根解析失败跳过，不抛。
    不在这里设置 kline_backfilled_at。
    """
    if not isinstance(rows, list):
        return 0
    written = 0
    now = int(now)
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        opened = db.unix_ts(raw.get("time"))
        close = as_real(raw.get("close"))
        if opened is None or close is None:
            continue
        opened = opened - opened % DAY_SEC
        high = as_real(raw.get("high"))
        low = as_real(raw.get("low"))
        open_ = as_real(raw.get("open"))
        volume = as_real(raw.get("volume"))
        if high is None:
            high = close
        if low is None:
            low = close
        if open_ is None:
            open_ = close
        is_closed = 1 if opened + DAY_SEC <= now else 0
        con.execute(
            """INSERT INTO token_candle(
                 chain, address, candle_open_ts, open, high, low, close, volume, fetched_at, is_closed)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(chain, address, candle_open_ts) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low,
                 close=excluded.close, volume=excluded.volume,
                 fetched_at=excluded.fetched_at, is_closed=excluded.is_closed""",
            (chain, address, opened, open_, high, low, close, volume, now, is_closed),
        )
        con.execute(
            """INSERT INTO daily_kline(chain, address, ts, open, high, low, close, volume)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(chain, address, ts) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low,
                 close=excluded.close, volume=excluded.volume""",
            (chain, address, opened, str(open_), str(high), str(low), str(close), "" if volume is None else str(volume)),
        )
        written += 1
    return written


def schedule_kline_retry(con, chain, address, now, delay=120):
    con.execute(
        """UPDATE token_registry SET kline_retry_after=?
           WHERE chain=? AND address=?""",
        (int(now) + int(delay), chain, address),
    )


def commit_kline_fetch(con, chain, address, rows, now, parsed_ok):
    """只有解析成功且至少写入一根 token_candle，才盖 kline_backfilled_at。

    timeout / 429 / 空列表 / 非法 JSON / 解析失败 / 零写入都不算完成，并安排重试。
    """
    now = int(now)
    if not parsed_ok:
        schedule_kline_retry(con, chain, address, now)
        return 0
    written = write_daily_candles(con, chain, address, rows, now)
    if written <= 0:
        schedule_kline_retry(con, chain, address, now)
        return 0
    con.execute(
        """UPDATE token_registry SET kline_backfilled_at=?, kline_retry_after=NULL, updated_at=?
           WHERE chain=? AND address=?""",
        (now, now, chain, address),
    )
    db.touch_kline_fetched(con, chain, address, now)
    refresh_metrics(con, chain, address, now)
    return written


def closed_candle_rows(con, chain, address, now):
    rows = con.execute(
        """SELECT candle_open_ts, high, close FROM token_candle
           WHERE chain=? AND address=? AND is_closed=1 AND close IS NOT NULL AND close>0
             AND candle_open_ts + ? <= ?
           ORDER BY candle_open_ts""",
        (chain, address, DAY_SEC, int(now)),
    ).fetchall()
    out = []
    seen = set()
    for row in rows:
        ts = int(row["candle_open_ts"])
        if ts in seen:
            continue
        seen.add(ts)
        out.append((ts, float(row["close"]), float(row["high"]) if row["high"] is not None else float(row["close"])))
    return out


def streak_from_closed(closed):
    """与 src/lib/rh/streak.ts 相同：只比较相邻已收盘日，平盘和缺天都中断。"""
    streak = 0
    for i in range(len(closed) - 1, 0, -1):
        if closed[i][0] - closed[i - 1][0] != DAY_SEC:
            break
        if closed[i][1] > closed[i - 1][1]:
            streak += 1
        else:
            break
    return streak


def returns_from_closed(closed):
    """return_Nd = 最近一根已收盘 close / 向前第 N 根连续日 K 的 close - 1。

    窗口里缺任何一根，返回 None。绝不返回 0 来表示缺失。
    """
    def one(n):
        if len(closed) < n + 1:
            return None
        window = closed[-(n + 1):]
        for i in range(1, len(window)):
            if window[i][0] - window[i - 1][0] != DAY_SEC:
                return None
        base = window[0][1]
        last = window[-1][1]
        if base is None or base <= 0 or last is None or last <= 0:
            return None
        return last / base - 1
    return one(2), one(3), one(5)


def _has_streak_window(closed):
    if len(closed) < 2:
        return False
    return closed[-1][0] - closed[-2][0] == DAY_SEC


def can_qualify(reg, closed, liquidity, age_sec):
    """qualified_at：第一次同时满足下面六条的时间。之后不覆盖、不删除。

    1. 已在 token_registry
    2. 已有 50k 观察（observed_crossing 或 first_observed_above 均可，两者仍分开存）
    3. K 线回填已成功
    4. 至少两根相邻的已收盘日 K，连涨比较有定义（结果可以是 0）
    5. 当前流动性新鲜（年龄 <= 300 秒）
    6. 当前流动性 >= 50000
    return_2d/3d/5d 缺数据时保持 NULL，不因此阻止 qualified_at。
    """
    if reg is None:
        return False
    if not reg["first_liquidity_50k_at"] or not reg["kline_backfilled_at"]:
        return False
    if not _has_streak_window(closed):
        return False
    return formal_eligible(liquidity, age_sec)


def as_of_date(now):
    return time.strftime("%Y-%m-%d", time.gmtime(int(now)))


def _snapshot_liq(con, chain, address):
    row = con.execute(
        """SELECT liquidity_num, liquidity, liquidity_updated_at, ts
           FROM token_snapshot WHERE chain=? AND address=?""",
        (chain, address),
    ).fetchone()
    if row is None:
        return None, None
    liq = row["liquidity_num"]
    if liq is None:
        liq = as_real(row["liquidity"])
    updated = row["liquidity_updated_at"] if row["liquidity_updated_at"] else row["ts"]
    return liq, updated


def refresh_metrics(con, chain, address, now):
    reg = con.execute(
        "SELECT * FROM token_registry WHERE chain=? AND address=?",
        (chain, address),
    ).fetchone()
    if reg is None:
        return None
    now = int(now)
    closed = closed_candle_rows(con, chain, address, now)
    liq, updated = _snapshot_liq(con, chain, address)
    age = None if updated is None else now - int(updated)
    r2, r3, r5 = returns_from_closed(closed)
    streak = streak_from_closed(closed)
    eligible = 1 if formal_eligible(liq, age) else 0
    qualified = reg["qualified_at"]
    if qualified is None and can_qualify(reg, closed, liq, age):
        qualified = now
        con.execute(
            """UPDATE token_registry SET qualified_at=?, updated_at=?
               WHERE chain=? AND address=? AND qualified_at IS NULL""",
            (qualified, now, chain, address),
        )
    con.execute(
        """INSERT INTO daily_metrics(
             chain, address, as_of_date, streak, return_2d, return_3d, return_5d,
             liquidity, liquidity_age_sec, eligible, qualified_at, calculated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(chain, address, as_of_date) DO UPDATE SET
             streak=excluded.streak,
             return_2d=excluded.return_2d,
             return_3d=excluded.return_3d,
             return_5d=excluded.return_5d,
             liquidity=excluded.liquidity,
             liquidity_age_sec=excluded.liquidity_age_sec,
             eligible=excluded.eligible,
             qualified_at=COALESCE(daily_metrics.qualified_at, excluded.qualified_at),
             calculated_at=excluded.calculated_at""",
        (
            chain, address, as_of_date(now), streak, r2, r3, r5,
            liq, age, eligible, qualified, now,
        ),
    )
    return {"streak": streak, "return_2d": r2, "return_3d": r3, "return_5d": r5, "eligible": eligible, "qualified_at": qualified}


def parse_rank_items(data):
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    if isinstance(data, dict) and isinstance(data.get("rank"), list):
        return [row for row in data["rank"] if isinstance(row, dict)]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def parse_hot_items(data):
    rows = []
    blocks = data if isinstance(data, list) else [data]
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        blocks = data["data"]
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("tokens"), list):
            rows.extend(row for row in block["tokens"] if isinstance(row, dict))
        elif isinstance(block, dict) and isinstance(block.get("rank"), list):
            rows.extend(row for row in block["rank"] if isinstance(row, dict))
        elif isinstance(block, dict) and block.get("address"):
            rows.append(block)
    return rows


def parse_trench_items(data):
    """三类都收。

    当前 GMGN trenches 响应键是 new_creation / near_completion / completed。
    旧响应把 near_completion 放在 pump 下面，那个键仍然收。
    """
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    if not isinstance(data, dict):
        return []
    mapping = (
        ("new_creation", "new_creation"),
        ("near_completion", "near_completion"),
        ("pump", "near_completion"),
        ("completed", "completed"),
    )
    out = []
    for key, variant in mapping:
        rows = data.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("address"):
                out.append((variant, row))
    return out


def parse_signal_items(data):
    if isinstance(data, dict):
        for key in ("data", "list", "signals"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if isinstance(data, dict):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        address = item.get("token_address") or item.get("address")
        if not address:
            continue
        cur = item.get("cur_data") if isinstance(item.get("cur_data"), dict) else {}
        snap = item.get("data") if isinstance(item.get("data"), dict) else {}
        created = _created_from_item(snap) or _created_from_item(item)
        out.append({
            "address": address,
            "symbol": item.get("symbol") or snap.get("symbol") or cur.get("symbol"),
            "name": item.get("name") or snap.get("name"),
            "liquidity": cur.get("liquidity") if cur.get("liquidity") is not None else snap.get("liquidity"),
            "price": item.get("price") if item.get("price") is not None else snap.get("price") or cur.get("price"),
            "market_cap": item.get("market_cap") if item.get("market_cap") is not None else snap.get("market_cap"),
            "signal_type": item.get("signal_type"),
            "token_created_at": created,
            "rank": item.get("rank"),
        })
    return out


def _market_cap_of(item):
    if not isinstance(item, dict):
        return None
    if item.get("market_cap") is not None:
        return item.get("market_cap")
    return item.get("usd_market_cap")


def apply_source_items(con, chain, source, items, now, source_variant=""):
    """把已经解析出的 token 行写入 event + registry。不发网络请求。"""
    now = int(now)
    stats = {"rows_received": 0, "rows_parsed": 0, "rows_written": 0, "new_addresses": 0, "events_written": 0}
    for item in items:
        stats["rows_received"] += 1
        if not isinstance(item, dict):
            continue
        address = item.get("address") or item.get("token_address")
        if not address:
            continue
        stats["rows_parsed"] += 1
        variant = source_variant or str(item.get("_variant") or item.get("signal_type") or "")
        created = item.get("token_created_at")
        if created is None:
            created = _created_from_item(item)
        out = ingest_discovery(
            con, chain, address, source, now,
            source_variant=variant,
            liquidity=item.get("liquidity"),
            price=item.get("price"),
            market_cap=_market_cap_of(item),
            rank=item.get("rank"),
            symbol=item.get("symbol"),
            name=item.get("name"),
            token_created_at=created,
            token_created_at_source="gmgn_creation_timestamp" if created else None,
            metadata=item,
        )
        stats["events_written"] += out["event_inserted"]
        stats["new_addresses"] += out["registry_inserted"]
        if out["registry_updated"]:
            stats["rows_written"] += 1
    return stats


def upsert_snapshot_numbers(con, chain, address, now, price, volume, liquidity, market_cap, pc_24h, holders=None):
    """快照流动性用 REAL。TEXT 列保留给旧页面，比较不要靠字符串。"""
    now = int(now)
    liq = as_real(liquidity)
    con.execute(
        """INSERT INTO token_snapshot(
             chain, address, ts, price, pc_24h, volume_24h, liquidity, market_cap, holders,
             liquidity_num, liquidity_updated_at, commit_ok)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,1)
           ON CONFLICT(chain, address) DO UPDATE SET
             ts=excluded.ts,
             price=COALESCE(NULLIF(excluded.price, ''), token_snapshot.price),
             pc_24h=COALESCE(NULLIF(excluded.pc_24h, ''), token_snapshot.pc_24h),
             volume_24h=COALESCE(NULLIF(excluded.volume_24h, ''), token_snapshot.volume_24h),
             liquidity=COALESCE(NULLIF(excluded.liquidity, ''), token_snapshot.liquidity),
             market_cap=COALESCE(NULLIF(excluded.market_cap, ''), token_snapshot.market_cap),
             holders=COALESCE(excluded.holders, token_snapshot.holders),
             liquidity_num=COALESCE(excluded.liquidity_num, token_snapshot.liquidity_num),
             liquidity_updated_at=excluded.liquidity_updated_at,
             commit_ok=1""",
        (
            chain, address, now,
            "" if price is None else str(price),
            "" if pc_24h is None else str(pc_24h),
            "" if volume is None else str(volume),
            "" if liquidity is None else str(liquidity),
            "" if market_cap is None else str(market_cap),
            holders,
            liq,
            now if liq is not None or price not in (None, "") else now,
        ),
    )


def _ensure_column(con, table, column, decl):
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _repair_clocks(con):
    pending = con.execute(
        """SELECT 1 FROM tokens
           WHERE token_created_at IS NULL AND creation_ts IS NOT NULL AND creation_ts > 0
           LIMIT 1"""
    ).fetchone()
    if pending:
        con.execute(
            """UPDATE tokens SET token_created_at = creation_ts
               WHERE token_created_at IS NULL AND creation_ts IS NOT NULL AND creation_ts > 0"""
        )
    now = int(time.time())
    today = now - now % DAY_SEC
    pending_k = con.execute(
        """SELECT 1 FROM tokens
           WHERE kline_fetched_at IS NULL AND EXISTS (
             SELECT 1 FROM daily_kline d
             WHERE d.chain = tokens.chain AND d.address = tokens.address AND d.ts = ?
           ) LIMIT 1""",
        (today,),
    ).fetchone()
    if pending_k:
        con.execute(
            """UPDATE tokens SET kline_fetched_at = ?
               WHERE kline_fetched_at IS NULL AND EXISTS (
                 SELECT 1 FROM daily_kline d
                 WHERE d.chain = tokens.chain AND d.address = tokens.address AND d.ts = ?
               )""",
            (today, today),
        )


def _seed_registry(con, now):
    """只迁身份和当前可见字段。

    不把 snapshot 里 liquidity >= 50000 写成 first_liquidity_50k_at。
    Legacy token_snapshot did not preserve liquidity history. Historical
    first-liquidity-$50k timestamps before Phase 1 deployment cannot be
    reconstructed reliably.
    """
    con.execute(
        """INSERT INTO token_registry(
             chain, address, symbol, name, first_seen_at, last_seen_at,
             first_source, sources_seen, token_created_at, token_created_at_source, updated_at)
           SELECT t.chain, t.address, t.symbol, t.name, t.first_seen_at,
                  COALESCE(
                    (SELECT s.ts FROM token_snapshot s WHERE s.chain=t.chain AND s.address=t.address),
                    t.first_seen_at
                  ),
                  ?, ?,
                  t.token_created_at,
                  CASE WHEN t.token_created_at IS NOT NULL THEN 'gmgn_creation_timestamp' ELSE NULL END,
                  ?
           FROM tokens t
           WHERE NOT EXISTS (
             SELECT 1 FROM token_registry r WHERE r.chain=t.chain AND r.address=t.address
           )""",
        (LEGACY_SOURCE, json.dumps([LEGACY_SOURCE]), int(now)),
    )


def _copy_candles(con, now):
    """已有 daily_kline 是以前拉到的 K 线，可以进 token_candle。

    这不是新的回填成功，所以不写 kline_backfilled_at。
    """
    con.execute(
        """INSERT OR IGNORE INTO token_candle(
             chain, address, candle_open_ts, open, high, low, close, volume, fetched_at, is_closed)
           SELECT d.chain, d.address, d.ts,
                  CAST(NULLIF(d.open, '') AS REAL),
                  CAST(NULLIF(d.high, '') AS REAL),
                  CAST(NULLIF(d.low, '') AS REAL),
                  CAST(NULLIF(d.close, '') AS REAL),
                  CAST(NULLIF(d.volume, '') AS REAL),
                  COALESCE(
                    (SELECT t.kline_fetched_at FROM tokens t WHERE t.chain=d.chain AND t.address=d.address),
                    d.ts
                  ),
                  CASE WHEN d.ts + ? <= ? THEN 1 ELSE 0 END
           FROM daily_kline d""",
        (DAY_SEC, int(now)),
    )


def _fill_snapshot_numbers(con):
    con.execute(
        """UPDATE token_snapshot
           SET liquidity_num = CAST(liquidity AS REAL)
           WHERE liquidity_num IS NULL AND liquidity IS NOT NULL AND liquidity != ''"""
    )
    con.execute(
        """UPDATE token_snapshot
           SET liquidity_updated_at = ts
           WHERE liquidity_updated_at IS NULL AND ts IS NOT NULL"""
    )


def _rebuild_metrics(con, now):
    tokens = con.execute("SELECT chain, address FROM token_registry").fetchall()
    for row in tokens:
        refresh_metrics(con, row["chain"], row["address"], now)


def migrate(con):
    """初始化时补列、种子 registry。重复调用不再改首次字段，也不再 ALTER。"""
    for col, decl in (
        ("pc_24h", "TEXT"), ("holders", "INTEGER"), ("price_ds", "TEXT"),
        ("volume_ds", "TEXT"), ("liquidity_ds", "TEXT"), ("dex_price", "TEXT"),
        ("diverge", "INTEGER"), ("anchor_bid", "TEXT"), ("anchor_ask", "TEXT"),
        ("anchor_generated_at", "INTEGER"), ("anchor_multiplier", "TEXT"),
        ("halt", "INTEGER"), ("market_closed", "INTEGER"), ("oracle_price", "TEXT"),
        ("oracle_updated_at", "INTEGER"), ("smart_degen_count", "INTEGER"),
        ("sniper_count", "INTEGER"), ("renowned_count", "INTEGER"),
        ("top10_holder_rate", "TEXT"), ("rat_trader_rate", "TEXT"),
        ("bundler_rate", "TEXT"), ("swaps", "INTEGER"), ("commit_ok", "INTEGER"),
        ("chg_price", "INTEGER"), ("chg_volume", "INTEGER"), ("chg_liquidity", "INTEGER"),
        ("security_note", "TEXT"), ("liquidity_num", "REAL"), ("liquidity_updated_at", "INTEGER"),
    ):
        _ensure_column(con, "token_snapshot", col, decl)
    for col, decl in (
        ("logo", "TEXT"), ("token_created_at", "INTEGER"), ("pair_created_at", "INTEGER"),
        ("first_seen_at", "INTEGER"), ("kline_fetched_at", "INTEGER"),
    ):
        _ensure_column(con, "tokens", col, decl)
    for col, decl in (
        ("rows_parsed", "INTEGER NOT NULL DEFAULT 0"),
        ("rows_written", "INTEGER NOT NULL DEFAULT 0"),
        ("new_addresses", "INTEGER NOT NULL DEFAULT 0"),
        ("events_written", "INTEGER NOT NULL DEFAULT 0"),
        ("request_ok", "INTEGER NOT NULL DEFAULT 0"),
        ("run_state", "TEXT"),
    ):
        _ensure_column(con, "source_health", col, decl)
    _repair_clocks(con)
    # 旧快照里低于 50k 的当前值只说明「当时看到它还没到 50k」。
    # 不写 first_liquidity_50k_at，所以不能把它当成历史首次突破时间。
    # 下一次真实观测到 >= 50k 才记 observed_crossing，时间是那一次观测。
    if db.meta_get(con, "phase1_below_noted") != "1":
        con.execute(
            """UPDATE token_registry
               SET seen_liquidity_below_50k = 1
               WHERE first_liquidity_50k_at IS NULL
                 AND seen_liquidity_below_50k = 0
                 AND EXISTS (
                   SELECT 1 FROM token_snapshot s
                   WHERE s.chain = token_registry.chain
                     AND s.address = token_registry.address
                     AND COALESCE(s.liquidity_num, CAST(NULLIF(s.liquidity, '') AS REAL)) < ?
                 )""",
            (LIQUIDITY_THRESHOLD,),
        )
        db.meta_set(con, "phase1_below_noted", "1")
    if db.meta_get(con, "phase1_migrated") == "1":
        con.commit()
        return
    now = int(time.time())
    _fill_snapshot_numbers(con)
    _seed_registry(con, now)
    _copy_candles(con, now)
    _rebuild_metrics(con, now)
    db.meta_set(con, "phase1_migrated", "1")
    db.meta_set(con, "phase1_legacy_note", LEGACY_NOTE)
    con.commit()


def evidence(con, now=None):
    now = int(time.time() if now is None else now)
    def one(sql, args=()):
        row = con.execute(sql, args).fetchone()
        if row is None:
            return None
        return row[0]

    chains = con.execute(
        "SELECT chain, COUNT(*) AS n FROM token_registry GROUP BY chain ORDER BY chain"
    ).fetchall()
    sources = con.execute(
        "SELECT first_source, COUNT(*) AS n FROM token_registry GROUP BY first_source ORDER BY n DESC"
    ).fetchall()
    health = con.execute(
        """SELECT source, chain, run_state, rows_received, rows_parsed, rows_written,
                  new_addresses, events_written, request_ok, last_error, consecutive_errors
           FROM source_health
           WHERE source IN ('gmgn','gmgn_hot','gmgn_new_pair','gmgn_signal','gmgn_kline')
           ORDER BY source, chain"""
    ).fetchall()
    return {
        "now": now,
        "legacy_note": db.meta_get(con, "phase1_legacy_note"),
        "registry_total": one("SELECT COUNT(*) FROM token_registry"),
        "registry_by_chain": [dict(r) for r in chains],
        "first_source": [dict(r) for r in sources],
        "multi_source": one(
            """SELECT COUNT(*) FROM token_registry
               WHERE json_valid(sources_seen) AND json_array_length(sources_seen) > 1"""
        ),
        "observed_crossing": one(
            "SELECT COUNT(*) FROM token_registry WHERE liquidity_50k_observation_type=?",
            (OBS_CROSSING,),
        ),
        "first_observed_above": one(
            "SELECT COUNT(*) FROM token_registry WHERE liquidity_50k_observation_type=?",
            (OBS_FIRST_ABOVE,),
        ),
        "pending_kline": one(
            """SELECT COUNT(*) FROM token_registry
               WHERE first_liquidity_50k_at IS NOT NULL AND kline_backfilled_at IS NULL"""
        ),
        "backfilled": one(
            "SELECT COUNT(*) FROM token_registry WHERE kline_backfilled_at IS NOT NULL"
        ),
        "retry_pending": one(
            """SELECT COUNT(*) FROM token_registry
               WHERE kline_retry_after IS NOT NULL AND kline_backfilled_at IS NULL"""
        ),
        "events": one("SELECT COUNT(*) FROM discovery_event"),
        "events_by_source": [
            dict(r) for r in con.execute(
                "SELECT source, COUNT(*) AS n FROM discovery_event GROUP BY source"
            )
        ],
        "candles": one("SELECT COUNT(*) FROM token_candle"),
        "candle_fetched_min": one("SELECT MIN(fetched_at) FROM token_candle"),
        "candle_fetched_max": one("SELECT MAX(fetched_at) FROM token_candle"),
        "daily_metrics": one("SELECT COUNT(*) FROM daily_metrics"),
        "cooldown_start": db.meta_get(con, "gmgn_cooldown_start"),
        "cooldown_until": db.meta_get(con, "gmgn_cooldown_until"),
        "cooldown_basis": db.meta_get(con, "gmgn_cooldown_basis"),
        "health": [dict(r) for r in health],
    }
