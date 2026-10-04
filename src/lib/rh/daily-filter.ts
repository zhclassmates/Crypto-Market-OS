import { DAY_SEC, getFinalizedDailyBars, type DailyBar } from "./streak.ts";

export const MARKET_DAILY_COLUMN_LIMIT = 7;

export type DailyReturnMap = Record<string, number | null>;
export type DailyDirection = "UP" | "DOWN";
export type DailyReturnFilters = Record<string, DailyDirection>;

export function utcDateKey(ts: number): string {
  return new Date(ts * 1000).toISOString().slice(0, 10);
}

/** 日期列最多保留最近 15 个自然日；默认视口只露出最近 7 天。 */
export const MARKET_DATE_HISTORY = 15;
export const MARKET_DATE_VIEWPORT = 7;

/** UTC 日历窗口：最近 15 个自然日，今天在最右，不生成未来日期。 */
export function calendarDateWindow(
  now: number,
  history = MARKET_DATE_HISTORY,
): string[] {
  const todayStart = Math.floor(now / DAY_SEC) * DAY_SEC;
  return Array.from(
    { length: history },
    (_, index) => utcDateKey(todayStart - (history - 1 - index) * DAY_SEC),
  );
}

/**
 * 默认 7 天视口里的相对位置：今天 = T+3，T0 = 今天 − 3 天。
 * 更早的日期继续往负数走（T-4、T-5 …）。
 */
export function dateTOffset(date: string, today: string): number {
  const diff = Math.round((Date.parse(`${today}T00:00:00Z`) - Date.parse(`${date}T00:00:00Z`)) / (DAY_SEC * 1000));
  return 3 - diff;
}

export function fmtTOffset(offset: number): string {
  return offset === 0 ? "T0" : offset > 0 ? `T+${offset}` : `T${offset}`;
}

export function formatDailyReturn(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const pct = value * 100;
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${Math.abs(pct).toFixed(1)}%`;
}

/** 展示层日收益：只使用相邻的 FINALIZED UTC 日K。 */
export function dailyReturnsFromFinalized(
  bars: DailyBar[],
  now: number,
  createdAt: number | null,
): { dates: string[]; returns: DailyReturnMap } {
  const finalized = getFinalizedDailyBars(bars, now, createdAt);
  const dates = finalized.map((bar) => utcDateKey(bar.ts));
  const returns: DailyReturnMap = Object.fromEntries(dates.map((date) => [date, null]));

  for (let i = 1; i < finalized.length; i++) {
    const previous = finalized[i - 1]!;
    const current = finalized[i]!;
    if (current.ts - previous.ts !== DAY_SEC || previous.close <= 0) continue;
    returns[utcDateKey(current.ts)] = current.close / previous.close - 1;
  }

  return { dates, returns };
}

export function latestFinalizedDates(
  dates: Iterable<string>,
  limit = MARKET_DAILY_COLUMN_LIMIT,
): string[] {
  if (!Number.isInteger(limit) || limit <= 0) return [];
  return [...new Set(dates)].sort().slice(-limit);
}

export function matchesDailyReturn(
  value: number | null | undefined,
  direction: DailyDirection,
): boolean {
  if (value == null || !Number.isFinite(value)) return false;
  return direction === "UP" ? value > 0 : value < 0;
}

/** 日期条件之间固定使用 AND；缺少任意一天的收益即不通过。 */
export function matchesDailyFilters(
  returns: DailyReturnMap,
  filters: DailyReturnFilters,
): boolean {
  return Object.entries(filters).every(([date, direction]) => matchesDailyReturn(returns[date], direction));
}

/** NONE → UP → DOWN → NONE，且每个状态都绑定实际 calendar date。 */
export function cycleDailyFilter(
  filters: DailyReturnFilters,
  date: string,
): DailyReturnFilters {
  const current = filters[date];
  if (current == null) return { ...filters, [date]: "UP" };
  if (current === "UP") return { ...filters, [date]: "DOWN" };
  return clearDailyFilters(filters, date);
}

export function clearDailyFilters(
  filters: DailyReturnFilters,
  date?: string,
): DailyReturnFilters {
  if (date == null) return {};
  const next = { ...filters };
  delete next[date];
  return next;
}

/** 日期列主排序：只有最后一次点击的日期参与排序，其他日期只筛选。UP = 降序，DOWN = 升序。 */
export interface DailyPrimarySort {
  date: string;
  dir: "desc" | "asc";
}

/** 点击日期列后的主排序：点到 UP/DOWN 就换成这一列；这一列点回 NONE 则取消主排序。 */
export function nextPrimarySort(
  prev: DailyPrimarySort | null,
  date: string,
  direction: DailyDirection | undefined,
): DailyPrimarySort | null {
  if (direction === "UP") return { date, dir: "desc" };
  if (direction === "DOWN") return { date, dir: "asc" };
  return prev?.date === date ? null : prev;
}

/** 按原始数值日收益排序（不是格式化后的字符串）；缺值永远排最后。 */
export function compareDailyReturn(
  a: DailyReturnMap | undefined,
  b: DailyReturnMap | undefined,
  sort: DailyPrimarySort,
): number {
  const va = a?.[sort.date];
  const vb = b?.[sort.date];
  const okA = va != null && Number.isFinite(va);
  const okB = vb != null && Number.isFinite(vb);
  if (!okA && !okB) return 0;
  if (!okA) return 1;
  if (!okB) return -1;
  return sort.dir === "desc" ? vb - va : va - vb;
}

/** 日期列滚动时只保留仍对应同一 calendar date 的条件，绝不按列位置迁移。 */
export function reconcileDailyFilters(
  filters: DailyReturnFilters,
  visibleDates: readonly string[],
): DailyReturnFilters {
  const visible = new Set(visibleDates);
  return Object.fromEntries(Object.entries(filters).filter(([date]) => visible.has(date)));
}
