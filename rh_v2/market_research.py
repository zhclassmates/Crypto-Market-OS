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
# EARLY 观察池下限。EARLY 只读已有 snapshot / discovery_event 事实，不进日 K 队列。
EARLY_LIQUIDITY_FLOOR = 20000
TIER_MAIN = "MAIN"
TIER_EARLY = "EARLY"
TIER_IGNORE = "IGNORE"
LIQUIDITY_FRESHNESS_SEC = 300
DISCOVERY_BUCKET_SEC = 300
DAY_SEC = 86400
LOW_BASE_CLOSE = 1e-8
EXTREME_ABS_RETURN = 50
KLINE_REPAIR_BATCH = 8
# 一次日 K 请求回看多远。market_collect.upsert_daily_kline 用同一个值。
KLINE_FETCH_WINDOW_SEC = 100 * DAY_SEC
STATUS_OPEN = "OPEN"
STATUS_PROVISIONAL = "PROVISIONAL"
STATUS_FINALIZED = "FINALIZED"
STREAK_POSITIVE = "POSITIVE_STREAK"
STREAK_ZERO = "VALID_ZERO"
STREAK_INSUFFICIENT = "INSUFFICIENT_DATA"
# rebuild_research_facts / migrate 写入。重复 migrate 看到这个值就不再全表重算。
CANDLE_FINALIZED_CONTRACT = "observed_at_ge_bar_end_v1"
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


def utc_day_start(now):
    now = int(now)
    return now - now % DAY_SEC


def bar_end(ts):
    return int(ts) + DAY_SEC


def observation_proves_final(bar_open, observed_at):
    """历史日 K 是否 FINALIZED，只由这根 bar 的观测时间决定。

    合同：observed_at >= bar_end，且这根 bar 落在该次日 K 请求的回看窗口里。
    读数时刻、迁移时刻、'今天已经是以后了' 都不能代入。
    缺观测时间 → 不能定稿。
    """
    if observed_at is None:
        return False
    try:
        opened = int(bar_open)
        obs = int(observed_at)
    except (TypeError, ValueError):
        return False
    if obs < opened + DAY_SEC:
        return False
    if opened < obs - KLINE_FETCH_WINDOW_SEC:
        return False
    return True


def bar_eligible_by_creation(bar_ts, created_at):
    """bar 所在 UTC 日 >= token 创建日。createdAt 不表示是否收盘。"""
    if created_at is None:
        return True
    try:
        created = int(created_at)
    except (TypeError, ValueError):
        return True
    if created <= 0:
        return True
    return int(bar_ts) >= utc_day_start(created)


def _source_closed(raw):
    if not isinstance(raw, dict):
        return False
    for key in ("closed", "is_closed", "final", "is_final"):
        val = raw.get(key)
        if val in (True, 1, "1", "true", "TRUE", "final", "closed"):
            return True
    return False


def bar_status(ts, fetched_at, now, finalized_at=None, source_closed=False):
    """FINALIZED 只看观测时间。source_closed 不能在没有观测时间时猜定稿。

    now 只用来区分今天还没收盘的 OPEN 和已经过了日历的 PROVISIONAL。
    读数时刻不得把盘中 bar 定稿。
    """
    del source_closed
    if bar_end(ts) > int(now):
        return STATUS_OPEN
    if observation_proves_final(ts, finalized_at) or observation_proves_final(ts, fetched_at):
        return STATUS_FINALIZED
    return STATUS_PROVISIONAL


def _finalized_at_for_write(opened, now, source_closed):
    """now 是这一次抓取的观测时间，不是迁移执行时间。"""
    now = int(now)
    if source_closed and observation_proves_final(opened, now):
        return now
    if observation_proves_final(opened, now):
        return now
    return None


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


