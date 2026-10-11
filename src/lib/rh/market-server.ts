import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { DatabaseSync } from "node:sqlite";
import { existsSync } from "node:fs";
import { join } from "node:path";
import {
  displayCreated,
  formalStreakEligible,
  canonicalWindowEndTs,
  officialDailyMetrics,
  parseDays,
  streakBoardEligible,
  STREAK_MIN_LIQUIDITY,
  type DailyBar,
  type DailyStatus,
  type QualityFlag,
  type StreakStatus,
} from "./streak.ts";
import {
  dailyHistoryForWindow,
  dailyReturnsFromFinalized,
  finalizedDateWindow,
  latestFinalizedDates,
  parseVolumeUsd,
  utcDateKey,
  type DailyHistoryEntry,
  type DailyReturnMap,
} from "./daily-filter.ts";
import {
  EARLY_TIER_SQL,
  MAIN_MIN_LIQUIDITY,
  SNAPSHOT_LIQ_SQL,
  readMarketInclusionStats,
  readMarketTierStats,
  type MarketInclusionStats,
  type MarketTierStats,
} from "./market-stats.ts";

export interface MarketEligibility {
  days: number;
  registry: number;
  enoughCandleHistory: number;
  liquidityQualified: number;
  freshQualified: number;
  finalEligible: number;
}

// RH_MARKET_DB 只用于离线验证（指向数据库副本）；默认仍是生产库。
const DB_PATH = process.env.RH_MARKET_DB || join(process.cwd(), "rh_v2/market.sqlite");

interface RankedToken {
  chain: string;
  address: string;
  symbol: string | null;
  name: string | null;
  logo: string | null;
  creationTs: number | null;
  tokenCreatedAt: number | null;
  pairCreatedAt: number | null;
  firstSeenAt: number | null;
  createdAt: number | null;
  createdSource: "token" | "pair" | null;
  klineFetchedAt: number | null;
  price: string;
  pc24h: string | null; // GMGN 滚动 24h 涨幅，小数
  pc24hSource: string | null; // 写入 pc_24h 的发现源；trending = 明确 --interval 24h
  pcInterval: string | null; // "24h" 或 null（窗口未确认 / legacy）
  volume24h: string;
  liquidity: string;
  marketCap: string;
  holders: number | null;
  priceSource: string | null;
  priceUpdatedAt: number | null;
  volume24hSource: string | null;
  volume24hUpdatedAt: number | null;
  liquiditySource: string | null;
  marketCapSource: string | null;
  marketCapUpdatedAt: number | null;
  holdersSource: string | null;
  holdersUpdatedAt: number | null;
  securityUpdatedAt: number | null;
  securityIsHoneypot: boolean | null;
  securityIsBlacklist: boolean | null;
  securityIsOpenSource: boolean | null;
  securityIsRenounced: boolean | null;
  securityTop10HolderRate: string | null;
  // V1 字段底座。null = 尚未观察到 / endpoint 不提供；0 是合法值。
  swaps24h: number | null; // 24h 交易笔数（buys + sells），不是钱包数
  buys24h: number | null; // 24h 买入笔数，不是独立买家数
  sells24h: number | null; // 24h 卖出笔数，不是独立卖家数
  activitySource: string | null;
  activityUpdatedAt: number | null;
  pc1h: string | null; // GMGN price_change_percent1h（Trending/Hot）
  pc1hUpdatedAt: number | null;
  isWashTrading: boolean | null;
  securityRenouncedMint: boolean | null;
  securityRenouncedFreezeAccount: boolean | null;
  securitySellTax: string | null; // 原样字符串，刻度未编码
  trendingRank: number | null; // 最近 24h 内最新一次 Trending 名次；null = 未在榜
  trendingRankAt: number | null;
  trendingRankContext: string | null; // endpoint/interval，名次只在同一上下文内可比
  hotRank: number | null;
  hotRankAt: number | null;
  hotRankContext: string | null;
  lastSignalType: string | null; // GMGN signal_type 原始代码，含义未编码
  lastSignalTriggerAt: number | null;
  lastSignalTriggerMc: number | null;
  changeNd: number | null; // 已定稿 UTC 日 K 的 N 日累计。不是滚动 24H，也不是日K
  change1d: number | null; // 日K：最近两根已定稿日 K 的收盘比。closed_daily_change
  dailyReturns: DailyReturnMap;
  /** 统一 7 日窗口（ndWindowEnd 的 T-6…T0），每格收益 + USD 成交量来自同一根 FINALIZED 日K。 */
  dailyHistory: DailyHistoryEntry[];
  /** 全市场新币优先排序键（unix 秒）。null = 系统里没有任何首次时间。 */
  newnessAt: number | null;
  newnessSource: "first_seen" | "creation" | null;
  /**
   * 是否属于改版前的榜单候选集合（原预筛 + 原服务端剔除规则）。
   * 连涨榜只在这个集合里筛，保证全市场扩容不改变连涨榜。
   */
  streakPool: boolean;
  streak: number | null;
  streakStatus: StreakStatus;
  streakReturn: number | null;
  streakDrawdown: number | null;
  closedCandles: number;
  lastDailyStatus: DailyStatus | null;
  qualityFlags: QualityFlag[];
  priceDs: string | null;
  volumeDs: string | null;
  liquidityDs: string | null;
  dexPrice: string | null;
  diverge: number;
  anchorBid: string | null;
  anchorAsk: string | null;
  anchorGeneratedAt: number | null;
  anchorMultiplier: string | null;
  halt: boolean;
  marketClosed: boolean;
  oraclePrice: string | null;
  oracleUpdatedAt: number | null;
  commitOk: boolean;
  chgPrice: boolean;
  chgVolume: boolean;
  chgLiquidity: boolean;
  liquidityNum: number | null;
  liquidityUpdatedAt: number | null;
  observationType: string | null;
  qualifiedAt: number | null;
  return2d: number | null;
  return3d: number | null;
  return5d: number | null;
}

