/** 日 K 定稿、连涨与 N 日累计。market / streak 共用这一份实现。 */

export const DAY_SEC = 86400;
export const STREAK_MIN_LIQUIDITY = 50_000;
export const DRAWDOWN_HINT = 0.2;
export const DRAWDOWN_ALERT = 0.4;
/** 一次日 K 请求回看多远。与 rh_v2/market_research.py KLINE_FETCH_WINDOW_SEC 相同。 */
export const KLINE_FETCH_WINDOW_SEC = 100 * DAY_SEC;

/** 市场排行 N 日累计的唯一默认窗口。前端按钮和后端 parse 共用。 */
export const DEFAULT_DAYS = 7;
export const PRESET_DAYS = [1, 2, 3, 5, 7, 10, 14, 30] as const;
export const MAX_CUSTOM_DAYS = 90;

/**
 * 相邻已收盘日对里，前收低于约 1% 分位（2026-10-02 market.sqlite 实测 p1≈6e-9）。
 * 只做质量标签，不改 raw return。
 */
export const LOW_BASE_CLOSE = 1e-8;
/**
 * |return| ≥ 50（5000%）。同库 abs 1D 的 p99.9≈18.7，HEARTH 1D≈292766。
 * 只做质量标签，不改 raw return。
 */
export const EXTREME_ABS_RETURN = 50;

export type DailyStatus = "OPEN" | "PROVISIONAL" | "FINALIZED";
export type StreakStatus = "POSITIVE_STREAK" | "VALID_ZERO" | "INSUFFICIENT_DATA";
export type QualityFlag = "LOW_BASE" | "EXTREME_RETURN";
export type RankWriteChannel = "data" | "error" | "loading" | "eligibility";

export function parseDays(raw: unknown): number {
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isInteger(n) || n < 1 || n > MAX_CUSTOM_DAYS) return DEFAULT_DAYS;
  return n;
}

export interface DailyBar {
  ts: number;
  high: number;
  close: number;
  /** 这一根自己的抓取时间。禁止用 token 级 kline_fetched_at 顶上。 */
  fetchedAt?: number | null;
  /** 第一次满足 finalized 条件的时间。可空，定稿可现场算。 */
  finalizedAt?: number | null;
  /** 数据源若明确给了 closed/final，优先采信。 */
  sourceClosed?: boolean | null;
}

export interface ClassifiedBar extends DailyBar {
  end: number;
  status: DailyStatus;
}

export interface StreakMetrics {
  /** 正式连涨。INSUFFICIENT_DATA 为 null（页面显示 —），VALID_ZERO 为 0。 */
  streak: number | null;
  streakStatus: StreakStatus;
  /** latest finalized close / close before the streak − 1. Null when streak is 0 or unavailable. */
  streakReturn: number | null;
  /** 1 − latest finalized close / max high over the streak candles. */
  streakDrawdown: number | null;
  /** last finalized close / previous finalized close − 1. */
  change1d: number | null;
  closedCount: number;
  lastStatus: DailyStatus | null;
  qualityFlags: QualityFlag[];
}

export function patternFromFinalized(
  finalized: { close: number; ts: number }[],
): { pattern: string; downDays: number; flatDays: number } {
  const marks: string[] = [];
  for (let i = 1; i < finalized.length; i++) {
    const prev = finalized[i - 1]!.close;
    const curr = finalized[i]!.close;
    if (curr > prev) marks.push("+");
    else if (curr < prev) marks.push("-");
    else marks.push("=");
  }
  const run = (target: string) => {
    let count = 0;
    for (let i = marks.length - 1; i >= 0; i--) {
      if (marks[i] !== target) break;
      count++;
    }
    return count;
  };
  return { pattern: marks.join(""), downDays: run("-"), flatDays: run("=") };
}

export function utcDayStart(now: number): number {
  return now - (now % DAY_SEC);
}

export function barEnd(ts: number): number {
  return ts + DAY_SEC;
}

export function calendarClosed(bar: { ts: number }, now: number): boolean {
  return barEnd(bar.ts) <= now;
}

/**
 * bar 所在 UTC 日 >= token 创建日。createdAt 只判断代币当时是否存在，
 * 不参与是否收盘 / 是否定稿。
 */
export function barEligibleByCreation(barTs: number, createdAt: number | null): boolean {
  if (createdAt == null || !Number.isFinite(createdAt) || createdAt <= 0) return true;
  return barTs >= utcDayStart(createdAt);
}

