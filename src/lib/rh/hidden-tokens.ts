/** 仅影响这台浏览器的 MarketView 展示，不改变任何服务端数据。 */
export const HIDDEN_TOKENS_STORAGE_KEY = "market-hidden-tokens-v1";
export const HIDDEN_TOKENS_EVENT = "market-hidden-tokens-change";

export function hiddenTokenKey(chain: string, address: string): string {
  const normalizedChain = chain.trim().toLowerCase();
  const normalizedAddress = (normalizedChain === "sol" || normalizedChain === "solana")
    ? address.trim()
    : address.trim().toLowerCase();
  return `${normalizedChain}:${normalizedAddress}`;
}

function normalizeStoredKey(value: string): string | null {
  const separator = value.indexOf(":");
  if (separator <= 0 || separator === value.length - 1) return null;
  const chain = value.slice(0, separator).trim();
  const address = value.slice(separator + 1).trim();
  if (!chain || !address) return null;
  return hiddenTokenKey(chain, address);
}

export function parseHiddenTokens(raw: string | null): string[] {
  if (!raw) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];
  const keys = new Set<string>();
  for (const value of parsed) {
    if (typeof value !== "string") continue;
    const key = normalizeStoredKey(value);
    if (key) keys.add(key);
  }
  return [...keys];
}

export function loadHiddenTokens(storage: { getItem(key: string): string | null } | null): string[] {
  return storage ? parseHiddenTokens(storage.getItem(HIDDEN_TOKENS_STORAGE_KEY)) : [];
}

export function writeHiddenTokens(
  storage: { setItem(key: string, value: string): void },
  keys: readonly string[],
): void {
  storage.setItem(HIDDEN_TOKENS_STORAGE_KEY, JSON.stringify([...new Set(keys)]));
}

export function addHiddenToken(keys: readonly string[], chain: string, address: string): string[] {
  const next = new Set(keys);
  next.add(hiddenTokenKey(chain, address));
  return [...next];
}

export function removeHiddenToken(keys: readonly string[], key: string): string[] {
  const normalized = normalizeStoredKey(key);
  if (!normalized) return [...keys];
  return keys.filter((item) => item !== normalized);
}
