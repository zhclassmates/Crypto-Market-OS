import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useServerFn } from "@tanstack/react-start";
import { RefreshCw, Search, ArrowUp, ArrowDown, Star } from "lucide-react";
import { fetchMarketHot, fetchMarketRank, type GmgnClock, type HotToken } from "@/lib/rh/market-server";
import {
  CHAINLINK_POLL_PERIOD,
  GMGN_PRICE_PERIOD,
  SOURCE_PERIOD,
  adjustedAnchor,
  deviationRatio,
  fieldAgeSec,
  fmtAge,
  tokenIsStale,
} from "@/lib/rh/market-status";
import {
  DEFAULT_DAYS,
  DRAWDOWN_ALERT,
  DRAWDOWN_HINT,
  LIQUIDITY_FRESHNESS_SEC,
  MAX_CUSTOM_DAYS,
  PRESET_DAYS,
  STREAK_MIN_LIQUIDITY,
  anchorDeviation,
  compareStreakThenReturn,
  fmtRelativeAge,
  formalStreakEligible,
  klineIsStale,
} from "@/lib/rh/streak";
import { MarketHealthBar } from "@/components/market-health-bar";
import {
  WATCH_EVENT,
  loadWatchlist,
  toggleWatchItem,
  watchKey,
  writeWatchlist,
  type WatchItem,
} from "@/lib/rh/watchlist";

interface RankedToken {
  chain: string;
  address: string;
  symbol: string | null;
  name: string | null;
  logo: string | null;
  price: string;
  pc24h: string | null;
  volume24h: string;
  liquidity: string;
  marketCap: string;
  holders: number | null;
  changeNd: number | null;
  change1d: number | null;
  streak: number;
  streakReturn: number | null;
  streakDrawdown: number | null;
  closedCandles: number;
  createdAt: number | null;
  createdSource: "token" | "pair" | null;
  tokenCreatedAt: number | null;
  pairCreatedAt: number | null;
  firstSeenAt: number | null;
  klineFetchedAt: number | null;
  spark: number[] | null;
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
}

interface ViewToken extends RankedToken {
  ageSec: number | null;
  liquidityAgeSec: number | null;
  stale: boolean;
  klineStale: boolean;
}

const CHAIN_TABS = ["all", "sol", "robinhood", "base", "eth"] as const;
const CHAIN_LABEL: Record<string, string> = {
  all: "全部", sol: "Solana", robinhood: "Robinhood", base: "Base", eth: "Ethereum",
};
const CHAIN_BADGE: Record<string, string> = {
  sol: "bg-[#9945FF]", robinhood: "bg-[#00C805]", base: "bg-[#0052FF]", eth: "bg-[#627EEA]",
};
const HEAVY_MS = 60_000;
const HOT_MS = 8_000;
const REORDER_MS = 20_000;
/** 一次只画这么多行。整表上千行每秒重绘会把页面拖住。 */
const PAGE_ROWS = 100;

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
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}
function fmtPct(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  const pct = v * 100;
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${Math.abs(pct).toFixed(1)}%`;
}
function pctColor(v: number | null | undefined): string {
  if (v == null) return "text-muted";
  if (v > 0) return "text-moss";
  if (v < 0) return "text-clay";
  return "text-muted";
}

function Sparkline({ data }: { data: number[] | null }) {
  if (!data || data.length < 2) return <div className="h-8 w-24" />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 96, h = 30;
  const pts = data.map((v, i) => [
    (i / (data.length - 1)) * w,
    h - 2 - ((v - min) / range) * (h - 4),
  ]);
  const up = data[data.length - 1] >= data[0];
  const color = up ? "var(--color-moss)" : "var(--color-clay)";
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${d} L${w},${h} L0,${h} Z`;
  return (
    <svg width={w} height={h} className="block" aria-hidden>
      <path d={area} fill={color} opacity={0.12} />
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
}

function fmtLocal(ts: number): string {
  const d = new Date(ts * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function shortCa(address: string): string {
  if (address.length <= 13) return address;
  return `${address.slice(0, 6)}...${address.slice(-5)}`;
}

function CaCell({ address }: { address: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      title={address}
      onClick={() => {
        void navigator.clipboard.writeText(address).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1200);
        });
      }}
      className="max-w-28 truncate font-mono text-xs text-muted hover:text-fg"
    >
      {copied ? "已复制" : shortCa(address)}
    </button>
  );
}

