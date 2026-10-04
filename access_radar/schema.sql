-- Recent Access Radar — core schema (SQLite >= 3.37, STRICT tables)
-- 所有时间字段均为 UTC 毫秒整数 (INTEGER)。
-- 约定：可选维度用 '' 而不是 NULL，保证 UNIQUE 约束生效（SQLite 中 NULL 互不相等）。

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- 平台 / 来源
CREATE TABLE IF NOT EXISTS platform (
    platform_id   TEXT PRIMARY KEY,                 -- 'upbit', 'ramp', 'xstocks', 'solana' ...
    name          TEXT NOT NULL,
    platform_type TEXT NOT NULL CHECK (platform_type IN
        ('CEX','DEX','ONRAMP','ONRAMP_AGGREGATOR','ISSUER','LENDING','PERP_DEX','WALLET','CHAIN','DATA_VENDOR','OTHER')),
    country       TEXT NOT NULL DEFAULT '',
    created_at    INTEGER NOT NULL
) STRICT;

-- source 与 platform 分开：一个 source（如 NewListings、Onramper）可报告多个 platform。
CREATE TABLE IF NOT EXISTS source (
    source_id             TEXT PRIMARY KEY,         -- 'upbit_market', 'upbit_notice', 'newlistings' ...
    name                  TEXT NOT NULL,
    kind                  TEXT NOT NULL CHECK (kind IN ('SNAPSHOT','ANNOUNCEMENT')),
    tier                  TEXT NOT NULL CHECK (tier IN
        ('OFFICIAL_STRUCTURED','OFFICIAL_ANNOUNCEMENT','THIRD_PARTY','AGGREGATOR','LLM_EXTRACTED')),
    tier_weight           REAL NOT NULL CHECK (tier_weight > 0 AND tier_weight < 1),
    independence_group    TEXT NOT NULL,            -- 同组来源不重复计数
    origin_platform_id    TEXT REFERENCES platform(platform_id),  -- 官方来源所属平台；中继/聚合为 NULL
    is_relay              INTEGER NOT NULL DEFAULT 0 CHECK (is_relay IN (0,1)), -- 1=转述他源（观测可带 origin_group 覆盖独立组）
    add_confirm_obs       INTEGER NOT NULL DEFAULT 1 CHECK (add_confirm_obs IN (1,2)),
    remove_confirm_misses INTEGER NOT NULL DEFAULT 3 CHECK (remove_confirm_misses >= 1),
    size_tolerance        REAL NOT NULL DEFAULT 0.2,
    size_min_abs          INTEGER NOT NULL DEFAULT 3,
    remove_min_elapsed_ms INTEGER NOT NULL DEFAULT 0, -- 可选：REMOVE 还要求首个 miss 起至少经过该时长（高频轮询源防抖）
    created_at            INTEGER NOT NULL
) STRICT;