function openReadDb(): DatabaseSync {
  const db = new DatabaseSync(DB_PATH, { open: true });
  db.exec("PRAGMA busy_timeout=10000");
  return db;
}

function flag(v: unknown): boolean {
  return Number(v || 0) === 1;
}

function nullableFlag(v: unknown): boolean | null {
  return v == null ? null : Number(v) === 1;
}

function optionalSnapshotSelect(db: DatabaseSync): string {
  const cols = db.prepare("PRAGMA table_info(token_snapshot)").all() as unknown as { name: string }[];
  const names = new Set(cols.map((c) => c.name));
  const wanted = [
    "price_source", "price_updated_at", "pc_24h_source", "volume_24h_source", "volume_24h_updated_at",
    "liquidity_source", "market_cap_source", "market_cap_updated_at",
    "holders_source", "holders_updated_at", "security_updated_at",
    "security_is_honeypot", "security_is_blacklist", "security_is_open_source",
    "security_is_renounced", "security_top10_holder_rate",
    "swaps", "swaps_source", "swaps_updated_at",
    "buys_24h", "sells_24h", "pc_1h", "pc_1h_updated_at", "is_wash_trading",
    "security_renounced_mint", "security_renounced_freeze_account", "security_sell_tax",
  ];
  return wanted.map((name) => names.has(name) ? `s.${name}` : `NULL AS ${name}`).join(", ");
}

interface LatestEvents {
  trendingRank: number | null;
  trendingRankAt: number | null;
  trendingRankContext: string | null;
  hotRank: number | null;
  hotRankAt: number | null;
  hotRankContext: string | null;
  lastSignalType: string | null;
  lastSignalTriggerAt: number | null;
  lastSignalTriggerMc: number | null;
}

/** 最近 24h 每个 token 每个来源的最新一条发现事件。没有事件 = 未在榜，不是名次 0。 */
function loadLatestEvents(db: DatabaseSync, now: number): Map<string, LatestEvents> {
  const rows = db
    .prepare(
      `WITH x AS (
         SELECT chain, address, source, source_variant, rank, seen_at, metadata_json,
                ROW_NUMBER() OVER (PARTITION BY chain, address, source ORDER BY seen_at DESC, id DESC) AS rn
         FROM discovery_event
         WHERE source IN ('trending', 'hot', 'signal') AND seen_at >= ?
       )
       SELECT chain, address, source, source_variant, rank, seen_at,
              json_extract(metadata_json, '$.trigger_at') AS trigger_at,
              json_extract(metadata_json, '$.trigger_mc') AS trigger_mc
       FROM x WHERE rn = 1`,
    )
    .all(now - 86400) as unknown as {
    chain: string;
    address: string;
    source: string;
    source_variant: string | null;
    rank: number | null;
    seen_at: number;
    trigger_at: number | null;
    trigger_mc: number | null;
  }[];
  const out = new Map<string, LatestEvents>();
  for (const r of rows) {
    const key = `${r.chain}:${r.address}`;
    const e = out.get(key) ?? {
      trendingRank: null, trendingRankAt: null, trendingRankContext: null,
      hotRank: null, hotRankAt: null, hotRankContext: null,
      lastSignalType: null, lastSignalTriggerAt: null, lastSignalTriggerMc: null,
    };
    if (r.source === "trending") {
      e.trendingRank = r.rank;
      e.trendingRankAt = r.seen_at;
      e.trendingRankContext = `trending/${r.source_variant || "?"}`;
    } else if (r.source === "hot") {
      e.hotRank = r.rank;
      e.hotRankAt = r.seen_at;
      e.hotRankContext = "hot-searches/默认参数";
    } else if (r.source === "signal") {
      e.lastSignalType = r.source_variant || null;
      e.lastSignalTriggerAt = r.trigger_at == null ? null : Number(r.trigger_at);
      e.lastSignalTriggerMc = r.trigger_mc == null ? null : Number(r.trigger_mc);
    }
    out.set(key, e);
  }
  return out;
}

export interface GmgnClock {
  lastSuccess: number | null;
  sourceTimestamp: number | null;
  sourceTimestampMissing: boolean;
}

