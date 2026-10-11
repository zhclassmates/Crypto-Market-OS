import { useEffect, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { Star, EyeOff, X, ArrowUp, ArrowDown } from "lucide-react";
import { fetchUnifiedMarket, fetchUnifiedDetail } from "@/lib/rh/wm-unified-server";
import { loadWatchlist, writeWatchlist, WATCH_EVENT } from "@/lib/rh/watchlist";
import {
  hiddenTokenKey,
  loadHiddenTokens,
  addHiddenToken,
  writeHiddenTokens,
  HIDDEN_TOKENS_EVENT,
} from "@/lib/rh/hidden-tokens";
import { formatCompactUsd } from "@/lib/rh/daily-filter";
import { formatUnifiedDailyReturn, cycleDateSort, historyGapLabel, seedDefaultWatch } from "@/lib/rh/wm-unified-display";
import type { UnifiedQuery } from "@/lib/rh/wm-unified-query";
const parse = (v: unknown) => {
  try {
    return JSON.parse(String(v ?? "[]"));
  } catch {
    return [];
  }
};
const priceUsd = (v: unknown) =>
  v == null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumSignificantDigits: 6,
      }).format(Number(v));
const usd = (v: unknown) => (v == null ? "—" : Math.abs(Number(v)) >= 1e15 ? "$"+Number(v).toExponential(3) : formatCompactUsd(Number(v)));
export function WmUnifiedMarket({ watchOnly = false }: { watchOnly?: boolean }) {
  const fetch = useServerFn(fetchUnifiedMarket),
    detailFn = useServerFn(fetchUnifiedDetail);
  const [data, setData] = useState<Awaited<ReturnType<typeof fetch>> | null>(null);
  const [query, setQuery] = useState<UnifiedQuery>({
    page: 1,
    sort: "market_cap",
    direction: "desc",

  });
  const [search, setSearch] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [localVersion, setLocalVersion] = useState(0),
    [hiddenMode, setHiddenMode] = useState<"exclude"|"all"|"only">("exclude"),
    [onlyWatch, setOnlyWatch] = useState(watchOnly);
  const [watch, setWatch] = useState<string[]>([]),
    [hidden, setHidden] = useState<string[]>([]);
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof detailFn>> | null>(null),
    [detailBusy, setDetailBusy] = useState(false),
    [detailId, setDetailId] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setQuery((q) => ({ ...q, search, page: 1 })), 250);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    const update = () => {
      setWatch(loadWatchlist(localStorage).map((w) => hiddenTokenKey(w.chain, w.address)));
      setHidden(loadHiddenTokens(localStorage));
      setLocalVersion((n) => n + 1);
    };
    update();
    window.addEventListener(WATCH_EVENT, update);
    window.addEventListener(HIDDEN_TOKENS_EVENT, update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener(WATCH_EVENT, update);
      window.removeEventListener(HIDDEN_TOKENS_EVENT, update);
      window.removeEventListener("storage", update);
    };
  }, []);
  useEffect(() => {
    let cancelled = false;
    async function pull() {
      setBusy(true);
      try {
        const result = await fetch({
          data: {
            ...query,
            identity:query.identity as "VERIFIED_MAPPING"|"CONTRACT_MATCH"|"VERIFIED_CONTRACT"|"UNRESOLVED"|undefined,
            source: query.source as "cg" | "cmc" | "dex" | "gmgn" | undefined,
            quality: query.quality as "VALID" | "PARTIAL" | "CONFLICT" | "BLOCKED" | undefined,
            direction: query.direction as "asc" | "desc",
            hiddenKeys: hiddenMode === "exclude" ? hidden : [],
            onlyHiddenKeys: hiddenMode === "only" ? hidden : undefined,
            watchKeys: onlyWatch ? watch : undefined,
          },
        });
        if (!cancelled) {
          setData(result);
          if (seedDefaultWatch(localStorage,result.defaultWatch)) window.dispatchEvent(new Event(WATCH_EVENT));
          setError("");
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setBusy(false);
      }
    }
    pull();
    const timer = setInterval(pull, 60000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [fetch, query, localVersion, hiddenMode, onlyWatch]);
  function sort(field: string) {
    setQuery((q) => ({
      ...q,
      page: 1,
      sort: field,
      dates: [],
      direction: q.sort === field && q.direction === "desc" ? "asc" : "desc",
    }));
  }
  function sortDate(date: string) {
    setQuery(q=>({...q,page:1,dates:cycleDateSort(q.dates??[],date)}));
  }
  async function openDetail(id: string) {
    setDetailId(id);
    setDetail(null);
    setDetailBusy(true);
    try {
      setDetail(await detailFn({ data: { id } }));
    } catch (e) {
      setError(String(e));
    } finally {
      setDetailBusy(false);
    }
  }
  function star(r: {
    contracts: string;
    canonical_asset_id: string;
    preference_aliases: string;
    name: string | null;
    symbol: string | null;
  }) {
    const items = loadWatchlist(localStorage);
    const keys = new Set(
      [r.canonical_asset_id, ...parse(r.preference_aliases)].map((id: string) => "unified:" + id),
    );
    for (const t of parse(r.contracts) as { chain_id: string; contract_address: string }[]) {
      const chain =
        ({ ethereum: "eth", solana: "sol", robinhood: "rh" } as Record<string, string>)[
          t.chain_id
        ] ?? t.chain_id;
      keys.add(hiddenTokenKey(chain, t.contract_address));
    }
    const next = isStar(r)
      ? items.filter((w) => !keys.has(hiddenTokenKey(w.chain, w.address)))
      : [
          ...items,
          {
            chain: "unified",
            address: r.canonical_asset_id,
            name: r.name,
            symbol: r.symbol,
            addedAt: Date.now(),
          },
        ];
    writeWatchlist(localStorage, next);
    window.dispatchEvent(new Event(WATCH_EVENT));
  }
  function isStar(r: {
    contracts: string;
    canonical_asset_id: string;
    preference_aliases: string;
  }) {
    return (
      [r.canonical_asset_id, ...parse(r.preference_aliases)].some((id: string) =>
        watch.includes("unified:" + id),
      ) ||
      (parse(r.contracts) as { chain_id: string; contract_address: string }[]).some((t) =>
        watch.includes(
          hiddenTokenKey(
            ({ ethereum: "eth", solana: "sol", robinhood: "rh" } as Record<string, string>)[
              t.chain_id
            ] ?? t.chain_id,
            t.contract_address,
          ),
        ),
      )
    );
  }
  function preferenceKeys(r: {canonical_asset_id:string;preference_aliases:string;contracts:string}) {
    return [r.canonical_asset_id,...parse(r.preference_aliases)].map(id=>"unified:"+id).concat(
      parse(r.contracts).map((t:{chain_id:string;contract_address:string})=>hiddenTokenKey(
        ({ethereum:"eth",solana:"sol",robinhood:"rh"} as Record<string,string>)[t.chain_id]??t.chain_id,t.contract_address)));
  }
  function isHidden(r: Parameters<typeof preferenceKeys>[0]) {return preferenceKeys(r).some(key=>hidden.includes(key));}
  function restore(r: Parameters<typeof preferenceKeys>[0]) {
    const keys=new Set(preferenceKeys(r));writeHiddenTokens(localStorage,loadHiddenTokens(localStorage).filter(key=>!keys.has(key)));
    window.dispatchEvent(new Event(HIDDEN_TOKENS_EVENT));
  }
  function hide(id: string) {
    writeHiddenTokens(localStorage, addHiddenToken(loadHiddenTokens(localStorage), "unified", id));
    window.dispatchEvent(new Event(HIDDEN_TOKENS_EVENT));
  }
  const stats = data?.stats;
  const selectClass = "min-h-11 rounded-lg border border-line bg-bg px-3 text-xs text-fg";
  return (
    <section className="mb-6 rounded-xl border border-line bg-surface" data-unified-market aria-busy={busy}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line p-4">
        <div>
          <h2 className="text-lg font-semibold text-fg">全市场排行 · CG + CMC + DEX + GMGN</h2>
          <p className="mt-1 text-xs text-muted">
            按可信身份合并 · 资产级总量与链上池数据分开 · 每页 50 条
          </p>
        </div>
        <span className="font-mono text-xs text-muted">
          最新整合 UTC {stats?.synced_at?.slice(0, 19).replace("T", " ") ?? "—"}
        </span>
      </div>
      {stats && (
        <div className="grid grid-cols-2 gap-3 border-b border-line p-4 md:grid-cols-4 xl:grid-cols-8">
          {[
            ["CG 已收录", stats.cg],
            ["CMC 已收录", stats.cmc],
            ["DEX 原始", stats.dex],
            ["GMGN 代币", stats.gmgn],
            ["唯一资产", stats.unique_assets],
            ["链级代币", stats.chain_tokens],
            ["多源匹配", stats.multi_source_matches],
            ["身份待确认", stats.unresolved],
            ["字段冲突", stats.field_conflicts],
          ].map(([k, v]) => (
            <div key={String(k)}>
              <div className="text-xs text-muted">{k}</div>
              <div className="mt-1 font-mono text-lg text-fg">{Number(v).toLocaleString()}</div>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-2 p-4">
        <input
          aria-label="统一市场搜索"
          placeholder="名称 / Symbol / 合约地址"
          className={selectClass + " w-full sm:w-64"}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="统一链筛选"
          className={selectClass}
          value={query.chain ?? ""}
          onChange={(e) => setQuery((q) => ({ ...q, chain: e.target.value || undefined, page: 1 }))}
        >
          <option value="">全部链</option>
          {["bitcoin", "ethereum", "solana", "base", "bsc", "robinhood"].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <select
          aria-label="统一来源筛选"
          className={selectClass}
          value={query.source ?? ""}
          onChange={(e) =>
            setQuery((q) => ({ ...q, source: e.target.value || undefined, page: 1 }))
          }
        >
          <option value="">全部来源</option>
          {["cg", "cmc", "dex", "gmgn"].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <select
          aria-label="统一质量筛选"
          className={selectClass}
          value={query.quality ?? ""}
          onChange={(e) =>
            setQuery((q) => ({ ...q, quality: e.target.value || undefined, page: 1 }))
          }
        >
          <option value="">全部质量</option>
          {["VALID", "PARTIAL", "CONFLICT", "BLOCKED"].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <select aria-label="统一身份筛选" className={selectClass} value={query.identity??""}
          onChange={e=>setQuery(q=>({...q,identity:e.target.value||undefined,page:1}))}>
          <option value="">全部身份</option>
          {["VERIFIED_MAPPING","CONTRACT_MATCH","VERIFIED_CONTRACT","UNRESOLVED"].map(x=><option key={x}>{x}</option>)}
        </select>
        <details className="rounded-lg border border-line p-3 text-xs text-muted">
          <summary className="cursor-pointer">金额 / 币龄区间</summary>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {([
            ["市值","minMarketCap","maxMarketCap"], ["成交量","minVolume","maxVolume"],
            ["流动性","minLiquidity","maxLiquidity"], ["币龄（天）","minAgeDays","maxAgeDays"],
          ] as const).map(([label,lower,upper])=><div key={lower} className="flex flex-wrap items-center gap-2">
            <span>{label}</span>
            {[lower,upper].map((key,i)=><input key={key} type="number" min="0" step="any" aria-label={`${label}${i===0?"下限":"上限"}`} placeholder={i===0?"下限":"上限"}
              value={query[key]??""} className={selectClass+" w-24"}
              onChange={e=>{const value=e.target.valueAsNumber;setQuery(q=>({...q,[key]:Number.isFinite(value)&&value>=0?value:undefined,page:1}));}} />)}
          </div>)}
          </div>
          <p className="mt-2">币龄仅按真实创建时间；未知币龄不符合区间筛选，未筛选时正常展示。</p>
        </details>
        <button
          className={selectClass}
          aria-pressed={onlyWatch}
          onClick={() => {
            setOnlyWatch(!onlyWatch);
            setQuery((q) => ({ ...q, page: 1 }));
          }}
        >
          星标 {onlyWatch ? "✓" : ""}
        </button>
        <select aria-label="隐藏代币筛选" className={selectClass} value={hiddenMode}
          onChange={e=>{setHiddenMode(e.target.value as typeof hiddenMode);setQuery(q=>({...q,page:1}));}}>
          <option value="exclude">不显示已隐藏</option><option value="all">显示全部（含隐藏）</option><option value="only">仅看已隐藏</option>
        </select>
        <select aria-label="统一分层筛选" className={selectClass} value={query.tier??""}
          onChange={e=>setQuery(q=>({...q,tier:e.target.value as UnifiedQuery["tier"]||undefined,page:1}))}>
          <option value="">全部分层</option><option value="NEW">NEW · 今日首次收录</option>
          <option value="EARLY">EARLY · 流动性 ≥ $20k</option><option value="MAIN">MAIN · 原有晋级口径</option>
        </select>
        {hiddenMode !== "exclude" && hidden.length>0 && <button className={selectClass} onClick={()=>{
          writeHiddenTokens(localStorage,[]);window.dispatchEvent(new Event(HIDDEN_TOKENS_EVENT));
        }}>恢复本机隐藏 ({hidden.length})</button>}
        {query.dates?.length || query.dailyFilters?.length ? (
          <button
            className={selectClass}
            onClick={() => setQuery((q) => ({ ...q, dates: [], dailyFilters: [], page: 1 }))}
          >
            清除日期排序 / 筛选
          </button>
        ) : null}
      </div>
      <p className="px-4 pb-3 text-xs text-muted">
        日期点击：默认 → ↑ 涨幅最高 → ↓ 涨幅最低 → 默认；可直接同时选多列，最近点击优先；下拉涨跌条件为 AND 组合筛选。
        后端先筛选全市场，再数值排序、分页；缺失值始终置后。仅相邻同源 UTC 日终价计算涨跌幅，当天未收盘显示 —。
        DEX 流动性为最大返回池，GMGN 为链级报告值；成交量口径以字段来源为准。
        {query.quality === "VALID"
          ? " 当前为研究级筛选口径：仅显示来源可信、身份已确认且核心报价字段可用的 VALID 记录。七日历史完整度独立判断，缺失日期仍显示 —；切「全部质量」可查看含 GMGN 战壕新币在内的 PARTIAL 记录。"
          : " 默认展示全部真实已收录资产。当前包含 PARTIAL/未交叉验证记录：GMGN 战壕新币的极端价格或市值为源端原始报告值，不代表可信，决策请以 VALID 为准。"}
        {stats?.identity_conflicts
          ? ` 同合约多官方 ID 冲突 ${stats.identity_conflicts} 项，详情可追溯。`
          : ""}
      </p>
      <p className="px-4 pb-3 text-xs text-muted">
        DEX 原始采集为 2 条观察清单，不代表全市场完整覆盖。
        {stats?.onchain_audit?.dex_auxiliary_records ? ` 另保留 ${Number(stats.onchain_audit.dex_auxiliary_records).toLocaleString()} 条本地 DEX 辅助记录，缺报价时间，不用于可靠历史或主值。` : ""}
      </p>
      {error && (
        <p role="alert" className="px-4 py-3 text-negative">
          统一数据读取失败：{error}
        </p>
      )}
      <p className="px-4 pb-3 text-xs text-muted">日历终点：{data?.windowEndUtc??"—"} UTC（已收盘）；已采集日终数据终点：{data?.latestFinalizedDate??"—"} UTC。报价更新时间见各行，整合时间不代表实时报价。</p>
      <div className="overflow-x-auto" data-unified-scroll>
        <table className="w-full text-left text-xs">
          <thead className="border-y border-line text-muted">
            <tr>
              <th className="sticky left-0 z-20 w-44 min-w-44 max-w-44 bg-surface p-3">Token</th>
              <th className="sticky left-44 z-20 w-12 min-w-12 bg-surface p-2">Star</th>
              <th className="p-3">Chain</th>
              {[
                ["Price", "price_usd"],
                ["MC", "market_cap"],
                ["FDV", "fdv"],
                ["Volume · 24h", "volume_24h"],
                ["Liquidity · 链/池", "liquidity_usd"],
              ].map(([label, field]) => (
                <th key={field} className="p-3 whitespace-nowrap">
                  <button onClick={() => sort(field)}>
                    {label}{" "}
                    {query.sort === field && !query.dates?.length ? (
                      query.direction === "desc" ? (
                        <ArrowDown className="inline size-3" />
                      ) : (
                        <ArrowUp className="inline size-3" />
                      )
                    ) : null}
                  </button>
                </th>
              ))}
              {data?.dates.map((d, i) => (
                <th key={d} className="p-3 whitespace-nowrap">
                  <button aria-label={`${d} 涨跌幅排序`} data-sort-date={d} data-sort-direction={query.dates?.find(x=>x.date===d)?.direction??"none"} className="min-h-11" onClick={() => sortDate(d)}>
                    {`T${i === 6 ? "0" : i - 6}`}{" "}
                    {query.dates?.findIndex((x) => x.date === d) !== undefined && query.dates.findIndex((x) => x.date === d) >= 0
                      ? `${query.dates.findIndex((x) => x.date === d) + 1}${query.dates.find((x) => x.date === d)?.direction === "desc" ? "↑" : "↓"}`
                      : ""}
                    <span className="block font-normal">{d} UTC</span>
                    <span className="block font-normal text-muted">有效 {data.participation.find(x=>x.date===d)?.valid.toLocaleString()??0}</span>
                  </button>
                  <select
                    aria-label={`${d} 涨跌筛选`}
                    className="mt-1 rounded border border-line bg-bg text-fg"
                    value={query.dailyFilters?.find((f) => f.date === d)?.sign ?? ""}
                    onChange={(e) =>
                      setQuery((q) => ({
                        ...q,
                        page: 1,
                        dailyFilters: [
                          ...(q.dailyFilters ?? []).filter((f) => f.date !== d),
                          ...(e.target.value
                            ? [{ date: d, sign: e.target.value as "positive" | "negative" }]
                            : []),
                        ],
                      }))
                    }
                  >
                    <option value="">全部</option>
                    <option value="positive">上涨</option>
                    <option value="negative">下跌</option>
                  </select>
                </th>
              ))}
              <th className="p-3">Sources</th>
              <th className="p-3">Quality / Tier</th>
              <th className="p-3">Updated · UTC</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows.map((r) => (
              <tr
                key={String(r.canonical_asset_id)}
                data-unified-asset={String(r.canonical_asset_id)}
                className="border-b border-line/60"
              >
                <td className="sticky left-0 z-10 w-44 min-w-44 max-w-44 bg-surface p-3">
                  <div className="flex items-center gap-2">
                    <button
                      className="min-h-11 text-left"
                      onClick={() => openDetail(String(r.canonical_asset_id))}
                    >
                      <strong className="block text-fg">
                        {String(r.symbol ?? "—").toUpperCase()}
                      </strong>
                      <span className="block max-w-28 truncate text-muted">{String(r.name ?? "—")}</span>
                      <span className="block text-muted">{parse(r.chains).join(" / ")||"链未知"}</span>
                      {r.identity_confidence==="UNRESOLVED"?<span className="block text-muted">身份待确认</span>:null}
                      <span className="block text-muted">{r.quality_status}</span>
                      {parse(r.contracts)[0]?.contract_address ? <span className="block font-mono text-muted" title={parse(r.contracts)[0].contract_address}>{parse(r.contracts)[0].contract_address.slice(0,5)}…{parse(r.contracts)[0].contract_address.slice(-4)}</span> : null}
                    </button>
                    <button
                      aria-label={`${isHidden(r) ? "恢复" : "隐藏"} ${r.symbol}`}
                      className="min-h-11 text-muted"
                      onClick={() => isHidden(r) ? restore(r) : hide(String(r.canonical_asset_id))}
                    >
                      <EyeOff className="size-3" />
                    </button>
                  </div>
                </td>
                <td className="sticky left-44 z-10 w-12 min-w-12 bg-surface p-2">                    <button
                      aria-label={`星标 ${r.symbol}`} aria-pressed={isStar(r)}
                      className="min-h-11 min-w-11"
                      onClick={() => star(r)}
                    >
                      <Star
                        className={
                          "size-4 " + (isStar(r) ? "fill-primary text-primary" : "text-muted")
                        }
                      />
                    </button>
</td>
                <td className="p-3">{parse(r.chains).join(", ") || "—"}</td>
                {["price_usd", "market_cap", "fdv", "volume_24h", "liquidity_usd"].map((f) => (
                  <td
                    key={f}
                    className="p-3 font-mono whitespace-nowrap"
                    title={parse(r.selection_json)[f]?.source ?? "缺失"}
                  >
                    {f === "price_usd" ? priceUsd(r.price_usd) : usd(r[f as keyof typeof r])}
                    {f !== "price_usd" && parse(r.selection_json)[f]?.provider === "gmgn" ? <span className="block text-muted">链级报告</span> : null}
                    {f === "price_usd" && r.primary_source === "dex" ? (
                      <span className="block text-muted">池价</span>
                    ) : null}
                  </td>
                ))}
                {data.dates.map((d) => {
                  const h = r.history.find((x) => x.date_utc === d);
                  return (
                    <td
                      key={d} data-history-date={d} data-daily-return={h?.daily_return??""}
                      className="p-3 font-mono whitespace-nowrap"
                      title={
                        h
                          ? `${h.provider}:${h.provider_id} · ${h.time_basis} · ${h.data_timestamp} · ${h.return_quality??""}`
                          : historyGapLabel(r.first_seen_utc,d)
                      }
                    >
                      <span className="block">
                        {h?.daily_return == null
                          ? "—"
                          : formatUnifiedDailyReturn(Number(h.daily_return))}
                      </span>
                      <span className="text-muted">
                        {h
                          ? `${priceUsd(h.price_usd)}${h.time_basis === "utc_finalized" ? " 日终" : " 盘中"}`
                          : "—"}
                      </span>
                    </td>
                  );
                })}
                <td className="p-3 font-mono">{parse(r.source_list).join(" + ").toUpperCase()}</td>
                <td className="p-3">
                  <span
                    className={r.quality_status === "CONFLICT" ? "text-negative" : "text-muted"}
                  >
                    {String(r.quality_status)}
                  </span>
                  <span className="mt-1 block text-muted">{String(r.identity_confidence)}</span>
                  <span className="block text-muted">{r.is_new ? "NEW · " : ""}{r.market_tier}</span>
                </td>
                <td className="p-3 font-mono whitespace-nowrap" title="采用报价的真实来源时间；不代表实时">
                  {r.data_timestamp ? <><span className="block">{r.data_timestamp.slice(0,19).replace("T"," ")}</span><span className="block text-muted">{Math.max(0,Math.floor((Date.now()-Date.parse(r.data_timestamp))/3600000))} 小时前</span></> : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!data && !error && <p className="p-6 text-muted">正在读取统一市场…</p>}
      {data && !data.rows.length && <p className="p-6 text-muted">没有符合筛选条件的资产。</p>}
      <div className="flex items-center justify-between gap-3 p-4 text-xs text-muted">
        <span>
          {busy ? "更新中 · " : ""}
          {data?.total.toLocaleString() ?? "—"} 条 · 第 {data?.page ?? 1} 页
        </span>
        <div className="flex gap-2">
          <button
            className={selectClass}
            disabled={!data || data.page <= 1 || busy}
            onClick={() => setQuery((q) => ({ ...q, page: (data?.page ?? 1) - 1 }))}
          >
            上一页
          </button>
          <button
            className={selectClass}
            disabled={!data || data.page * 50 >= data.total || busy}
            onClick={() => setQuery((q) => ({ ...q, page: (data?.page ?? 1) + 1 }))}
          >
            下一页
          </button>
        </div>
      </div>
      {detailId && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-bg/80"
          onClick={() => setDetailId("")}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-label="统一资产详情"
            className="h-full w-full max-w-3xl overflow-y-auto border-l border-line bg-surface p-4 text-xs"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg text-fg">资产来源、采用结果与历史</h3>
              <button
                aria-label="关闭统一详情"
                className="min-h-11 p-3"
                onClick={() => setDetailId("")}
              >
                <X />
              </button>
            </div>
            <p className="break-all py-3 font-mono text-muted">{detailId}</p>
            {detail?.current && (
              <p className="mb-3 text-muted">
                记录质量：{String((detail.current as Record<string, unknown>).quality_status)} ·
                缺失字段：
                {parse((detail.current as Record<string, unknown>).missing_fields).join(", ") ||
                  "无"}
              </p>
            )}
            {detailBusy ? (
              <p>读取中…</p>
            ) : (
              detail && (
                <>
                  <h4 className="my-3 font-semibold">字段采用结果与理由</h4>
                  <p className="px-4 pb-3 text-xs text-muted">日历终点：{data?.windowEndUtc??"—"} UTC（已收盘）；已采集日终数据终点：{data?.latestFinalizedDate??"—"} UTC。报价更新时间见各行，整合时间不代表实时报价。</p>
      <div className="overflow-x-auto" data-unified-scroll>
                    <table className="w-full">
                      <tbody>
                        {Object.entries(
                          parse(
                            (detail.current as Record<string, unknown>)?.selection_json,
                          ) as Record<string, Record<string, unknown>>,
                        ).map(([f, s]) => (
                          <tr key={f} className="border-b border-line">
                            <td className="p-2">{f}</td>
                            <td className="p-2">{s.value == null ? "—" : String(s.value)}</td>
                            <td className="p-2">
                              {String(s.source ?? "—")}
                              <span className="block text-muted">{String(s.timestamp ?? "")}</span>
                              <span className="block text-muted">{String(s.reason)}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {[
                    ["来源身份与依据", detail.mappings],
                    ["字段冲突 / 非同步窗口", detail.conflicts],
                    [
                      "原始来源数值（保留版本）",
                      detail.raw.map((r) => ({ ...r, payload_json: parse(r.payload_json) })),
                    ],
                    ["统一 UTC 历史", detail.history],
                    [
                      "DEX 返回池口径",
                      parse((detail.current as Record<string, unknown>)?.pool_data_json),
                    ],
                  ].map(([label, rows]) => (
                    <details
                      key={String(label)}
                      open={label === "字段冲突 / 非同步窗口"}
                      className="my-3 rounded border border-line p-3"
                    >
                      <summary className="cursor-pointer font-medium">{String(label)}</summary>
                      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs text-muted">
                        {JSON.stringify(rows, null, 2)}
                      </pre>
                    </details>
                  ))}
                </>
              )
            )}
          </section>
        </div>
      )}
    </section>
  );
}
