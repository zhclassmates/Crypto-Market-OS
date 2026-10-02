"""日 K 线数据库。独立表，不影响 rh_v2 现有结构。"""
import sqlite3
import os

DB_PATH = os.environ.get("KLINE_DB", os.path.join(os.path.dirname(__file__), "kline.sqlite"))

SCHEMA = """
PRAGMA journal_mode=WAL;

-- 监控列表：chain + address 是拉取目标，label 可选显示名
CREATE TABLE IF NOT EXISTS kline_watch (
    chain   TEXT NOT NULL,
    address TEXT NOT NULL,
    label   TEXT,
    added_ts INTEGER,
    PRIMARY KEY (chain, address)
);

-- 日 K 线。ts 是当日 UTC 00:00 的 unix 秒。
CREATE TABLE IF NOT EXISTS daily_kline (
    chain   TEXT NOT NULL,
    address TEXT NOT NULL,
    ts      INTEGER NOT NULL,
    open    TEXT, high TEXT, low TEXT, close TEXT, volume TEXT,
    PRIMARY KEY (chain, address, ts)
);
CREATE INDEX IF NOT EXISTS ix_dk_addr ON daily_kline(address, ts);

CREATE TABLE IF NOT EXISTS kline_meta (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path=None):
    con = sqlite3.connect(path or DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def meta_get(con, k, default=None):
    r = con.execute("SELECT v FROM kline_meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def meta_set(con, k, v):
    con.execute("INSERT OR REPLACE INTO kline_meta(k,v) VALUES(?,?)", (k, str(v)))
