export type MarketAccessKind =
  | "BINANCE_WALLET_ASSET"
  | "BINANCE_WALLET_CONTRACT"
  | "BINANCE_WALLET_TRADABLE"
  | "BINANCE_ALPHA"
  | "BINANCE_ALPHA_LIVE"
  | "BINANCE_FUTURES"
  | "BINANCE_SPOT"
  | "BINANCE_PRE_MARKET"
  | "COINBASE_ROADMAP"
  | "COINBASE_SPOT"
  | "UPBIT_BTC"
  | "UPBIT_USDT"
  | "UPBIT_KRW"
  | "ROBINHOOD"
  | "OTHER";

export interface MarketAccessEvent {
  id: string;
  kind: MarketAccessKind;
  venue: string;
  label: string;
  symbol?: string;
  chain?: string;
  address?: string;
  detectedAt?: number;
  receivedAt?: number;
  isScheduled?: boolean;
  sourceUrl?: string;
}

export type AccessCategory =
  | "all"
  | "wallet"
  | "alpha"
  | "alpha-live"
  | "futures"
  | "spot"
  | "pre-market"
  | "roadmap"
  | "robinhood"
  | "upbit"
  | "coinbase";

const WALLET_KINDS = new Set<MarketAccessKind>([
  "BINANCE_WALLET_ASSET",
  "BINANCE_WALLET_CONTRACT",
  "BINANCE_WALLET_TRADABLE",
]);

const UPBIT_KINDS = new Set<MarketAccessKind>([
  "UPBIT_BTC",
  "UPBIT_USDT",
  "UPBIT_KRW",
]);

const COINBASE_KINDS = new Set<MarketAccessKind>([
  "COINBASE_ROADMAP",
  "COINBASE_SPOT",
]);

/** 最近的已知事件排在前面；没有 detectedAt 的事件稳定地排在最后。 */
export function sortAccessEvents(
  events: readonly MarketAccessEvent[] | null | undefined,
): MarketAccessEvent[] {
  return [...(events ?? [])]
    .map((event, index) => ({ event, index }))
    .sort((a, b) => {
      const aHasTime = Number.isFinite(a.event.detectedAt);
      const bHasTime = Number.isFinite(b.event.detectedAt);
      if (aHasTime !== bHasTime) return aHasTime ? -1 : 1;
      if (!aHasTime || !bHasTime) return a.index - b.index;
      const delta = (b.event.detectedAt as number) - (a.event.detectedAt as number);
      return delta || a.index - b.index;
    })
    .map(({ event }) => event);
}

export function getLatestAccessEvent(
  events: readonly MarketAccessEvent[] | null | undefined,
): MarketAccessEvent | undefined {
  return sortAccessEvents(events)[0];
}

/** 表格与最近状态卡片使用的紧凑、客观标签。 */
export function marketAccessLabel(kind: MarketAccessKind): string {
  if (WALLET_KINDS.has(kind)) return "Binance Wallet";
  if (kind === "BINANCE_ALPHA") return "Alpha";
  if (kind === "BINANCE_ALPHA_LIVE") return "Alpha Live";
  if (kind === "BINANCE_FUTURES") return "Binance Futures";
  if (kind === "BINANCE_SPOT") return "Binance Spot";
  if (kind === "BINANCE_PRE_MARKET") return "Binance Pre-market";
  if (kind === "COINBASE_ROADMAP") return "Coinbase · Roadmap";
  if (kind === "COINBASE_SPOT") return "Coinbase · Spot";
  if (kind === "UPBIT_BTC") return "Upbit · BTC";
  if (kind === "UPBIT_USDT") return "Upbit · USDT";
  if (kind === "UPBIT_KRW") return "Upbit · KRW";
  if (kind === "ROBINHOOD") return "Robinhood";
  return "Other";
}

/** 颜色只区分场所 / 产品，不表达利好、强弱或评分。 */
export function marketAccessTone(kind: MarketAccessKind): string {
  if (kind === "BINANCE_ALPHA_LIVE") return "border-brass/35 bg-brass/10 text-brass";
  if (kind === "BINANCE_ALPHA" || WALLET_KINDS.has(kind)) return "border-line bg-surface-2 text-fg";
  return "border-line bg-surface text-muted";
}

/** 单个事件的主分类。Roadmap 保留独立入口；Coinbase 汇总筛选由 matchesAccessCategory 处理。 */
export function getAccessCategory(event: MarketAccessEvent): AccessCategory {
  if (WALLET_KINDS.has(event.kind)) return "wallet";
  if (event.kind === "BINANCE_ALPHA") return "alpha";
  if (event.kind === "BINANCE_ALPHA_LIVE") return "alpha-live";
  if (event.kind === "BINANCE_FUTURES") return "futures";
  if (event.kind === "BINANCE_SPOT") return "spot";
  if (event.kind === "BINANCE_PRE_MARKET") return "pre-market";
  if (event.kind === "COINBASE_ROADMAP") return "roadmap";
  if (event.kind === "COINBASE_SPOT") return "coinbase";
  if (UPBIT_KINDS.has(event.kind)) return "upbit";
  if (event.kind === "ROBINHOOD") return "robinhood";
  return "all";
}

