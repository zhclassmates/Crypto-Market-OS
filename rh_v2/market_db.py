"""全市场 Token 排行数据库。"""
import os
import sqlite3

DB_PATH = os.environ.get("MARKET_DB", os.path.join(os.path.dirname(__file__), "market.sqlite"))

SCHEMA = """
PRAGMA journal_mode=WAL;

-- 代币基本信息。三个时间禁止互相填充：
-- token_created_at 代币创建，pair_created_at 池子创建，first_seen_at 我们第一次写入。
-- creation_ts 只镜像 token_created_at，留给旧的 N 日涨幅资格判断。
CREATE TABLE IF NOT EXISTS tokens (
    chain            TEXT NOT NULL,
    address          TEXT NOT NULL,
    symbol           TEXT,
    name             TEXT,
    logo             TEXT,
    creation_ts      INTEGER,
    token_created_at INTEGER,
    pair_created_at  INTEGER,
    first_seen_at    INTEGER,
    kline_fetched_at INTEGER,
    PRIMARY KEY (chain, address)
);

-- 小时级价格快照。锚定价 = 此表中 <= anchor_time 的最后一笔 price。
CREATE TABLE IF NOT EXISTS hourly_price (
    chain   TEXT NOT NULL,
    address TEXT NOT NULL,
    ts      INTEGER NOT NULL,    -- unix 秒，整点小时
    price   TEXT NOT NULL,       -- 美元价，字符串保留精度
    PRIMARY KEY (chain, address, ts)
);
CREATE INDEX IF NOT EXISTS ix_hp_addr_ts ON hourly_price(address, ts);

-- 日 K 线（用于连涨天数）。ts 是当日 UTC 00:00。
CREATE TABLE IF NOT EXISTS daily_kline (
    chain   TEXT NOT NULL,
    address TEXT NOT NULL,
    ts      INTEGER NOT NULL,
    open    TEXT, high TEXT, low TEXT, close TEXT, volume TEXT,
    PRIMARY KEY (chain, address, ts)
);
CREATE INDEX IF NOT EXISTS ix_dk_addr_ts ON daily_kline(address, ts);

-- 当前快照（price / volume_24h / liquidity / market_cap / holders / 24h涨幅）
CREATE TABLE IF NOT EXISTS token_snapshot (
    chain     TEXT NOT NULL,
    address   TEXT NOT NULL,
    ts        INTEGER NOT NULL,    -- 采集时间
    price     TEXT,
    pc_24h    TEXT,                -- GMGN price_change_percent，0.125 = +12.5%
    volume_24h TEXT,
    liquidity TEXT,
    market_cap TEXT,
    holders   INTEGER,
    PRIMARY KEY (chain, address)
);

CREATE TABLE IF NOT EXISTS market_meta (k TEXT PRIMARY KEY, v TEXT);

-- 每个 source × chain 一行。时间列禁止互相填充。
CREATE TABLE IF NOT EXISTS source_health (
    source TEXT NOT NULL,
    chain TEXT NOT NULL,
    period_sec INTEGER NOT NULL,
    collector_heartbeat INTEGER,
    last_attempt INTEGER,
    last_success INTEGER,
    round_ok INTEGER NOT NULL DEFAULT 0,
    source_timestamp INTEGER,
    source_timestamp_missing INTEGER NOT NULL DEFAULT 1,
    db_written_at INTEGER,
    ui_fetched_at INTEGER,
    last_change_at INTEGER,
    rows_received INTEGER NOT NULL DEFAULT 0,
    hot_changed INTEGER NOT NULL DEFAULT 0,
    cold_changed INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER,
    consecutive_errors INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    successes INTEGER NOT NULL DEFAULT 0,
    has_display_rows INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source, chain)
);

CREATE TABLE IF NOT EXISTS source_latency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    chain TEXT NOT NULL,
    ts INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_source_latency ON source_latency(source, chain, ts);

-- Phase 1 永久发现账本。掉榜、流动性跌破 50k 都不删除。
-- Legacy token_snapshot did not preserve liquidity history. Historical
-- first-liquidity-$50k timestamps before Phase 1 deployment cannot be
-- reconstructed reliably.
CREATE TABLE IF NOT EXISTS token_registry (
    chain TEXT NOT NULL,
    address TEXT NOT NULL,
    symbol TEXT,
    name TEXT,
    first_seen_at INTEGER,
    last_seen_at INTEGER,
    first_source TEXT,
    sources_seen TEXT,
    first_liquidity_50k_at INTEGER,
    liquidity_50k_observation_type TEXT,
    source_at_50k TEXT,
    kline_backfilled_at INTEGER,
    kline_retry_after INTEGER,
    qualified_at INTEGER,
    token_created_at INTEGER,
    token_created_at_source TEXT,
    seen_liquidity_below_50k INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER,
    PRIMARY KEY (chain, address)
);
CREATE INDEX IF NOT EXISTS ix_reg_liq50 ON token_registry(first_liquidity_50k_at);
CREATE INDEX IF NOT EXISTS ix_reg_qualified ON token_registry(qualified_at);
CREATE INDEX IF NOT EXISTS ix_reg_chain_seen ON token_registry(chain, first_seen_at);

-- 研究事实。同一 300 秒桶内同一来源只留一行，不是最后状态快照。
CREATE TABLE IF NOT EXISTS discovery_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain TEXT NOT NULL,
    address TEXT NOT NULL,
    source TEXT NOT NULL,
    source_variant TEXT NOT NULL DEFAULT '',
    seen_at INTEGER NOT NULL,
    time_bucket INTEGER NOT NULL,
    liquidity REAL,
    price REAL,
    market_cap REAL,
    rank INTEGER,
    metadata_json TEXT,
    UNIQUE (chain, address, source, source_variant, time_bucket)
);
CREATE INDEX IF NOT EXISTS ix_disc_addr_seen ON discovery_event(chain, address, seen_at);

CREATE TABLE IF NOT EXISTS token_candle (
    chain TEXT NOT NULL,
    address TEXT NOT NULL,
    candle_open_ts INTEGER NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    fetched_at INTEGER,
    is_closed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chain, address, candle_open_ts)
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    chain TEXT NOT NULL,
    address TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    streak INTEGER,
    return_2d REAL,
    return_3d REAL,
    return_5d REAL,
    liquidity REAL,
    liquidity_age_sec INTEGER,
    eligible INTEGER,
    qualified_at INTEGER,
    calculated_at INTEGER,
    UNIQUE (chain, address, as_of_date)
);
"""


