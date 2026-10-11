import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useServerFn } from "@tanstack/react-start";
import { RefreshCw, Search, ArrowUp, ArrowDown, Star, Copy, Check, X } from "lucide-react";
import { fetchMarketHot, fetchMarketRank, type GmgnClock, type HotToken, type MarketEligibility } from "@/lib/rh/market-server";
import type { MarketInclusionStats, MarketTierStats } from "@/lib/rh/market-stats";
import {
  GMGN_PRICE_PERIOD,
  SOURCE_PERIOD,
  adjustedAnchor,
  fieldAgeSec,
  fmtAge,
  tokenIsStale,
} from "@/lib/rh/market-status";
import {
  DEFAULT_DAYS,
  LIQUIDITY_FRESHNESS_SEC,
  STREAK_MIN_LIQUIDITY,
  anchorDeviation,
  compareStreakThenReturn,
  fmtRelativeAge,
  formalStreakEligible,
  isPositiveStreak,
  klineIsStale,
  shouldCommitRankWrite,
  type DailyStatus,
  type QualityFlag,
  type StreakStatus,
} from "@/lib/rh/streak";
import { MarketHealthBar } from "@/components/market-health-bar";
import { WmUnifiedMarket } from "@/components/wm-unified-market";
import { WmQualityBar } from "@/components/wm-quality-bar";
import { MarketAccessDrawer, type MarketAccessDrawerDetail } from "@/components/market-access-drawer";
import { TokenDetailDrawer } from "@/components/token-detail";
import {
  compareDailyReturn,
  cycleDailyFilter,
  dateTOffset,
  finalizedDateWindow,
  nextPrimarySort,
  type DailyPrimarySort,
  fmtTOffset,
  formatCompactUsd,
  formatDailyReturn,
  matchesDailyFilters,
  reconcileDailyFilters,
  type DailyHistoryEntry,
  type DailyReturnFilters,
  type DailyReturnMap,
} from "@/lib/rh/daily-filter";
import {
  WATCH_EVENT,
  loadWatchlist,
  toggleWatchItem,
  watchKey,
  writeWatchlist,
  type WatchItem,
} from "@/lib/rh/watchlist";
import { MARKET_CHAIN_LABEL, MARKET_CHAIN_TABS } from "@/lib/rh/market-chains";
import { compareNewness, mergeSearchHits } from "@/lib/rh/market-browse";
import {
  HIDDEN_TOKENS_EVENT,
  addHiddenToken,
  hiddenTokenKey,
  loadHiddenTokens,
  removeHiddenToken,
  writeHiddenTokens,
} from "@/lib/rh/hidden-tokens";
import {
  applyMarketAccessDemo,
  getLatestAccessEvent,
  isScheduledAccessEvent,
  isSurpriseAccessEvent,
  marketAccessLabel,
  marketAccessTone,
  matchesAccessCategory,
  type AccessCategory,
  type MarketAccessEvent,
} from "@/lib/rh/market-access";

interface RankedToken {
  chain: string;
  address: string;
  symbol: string | null;
  name: string | null;
  logo: string | null;
  price: string;
  pc24h: string | null;
  pc24hSource?: string | null;
  pcInterval?: string | null;
  pc1h?: string | null;
  buys24h?: number | null;
  sells24h?: number | null;
  swaps24h?: number | null;
  trendingRank?: number | null;
  trendingRankAt?: number | null;
  trendingRankContext?: string | null;
  hotRank?: number | null;
  hotRankContext?: string | null;
  volume24h: string;
  liquidity: string;
  marketCap: string;
  holders: number | null;
  priceSource: string | null;
  priceUpdatedAt: number | null;
  volume24hSource: string | null;
  volume24hUpdatedAt: number | null;
  liquiditySource: string | null;
  marketCapSource: string | null;
  marketCapUpdatedAt: number | null;
  holdersSource: string | null;
  holdersUpdatedAt: number | null;
  securityUpdatedAt: number | null;
  securityIsHoneypot: boolean | null;
  securityIsBlacklist: boolean | null;
  securityIsOpenSource: boolean | null;
  securityIsRenounced: boolean | null;
  securityTop10HolderRate: string | null;
  changeNd: number | null;
  change1d: number | null;
  dailyReturns: DailyReturnMap;
  /** 统一 7 日窗口每格：收益 + USD 成交量，同一根 FINALIZED 日K。只展示，不参与排序 / 筛选。 */
  dailyHistory?: DailyHistoryEntry[];
  /** 全市场新币优先排序键：系统首次看到的时间，缺失才退回 creation。 */
  newnessAt?: number | null;
  /** 改版前的榜单候选集合；连涨榜只在其中筛，全市场扩容不改连涨榜。 */
  streakPool?: boolean;
  streak: number | null;
  streakStatus?: StreakStatus;
  streakReturn: number | null;
  streakDrawdown: number | null;
  closedCandles: number;
  lastDailyStatus: DailyStatus | null;
  qualityFlags: QualityFlag[];
  createdAt: number | null;
  createdSource: "token" | "pair" | null;
  tokenCreatedAt: number | null;
  pairCreatedAt: number | null;
  firstSeenAt: number | null;
  klineFetchedAt: number | null;
  priceDs: string | null;
  volumeDs: string | null;
  liquidityDs: string | null;
  dexPrice: string | null;
  diverge: number;
  anchorBid: string | null;
  anchorAsk: string | null;
  anchorGeneratedAt: number | null;
  anchorMultiplier: string | null;
  halt: boolean;
  marketClosed: boolean;
  oraclePrice: string | null;
  oracleUpdatedAt: number | null;
  commitOk: boolean;
  chgPrice: boolean;
  chgVolume: boolean;
  chgLiquidity: boolean;
  liquidityNum: number | null;
  liquidityUpdatedAt: number | null;
  observationType: string | null;
  qualifiedAt: number | null;
  return2d: number | null;
  return3d: number | null;
  return5d: number | null;
  marketAccess?: MarketAccessEvent[];
}

interface ViewToken extends RankedToken {
  ageSec: number | null;
  liquidityAgeSec: number | null;
  volumeAgeSec: number | null;
  marketCapAgeSec: number | null;
  holdersAgeSec: number | null;
  stale: boolean;
  klineStale: boolean;
  liqStale: boolean;
}

const CHAIN_BADGE: Record<string, string> = {
  sol: "bg-chain-sol", robinhood: "bg-chain-robinhood", base: "bg-chain-base", eth: "bg-chain-eth", bsc: "bg-chain-bsc",
};
const HEAVY_MS = 60_000;
const HOT_MS = 8_000;
const REORDER_MS = 20_000;

function fmtPrice(v: string | number | null | undefined): string {
  const n = Number(v);
  if (!isFinite(n) || n === 0) return "–";
  if (n >= 1) return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
  if (n >= 0.0001) return n.toPrecision(4);
  return n.toExponential(2);
}
function fmtUsd(v: string): string {
  const n = Number(v);
  if (!isFinite(n) || n === 0) return "–";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}