# 当前流动性：与 pick_kline_repair 同一口径。
SNAPSHOT_LIQ_SQL = "COALESCE(s.liquidity_num, CAST(NULLIF(s.liquidity, '') AS REAL))"
# MAIN = 现有日 K 队列门槛：已观测到 50k、已回填，或当前流动性 >= 50k。
# 曾经进过 MAIN 的 token 流动性回落后仍是 MAIN，不丢已回填的历史。
MAIN_TIER_SQL = (
    f"(r.first_liquidity_50k_at IS NOT NULL OR r.kline_backfilled_at IS NOT NULL"
    f" OR {SNAPSHOT_LIQ_SQL} >= {LIQUIDITY_THRESHOLD})"
)
EARLY_TIER_SQL = (
    f"(NOT {MAIN_TIER_SQL} AND {SNAPSHOT_LIQ_SQL} >= {EARLY_LIQUIDITY_FLOOR})"
)
TIER_SQL = (
    f"CASE WHEN {MAIN_TIER_SQL} THEN '{TIER_MAIN}'"
    f" WHEN {EARLY_TIER_SQL} THEN '{TIER_EARLY}' ELSE '{TIER_IGNORE}' END"
)


def liquidity_tier(reg, liquidity):
    """MAIN / EARLY / IGNORE。派生值，不落库；和 TIER_SQL 同一规则。"""
    if reg is not None and (_field(reg, "first_liquidity_50k_at") or _field(reg, "kline_backfilled_at")):
        return TIER_MAIN
    liq = as_real(liquidity)
    if liq is None:
        return TIER_IGNORE
    if liq >= LIQUIDITY_THRESHOLD:
        return TIER_MAIN
    if liq >= EARLY_LIQUIDITY_FLOOR:
        return TIER_EARLY
    return TIER_IGNORE


def tier_counts(con):
    rows = con.execute(
        f"""SELECT {TIER_SQL} AS tier, COUNT(*) AS n
            FROM token_registry r
            LEFT JOIN token_snapshot s ON s.chain=r.chain AND s.address=r.address
            GROUP BY tier"""
    ).fetchall()
    out = {TIER_MAIN: 0, TIER_EARLY: 0, TIER_IGNORE: 0}
    for row in rows:
        out[row[0]] = row[1]
    return out


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
        "launchpad_platform", "holder_count", "volume_24h", "swaps_24h",
        # V1 活跃度历史：按事件保存 24h 笔数/量与 1h 涨跌（笔数不是人数）。
        "volume", "swaps", "buys", "sells", "buys_24h", "sells_24h",
        "price_change_percent1h", "trigger_mc",
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
    每根有自己的 fetched_at。日历收盘且本次抓取发生在 bar.end 之后才写 finalized_at。
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
        amount = as_real(raw.get("amount"))
        if high is None:
            high = close
        if low is None:
            low = close
        if open_ is None:
            open_ = close
        source_closed = _source_closed(raw)
        finalized_at = _finalized_at_for_write(opened, now, source_closed)
        is_closed = 1 if observation_proves_final(opened, now) else 0
        vol_text = "" if volume is None else str(volume)
        amt_text = None if amount is None else str(amount)
        con.execute(
            """INSERT INTO token_candle(
                 chain, address, candle_open_ts, open, high, low, close, volume, amount,
                 fetched_at, finalized_at, is_closed)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(chain, address, candle_open_ts) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low,
                 close=excluded.close, volume=excluded.volume, amount=excluded.amount,
                 fetched_at=excluded.fetched_at,
                 is_closed=CASE
                   WHEN COALESCE(excluded.finalized_at, token_candle.finalized_at) IS NOT NULL THEN 1
                   ELSE 0
                 END,
                 finalized_at=COALESCE(excluded.finalized_at, token_candle.finalized_at)""",
            (chain, address, opened, open_, high, low, close, volume, amount, now, finalized_at, is_closed),
        )
        con.execute(
            """INSERT INTO daily_kline(
                 chain, address, ts, open, high, low, close, volume, amount, fetched_at, finalized_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(chain, address, ts) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low,
                 close=excluded.close, volume=excluded.volume, amount=excluded.amount,
                 fetched_at=excluded.fetched_at,
                 finalized_at=COALESCE(excluded.finalized_at, daily_kline.finalized_at)""",
            (
                chain, address, opened, str(open_), str(high), str(low), str(close),
                vol_text, amt_text, now, finalized_at,
            ),
        )
        written += 1
    return written


