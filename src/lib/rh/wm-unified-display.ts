import {loadWatchlist,writeWatchlist} from "./watchlist.ts";
import { formatDailyReturn } from "./daily-filter.ts";
/** Unified SQLite daily_return stores percentage points; legacy UI takes a ratio. */
export function formatUnifiedDailyReturn(percentPoints: number | null | undefined): string {
  return formatDailyReturn(percentPoints == null ? null : percentPoints / 100);
}
export type DatePriority = { date: string; direction: "asc" | "desc" };
/** Up (highest return first), down (lowest first), then unranked. */
export function cycleDateSort(prior: DatePriority[], date: string, _append = true): DatePriority[] {
  const old=prior.find(d=>d.date===date);
  const next=old?.direction==="asc" ? undefined : {date,direction:old?.direction==="desc" ? "asc" as const : "desc" as const};
  const others = prior.filter(d => d.date !== date);
  return next ? [next, ...others] : others;
}

export function completedUtcWindow(now = new Date()): string[] {
  const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - 1));
  return Array.from({ length: 7 }, (_, i) => {
    const day = new Date(end);
    day.setUTCDate(day.getUTCDate() - 6 + i);
    return day.toISOString().slice(0, 10);
  });
}

export function historyGapLabel(firstSeen: string | null, date: string): string {
  return firstSeen && firstSeen.slice(0, 10) > date ? "未收录：该日尚无本地记录" : "历史缺口：未采集到有效日终价";
}

export const DEFAULT_WATCH_SEEDED = "unified-native-watch-seeded-v1";
export function seedDefaultWatch(storage: {getItem(k:string):string|null;setItem(k:string,v:string):void}, defaults: {canonical_asset_id:string;name:string|null;symbol:string|null}[], now=Date.now()) {
  if (storage.getItem(DEFAULT_WATCH_SEEDED) || defaults.length !== 3) return false;
  const items=loadWatchlist(storage);
  for (const row of defaults) if (!items.some(w=>w.chain==='unified' && w.address===row.canonical_asset_id))
    items.push({chain:'unified',address:row.canonical_asset_id,name:row.name,symbol:row.symbol,addedAt:now});
  writeWatchlist(storage,items);
  storage.setItem(DEFAULT_WATCH_SEEDED,'1');
  return true;
}