/**
 * 历史日 K 是否 FINALIZED，只由产生/证明这根 bar 的观测时间决定。
 * observed_at >= bar_end，且 bar 落在该次日 K 请求的回看窗口里。
 * 读数时刻 now / 迁移时刻不得代入。缺观测时间 → 不能定稿。
 */
export function observationProvesFinal(
  barOpen: number,
  observedAt: number | null | undefined,
): boolean {
  if (observedAt == null || !Number.isFinite(observedAt)) return false;
  if (observedAt < barOpen + DAY_SEC) return false;
  if (barOpen < observedAt - KLINE_FETCH_WINDOW_SEC) return false;
  return true;
}

/**
 * OPEN：日历还没收盘（now 只用于这一档）。
 * FINALIZED：这根 bar 自己的观测时间证明 close 已发生。
 * PROVISIONAL：日历已过，但没有可证明的观测。
 * sourceClosed 不能在缺少观测时间时猜定稿。
 */
export function barStatus(bar: DailyBar, now: number): DailyStatus {
  if (barEnd(bar.ts) > now) return "OPEN";
  if (observationProvesFinal(bar.ts, bar.finalizedAt) || observationProvesFinal(bar.ts, bar.fetchedAt)) {
    return "FINALIZED";
  }
  return "PROVISIONAL";
}

export function classifyBars(
  bars: DailyBar[],
  now: number,
  createdAt: number | null,
): ClassifiedBar[] {
  const byTs = new Map<number, ClassifiedBar>();
  for (const bar of bars) {
    if (!Number.isFinite(bar.ts) || !Number.isFinite(bar.close) || bar.close <= 0) continue;
    if (!barEligibleByCreation(bar.ts, createdAt)) continue;
    const high = Number.isFinite(bar.high) && bar.high > 0 ? bar.high : bar.close;
    const classified: ClassifiedBar = {
      ts: bar.ts,
      high,
      close: bar.close,
      fetchedAt: bar.fetchedAt ?? null,
      finalizedAt: bar.finalizedAt ?? null,
      sourceClosed: bar.sourceClosed ?? null,
      end: barEnd(bar.ts),
      status: barStatus(bar, now),
    };
    byTs.set(bar.ts, classified);
  }
  return [...byTs.values()].sort((a, b) => a.ts - b.ts);
}

export function getFinalizedDailyBars(
  bars: DailyBar[],
  now: number,
  createdAt: number | null,
): ClassifiedBar[] {
  return classifyBars(bars, now, createdAt).filter((b) => b.status === "FINALIZED");
}

/**
 * 日历已收盘的日 K，含 PROVISIONAL。不从序列里删掉未定稿的 bar。
 * klineFetchedAt 参数只为兼容旧调用，不参与成员资格。
 */
export function closedBars(
  bars: DailyBar[],
  now: number,
  klineFetchedAt: number | null,
  createdAt: number | null,
): DailyBar[] {
  void klineFetchedAt;
  return classifyBars(bars, now, createdAt).filter((b) => b.status !== "OPEN");
}

export function hasContiguousDays(bars: { ts: number }[], n: number): boolean {
  if (!Number.isInteger(n) || n < 1) return false;
  if (bars.length < n + 1) return false;
  const window = bars.slice(-(n + 1));
  for (let i = 1; i < window.length; i++) {
    if (window[i]!.ts - window[i - 1]!.ts !== DAY_SEC) return false;
  }
  return true;
}

/**
 * 日 K 新鲜度：当前 UTC 日开始之后还没有成功拉取。
 * 与 finalized 是两条轴。昨天已 FINALIZED 但今天没重拉，仍可标 stale。
 */
export function klineIsStale(now: number, klineFetchedAt: number | null): boolean {
  if (klineFetchedAt == null || !Number.isFinite(klineFetchedAt)) return true;
  return klineFetchedAt < utcDayStart(now);
}

/** 快速切换 N 日窗口时，只有最新一次请求能写回。成功 / 失败 / loading / eligibility 都走这里。 */
export function isCurrentDaysRequest(
  requestSeq: number,
  latestSeq: number,
  requestDays: number,
  selectedDays: number,
): boolean {
  return requestSeq === latestSeq && requestDays === selectedDays;
}

export function shouldCommitRankWrite(
  requestSeq: number,
  latestSeq: number,
  requestDays: number,
  selectedDays: number,
  _channel: RankWriteChannel,
): boolean {
  void _channel;
  return isCurrentDaysRequest(requestSeq, latestSeq, requestDays, selectedDays);
}