def schedule_kline_retry(con, chain, address, now, delay=120):
    con.execute(
        """UPDATE token_registry SET kline_retry_after=?
           WHERE chain=? AND address=?""",
        (int(now) + int(delay), chain, address),
    )


def kline_repair_delay(now):
    """UTC 日切后 00:02 / 00:07 / 00:15 的等价退避。"""
    age = int(now) - utc_day_start(now)
    if age < 120:
        return 120 - age
    if age < 420:
        return 420 - age
    if age < 900:
        return 900 - age
    return 900


def yesterday_open(now):
    return utc_day_start(now) - DAY_SEC


def last_finalized_open(con, chain, address, now):
    rows = con.execute(
        """SELECT candle_open_ts, fetched_at, finalized_at FROM token_candle
           WHERE chain=? AND address=? AND close IS NOT NULL AND close>0
           ORDER BY candle_open_ts""",
        (chain, address),
    ).fetchall()
    last = None
    for row in rows:
        ts = int(row["candle_open_ts"])
        status = bar_status(ts, row["fetched_at"], now, row["finalized_at"])
        if status == STATUS_FINALIZED:
            last = ts
    return last


def needs_yesterday_finalize(con, chain, address, now):
    yesterday = yesterday_open(now)
    today = utc_day_start(now)
    row = con.execute(
        """SELECT candle_open_ts, fetched_at, finalized_at, close FROM token_candle
           WHERE chain=? AND address=? AND candle_open_ts=?""",
        (chain, address, yesterday),
    ).fetchone()
    if row is None:
        tok = con.execute(
            "SELECT kline_fetched_at FROM tokens WHERE chain=? AND address=?",
            (chain, address),
        ).fetchone()
        fetched = tok["kline_fetched_at"] if tok else None
        return fetched is None or int(fetched) < today
    if row["close"] is None:
        return True
    status = bar_status(row["candle_open_ts"], row["fetched_at"], now, row["finalized_at"])
    return status != STATUS_FINALIZED


def pick_kline_repair(con, chain, now, limit=KLINE_REPAIR_BATCH):
    """优先补：流动性>=50k / 正式榜候选 / 已回填研究币，且昨日 K 未 FINALIZED。"""
    yesterday = yesterday_open(now)
    today = utc_day_start(now)
    rows = con.execute(
        """SELECT r.address,
                  COALESCE(s.liquidity_num, CAST(NULLIF(s.liquidity, '') AS REAL)) AS liq,
                  r.first_liquidity_50k_at,
                  r.kline_backfilled_at,
                  r.kline_retry_after,
                  t.kline_fetched_at,
                  c.fetched_at AS y_fetched,
                  c.finalized_at AS y_finalized,
                  c.candle_open_ts AS y_ts
           FROM token_registry r
           LEFT JOIN token_snapshot s ON s.chain=r.chain AND s.address=r.address
           LEFT JOIN tokens t ON t.chain=r.chain AND t.address=r.address
           LEFT JOIN token_candle c
             ON c.chain=r.chain AND c.address=r.address AND c.candle_open_ts=?
           WHERE r.chain=?
             AND (r.kline_retry_after IS NULL OR r.kline_retry_after <= ?)
             AND (
               r.first_liquidity_50k_at IS NOT NULL
               OR COALESCE(s.liquidity_num, CAST(NULLIF(s.liquidity, '') AS REAL)) >= ?
               OR r.kline_backfilled_at IS NOT NULL
             )
             AND (
               (c.candle_open_ts IS NULL AND (t.kline_fetched_at IS NULL OR t.kline_fetched_at < ?))
               OR (c.candle_open_ts IS NOT NULL AND (c.fetched_at IS NULL OR c.fetched_at < ?))
             )
           ORDER BY
             CASE WHEN COALESCE(s.liquidity_num, CAST(NULLIF(s.liquidity, '') AS REAL)) >= ? THEN 0 ELSE 1 END,
             CASE WHEN r.first_liquidity_50k_at IS NOT NULL THEN 0 ELSE 1 END,
             COALESCE(r.kline_retry_after, 0)
           LIMIT ?""",
        (yesterday, chain, int(now), LIQUIDITY_THRESHOLD, today, today, LIQUIDITY_THRESHOLD, int(limit)),
    ).fetchall()
    out = []
    for row in rows:
        if row["y_ts"] is None:
            if row["kline_backfilled_at"] is None and row["liq"] is not None and row["liq"] < LIQUIDITY_THRESHOLD:
                continue
            out.append(row["address"])
            continue
        status = bar_status(row["y_ts"], row["y_fetched"], now, row["y_finalized"])
        if status != STATUS_FINALIZED:
            out.append(row["address"])
    return out


