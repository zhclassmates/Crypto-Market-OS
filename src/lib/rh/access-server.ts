/**
 * Recent Access Radar 的服务端只读层：access.sqlite（ACCESS_DB）+ rh_v2/market.sqlite（GMGN 行情）。
 * 只读打开，不写库、不联网。库文件或表不存在时返回空数据 + initialized=false，任何异常都不抛给 UI。
 * 纯展示逻辑在 access-core.ts；read* 函数与 createServerFn 分开，方便离线 smoke（node --experimental-strip-types）。
 */
import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { DatabaseSync } from "node:sqlite";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  FEED_WINDOWS,
  buildSourceSummaries,
  collapseSiblings,
  collectorState,
  dedupeStateRows,
  filterEvents,
  groupStates,
  isWarningMarker,
  marketChainToAccess,
  marketKey,
  normalizeContract,
  shapeBuyEntry,
  shapeEvent,
  sortBuyEntries,
  summarizeHealth,
  summarizeMaintenance,
  windowMs,
  type AccessEvent,
  type AccessStateGroup,
  type BuyEntry,
  type Deployment,
  type DisconnectRow,
  type FeedWindow,
  type HealthSummary,
  type MaintenanceRunRow,
  type MaintenanceSummary,
  type MarketLink,
  type RawAccessStateRow,
  type RawEventRow,
  type RawObservationRow,
  type SourceHealthRow,
  type SourceRunRow,
  type SourceSummary,
} from "./access-core.ts";

export type {
  AccessEvent,
  AccessStateGroup,
  BuyEntry,
  HealthSummary,
  MaintenanceSummary,
  MarketLink,
  SourceSummary,
} from "./access-core.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
// 与 radar_core.default_db_path 相同：env ACCESS_DB，其次旧名 ACCESS_RADAR_DB，默认 access_radar 包目录下的 access.sqlite（与 cwd 无关）。
const ACCESS_DB_PATH = process.env.ACCESS_DB || process.env.ACCESS_RADAR_DB || join(HERE, "../../../access_radar/access.sqlite");
// 与 market-server 相同：RH_MARKET_DB 只用于离线验证。
const MARKET_DB_PATH = process.env.RH_MARKET_DB || join(HERE, "../../../rh_v2/market.sqlite");

/** radar_core schema.sql 的领域表；缺任何一张都按“未初始化”处理。 */
const CORE_TABLES = [
  "platform",
  "source",
  "asset",
  "asset_deployment",
  "source_asset_ref",
  "access_state",
  "access_event",
  "event_observation_link",
  "source_observation",
  "raw_blob",
] as const;

export interface ReadOptions {
  accessDb?: string;
  marketDb?: string;
  now?: number;
}

export interface ReadBase {
  ok: true;
  /** false = 库文件不存在或缺表；UI 显示初始化提示。 */
  initialized: boolean;
  reason: string | null;
  /** 读库出错（库损坏、锁超时等）。数据为空，但不抛异常。 */
  error: string | null;
  now: number;
}

function openRead(path: string): DatabaseSync | null {
  if (!path || !existsSync(path)) return null;
  const db = new DatabaseSync(path, { readOnly: true });
  db.exec("PRAGMA busy_timeout=10000");
  return db;
}

function tableSet(db: DatabaseSync): Set<string> {
  const rows = db.prepare("SELECT name FROM sqlite_master WHERE type IN ('table','view')").all() as unknown as { name: string }[];
  return new Set(rows.map((r) => r.name));
}

function columnSet(db: DatabaseSync, table: string): Set<string> {
  const rows = db.prepare(`PRAGMA table_info(${table})`).all() as unknown as { name: string }[];
  return new Set(rows.map((r) => r.name));
}

function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function placeholders(n: number): string {
  return Array.from({ length: n }, () => "?").join(",");
}

function chunks<T>(arr: T[], size = 500): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