function CreatedCell({ t, now }: { t: RankedToken; now: number }) {
  if (t.createdAt == null) {
    return <span className="font-mono text-xs text-muted" title="没有代币创建时间，也没有池子创建时间">—</span>;
  }
  const kind = t.createdSource === "pair" ? "池子创建" : "代币创建";
  return (
    <span className="whitespace-nowrap font-mono text-xs" title={`${kind} ${fmtLocal(t.createdAt)}`}>
      {fmtRelativeAge(now, t.createdAt)}
      {t.createdSource === "pair" ? <span className="ml-1 text-[10px] text-brass">pair</span> : null}
    </span>
  );
}

function drawdownClass(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "text-muted";
  if (v > DRAWDOWN_ALERT) return "text-clay font-medium";
  if (v > DRAWDOWN_HINT) return "text-brass";
  return "text-fg";
}

function fmtDrawdown(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function klineTitle(t: ViewToken, now: number): string {
  if (t.klineFetchedAt == null) return "日K没有成功拉取时间。这个数字不能当成最新价。";
  return `日K拉取于 ${fmtAge(now - t.klineFetchedAt)} 前。价格更新时间是另一路。`;
}

function AnchorTag({ t, now }: { t: ViewToken; now: number }) {
  const hasAnchor = t.anchorBid != null || t.anchorAsk != null || t.anchorGeneratedAt != null;
  if (!hasAnchor) return null;
  const age = t.anchorGeneratedAt == null ? null : now - t.anchorGeneratedAt;
  const stale = age == null || age > 2 * SOURCE_PERIOD.robinhood_anchor;
  if (stale) {
    return <span className="font-mono text-[10px] text-clay" title="锚价过期，不拿旧锚价做判断">Anchor stale</span>;
  }
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

function TokenCell({ t, now, showAnchor }: { t: ViewToken; now: number; showAnchor: boolean }) {
  const [logoOk, setLogoOk] = useState(true);
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-8 w-8 shrink-0">
        {t.logo && logoOk ? (
          <img src={t.logo} alt="" className="h-8 w-8 rounded-full bg-surface-2 object-cover" loading="lazy" onError={() => setLogoOk(false)} />
        ) : (
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-2 font-mono text-xs text-muted">
            {(t.symbol || "?").slice(0, 2)}
          </div>
        )}
        <span className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border border-bg ${CHAIN_BADGE[t.chain] || "bg-muted"}`} title={t.chain} />
      </div>
      <div className="w-36 min-w-0" title={t.name || t.symbol || ""}>
        <p className="truncate text-sm font-medium leading-tight">{t.symbol || "?"}</p>
        <p className="truncate font-mono text-xs text-muted leading-tight">{t.name || ""}</p>
        {showAnchor ? <AnchorTag t={t} now={now} /> : null}
      </div>
    </div>
  );
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

type SortKey = "changeNd" | "streak" | "volume24h" | "liquidity" | "marketCap" | "price" | "pc24h" | "holders" | "change1d" | "streakReturn" | "streakDrawdown";
type SortMode = SortKey | "added";
type Board = "all" | "streak";

function StarButton({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={on ? "移出自选" : "加入自选"}
      title={on ? "移出自选" : "加入自选"}
      onClick={onClick}
      className="inline-flex size-8 shrink-0 items-center justify-center rounded-full hover:bg-surface-2"
    >
      <Star className={"size-4 " + (on ? "fill-brass text-brass" : "text-muted")} />
    </button>
  );
}

function keyOf(t: { chain: string; address: string }) {
  return `${t.chain}:${t.address}`;
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
  };
}

function decorate(t: RankedToken, clock: GmgnClock | undefined, now: number): ViewToken {
  const ageSec = fieldAgeSec(
    now,
    clock?.lastSuccess ?? null,
    clock?.sourceTimestamp ?? null,
    clock?.sourceTimestampMissing ?? true,
  );
  const liquidityAgeSec = t.liquidityUpdatedAt == null ? null : now - t.liquidityUpdatedAt;
  return {
    ...t,
    ageSec,
    liquidityAgeSec,
    stale: tokenIsStale(ageSec, GMGN_PRICE_PERIOD, t.halt, t.marketClosed),
    klineStale: klineIsStale(now, t.klineFetchedAt),
  };
}

export function MarketView({ watchOnly = false }: { watchOnly?: boolean }) {
  const [days, setDays] = useState(DEFAULT_DAYS);
  const [customDays, setCustomDays] = useState("");
  const [customErr, setCustomErr] = useState("");
  const [chain, setChain] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [data, setData] = useState<RankedToken[] | null>(null);
  const [hotMap, setHotMap] = useState<Map<string, HotToken>>(new Map());
  const [gmgn, setGmgn] = useState<Record<string, GmgnClock>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sortKey, setSortKey] = useState<SortMode>(watchOnly ? "added" : "changeNd");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [board, setBoard] = useState<Board>("all");
  const [watch, setWatch] = useState<WatchItem[]>([]);
  const [heavyTick, setHeavyTick] = useState(0);
  const [orderTick, setOrderTick] = useState(0);
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));
  const [registryCount, setRegistryCount] = useState<number | null>(null);
  const [limit, setLimit] = useState(PAGE_ROWS);

  const rankFn = useServerFn(fetchMarketRank);
  const hotFn = useServerFn(fetchMarketHot);
  const inflight = useRef<AbortController | null>(null);
  const hotRef = useRef(hotMap);
  const gmgnRef = useRef(gmgn);
  const nowRef = useRef(now);
  // 自选页只向后端要自选里的币；排行页由后端按榜单条件预筛。
  const watchKeysParam = watchOnly ? watch.map((w) => watchKey(w.chain, w.address)) : undefined;
  const keysRef = useRef(watchKeysParam);
  keysRef.current = watchKeysParam;
  hotRef.current = hotMap;
  gmgnRef.current = gmgn;
  nowRef.current = now;

  function applyCustom() {
    setCustomErr("");
    const n = Number(customDays);
    if (!customDays.trim() || !Number.isInteger(n) || n < 1 || n > MAX_CUSTOM_DAYS) {
      setCustomErr(`1–${MAX_CUSTOM_DAYS} 的整数`);
      return;
    }
    selectDays(n);
  }

  function selectDays(n: number) {
    setDays(n);
    if (!watchOnly && board === "all") {
      setSortKey("changeNd");
      setSortDir("desc");
    }
  }

  async function load(silent = false) {
    inflight.current?.abort();
    const ctrl = new AbortController();
    inflight.current = ctrl;
    if (!silent) setLoading(true);
    setError("");
    try {
      const res = await rankFn({ data: { days, keys: keysRef.current } });
      if (ctrl.signal.aborted) return;
      if (!res.ok) {
        setError(res.error || "拉取失败");
        setData([]);
      } else {
        setData(res.tokens);
        if (res.registryCount != null) setRegistryCount(res.registryCount);
        if (res.gmgn) setGmgn(res.gmgn);
        const ranked = [...res.tokens]
          .filter((t) => t.changeNd != null && isFinite(t.changeNd))
          .sort((a, b) => (b.changeNd ?? -Infinity) - (a.changeNd ?? -Infinity));
        console.debug("[market-rank]", {
          selectedDays: days,
          requestDays: days,
          backendDays: res.days,
          calculationDays: res.days,
          rows: res.tokens.length,
          top5: ranked.slice(0, 5).map((t) => ({
            symbol: t.symbol,
            address: t.address,
            changeNd: t.changeNd,
          })),
        });
      }
    } catch (e) {
      if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
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

  function onStar(t: { chain: string; address: string; symbol: string | null; name: string | null }) {
    const current = loadWatchlist(window.localStorage);
    const next = toggleWatchItem(current, t, Math.floor(Date.now() / 1000));
    writeWatchlist(window.localStorage, next);
    setWatch(next);
    window.dispatchEvent(new Event(WATCH_EVENT));
  }

  const watchSig = watchOnly ? (watchKeysParam ?? []).join(",") : "";
  useEffect(() => {
    // 自选为空不用问后端；挂载时 watch 还没读出来，读到后 watchSig 变了会再拉
    if (watchOnly && watch.length === 0) { setData([]); return; }
    load();
    if (watchOnly) loadHot();
  }, [days, watchSig]);
  useEffect(() => { setLimit(PAGE_ROWS); }, [days, board, chain, search, sortKey, sortDir]);
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

  const watchKeys = useMemo(() => new Set(watch.map((w) => watchKey(w.chain, w.address))), [watch]);

  const filtered = useMemo(() => {
    if (!data) return [];
    let arr = data;
    if (watchOnly) arr = arr.filter((t) => watchKeys.has(keyOf(t)));
    if (chain !== "all") arr = arr.filter((t) => t.chain === chain);
    const q = search.trim().toLowerCase();
    if (q) {
      arr = arr.filter((t) =>
        (t.symbol || "").toLowerCase().includes(q) ||
        (t.name || "").toLowerCase().includes(q) ||
        t.address.toLowerCase().includes(q),
      );
    }
    return arr;
  }, [data, chain, search, watchOnly, watchKeys]);

  const onBoard = (t: ViewToken) => {
    if (watchOnly) return true;
    if (board === "streak") return formalStreakEligible(t.liquidityNum ?? t.liquidity, t.liquidityAgeSec);
    // 全市场按 N 日累计排；日K不足 N+1 根的币不符合条件，不列
    return t.changeNd != null;
  };

  const order = useMemo(() => {
    const rows = filtered
      .map((t) => decorate(applyHot(t, hotRef.current.get(keyOf(t))), gmgnRef.current[t.chain], nowRef.current))
      .filter(onBoard);
    if (sortKey === "added") {
      const rank = new Map(watch.map((w, i) => [watchKey(w.chain, w.address), i]));
      rows.sort((a, b) => (rank.get(keyOf(a)) ?? 1e9) - (rank.get(keyOf(b)) ?? 1e9));
      return rows.map(keyOf);
    }
    const metric = sortKey;
    const val = (t: ViewToken): number | null => {
      if (metric === "changeNd") return t.changeNd;
      if (metric === "streak") return t.streak;
      if (metric === "change1d") return t.change1d;
      if (metric === "streakReturn") return t.streakReturn;
      if (metric === "streakDrawdown") return t.streakDrawdown;
      if (metric === "holders") return t.holders;
      if (metric === "pc24h") {
        if (t.pc24h == null) return null;
        const n = Number(t.pc24h);
        return isFinite(n) ? n : null;
      }
      const n = Number(t[metric]);
      return isFinite(n) && n > 0 ? n : null;
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
  }, [filtered, sortKey, sortDir, orderTick, board, watchOnly, watch]);

  const shown = useMemo(() => {
    const latest = new Map(filtered.map((t) => [keyOf(t), decorate(applyHot(t, hotMap.get(keyOf(t))), gmgn[t.chain], now)]));
    const rows: ViewToken[] = [];
    const seen = new Set<string>();
    for (const k of order) {
      const row = latest.get(k);
      if (!row || !onBoard(row)) continue;
      rows.push(row);
      seen.add(k);
    }
    for (const [k, row] of latest) {
      if (seen.has(k) || !onBoard(row)) continue;
      rows.push(row);
    }
    return rows;
  }, [filtered, hotMap, gmgn, now, order, board]);

  const movers = useMemo(() => {
    return shown
      .filter((t) => !t.stale && t.pc24h != null && isFinite(Number(t.pc24h)))
      .slice()
      .sort((a, b) => Math.abs(Number(b.pc24h)) - Math.abs(Number(a.pc24h)))
      .slice(0, 8);
  }, [shown]);

  const columns: Board = watchOnly ? "all" : board;

  const absent = useMemo(() => {
    if (!watchOnly || data == null || error) return [] as WatchItem[];
    const live = new Set(data.map(keyOf));
    const q = search.trim().toLowerCase();
    return watch.filter((w) => {
      if (live.has(watchKey(w.chain, w.address))) return false;
      if (chain !== "all" && w.chain !== chain) return false;
      if (!q) return true;
      return (
        (w.symbol || "").toLowerCase().includes(q) ||
        (w.name || "").toLowerCase().includes(q) ||
        w.address.toLowerCase().includes(q)
      );
    });
  }, [watchOnly, data, error, watch, chain, search]);

  const tableRows = useMemo(() => {
    type Row = { kind: "live"; token: ViewToken } | { kind: "gone"; item: WatchItem };
    if (!watchOnly) return shown.map((token): Row => ({ kind: "live", token }));
    if (sortKey !== "added") {
      return [
        ...shown.map((token): Row => ({ kind: "live", token })),
        ...absent.map((item): Row => ({ kind: "gone", item })),
      ];
    }
    const liveBy = new Map(shown.map((t) => [keyOf(t), t]));
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
  }, [watchOnly, shown, absent, sortKey, watch]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else { setSortKey(key); setSortDir("desc"); }
  }
  const sortArrow = (key: SortKey) =>
    sortKey === key ? (sortDir === "desc" ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />) : null;

  const Th = ({ k, label, right = true, title }: { k: SortKey; label: string; right?: boolean; title?: string }) => (
    <th
      onClick={() => toggleSort(k)}
      title={title}
      className={`cursor-pointer px-3 py-2 font-mono text-xs whitespace-nowrap hover:text-fg ${right ? "text-right" : "text-center"}`}
    >
      <span className={`inline-flex items-center gap-1 ${right ? "flex-row-reverse" : ""}`}>{label}{sortArrow(k)}</span>
    </th>
  );

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6">
      <MarketHealthBar />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索 token"
            className="h-9 w-52 rounded-full border border-line bg-bg pl-9 pr-3 text-sm text-fg focus:border-brass focus:outline-none"
          />
        </div>
        {CHAIN_TABS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setChain(c)}
            className={"min-h-9 rounded-full border px-3 text-sm " + (chain === c ? "border-brass text-fg" : "border-line text-muted")}
          >
            {CHAIN_LABEL[c]}
          </button>
        ))}
        {watchOnly ? (
          <button
            type="button"
            onClick={() => setSortKey("added")}
            className={"min-h-9 rounded-full border px-3 text-sm " + (sortKey === "added" ? "border-brass text-fg" : "border-line text-muted")}
          >
            加入顺序
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => {
                setBoard("all");
                setSortKey("changeNd");
                setSortDir("desc");
              }}
              className={"min-h-9 rounded-full border px-3 text-sm " + (board === "all" ? "border-brass text-fg" : "border-line text-muted")}
            >
              全市场
            </button>
            <button
              type="button"
              onClick={() => {
                setBoard("streak");
                setSortKey("streak");
                setSortDir("desc");
              }}
              className={"min-h-9 rounded-full border px-3 text-sm " + (board === "streak" ? "border-brass text-fg" : "border-line text-muted")}
            >
              连涨榜
            </button>
          </>
        )}
        <div className="ml-auto">
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

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {PRESET_DAYS.map((d) => (
          <button
            key={d}
            type="button"
            aria-pressed={days === d}
            data-days={d}
            onClick={() => selectDays(d)}
            className={"min-h-9 rounded-full border px-3 text-sm font-mono " + (days === d ? "border-brass bg-brass/10 text-fg" : "border-line text-muted")}
          >
            {d}D
          </button>
        ))}
        <div className="flex items-center gap-1">
          <input
            type="text"
            value={customDays}
            onChange={(e) => setCustomDays(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyCustom()}
            placeholder="自定义"
            className="h-9 w-20 rounded-full border border-line bg-bg px-3 text-sm font-mono text-fg focus:border-brass focus:outline-none"
          />
          <button type="button" onClick={applyCustom} className="h-9 rounded-full border border-line px-3 text-sm text-muted hover:text-fg">
            应用
          </button>
        </div>
        {customErr && <span className="text-xs text-clay">{customErr}</span>}
        {!watchOnly && data && (
          <span className="ml-auto font-mono text-xs text-muted" data-testid="board-count">
            {loading ? "计算中…" : board === "streak"
              ? `正式连涨榜 ${shown.length} 个`
              : `符合 ${days}D 条件 ${shown.length} 个${registryCount != null ? ` · 名册 ${registryCount} 个，其余日K不足 ${days + 1} 根` : ""}`}
          </span>
        )}
      </div>

      <div className="mb-4">
        <h3 className="mb-2 font-mono text-xs text-muted">实时异动 · 不含 STALE</h3>
        <div className="flex gap-2 overflow-x-auto">
          {movers.map((t) => (
            <div key={keyOf(t)} className="min-w-36 rounded-lg border border-line px-3 py-2">
              <p className="truncate text-sm">{t.symbol || "?"}</p>
              <p className={`font-mono text-xs ${pctColor(Number(t.pc24h))}`}>{fmtPct(Number(t.pc24h))}</p>
            </div>
          ))}
          {movers.length === 0 && <p className="text-xs text-muted">没有仍在周期内的行情</p>}
        </div>
      </div>

      {error && <p className="mb-3 rounded-lg border border-clay/30 bg-clay/10 p-3 text-sm text-clay">{error}</p>}

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-left text-sm" data-days={days} data-sort={String(sortKey)}>
          <thead>
            <tr className="border-b border-line bg-surface-2 text-xs text-muted">
              <th className="px-3 py-2 font-mono">#</th>
              <th className="px-3 py-2 font-mono">Token</th>
              <th className="px-3 py-2 font-mono">CA</th>
              <th className="px-3 py-2 font-mono">Created</th>
              <th className="px-3 py-2 font-mono">Chart</th>
              <Th k="price" label="Price" />
              {columns === "all" && <th className="px-3 py-2 font-mono text-right">Age</th>}
              <Th k="marketCap" label="Mkt Cap" />
              <Th k="pc24h" label="24H" title="当前价格相对 24 小时前的滚动涨跌幅。" />
              <Th k="change1d" label="日K" title="最近一根已收盘 UTC 日K，相对前一根已收盘日K的涨跌幅。" />
              <Th k="streak" label="连涨" right={false} title="连续多少根已收盘 UTC 日K收盘价高于前一日。不受顶部天数按钮影响。" />
              <Th
                k="changeNd"
                label={`${days}D累计`}
                title="最新已收盘 UTC 日K收盘价，相对 N 个完整日线区间前收盘价的累计变化。顶部天数按钮只改这一列和它的排名。"
              />
              <Th k="streakReturn" label="累计涨幅" title="连涨这段的收盘价累计。不是 N 日累计。" />
              <Th k="streakDrawdown" label="回撤" />
              <Th k="volume24h" label="Volume(24h)" />
              <Th k="liquidity" label="Liquidity" />
              <Th k="holders" label="Holders" />
              {columns === "all" && (
                <>
                  <th className="px-3 py-2 font-mono text-right">Anchor</th>
                  <th className="px-3 py-2 font-mono text-right">Oracle</th>
                  <th className="px-3 py-2 font-mono text-right">DEX</th>
                  <th className="px-3 py-2 font-mono text-right">偏离</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {tableRows.slice(0, limit).map((row, i) => {
              if (row.kind === "gone") {
                const item = row.item;
                return (
                  <tr key={watchKey(item.chain, item.address)} className="border-b border-line/50 text-muted last:border-b-0">
                    <td className="px-3 py-2 font-mono text-xs">{i + 1}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1">
                        <StarButton on onClick={() => onStar(item)} />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{item.symbol || "?"}</p>
                          <p className="truncate font-mono text-xs">{item.name || ""}</p>
                          <p className="font-mono text-[10px] text-clay">不在当前榜</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2"><CaCell address={item.address} /></td>
                    {Array.from({ length: 18 }, (_, n) => (
                      <td key={n} className="px-3 py-2 text-right font-mono text-xs">—</td>
                    ))}
                  </tr>
                );
              }
              const t = row.token;
              const anchor = t.chain === "robinhood" ? adjustedAnchor(t.anchorBid, t.anchorAsk, t.anchorMultiplier) : null;
              const dex = Number(t.dexPrice);
              const dev = deviationRatio(anchor, Number.isFinite(dex) ? dex : null);
              const oracleAge = t.oracleUpdatedAt ? now - t.oracleUpdatedAt : null;
              const oracleStale = t.chain === "robinhood" && (oracleAge == null || oracleAge > 2 * CHAINLINK_POLL_PERIOD);
              const tag = t.halt ? "停牌" : t.marketClosed ? "休市" : t.stale ? "STALE" : "";
              const klineBadge = () => (t.klineStale ? <span className="mr-1 font-mono text-[10px] text-clay">stale</span> : null);
              const kTitle = klineTitle(t, now);
              return (
                <tr key={keyOf(t)} className={"border-b border-line/50 last:border-b-0 hover:bg-surface/40 " + (t.stale ? "text-muted opacity-60" : "")}>
                  <td className="px-3 py-2 font-mono text-xs text-muted">{i + 1}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1">
                      <StarButton on={watchKeys.has(keyOf(t))} onClick={() => onStar(t)} />
                      <div>
                        <TokenCell t={t} now={now} showAnchor={!watchOnly && board === "streak"} />
                        {tag && <span className="ml-10 font-mono text-[10px] text-clay">{tag}</span>}
                        {t.diverge === 1 && <span className="ml-1 font-mono text-[10px] text-brass">DIVERGE</span>}
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2"><CaCell address={t.address} /></td>
                  <td className="px-3 py-2"><CreatedCell t={t} now={now} /></td>
                  <td className="px-3 py-2"><Sparkline data={t.spark} /></td>
                  <FlashCell value={t.price} armed={t.commitOk && t.chgPrice} className="px-3 py-2 text-right font-mono text-xs">
                    <span title={`价格 ${fmtAge(t.ageSec)}。这不是日K时间`}>${fmtPrice(t.price)}</span>
                  </FlashCell>
                  {columns === "all" && <td className="px-3 py-2 text-right font-mono text-xs">{fmtAge(t.ageSec)}</td>}
                  <td className="px-3 py-2 text-right font-mono text-xs">{fmtUsd(t.marketCap)}</td>
                  <td className={`px-3 py-2 text-right font-mono text-xs ${pctColor(Number(t.pc24h))}`} title="滚动 24 小时，不是 UTC 日K">
                    {t.pc24h == null ? "—" : fmtPct(Number(t.pc24h))}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono text-xs ${pctColor(t.change1d)}`} title={kTitle}>
                    {klineBadge()}{fmtPct(t.change1d)}
                  </td>
                  <td className="px-3 py-2 text-center" title={`${kTitle} 已收盘日K ${t.closedCandles} 根。连涨不受顶部天数按钮影响。`}>
                    {klineBadge()}
                    <span className={"font-mono text-sm " + (t.streak > 0 ? "text-moss font-medium" : "text-muted")}>
                      {t.streak > 0 ? `${t.streak}D` : t.streak}
                    </span>
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono text-xs font-medium ${pctColor(t.changeNd)}`}
                    title={`${days} 根已收盘 UTC 日K区间的累计。不足 ${days} 个完整区间显示 —。`}
                  >
                    {klineBadge()}{fmtPct(t.changeNd)}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono text-xs ${pctColor(t.streakReturn)}`} title={kTitle}>
                    {klineBadge()}{fmtPct(t.streakReturn)}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono text-xs ${drawdownClass(t.streakDrawdown)}`} title={`${kTitle} 超过 40% 仍保留连涨资格`}>
                    {klineBadge()}{fmtDrawdown(t.streakDrawdown)}
                  </td>
                  <FlashCell value={t.volume24h} armed={t.commitOk && t.chgVolume} className="px-3 py-2 text-right font-mono text-xs">
                    {fmtUsd(t.volume24h)}
                  </FlashCell>
                  <FlashCell value={t.liquidity} armed={t.commitOk && t.chgLiquidity} className="px-3 py-2 text-right font-mono text-xs">
                    <span title={`流动性 $${STREAK_MIN_LIQUIDITY.toLocaleString()} 且年龄不超过 ${LIQUIDITY_FRESHNESS_SEC}s 才进正式连涨榜。当前年龄 ${t.liquidityAgeSec == null ? "未知" : `${t.liquidityAgeSec}s`}。`}>
                      {t.stale ? <span className="mr-1 text-[10px] text-clay">stale </span> : null}
                      {fmtUsd(t.liquidity)}
                    </span>
                  </FlashCell>
                  <td className="px-3 py-2 text-right font-mono text-xs">{t.holders != null ? t.holders.toLocaleString() : "—"}</td>
                  {columns === "all" && (
                    <>
                      <td className="px-3 py-2 text-right font-mono text-xs">{anchor == null ? "—" : `$${fmtPrice(anchor)}`}</td>
                      <td className={"px-3 py-2 text-right font-mono text-xs " + (oracleStale ? "text-muted" : "")}>
                        {t.oraclePrice ? `$${fmtPrice(t.oraclePrice)}` : "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-xs">{t.dexPrice ? `$${fmtPrice(t.dexPrice)}` : "—"}</td>
                      <td className={`px-3 py-2 text-right font-mono text-xs ${pctColor(dev)}`}>{fmtPct(dev)}</td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
        {tableRows.length > limit && (
          <button
            type="button"
            onClick={() => setLimit((n) => n + PAGE_ROWS * 2)}
            className="block w-full border-t border-line py-3 text-center text-sm text-muted hover:bg-surface/40 hover:text-fg"
          >
            显示更多（已显示 {limit} / {tableRows.length}）
          </button>
        )}
        {tableRows.length === 0 && !loading && !error && (
          <p className="p-8 text-center text-muted">
            {watchOnly
              ? (watch.length === 0 ? "还没有自选。到市场排行，点代币旁边的星标。" : "没有匹配的自选")
              : board === "streak"
                ? "正式连涨榜没有流动性不低于 $50,000 且年龄不超过 300 秒的代币"
                : data && data.length > 0
                  ? `没有已收盘日K满 ${days + 1} 根的代币，换个更短的天数试试`
                  : "没有数据，先跑采集器"}
          </p>
        )}
      </div>
      <p className="mt-3 text-xs text-muted">
        {watchOnly
          ? "自选存在这台浏览器。点星标加入或移出。名单不看 $50,000 流动性门槛。掉出当前榜的代币留在这里，并标成不在当前榜。默认按加入顺序。"
          : null}
        {watchOnly ? " " : null}
        24H：当前价格相对 24 小时前的滚动涨跌幅。日K：最近一根已收盘 UTC 日K，相对前一根已收盘日K的涨跌幅。连涨：连续多少根已收盘 UTC 日K收盘价高于前一日。{days}D累计：最新已收盘 UTC 日K收盘价，相对 {days} 个完整日线区间前收盘价的累计变化。顶部天数只改 N 日累计和全市场按它的排名。正式连涨榜要求流动性不低于 $50,000，且流动性年龄不超过 300 秒。过期的流动性可以留在全市场表里，但不进入正式连涨排名。回撤超过 40% 只标红，不取消连涨。CA 和 Created 不参与排序。Age 是价格源年龄，不是日 K 年龄。
      </p>
    </div>
  );
}