function readGmgnClocks(db: DatabaseSync): Record<string, GmgnClock> {
  const out: Record<string, GmgnClock> = {};
  const exists = db
    .prepare("SELECT 1 AS n FROM sqlite_master WHERE type='table' AND name='source_health'")
    .get() as { n: number } | undefined;
  if (!exists) return out;
  const rows = db
    .prepare(
      "SELECT chain, last_success, source_timestamp, source_timestamp_missing FROM source_health WHERE source='gmgn'",
    )
    .all() as unknown as {
    chain: string;
    last_success: number | null;
    source_timestamp: number | null;
    source_timestamp_missing: number | null;
  }[];
  for (const r of rows) {
    out[r.chain] = {
      lastSuccess: r.last_success,
      sourceTimestamp: r.source_timestamp,
      sourceTimestampMissing: Number(r.source_timestamp_missing ?? 1) === 1,
    };
  }
  return out;
}

function dailyKlineHasFetchedAt(db: DatabaseSync): boolean {
  const cols = db.prepare("PRAGMA table_info(daily_kline)").all() as unknown as { name: string }[];
  return cols.some((c) => c.name === "fetched_at");
}

function loadDailyBars(db: DatabaseSync): Map<string, DailyBar[]> {
  const sql = dailyKlineHasFetchedAt(db)
    ? "SELECT chain, address, ts, high, close, volume, fetched_at, finalized_at FROM daily_kline"
    : "SELECT chain, address, ts, high, close, volume, NULL AS fetched_at, NULL AS finalized_at FROM daily_kline";
  const rows = db.prepare(sql).all() as unknown as {
    chain: string;
    address: string;
    ts: number;
    high: string | null;
    close: string | null;
    /** GMGN kline volume = USD 成交额（volume / amount 落在当日 [low, high]）。缺失时写的是 ""。 */
    volume: string | null;
    fetched_at: number | null;
    finalized_at: number | null;
  }[];
  const out = new Map<string, DailyBar[]>();
  for (const row of rows) {
    const key = `${row.chain}:${row.address}`;
    let list = out.get(key);
    if (!list) {
      list = [];
      out.set(key, list);
    }
    list.push({
      ts: row.ts,
      high: Number(row.high),
      close: Number(row.close),
      fetchedAt: row.fetched_at ?? null,
      finalizedAt: row.finalized_at ?? null,
      volumeUsd: parseVolumeUsd(row.volume),
    });
  }
  return out;
}

/**
 * 没有日 K、池子也不到连涨门槛的币进不了任何一个榜，不往前端送。
 * 全市场 7000+ 个币里大多是这种，整表下发会让接口和页面都卡住。
 */
const BOARD_PREFILTER = `(t.kline_fetched_at IS NOT NULL OR s.liquidity_num >= ${STREAK_MIN_LIQUIDITY})`;

/** 全市场默认浏览集合里“最新 N 个”的 N。这是首屏浏览集合，不是准入上限：搜索仍查全库。 */
export const MARKET_BROWSE_NEWEST = 500;

/**
 * newness = 本系统最早看到它的时间：registry/tokens.first_seen_at 与最早 discovery_event 取最早；
 * 都没有才退回 creation_timestamp。只用于全市场新币优先，不参与连涨榜任何计算。
 */
const MARKET_NEWNESS_CTE = `
  market_disc AS (
    SELECT chain, address, MIN(seen_at) AS first_disc FROM discovery_event GROUP BY chain, address
  ),
  market_newness AS (
    SELECT r.chain, r.address,
           MIN(COALESCE(r.first_seen_at, t.first_seen_at, d.first_disc),
               COALESCE(t.first_seen_at, d.first_disc, r.first_seen_at),
               COALESCE(d.first_disc, r.first_seen_at, t.first_seen_at)) AS seen_at,
           COALESCE(t.token_created_at, r.token_created_at) AS created_at
    FROM token_registry r
    LEFT JOIN tokens t ON t.chain = r.chain AND t.address = r.address
    LEFT JOIN market_disc d ON d.chain = r.chain AND d.address = r.address
  ),
  market_newest AS MATERIALIZED (
    SELECT chain, address FROM market_newness
    ORDER BY COALESCE(seen_at, created_at) DESC NULLS LAST, chain, address
    LIMIT ${MARKET_BROWSE_NEWEST}
  )`;

/**
 * 全市场默认浏览集合 = 原有榜单预筛 ∪ 有日K ∪ 最新 N 个。
 * 原预筛集合原样保留在里面，连涨榜的候选集合因此不变。
 */
const MARKET_BROWSE_SQL = `(${BOARD_PREFILTER}
  OR EXISTS (SELECT 1 FROM daily_kline k WHERE k.chain = r.chain AND k.address = r.address)
  OR EXISTS (SELECT 1 FROM market_newest w WHERE w.chain = r.chain AND w.address = r.address))`;