/** 打开 access.sqlite、检查表、执行 fn；任何失败都折叠成 empty + 标志位。 */
function withAccess<T extends object>(
  opts: ReadOptions,
  required: readonly string[],
  empty: () => T,
  fn: (db: DatabaseSync, tables: Set<string>, now: number) => T,
): T & ReadBase {
  const now = opts.now ?? Date.now();
  const path = opts.accessDb ?? ACCESS_DB_PATH;
  const base = (initialized: boolean, reason: string | null, error: string | null): ReadBase => ({
    ok: true,
    initialized,
    reason,
    error,
    now,
  });
  let db: DatabaseSync | null = null;
  try {
    db = openRead(path);
    if (!db) return { ...empty(), ...base(false, "Access Radar 库文件不存在", null) };
    const tables = tableSet(db);
    const missing = required.filter((t) => !tables.has(t));
    if (missing.length) return { ...empty(), ...base(false, `库未初始化（缺 ${missing.join(", ")} 表）`, null) };
    return { ...fn(db, tables, now), ...base(true, null, null) };
  } catch (e) {
    return { ...empty(), ...base(!!db, null, errText(e)) };
  } finally {
    try {
      db?.close();
    } catch {
      /* 忽略 */
    }
  }
}

// ----------------------------------------------------------------------------- GMGN 行情链接
function num(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function str(v: unknown): string | null {
  return v == null || v === "" ? null : String(v);
}

/** 按（链, 地址）批量查询：EVM 地址大小写不敏感，其余精确匹配。返回 原始行 + 归一化 key。 */
function queryByAddress(
  db: DatabaseSync,
  table: string,
  addrCol: string,
  select: string,
  chain: string,
  addresses: string[],
  orderBy = "",
): { key: string; row: Record<string, unknown> }[] {
  const evm = addresses.filter((a) => a.startsWith("0x")).map((a) => a.toLowerCase());
  const other = addresses.filter((a) => !a.startsWith("0x"));
  const conds: string[] = [];
  const args: string[] = [chain];
  if (other.length) {
    conds.push(`${addrCol} IN (${placeholders(other.length)})`);
    args.push(...other);
  }
  if (evm.length) {
    conds.push(`lower(${addrCol}) IN (${placeholders(evm.length)})`);
    args.push(...evm);
  }
  if (!conds.length) return [];
  const rows = db
    .prepare(`SELECT ${select}, ${addrCol} AS _addr FROM ${table} WHERE chain = ? AND (${conds.join(" OR ")}) ${orderBy}`)
    .all(...args) as unknown as Record<string, unknown>[];
  return rows.map((row) => ({ key: marketKey(chain, String(row._addr ?? "")), row }));
}

function pick(cols: Set<string>, wanted: Record<string, string>): string {
  return Object.entries(wanted)
    .map(([alias, col]) => (cols.has(col) ? `${col} AS ${alias}` : `NULL AS ${alias}`))
    .join(", ");
}

/**
 * GMGN 行情链接。表选择在运行时探测：
 * 1. token_daily_snapshot（待合入的 V1 每日快照补丁）存在时优先，取该地址 fetched_at 最新的一行（不同 source 不合并）；
 * 2. 该表不存在或没有这个地址时，回落到 token_snapshot（当前快照）+ token_registry / tokens（代号、名称）。
 * 列名用 PRAGMA table_info 探测，缺列记 null。
 */
export function lookupMarket(db: DatabaseSync, refs: { chain: string; address: string }[]): Map<string, MarketLink> {
  const out = new Map<string, MarketLink>();
  if (!refs.length) return out;
  const tables = tableSet(db);
  const byChain = new Map<string, string[]>();
  for (const r of refs) {
    const list = byChain.get(r.chain) ?? [];
    if (!list.includes(r.address)) list.push(r.address);
    byChain.set(r.chain, list);
  }
  const want = (chain: string, addresses: string[]) => addresses.filter((a) => !out.has(marketKey(chain, a)));

  if (tables.has("token_daily_snapshot")) {
    const c = columnSet(db, "token_daily_snapshot");
    if (c.has("chain") && c.has("token_address")) {
      const select = pick(c, {
        symbol: "symbol",
        price: "price",
        market_cap: "market_cap",
        liquidity: "liquidity",
        volume_24h: "volume_24h",
        holders: "holder_count",
        source: "source",
        observed_at: "fetched_at",
      });
      const order = c.has("fetched_at") ? "ORDER BY fetched_at DESC" : "";
      for (const [chain, addresses] of byChain) {
        for (const part of chunks(addresses)) {
          for (const { key, row } of queryByAddress(db, "token_daily_snapshot", "token_address", select, chain, part, order)) {
            if (out.has(key)) continue;
            out.set(key, {
              chain,
              address: String(row._addr),
              symbol: str(row.symbol),
              name: null,
              price: num(row.price),
              marketCap: num(row.market_cap),
              liquidity: num(row.liquidity),
              volume24h: num(row.volume_24h),
              holders: num(row.holders),
              observedAt: num(row.observed_at),
              table: "token_daily_snapshot",
              source: str(row.source),
            });
          }
        }
      }
    }
  }

  const identity = new Map<string, { address: string; symbol: string | null; name: string | null; table: string }>();
  for (const t of ["token_registry", "tokens"] as const) {
    if (!tables.has(t)) continue;
    const c = columnSet(db, t);
    if (!c.has("chain") || !c.has("address")) continue;
    const select = pick(c, { symbol: "symbol", name: "name" });
    for (const [chain, addresses] of byChain) {
      for (const part of chunks(want(chain, addresses))) {
        for (const { key, row } of queryByAddress(db, t, "address", select, chain, part)) {
          const prev = identity.get(key);
          if (!prev) identity.set(key, { address: String(row._addr), symbol: str(row.symbol), name: str(row.name), table: t });
          else {
            prev.symbol = prev.symbol ?? str(row.symbol);
            prev.name = prev.name ?? str(row.name);
          }
        }
      }
    }
  }

  if (tables.has("token_snapshot")) {
    const c = columnSet(db, "token_snapshot");
    if (c.has("chain") && c.has("address")) {
      const select = pick(c, {
        price: "price",
        market_cap: "market_cap",
        liquidity: "liquidity",
        volume_24h: "volume_24h",
        holders: "holders",
        observed_at: "ts",
      });
      for (const [chain, addresses] of byChain) {
        for (const part of chunks(want(chain, addresses))) {
          for (const { key, row } of queryByAddress(db, "token_snapshot", "address", select, chain, part)) {
            if (out.has(key)) continue;
            const id = identity.get(key);
            out.set(key, {
              chain,
              address: String(row._addr),
              symbol: id?.symbol ?? null,
              name: id?.name ?? null,
              price: num(row.price),
              marketCap: num(row.market_cap),
              liquidity: num(row.liquidity),
              volume24h: num(row.volume_24h),
              holders: num(row.holders),
              observedAt: num(row.observed_at),
              table: "token_snapshot",
              source: null,
            });
          }
        }
      }
    }
  }

  for (const [key, id] of identity) {
    if (out.has(key)) continue;
    const chain = key.slice(0, key.indexOf(":"));
    out.set(key, {
      chain,
      address: id.address,
      symbol: id.symbol,
      name: id.name,
      price: null,
      marketCap: null,
      liquidity: null,
      volume24h: null,
      holders: null,
      observedAt: null,
      table: id.table,
      source: null,
    });
  }
  return out;
}

/** 打开 market.sqlite 做行情链接；库不存在或出错时返回空表（行情只是附加信息）。 */
export function readMarketLinks(refs: { chain: string; address: string }[], opts: ReadOptions = {}): Map<string, MarketLink> {
  if (!refs.length) return new Map();
  let db: DatabaseSync | null = null;
  try {
    db = openRead(opts.marketDb ?? MARKET_DB_PATH);
    if (!db) return new Map();
    return lookupMarket(db, refs);
  } catch {
    return new Map();
  } finally {
    try {
      db?.close();
    } catch {
      /* 忽略 */
    }
  }
}

// ----------------------------------------------------------------------------- feed
export interface FeedQuery {
  window?: FeedWindow;
  /** UTC 毫秒；给出时覆盖 window。 */
  since?: number;
  eventTypes?: string[];
  platform?: string;
  /** 市场链 key（sol / eth ...）或 Access 链名。 */
  chain?: string;
  limit?: number;
  includeRetracted?: boolean;
}

export interface FeedData {
  events: AccessEvent[];
  since: number;
  window: string;
  platforms: { id: string; name: string; count: number }[];
  eventTypes: { type: string; count: number }[];
  truncated: boolean;
  /** 实际读的表：扩展版 v_recent_feed，或老库回落到 access_event。 */
  feedSource: "v_recent_feed" | "access_event" | null;
  /** false = 老库没有 group_key，同组事件不合并。 */
  grouped: boolean;
}

/**
 * access_state.ref_id 只是“第一个建出这条 access 的来源”的 ref（例如 NewListings 中继）；其他来源（市场列表、
 * 官方公告）的 ref 通过 source_observation.ref_id 关联。解析状态取这些 ref 里最强的（CONFIRMED > SUGGESTED），都没有再用 s.ref_id。
 */
const BEST_REF = `COALESCE((SELECT rr.ref_id FROM source_observation o JOIN source_asset_ref rr ON rr.ref_id = o.ref_id
  WHERE o.access_id = s.access_id AND rr.resolution_status <> 'UNRESOLVED'
  ORDER BY rr.resolution_status = 'CONFIRMED' DESC, rr.ref_id LIMIT 1), s.ref_id)`;

/** 老库（没有扩展版 v_recent_feed）时直接读 access_event；group_key / url 缺列时用占位（不合并、无代表链接）。 */
const legacyEventSelect = (hasGroupKey: boolean) => `
SELECT ${hasGroupKey ? "e.group_key" : "'ev:' || e.event_id AS group_key"}, NULL AS url, e.event_id, e.access_id, e.asset_key, e.platform_id, e.access_kind, e.quote, e.family, e.from_status, e.to_status,
       e.event_type, e.fiat_tier, e.anchor_at, e.announced_at, e.source_detected_at, e.observed_at, e.effective_at,
       e.live_observed_at, e.poll_prev_at, e.confidence, e.independent_source_count, e.provisional, e.retracted,
       e.first_source_id, e.updated_at,
       s.network, s.country, s.fiat, s.payment_method, s.status AS current_status, s.pending_removal_at,
       s.asset_id, a.asset_key AS g_asset_key, a.symbol AS asset_symbol, a.name AS asset_name, a.asset_type,
       r.platform_symbol, r.resolution_status, r.resolution_source, r.suggested_asset_id,
       sa.asset_key AS suggested_asset_key, sa.symbol AS suggested_symbol,
       p.name AS platform_name, p.platform_type, fs.name AS first_source_name, fs.tier AS first_source_tier
FROM access_event e
LEFT JOIN access_state s ON s.access_id = e.access_id
LEFT JOIN asset a ON a.asset_id = s.asset_id
LEFT JOIN source_asset_ref r ON r.ref_id = ${BEST_REF}
LEFT JOIN asset sa ON sa.asset_id = r.suggested_asset_id
LEFT JOIN platform p ON p.platform_id = e.platform_id
LEFT JOIN source fs ON fs.source_id = e.first_source_id`;

/** 扩展版 v_recent_feed 需要的列（schema.sql：前 23 列 + 扩展列）；缺任一列就回落到 legacyEventSelect。 */
const VIEW_COLUMNS = [
  "event_id", "anchor_at", "event_type", "platform_id", "asset_key", "quote", "from_status", "to_status", "fiat_tier",
  "confidence", "independent_source_count", "provisional", "retracted", "announced_at", "source_detected_at", "observed_at",
  "effective_at", "live_observed_at", "poll_prev_at", "asset_id", "asset_symbol", "asset_type", "access_id", "access_kind",
  "family", "group_key", "first_source_id", "updated_at", "network", "country", "fiat", "payment_method", "current_status",
  "pending_removal_at", "g_asset_key", "asset_name", "platform_symbol", "resolution_status", "resolution_source",
  "suggested_asset_id", "url",
] as const;

/** v_recent_feed 已含 BEST_REF 口径的 ref / 资产 / 状态列与代表 url；这里只补平台名、首个来源与建议资产。 */
const VIEW_EVENT_SELECT = `
SELECT ${VIEW_COLUMNS.map((c) => `e.${c}`).join(", ")},
       sa.asset_key AS suggested_asset_key, sa.symbol AS suggested_symbol,
       p.name AS platform_name, p.platform_type, fs.name AS first_source_name, fs.tier AS first_source_tier
FROM v_recent_feed e
LEFT JOIN asset sa ON sa.asset_id = e.suggested_asset_id
LEFT JOIN platform p ON p.platform_id = e.platform_id
LEFT JOIN source fs ON fs.source_id = e.first_source_id`;

interface FeedSchema {
  select: string;
  fromView: boolean;
  hasGroupKey: boolean;
}

/** 运行时探测 schema（UI 只读，不迁移；Python 首次打开老库时才会补列 / 重建视图）。 */
function feedSchema(db: DatabaseSync, tables: Set<string>): FeedSchema {
  const hasGroupKey = columnSet(db, "access_event").has("group_key");
  if (tables.has("v_recent_feed")) {
    const vc = columnSet(db, "v_recent_feed");
    if (VIEW_COLUMNS.every((c) => vc.has(c))) return { select: VIEW_EVENT_SELECT, fromView: true, hasGroupKey };
  }
  return { select: legacyEventSelect(hasGroupKey), fromView: false, hasGroupKey };
}

function readEvidence(db: DatabaseSync, eventIds: number[]): Map<number, RawObservationRow[]> {
  const out = new Map<number, RawObservationRow[]>();
  const urlCol = columnSet(db, "source_observation").has("url") ? "o.url" : "NULL AS url";
  for (const part of chunks(eventIds)) {
    const rows = db
      .prepare(
        `SELECT l.event_id, l.role, o.obs_id, o.source_id, o.obs_kind, o.action, o.origin_group, o.observed_at,
                o.announced_at, o.source_event_id, src.name AS source_name, src.tier, ${urlCol},
                CASE WHEN length(b.json) <= 20000 THEN b.json END AS raw_json
         FROM event_observation_link l
         JOIN source_observation o ON o.obs_id = l.obs_id
         LEFT JOIN source src ON src.source_id = o.source_id
         LEFT JOIN raw_blob b ON b.raw_id = o.raw_id
         WHERE l.event_id IN (${placeholders(part.length)})
         ORDER BY o.observed_at, o.obs_id`,
      )
      .all(...part) as unknown as RawObservationRow[];
    for (const r of rows) {
      const list = out.get(r.event_id) ?? [];
      list.push(r);
      out.set(r.event_id, list);
    }
  }
  return out;
}

function readDeployments(db: DatabaseSync, assetIds: number[]): Map<number, Deployment[]> {
  const out = new Map<number, Deployment[]>();
  for (const part of chunks([...new Set(assetIds)])) {
    const rows = db
      .prepare(`SELECT asset_id, chain, contract FROM asset_deployment WHERE asset_id IN (${placeholders(part.length)}) ORDER BY deployment_id`)
      .all(...part) as unknown as { asset_id: number; chain: string; contract: string }[];
    for (const r of rows) {
      const list = out.get(r.asset_id) ?? [];
      list.push({ chain: r.chain, contract: r.contract });
      out.set(r.asset_id, list);
    }
  }
  return out;
}

/** 最近事件 feed，口径同 radar_core.recent_events：anchor_at 或 updated_at 落在窗口内，默认排除撤回，新的在前。 */
export function readAccessFeed(q: FeedQuery = {}, opts: ReadOptions = {}): FeedData & ReadBase {
  const window = q.since != null ? "custom" : (q.window ?? "24h");
  const emptyFeed = (): FeedData => ({ events: [], since: 0, window, platforms: [], eventTypes: [], truncated: false, feedSource: null, grouped: false });
  return withAccess(opts, CORE_TABLES, emptyFeed, (db, tables, now) => {
    const schema = feedSchema(db, tables);
    const since = q.since ?? now - windowMs(q.window ?? "24h");
    const limit = Math.min(1000, Math.max(1, q.limit ?? 300));
    const where = ["(e.anchor_at >= ? OR e.updated_at >= ?)"];
    const args: (string | number)[] = [since, since];
    if (!q.includeRetracted) where.push("e.retracted = 0");
    const base = where.join(" AND ");
    const baseArgs = [...args];
    if (q.eventTypes?.length) {
      where.push(`e.event_type IN (${placeholders(q.eventTypes.length)})`);
      args.push(...q.eventTypes.map((t) => t.toUpperCase()));
    }
    if (q.platform) {
      where.push("e.platform_id = ?");
      args.push(q.platform);
    }
    // 链过滤需要部署信息，在取回后过滤；同组事件折叠后行数变少，也多取一些以免不足 limit。
    const fetchN = q.chain && q.chain !== "all" ? 2000 : Math.min(2000, limit * 3 + 1);
    const rows = db
      .prepare(`${schema.select} WHERE ${where.join(" AND ")} ORDER BY e.anchor_at DESC, e.event_id DESC LIMIT ?`)
      .all(...args, fetchN) as unknown as RawEventRow[];

    const evidence = readEvidence(db, rows.map((r) => r.event_id));
    const deps = readDeployments(
      db,
      rows.flatMap((r) => [r.asset_id, r.asset_id == null ? r.suggested_asset_id : null]).filter((x): x is number => x != null),
    );
    const depsFor = (r: RawEventRow) => deps.get((r.asset_id ?? r.suggested_asset_id) as number) ?? [];
    let events = rows.map((r) => shapeEvent(r, { evidence: evidence.get(r.event_id), deployments: depsFor(r) }));
    // 同一 group_key（同一公告 + 同一资产，例如无交易对公告按 quote 拆出的事件，STATE_MACHINE.md §6.1）折叠成一行
    events = collapseSiblings(filterEvents(events, { chain: q.chain, includeRetracted: q.includeRetracted }));
    const truncated = events.length > limit;
    events = events.slice(0, limit);

    const market = readMarketLinks(events.flatMap((e) => e.marketRefs), opts);
    if (market.size) {
      events = events.map((e) => {
        for (const r of e.marketRefs) {
          const hit = market.get(marketKey(r.chain, r.address));
          if (hit) return { ...e, market: hit };
        }
        return e;
      });
    }

    // 计数口径与折叠后的 feed 一致：同一 group_key 只算一次（老库无该列时按事件计）。
    const groupKey = schema.hasGroupKey ? "e.group_key" : "e.event_id";
    const platforms = (
      db
        .prepare(
          `SELECT e.platform_id AS id, COALESCE(p.name, e.platform_id) AS name, COUNT(DISTINCT ${groupKey}) AS count
           FROM access_event e LEFT JOIN platform p ON p.platform_id = e.platform_id
           WHERE ${base} GROUP BY e.platform_id ORDER BY count DESC, e.platform_id`,
        )
        .all(...baseArgs) as unknown as { id: string; name: string; count: number }[]
    ).map((r) => ({ id: r.id, name: r.name, count: Number(r.count) }));
    const eventTypes = (
      db
        .prepare(`SELECT e.event_type AS type, COUNT(DISTINCT ${groupKey}) AS count FROM access_event e WHERE ${base} GROUP BY e.event_type ORDER BY count DESC, e.event_type`)
        .all(...baseArgs) as unknown as { type: string; count: number }[]
    ).map((r) => ({ type: r.type, count: Number(r.count) }));

    return { events, since, window, platforms, eventTypes, truncated, feedSource: schema.fromView ? "v_recent_feed" : "access_event", grouped: schema.hasGroupKey };
  });
}

// ----------------------------------------------------------------------------- 当前可达状态
const STATE_SELECT = `
SELECT s.access_id, s.asset_key, s.asset_id, s.platform_id, s.access_kind, s.quote, s.country, s.fiat, s.payment_method,
       s.network, s.status, s.fiat_tier, s.provisional, s.pending_removal_at, s.first_seen_at, s.last_seen_at,
       s.status_since, s.created_via_baseline,
       a.asset_key AS g_asset_key, a.symbol AS asset_symbol, a.name AS asset_name, a.asset_type,
       r.platform_symbol, r.resolution_status, r.resolution_source, r.suggested_asset_id,
       p.name AS platform_name, p.platform_type
FROM access_state s
LEFT JOIN asset a ON a.asset_id = s.asset_id
LEFT JOIN source_asset_ref r ON r.ref_id = ${BEST_REF}
LEFT JOIN platform p ON p.platform_id = s.platform_id`;

export interface StateQuery {
  statuses?: string[];
  platform?: string;
  limit?: number;
}

export interface StateData {
  groups: AccessStateGroup[];
  total: number;
  truncated: boolean;
}

/** 每个资产 / 平台的当前可达状态（默认不含 NONE）。 */
export function readAccessStates(q: StateQuery = {}, opts: ReadOptions = {}): StateData & ReadBase {
  return withAccess(opts, CORE_TABLES, (): StateData => ({ groups: [], total: 0, truncated: false }), (db) => {
    const statuses = q.statuses?.length ? q.statuses : ["ANNOUNCED", "LIVE", "SUSPENDED", "REMOVED"];
    const limit = Math.min(5000, Math.max(1, q.limit ?? 2000));
    const where = [`s.status IN (${placeholders(statuses.length)})`];
    const args: (string | number)[] = [...statuses];
    if (q.platform) {
      where.push("s.platform_id = ?");
      args.push(q.platform);
    }
    const rows = db
      .prepare(`${STATE_SELECT} WHERE ${where.join(" AND ")} ORDER BY s.status_since DESC, s.access_id DESC LIMIT ?`)
      .all(...args, limit + 1) as unknown as RawAccessStateRow[];
    const truncated = rows.length > limit;
    const kept = rows.slice(0, limit);
    return { groups: groupStates(kept), total: kept.length, truncated };
  });
}

// ----------------------------------------------------------------------------- 来源健康
export interface HealthData {
  sources: SourceSummary[];
  summary: HealthSummary;
  /** source_run / runner_meta（access_db.py 运行器表）是否存在；不存在时只按 source_health 判断。 */
  hasRunnerTables: boolean;
  /** maintenance_run（维护任务，如每小时 resolve）。表不存在时为空数组，hasMaintenanceTable=false。 */
  maintenance: MaintenanceSummary[];
  hasMaintenanceTable: boolean;
  resolution: Record<"CONFIRMED" | "SUGGESTED" | "UNRESOLVED", number>;
}

export function readAccessHealth(opts: ReadOptions = {}): HealthData & ReadBase {
  const empty = (): HealthData => {
    const collector = collectorState(opts.now ?? Date.now(), null);
    return {
      sources: [],
      summary: summarizeHealth([], collector),
      hasRunnerTables: false,
      maintenance: [],
      hasMaintenanceTable: false,
      resolution: { CONFIRMED: 0, SUGGESTED: 0, UNRESOLVED: 0 },
    };
  };
  return withAccess(opts, ["source_health"], empty, (db, tables, now) => {
    const hasRun = tables.has("source_run");
    const runs = hasRun ? (db.prepare("SELECT * FROM source_run").all() as unknown as SourceRunRow[]) : [];
    let hb: string | null = null;
    if (tables.has("runner_meta")) {
      const r = db.prepare("SELECT v FROM runner_meta WHERE k = 'collector_heartbeat'").get() as { v: string | null } | undefined;
      hb = r?.v ?? null;
    }
    const scopes = db.prepare("SELECT * FROM source_health ORDER BY source_id, scope").all() as unknown as SourceHealthRow[];
    const gaps = tables.has("source_disconnect")
      ? (db
          .prepare("SELECT * FROM source_disconnect WHERE ended_at IS NULL OR backfilled = 0 ORDER BY started_at DESC")
          .all() as unknown as DisconnectRow[])
      : [];
    const collector = collectorState(now, hb);
    const sources = buildSourceSummaries(now, runs, scopes, gaps, collector);
    const resolution = { CONFIRMED: 0, SUGGESTED: 0, UNRESOLVED: 0 };
    if (tables.has("source_asset_ref")) {
      for (const r of db
        .prepare("SELECT resolution_status AS s, COUNT(*) AS n FROM source_asset_ref GROUP BY resolution_status")
        .all() as unknown as { s: keyof typeof resolution; n: number }[]) {
        if (r.s in resolution) resolution[r.s] = Number(r.n);
      }
    }
    const hasMaint = tables.has("maintenance_run");
    const maintenance = hasMaint
      ? (db.prepare("SELECT * FROM maintenance_run ORDER BY job_id").all() as unknown as MaintenanceRunRow[]).map((r) =>
          summarizeMaintenance(now, r),
        )
      : [];
    return {
      sources,
      summary: summarizeHealth(sources, collector),
      hasRunnerTables: hasRun,
      maintenance,
      hasMaintenanceTable: hasMaint,
      resolution,
    };
  });
}

// ----------------------------------------------------------------------------- 代币详情：买入入口
export interface BuyEntriesData {
  chain: string;
  address: string;
  accessChains: string[];
  assets: { assetKey: string; symbol: string; assetType: string }[];
  entries: BuyEntry[];
}

/**
 * 韩国交易所警示（유의 종목）标记：asset_key 'warning:<SYM>' 的 ANNOUNCEMENT 观测，最新一条 action=SUSPEND 视为“警示中”。
 * 返回 "platform:SYM" 集合。只是提示，不改变入口状态。
 */
function readWarnings(db: DatabaseSync, rows: RawAccessStateRow[]): Set<string> {
  const out = new Set<string>();
  const pairs = [...new Set(rows.filter((r) => r.platform_symbol).map((r) => `${r.platform_id}:${r.platform_symbol!.toUpperCase()}`))];
  for (const pair of pairs) {
    const i = pair.indexOf(":");
    const platform = pair.slice(0, i);
    const sym = pair.slice(i + 1);
    const r = db
      .prepare(
        `SELECT action FROM source_observation WHERE platform_id = ? AND asset_key = ? AND obs_kind = 'ANNOUNCEMENT'
         ORDER BY COALESCE(announced_at, observed_at) DESC, obs_id DESC LIMIT 1`,
      )
      .get(platform, `warning:${sym}`) as { action: string } | undefined;
    if (r && r.action.toUpperCase() === "SUSPEND") out.add(pair);
  }
  return out;
}

/** 按（市场链, 合约）找这个代币在哪些平台可买 / 可达。匹配：资产部署 → asset_id；建议匹配（SUGGESTED）；平台内 ca:/crypto: 合约键。 */
export function readBuyEntries(chain: string, address: string, opts: ReadOptions = {}): BuyEntriesData & ReadBase {
  const accessChains = marketChainToAccess(chain);
  const contract = normalizeContract(address);
  const empty = (): BuyEntriesData => ({ chain, address, accessChains, assets: [], entries: [] });
  return withAccess(opts, CORE_TABLES, empty, (db) => {
    if (!contract || !accessChains.length) return empty();
    const evm = contract.startsWith("0x");
    const assets = db
      .prepare(
        `SELECT DISTINCT a.asset_id, a.asset_key, a.symbol, a.asset_type FROM asset_deployment d JOIN asset a ON a.asset_id = d.asset_id
         WHERE d.chain IN (${placeholders(accessChains.length)}) AND ${evm ? "lower(d.contract)" : "d.contract"} = ?`,
      )
      .all(...accessChains, contract) as unknown as { asset_id: number; asset_key: string; symbol: string; asset_type: string }[];
    const ids = assets.map((a) => a.asset_id);
    const keys = accessChains.flatMap((c) => [`ca:${c}:${contract}`, `crypto:${c}:${contract}`]);
    const parts: string[] = [];
    const args: (string | number)[] = [];
    if (ids.length) {
      parts.push(`SELECT 'asset' AS "match", q.* FROM (${STATE_SELECT} WHERE s.asset_id IN (${placeholders(ids.length)})) q`);
      args.push(...ids);
      parts.push(
        `SELECT 'suggested' AS "match", q.* FROM (${STATE_SELECT} WHERE s.asset_id IS NULL AND r.resolution_status = 'SUGGESTED'
           AND r.suggested_asset_id IN (${placeholders(ids.length)})) q`,
      );
      args.push(...ids);
    }
    parts.push(
      `SELECT 'key' AS "match", q.* FROM (${STATE_SELECT} WHERE ${evm ? "lower(s.asset_key)" : "s.asset_key"} IN (${placeholders(keys.length)})) q`,
    );
    args.push(...keys);
    const rows = db.prepare(parts.join(" UNION ALL ")).all(...args) as unknown as RawAccessStateRow[];
    const kept = dedupeStateRows(rows).filter((r) => r.status !== "NONE" && !isWarningMarker(r.asset_key));
    const warned = readWarnings(db, kept);
    const entries = sortBuyEntries(
      kept.map((r) => ({ ...shapeBuyEntry(r), warning: warned.has(`${r.platform_id}:${(r.platform_symbol ?? "").toUpperCase()}`) })),
    );
    return {
      chain,
      address,
      accessChains,
      assets: assets.map((a) => ({ assetKey: a.asset_key, symbol: a.symbol, assetType: a.asset_type })),
      entries,
    };
  });
}

// ----------------------------------------------------------------------------- server functions
export const fetchAccessFeed = createServerFn({ method: "POST" })
  .validator(
    z.object({
      window: z.enum(FEED_WINDOWS).optional(),
      since: z.number().int().nonnegative().optional(),
      eventTypes: z.array(z.string().min(1).max(64)).max(64).optional(),
      platform: z.string().min(1).max(64).optional(),
      chain: z.string().min(1).max(32).optional(),
      limit: z.number().int().min(1).max(1000).optional(),
    }),
  )
  .handler(async ({ data }) => readAccessFeed(data));

export const fetchAccessState = createServerFn({ method: "POST" })
  .validator(
    z.object({
      statuses: z.array(z.enum(["NONE", "ANNOUNCED", "LIVE", "SUSPENDED", "REMOVED"])).max(5).optional(),
      platform: z.string().min(1).max(64).optional(),
      limit: z.number().int().min(1).max(5000).optional(),
    }),
  )
  .handler(async ({ data }) => readAccessStates(data));

export const fetchAccessHealth = createServerFn({ method: "GET" }).handler(async () => readAccessHealth());

export const fetchBuyEntries = createServerFn({ method: "POST" })
  .validator(z.object({ chain: z.string().min(1).max(32), address: z.string().min(1).max(128) }))
  .handler(async ({ data }) => readBuyEntries(data.chain, data.address));
