import { DAY_SEC, getFinalizedDailyBars, type DailyBar } from "./streak.ts";

export const MARKET_DAILY_COLUMN_LIMIT = 7;

export type DailyReturnMap = Record<string, number | null>;
export type DailyDirection = "UP" | "DOWN";
export type DailyReturnFilters = Record<string, DailyDirection>;

export function utcDateKey(ts: number): string {
  return new Date(ts * 1000).toISOString().slice(0, 10);
}

/** MarketView 只展示以统一 finalized 终点为基准的最近 7 个自然日。 */
export const MARKET_DATE_HISTORY = 7;
export const MARKET_DATE_VIEWPORT = 7;

/** UTC 日历窗口：以传入时间所在的自然日为终点，不生成更晚日期。 */
export function calendarDateWindow(
  windowEndTs: number,
  history = MARKET_DATE_HISTORY,
): string[] {
  const windowEndStart = Math.floor(windowEndTs / DAY_SEC) * DAY_SEC;
  return Array.from(
    { length: history },
    (_, index) => utcDateKey(windowEndStart - (history - 1 - index) * DAY_SEC),
  );
}

/** 只接受 API 给出的统一 YYYY-MM-DD 终点；缺失或非法时不猜测本机日期。 */
export function finalizedDateWindow(windowEnd: string | null | undefined): string[] {
  if (!windowEnd || !/^\d{4}-\d{2}-\d{2}$/.test(windowEnd)) return [];
  const windowEndMs = Date.parse(`${windowEnd}T00:00:00Z`);
  if (!Number.isFinite(windowEndMs)) return [];
  const windowEndTs = windowEndMs / 1000;
  if (utcDateKey(windowEndTs) !== windowEnd) return [];
  return calendarDateWindow(windowEndTs);
}

/** 统一窗口终点就是 T：窗口七列依次为 T-6 … T0。 */
export function dateTOffset(date: string, windowEnd: string): number {
  return Math.round(
    (Date.parse(`${date}T00:00:00Z`) - Date.parse(`${windowEnd}T00:00:00Z`)) /
      (DAY_SEC * 1000),
  );
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

/**
 * 同一个 (chain, address, date) 的一格：收益和成交量都取自这一天同一根 FINALIZED 日K。
 * returnPct 是小数（0.339 = +33.9%），与 dailyReturns[date] 同值；null = 缺，不是 0。
 */
export interface DailyHistoryEntry {
  date: string;
  returnPct: number | null;
  volumeUsd: number | null;
}

/** "" / null / 非数字 / 负数 → null；只有源明确给出的 0 才是 0。 */
export function parseVolumeUsd(v: unknown): number | null {
  if (v == null) return null;
  if (typeof v === "string" && v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

/** 展示层日收益：只使用相邻的 FINALIZED UTC 日K。 */
export function dailyReturnsFromFinalized(
  bars: DailyBar[],
  now: number,
  createdAt: number | null,
): { dates: string[]; returns: DailyReturnMap; history: Record<string, DailyHistoryEntry> } {
  const finalized = getFinalizedDailyBars(bars, now, createdAt);
  const dates = finalized.map((bar) => utcDateKey(bar.ts));
  const history: Record<string, DailyHistoryEntry> = {};

  for (let i = 0; i < finalized.length; i++) {
    const current = finalized[i]!;
    const previous = i > 0 ? finalized[i - 1]! : null;
    const date = utcDateKey(current.ts);
    const returnPct =
      previous && current.ts - previous.ts === DAY_SEC && previous.close > 0
        ? current.close / previous.close - 1
        : null;
    history[date] = { date, returnPct, volumeUsd: parseVolumeUsd(current.volumeUsd) };
  }

  const returns: DailyReturnMap = Object.fromEntries(
    dates.map((date) => [date, history[date]!.returnPct]),
  );
  return { dates, returns, history };
}

/** 按统一窗口取格子；该日没有 FINALIZED 日K 时两个值都是 null。 */
export function dailyHistoryForWindow(
  history: Record<string, DailyHistoryEntry>,
  windowDates: readonly string[],
): DailyHistoryEntry[] {
  return windowDates.map((date) => history[date] ?? { date, returnPct: null, volumeUsd: null });
}

/** 紧凑 USD：最多 3 位有效数字。null = 没有可信数据 → —；真实 0 → $0。 */
export function formatCompactUsd(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value < 0) return "—";
  if (value === 0) return "$0";
  if (value < 1) return "<$1";
  const rounded = Number(value.toPrecision(3));
  const units: [number, string][] = [[1e9, "B"], [1e6, "M"], [1e3, "K"]];
  for (const [size, suffix] of units) {
    if (rounded >= size) return `$${Number((rounded / size).toPrecision(3))}${suffix}`;
  }
  return `$${Math.round(rounded)}`;
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