export function streakFromClosed(
  finalized: { ts: number; close: number }[],
): { streak: number | null; status: StreakStatus } {
  if (
    finalized.length < 2
    || finalized[finalized.length - 1]!.ts - finalized[finalized.length - 2]!.ts !== DAY_SEC
  ) {
    return { streak: null, status: "INSUFFICIENT_DATA" };
  }
  let streak = 0;
  for (let i = finalized.length - 1; i >= 1; i--) {
    if (finalized[i]!.ts - finalized[i - 1]!.ts !== DAY_SEC) break;
    if (finalized[i]!.close > finalized[i - 1]!.close) streak++;
    else break;
  }
  if (streak >= 1) return { streak, status: "POSITIVE_STREAK" };
  return { streak: 0, status: "VALID_ZERO" };
}

/** 与 Python streak_from_closed 相同。缺前一日 → null，明确没涨 → 0。 */
export function calcStreak(finalized: { ts: number; close: number }[]): number | null {
  return streakFromClosed(finalized).streak;
}

export function calcNDayReturn(
  finalized: { ts: number; close: number }[],
  n: number,
): number | null {
  return returnOverClosedCandles(finalized, n);
}

function officialAvailable(calendarClosed: ClassifiedBar[]): boolean {
  const last = calendarClosed[calendarClosed.length - 1];
  return last != null && last.status === "FINALIZED";
}

export function qualityFlagsFor(
  finalized: { ts: number; close: number }[],
  change1d: number | null,
  changeNd: number | null,
  n?: number,
): QualityFlag[] {
  const flags = new Set<QualityFlag>();
  if (finalized.length >= 2) {
    const prev = finalized[finalized.length - 2]!;
    const last = finalized[finalized.length - 1]!;
    if (last.ts - prev.ts === DAY_SEC && prev.close > 0 && prev.close < LOW_BASE_CLOSE) {
      flags.add("LOW_BASE");
    }
  }
  if (typeof n === "number" && changeNd != null && hasContiguousDays(finalized, n)) {
    const base = finalized[finalized.length - 1 - n]!.close;
    if (base > 0 && base < LOW_BASE_CLOSE) flags.add("LOW_BASE");
  }
  if (change1d != null && Math.abs(change1d) >= EXTREME_ABS_RETURN) flags.add("EXTREME_RETURN");
  if (changeNd != null && Math.abs(changeNd) >= EXTREME_ABS_RETURN) flags.add("EXTREME_RETURN");
  return [...flags];
}

export function rankingQualityOk(flags: readonly string[]): boolean {
  return !flags.includes("LOW_BASE") && !flags.includes("EXTREME_RETURN");
}

/**
 * 全市场统一的 N 日窗口终点：UTC 昨天（今天的日K 还没收盘）。
 * 只由日历决定，不看任何 token 的数据：个别 token 提前/延迟、修复队列补数，
 * 都不能推进或回退市场日期。数据没到的 token 在这个终点上就是 incomplete。
 */
export function canonicalWindowEndTs(now: number): number {
  return utcDayStart(now) - DAY_SEC;
}

/**
 * ND = N 个涨跌日（close(D) vs close(D−1)），需要 N+1 根连续 FINALIZED 日K。
 * display 是 N 个展示日，required 是 N+1 根所需日K。
 */
export function ndWindowDays(windowEndTs: number, n: number): { display: number[]; required: number[] } {
  const required = Array.from({ length: n + 1 }, (_, i) => windowEndTs - (n - i) * DAY_SEC);
  return { display: required.slice(1), required };
}