/** 全库搜索：symbol / name / address 子串，不看浏览集合，不看日K条数。 */
const MARKET_SEARCH_SQL = `(instr(lower(r.address), :q) > 0
  OR instr(lower(COALESCE(t.symbol, r.symbol, '')), :q) > 0
  OR instr(lower(COALESCE(t.name, r.name, '')), :q) > 0)`;
const MARKET_SEARCH_LIMIT = 200;

function keySet(keys: string[] | undefined): Set<string> | null {
  return keys ? new Set(keys.map((k) => k.toLowerCase())) : null;
}

function readMeta(db: DatabaseSync, k: string): string | null {
  const row = db.prepare("SELECT v FROM market_meta WHERE k=?").get(k) as { v: string } | undefined;
  return row?.v ?? null;
}

function readMaxPriceTs(db: DatabaseSync): number | null {
  const row = db.prepare("SELECT MAX(ts) AS ts FROM hourly_price").get() as { ts: number | null } | undefined;
  return row?.ts ?? null;
}

function emptyEligibility(days: number, registry = 0): MarketEligibility {
  return {
    days,
    registry,
    enoughCandleHistory: 0,
    liquidityQualified: 0,
    freshQualified: 0,
    finalEligible: 0,
  };
}

export const fetchMarketRank = createServerFn({ method: "POST" })
  .validator(z.object({
    days: z.unknown().optional(),
    keys: z.array(z.string()).max(2000).optional(),
    /** 全库搜索；给了就只返回命中的 token，不受默认浏览集合限制。 */
    search: z.string().max(200).optional(),
  }))
  .handler(async ({ data }): Promise<{
    ok: boolean;
    tokens: RankedToken[];
    dailyDates?: string[];
    /** N 日窗口终点：UTC 昨天（canonical_window_end）。 */
    ndWindowEnd?: string | null;
    inclusionStats?: MarketInclusionStats;
    tierStats?: MarketTierStats;
    days?: number;
    eligibility?: MarketEligibility;
    /** 名册总数。没下发的是日K不足 N+1 根、池深也不到连涨门槛的币。 */
    registryCount?: number;
    lastMarketUpdate?: string | null;
    lastPriceUpdate?: string | null;
    lastKlineUpdate?: string | null;
    chainTs?: Record<string, number>; // 每条链最新一轮快照时间（某链本轮失败时会比别的链旧）
    gmgn?: Record<string, GmgnClock>;
    error?: string;
  }> => {
    try {
      if (!existsSync(DB_PATH)) {
        return { ok: false, tokens: [], error: "数据库不存在，先跑采集器" };
      }
      const db = openReadDb();
      const now = Math.floor(Date.now() / 1000);
      const days = parseDays(data.days);
      const watch = keySet(data.keys);
      const search = watch ? "" : (data.search ?? "").trim().toLowerCase();
      const bars = loadDailyBars(db);
      const optionalSnapshot = optionalSnapshotSelect(db);
      const latestEvents = loadLatestEvents(db, now);
      const inclusionStats = readMarketInclusionStats(db, now);
      const tierStats = readMarketTierStats(db);
      const registryCount = inclusionStats.totalTokens;
      const eligibility = emptyEligibility(days, registryCount);

      const scope = watch
        ? ""
        : search
          ? `WHERE ${MARKET_SEARCH_SQL}
             ORDER BY (lower(r.address) = :q OR lower(COALESCE(t.symbol, r.symbol, '')) = :q) DESC,
                      COALESCE(n.seen_at, n.created_at) DESC NULLS LAST
             LIMIT ${MARKET_SEARCH_LIMIT}`
          : `WHERE ${MARKET_BROWSE_SQL}`;
      const tokens = db
        .prepare(
          `WITH ${MARKET_NEWNESS_CTE}
           SELECT r.chain, r.address,
                  COALESCE(t.symbol, r.symbol) AS symbol,
                  COALESCE(t.name, r.name) AS name,
                  t.logo, t.creation_ts,
                  COALESCE(t.token_created_at, r.token_created_at) AS token_created_at,
                  t.pair_created_at,
                  COALESCE(r.first_seen_at, t.first_seen_at) AS first_seen_at,
                  t.kline_fetched_at,
                  s.price, s.pc_24h, s.volume_24h, s.liquidity, s.market_cap, s.holders,
                  s.price_ds, s.volume_ds, s.liquidity_ds, s.dex_price, s.diverge,
                  s.anchor_bid, s.anchor_ask, s.anchor_generated_at, s.anchor_multiplier,
                  s.halt, s.market_closed, s.oracle_price, s.oracle_updated_at,
                  s.commit_ok, s.chg_price, s.chg_volume, s.chg_liquidity,
                  s.liquidity_num, s.liquidity_updated_at,
                  ${optionalSnapshot},
                  r.liquidity_50k_observation_type, r.qualified_at,
                  n.seen_at AS newness_seen_at, n.created_at AS newness_created_at,
                  ${BOARD_PREFILTER} AS legacy_board
           FROM token_registry r
           LEFT JOIN tokens t ON t.chain = r.chain AND t.address = r.address
           LEFT JOIN token_snapshot s ON s.chain = r.chain AND s.address = r.address
           LEFT JOIN market_newness n ON n.chain = r.chain AND n.address = r.address
           ${scope}`,
        )
        .all(search ? { q: search } : {}) as unknown as {
        chain: string;
        address: string;
        symbol: string | null;
        name: string | null;
        logo: string | null;
        creation_ts: number | null;
        token_created_at: number | null;
        pair_created_at: number | null;
        first_seen_at: number | null;
        kline_fetched_at: number | null;
        price: string;
        pc_24h: string | null;
        volume_24h: string;
        liquidity: string;
        market_cap: string;
        holders: number | null;
        price_source: string | null;
        price_updated_at: number | null;
        pc_24h_source: string | null;
        volume_24h_source: string | null;
        volume_24h_updated_at: number | null;
        liquidity_source: string | null;
        market_cap_source: string | null;
        market_cap_updated_at: number | null;
        holders_source: string | null;
        holders_updated_at: number | null;
        security_updated_at: number | null;
        security_is_honeypot: number | null;
        security_is_blacklist: number | null;
        security_is_open_source: number | null;
        security_is_renounced: number | null;
        security_top10_holder_rate: string | null;
        swaps: number | null;
        swaps_source: string | null;
        swaps_updated_at: number | null;
        buys_24h: number | null;
        sells_24h: number | null;
        pc_1h: string | null;
        pc_1h_updated_at: number | null;
        is_wash_trading: number | null;
        security_renounced_mint: number | null;
        security_renounced_freeze_account: number | null;
        security_sell_tax: string | null;
        price_ds: string | null;
        volume_ds: string | null;
        liquidity_ds: string | null;
        dex_price: string | null;
        diverge: number | null;
        anchor_bid: string | null;
        anchor_ask: string | null;
        anchor_generated_at: number | null;
        anchor_multiplier: string | null;
        halt: number | null;
        market_closed: number | null;
        oracle_price: string | null;
        oracle_updated_at: number | null;
        commit_ok: number | null;
        chg_price: number | null;
        chg_volume: number | null;
        chg_liquidity: number | null;
        liquidity_num: number | null;
        liquidity_updated_at: number | null;
        liquidity_50k_observation_type: string | null;
        qualified_at: number | null;
        newness_seen_at: number | null;
        newness_created_at: number | null;
        legacy_board: number | null;
      }[];

      const ranked: RankedToken[] = [];
      const finalizedDates = new Set<string>();
      const windowEndTs = canonicalWindowEndTs(now);
      const ndWindowEnd = windowEndTs == null ? null : utcDateKey(windowEndTs);
      // 与前端表头同一个函数、同一个输入，保证每行 7 格和表头日期逐一对应。
      const windowDates = finalizedDateWindow(ndWindowEnd);
      for (const t of tokens) {
        if (watch && !watch.has(`${t.chain}:${t.address}`.toLowerCase())) continue;
        const tokenCreatedAt = t.token_created_at ?? null;
        const pairCreatedAt = t.pair_created_at ?? null;
        const created = displayCreated(tokenCreatedAt, pairCreatedAt);
        const tokenBars = bars.get(`${t.chain}:${t.address}`) ?? [];
        // 日期列只看相邻两根 FINALIZED 日K 是否都在；created_at 偶尔晚于真实首根有量日K，不参与判断。
        const dailySeries = dailyReturnsFromFinalized(tokenBars, now, null);
        for (const date of dailySeries.dates) finalizedDates.add(date);
        const metrics = officialDailyMetrics(tokenBars, now, created.at, days, windowEndTs);
        const return2d = officialDailyMetrics(tokenBars, now, created.at, 2, windowEndTs).changeNd;
        const return3d = officialDailyMetrics(tokenBars, now, created.at, 3, windowEndTs).changeNd;
        const return5d = officialDailyMetrics(tokenBars, now, created.at, 5, windowEndTs).changeNd;
        const changeNd = metrics.changeNd;
        const liq = t.liquidity_num ?? t.liquidity;
        const liqAge = t.liquidity_updated_at == null ? null : now - t.liquidity_updated_at;
        // 改版前：预筛 + “没 N 日累计、池子不够、也没连涨就不下发”。现在全市场照常下发，只把旧集合标出来给连涨榜用。
        const legacyBoard = Number(t.legacy_board ?? 0) === 1;
        const streakPool = watch != null ||
          (legacyBoard && !(changeNd == null && !streakBoardEligible(liq) && metrics.streak == null));
        // 统计口径保持改版前的集合；搜索请求不重复计数。
        if (!search && (watch != null || legacyBoard) && changeNd != null) {
          eligibility.enoughCandleHistory += 1;
          if (streakBoardEligible(liq)) {
            eligibility.liquidityQualified += 1;
            if (formalStreakEligible(liq, liqAge)) eligibility.freshQualified += 1;
          }
        }
        ranked.push({
          chain: t.chain,
          address: t.address,
          symbol: t.symbol,
          name: t.name,
          logo: t.logo,
          creationTs: t.creation_ts,
          tokenCreatedAt,
          pairCreatedAt,
          firstSeenAt: t.first_seen_at ?? null,
          createdAt: created.at,
          createdSource: created.source,
          klineFetchedAt: t.kline_fetched_at ?? null,
          price: t.price ?? "",
          // GMGN price_change_percent 已是百分数（-12.3 = -12.3%），转成小数；空串视为缺失
          pc24h: t.pc_24h != null && t.pc_24h !== "" && isFinite(Number(t.pc_24h))
            ? String(Number(t.pc_24h) / 100)
            : null,
          pc24hSource: t.pc_24h_source ?? null,
          pcInterval: t.pc_24h_source === "trending" ? "24h" : null,
          volume24h: t.volume_24h ?? "",
          liquidity: t.liquidity_num != null ? String(t.liquidity_num) : (t.liquidity ?? ""),
          marketCap: t.market_cap ?? "",
          holders: t.holders,
          priceSource: t.price_source,
          priceUpdatedAt: t.price_updated_at,
          volume24hSource: t.volume_24h_source,
          volume24hUpdatedAt: t.volume_24h_updated_at,
          liquiditySource: t.liquidity_source,
          marketCapSource: t.market_cap_source,
          marketCapUpdatedAt: t.market_cap_updated_at,
          holdersSource: t.holders_source,
          holdersUpdatedAt: t.holders_updated_at,
          securityUpdatedAt: t.security_updated_at,
          securityIsHoneypot: nullableFlag(t.security_is_honeypot),
          securityIsBlacklist: nullableFlag(t.security_is_blacklist),
          securityIsOpenSource: nullableFlag(t.security_is_open_source),
          securityIsRenounced: nullableFlag(t.security_is_renounced),
          securityTop10HolderRate: t.security_top10_holder_rate,
          swaps24h: t.swaps ?? null,
          buys24h: t.buys_24h ?? null,
          sells24h: t.sells_24h ?? null,
          activitySource: t.swaps_source ?? null,
          activityUpdatedAt: t.swaps_updated_at ?? null,
          pc1h: t.pc_1h ?? null,
          pc1hUpdatedAt: t.pc_1h_updated_at ?? null,
          isWashTrading: nullableFlag(t.is_wash_trading),
          securityRenouncedMint: nullableFlag(t.security_renounced_mint),
          securityRenouncedFreezeAccount: nullableFlag(t.security_renounced_freeze_account),
          securitySellTax: t.security_sell_tax ?? null,
          ...(latestEvents.get(`${t.chain}:${t.address}`) ?? {
            trendingRank: null, trendingRankAt: null, trendingRankContext: null,
            hotRank: null, hotRankAt: null, hotRankContext: null,
            lastSignalType: null, lastSignalTriggerAt: null, lastSignalTriggerMc: null,
          }),
          changeNd,
          change1d: metrics.change1d,
          dailyReturns: dailySeries.returns,
          dailyHistory: dailyHistoryForWindow(dailySeries.history, windowDates),
          newnessAt: t.newness_seen_at ?? t.newness_created_at ?? null,
          newnessSource: t.newness_seen_at != null ? "first_seen" : t.newness_created_at != null ? "creation" : null,
          streakPool,
          streak: metrics.streak,
          streakStatus: metrics.streakStatus,
          streakReturn: metrics.streakReturn,
          streakDrawdown: metrics.streakDrawdown,
          closedCandles: metrics.closedCount,
          lastDailyStatus: metrics.lastStatus,
          qualityFlags: metrics.qualityFlags,
          priceDs: t.price_ds,
          volumeDs: t.volume_ds,
          liquidityDs: t.liquidity_ds,
          dexPrice: t.dex_price,
          diverge: Number(t.diverge || 0),
          anchorBid: t.anchor_bid,
          anchorAsk: t.anchor_ask,
          anchorGeneratedAt: t.anchor_generated_at,
          anchorMultiplier: t.anchor_multiplier,
          halt: flag(t.halt),
          marketClosed: flag(t.market_closed),
          oraclePrice: t.oracle_price,
          oracleUpdatedAt: t.oracle_updated_at,
          commitOk: flag(t.commit_ok),
          chgPrice: flag(t.chg_price),
          chgVolume: flag(t.chg_volume),
          chgLiquidity: flag(t.chg_liquidity),
          liquidityNum: t.liquidity_num == null ? null : Number(t.liquidity_num),
          liquidityUpdatedAt: t.liquidity_updated_at ?? null,
          observationType: t.liquidity_50k_observation_type ?? null,
          qualifiedAt: t.qualified_at ?? null,
          // Materialized daily_metrics may cross UTC midnight without a write.
          // API consumers always get the same request-time finalized-candle contract as changeNd.
          return2d,
          return3d,
          return5d,
        });
      }

      const chainTs: Record<string, number> = {};
      for (const r of db.prepare("SELECT chain, MAX(ts) AS ts FROM token_snapshot GROUP BY chain").all() as unknown as { chain: string; ts: number }[]) {
        chainTs[r.chain] = r.ts;
      }
      const lastMarketUpdate = readMeta(db, "last_market_update");
      const metaPriceTs = readMeta(db, "last_price_update");
      const dbPriceTs = readMaxPriceTs(db);
      const lastPriceUpdate =
        metaPriceTs != null
          ? metaPriceTs
          : dbPriceTs != null
            ? String(dbPriceTs)
            : null;
      // 日 K 由 market collector 维护（当日缺则拉），时间戳写在 market_meta
      const lastKlineUpdate = readMeta(db, "last_kline_update");
      const gmgn = readGmgnClocks(db);
      db.close();
      eligibility.finalEligible = eligibility.enoughCandleHistory;
      const dailyDates = latestFinalizedDates(finalizedDates);

      return {
        ok: true,
        tokens: ranked.slice(0, 800),
        dailyDates,
        ndWindowEnd,
        inclusionStats,
        tierStats,
        days,
        eligibility,
        registryCount,
        lastMarketUpdate,
        lastPriceUpdate,
        lastKlineUpdate,
        chainTs,
        gmgn,
      };
    } catch (e) {
      return {
        ok: false,
        tokens: [],
        error: e instanceof Error ? e.message : String(e),
      };
    }
  });

