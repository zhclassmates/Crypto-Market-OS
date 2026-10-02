/** 连涨口径。只使用已收盘、且在拉取时已经走完的 UTC 日 K。 */

export const DAY_SEC = 86400;
export const STREAK_MIN_LIQUIDITY = 50_000;
export const DRAWDOWN_HINT = 0.2;
export const DRAWDOWN_ALERT = 0.4;

/** 市场排行 N 日累计的唯一默认窗口。前端按钮和后端 parse 共用。 */
export const DEFAULT_DAYS = 7;
export const PRESET_DAYS = [1, 2, 3, 5, 7, 10, 14, 30] as const;
export const MAX_CUSTOM_DAYS = 90;

export function parseDays(raw: unknown): number {
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isInteger(n) || n < 1 || n > MAX_CUSTOM_DAYS) return DEFAULT_DAYS;
  return n;
}

export interface DailyBar {
  ts: number;
  high: number;
  close: number;
}

export interface StreakMetrics {
  streak: number;
  /** latest closed close / close before the streak − 1. Null when streak is 0. */
  streakReturn: number | null;
  /** 1 − latest closed close / max high over the streak candles. Null when streak is 0. */
  streakDrawdown: number | null;
  /** last closed close / previous closed close − 1. Not the rolling 24h change. */
  change1d: number | null;
  closedCount: number;
}

export function utcDayStart(now: number): number {
  return now - (now % DAY_SEC);
}

/** 日 K 在最近一个 UTC 日切之后没有再成功拉取，就不能当成已收盘。 */
export function klineIsStale(now: number, klineFetchedAt: number | null): boolean {
  if (klineFetchedAt == null || !Number.isFinite(klineFetchedAt)) return true;
  return klineFetchedAt < utcDayStart(now);
}

export function closedBars(
  bars: DailyBar[],
  now: number,
  klineFetchedAt: number | null,
  createdAt: number | null,
): DailyBar[] {
  if (klineFetchedAt == null || !Number.isFinite(klineFetchedAt)) return [];
  const byTs = new Map<number, DailyBar>();
  for (const bar of bars) {
    if (!Number.isFinite(bar.ts) || !Number.isFinite(bar.close) || bar.close <= 0) continue;
    const end = bar.ts + DAY_SEC;
    if (end > now) continue;
    if (klineFetchedAt < end) continue;
    if (createdAt != null && end <= createdAt) continue;
    const high = Number.isFinite(bar.high) && bar.high > 0 ? bar.high : bar.close;
    byTs.set(bar.ts, { ts: bar.ts, high, close: bar.close });
  }
  return [...byTs.values()].sort((a, b) => a.ts - b.ts);
}

export function streakMetrics(
  bars: DailyBar[],
  now: number,
  klineFetchedAt: number | null,
  createdAt: number | null,
): StreakMetrics {
  const closed = closedBars(bars, now, klineFetchedAt, createdAt);
  let streak = 0;
  for (let i = closed.length - 1; i >= 1; i--) {
    // 前一天是相邻的 UTC 日。缺一天就停，不能拿更早的收盘价顶上。
    if (closed[i].ts - closed[i - 1].ts !== DAY_SEC) break;
    if (closed[i].close > closed[i - 1].close) streak++;
    else break;
  }
  // 没有前收就不能记成上涨。1 根已收盘 K 的比较结果是 0，上限仍是根数本身。
  if (streak > closed.length) streak = closed.length;

  let streakReturn: number | null = null;
  let streakDrawdown: number | null = null;
  if (streak >= 1) {
    const base = closed[closed.length - 1 - streak];
    const latest = closed[closed.length - 1];
    if (base && base.close > 0) streakReturn = latest.close / base.close - 1;
    let high = 0;
    for (let i = closed.length - streak; i < closed.length; i++) {
      if (closed[i].high > high) high = closed[i].high;
    }
    if (high > 0) {
      const dd = 1 - latest.close / high;
      streakDrawdown = dd < 0 ? 0 : dd;
    }
  }

  let change1d: number | null = null;
  if (closed.length >= 2) {
    const prevBar = closed[closed.length - 2];
    const lastBar = closed[closed.length - 1];
    if (lastBar.ts - prevBar.ts === DAY_SEC && prevBar.close > 0) {
      change1d = lastBar.close / prevBar.close - 1;
    }
  }

  return {
    streak,
    streakReturn,
    streakDrawdown,
    change1d,
    closedCount: closed.length,
  };
}

/** 流动性只做金额门槛，不进分数。源过期由页面单独标 stale。 */
export function streakBoardEligible(liquidity: string | number | null | undefined): boolean {
  const n = typeof liquidity === "number" ? liquidity : Number(liquidity);
  return Number.isFinite(n) && n >= STREAK_MIN_LIQUIDITY;
}

/** 正式连涨榜还要求流动性年龄不超过 300 秒。缺年龄不合格。 */
export const LIQUIDITY_FRESHNESS_SEC = 300;

export function formalStreakEligible(
  liquidity: string | number | null | undefined,
  liquidityAgeSec: number | null | undefined,
): boolean {
  if (!streakBoardEligible(liquidity)) return false;
  if (liquidityAgeSec == null || !Number.isFinite(liquidityAgeSec)) return false;
  return liquidityAgeSec <= LIQUIDITY_FRESHNESS_SEC;
}

/**
 * return_Nd = 最近一根已收盘 close / 向前第 N 根连续已收盘日 K 的 close − 1。
 * 窗口里缺任何一根返回 null，不返回 0。
 */
export function returnOverClosedCandles(
  closed: { ts: number; close: number }[],
  n: number,
): number | null {
  if (closed.length < n + 1) return null;
  const window = closed.slice(-(n + 1));
  for (let i = 1; i < window.length; i++) {
    if (window[i]!.ts - window[i - 1]!.ts !== DAY_SEC) return null;
  }
  const base = window[0]!.close;
  const last = window[window.length - 1]!.close;
  if (!(base > 0) || !(last > 0)) return null;
  return last / base - 1;
}

/** 连涨天数优先，累计涨幅只作同天数里的次序。方向同时作用于两个键。 */
export function compareStreakThenReturn(
  a: { streak: number; streakReturn: number | null },
  b: { streak: number; streakReturn: number | null },
  dir: "desc" | "asc" = "desc",
): number {
  const sign = dir === "desc" ? 1 : -1;
  if (a.streak !== b.streak) return (b.streak - a.streak) * sign;
  if (a.streakReturn == null && b.streakReturn == null) return 0;
  if (a.streakReturn == null) return 1;
  if (b.streakReturn == null) return -1;
  return (b.streakReturn - a.streakReturn) * sign;
}

export function displayCreated(
  tokenCreatedAt: number | null,
  pairCreatedAt: number | null,
): { at: number | null; source: "token" | "pair" | null } {
  if (tokenCreatedAt != null && tokenCreatedAt > 0) return { at: tokenCreatedAt, source: "token" };
  if (pairCreatedAt != null && pairCreatedAt > 0) return { at: pairCreatedAt, source: "pair" };
  return { at: null, source: null };
}

export function fmtRelativeAge(now: number, ts: number): string {
  const sec = Math.max(0, Math.floor(now - ts));
  if (sec < 3600) return `${Math.max(1, Math.floor(sec / 60))}m`;
  if (sec < DAY_SEC) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / DAY_SEC)}d`;
}

export function anchorDeviation(poolPrice: number | null, anchorPrice: number | null): number | null {
  if (poolPrice == null || anchorPrice == null || poolPrice <= 0 || anchorPrice <= 0) return null;
  return poolPrice / anchorPrice - 1;
}
