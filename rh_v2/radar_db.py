"""Radar 持久化（独立的 radar.sqlite）。

market.sqlite 只读（ATTACH 都不做，单独开只读连接），Radar 自己的历史只写这里：
  radar_run          每一轮 evaluation 的元数据 + 全市场漏斗计数
  radar_run_summary  每轮 × 每条链的漏斗计数（用于 "+2 since last scan"）
  radar_eval         逐币 evaluation：FAST GATE、六个 signal 原值、每项得分、raw/final score、
                     known/unknown 计数、stage、revival、breakout 标志、evaluated_at、finalized_date、证据
  radar_state        每币当前状态机状态（stage、降级连击计数、最后一次 eval）
  radar_transition   每次 stage 迁移：from → to、原因、score、signal 快照、occurred_at（永久保留）

迁移只在 connect() 里做；版本号写在 radar_meta.schema_version。
"""
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
RADAR_DB_PATH = os.environ.get("RADAR_DB") or os.path.join(HERE, "radar.sqlite")
MARKET_DB_PATH = os.environ.get("RH_MARKET_DB") or os.path.join(HERE, "market.sqlite")

SCHEMA_VERSION = 1

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS radar_meta (k TEXT PRIMARY KEY, v TEXT);

CREATE TABLE IF NOT EXISTS radar_run (
    run_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    mode             TEXT NOT NULL,              -- live | recompute
    started_at       INTEGER NOT NULL,
    finished_at      INTEGER,
    as_of            INTEGER NOT NULL,           -- evaluation 时刻（unix 秒）
    finalized_date   TEXT NOT NULL,              -- 统一 latest finalized UTC 日期 YYYY-MM-DD
    scanned          INTEGER NOT NULL DEFAULT 0,
    gate_pass        INTEGER NOT NULL DEFAULT 0,
    gate_reject      INTEGER NOT NULL DEFAULT 0,
    gate_unknown     INTEGER NOT NULL DEFAULT 0,
    stage_normal     INTEGER NOT NULL DEFAULT 0,
    stage_observe    INTEGER NOT NULL DEFAULT 0,
    stage_early      INTEGER NOT NULL DEFAULT 0,
    stage_ready      INTEGER NOT NULL DEFAULT 0,
    revival_true     INTEGER NOT NULL DEFAULT 0,
    revival_null     INTEGER NOT NULL DEFAULT 0,
    breakout_true    INTEGER NOT NULL DEFAULT 0,
    near_breakout    INTEGER NOT NULL DEFAULT 0,
    new_observations INTEGER NOT NULL DEFAULT 0,
    evals_written    INTEGER NOT NULL DEFAULT 0,
    transitions      INTEGER NOT NULL DEFAULT 0,
    cross_list_coverage TEXT,                    -- JSON {chain: {reliable, sources:{src: n}}}
    error            TEXT
);

CREATE TABLE IF NOT EXISTS radar_run_summary (
    run_id        INTEGER NOT NULL REFERENCES radar_run(run_id) ON DELETE CASCADE,
    chain         TEXT NOT NULL,                 -- 'all' 或具体链
    scanned       INTEGER NOT NULL,
    gate_pass     INTEGER NOT NULL,
    gate_reject   INTEGER NOT NULL,
    gate_unknown  INTEGER NOT NULL,
    stage_observe INTEGER NOT NULL,
    stage_early   INTEGER NOT NULL,
    stage_ready   INTEGER NOT NULL,
    revival       INTEGER NOT NULL,
    breakout      INTEGER NOT NULL,
    candidates    INTEGER NOT NULL,
    PRIMARY KEY (run_id, chain)
);