export interface HotToken {
  chain: string;
  address: string;
  price: string;
  volume24h: string;
  liquidity: string;
  priceDs: string | null;
  volumeDs: string | null;
  liquidityDs: string | null;
  dexPrice: string | null;
  diverge: number;
  anchorBid: string | null;
  anchorAsk: string | null;
  anchorGeneratedAt: number | null;
  anchorMultiplier: string | null;
  halt: boolean;
  marketClosed: boolean;
  oraclePrice: string | null;
  oracleUpdatedAt: number | null;
  commitOk: boolean;
  chgPrice: boolean;
  chgVolume: boolean;
  chgLiquidity: boolean;
  liquidityNum: number | null;
  liquidityUpdatedAt: number | null;
  priceSource: string | null;
  priceUpdatedAt: number | null;
  volume24hSource: string | null;
  volume24hUpdatedAt: number | null;
  liquiditySource: string | null;
}

/**
 * 只读当前榜快照的热列，不扫日 K / 小时价。
 * 8 秒一轮，仍只覆盖原榜单预筛集合；全市场新增的“最新 N 个”（无日K、池子 < 5 万）随 60 秒整表刷新。
 */
export const fetchMarketHot = createServerFn({ method: "POST" })
  .validator(z.object({ keys: z.array(z.string()).max(2000).optional() }))
  .handler(async ({ data }): Promise<{
  ok: boolean;
  tokens: HotToken[];
  gmgn: Record<string, GmgnClock>;
  error?: string;
}> => {
  try {
    if (!existsSync(DB_PATH)) return { ok: false, tokens: [], gmgn: {}, error: "数据库不存在" };
    const watch = keySet(data.keys);
    const db = openReadDb();
    const optionalSnapshot = optionalSnapshotSelect(db);
    const rows = db
      .prepare(
        `SELECT s.chain, s.address, s.price, s.volume_24h, s.liquidity, s.liquidity_num,
                s.liquidity_updated_at,
                ${optionalSnapshot},
                s.price_ds, s.volume_ds, s.liquidity_ds, s.dex_price, s.diverge,
                s.anchor_bid, s.anchor_ask, s.anchor_generated_at, s.anchor_multiplier,
                s.halt, s.market_closed, s.oracle_price, s.oracle_updated_at,
                s.commit_ok, s.chg_price, s.chg_volume, s.chg_liquidity
         FROM token_registry r
         JOIN token_snapshot s ON s.chain = r.chain AND s.address = r.address
         LEFT JOIN tokens t ON t.chain = r.chain AND t.address = r.address
         ${watch ? "" : `WHERE ${BOARD_PREFILTER}`}`,
      )
      .all() as unknown as Record<string, string | number | null>[];
    const kept = watch ? rows.filter((t) => watch.has(`${t.chain}:${t.address}`.toLowerCase())) : rows;
    const tokens: HotToken[] = kept.map((t) => ({
      chain: String(t.chain),
      address: String(t.address),
      price: String(t.price ?? ""),
      volume24h: String(t.volume_24h ?? ""),
      liquidity: t.liquidity_num != null ? String(t.liquidity_num) : String(t.liquidity ?? ""),
      liquidityNum: t.liquidity_num == null ? null : Number(t.liquidity_num),
      liquidityUpdatedAt: (t.liquidity_updated_at as number | null) ?? null,
      priceSource: (t.price_source as string | null) ?? null,
      priceUpdatedAt: (t.price_updated_at as number | null) ?? null,
      volume24hSource: (t.volume_24h_source as string | null) ?? null,
      volume24hUpdatedAt: (t.volume_24h_updated_at as number | null) ?? null,
      liquiditySource: (t.liquidity_source as string | null) ?? null,
      priceDs: (t.price_ds as string | null) ?? null,
      volumeDs: (t.volume_ds as string | null) ?? null,
      liquidityDs: (t.liquidity_ds as string | null) ?? null,
      dexPrice: (t.dex_price as string | null) ?? null,
      diverge: Number(t.diverge || 0),
      anchorBid: (t.anchor_bid as string | null) ?? null,
      anchorAsk: (t.anchor_ask as string | null) ?? null,
      anchorGeneratedAt: (t.anchor_generated_at as number | null) ?? null,
      anchorMultiplier: (t.anchor_multiplier as string | null) ?? null,
      halt: flag(t.halt),
      marketClosed: flag(t.market_closed),
      oraclePrice: (t.oracle_price as string | null) ?? null,
      oracleUpdatedAt: (t.oracle_updated_at as number | null) ?? null,
      commitOk: flag(t.commit_ok),
      chgPrice: flag(t.chg_price),
      chgVolume: flag(t.chg_volume),
      chgLiquidity: flag(t.chg_liquidity),
    }));
    const gmgn = readGmgnClocks(db);
    db.close();
    return { ok: true, tokens, gmgn };
  } catch (e) {
    return { ok: false, tokens: [], gmgn: {}, error: e instanceof Error ? e.message : String(e) };
  }
});

