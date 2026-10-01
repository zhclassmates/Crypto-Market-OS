"""SQLite 结构。第一年百万行级，SQLite 足够；以后要换 Postgres 只改这里。"""
import sqlite3
from config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS tokens (
    address      TEXT PRIMARY KEY,           -- 小写合约地址
    symbol       TEXT, name TEXT,
    first_seen   INTEGER,                    -- 我们第一次看到它（unix 秒）
    pair_created INTEGER,                    -- 最早池子创建时间（unix 秒）
    top_pool     TEXT,                       -- 池深最大的池子地址
    dex          TEXT,
    source       TEXT                        -- gt_top / gt_new / extra
);

-- 原始小时快照：只存「当时能看到的」，不存算出来的东西
CREATE TABLE IF NOT EXISTS snapshots (
    ts INTEGER, address TEXT,
    price REAL, mcap REAL, fdv REAL, liq REAL,
    vol_h1 REAL, vol_h6 REAL, vol_h24 REAL,
    buys_h1 INTEGER, sells_h1 INTEGER, buys_h6 INTEGER, sells_h6 INTEGER,
    buys_h24 INTEGER, sells_h24 INTEGER,
    pc_h1 REAL, pc_h6 REAL, pc_h24 REAL,
    n_pairs INTEGER,
    in_obs INTEGER DEFAULT 0,
    -- 仅观察池填：
    holders INTEGER, top10_pct REAL,
    buyers_h1 INTEGER, sellers_h1 INTEGER, buyers_h24 INTEGER, sellers_h24 INTEGER,
    PRIMARY KEY (ts, address)
);
CREATE INDEX IF NOT EXISTS ix_snap_addr ON snapshots(address, ts);

-- 衍生指标 + 评分（每小时重算，可随时按新公式整表重算）
CREATE TABLE IF NOT EXISTS scores (
    ts INTEGER, address TEXT,
    vol_accel_6v18 REAL, vol_accel_1v24 REAL, tx_accel_6v18 REAL,
    buy_ratio_h1 REAL, buy_ratio_h6 REAL,
    vol_liq REAL, holder_g6 REAL, holder_g24 REAL, buyer_accel REAL,
    runup_from_low REAL, dd_from_high REAL, n_hist INTEGER,
    heat REAL, quality REAL, entry REAL,
    listing_p TEXT, listing_basis TEXT,
    state TEXT, reasons TEXT,
    PRIMARY KEY (ts, address)
);

-- 交易所状态（每日刷新；*_since 是首次上线时间，unix 毫秒，来自交易所自身数据）
CREATE TABLE IF NOT EXISTS listings (
    address TEXT, symbol TEXT,
    venue TEXT,                    -- binance_alpha / binance_perp / binance_spot / aster_perp / hl_perp
    since_ms INTEGER,
    match_by TEXT,                 -- address（精确）/ symbol（可能撞名，需人工确认）
    checked_ts INTEGER,
    PRIMARY KEY (address, symbol, venue)
);

-- 币安全量升档事件（全链，不只 RH），用于 ListingP 频率表
CREATE TABLE IF NOT EXISTS binance_events (
    symbol TEXT, chain_id TEXT, address TEXT,
    alpha_ms INTEGER, perp_ms INTEGER, spot_ms INTEGER,
    PRIMARY KEY (symbol, chain_id, address)
);

-- 状态机持久化
CREATE TABLE IF NOT EXISTS state (
    address TEXT PRIMARY KEY, state TEXT, since_ts INTEGER,
    pending TEXT, pending_count INTEGER DEFAULT 0
);

-- 回填用：GT 小时 K 线（只给观察池补过去 7 天，用于「距低点几倍 / 距高点回撤」）
CREATE TABLE IF NOT EXISTS ohlcv (
    address TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,
    PRIMARY KEY (address, ts)
);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path=None):
    con = sqlite3.connect(path or DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def meta_get(con, k, default=None):
    r = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def meta_set(con, k, v):
    con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, str(v)))