CREATE TABLE IF NOT EXISTS radar_eval (
    eval_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             INTEGER NOT NULL,
    chain              TEXT NOT NULL,
    address            TEXT NOT NULL,
    evaluated_at       INTEGER NOT NULL,
    finalized_date     TEXT NOT NULL,
    gate               TEXT NOT NULL CHECK (gate IN ('PASS','REJECT','UNKNOWN')),
    low_liquidity      INTEGER,                  -- null = gate 不是 PASS
    gate_reasons       TEXT NOT NULL,            -- JSON [{level, code, text}]
    volume_ratio       REAL,
    buy_share          REAL,
    holder_growth      REAL,
    liquidity_growth   REAL,
    cross_list_count   INTEGER,
    breakout_distance  REAL,
    breakout_10d       INTEGER,                  -- 1 / 0 / null
    near_breakout_10d  INTEGER,                  -- 1 / 0 / null
    score_volume       INTEGER NOT NULL,
    score_buy          INTEGER NOT NULL,
    score_holder       INTEGER NOT NULL,
    score_liquidity    INTEGER NOT NULL,
    score_cross        INTEGER NOT NULL,
    score_breakout     INTEGER NOT NULL,
    raw_score          INTEGER NOT NULL,
    score              INTEGER NOT NULL,
    known_signal_count   INTEGER NOT NULL,
    unknown_signal_count INTEGER NOT NULL,
    entry_stage        TEXT NOT NULL,            -- 本次分数单独指向的 stage（不含滞回）
    stage              TEXT NOT NULL,            -- 状态机之后的 stage
    revival            INTEGER,                  -- 1 / 0 / null
    observation_valid  INTEGER NOT NULL,         -- 1 = 计入状态机（新数据且 gate 不是 UNKNOWN）
    fingerprint        TEXT NOT NULL,
    evidence           TEXT NOT NULL             -- JSON：每个 signal 的输入、口径、时间；revival 证据
);
CREATE INDEX IF NOT EXISTS ix_radar_eval_token ON radar_eval(chain, address, evaluated_at);
CREATE INDEX IF NOT EXISTS ix_radar_eval_time ON radar_eval(evaluated_at);

CREATE TABLE IF NOT EXISTS radar_state (
    chain              TEXT NOT NULL,
    address            TEXT NOT NULL,
    stage              TEXT NOT NULL,
    stage_since        INTEGER NOT NULL,
    below_streak       TEXT NOT NULL,            -- JSON {"READY": n, "EARLY": n, "OBSERVE": n}
    recent_valid_scores TEXT NOT NULL,           -- JSON 最近几次 valid observation 的 score（解释降级）
    last_fingerprint   TEXT,
    last_outcome       TEXT,                     -- gate/分项分/stage/revival/breakout 摘要；变了就落一行 eval
    last_eval_id       INTEGER,
    last_evaluated_at  INTEGER NOT NULL,
    last_valid_at      INTEGER,
    last_change_at     INTEGER NOT NULL,         -- 最近一次 stage 迁移；没有迁移 = 首次评估
    first_evaluated_at INTEGER NOT NULL,
    PRIMARY KEY (chain, address)
);
CREATE INDEX IF NOT EXISTS ix_radar_state_stage ON radar_state(stage);

CREATE TABLE IF NOT EXISTS radar_transition (
    transition_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL,
    eval_id        INTEGER NOT NULL,
    chain          TEXT NOT NULL,
    address        TEXT NOT NULL,
    from_stage     TEXT NOT NULL,
    to_stage       TEXT NOT NULL,
    reason         TEXT NOT NULL,
    score          INTEGER NOT NULL,
    signals        TEXT NOT NULL,                -- JSON 迁移时的六个 signal + 分项分 + gate
    occurred_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_radar_transition_token ON radar_transition(chain, address, occurred_at);
"""


def connect(path=None):
    con = sqlite3.connect(path or RADAR_DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    con.executescript(SCHEMA)
    con.execute(
        "INSERT INTO radar_meta(k, v) VALUES ('schema_version', ?) "
        "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (str(SCHEMA_VERSION),),
    )
    con.commit()
    return con


def connect_market_ro(path=None):
    """market.sqlite 只读。采集器是唯一写者；这里绝不写。"""
    con = sqlite3.connect(path or MARKET_DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA query_only=ON")
    return con


def meta_get(con, k, default=None):
    row = con.execute("SELECT v FROM radar_meta WHERE k=?", (k,)).fetchone()
    return row[0] if row else default


def meta_set(con, k, v):
    con.execute(
        "INSERT INTO radar_meta(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (k, str(v)),
    )