def connect(path=None):
    """打开库。建表和一次性迁移只在这里做，请求路径不再 ALTER / UPDATE。"""
    con = sqlite3.connect(path or DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=10000")
    con.executescript(SCHEMA)
    con.execute("PRAGMA busy_timeout=10000")
    import market_research
    market_research.migrate(con)
    if con.in_transaction:
        con.commit()
    return con


def _iso_to_unix(text):
    from datetime import datetime
    raw = text.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    if "." in raw:
        head, tail = raw.split(".", 1)
        frac = []
        rest = []
        for i, ch in enumerate(tail):
            if ch.isdigit() and not rest:
                frac.append(ch)
            else:
                rest = list(tail[i:])
                break
        raw = head + "." + "".join(frac[:6]) + "".join(rest)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    try:
        return int(dt.timestamp())
    except (OverflowError, OSError, ValueError):
        return None


def _bucket_unix(n):
    """半开区间： [1e12, 1e15) 毫秒，[1e15, 1e17) 微秒，>=1e17 纳秒。"""
    if isinstance(n, float):
        if n != n or n in (float("inf"), float("-inf")) or n <= 0:
            return None
        if n >= 1e17:
            return int(n // 1_000_000_000)
        if n >= 1e15:
            return int(n // 1_000_000)
        if n >= 1e12:
            return int(n // 1000)
        return int(n)
    if n <= 0:
        return None
    if n >= 10**17:
        return n // 1_000_000_000
    if n >= 10**15:
        return n // 1_000_000
    if n >= 10**12:
        return n // 1000
    return int(n)


def unix_ts(v):
    """统一成 Unix 秒。失败返回 None，不抛异常。0 和负数是未知，不是 1970。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        text = v.strip()
        if not text:
            return None
        if "T" in text or (len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-"):
            return _iso_to_unix(text)
        if text[0] == "-":
            body = text[1:]
            if body.isdigit():
                return _bucket_unix(-int(body))
        if text.isdigit():
            return _bucket_unix(int(text))
        try:
            n = float(text)
        except ValueError:
            return None
        return _bucket_unix(n)
    if isinstance(v, int):
        return _bucket_unix(v)
    if isinstance(v, float):
        return _bucket_unix(v)
    return None


def rank_times(item):
    """从已经拉到的榜单行里拆时间。不把 open_timestamp 写进代币创建或池子创建。"""
    if not isinstance(item, dict):
        return None, None
    token_created = unix_ts(item.get("creation_timestamp"))
    pool = item.get("pool") if isinstance(item.get("pool"), dict) else {}
    pair_created = unix_ts(pool.get("creation_timestamp"))
    if pair_created is None:
        pair_created = unix_ts(item.get("pool_creation_timestamp"))
    if pair_created is None:
        pair_created = unix_ts(item.get("pair_created_at"))
    return token_created, pair_created


def upsert_token(con, chain, address, symbol, name, logo, token_created_at, pair_created_at, now):
    """first_seen_at 只在插入时写。冲突更新不补、不覆盖。"""
    con.execute(
        """INSERT INTO tokens(
             chain, address, symbol, name, logo, creation_ts,
             token_created_at, pair_created_at, first_seen_at)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(chain, address) DO UPDATE SET
             symbol=excluded.symbol,
             name=excluded.name,
             logo=excluded.logo,
             creation_ts=COALESCE(excluded.creation_ts, tokens.creation_ts),
             token_created_at=COALESCE(excluded.token_created_at, tokens.token_created_at),
             pair_created_at=COALESCE(excluded.pair_created_at, tokens.pair_created_at)""",
        (
            chain, address, symbol, name, logo,
            token_created_at, token_created_at, pair_created_at, int(now),
        ),
    )


def touch_kline_fetched(con, chain, address, now):
    con.execute(
        "UPDATE tokens SET kline_fetched_at=? WHERE chain=? AND address=?",
        (int(now), chain, address),
    )


def meta_get(con, k, default=None):
    r = con.execute("SELECT v FROM market_meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def meta_set(con, k, v):
    con.execute("INSERT OR REPLACE INTO market_meta(k,v) VALUES(?,?)", (k, str(v)))
