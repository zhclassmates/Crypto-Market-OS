"""SQLite 存储。WAL 模式：采集进程持续写，同时可以另开进程读（health / 研究脚本 / DuckDB）。

所有 ts 均为 UTC 毫秒。bars.ts = K 线开盘时间。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars(
  venue TEXT, market TEXT, symbol TEXT, interval TEXT, ts INTEGER,
  open REAL, high REAL, low REAL, close REAL,
  vol_base REAL, vol_quote REAL,
  taker_buy_quote REAL,          -- 主动买成交额
  cvd_quote REAL,                -- 本 bar 净主动买额 = 2*taker_buy_quote - vol_quote（按 bar 切，不无限累计）
  trades INTEGER,
  PRIMARY KEY(venue, market, symbol, interval, ts));

CREATE TABLE IF NOT EXISTS oi(
  venue TEXT, symbol TEXT, source TEXT, ts INTEGER,   -- source: hist5m | hist15m | snapshot
  oi_base REAL, oi_usd REAL,
  PRIMARY KEY(venue, symbol, source, ts));

CREATE TABLE IF NOT EXISTS funding_live(              -- 每次轮询采样的实时/预测费率
  venue TEXT, symbol TEXT, ts INTEGER,
  mark REAL, index_px REAL, rate REAL, next_funding_ts INTEGER,
  PRIMARY KEY(venue, symbol, ts));

CREATE TABLE IF NOT EXISTS funding_settled(           -- 已结算费率
  venue TEXT, symbol TEXT, ts INTEGER, rate REAL,
  PRIMARY KEY(venue, symbol, ts));

CREATE TABLE IF NOT EXISTS liq_prints(                -- 本所可见强平（抽样快照，不是全量）
  venue TEXT, symbol TEXT, ts INTEGER,
  side TEXT,                     -- long_liq | short_liq（已统一语义）
  price REAL, qty REAL, notional REAL, raw_side TEXT,
  PRIMARY KEY(venue, symbol, ts, side, price, qty));

CREATE TABLE IF NOT EXISTS ws_heartbeat(              -- 某分钟 WS 全程在线才写一行；用于算强平覆盖率
  venue TEXT, minute_ts INTEGER, msgs INTEGER,
  PRIMARY KEY(venue, minute_ts));

CREATE TABLE IF NOT EXISTS poll_log(
  ts INTEGER, job TEXT, ok INTEGER, detail TEXT);

CREATE INDEX IF NOT EXISTS idx_liq_ts ON liq_prints(ts);
CREATE INDEX IF NOT EXISTS idx_poll_ts ON poll_log(ts);
"""


def connect(path: Path, readonly: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if readonly:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path, timeout=30)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.executescript(SCHEMA)
    return con


class Store:
    def __init__(self, path: Path):
        self.con = connect(path)

    def _many(self, sql: str, rows: list[tuple]) -> int:
        if not rows:
            return 0
        with self.con:
            self.con.executemany(sql, rows)
        return len(rows)

    def upsert_bars(self, rows): return self._many(
        "INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    def upsert_oi(self, rows): return self._many(
        "INSERT OR REPLACE INTO oi VALUES (?,?,?,?,?,?)", rows)

    def upsert_funding_live(self, rows): return self._many(
        "INSERT OR REPLACE INTO funding_live VALUES (?,?,?,?,?,?,?)", rows)

    def upsert_funding_settled(self, rows): return self._many(
        "INSERT OR REPLACE INTO funding_settled VALUES (?,?,?,?)", rows)

    def insert_liqs(self, rows): return self._many(
        "INSERT OR IGNORE INTO liq_prints VALUES (?,?,?,?,?,?,?,?)", rows)

    def heartbeat(self, venue: str, minute_ts: int, msgs: int):
        with self.con:
            self.con.execute("INSERT OR REPLACE INTO ws_heartbeat VALUES (?,?,?)", (venue, minute_ts, msgs))

    def log(self, ts: int, job: str, ok: bool, detail: str = ""):
        with self.con:
            self.con.execute("INSERT INTO poll_log VALUES (?,?,?,?)", (ts, job, int(ok), detail[:500]))

    def last_ts(self, table: str, where: str, params: tuple) -> int | None:
        row = self.con.execute(f"SELECT MAX(ts) FROM {table} WHERE {where}", params).fetchone()
        return row[0] if row and row[0] is not None else None