/** "" / null / 非数字 → null；"0" → 0。不用 `x || 0` 吞掉真实 0。 */
function numOrNull(v: string | number | null | undefined): number | null {
  if (v == null) return null;
  if (typeof v === "string" && v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
function fmtPct(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  const pct = v * 100;
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${Math.abs(pct).toFixed(1)}%`;
}
function pctColor(v: number | null | undefined): string {
  if (v == null) return "text-muted";
  if (v > 0) return "text-positive";
  if (v < 0) return "text-negative";
  return "text-muted";
}

function fmtLocal(ts: number): string {
  const d = new Date(ts * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function CopyAddress({ address }: { address: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <span className="inline-flex max-w-full items-center gap-1 font-mono text-[10px] leading-tight text-muted">
      <span className="truncate" title={address}>{compactCa(address)}</span>
      <button
        type="button"
        aria-label="复制完整 CA"
        title={copied ? "已复制" : `复制 ${address}`}
        onClick={() => {
          void navigator.clipboard.writeText(address).then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          });
        }}
        className="shrink-0 rounded p-0.5 hover:text-fg"
      >
        {copied ? <Check className="h-3 w-3 text-positive" /> : <Copy className="h-3 w-3" />}
      </button>
    </span>
  );
}

function eligibilityTitle(e: MarketEligibility | null, days: number): string {
  if (!e) return `具备完整 ${days}D 涨跌 = ${days} 个涨跌日，需 ${days + 1} 根连续 FINALIZED 日K。流动性门槛只约束正式连涨榜。`;
  return [
    `名册 ${e.registry} 个`,
    `具备完整 ${e.days}D 涨跌（${e.days} 个涨跌日，需 ${e.days + 1} 根连续 finalized 日K）${e.enoughCandleHistory} 个`,
    `其中流动性≥$${STREAK_MIN_LIQUIDITY.toLocaleString()} ${e.liquidityQualified} 个`,
    `其中流动性新鲜(≤${LIQUIDITY_FRESHNESS_SEC}s) ${e.freshQualified} 个`,
    `全市场${e.days}日榜按完整 finalized 日K，共 ${e.finalEligible} 个`,
    `正式连涨榜另要求流动性≥$${STREAK_MIN_LIQUIDITY.toLocaleString()} 且年龄≤${LIQUIDITY_FRESHNESS_SEC}秒`,
  ].join(" · ");
}

function AnchorTag({ t, now }: { t: ViewToken; now: number }) {
  const hasAnchor = t.anchorBid != null || t.anchorAsk != null || t.anchorGeneratedAt != null;
  if (!hasAnchor) return null;
  const age = t.anchorGeneratedAt == null ? null : now - t.anchorGeneratedAt;
  const stale = age == null || age > 2 * SOURCE_PERIOD.robinhood_anchor;
  if (stale) return null;
  const anchor = adjustedAnchor(t.anchorBid, t.anchorAsk, t.anchorMultiplier);
  const pool = Number(t.dexPrice);
  const dev = anchorDeviation(Number.isFinite(pool) ? pool : null, anchor);
  if (dev == null) return null;
  return (
    <span className={`font-mono text-[10px] ${pctColor(dev)}`} title="pool / anchor − 1。不参与连涨排序、累计涨幅或连涨天数">
      Anchor {fmtPct(dev)}
    </span>
  );
}

function TokenCell({
  t,
  now,
  showAnchor,
  onOpen,
  onOpenAccess,
}: {
  t: ViewToken;
  now: number;
  showAnchor: boolean;
  onOpen: () => void;
  onOpenAccess: () => void;
}) {
  const [logoOk, setLogoOk] = useState(true);
  const flags = t.qualityFlags ?? [];
  const accessEvents = t.marketAccess ?? [];
  const latestAccess = getLatestAccessEvent(accessEvents);
  const securityRisk = t.securityIsHoneypot === true || t.securityIsBlacklist === true;
  const createdTitle = t.createdAt == null
    ? "没有代币创建时间，也没有池子创建时间"
    : `${t.createdSource === "pair" ? "池子创建" : "代币创建"} ${fmtLocal(t.createdAt)}`;
  const securityTitle = t.securityUpdatedAt == null ? null : [
    `Security source GMGN · ${fmtAge(now - t.securityUpdatedAt)} 前`,
    `honeypot=${String(t.securityIsHoneypot)}`,
    `blacklist=${String(t.securityIsBlacklist)}`,
    `open_source=${String(t.securityIsOpenSource)}`,
    `renounced=${String(t.securityIsRenounced)}`,
    `top10=${t.securityTop10HolderRate ?? "null"}`,
  ].join(" · ");
  return (
    <div className="flex items-center gap-1.5">
      <button type="button" onClick={onOpen} title="打开详情" className="relative h-7 w-7 shrink-0">
        {t.logo && logoOk ? (
          <img src={t.logo} alt="" className="h-7 w-7 rounded-full bg-surface-2 object-cover" loading="lazy" onError={() => setLogoOk(false)} />
        ) : (
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-surface-2 font-mono text-xs text-muted">
            {(t.symbol || "?").slice(0, 2)}
          </span>
        )}
        <span className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border border-bg ${CHAIN_BADGE[t.chain] || "bg-muted"}`} title={t.chain} />
      </button>
      <div className="w-28 min-w-0">
        <div className="flex min-w-0 items-baseline gap-1.5">
          <button type="button" onClick={onOpen} title={`${t.symbol || "?"} ${t.name || ""} · 打开详情`} className="min-w-0 truncate text-left text-sm font-medium leading-tight hover:underline">
            {t.symbol || "?"}
          </button>
          {latestAccess ? (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onOpenAccess();
              }}
              title={`${marketAccessLabel(latestAccess.kind)} · 查看全部市场准入记录`}
              aria-label={`查看 ${t.symbol || "Token"} 的市场准入状态`}
              className={`inline-flex h-5 max-w-20 shrink-0 items-center truncate rounded-full border px-1.5 font-mono text-[10px] leading-none ${marketAccessTone(latestAccess.kind)}`}
            >
              {marketAccessLabel(latestAccess.kind)}
            </button>
          ) : (
            <span className="shrink-0 font-mono text-[10px] text-muted" title={createdTitle}>
              {t.createdAt == null ? "—" : fmtRelativeAge(now, t.createdAt)}
            </span>
          )}
        </div>
        <div className="flex min-w-0 items-center justify-between gap-1">
          <CopyAddress address={t.address} />
          {latestAccess ? (
            <span className="shrink-0 font-mono text-[10px] text-muted" title={createdTitle}>
              {t.createdAt == null ? "—" : fmtRelativeAge(now, t.createdAt)}
            </span>
          ) : null}
        </div>
        {flags.length > 0 ? (
          <p className="truncate font-mono text-[10px] text-primary leading-tight">{flags.join(" · ")}</p>
        ) : null}
        {securityTitle ? (
          <p className={`truncate font-mono text-[10px] leading-tight ${securityRisk ? "text-negative" : "text-muted"}`} title={securityTitle}>
            {securityRisk ? "SECURITY RISK" : "Security checked"}
          </p>
        ) : null}
        {showAnchor ? <AnchorTag t={t} now={now} /> : null}
      </div>
    </div>
  );
}

function compactCa(address: string): string {
  if (address.length <= 10) return address;
  return `${address.slice(0, 4)}…${address.slice(-4)}`;
}

function FlashCell({
  value,
  armed,
  className,
  children,
}: {
  value: string;
  armed: boolean;
  className?: string;
  children: ReactNode;
}) {
  const prev = useRef<string | null>(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (prev.current != null && prev.current !== value && armed) {
      setOn(true);
      const t = window.setTimeout(() => setOn(false), 800);
      prev.current = value;
      return () => window.clearTimeout(t);
    }
    prev.current = value;
  }, [value, armed]);
  return <td className={(className || "") + (on ? " cell-flash" : "")}>{children}</td>;
}

type SortKey = "changeNd" | "streak" | "volume24h" | "liquidity" | "marketCap" | "price" | "holders" | "streakReturn" | "streakDrawdown" | "buys24h" | "sells24h" | "swaps24h" | "trendingRank";
type SortMode = SortKey | "added" | "newness";
type Board = "all" | "streak" | "watch";