def note_kline_repair_state(con, chain, address, now):
    """拉取成功后若昨日仍未定稿，继续进修复队列；已定稿则清 retry。"""
    if needs_yesterday_finalize(con, chain, address, now):
        schedule_kline_retry(con, chain, address, now, kline_repair_delay(now))
        return False
    con.execute(
        """UPDATE token_registry SET kline_retry_after=NULL, updated_at=?
           WHERE chain=? AND address=? AND kline_backfilled_at IS NOT NULL""",
        (int(now), chain, address),
    )
    return True


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
        """UPDATE token_registry SET kline_backfilled_at=?, updated_at=?
           WHERE chain=? AND address=?""",
        (now, now, chain, address),
    )
    db.touch_kline_fetched(con, chain, address, now)
    note_kline_repair_state(con, chain, address, now)
    refresh_metrics(con, chain, address, now)
    return written


def classified_candle_rows(con, chain, address, now, created_at=None):
    rows = con.execute(
        """SELECT candle_open_ts, high, close, fetched_at, finalized_at FROM token_candle
           WHERE chain=? AND address=? AND close IS NOT NULL AND close>0
           ORDER BY candle_open_ts""",
        (chain, address),
    ).fetchall()
    out = []
    seen = set()
    for row in rows:
        ts = int(row["candle_open_ts"])
        if ts in seen:
            continue
        seen.add(ts)
        if not bar_eligible_by_creation(ts, created_at):
            continue
        close = float(row["close"])
        high = float(row["high"]) if row["high"] is not None else close
        status = bar_status(ts, row["fetched_at"], now, row["finalized_at"])
        out.append({
            "ts": ts,
            "close": close,
            "high": high,
            "fetched_at": row["fetched_at"],
            "finalized_at": row["finalized_at"],
            "status": status,
        })
    return out


def closed_candle_rows(con, chain, address, now, created_at=None):
    """正式指标只用 FINALIZED 日 K。PROVISIONAL 保留在库里，不进这列。"""
    out = []
    for row in classified_candle_rows(con, chain, address, now, created_at):
        if row["status"] != STATUS_FINALIZED:
            continue
        out.append((row["ts"], row["close"], row["high"]))
    return out


def official_tail_finalized(classified):
    calendar = [row for row in classified if row["status"] != STATUS_OPEN]
    if not calendar:
        return True
    return calendar[-1]["status"] == STATUS_FINALIZED


def streak_from_closed(closed):
    """与 src/lib/rh/streak.ts calcStreak 相同：只比较相邻已收盘日，平盘和缺天都中断。

    最后一根没有相邻的前一日 close（不足两根、或前一天缺），没有证据，返回 None。
    None 是 INSUFFICIENT_DATA，0 是 VALID_ZERO（最后一天明确没涨）。
    """
    if len(closed) < 2 or closed[-1][0] - closed[-2][0] != DAY_SEC:
        return None
    streak = 0
    for i in range(len(closed) - 1, 0, -1):
        if closed[i][0] - closed[i - 1][0] != DAY_SEC:
            break
        if closed[i][1] > closed[i - 1][1]:
            streak += 1
        else:
            break
    return streak


