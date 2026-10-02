/** 自选只存在这台浏览器。身份是 chain + address，和榜单同一套。 */

export const WATCH_STORAGE_KEY = "rh.watchlist.v1";
export const WATCH_EVENT = "rh-watchlist";

export interface WatchItem {
  chain: string;
  address: string;
  symbol: string | null;
  name: string | null;
  addedAt: number;
}

export function watchKey(chain: string, address: string): string {
  return `${chain}:${address}`;
}

export function parseWatchlist(raw: string | null): WatchItem[] {
  if (!raw) return [];
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(data)) return [];
  const out: WatchItem[] = [];
  const seen = new Set<string>();
  for (const row of data) {
    if (!row || typeof row !== "object") continue;
    const r = row as Record<string, unknown>;
    const chain = typeof r.chain === "string" ? r.chain.trim() : "";
    const address = typeof r.address === "string" ? r.address.trim() : "";
    if (!chain || !address) continue;
    const key = watchKey(chain, address);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      chain,
      address,
      symbol: typeof r.symbol === "string" ? r.symbol : null,
      name: typeof r.name === "string" ? r.name : null,
      addedAt: typeof r.addedAt === "number" && Number.isFinite(r.addedAt) ? r.addedAt : 0,
    });
  }
  return out;
}

/** 已在名单里则移出，否则追加到末尾。同名不同地址互不影响。 */
export function toggleWatchItem(
  items: WatchItem[],
  next: Omit<WatchItem, "addedAt">,
  now: number,
): WatchItem[] {
  const key = watchKey(next.chain, next.address);
  if (items.some((w) => watchKey(w.chain, w.address) === key)) {
    return items.filter((w) => watchKey(w.chain, w.address) !== key);
  }
  return [
    ...items,
    {
      chain: next.chain,
      address: next.address,
      symbol: next.symbol,
      name: next.name,
      addedAt: now,
    },
  ];
}

export function loadWatchlist(storage: { getItem(key: string): string | null } | null): WatchItem[] {
  if (!storage) return [];
  return parseWatchlist(storage.getItem(WATCH_STORAGE_KEY));
}

export function writeWatchlist(storage: { setItem(key: string, value: string): void }, items: WatchItem[]): void {
  storage.setItem(WATCH_STORAGE_KEY, JSON.stringify(items));
}