export function officialDailyMetrics(
  bars: DailyBar[],
  now: number,
  createdAt: number | null,
  n: number,
  /** 给了就要求 N 日窗口恰好结束在这根日K；token 自己最后一根更早时不算完整。 */
  windowEndTs: number | null = null,
): StreakMetrics & { changeNd: number | null } {
  const classified = classifyBars(bars, now, createdAt);
  const calendar = classified.filter((b) => b.status !== "OPEN");
  const finalized = classified.filter((b) => b.status === "FINALIZED");
  const lastStatus = calendar.at(-1)?.status ?? null;

  if (!officialAvailable(calendar)) {
    const emptyFlags: QualityFlag[] = [];
    return {
      streak: null,
      streakStatus: "INSUFFICIENT_DATA",
      streakReturn: null,
      streakDrawdown: null,
      change1d: null,
      closedCount: finalized.length,
      lastStatus,
      qualityFlags: emptyFlags,
      changeNd: null,
    };
  }

  const { streak, status: streakStatus } = streakFromClosed(finalized);
  let streakReturn: number | null = null;
  let streakDrawdown: number | null = null;
  if (streak != null && streak >= 1) {
    const base = finalized[finalized.length - 1 - streak];
    const latest = finalized[finalized.length - 1]!;
    if (base && base.close > 0) streakReturn = latest.close / base.close - 1;
    let high = 0;
    for (let i = finalized.length - streak; i < finalized.length; i++) {
      if (finalized[i]!.high > high) high = finalized[i]!.high;
    }
    if (high > 0) {
      const dd = 1 - latest.close / high;
      streakDrawdown = dd < 0 ? 0 : dd;
    }
  }

  let change1d: number | null = null;
  if (finalized.length >= 2) {
    const prevBar = finalized[finalized.length - 2]!;
    const lastBar = finalized[finalized.length - 1]!;
    if (lastBar.ts - prevBar.ts === DAY_SEC && prevBar.close > 0) {
      change1d = lastBar.close / prevBar.close - 1;
    }
  }

  const endsOnWindow = windowEndTs == null || finalized.at(-1)?.ts === windowEndTs;
  const changeNd = endsOnWindow ? calcNDayReturn(finalized, n) : null;
  const qualityFlags = qualityFlagsFor(finalized, change1d, changeNd, n);
  return {
    streak,
    streakStatus,
    streakReturn,
    streakDrawdown,
    change1d,
    closedCount: finalized.length,
    lastStatus,
    qualityFlags,
    changeNd,
  };
}

export function streakMetrics(
  bars: DailyBar[],
  now: number,
  klineFetchedAt: number | null,
  createdAt: number | null,
): StreakMetrics {
  void klineFetchedAt;
  const m = officialDailyMetrics(bars, now, createdAt, 1);
  return {
    streak: m.streak,
    streakStatus: m.streakStatus,
    streakReturn: m.streakReturn,
    streakDrawdown: m.streakDrawdown,
    change1d: m.change1d,
    closedCount: m.closedCount,
    lastStatus: m.lastStatus,
    qualityFlags: m.qualityFlags,
  };
}

/** 流动性只做金额门槛，不进分数。源过期由页面单独标 stale。 */
export function streakBoardEligible(liquidity: string | number | null | undefined): boolean {
  const n = typeof liquidity === "number" ? liquidity : Number(liquidity);
  return Number.isFinite(n) && n >= STREAK_MIN_LIQUIDITY;
}

/** 正式连涨榜还要求流动性年龄不超过 300 秒。缺年龄不合格。 */
export const LIQUIDITY_FRESHNESS_SEC = 300;

/** 连涨榜只接受真正的正连涨；VALID_ZERO 与数据不足都不合格。 */
export function isPositiveStreak(status: StreakStatus | null | undefined): boolean {
  return status === "POSITIVE_STREAK";
}

export function formalStreakEligible(
  liquidity: string | number | null | undefined,
  liquidityAgeSec: number | null | undefined,
): boolean {
  if (!streakBoardEligible(liquidity)) return false;
  if (liquidityAgeSec == null || !Number.isFinite(liquidityAgeSec)) return false;
  return liquidityAgeSec <= LIQUIDITY_FRESHNESS_SEC;
}

/**
 * return_Nd = 最近一根已定稿 close / 向前第 N 根连续已定稿日 K 的 close − 1。
 * 窗口里缺任何一根返回 null，不返回 0。不在这里封顶或改数。
 */
export function returnOverClosedCandles(
  closed: { ts: number; close: number }[],
  n: number,
): number | null {
  if (!Number.isInteger(n) || n < 1) return null;
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

/** 连涨天数优先，累计涨幅只作同天数里的次序。方向同时作用于两个键。null 排最后。 */
export function compareStreakThenReturn(
  a: { streak: number | null; streakReturn: number | null },
  b: { streak: number | null; streakReturn: number | null },
  dir: "desc" | "asc" = "desc",
): number {
  const sign = dir === "desc" ? 1 : -1;
  if (a.streak == null && b.streak == null) {
    /* fall through to return */
  } else if (a.streak == null) return 1;
  else if (b.streak == null) return -1;
  else if (a.streak !== b.streak) return (b.streak - a.streak) * sign;
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