const ACCESS_CATEGORY_OPTIONS: { value: AccessCategory; label: string }[] = [
  { value: "all", label: "全部状态" },
  { value: "wallet", label: "Binance Wallet" },
  { value: "alpha", label: "Alpha" },
  { value: "alpha-live", label: "Alpha Live" },
  { value: "futures", label: "Futures" },
  { value: "spot", label: "Spot" },
  { value: "pre-market", label: "Pre-market" },
  { value: "roadmap", label: "Roadmap" },
  { value: "robinhood", label: "Robinhood" },
  { value: "upbit", label: "Upbit" },
  { value: "coinbase", label: "Coinbase" },
];

function dateLabel(date: string): string {
  return date.slice(5).replace("-", "/");
}

function StarButton({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={on ? "移出自选" : "加入自选"}
      title={on ? "移出自选" : "加入自选"}
      onClick={(e) => {
        // 星标只切自选，不冒泡到行 / 详情 / 排序
        e.preventDefault();
        e.stopPropagation();
        onClick();
      }}
      className="inline-flex size-8 shrink-0 items-center justify-center rounded-full hover:bg-surface-2"
    >
      <Star className={"size-4 " + (on ? "fill-primary text-primary" : "text-muted")} />
    </button>
  );
}

function HideTokenButton({ symbol, onClick }: { symbol: string | null; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={`隐藏 ${symbol || "Token"}`}
      title={`隐藏 ${symbol || "Token"}`}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onClick();
      }}
      className="inline-flex size-7 items-center justify-center rounded-full text-muted opacity-35 hover:bg-surface-2 hover:text-fg hover:opacity-100"
    >
      <X className="size-3.5" />
    </button>
  );
}

