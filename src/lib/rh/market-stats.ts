import type { DatabaseSync } from "node:sqlite";
import { DAY_SEC, utcDayStart } from "./streak.ts";

export interface MarketInclusionStats {
  totalTokens: number;
  todayNewTokens: number;
}

/** 收录口径只认 chain + address 的最早 first_seen_at。 */
export function readMarketInclusionStats(db: DatabaseSync, now: number): MarketInclusionStats {
  const dayStart = utcDayStart(now);
  const identityRows = `
    SELECT chain, address, MIN(first_seen_at) AS first_seen_at
    FROM token_registry
    GROUP BY chain, address
  `;
  const total = db.prepare(`SELECT COUNT(*) AS n FROM (${identityRows})`).get() as { n: number };
  const today = db
    .prepare(`SELECT COUNT(*) AS n FROM (${identityRows}) WHERE first_seen_at >= ? AND first_seen_at < ?`)
    .get(dayStart, dayStart + DAY_SEC) as { n: number };
  return { totalTokens: Number(total.n), todayNewTokens: Number(today.n) };
}

export const EARLY_MIN_LIQUIDITY = 20_000;
export const MAIN_MIN_LIQUIDITY = 50_000;

/** 当前流动性：与 Python pick_kline_repair 同一口径。需要别名 s = token_snapshot。 */
export const SNAPSHOT_LIQ_SQL = "COALESCE(s.liquidity_num, CAST(NULLIF(s.liquidity, '') AS REAL))";
/**
 * MAIN = 现有日 K 队列门槛（rh_v2/market_research.py MAIN_TIER_SQL）：
 * 已观测到 50k、已回填，或当前流动性 >= 50k。需要别名 r = token_registry。
 */
export const MAIN_TIER_SQL =
  `(r.first_liquidity_50k_at IS NOT NULL OR r.kline_backfilled_at IS NOT NULL OR ${SNAPSHOT_LIQ_SQL} >= ${MAIN_MIN_LIQUIDITY})`;
/** EARLY = 不是 MAIN，且 20k <= 当前流动性 < 50k。只观察，不进日 K 队列。 */
export const EARLY_TIER_SQL = `(NOT ${MAIN_TIER_SQL} AND ${SNAPSHOT_LIQ_SQL} >= ${EARLY_MIN_LIQUIDITY})`;

export interface MarketTierStats {
  mainTokens: number;
  earlyTokens: number;
  ignoreTokens: number;
}

export function readMarketTierStats(db: DatabaseSync): MarketTierStats {
  const row = db
    .prepare(
      `SELECT SUM(CASE WHEN ${MAIN_TIER_SQL} THEN 1 ELSE 0 END) AS main,
              SUM(CASE WHEN ${EARLY_TIER_SQL} THEN 1 ELSE 0 END) AS early,
              COUNT(*) AS total
       FROM token_registry r
       LEFT JOIN token_snapshot s ON s.chain = r.chain AND s.address = r.address`,
    )
    .get() as { main: number | null; early: number | null; total: number };
  const main = Number(row.main ?? 0);
  const early = Number(row.early ?? 0);
  return { mainTokens: main, earlyTokens: early, ignoreTokens: Number(row.total) - main - early };
}
