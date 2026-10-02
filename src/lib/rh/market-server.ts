import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { DatabaseSync, type StatementSync } from "node:sqlite";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  closedBars,
  displayCreated,
  parseDays,
  returnOverClosedCandles,
  streakBoardEligible,
  streakMetrics,
  STREAK_MIN_LIQUIDITY,
  type DailyBar,
} from "./streak.ts";

const DB_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  "../../../rh_v2/market.sqlite",
);

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
  volume24h: string;
  liquidity: string;
  marketCap: string;
  holders: number | null;
  changeNd: number | null; // 已收盘 UTC 日 K 的 N 日累计。不是滚动 24H，也不是日K
  change1d: number | null; // 日K：最近两根已收盘日 K 的收盘比。closed_daily_change
  streak: number;
  streakReturn: number | null;
  streakDrawdown: number | null;
  closedCandles: number;
  spark: number[] | null; // 最近 24 个整点美元价
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

function loadDailyBars(db: DatabaseSync): Map<string, DailyBar[]> {
  const rows = db.prepare("SELECT chain, address, ts, high, close FROM daily_kline").all() as unknown as {
    chain: string;
    address: string;
    ts: number;
    high: string | null;
    close: string | null;
  }[];
  const out = new Map<string, DailyBar[]>();
  for (const row of rows) {
    const key = `${row.chain}:${row.address}`;
    let list = out.get(key);
    if (!list) {
      list = [];
      out.set(key, list);
    }
    list.push({ ts: row.ts, high: Number(row.high), close: Number(row.close) });
  }
  return out;
}

function sparkline(stmt: StatementSync, chain: string, address: string, now: number): number[] | null {
  const since = now - now % 3600 - 24 * 3600;
  const rows = stmt.all(chain, address, since) as unknown as { price: string }[];
  if (rows.length < 2) return null;
  return rows.map((r) => Number(r.price)).filter((n) => isFinite(n) && n > 0);
}

/**
 * 没有日 K、池子也不到连涨门槛的币进不了任何一个榜，不往前端送。
 * 全市场 7000+ 个币里大多是这种，整表下发会让接口和页面都卡住。
 */
const BOARD_PREFILTER = `(t.kline_fetched_at IS NOT NULL OR s.liquidity_num >= ${STREAK_MIN_LIQUIDITY})`;

function keySet(keys: string[] | undefined): Set<string> | null {
  return keys ? new Set(keys) : null;
}

function readMeta(db: DatabaseSync, k: string): string | null {
  const row = db.prepare("SELECT v FROM market_meta WHERE k=?").get(k) as { v: string } | undefined;
  return row?.v ?? null;
}

function readMaxPriceTs(db: DatabaseSync): number | null {
  const row = db.prepare("SELECT MAX(ts) AS ts FROM hourly_price").get() as { ts: number | null } | undefined;
  return row?.ts ?? null;
}

export const fetchMarketRank = createServerFn({ method: "POST" })
  .validator(z.object({ days: z.unknown().optional(), keys: z.array(z.string()).max(2000).optional() }))
  .handler(async ({ data }): Promise<{
    ok: boolean;
    tokens: RankedToken[];
    days?: number;
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
      const bars = loadDailyBars(db);
      const sparkStmt = db.prepare(
        "SELECT price FROM hourly_price WHERE chain=? AND address=? AND ts >= ? ORDER BY ts ASC",
      );
      const registryCount = (db.prepare("SELECT COUNT(*) AS n FROM token_registry").get() as { n: number }).n;

      const tokens = db
        .prepare(
          `SELECT r.chain, r.address,
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
                  r.liquidity_50k_observation_type, r.qualified_at,
                  m.return_2d, m.return_3d, m.return_5d
           FROM token_registry r
           LEFT JOIN tokens t ON t.chain = r.chain AND t.address = r.address
           LEFT JOIN token_snapshot s ON s.chain = r.chain AND s.address = r.address
           LEFT JOIN daily_metrics m ON m.chain = r.chain AND m.address = r.address
             AND m.as_of_date = (
               SELECT MAX(m2.as_of_date) FROM daily_metrics m2
               WHERE m2.chain = r.chain AND m2.address = r.address
             )
           ${watch ? "" : `WHERE ${BOARD_PREFILTER}`}`,
        )
        .all() as unknown as {
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
        return_2d: number | null;
        return_3d: number | null;
        return_5d: number | null;
      }[];

      const ranked: RankedToken[] = [];
      for (const t of tokens) {
        if (watch && !watch.has(`${t.chain}:${t.address}`)) continue;
        const tokenCreatedAt = t.token_created_at ?? null;
        const pairCreatedAt = t.pair_created_at ?? null;
        const created = displayCreated(tokenCreatedAt, pairCreatedAt);
        const tokenBars = bars.get(`${t.chain}:${t.address}`) ?? [];
        const metrics = streakMetrics(
          tokenBars,
          now,
          t.kline_fetched_at ?? null,
          created.at,
        );
        const closed = closedBars(
          tokenBars,
          now,
          t.kline_fetched_at ?? null,
          created.at,
        );
        const changeNd = returnOverClosedCandles(closed, days);
        // 全市场榜要 N 日累计，连涨榜要流动性门槛；两样都不沾的不下发。自选不过滤。
        if (!watch && changeNd == null && !streakBoardEligible(t.liquidity_num ?? t.liquidity)) continue;
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
          volume24h: t.volume_24h ?? "",
          liquidity: t.liquidity_num != null ? String(t.liquidity_num) : (t.liquidity ?? ""),
          marketCap: t.market_cap ?? "",
          holders: t.holders,
          changeNd,
          change1d: metrics.change1d,
          streak: metrics.streak,
          streakReturn: metrics.streakReturn,
          streakDrawdown: metrics.streakDrawdown,
          closedCandles: metrics.closedCount,
          spark: sparkline(sparkStmt, t.chain, t.address, now),
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
          return2d: t.return_2d == null ? null : Number(t.return_2d),
          return3d: t.return_3d == null ? null : Number(t.return_3d),
          return5d: t.return_5d == null ? null : Number(t.return_5d),
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

      return {
        ok: true,
        tokens: ranked,
        days,
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
}

/** 只读当前榜快照的热列，不扫日 K / 小时价。 */
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
    const rows = db
      .prepare(
        `SELECT s.chain, s.address, s.price, s.volume_24h, s.liquidity, s.liquidity_num,
                s.liquidity_updated_at,
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
    const kept = watch ? rows.filter((t) => watch.has(`${t.chain}:${t.address}`)) : rows;
    const tokens: HotToken[] = kept.map((t) => ({
      chain: String(t.chain),
      address: String(t.address),
      price: String(t.price ?? ""),
      volume24h: String(t.volume_24h ?? ""),
      liquidity: t.liquidity_num != null ? String(t.liquidity_num) : String(t.liquidity ?? ""),
      liquidityNum: t.liquidity_num == null ? null : Number(t.liquidity_num),
      liquidityUpdatedAt: (t.liquidity_updated_at as number | null) ?? null,
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