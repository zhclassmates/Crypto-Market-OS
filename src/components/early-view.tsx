import { useEffect, useMemo, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { ArrowDown, ArrowUp, RefreshCw, Search } from "lucide-react";
import { fetchMarketEarly, type EarlyToken } from "@/lib/rh/market-server";
import type { MarketInclusionStats, MarketTierStats } from "@/lib/rh/market-stats";
import { EARLY_MIN_LIQUIDITY, MAIN_MIN_LIQUIDITY } from "@/lib/rh/market-stats";
import { fmtRelativeAge } from "@/lib/rh/streak";
import { MARKET_CHAIN_LABEL, MARKET_CHAIN_TABS } from "@/lib/rh/market-chains";

type SortKey = "liquidity" | "volume24h" | "createdAt";

const CHAIN_BADGE: Record<string, string> = {
  sol: "bg-[#9945FF]", robinhood: "bg-[#00C805]", base: "bg-[#0052FF]", eth: "bg-[#627EEA]", bsc: "bg-[#F0B90B]",
};
const REFRESH_MS = 60_000;
const PAGE_ROWS = 100;

function fmtUsd(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

function fmtPrice(v: string | null): string {
  const n = v == null || v === "" ? NaN : Number(v);
  if (!Number.isFinite(n)) return "—";
  if (n >= 1) return `$${n.toFixed(4)}`;
  return `$${n.toPrecision(4)}`;
}

function fmtInt(n: number | null): string {
  return n == null ? "—" : n.toLocaleString();
}

function fmtPct(v: string | null): { text: string; cls: string } {
  const n = v == null || v === "" ? NaN : Number(v);
  if (!Number.isFinite(n)) return { text: "—", cls: "text-muted" };
  const pct = n; // token_snapshot.pc_24h 原样是百分数（rank 接口才 /100）
  return { text: `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`, cls: pct > 0 ? "text-moss" : pct < 0 ? "text-clay" : "text-muted" };
}

function liqDelta(t: EarlyToken): { text: string; cls: string; title: string } {
  if (t.liquidity24hAgo == null || t.liquidity24hAgo <= 0) {
    return { text: "—", cls: "text-muted", title: "约 24 小时前没有带流动性的 discovery 记录" };
  }
  const d = t.liquidity / t.liquidity24hAgo - 1;
  return {
    text: `${d > 0 ? "+" : ""}${(d * 100).toFixed(0)}%`,
    cls: d > 0 ? "text-moss" : d < 0 ? "text-clay" : "text-muted",
    title: `约 24h 前 ${fmtUsd(t.liquidity24hAgo)} → 现在 ${fmtUsd(t.liquidity)}`,
  };
}

function Logo({ logo, symbol }: { logo: string | null; symbol: string | null }) {
  const [ok, setOk] = useState(true);
  if (logo && ok) {
    return <img src={logo} alt="" className="h-6 w-6 shrink-0 rounded-full bg-surface-2 object-cover" loading="lazy" onError={() => setOk(false)} />;
  }
  return (
    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-2 font-mono text-[10px] text-muted">
      {(symbol || "?").slice(0, 2)}
    </span>
  );
}

/** EARLY 观察池：$20k ≤ 当前流动性 < $50k。只展示事实，不打分、不进正式榜。 */
export function EarlyView() {
  const earlyFn = useServerFn(fetchMarketEarly);
  const [tokens, setTokens] = useState<EarlyToken[] | null>(null);
  const [inclusion, setInclusion] = useState<MarketInclusionStats | null>(null);
  const [tiers, setTiers] = useState<MarketTierStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [chain, setChain] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("liquidity");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [limit, setLimit] = useState(PAGE_ROWS);
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));

  async function load() {
    setLoading(true);
    setError("");
    try {
      const res = await earlyFn({ data: {} });
      if (!res.ok) {
        setError(res.error || "拉取失败");
      } else {
        setTokens(res.tokens);
        setInclusion(res.inclusionStats ?? null);
        setTiers(res.tierStats ?? null);
      }
      setNow(Math.floor(Date.now() / 1000));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), REFRESH_MS);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = (tokens ?? []).filter((t) => {
      if (chain !== "all" && t.chain !== chain) return false;
      if (!q) return true;
      return (t.symbol ?? "").toLowerCase().includes(q)
        || (t.name ?? "").toLowerCase().includes(q)
        || t.address.toLowerCase().includes(q);
    });
    const sign = sortDir === "desc" ? -1 : 1;
    return [...list].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return (av - bv) * sign;
    });
  }, [tokens, chain, search, sortKey, sortDir]);

  function toggleSort(k: SortKey) {
    if (sortKey === k) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else {
      setSortKey(k);
      setSortDir("desc");
    }
  }

  const SortTh = ({ k, label, title }: { k: SortKey; label: string; title?: string }) => (
    <th onClick={() => toggleSort(k)} title={title} className="cursor-pointer whitespace-nowrap px-3 py-2 text-right font-mono text-xs hover:text-fg">
      <span className="inline-flex flex-row-reverse items-center gap-1">
        {label}
        {sortKey === k ? (sortDir === "desc" ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />) : null}
      </span>
    </th>
  );
  const Th = ({ label, title }: { label: string; title?: string }) => (
    <th title={title} className="whitespace-nowrap px-3 py-2 text-right font-mono text-xs">{label}</th>
  );

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6" id="sec-early">
      <div className="mb-4">
        <h2 className="text-lg font-medium">早期观察 · EARLY</h2>
        <p className="mt-1 max-w-2xl text-sm text-pretty text-muted">
          当前流动性 ${EARLY_MIN_LIQUIDITY.toLocaleString()} – ${MAIN_MIN_LIQUIDITY.toLocaleString()}，还没进过正式榜的币。
          只列快照事实，不打分、不拉日K。流动性一旦观测到 ≥ ${MAIN_MIN_LIQUIDITY.toLocaleString()}，下一轮自动进入 MAIN。
        </p>
      </div>

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
        {MARKET_CHAIN_TABS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setChain(c)}
            className={"min-h-9 rounded-full border px-3 text-sm " + (chain === c ? "border-brass text-fg" : "border-line text-muted")}
          >
            {MARKET_CHAIN_LABEL[c]}
          </button>
        ))}
        <p className="ml-auto flex flex-wrap gap-x-3 font-mono text-xs text-muted" data-testid="tier-stats">
          {inclusion ? <span>总收录 <span className="text-fg">{inclusion.totalTokens.toLocaleString()}</span></span> : null}
          {tiers ? (
            <>
              <span>MAIN <span className="text-fg">{tiers.mainTokens.toLocaleString()}</span></span>
              <span>EARLY <span className="text-brass">{tiers.earlyTokens.toLocaleString()}</span></span>
            </>
          ) : null}
        </p>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-1 rounded-full border border-line px-3 py-1.5 text-sm text-muted hover:text-fg disabled:opacity-50"
        >
          <RefreshCw className={"size-4 " + (loading ? "animate-spin" : "")} />
          刷新
        </button>
      </div>

      {error && <p className="mb-3 rounded-lg border border-clay/30 bg-clay/10 p-3 text-sm text-clay">{error}</p>}

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-left text-sm" data-testid="early-table">
          <thead>
            <tr className="border-b border-line bg-surface-2 text-xs text-muted">
              <th className="px-3 py-2 font-mono">#</th>
              <th className="px-3 py-2 font-mono">Token</th>
              <th className="px-3 py-2 font-mono">Chain</th>
              <Th label="Price" />
              <Th label="24H" title="GMGN 24h 价格涨跌" />
              <SortTh k="liquidity" label="Liquidity" />
              <Th label="Liq 24H" title="对比约 24 小时前 discovery_event 记录的流动性" />
              <SortTh k="volume24h" label="24H Volume" />
              <Th label="Buy" title="24h 买入笔数（不是人数）" />
              <Th label="Sell" title="24h 卖出笔数（不是人数）" />
              <Th label="Txns" title="GMGN swaps 笔数" />
              <Th label="Holders" title="GMGN holder_count；没有来源时为 —" />
              <SortTh k="createdAt" label="Created" title="代币创建时间（缺失时用池子创建时间）" />
              <Th label="距 MAIN" title={`${MAIN_MIN_LIQUIDITY.toLocaleString()} − 当前流动性`} />
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((t, i) => {
              const pc = fmtPct(t.pc24h);
              const ld = liqDelta(t);
              const liqAge = t.liquidityUpdatedAt == null ? null : now - t.liquidityUpdatedAt;
              return (
                <tr key={`${t.chain}:${t.address}`} className="border-b border-line/50 last:border-b-0 hover:bg-surface-2/50">
                  <td className="px-3 py-2 font-mono text-xs text-muted">{i + 1}</td>
                  <td className="px-3 py-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <Logo logo={t.logo} symbol={t.symbol} />
                      <div className="min-w-0">
                        <p className="max-w-32 truncate text-sm font-medium" title={t.name ?? undefined}>{t.symbol || "?"}</p>
                        <p className="font-mono text-[10px] text-muted" title={t.address}>{t.address.slice(0, 4)}…{t.address.slice(-4)}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1.5 font-mono text-xs">
                      <span className={`h-2 w-2 rounded-full ${CHAIN_BADGE[t.chain] || "bg-muted"}`} />
                      {MARKET_CHAIN_LABEL[t.chain] ?? t.chain}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{fmtPrice(t.price)}</td>
                  <td className={`px-3 py-2 text-right font-mono text-xs ${pc.cls}`}>{pc.text}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs" title={liqAge == null ? "没有流动性时间" : `更新于 ${fmtRelativeAge(now, t.liquidityUpdatedAt!)} 前`}>
                    {fmtUsd(t.liquidity)}
                    {liqAge != null && liqAge > 86_400 ? <span className="ml-1 text-clay">旧</span> : null}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono text-xs ${ld.cls}`} title={ld.title}>{ld.text}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{fmtUsd(t.volume24h)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-moss">{fmtInt(t.buys24h)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-clay">{fmtInt(t.sells24h)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{fmtInt(t.swaps24h)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{fmtInt(t.holders)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-muted">
                    {t.createdAt == null ? "—" : fmtRelativeAge(now, t.createdAt)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-brass">{fmtUsd(t.toMain)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length > limit && (
          <button
            type="button"
            onClick={() => setLimit((l) => l + PAGE_ROWS)}
            className="block w-full border-t border-line py-3 text-sm text-muted hover:text-fg"
          >
            显示更多（已显示 {limit} / {rows.length}）
          </button>
        )}
        {rows.length === 0 && !loading && !error && (
          <p className="p-6 text-center text-sm text-muted">{tokens == null ? "加载中…" : "没有 EARLY 代币"}</p>
        )}
      </div>
    </div>
  );
}