export function matchesAccessCategory(
  event: MarketAccessEvent,
  category: AccessCategory,
): boolean {
  if (category === "all") return true;
  if (category === "coinbase") return COINBASE_KINDS.has(event.kind);
  return getAccessCategory(event) === category;
}

export function isSafeSourceUrl(url: string | null | undefined): boolean {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function isSurpriseAccessEvent(event: MarketAccessEvent): boolean {
  return event.kind === "BINANCE_ALPHA_LIVE" && event.isScheduled === false;
}

export function isScheduledAccessEvent(event: MarketAccessEvent): boolean {
  return event.kind === "BINANCE_ALPHA_LIVE" && event.isScheduled === true;
}

interface DemoToken {
  chain: string;
  address: string;
  marketAccess?: MarketAccessEvent[];
}

interface DemoTemplate {
  preferredKey: string;
  makeEvents: (now: number) => MarketAccessEvent[];
}

function demoEvent(
  id: string,
  kind: MarketAccessKind,
  venue: string,
  label: string,
  detectedAt: number,
  receivedDelay: number,
  extra: Pick<MarketAccessEvent, "isScheduled" | "sourceUrl"> = {},
): MarketAccessEvent {
  return {
    id,
    kind,
    venue,
    label,
    detectedAt,
    receivedAt: detectedAt + receivedDelay,
    ...extra,
  };
}

const DEMO_TEMPLATES: DemoTemplate[] = [
  {
    preferredKey: "eth:0x49ccb3eebff3040f7063a360575ab65e346f4a6c",
    makeEvents: (now) => [
      demoEvent("demo-pons-wallet-asset", "BINANCE_WALLET_ASSET", "Binance Wallet", "Asset", now - 259_200, 18),
      demoEvent("demo-pons-wallet-contract", "BINANCE_WALLET_CONTRACT", "Binance Wallet", "Contract", now - 172_800, 23),
      demoEvent("demo-pons-alpha", "BINANCE_ALPHA", "Binance", "Alpha", now - 86_400, 12),
      demoEvent(
        "demo-pons-alpha-live",
        "BINANCE_ALPHA_LIVE",
        "Binance",
        "Alpha Live",
        now - 720,
        14,
        { isScheduled: false, sourceUrl: "https://www.binance.com/en/support/announcement" },
      ),
    ],
  },
  {
    preferredKey: "sol:CVwTfrKpe3DtGkDTbCLQMtveMEEDVWjZbMSSCRUH8izW",
    makeEvents: (now) => [
      demoEvent("demo-orbio-wallet-tradable", "BINANCE_WALLET_TRADABLE", "Binance Wallet", "Tradable", now - 1_680, 9),
    ],
  },
  {
    preferredKey: "sol:78UzvBJaFvUAiSsWsiynH2aYqTchcDAvkKw81fHzpump",
    makeEvents: (now) => [
      demoEvent("demo-xyz-upbit-krw", "UPBIT_KRW", "Upbit", "KRW", now - 2_760, 21),
    ],
  },
  {
    preferredKey: "base:0x6e252dfa99884c6f613f31387798b55ed95150f6",
    makeEvents: (now) => [
      demoEvent("demo-ct-futures", "BINANCE_FUTURES", "Binance", "Futures", now - 4_200, 17, { isScheduled: true }),
    ],
  },
  {
    preferredKey: "robinhood:0x3f0e0131f7384d6811204937e36cb61ba305ffbd",
    makeEvents: (now) => [
      demoEvent("demo-node-coinbase-roadmap", "COINBASE_ROADMAP", "Coinbase", "Roadmap", now - 7_200, 31),
    ],
  },
];

/**
 * DEV 查询参数专用 fixture。模板只绑定明确指定的 chain + address；当前数据不含该 token 时不显示，
 * 不找其他 token 顶替，绝不按 symbol 猜身份。
 */
export function applyMarketAccessDemo<T extends DemoToken>(tokens: readonly T[], now: number): T[] {
  const eventsByKey = new Map<string, MarketAccessEvent[]>();
  for (const template of DEMO_TEMPLATES) {
    eventsByKey.set(template.preferredKey, template.makeEvents(now));
  }

  return tokens.map((token) => {
    const fixture = eventsByKey.get(`${token.chain}:${token.address}`);
    if (!fixture) return token;
    return { ...token, marketAccess: [...(token.marketAccess ?? []), ...fixture] };
  });
}