def streak_status(closed):
    streak = streak_from_closed(closed)
    if streak is None:
        return STREAK_INSUFFICIENT
    if streak >= 1:
        return STREAK_POSITIVE
    return STREAK_ZERO


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
    """qualified_at：第一次同时满足下面六条的时间。

    1. 已在 token_registry
    2. 已有 50k 观察（observed_crossing 或 first_observed_above 均可，两者仍分开存）
    3. K 线回填已成功
    4. 至少两根相邻的 FINALIZED 日 K，连涨比较有定义（结果可以是 0）
    5. 当前流动性新鲜（年龄 <= 300 秒）
    6. 当前流动性 >= 50000
    return_2d/3d/5d 缺数据时保持 NULL，不因此阻止 qualified_at。

    实时路径：一旦写入就 sticky，流动性跌破不清掉。
    修复路径：如果连第 4 条（相邻 FINALIZED 日 K）都不成立，旧值必须清掉。
    """
    if reg is None:
        return False
    if not reg["first_liquidity_50k_at"] or not reg["kline_backfilled_at"]:
        return False
    if not _has_streak_window(closed):
        return False
    return formal_eligible(liquidity, age_sec)


def as_of_date(finalized_open):
    """指标实际使用的最后一根 FINALIZED 日 K；无定稿输入时为空。"""
    if finalized_open is None:
        # daily_metrics 的旧 schema 是 NOT NULL；空串明确表示没有 as-of 日，
        # 不能拿运行日、请求日或 OPEN/PROVISIONAL bar 的日期冒充。
        return ""
    return time.strftime("%Y-%m-%d", time.gmtime(int(finalized_open)))


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


def refresh_metrics(con, chain, address, now, repair_qualified=False):
    """正式研究指标只走 FINALIZED 日 K。repair_qualified 会按当前 finalized 事实重写 qualified_at。"""
    reg = con.execute(
        "SELECT * FROM token_registry WHERE chain=? AND address=?",
        (chain, address),
    ).fetchone()
    if reg is None:
        return None
    now = int(now)
    created = None
    tok = con.execute(
        "SELECT token_created_at FROM tokens WHERE chain=? AND address=?",
        (chain, address),
    ).fetchone()
    if tok and tok["token_created_at"]:
        created = tok["token_created_at"]
    elif reg["token_created_at"]:
        created = reg["token_created_at"]
    classified = classified_candle_rows(con, chain, address, now, created)
    closed = [(row["ts"], row["close"], row["high"]) for row in classified if row["status"] == STATUS_FINALIZED]
    liq, updated = _snapshot_liq(con, chain, address)
    age = None if updated is None else now - int(updated)
    if official_tail_finalized(classified):
        r2, r3, r5 = returns_from_closed(closed)
        streak = streak_from_closed(closed)
    else:
        r2, r3, r5 = None, None, None
        streak = None
    eligible = 1 if formal_eligible(liq, age) else 0
    qualified = reg["qualified_at"]
    if repair_qualified and not _has_streak_window(closed):
        if qualified is not None:
            con.execute(
                """UPDATE token_registry SET qualified_at=NULL, updated_at=?
                   WHERE chain=? AND address=?""",
                (now, chain, address),
            )
        qualified = None
    elif qualified is None and can_qualify(reg, closed, liq, age):
        qualified = now
        con.execute(
            """UPDATE token_registry SET qualified_at=?, updated_at=?
               WHERE chain=? AND address=? AND qualified_at IS NULL""",
            (qualified, now, chain, address),
        )
    qualified_sql = (
        "qualified_at=excluded.qualified_at"
        if repair_qualified
        else "qualified_at=COALESCE(daily_metrics.qualified_at, excluded.qualified_at)"
    )
    metric_as_of = as_of_date(closed[-1][0] if closed else None)
    # daily_metrics 是每个 token 的当前物化结果，不保留会参与集合统计的旧行。
    # as_of 日推进或回退时先移除旧 key，避免旧 positive streak 残留。
    con.execute(
        "DELETE FROM daily_metrics WHERE chain=? AND address=? AND as_of_date<>?",
        (chain, address, metric_as_of),
    )
    con.execute(
        f"""INSERT INTO daily_metrics(
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
             {qualified_sql},
             calculated_at=excluded.calculated_at""",
        (
            chain, address, metric_as_of, streak, r2, r3, r5,
            liq, age, eligible, qualified, now,
        ),
    )
    return {
        "streak": streak,
        "streak_status": streak_status(closed) if official_tail_finalized(classified) else STREAK_INSUFFICIENT,
        "return_2d": r2,
        "return_3d": r3,
        "return_5d": r5,
        "eligible": eligible,
        "qualified_at": qualified,
    }