-- ---------------------------------------------------------------- 资产身份（三层）
CREATE TABLE IF NOT EXISTS asset (
    asset_id    INTEGER PRIMARY KEY,
    asset_key   TEXT NOT NULL UNIQUE,               -- 'crypto:ethereum:0x...', 'xstocks:AAPLx', 'ondo:AAPLon'
    asset_type  TEXT NOT NULL CHECK (asset_type IN
        ('CRYPTO','STABLECOIN','TOKENIZED_STOCK','ETF','FUND','TREASURY','COMMODITY','RWA_OTHER')),
    symbol      TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    issuer      TEXT NOT NULL DEFAULT '',           -- 'backed', 'ondo', 'circle' ...
    underlying  TEXT NOT NULL DEFAULT '',           -- 'NASDAQ:AAPL'；AAPLx != AAPLon != NASDAQ:AAPL
    product_id  TEXT NOT NULL DEFAULT '',           -- 发行方内部 id
    created_at  INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS asset_deployment (
    deployment_id INTEGER PRIMARY KEY,
    asset_id      INTEGER NOT NULL REFERENCES asset(asset_id),
    chain         TEXT NOT NULL,                    -- 小写规范名 'ethereum','solana','bsc'
    contract      TEXT NOT NULL,                    -- EVM 地址统一小写
    decimals      INTEGER,
    created_at    INTEGER NOT NULL,
    UNIQUE (chain, contract)
) STRICT;

CREATE TABLE IF NOT EXISTS source_asset_ref (
    ref_id             INTEGER PRIMARY KEY,
    source_id          TEXT NOT NULL REFERENCES source(source_id),
    platform_id        TEXT NOT NULL REFERENCES platform(platform_id),
    platform_symbol    TEXT NOT NULL,               -- 'REZ'
    native_id          TEXT NOT NULL DEFAULT '',    -- 'KRW-REZ', 'REZUSDT', xStocks uuid ...
    asset_id           INTEGER REFERENCES asset(asset_id),          -- 可为空：解析不出也照样落库
    suggested_asset_id INTEGER REFERENCES asset(asset_id),
    resolution_status  TEXT NOT NULL DEFAULT 'UNRESOLVED'
        CHECK (resolution_status IN ('UNRESOLVED','SUGGESTED','CONFIRMED')),
    resolution_source  TEXT NOT NULL DEFAULT '',
    resolved_at        INTEGER,
    created_at         INTEGER NOT NULL,
    UNIQUE (source_id, platform_id, platform_symbol)
) STRICT;

-- ---------------------------------------------------------------- 规范状态
-- asset_key 是“平台内身份”（默认 'sym:REZ'，或适配器显式给出 'ca:solana:<mint>' / 'xstocks:AAPLx'），
-- 全局资产通过 asset_id 关联；这样解析前后合并键不变，不需要 rekey。
CREATE TABLE IF NOT EXISTS access_state (
    access_id          INTEGER PRIMARY KEY,
    asset_key          TEXT NOT NULL,
    asset_id           INTEGER REFERENCES asset(asset_id),
    ref_id             INTEGER REFERENCES source_asset_ref(ref_id),
    platform_id        TEXT NOT NULL REFERENCES platform(platform_id),
    access_kind        TEXT NOT NULL CHECK (access_kind IN
        ('SPOT','PERP','CATALOG','ALPHA','ROADMAP','FIAT_ROUTE','DEPOSIT_NETWORK','WITHDRAW_NETWORK',
         'COLLATERAL','LENDING','CHAIN_DEPLOYMENT')),
    quote              TEXT NOT NULL DEFAULT '',
    country            TEXT NOT NULL DEFAULT '',
    fiat               TEXT NOT NULL DEFAULT '',
    payment_method     TEXT NOT NULL DEFAULT '',
    network            TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL CHECK (status IN ('NONE','ANNOUNCED','LIVE','SUSPENDED','REMOVED')),
    fiat_tier          TEXT CHECK (fiat_tier IS NULL OR fiat_tier IN ('SUPPORTED','QUOTABLE','CONFIRMED')),
    provisional        INTEGER NOT NULL DEFAULT 0 CHECK (provisional IN (0,1)),
    miss_count         INTEGER NOT NULL DEFAULT 0,
    pending_removal_at INTEGER,                     -- 官方下架公告给出的未来生效时间
    first_seen_at      INTEGER NOT NULL,
    last_seen_at       INTEGER NOT NULL,
    status_since       INTEGER NOT NULL,
    created_via_baseline INTEGER NOT NULL DEFAULT 0 CHECK (created_via_baseline IN (0,1)),
    UNIQUE (asset_key, platform_id, access_kind, quote, country, fiat, payment_method, network)
) STRICT;
CREATE INDEX IF NOT EXISTS ix_access_state_merge ON access_state(asset_key, platform_id, access_kind, quote);

-- 每个 (source, scope) 对某个 access 的视图：用于 miss 计数、临时(provisional)确认。
CREATE TABLE IF NOT EXISTS source_item_state (
    source_id        TEXT NOT NULL REFERENCES source(source_id),
    scope            TEXT NOT NULL,
    access_id        INTEGER NOT NULL REFERENCES access_state(access_id),
    present          INTEGER NOT NULL CHECK (present IN (0,1)),
    reported_status  TEXT NOT NULL,
    fiat_tier        TEXT,
    miss_count       INTEGER NOT NULL DEFAULT 0,
    seen_streak      INTEGER NOT NULL DEFAULT 0,
    first_miss_at    INTEGER,
    first_seen_at    INTEGER NOT NULL,
    last_seen_at     INTEGER NOT NULL,
    PRIMARY KEY (source_id, scope, access_id)
) STRICT;

-- ---------------------------------------------------------------- 观测（来源说了什么）
CREATE TABLE IF NOT EXISTS raw_blob (
    raw_id  INTEGER PRIMARY KEY,
    sha256  TEXT NOT NULL UNIQUE,
    json    TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS source_snapshot (
    snapshot_id   INTEGER PRIMARY KEY,
    source_id     TEXT NOT NULL REFERENCES source(source_id),
    scope         TEXT NOT NULL,
    fetched_at    INTEGER NOT NULL,
    poll_prev_at  INTEGER,
    item_count    INTEGER NOT NULL,
    valid_count   INTEGER NOT NULL,
    outcome       TEXT NOT NULL CHECK (outcome IN ('BASELINE','DIFF','DEGRADED','SIZE_ACCEPTED')),
    note          TEXT NOT NULL DEFAULT '',
    raw_id        INTEGER REFERENCES raw_blob(raw_id)
) STRICT;

CREATE TABLE IF NOT EXISTS source_observation (
    obs_id             INTEGER PRIMARY KEY,
    source_id          TEXT NOT NULL REFERENCES source(source_id),
    scope              TEXT NOT NULL DEFAULT '',
    snapshot_id        INTEGER REFERENCES source_snapshot(snapshot_id),
    obs_kind           TEXT NOT NULL CHECK (obs_kind IN ('SNAPSHOT_NEW','SNAPSHOT_CHANGE','SNAPSHOT_SEEN_AGAIN','SNAPSHOT_MISS','ANNOUNCEMENT')),
    platform_id        TEXT NOT NULL REFERENCES platform(platform_id),
    ref_id             INTEGER REFERENCES source_asset_ref(ref_id),
    access_id          INTEGER REFERENCES access_state(access_id),
    asset_key          TEXT NOT NULL,
    access_kind        TEXT NOT NULL,
    quote              TEXT NOT NULL DEFAULT '',
    country            TEXT NOT NULL DEFAULT '',
    fiat               TEXT NOT NULL DEFAULT '',
    payment_method     TEXT NOT NULL DEFAULT '',
    network            TEXT NOT NULL DEFAULT '',
    reported_status    TEXT NOT NULL DEFAULT '',
    action             TEXT NOT NULL DEFAULT '',    -- 公告类：LISTING/DELISTING/SUSPEND/RESUME
    fiat_tier          TEXT,
    origin_group       TEXT NOT NULL,               -- 实际计入的独立组
    announced_at       INTEGER,
    source_detected_at INTEGER,
    observed_at        INTEGER NOT NULL,
    effective_at       INTEGER,
    poll_prev_at       INTEGER,
    source_event_id    TEXT NOT NULL DEFAULT '',
    raw_id             INTEGER REFERENCES raw_blob(raw_id),
    url                TEXT                         -- 公告详情页链接（公告 dict 的 url 键）；快照观测一般为 NULL
) STRICT;
CREATE INDEX IF NOT EXISTS ix_obs_access ON source_observation(access_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_obs_source_event
    ON source_observation(source_id, source_event_id, platform_id, asset_key, access_kind, quote)
    WHERE source_event_id <> '';

-- ---------------------------------------------------------------- 规范事件（一次“episode”）
CREATE TABLE IF NOT EXISTS access_event (
    event_id                INTEGER PRIMARY KEY,
    access_id               INTEGER NOT NULL REFERENCES access_state(access_id),
    asset_key               TEXT NOT NULL,          -- 合并键：(asset_key, platform_id, access_kind, quote)
    platform_id             TEXT NOT NULL REFERENCES platform(platform_id),
    access_kind             TEXT NOT NULL,
    quote                   TEXT NOT NULL DEFAULT '',
    family                  TEXT NOT NULL CHECK (family IN ('ADD','SUSPEND','RESUME','REMOVE','TIER')),
    from_status             TEXT NOT NULL,
    to_status               TEXT NOT NULL,
    event_type              TEXT NOT NULL,          -- 由 (access_kind, from, to[, fiat_tier]) 推导
    fiat_tier               TEXT,
    anchor_at               INTEGER NOT NULL,       -- episode 最早已知时间，用于 72h 合并窗口和 feed 排序
    announced_at            INTEGER,
    source_detected_at      INTEGER,
    observed_at             INTEGER NOT NULL,       -- 我方首次入库
    effective_at            INTEGER,                -- 公告给出的生效/开盘时间（可在未来）
    live_observed_at        INTEGER,                -- 首次在结构化快照中看到 to_status 的时间
    poll_prev_at            INTEGER,                -- 与 live_observed_at 构成不确定区间 (poll_prev_at, live_observed_at]
    confidence              REAL NOT NULL,
    independent_source_count INTEGER NOT NULL,
    provisional             INTEGER NOT NULL DEFAULT 0 CHECK (provisional IN (0,1)),
    retracted               INTEGER NOT NULL DEFAULT 0 CHECK (retracted IN (0,1)),
    first_source_id         TEXT NOT NULL REFERENCES source(source_id),
    created_at              INTEGER NOT NULL,
    updated_at              INTEGER NOT NULL,
    group_key               TEXT                    -- 展示分组：'ann:<source_id>:<source_event_id>:<asset_key>' 或 'ev:<event_id>'
) STRICT;
CREATE INDEX IF NOT EXISTS ix_event_merge ON access_event(asset_key, platform_id, access_kind, quote, family, anchor_at);
CREATE INDEX IF NOT EXISTS ix_event_anchor ON access_event(anchor_at);

CREATE TABLE IF NOT EXISTS event_observation_link (
    event_id INTEGER NOT NULL REFERENCES access_event(event_id),
    obs_id   INTEGER NOT NULL REFERENCES source_observation(obs_id),
    role     TEXT NOT NULL CHECK (role IN ('ORIGIN','PROGRESS','CORROBORATE','CONFIRM','RETRACT')),
    PRIMARY KEY (event_id, obs_id)
) STRICT;

-- 每次实际发生的状态迁移（审计日志）；access_event 是对它们的 episode 级聚合。
CREATE TABLE IF NOT EXISTS access_transition (
    transition_id INTEGER PRIMARY KEY,
    access_id     INTEGER NOT NULL REFERENCES access_state(access_id),
    event_id      INTEGER REFERENCES access_event(event_id),
    from_status   TEXT NOT NULL,
    to_status     TEXT NOT NULL,
    at            INTEGER NOT NULL,
    source_id     TEXT NOT NULL REFERENCES source(source_id),
    obs_id        INTEGER REFERENCES source_observation(obs_id),
    reason        TEXT NOT NULL DEFAULT ''
) STRICT;

CREATE TABLE IF NOT EXISTS rejected_transition (
    rejected_id  INTEGER PRIMARY KEY,
    access_id    INTEGER REFERENCES access_state(access_id),
    from_status  TEXT NOT NULL,
    to_status    TEXT NOT NULL,
    at           INTEGER NOT NULL,
    source_id    TEXT NOT NULL,
    obs_id       INTEGER,
    reason       TEXT NOT NULL
) STRICT;

-- ---------------------------------------------------------------- 健康与基线
CREATE TABLE IF NOT EXISTS source_health (
    source_id             TEXT NOT NULL REFERENCES source(source_id),
    scope                 TEXT NOT NULL,
    status                TEXT NOT NULL CHECK (status IN ('HEALTHY','DEGRADED','DOWN')),
    schema_ok             INTEGER NOT NULL DEFAULT 1 CHECK (schema_ok IN (0,1)),
    last_snapshot_size    INTEGER,                  -- 最近一次被接受的快照规模（参考值）
    anomaly_size          INTEGER,                  -- 连续异常时的规模
    consecutive_anomalies INTEGER NOT NULL DEFAULT 0,
    baseline_done         INTEGER NOT NULL DEFAULT 0 CHECK (baseline_done IN (0,1)),
    last_fetch_at         INTEGER,
    last_ok_at            INTEGER,
    last_error            TEXT NOT NULL DEFAULT '',
    updated_at            INTEGER NOT NULL,
    PRIMARY KEY (source_id, scope)
) STRICT;

CREATE TABLE IF NOT EXISTS source_disconnect (
    disconnect_id INTEGER PRIMARY KEY,
    source_id     TEXT NOT NULL REFERENCES source(source_id),
    scope         TEXT NOT NULL DEFAULT '',
    started_at    INTEGER NOT NULL,
    ended_at      INTEGER,                          -- NULL = 仍断开；区间需要用 History/REST 补数
    reason        TEXT NOT NULL DEFAULT '',
    backfilled    INTEGER NOT NULL DEFAULT 0 CHECK (backfilled IN (0,1))
) STRICT;

CREATE TABLE IF NOT EXISTS source_scope_baseline (
    source_id    TEXT NOT NULL REFERENCES source(source_id),
    scope        TEXT NOT NULL,
    snapshot_id  INTEGER REFERENCES source_snapshot(snapshot_id),
    completed_at INTEGER NOT NULL,
    item_count   INTEGER NOT NULL,
    PRIMARY KEY (source_id, scope)
) STRICT;

-- ---------------------------------------------------------------- 增量迁移说明
-- 老库升级由 radar_core.init_db 完成：缺列则 ALTER TABLE ADD COLUMN（access_event.group_key、source_observation.url），
-- 回填 group_key，建 ix_event_group，并在视图缺列时 DROP + 重建 v_recent_feed（以下文为准）。
-- 因此依赖新列的索引不写在本文件里（老库执行本文件时这些列还不存在）。

-- ---------------------------------------------------------------- feed 视图
-- 前 23 列是 v0.1 的原有列（顺序不变）；之后为扩展列。ref = 该 access 最强的 ref（CONFIRMED > SUGGESTED，来自
-- 该 access 或该事件的观测），都没有则 access_state.ref_id。url = 代表链接：公告优先，其次 ORIGIN，再按 obs_id。
CREATE VIEW IF NOT EXISTS v_recent_feed AS
SELECT e.event_id, e.anchor_at, e.event_type, e.platform_id, e.asset_key, e.quote,
       e.from_status, e.to_status, e.fiat_tier, e.confidence, e.independent_source_count,
       e.provisional, e.retracted, e.announced_at, e.source_detected_at, e.observed_at,
       e.effective_at, e.live_observed_at, e.poll_prev_at, a.asset_id, a.symbol AS asset_symbol,
       a.asset_type, (SELECT COUNT(*) FROM event_observation_link l WHERE l.event_id = e.event_id) AS obs_count,
       e.access_id, e.access_kind, e.family, e.group_key, e.first_source_id, e.updated_at,
       s.network, s.country, s.fiat, s.payment_method, s.status AS current_status, s.pending_removal_at,
       a.asset_key AS g_asset_key, a.name AS asset_name,
       r.ref_id, r.source_id AS ref_source_id, r.platform_symbol, r.native_id, r.resolution_status,
       r.resolution_source, r.suggested_asset_id,
       (SELECT o.url FROM event_observation_link l JOIN source_observation o ON o.obs_id = l.obs_id
         WHERE l.event_id = e.event_id AND l.role <> 'RETRACT' AND o.url IS NOT NULL AND o.url <> ''
         ORDER BY (o.obs_kind = 'ANNOUNCEMENT') DESC, (l.role = 'ORIGIN') DESC, o.obs_id LIMIT 1) AS url
FROM access_event e
LEFT JOIN access_state s ON s.access_id = e.access_id
LEFT JOIN asset a ON a.asset_id = s.asset_id
LEFT JOIN source_asset_ref r ON r.ref_id = COALESCE(
    (SELECT rr.ref_id FROM source_observation o JOIN source_asset_ref rr ON rr.ref_id = o.ref_id
      WHERE (o.access_id = e.access_id
             OR o.obs_id IN (SELECT l.obs_id FROM event_observation_link l WHERE l.event_id = e.event_id))
        AND rr.resolution_status <> 'UNRESOLVED'
      ORDER BY rr.resolution_status = 'CONFIRMED' DESC, rr.ref_id LIMIT 1),
    s.ref_id);
