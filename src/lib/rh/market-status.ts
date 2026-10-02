/** 与 rh_v2/market_health.py 同一套口径。浏览器和接口都能引用。 */

export const FAIL_THRESHOLD = 3;
export const DIVERGE_RATIO = 0.05;
export const GMGN_PRICE_PERIOD = 300;
export const CHAINLINK_POLL_PERIOD = 30;

export const CHAINS = ["sol", "base", "eth", "robinhood"] as const;

export const SOURCE_PERIOD: Record<string, number> = {
  gmgn: 300,
  gmgn_hot: 120,
  gmgn_new_pair: 300,
  gmgn_signal: 300,
  gmgn_kline: 60,
  gmgn_security: 600,
  dexscreener: 15,
  robinhood_anchor: 15,
  chainlink: 30,
};

export const SOURCE_LABEL: Record<string, string> = {
  gmgn: "GMGN",
  gmgn_hot: "GMGN 热搜",
  gmgn_new_pair: "GMGN Trenches",
  gmgn_signal: "GMGN Signal",
  gmgn_kline: "GMGN 日K",
  gmgn_security: "GMGN 安全",
  dexscreener: "DexScreener",
  robinhood_anchor: "Robinhood 锚价",
  chainlink: "Chainlink",
};

export const CHAIN_LABEL: Record<string, string> = {
  sol: "Solana",
  base: "Base",
  eth: "Ethereum",
  robinhood: "Robinhood",
};

export type MarketStatus =
  | "LIVE"
  | "DELAYED"
  | "STALE"
  | "FAILED"
  | "healthy"
  | "rate_limited"
  | "cooldown"
  | "failed"
  | "unsupported"
  | "zero_write";

export interface HealthSource {
  source: string;
  chain: string;
  periodSec: number;
  status: MarketStatus;
  apiAgeSec: number | null;
  dbAgeSec: number | null;
  latencyMs: number | null;
  p95LatencyMs: number | null;
  hotChanged: number;
  coldChanged: number;
  rowsReceived: number;
  consecutiveErrors: number;
  lastError: string | null;
  sourceTimestampMissing: boolean;
  collectorHeartbeat: number | null;
  lastAttempt: number | null;
  lastSuccess: number | null;
  sourceTimestamp: number | null;
  dbWrittenAt: number | null;
  uiFetchedAt: number | null;
  lastChangeAt: number | null;
  attempts: number;
  successes: number;
  rowsParsed: number;
  rowsWritten: number;
  newAddresses: number;
  eventsWritten: number;
  runState: string | null;
  requestOk: boolean;
}

const STATUS_RANK: Record<MarketStatus, number> = {
  LIVE: 0,
  healthy: 0,
  unsupported: 0,
  DELAYED: 1,
  rate_limited: 2,
  cooldown: 2,
  STALE: 3,
  zero_write: 4,
  FAILED: 5,
  failed: 5,
};

export function worseStatus(a: MarketStatus, b: MarketStatus): MarketStatus {
  return STATUS_RANK[a] >= STATUS_RANK[b] ? a : b;
}

export function catalog(): { source: string; chain: string; periodSec: number }[] {
  const rows: { source: string; chain: string; periodSec: number }[] = [];
  for (const chain of CHAINS) {
    for (const source of ["gmgn", "gmgn_hot", "gmgn_new_pair", "gmgn_signal", "gmgn_kline", "gmgn_security", "dexscreener"]) {
      rows.push({ source, chain, periodSec: SOURCE_PERIOD[source] });
    }
  }
  rows.push({ source: "robinhood_anchor", chain: "robinhood", periodSec: 15 });
  rows.push({ source: "chainlink", chain: "robinhood", periodSec: 30 });
  return rows;
}