def daily_metrics_fresh(calculated_at, now):
    """物化指标只在计算发生于当前 UTC 日时可直接消费。"""
    if calculated_at is None:
        return False
    try:
        calculated = int(calculated_at)
        current = int(now)
    except (TypeError, ValueError):
        return False
    return utc_day_start(current) <= calculated <= current


def refresh_daily_metrics_for_utc_day(con, now):
    """UTC 日切时刷新所有物化指标；同一 UTC 日重复调用是 no-op。

    日切本身会把昨天的 OPEN 变为 PROVISIONAL，即使数据库没有新写入，
    所以不能只在 token/Kline 写入时刷新。历史 replay 也按传入的 now 判定，
    不读取墙上时钟。
    """
    now = int(now)
    day = as_of_date(utc_day_start(now))
    if db.meta_get(con, "daily_metrics_refresh_utc_day") == day:
        return 0
    rows = con.execute("SELECT chain, address FROM token_registry").fetchall()
    for row in rows:
        refresh_metrics(con, row["chain"], row["address"], now)
    db.meta_set(con, "daily_metrics_refresh_utc_day", day)
    db.meta_set(con, "daily_metrics_refreshed_at", str(now))
    return len(rows)


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


def normalize_trench_row(row):
    """映射 Phase 2 实测的 Trenches 24h 字段，不做任何推导。

    key 缺失保持缺失，显式 null 保持 null，数值 0 保持 0。
    """
    if not isinstance(row, dict):
        return {}
    out = dict(row)
    if "volume_24h" in row:
        out["volume"] = row["volume_24h"]
    if "swaps_24h" in row:
        out["swaps"] = row["swaps_24h"]
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
        parsed = {
            "address": address,
            "symbol": item.get("symbol") or snap.get("symbol") or cur.get("symbol"),
            "name": item.get("name") or snap.get("name"),
            "signal_type": item.get("signal_type"),
            "token_created_at": created,
            "rank": item.get("rank"),
        }
        if "liquidity" in cur:
            parsed["liquidity"] = cur["liquidity"]
        elif "liquidity" in snap:
            parsed["liquidity"] = snap["liquidity"]
        if "holder_count" in cur:
            parsed["holder_count"] = cur["holder_count"]
        if "top_10_holder_rate" in cur:
            parsed["top_10_holder_rate"] = cur["top_10_holder_rate"]
        if "market_cap" in item:
            parsed["market_cap"] = item["market_cap"]
        elif "market_cap" in snap:
            parsed["market_cap"] = snap["market_cap"]
        # 信号事件本身的时间与触发市值，只进 discovery_event 元数据。
        if "trigger_at" in item:
            parsed["trigger_at"] = item["trigger_at"]
        if "trigger_mc" in item:
            parsed["trigger_mc"] = item["trigger_mc"]
        # Signal 的 price 路径在 Phase 2 未出现，activity 字段又是 zero-only。
        # 它们都不是此 endpoint 的 canonical snapshot 字段。
        out.append(parsed)
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


def _observed_at_sql(bar_ts_expr, fetched_expr, token_fetched_expr):
    """一条 SQL 表达式：这根 bar 的观测时间。迁移 now 不能出现。"""
    return f"""CASE
      WHEN {fetched_expr} IS NOT NULL
       AND {bar_ts_expr} >= {fetched_expr} - :window THEN {fetched_expr}
      WHEN {token_fetched_expr} IS NOT NULL
       AND {bar_ts_expr} >= {token_fetched_expr} - :window THEN {token_fetched_expr}
    END"""


def _proves_sql(bar_ts_expr, observed_expr):
    return (
        f"{observed_expr} IS NOT NULL "
        f"AND {observed_expr} >= {bar_ts_expr} + :day "
        f"AND {bar_ts_expr} >= {observed_expr} - :window"
    )