export interface EarlyToken {
  chain: string;
  address: string;
  symbol: string | null;
  name: string | null;
  logo: string | null;
  price: string | null;
  pc24h: string | null;
  liquidity: number;
  liquidityUpdatedAt: number | null;
  /** 约 24 小时前最后一次 discovery_event 里记录的流动性；没有就是 null。 */
  liquidity24hAgo: number | null;
  volume24h: number | null;
  buys24h: number | null;
  sells24h: number | null;
  swaps24h: number | null;
  holders: number | null;
  createdAt: number | null;
  firstSeenAt: number | null;
  /** 50000 - liquidity */
  toMain: number;
}

function numOrNull(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** EARLY 观察池：只读 registry + snapshot + discovery_event，不碰日 K。 */
export const fetchMarketEarly = createServerFn({ method: "POST" })
  .validator(z.object({}).optional())
  .handler(async (): Promise<{
    ok: boolean;
    tokens: EarlyToken[];
    inclusionStats?: MarketInclusionStats;
    tierStats?: MarketTierStats;
    error?: string;
  }> => {
    try {
      if (!existsSync(DB_PATH)) return { ok: false, tokens: [], error: "数据库不存在" };
      const db = openReadDb();
      const now = Math.floor(Date.now() / 1000);
      const optionalSnapshot = optionalSnapshotSelect(db);
      const rows = db
        .prepare(
          `SELECT r.chain, r.address,
                  COALESCE(t.symbol, r.symbol) AS symbol,
                  COALESCE(t.name, r.name) AS name,
                  t.logo,
                  COALESCE(t.token_created_at, r.token_created_at, t.creation_ts, t.pair_created_at) AS created_at,
                  r.first_seen_at,
                  s.price, s.pc_24h, s.volume_24h, s.holders,
                  ${SNAPSHOT_LIQ_SQL} AS liq,
                  COALESCE(s.liquidity_updated_at, s.ts) AS liq_at,
                  ${optionalSnapshot},
                  (SELECT e.liquidity FROM discovery_event e
                    WHERE e.chain = r.chain AND e.address = r.address
                      AND e.seen_at <= ? AND e.liquidity IS NOT NULL
                    ORDER BY e.seen_at DESC LIMIT 1) AS liq_24h_ago
           FROM token_registry r
           JOIN token_snapshot s ON s.chain = r.chain AND s.address = r.address
           LEFT JOIN tokens t ON t.chain = r.chain AND t.address = r.address
           WHERE ${EARLY_TIER_SQL}
           ORDER BY liq DESC`,
        )
        .all(now - 86_400) as unknown as Record<string, string | number | null>[];
      const inclusionStats = readMarketInclusionStats(db, now);
      const tierStats = readMarketTierStats(db);
      db.close();
      const tokens: EarlyToken[] = rows.map((t) => {
        const liquidity = Number(t.liq);
        return {
          chain: String(t.chain),
          address: String(t.address),
          symbol: (t.symbol as string | null) ?? null,
          name: (t.name as string | null) ?? null,
          logo: (t.logo as string | null) ?? null,
          price: t.price == null ? null : String(t.price),
          pc24h: t.pc_24h == null ? null : String(t.pc_24h),
          liquidity,
          liquidityUpdatedAt: numOrNull(t.liq_at),
          liquidity24hAgo: numOrNull(t.liq_24h_ago),
          volume24h: numOrNull(t.volume_24h),
          buys24h: numOrNull(t.buys_24h),
          sells24h: numOrNull(t.sells_24h),
          swaps24h: numOrNull(t.swaps),
          holders: numOrNull(t.holders),
          createdAt: numOrNull(t.created_at),
          firstSeenAt: numOrNull(t.first_seen_at),
          toMain: MAIN_MIN_LIQUIDITY - liquidity,
        };
      });
      return { ok: true, tokens, inclusionStats, tierStats };
    } catch (e) {
      return { ok: false, tokens: [], error: e instanceof Error ? e.message : String(e) };
    }
  });