function HiddenTokensMenu({
  keys,
  tokens,
  onRestore,
  onRestoreAll,
}: {
  keys: readonly string[];
  tokens: readonly RankedToken[];
  onRestore: (key: string) => void;
  onRestoreAll: () => void;
}) {
  const tokenByKey = useMemo(
    () => new Map(tokens.map((token) => [hiddenTokenKey(token.chain, token.address), token])),
    [tokens],
  );
  if (keys.length === 0) return null;
  return (
    <details className="relative">
      <summary className="min-h-9 list-none rounded-full border border-line px-3 py-2 font-mono text-xs text-muted hover:text-fg">
        已隐藏 {keys.length}
      </summary>
      <div className="absolute right-0 z-30 mt-2 w-80 rounded-xl border border-line bg-bg p-3 shadow-xl">
        <div className="flex items-center justify-between gap-3 border-b border-line pb-2">
          <p className="text-sm font-medium">已隐藏 Token</p>
          <button type="button" onClick={onRestoreAll} className="min-h-8 rounded-full px-2 font-mono text-xs text-muted hover:bg-surface-2 hover:text-fg">
            全部恢复
          </button>
        </div>
        <ul className="max-h-80 overflow-y-auto py-1">
          {keys.map((key) => {
            const token = tokenByKey.get(key);
            return (
              <li key={key} className="flex items-center justify-between gap-3 border-b border-line/50 py-2 last:border-b-0">
                <div className="min-w-0">
                  <p className="truncate text-sm">{token?.symbol || "?"}</p>
                  <p className="truncate font-mono text-[10px] text-muted" title={key}>{key}</p>
                </div>
                <button
                  type="button"
                  onClick={() => onRestore(key)}
                  className="min-h-8 shrink-0 rounded-full border border-line px-2 font-mono text-xs text-muted hover:text-fg"
                >
                  恢复
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </details>
  );
}

function keyOf(t: { chain: string; address: string }) {
  return `${t.chain}:${t.address}`;
}

function fmtAccessAge(timestamp: number | undefined, now: number): string {
  if (timestamp == null || !Number.isFinite(timestamp)) return "时间未记录";
  const age = Math.max(0, now - timestamp);
  if (age < 60) return `${age}秒前`;
  if (age < 3_600) return `${Math.floor(age / 60)}分钟前`;
  if (age < 86_400) return `${Math.floor(age / 3_600)}小时前`;
  return `${Math.floor(age / 86_400)}天前`;
}

function applyHot(t: RankedToken, hot: HotToken | undefined): RankedToken {
  if (!hot) return t;
  return {
    ...t,
    price: hot.price,
    volume24h: hot.volume24h,
    liquidity: hot.liquidity,
    priceDs: hot.priceDs,
    volumeDs: hot.volumeDs,
    liquidityDs: hot.liquidityDs,
    dexPrice: hot.dexPrice,
    diverge: hot.diverge,
    anchorBid: hot.anchorBid,
    anchorAsk: hot.anchorAsk,
    anchorGeneratedAt: hot.anchorGeneratedAt,
    anchorMultiplier: hot.anchorMultiplier,
    halt: hot.halt,
    marketClosed: hot.marketClosed,
    oraclePrice: hot.oraclePrice,
    oracleUpdatedAt: hot.oracleUpdatedAt,
    commitOk: hot.commitOk,
    chgPrice: hot.chgPrice,
    chgVolume: hot.chgVolume,
    chgLiquidity: hot.chgLiquidity,
    liquidityNum: hot.liquidityNum,
    liquidityUpdatedAt: hot.liquidityUpdatedAt,
    priceSource: hot.priceSource,
    priceUpdatedAt: hot.priceUpdatedAt,
    volume24hSource: hot.volume24hSource,
    volume24hUpdatedAt: hot.volume24hUpdatedAt,
    liquiditySource: hot.liquiditySource,
  };
}

function decorate(t: RankedToken, clock: GmgnClock | undefined, now: number): ViewToken {
  const ageSec = t.priceUpdatedAt == null
    ? fieldAgeSec(now, clock?.lastSuccess ?? null, clock?.sourceTimestamp ?? null, clock?.sourceTimestampMissing ?? true)
    : now - t.priceUpdatedAt;
  const liquidityAgeSec = t.liquidityUpdatedAt == null ? null : now - t.liquidityUpdatedAt;
  const volumeAgeSec = t.volume24hUpdatedAt == null ? null : now - t.volume24hUpdatedAt;
  const marketCapAgeSec = t.marketCapUpdatedAt == null ? null : now - t.marketCapUpdatedAt;
  const holdersAgeSec = t.holdersUpdatedAt == null ? null : now - t.holdersUpdatedAt;
  const quoteStale = tokenIsStale(ageSec, GMGN_PRICE_PERIOD, t.halt, t.marketClosed);
  return {
    ...t,
    ageSec,
    liquidityAgeSec,
    volumeAgeSec,
    marketCapAgeSec,
    holdersAgeSec,
    stale: quoteStale,
    klineStale: klineIsStale(now, t.klineFetchedAt),
    liqStale: liquidityAgeSec == null || liquidityAgeSec > 2 * GMGN_PRICE_PERIOD,
    qualityFlags: t.qualityFlags ?? [],
    lastDailyStatus: t.lastDailyStatus ?? null,
  };
}

function LegacyMarketView({ watchOnly: watchProp = false }: { watchOnly?: boolean }) {
  // 周期按钮已删除：顶部 N 日窗口固定为默认值，日期筛选全靠日期列。
  const days = DEFAULT_DAYS;
  const [chain, setChain] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [searchHits, setSearchHits] = useState<{ q: string; tokens: RankedToken[] } | null>(null);
  const [data, setData] = useState<RankedToken[] | null>(null);
  const [dailyFilters, setDailyFilters] = useState<DailyReturnFilters>({});
  // 最后一次点击的日期列 = 唯一主排序键；其他已选日期只参与 AND 筛选
  const [primarySort, setPrimarySort] = useState<DailyPrimarySort | null>(null);
  const [hotMap, setHotMap] = useState<Map<string, HotToken>>(new Map());
  const [gmgn, setGmgn] = useState<Record<string, GmgnClock>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sortKey, setSortKey] = useState<SortMode>(watchProp ? "added" : "newness");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [board, setBoard] = useState<Board>(watchProp ? "watch" : "all");
  const [accessOnly, setAccessOnly] = useState(false);
  const [accessCategory, setAccessCategory] = useState<AccessCategory>("all");
  const watchOnly = watchProp || board === "watch";
  const [watch, setWatch] = useState<WatchItem[]>([]);
  const [hiddenKeys, setHiddenKeys] = useState<string[]>([]);
  const [heavyTick, setHeavyTick] = useState(0);
  const [orderTick, setOrderTick] = useState(0);
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));
  const [inclusionStats, setInclusionStats] = useState<MarketInclusionStats | null>(null);
  const [tierStats, setTierStats] = useState<MarketTierStats | null>(null);
  const [ndWindowEnd, setNdWindowEnd] = useState<string | null>(null);
  const [eligibility, setEligibility] = useState<MarketEligibility | null>(null);
  const [appliedDays, setAppliedDays] = useState<number | null>(null);
  const [detail, setDetail] = useState<{ chain: string; address: string } | null>(null);
  const [accessDetail, setAccessDetail] = useState<MarketAccessDrawerDetail | null>(null);
  const [activityMode, setActivityMode] = useState<"price" | "access">("price");
  const [demoEnabled, setDemoEnabled] = useState(false);
  const demoNow = useRef(Math.floor(Date.now() / 1000));

  const rankFn = useServerFn(fetchMarketRank);
  const hotFn = useServerFn(fetchMarketHot);
  const inflight = useRef<AbortController | null>(null);
  const rankSeq = useRef(0);
  const daysRef = useRef(days);
  const hotRef = useRef(hotMap);
  const gmgnRef = useRef(gmgn);
  const nowRef = useRef(now);
  daysRef.current = days;
  // 自选页只向后端要自选里的币；排行页由后端按榜单条件预筛。
  const watchKeysParam = watchOnly ? watch.map((w) => watchKey(w.chain, w.address)) : undefined;
  const keysRef = useRef(watchKeysParam);
  keysRef.current = watchKeysParam;
  hotRef.current = hotMap;
  gmgnRef.current = gmgn;
  nowRef.current = now;

  function selectBoard(next: Board) {
    // 自选和榜单走两套后端请求（自选不看榜单预筛），切换时先清空，避免拿另一套数据闪一下
    if ((next === "watch") !== (board === "watch")) setData(null);
    setBoard(next);
    setSortKey(next === "watch" ? "added" : next === "streak" ? "streak" : "newness");
    setSortDir("desc");
  }

  async function load(silent = false) {
    const requestDays = daysRef.current;
    const seq = ++rankSeq.current;
    inflight.current?.abort();
    const ctrl = new AbortController();
    inflight.current = ctrl;
    const live = (channel: "data" | "error" | "loading" | "eligibility") =>
      shouldCommitRankWrite(seq, rankSeq.current, requestDays, daysRef.current, channel) && !ctrl.signal.aborted;
    if (!silent && live("loading")) setLoading(true);
    if (live("error")) setError("");
    try {
      const res = await rankFn({ data: { days: requestDays, keys: keysRef.current } });
      if (!live("data")) return;
      if (!res.ok) {
        if (live("error")) setError(res.error || "拉取失败");
      } else {
        if (live("data")) setData(res.tokens);
        if (live("data")) {
          setInclusionStats(res.inclusionStats ?? null);
          setTierStats(res.tierStats ?? null);
          setNdWindowEnd(res.ndWindowEnd ?? null);
        }
        if (live("data")) setAppliedDays(res.days ?? requestDays);
        if (live("eligibility") && res.eligibility) setEligibility(res.eligibility);
        if (live("data") && res.gmgn) setGmgn(res.gmgn);
        const ranked = [...res.tokens]
          .filter((t) => t.changeNd != null && isFinite(t.changeNd))
          .sort((a, b) => (b.changeNd ?? -Infinity) - (a.changeNd ?? -Infinity));
        console.debug("[market-rank]", {
          selectedDays: daysRef.current,
          requestDays,
          backendDays: res.days,
          calculationDays: res.days,
          applied: live("data"),
          rows: res.tokens.length,
          eligibility: res.eligibility,
          top5: ranked.slice(0, 5).map((t) => ({
            symbol: t.symbol,
            address: t.address,
            changeNd: t.changeNd,
            streak: t.streak,
          })),
        });
      }
    } catch (e) {
      if (live("error")) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (live("loading")) setLoading(false);
    }
  }

  async function loadHot() {
    try {
      const res = await hotFn({ data: { keys: keysRef.current } });
      if (!res.ok) return;
      setHotMap(new Map(res.tokens.map((t) => [keyOf(t), t])));
      setGmgn(res.gmgn);
    } catch {
      /* 热列失败时沿用上一拍，不把榜单清空 */
    }
  }

  useEffect(() => {
    const sync = () => setWatch(loadWatchlist(window.localStorage));
    sync();
    window.addEventListener("storage", sync);
    window.addEventListener(WATCH_EVENT, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(WATCH_EVENT, sync);
    };
  }, []);
  useEffect(() => {
    const sync = () => setHiddenKeys(loadHiddenTokens(window.localStorage));
    sync();
    window.addEventListener("storage", sync);
    window.addEventListener(HIDDEN_TOKENS_EVENT, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(HIDDEN_TOKENS_EVENT, sync);
    };
  }, []);
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const params = new URLSearchParams(window.location.search);
    setDemoEnabled(params.get("marketAccessDemo") === "1");
  }, []);

  function onStar(t: { chain: string; address: string; symbol: string | null; name: string | null }) {
    const current = loadWatchlist(window.localStorage);
    const next = toggleWatchItem(current, t, Math.floor(Date.now() / 1000));
    writeWatchlist(window.localStorage, next);
    setWatch(next);
    window.dispatchEvent(new Event(WATCH_EVENT));
  }

  function persistHidden(next: string[]) {
    writeHiddenTokens(window.localStorage, next);
    setHiddenKeys(next);
    window.dispatchEvent(new Event(HIDDEN_TOKENS_EVENT));
  }

  function hideToken(t: { chain: string; address: string }) {
    persistHidden(addHiddenToken(loadHiddenTokens(window.localStorage), t.chain, t.address));
  }

  function restoreHidden(key: string) {
    persistHidden(removeHiddenToken(loadHiddenTokens(window.localStorage), key));
  }

  function openTokenDetail(t: { chain: string; address: string }) {
    setAccessDetail(null);
    setDetail({ chain: t.chain, address: t.address });
  }

  function openAccessDetail(t: RankedToken) {
    setDetail(null);
    setAccessDetail({
      chain: t.chain,
      address: t.address,
      symbol: t.symbol,
      events: t.marketAccess ?? [],
    });
  }

  const watchSig = watchOnly ? (watchKeysParam ?? []).join(",") : "";
  useEffect(() => {
    // 自选为空不用问后端；挂载时 watch 还没读出来，读到后 watchSig 变了会再拉
    if (watchOnly && watch.length === 0) { setData([]); return; }
    load();
    if (watchOnly) loadHot();
  }, [days, watchOnly, watchSig]);
  useEffect(() => {
    const t = setInterval(() => setHeavyTick((x) => x + 1), HEAVY_MS);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (heavyTick === 0) return;
    load(true);
  }, [heavyTick]);
  useEffect(() => {
    loadHot();
    const t = setInterval(loadHot, HOT_MS);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const t = setInterval(() => setOrderTick((x) => x + 1), REORDER_MS);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const t = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const onVis = () => { if (document.visibilityState === "visible") setHeavyTick((x) => x + 1); };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  // 搜索查全库：默认浏览集合之外的命中由服务端返回，临时并进当前结果。
  useEffect(() => {
    const q = search.trim().toLowerCase();
    if (watchOnly || q.length < 2) {
      setSearchHits(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const res = await rankFn({ data: { days: daysRef.current, search: q } });
        if (!cancelled && res.ok) setSearchHits({ q, tokens: res.tokens });
      } catch {
        // 全库搜索失败时退回只搜当前已下发的列表
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [search, watchOnly]);

  // 日期表头只认 API 的全市场统一 ndWindowEnd。缺失时不使用浏览器日期猜测 T。
  const dailyDates = useMemo(() => finalizedDateWindow(ndWindowEnd), [ndWindowEnd]);
  const latestFinalizedDate = dailyDates[dailyDates.length - 1] ?? null;
  const dailyDateSignature = dailyDates.join(",");
  useEffect(() => {
    setDailyFilters((current) => reconcileDailyFilters(current, dailyDates));
    setPrimarySort((current) => (current && dailyDates.includes(current.date) ? current : null));
  }, [dailyDateSignature]);

  function clickDailyDate(date: string) {
    const next = cycleDailyFilter(dailyFilters, date);
    setDailyFilters(next);
    const nextSort = nextPrimarySort(primarySort, date, next[date]);
    setPrimarySort(nextSort);
    // 全市场取消日期排序 = 回到新币优先
    if (primarySort && !nextSort && board === "all" && !watchOnly) {
      setSortKey("newness");
      setSortDir("desc");
    }
  }

  // 默认视口停在最右：统一 T 可见。只在日期轮换 / 换榜 / 首次出数时归位，不打断用户手动滚动。
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const hasData = data != null;
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [dailyDateSignature, board, hasData]);

  const watchKeys = useMemo(() => new Set(watch.map((w) => watchKey(w.chain, w.address))), [watch]);
  const hiddenKeySet = useMemo(() => new Set(hiddenKeys), [hiddenKeys]);
  const isWatched = (t: { chain: string; address: string }) => watchKeys.has(watchKey(t.chain, t.address));
  const effectiveAccessCategory: AccessCategory = accessOnly ? accessCategory : "all";
  const marketData = useMemo(() => {
    if (!data) return null;
    const merged = mergeSearchHits(data, searchHits?.q === search.trim().toLowerCase() ? searchHits.tokens : []);
    return demoEnabled ? applyMarketAccessDemo(merged, demoNow.current) : merged;
  }, [data, demoEnabled, searchHits, search]);

  const filtered = useMemo(() => {
    if (!marketData) return [];
    let arr = marketData;
    if (watchOnly) arr = arr.filter(isWatched);
    if (chain !== "all") arr = arr.filter((t) => t.chain === chain);
    const q = search.trim().toLowerCase();
    if (q) {
      arr = arr.filter((t) =>
        (t.symbol || "").toLowerCase().includes(q) ||
        (t.name || "").toLowerCase().includes(q) ||
        t.address.toLowerCase().includes(q),
      );
    }
    if (Object.keys(dailyFilters).length > 0) {
      arr = arr.filter((t) => matchesDailyFilters(t.dailyReturns ?? {}, dailyFilters));
    }
    if (accessOnly) {
      arr = arr.filter((t) => {
        const accessEvents = t.marketAccess ?? [];
        return accessEvents.length > 0 && accessEvents.some((event) => matchesAccessCategory(event, effectiveAccessCategory));
      });
    }
    return arr;
  }, [marketData, chain, search, watchOnly, watchKeys, dailyFilters, accessOnly, effectiveAccessCategory]);

  const onBoard = (t: ViewToken) => {
    if (watchOnly) return true;
    if (board === "streak") return t.streakPool !== false && formalStreakEligible(t.liquidityNum ?? t.liquidity, t.liquidityAgeSec) && isPositiveStreak(t.streakStatus);
    // 全市场是高召回扫描：已收录即上榜，不要求 7D / 8 根日K / 币龄。隐藏由下游单独过滤。
    return true;
  };

  const order = useMemo(() => {
    const rows = filtered
      .map((t) => decorate(applyHot(t, hotRef.current.get(keyOf(t))), gmgnRef.current[t.chain], nowRef.current))
      .filter(onBoard)
      .filter((t) => !hiddenKeySet.has(hiddenTokenKey(t.chain, t.address)));
    if (primarySort) {
      rows.sort((a, b) => compareDailyReturn(a.dailyReturns, b.dailyReturns, primarySort));
      return rows.map(keyOf);
    }
    if (sortKey === "newness") {
      rows.sort(compareNewness);
      return rows.map(keyOf);
    }
    if (sortKey === "added") {
      const rank = new Map(watch.map((w, i) => [watchKey(w.chain, w.address), i]));
      rows.sort((a, b) => (rank.get(watchKey(a.chain, a.address)) ?? 1e9) - (rank.get(watchKey(b.chain, b.address)) ?? 1e9));
      return rows.map(keyOf);
    }
    const metric = sortKey;
    const val = (t: ViewToken): number | null => {
      if (metric === "changeNd") return t.changeNd;
      if (metric === "streak") return t.streak;
      if (metric === "streakReturn") return t.streakReturn;
      if (metric === "streakDrawdown") return t.streakDrawdown;
      if (metric === "holders") return t.holders;
      if (metric === "buys24h") return t.buys24h ?? null;
      if (metric === "sells24h") return t.sells24h ?? null;
      if (metric === "swaps24h") return t.swaps24h ?? null;
      if (metric === "trendingRank") return t.trendingRank ?? null;
      if (metric === "volume24h") return numOrNull(t.volume24h);
      // price / marketCap / liquidity：0 在这些源里表示缺失
      const n = numOrNull(t[metric]);
      return n != null && n > 0 ? n : null;
    };
    rows.sort((a, b) => {
      if (a.stale !== b.stale) return a.stale ? 1 : -1;
      if (sortKey === "streak") return compareStreakThenReturn(a, b, sortDir);
      const va = val(a), vb = val(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return sortDir === "desc" ? vb - va : va - vb;
    });
    return rows.map(keyOf);
  }, [filtered, sortKey, sortDir, primarySort, orderTick, board, watchOnly, watch, hiddenKeySet]);

  const shown = useMemo(() => {
    const latest = new Map(filtered.map((t) => [keyOf(t), decorate(applyHot(t, hotMap.get(keyOf(t))), gmgn[t.chain], now)]));
    const rows: ViewToken[] = [];
    const seen = new Set<string>();
    for (const k of order) {
      const row = latest.get(k);
      if (!row || !onBoard(row) || hiddenKeySet.has(hiddenTokenKey(row.chain, row.address))) continue;
      rows.push(row);
      seen.add(k);
    }
    for (const [k, row] of latest) {
      if (seen.has(k) || !onBoard(row) || hiddenKeySet.has(hiddenTokenKey(row.chain, row.address))) continue;
      rows.push(row);
    }
    return rows;
  }, [filtered, hotMap, gmgn, now, order, board, watchOnly, hiddenKeySet]);

  /** 具备完整数据 = N+1 根连续 FINALIZED 日K。质量标签只决定是否进正式榜，不改这个人数。 */
  const completeNdCount = useMemo(
    () => filtered.filter((t) => t.changeNd != null).length,
    [filtered],
  );

  const movers = useMemo(() => {
    return shown
      .filter((t) => !t.stale && t.pc24h != null && isFinite(Number(t.pc24h)))
      .slice()
      .sort((a, b) => Math.abs(Number(b.pc24h)) - Math.abs(Number(a.pc24h)))
      .slice(0, 8);
  }, [shown]);

  const accessUpdates = useMemo(() => {
    return shown
      .map((token) => {
        const event = getLatestAccessEvent(token.marketAccess ?? []);
        return event ? { token, event } : null;
      })
      .filter((item): item is { token: ViewToken; event: MarketAccessEvent } => item != null)
      .sort((a, b) => {
        const aTime = a.event.detectedAt;
        const bTime = b.event.detectedAt;
        if (aTime == null && bTime == null) return 0;
        if (aTime == null) return 1;
        if (bTime == null) return -1;
        return bTime - aTime;
      })
      .slice(0, 8);
  }, [shown]);

  const dailyFilterDates = Object.keys(dailyFilters);
  const absent = useMemo(() => {
    if (!watchOnly || data == null || error || dailyFilterDates.length > 0 || accessOnly) return [] as WatchItem[];
    const live = new Set(data.map((t) => watchKey(t.chain, t.address)));
    const q = search.trim().toLowerCase();
    return watch.filter((w) => {
      if (live.has(watchKey(w.chain, w.address))) return false;
      if (hiddenKeySet.has(hiddenTokenKey(w.chain, w.address))) return false;
      if (chain !== "all" && w.chain !== chain) return false;
      if (!q) return true;
      return (
        (w.symbol || "").toLowerCase().includes(q) ||
        (w.name || "").toLowerCase().includes(q) ||
        w.address.toLowerCase().includes(q)
      );
    });
  }, [watchOnly, data, error, watch, chain, search, dailyFilterDates.length, accessOnly, hiddenKeySet]);

  const tableRows = useMemo(() => {
    type Row = { kind: "live"; token: ViewToken } | { kind: "gone"; item: WatchItem };
    if (!watchOnly) return shown.map((token): Row => ({ kind: "live", token }));
    if (sortKey !== "added" || primarySort) {
      return [
        ...shown.map((token): Row => ({ kind: "live", token })),
        ...absent.map((item): Row => ({ kind: "gone", item })),
      ];
    }
    const liveBy = new Map(shown.map((t) => [watchKey(t.chain, t.address), t]));
    const goneBy = new Map(absent.map((w) => [watchKey(w.chain, w.address), w]));
    const out: Row[] = [];
    for (const w of watch) {
      const k = watchKey(w.chain, w.address);
      const live = liveBy.get(k);
      if (live) out.push({ kind: "live", token: live });
      else {
        const item = goneBy.get(k);
        if (item) out.push({ kind: "gone", item });
      }
    }
    return out;
  }, [watchOnly, shown, absent, sortKey, primarySort, watch]);

  function toggleSort(key: SortKey) {
    // 点普通列头 = 放弃日期主排序（日期筛选保留）
    setPrimarySort(null);
    if (sortKey === key && !primarySort) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else { setSortKey(key); setSortDir(key === "trendingRank" ? "asc" : "desc"); }
  }
  const sortArrow = (key: SortKey) =>
    sortKey === key && !primarySort ? (sortDir === "desc" ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />) : null;

  const Th = ({ k, label, right = true, title, className = "" }: { k: SortKey; label: string; right?: boolean; title?: string; className?: string }) => (
    <th
      onClick={() => toggleSort(k)}
      title={title}
      className={`cursor-pointer font-mono text-xs whitespace-nowrap hover:text-fg ${right ? "text-right" : "text-center"} ${className}`}
    >
      <span className={`inline-flex items-center gap-1 ${right ? "flex-row-reverse" : ""}`}>{label}{sortArrow(k)}</span>
    </th>
  );

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6">

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索 token"
            className="h-9 w-52 rounded-full border border-line bg-bg pl-9 pr-3 text-sm text-fg focus:border-primary focus:outline-none"
          />
        </div>
        {MARKET_CHAIN_TABS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setChain(c)}
            className={"min-h-9 rounded-full border px-3 text-sm " + (chain === c ? "border-primary text-fg" : "border-line text-muted")}
          >
            {MARKET_CHAIN_LABEL[c]}
          </button>
        ))}
        {!watchProp ? (
          <>
            <button
              type="button"
              onClick={() => selectBoard("all")}
              className={"min-h-9 rounded-full border px-3 text-sm " + (board === "all" ? "border-primary text-fg" : "border-line text-muted")}
            >
              全市场
            </button>
            <button
              type="button"
              onClick={() => selectBoard("streak")}
              className={"min-h-9 rounded-full border px-3 text-sm " + (board === "streak" ? "border-primary text-fg" : "border-line text-muted")}
            >
              连涨榜
            </button>
          </>
        ) : null}
        <button
          type="button"
          data-testid="access-filter"
          aria-pressed={accessOnly}
          onClick={() => setAccessOnly((value) => !value)}
          className={"min-h-9 rounded-full border px-3 text-sm " + (accessOnly ? "border-primary bg-primary/10 text-fg" : "border-line text-muted")}
        >
          状态
        </button>
        {!watchProp ? (
          <>
            <button
              type="button"
              data-testid="watch-tab"
              onClick={() => selectBoard("watch")}
              className={"min-h-9 rounded-full border px-3 text-sm " + (board === "watch" ? "border-primary text-fg" : "border-line text-muted")}
            >
              ★ 自选 <span className="font-mono">{watch.length}</span>
            </button>
          </>
        ) : null}
        {watchOnly ? (
          <button
            type="button"
            onClick={() => setSortKey("added")}
            className={"min-h-9 rounded-full border px-3 text-sm " + (sortKey === "added" ? "border-primary text-fg" : "border-line text-muted")}
          >
            加入顺序
          </button>
        ) : null}
        {!watchOnly && inclusionStats ? (
          <p className="ml-auto max-w-full overflow-x-auto whitespace-nowrap font-mono text-xs text-muted">
            总收录 <span className="text-fg">{inclusionStats.totalTokens.toLocaleString()}</span>
            <span className="mx-2 text-line">·</span>
            今日新增 <span className="text-positive">+{inclusionStats.todayNewTokens.toLocaleString()}</span>
            {tierStats ? (
              <>
                <span className="mx-2 text-line">·</span>
                <span title="MAIN：已观测到流动性≥$50k、已回填日K，或当前流动性≥$50k">
                  MAIN <span className="text-fg">{tierStats.mainTokens.toLocaleString()}</span>
                </span>
                <span className="mx-2 text-line">·</span>
                <a href="#sec-early" title="EARLY：$20k ≤ 当前流动性 < $50k，早期观察，不进正式榜" className="hover:text-fg">
                  EARLY <span className="text-primary">{tierStats.earlyTokens.toLocaleString()}</span>
                </a>
              </>
            ) : null}
          </p>
        ) : null}
        <div className={`flex items-center gap-2 ${watchOnly || !inclusionStats ? "ml-auto" : ""}`}>
          <HiddenTokensMenu
            keys={hiddenKeys}
            tokens={marketData ?? []}
            onRestore={restoreHidden}
            onRestoreAll={() => persistHidden([])}
          />
          <button
            type="button"
            onClick={() => load()}
            disabled={loading}
            className="inline-flex items-center gap-1 rounded-full border border-line px-3 py-1.5 text-sm text-muted hover:text-fg disabled:opacity-50"
          >
            <RefreshCw className={"size-4 " + (loading ? "animate-spin" : "")} />
            刷新
          </button>
        </div>
      </div>

      {accessOnly ? (
        <div className="mb-3 flex flex-wrap items-center gap-2" data-testid="access-categories">
          {ACCESS_CATEGORY_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              data-access-category={option.value}
              aria-pressed={accessCategory === option.value}
              onClick={() => setAccessCategory(option.value)}
              className={"min-h-9 rounded-full border px-3 font-mono text-xs " + (accessCategory === option.value ? "border-primary bg-primary/10 text-fg" : "border-line text-muted")}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}

      <div className="mb-4 flex min-h-9 flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-muted">
          {latestFinalizedDate
            ? `最近 ${dailyDates.length} 个统一 finalized 自然日（截至 ${dateLabel(latestFinalizedDate)}）。点日期列循环 ↑ / ↓ / 不筛，多个日期同时满足（AND）。`
            : "等待 API 提供全市场统一 latest finalized date。"}
        </span>
        {dailyFilterDates.length > 0 ? (
          <button
            type="button"
            onClick={() => {
              setDailyFilters({});
              setPrimarySort(null);
            }}
            className="inline-flex h-9 items-center gap-1 rounded-full border border-primary px-3 text-xs text-fg hover:bg-primary/10"
          >
            <X className="size-3" />
            清除全部日期筛选（{dailyFilterDates.length}）
          </button>
        ) : null}
        {!watchOnly && data && (
          <span
            className="ml-auto font-mono text-xs text-muted"
            data-testid="board-count"
            title={eligibilityTitle(eligibility, days)}
          >
            {loading ? "计算中…" : board === "streak"
              ? `正式连涨榜 ${shown.length} 个`
              : `${days}D窗口${latestFinalizedDate ? `（截至 ${dateLabel(latestFinalizedDate)}）` : ""} · ${completeNdCount} 个具备完整数据`}
          </span>
        )}
      </div>

      <div className="mb-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-mono text-xs text-muted">实时异动</h3>
          <div className="inline-flex rounded-full border border-line p-0.5" aria-label="实时异动显示模式">
            <button
              type="button"
              aria-pressed={activityMode === "price"}
              onClick={() => setActivityMode("price")}
              className={"min-h-8 rounded-full px-3 font-mono text-xs " + (activityMode === "price" ? "bg-surface-2 text-fg" : "text-muted")}
            >
              价格异动
            </button>
            <button
              type="button"
              aria-pressed={activityMode === "access"}
              onClick={() => setActivityMode("access")}
              className={"min-h-8 rounded-full px-3 font-mono text-xs " + (activityMode === "access" ? "bg-surface-2 text-fg" : "text-muted")}
            >
              最新状态
            </button>
          </div>
        </div>
        <div className="flex gap-2 overflow-x-auto">
          {activityMode === "price" ? (
            <>
              {movers.map((t) => (
                <div key={keyOf(t)} className="min-w-36 rounded-lg border border-line px-3 py-2">
                  <p className="truncate text-sm">{t.symbol || "?"}</p>
                  <p className={`font-mono text-xs ${pctColor(Number(t.pc24h))}`}>{fmtPct(Number(t.pc24h))}</p>
                </div>
              ))}
              {movers.length === 0 && <p className="text-xs text-muted">没有仍在周期内的行情</p>}
            </>
          ) : (
            <>
              {accessUpdates.map(({ token, event }) => (
                <button
                  key={`${keyOf(token)}:${event.id}`}
                  type="button"
                  onClick={() => openAccessDetail(token)}
                  className="min-w-40 rounded-lg border border-line px-3 py-2 text-left hover:bg-surface"
                >
                  <span className="block truncate text-sm text-fg">{token.symbol || "?"}</span>
                  <span className="mt-0.5 block truncate font-mono text-xs text-muted">
                    {marketAccessLabel(event.kind)}
                    {isSurpriseAccessEvent(event) ? " · Surprise" : null}
                    {isScheduledAccessEvent(event) ? " · Scheduled" : null}
                  </span>
                  <span className="mt-1 block font-mono text-[10px] text-muted">{fmtAccessAge(event.detectedAt, now)}</span>
                </button>
              ))}
              {accessUpdates.length === 0 && <p className="text-xs text-muted">没有已记录的市场准入状态</p>}
            </>
          )}
        </div>
      </div>

      {error && <p className="mb-3 rounded-lg border border-negative/30 bg-negative/10 p-3 text-sm text-negative">{error}</p>}

      <div ref={scrollRef} className="market-table-scroll overflow-x-auto rounded-xl border border-line" data-testid="market-scroll">
        <table className="market-table w-full text-left text-sm" data-days={days} data-applied-days={appliedDays ?? ""} data-window-end={latestFinalizedDate ?? ""} data-api-rows={marketData?.length ?? 0} data-qualified-rows={tableRows.length} data-sort={primarySort ? `daily:${primarySort.date}:${primarySort.dir}` : String(sortKey)}>
          <thead>
            <tr className="border-b border-line bg-surface-2 text-xs text-muted">
              <th className="market-star-sticky text-center font-mono" title="自选">★</th>
              <th className="market-hide-sticky text-center font-mono" title="隐藏">×</th>
              <th className="market-token-sticky font-mono">Token</th>
              <Th k="price" label="Price" className="market-price-col" />
              <th className="market-age-col font-mono text-right">Age</th>
              <Th k="marketCap" label="FDV / MC" title="上行 FDV：GMGN market_cap = price × total_supply。下行 MC：流通市值，库里没有独立字段时显示 —，不拿 FDV 顶替。按 FDV 排序。" className="market-fdv-col" />
              {dailyDates.map((date) => {
                const direction = dailyFilters[date];
                const isLatestFinalized = date === latestFinalizedDate;
                const isPrimary = primarySort?.date === date;
                const tLabel = fmtTOffset(dateTOffset(date, latestFinalizedDate!));
                return (
                  <th
                    key={date}
                    className="market-date-col text-center font-mono text-xs whitespace-nowrap"
                    data-daily-date={date}
                    data-latest-finalized={isLatestFinalized ? "true" : undefined}
                    data-t-offset={tLabel}
                    data-primary-sort={isPrimary ? primarySort.dir : undefined}
                  >
                    <button
                      type="button"
                      onClick={() => clickDailyDate(date)}
                      title={`${date} · ${tLabel}${isLatestFinalized ? "（最近 finalized）" : ""}：点击循环 NONE → UP → DOWN。最后点击的日期决定排序（↑ 从大到小，↓ 从小到大），其他已选日期只筛选`}
                      aria-label={`${date} 日收益筛选，当前 ${direction ?? "NONE"}`}
                      aria-pressed={direction != null}
                      data-daily-filter={direction ?? ""}
                      className={`inline-flex h-9 w-full flex-col items-center justify-center rounded-md px-1 leading-tight hover:bg-surface ${isPrimary ? "underline decoration-primary underline-offset-2" : ""} ${direction === "UP" ? "text-positive" : direction === "DOWN" ? "text-negative" : "text-muted hover:text-fg"}`}
                    >
                      <span>
                        {dateLabel(date)}
                        {direction === "UP" ? "↑" : direction === "DOWN" ? "↓" : null}
                      </span>
                      <span className="text-[10px] opacity-60">{tLabel}</span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row) => {
              if (row.kind === "gone") {
                const item = row.item;
                return (
                  <tr key={watchKey(item.chain, item.address)} data-watch-key={watchKey(item.chain, item.address)} className="border-b border-line/50 text-muted last:border-b-0">
                    <td className="market-star-sticky text-center">
                      <StarButton on onClick={() => onStar(item)} />
                    </td>
                    <td className="market-hide-sticky text-center">
                      <HideTokenButton symbol={item.symbol} onClick={() => hideToken(item)} />
                    </td>
                    <td className="market-token-sticky">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{item.symbol || "?"} <span className="font-mono text-[10px] text-muted">{item.chain}</span></p>
                        <CopyAddress address={item.address} />
                        <p className="font-mono text-[10px] text-negative">不在当前榜</p>
                      </div>
                    </td>
                    <td className="market-price-col text-right font-mono text-xs">—</td>
                    <td className="market-age-col text-right font-mono text-xs">—</td>
                    <td className="market-fdv-col text-right font-mono text-xs">
                      <div>—</div>
                      <div>—</div>
                    </td>
                    {dailyDates.map((date) => (
                      <td
                        key={date}
                        className="market-date-col text-right font-mono text-xs text-muted"
                        data-daily-date={date}
                        data-latest-finalized={date === latestFinalizedDate ? "true" : undefined}
                      >
                        <div>—</div>
                        <div className="market-daily-volume">—</div>
                      </td>
                    ))}
                  </tr>
                );
              }
              const t = row.token;
              const tag = t.halt ? "停牌" : t.marketClosed ? "休市" : "";
              const quoteTitle = `报价来源 ${t.priceSource ?? "legacy/unknown"}；年龄 ${fmtAge(t.ageSec)}。只影响 Price / 实时异动，不影响已收盘日K。`;
              const marketCapTitle = `Market cap 来源 ${t.marketCapSource ?? "legacy/unknown"}；年龄 ${fmtAge(t.marketCapAgeSec)}。`;
              return (
                <tr
                  key={keyOf(t)}
                  data-symbol={t.symbol || ""}
                  data-address={t.address}
                  data-chain={t.chain}
                  data-watch-key={watchKey(t.chain, t.address)}
                  data-streak={t.streak == null ? "" : String(t.streak)}
                  data-change-nd={t.changeNd == null ? "" : String(t.changeNd)}
                  data-daily-status={t.lastDailyStatus ?? ""}
                  className="border-b border-line/50 last:border-b-0 hover:bg-surface/40"
                >
                  <td className="market-star-sticky text-center">
                    <StarButton on={isWatched(t)} onClick={() => onStar(t)} />
                  </td>
                  <td className="market-hide-sticky text-center">
                    <HideTokenButton symbol={t.symbol} onClick={() => hideToken(t)} />
                  </td>
                  <td className="market-token-sticky">
                    <TokenCell
                      t={t}
                      now={now}
                      showAnchor={!watchOnly && board === "streak"}
                      onOpen={() => openTokenDetail(t)}
                      onOpenAccess={() => openAccessDetail(t)}
                    />
                    {tag && <span className="ml-10 font-mono text-[10px] text-negative">{tag}</span>}
                    {t.diverge === 1 && <span className="ml-1 font-mono text-[10px] text-primary">DIVERGE</span>}
                  </td>
                  <FlashCell value={t.price} armed={t.commitOk && t.chgPrice} className="market-price-col text-right font-mono text-xs">
                    <span title={quoteTitle}>
                      ${fmtPrice(t.price)}
                    </span>
                  </FlashCell>
                  <td className="market-age-col text-right font-mono text-xs">{fmtAge(t.ageSec)}</td>
                  <td className="market-fdv-col text-right font-mono text-xs" title={marketCapTitle}>
                    <div data-fdv>
                      {fmtUsd(t.marketCap)}
                    </div>
                    <div data-mc className="text-muted" title="流通市值（MC）：市场库没有单独的流通市值 / 流通量字段，不拿 FDV 顶替">—</div>
                  </td>
                  {dailyDates.map((date) => {
                    // 收益和成交量取自同一个 (chain, address, date) 对象，不分别查表。
                    const day = t.dailyHistory?.find((entry) => entry.date === date);
                    const dailyReturn = day?.returnPct ?? null;
                    const volumeUsd = day?.volumeUsd ?? null;
                    return (
                      <td
                        key={date}
                        className={`market-date-col text-right font-mono text-xs ${pctColor(dailyReturn)}`}
                        title={`${date} FINALIZED UTC 日K：收益 ${formatDailyReturn(dailyReturn)} · 成交量 ${volumeUsd == null ? "—（无可信数据）" : `$${Math.round(volumeUsd).toLocaleString("en-US")}`}`}
                        data-daily-date={date}
                        data-daily-return={dailyReturn == null ? "" : String(dailyReturn)}
                        data-daily-volume={volumeUsd == null ? "" : String(volumeUsd)}
                        data-latest-finalized={date === latestFinalizedDate ? "true" : undefined}
                      >
                        <div>{formatDailyReturn(dailyReturn)}</div>
                        <div className="market-daily-volume">{formatCompactUsd(volumeUsd)}</div>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
        {tableRows.length === 0 && !loading && !error && (
          <p className="p-8 text-center text-muted">
            {accessOnly
              ? "当前筛选没有已记录的市场准入状态"
              : watchOnly
              ? (watch.length === 0 ? "还没有自选。在全市场或连涨榜点代币前面的 ☆。" : "没有匹配的自选")
              : board === "streak"
                ? "正式连涨榜没有流动性不低于 $50,000 且年龄不超过 300 秒的代币"
                : data && data.length > 0
                  ? "没有匹配当前条件的代币"
                  : "没有数据，先跑采集器"}
          </p>
        )}
      </div>
      {detail ? <TokenDetailDrawer chain={detail.chain} address={detail.address} onClose={() => setDetail(null)} /> : null}
      {accessDetail ? <MarketAccessDrawer detail={accessDetail} onClose={() => setAccessDetail(null)} /> : null}
      <p className="mt-3 text-xs text-muted">
        {watchOnly
          ? "自选存在这台浏览器。点星标加入或移出。名单不看 $50,000 流动性门槛。掉出当前榜的代币留在这里，并标成不在当前榜。默认按加入顺序。"
          : null}
        {watchOnly ? " " : null}
        {`24H：当前价格相对 24 小时前的滚动涨跌幅，新鲜度跟报价走。日K / 连续上涨 / N日累计只用 FINALIZED 日K（日历已收盘且 fetched_at >= bar.end）。PROVISIONAL 日K保留在库里，不进正式指标。连续上涨与顶部 N 日窗口独立。${days}D累计需要 ${days + 1} 根连续 finalized 日K。LOW_BASE / EXTREME_RETURN 是质量标签，不改 raw 收益。正式连涨榜要求流动性不低于 $50,000，且流动性年龄不超过 300 秒。回撤超过 40% 只标红，不取消连续上涨。身份是 chain + CA，同名代币靠 CA 区分。Age 是价格源年龄，不是日 K 年龄。`}
      </p>
    </div>
  );
}

/** Unified paging is the default. The legacy full-registry query is opt-in so
 * its synchronous historical scan cannot stall the unified local-data panel. */
export function MarketView({watchOnly=false}:{watchOnly?:boolean}) {
  const [showLegacy,setShowLegacy]=useState(false);
  return <div className="mx-auto max-w-[1400px] px-4 py-6">
    <WmUnifiedMarket watchOnly={watchOnly} />
    <MarketHealthBar />
    <WmQualityBar />
    <button className="min-h-11 rounded-lg border border-line bg-surface px-4 text-sm text-muted" aria-expanded={showLegacy} onClick={()=>setShowLegacy(!showLegacy)}>
      {showLegacy?'收起':'展开'}链上观察与原有筛选
    </button>
    {showLegacy&&<LegacyMarketView watchOnly={watchOnly}/>}
  </div>;
}