def _backfill_per_bar_fetched(con):
    """把 canonical token_candle 的较新逐 bar 观测同步到 daily_kline。

    旧 collector 会更新 token_candle.fetched_at，但 daily_kline 当时还没有逐 bar
    时间列。后来 migration 写入的非空盘中时间不能挡住真实的收盘后重抓时间。
    这里只复制已经存在的观测事实；定稿仍由 rebuild_candle_finalized 按
    observed_at >= bar_end 统一写，migration/read 的当前时间不参与。
    """
    con.execute(
        """UPDATE daily_kline
           SET fetched_at = (
             SELECT tc.fetched_at FROM token_candle tc
             WHERE tc.chain = daily_kline.chain
               AND tc.address = daily_kline.address
               AND tc.candle_open_ts = daily_kline.ts
           )
           WHERE EXISTS (
             SELECT 1 FROM token_candle tc
             WHERE tc.chain = daily_kline.chain
               AND tc.address = daily_kline.address
               AND tc.candle_open_ts = daily_kline.ts
               AND tc.fetched_at IS NOT NULL
               AND (daily_kline.fetched_at IS NULL OR tc.fetched_at > daily_kline.fetched_at)
           )"""
    )


def _copy_candles(con, now):
    """已有 daily_kline 是以前拉到的 K 线，可以进 token_candle。

    这不是新的回填成功，所以不写 kline_backfilled_at。

    是否收盘只看当时那次观测：observed_at >= bar_end。observed_at 优先用
    这根 daily_kline 自己的 fetched_at；没有则用 token 最后一次成功拉日 K
    的时间，且这根 bar 必须落在那次请求的 100 天窗口里。
    迁移执行时间 now 不参与判断：同一根 bar 今天迁、明天迁，结果一样。
    没有可证明的观测时间就留 NULL，不收盘、不定稿。
    """
    del now  # 迁移时间不能决定历史 bar 的状态
    observed = _observed_at_sql("d.ts", "d.fetched_at", "t.kline_fetched_at")
    proves = _proves_sql("d.ts", observed)
    con.execute(
        f"""INSERT OR IGNORE INTO token_candle(
             chain, address, candle_open_ts, open, high, low, close, volume,
             fetched_at, finalized_at, is_closed)
           SELECT d.chain, d.address, d.ts,
                  CAST(NULLIF(d.open, '') AS REAL),
                  CAST(NULLIF(d.high, '') AS REAL),
                  CAST(NULLIF(d.low, '') AS REAL),
                  CAST(NULLIF(d.close, '') AS REAL),
                  CAST(NULLIF(d.volume, '') AS REAL),
                  {observed},
                  CASE WHEN {proves} THEN {observed} END,
                  CASE WHEN {proves} THEN 1 ELSE 0 END
           FROM daily_kline d
           LEFT JOIN tokens t ON t.chain = d.chain AND t.address = d.address""",
        {"day": DAY_SEC, "window": KLINE_FETCH_WINDOW_SEC},
    )