export function classifyStatus(
  now: number,
  lastSuccess: number | null,
  consecutiveErrors: number,
  hasDisplayRows: boolean,
  periodSec: number,
  roundOk: boolean,
  runState: string | null = null,
): MarketStatus {
  if (
    runState === "unsupported" ||
    runState === "cooldown" ||
    runState === "rate_limited" ||
    runState === "zero_write" ||
    runState === "failed"
  ) {
    return runState;
  }
  const period = periodSec || 60;
  if ((consecutiveErrors || 0) >= FAIL_THRESHOLD && !hasDisplayRows) return "FAILED";
  if (!lastSuccess) return "STALE";
  if (!roundOk) return "STALE";
  const apiAge = now - lastSuccess;
  if (apiAge > 2 * period) return "STALE";
  if (apiAge > period) return "DELAYED";
  return "LIVE";
}

export function fieldAgeSec(
  now: number,
  lastSuccess: number | null,
  sourceTimestamp: number | null,
  sourceTimestampMissing: boolean,
): number | null {
  const ages: number[] = [];
  if (lastSuccess) ages.push(now - lastSuccess);
  if (sourceTimestamp && !sourceTimestampMissing) ages.push(now - sourceTimestamp);
  if (!ages.length) return null;
  return Math.max(...ages);
}

export function tokenIsStale(
  ageSec: number | null,
  periodSec: number,
  halt = false,
  marketClosed = false,
): boolean {
  if (halt || marketClosed) return false;
  if (ageSec == null) return true;
  return ageSec > 2 * periodSec;
}

function num(v: string | number | null | undefined): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** 展示用。没有 currentMultiplier 就不把原始买卖价当成代币价。 */
export function adjustedAnchor(
  bid: string | number | null | undefined,
  ask: string | number | null | undefined,
  multiplier: string | number | null | undefined,
): number | null {
  const m = num(multiplier);
  if (m == null) return null;
  const b = num(bid);
  const a = num(ask);
  const mid = b != null && a != null ? (b + a) / 2 : b ?? a;
  if (mid == null) return null;
  return mid * m;
}

export function divergeFlag(
  gmgnPrice: string | number | null | undefined,
  dsPrice: string | number | null | undefined,
  ratio = DIVERGE_RATIO,
): boolean {
  const g = num(gmgnPrice);
  const d = num(dsPrice);
  if (g == null || d == null || g <= 0 || d <= 0) return false;
  return Math.abs(d - g) / g > ratio;
}

export function deviationRatio(adjusted: number | null, dex: number | null): number | null {
  if (adjusted == null || dex == null || dex <= 0) return null;
  return (adjusted - dex) / dex;
}

export function fmtAge(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec)) return "—";
  const s = Math.max(0, Math.floor(sec));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m${s % 60 ? `${s % 60}s` : ""}`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h${m ? `${m}m` : ""}`;
}

export type LabVerdict = "watch" | "pass" | "fail" | "short";

/** 2 分钟观察窗。价格没跳不算失败；冷源周期长于窗口时单独标出来。 */
export function labVerdict(input: {
  periodSec: number;
  successDelta: number;
  apiAgeSec: number | null;
  windowDone: boolean;
}): { state: LabVerdict; text: string } {
  if (!input.windowDone) return { state: "watch", text: "观察中" };
  if (input.periodSec > 120) {
    if (input.apiAgeSec != null && input.apiAgeSec > 2 * input.periodSec) {
      return { state: "fail", text: "超过 2 倍周期" };
    }
    return { state: "short", text: "观察窗短于周期" };
  }
  const ageOk = input.apiAgeSec != null && input.apiAgeSec <= input.periodSec;
  if (input.periodSec <= 30) {
    const need = Math.floor(90 / input.periodSec);
    if (input.successDelta >= need && ageOk) return { state: "pass", text: "通过" };
    if (!ageOk) return { state: "fail", text: "api_age 超出周期" };
    return { state: "fail", text: `成功次数 +${input.successDelta}，需要 +${need}` };
  }
  if (input.successDelta >= 1 && ageOk) return { state: "pass", text: "通过" };
  if (!ageOk) return { state: "fail", text: "api_age 超出周期" };
  return { state: "fail", text: "窗口内没有新的成功" };
}