def rebuild_candle_finalized(con):
    """按 observed_at >= bar_end 重写 token_candle / daily_kline 的定稿字段。

    不读 current time。窗口外的 fetched_at 不能证明这根 bar，清掉定稿。
    同一批历史 candle 无论哪天跑，结果一样。
    """
    params = {"day": DAY_SEC, "window": KLINE_FETCH_WINDOW_SEC}
    tc_obs = _observed_at_sql(
        "token_candle.candle_open_ts",
        "token_candle.fetched_at",
        "(SELECT t.kline_fetched_at FROM tokens t "
        "WHERE t.chain = token_candle.chain AND t.address = token_candle.address)",
    )
    tc_proves = _proves_sql("token_candle.candle_open_ts", tc_obs)
    con.execute(
        f"""UPDATE token_candle
            SET fetched_at = {tc_obs},
                finalized_at = CASE WHEN {tc_proves} THEN {tc_obs} END,
                is_closed = CASE WHEN {tc_proves} THEN 1 ELSE 0 END""",
        params,
    )
    dk_obs = _observed_at_sql(
        "daily_kline.ts",
        "daily_kline.fetched_at",
        "(SELECT t.kline_fetched_at FROM tokens t "
        "WHERE t.chain = daily_kline.chain AND t.address = daily_kline.address)",
    )
    dk_proves = _proves_sql("daily_kline.ts", dk_obs)
    con.execute(
        f"""UPDATE daily_kline
            SET fetched_at = {dk_obs},
                finalized_at = CASE WHEN {dk_proves} THEN {dk_obs} END""",
        params,
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


def _rebuild_metrics(con, now, repair_qualified=False):
    tokens = con.execute("SELECT chain, address FROM token_registry").fetchall()
    for row in tokens:
        refresh_metrics(
            con, row["chain"], row["address"], now, repair_qualified=repair_qualified,
        )


def rebuild_research_facts(con, now=None):
    """正式修复入口：candle finalized → daily_metrics → streak / N 日 → qualified_at。

    不手工 UPDATE 派生结果。now 只写 as_of_date / OPEN 日历，不定历史 finalized。
    """
    now = int(time.time() if now is None else now)
    _copy_candles(con, now)
    _backfill_per_bar_fetched(con)
    rebuild_candle_finalized(con)
    _rebuild_metrics(con, now, repair_qualified=True)
    db.meta_set(con, "candle_finalized_contract", CANDLE_FINALIZED_CONTRACT)
    con.commit()
    return now


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
        ("price_source", "TEXT"), ("price_updated_at", "INTEGER"),
        ("pc_24h_source", "TEXT"), ("pc_24h_updated_at", "INTEGER"),
        ("volume_24h_source", "TEXT"), ("volume_24h_updated_at", "INTEGER"),
        ("liquidity_source", "TEXT"), ("market_cap_source", "TEXT"),
        ("market_cap_updated_at", "INTEGER"), ("holders_source", "TEXT"),
        ("holders_updated_at", "INTEGER"), ("swaps_source", "TEXT"),
        ("swaps_updated_at", "INTEGER"), ("security_json", "TEXT"),
        ("security_updated_at", "INTEGER"), ("security_is_honeypot", "INTEGER"),
        ("security_is_blacklist", "INTEGER"), ("security_is_open_source", "INTEGER"),
        ("security_is_renounced", "INTEGER"), ("security_top10_holder_rate", "TEXT"),
        ("buys_24h", "INTEGER"), ("buys_24h_source", "TEXT"), ("buys_24h_updated_at", "INTEGER"),
        ("sells_24h", "INTEGER"), ("sells_24h_source", "TEXT"), ("sells_24h_updated_at", "INTEGER"),
        ("pc_1h", "TEXT"), ("pc_1h_source", "TEXT"), ("pc_1h_updated_at", "INTEGER"),
        ("is_wash_trading", "INTEGER"), ("is_wash_trading_source", "TEXT"),
        ("is_wash_trading_updated_at", "INTEGER"),
        ("security_renounced_mint", "INTEGER"), ("security_renounced_freeze_account", "INTEGER"),
        ("security_sell_tax", "TEXT"),
    ):
        _ensure_column(con, "token_snapshot", col, decl)
    for col, decl in (
        ("logo", "TEXT"), ("token_created_at", "INTEGER"), ("pair_created_at", "INTEGER"),
        ("first_seen_at", "INTEGER"), ("kline_fetched_at", "INTEGER"),
    ):
        _ensure_column(con, "tokens", col, decl)
    for col, decl in (
        ("amount", "TEXT"), ("fetched_at", "INTEGER"), ("finalized_at", "INTEGER"),
    ):
        _ensure_column(con, "daily_kline", col, decl)
    for col, decl in (
        ("amount", "REAL"), ("finalized_at", "INTEGER"),
    ):
        _ensure_column(con, "token_candle", col, decl)
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
    now = int(time.time())
    if db.meta_get(con, "phase1_migrated") != "1":
        _fill_snapshot_numbers(con)
        _seed_registry(con, now)
        db.meta_set(con, "phase1_migrated", "1")
        db.meta_set(con, "phase1_legacy_note", LEGACY_NOTE)
    _copy_candles(con, now)
    _backfill_per_bar_fetched(con)
    if db.meta_get(con, "candle_finalized_contract") != CANDLE_FINALIZED_CONTRACT:
        rebuild_candle_finalized(con)
        _rebuild_metrics(con, now, repair_qualified=True)
        db.meta_set(con, "candle_finalized_contract", CANDLE_FINALIZED_CONTRACT)
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
        "tiers": tier_counts(con),
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
