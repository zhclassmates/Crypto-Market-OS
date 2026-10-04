import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useServerFn } from "@tanstack/react-start";
import { ExternalLink, RefreshCw } from "lucide-react";
import { fetchAccessFeed, fetchAccessHealth } from "@/lib/rh/access-server";
import {
  ACCESS_INIT_HINT,
  EVENT_CATEGORIES,
  FEED_WINDOWS,
  HEALTH_LABEL,
  TZ_LABEL,
  filterEvents,
  fmtAgeMs,
  fmtAgo,
  fmtTs8,
  fmtTs8Full,
  eventQuotes,
  groupEventsByAsset,
  statusLabel,
  type AccessEvent,
  type EventCategory,
  type FeedWindow,
  type HealthLevel,
  type Tone,
} from "@/lib/rh/access-core";
import { MARKET_CHAIN_LABEL, MARKET_CHAIN_TABS } from "@/lib/rh/market-chains";
import { TokenDetailDrawer, fmtUsdN } from "@/components/token-detail";

const REFRESH_MS = 60_000;

type FeedResult = Awaited<ReturnType<typeof fetchAccessFeed>>;
type HealthResult = Awaited<ReturnType<typeof fetchAccessHealth>>;

const TONE_TEXT: Record<Tone, string> = {
  up: "text-moss",
  down: "text-clay",
  warn: "text-brass",
  muted: "text-muted",
};

const TONE_BADGE: Record<Tone, string> = {
  up: "border-moss/40 text-moss",
  down: "border-clay/40 text-clay",
  warn: "border-brass/40 text-brass",
  muted: "border-line text-muted",
};

const LEVEL_DOT: Record<HealthLevel, string> = {
  healthy: "bg-moss",
  degraded: "bg-brass",
  stale: "bg-clay",
  down: "bg-clay",
  off: "bg-line",
};

function Badge({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center rounded-full border px-1.5 font-mono text-[10px] leading-4 ${TONE_BADGE[tone]}`}>
      {children}
    </span>
  );
}

function InitHint({ reason }: { reason: string | null }) {
  return (
    <div className="rounded-xl border border-line p-8 text-center">
      <p className="text-sm">Access Radar 还没有数据</p>
      <p className="mt-1 text-xs text-muted">{reason ?? "库未初始化"}</p>
      <p className="mt-4 text-xs text-muted">先在仓库根目录跑一轮采集：</p>
      <code className="mt-2 inline-block rounded-lg border border-line bg-surface-2 px-3 py-1.5 font-mono text-xs text-fg">{ACCESS_INIT_HINT}</code>
      <p className="mt-3 text-[11px] text-muted">库路径取 ACCESS_DB 环境变量，默认 access_radar/access.sqlite。</p>
    </div>
  );
}

function HealthStrip({ data, now }: { data: HealthResult | null; now: number }) {
  const [showOff, setShowOff] = useState(false);
  if (!data || !data.initialized) return null;
  const { summary, sources, maintenance } = data;
  const active = sources.filter((s) => s.level !== "off");
  const off = sources.filter((s) => s.level === "off");
  const c = summary.collector;
  const drift = Math.max(0, now - data.now);
  return (
    <section className="mb-4 rounded-xl border border-line bg-surface" data-testid="access-health">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-3 py-2 text-xs">
        <h2 className="font-mono tracking-wide text-fg">SOURCE HEALTH</h2>
        <span className="inline-flex items-center gap-1 font-mono">
          <span className={`size-2 rounded-full ${LEVEL_DOT[summary.level]}`} />
          {summary.active ? summary.label : "无已接入来源"}
        </span>
        <span className={`font-mono ${c.alive ? "text-muted" : "text-clay"}`} title="runner_meta.collector_heartbeat，超过 60s 视为采集进程没在跑">
          采集进程 {c.heartbeatAt == null ? "无心跳" : `${c.alive ? "运行中" : "未运行"} · 心跳 ${fmtAgeMs((c.ageMs ?? 0) + drift)} 前`}
        </span>
        <span className="font-mono text-muted" title="source_asset_ref.resolution_status">
          身份 已确认 {data.resolution.CONFIRMED} · 待确认 {data.resolution.SUGGESTED} · 未解析 {data.resolution.UNRESOLVED}
        </span>
        {!data.hasRunnerTables ? <span className="text-muted">（无 source_run 表，只按 source_health 判断）</span> : null}
      </div>
      <div className="flex flex-wrap gap-1.5 px-3 py-2">
        {active.map((s) => (
          <span
            key={s.sourceId}
            className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-muted"
            title={[`${s.label}（${s.clock}）`, ...s.reasons, s.lastError ? `last_error: ${s.lastError}` : ""].filter(Boolean).join("\n")}
          >
            <span className={`mr-1 inline-block size-1.5 rounded-full ${LEVEL_DOT[s.level]}`} />
            {s.sourceId} {s.ageMs == null ? "—" : fmtAgeMs(s.ageMs + drift)}
            {s.level !== "healthy" ? <span className={s.level === "degraded" ? "text-brass" : "text-clay"}> {s.label}</span> : null}
          </span>
        ))}
        {active.length === 0 ? <span className="text-xs text-muted">还没有已接入的来源在运行</span> : null}
        {off.length ? (
          <button type="button" onClick={() => setShowOff((v) => !v)} className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-muted hover:text-fg">
            {HEALTH_LABEL.off} {off.length}
          </button>
        ) : null}
      </div>
      {showOff && off.length ? (
        <p className="px-3 pb-2 font-mono text-[10px] text-muted">
          {off.map((s) => `${s.sourceId}${s.reasons[0] ? `（${s.reasons[0]}）` : ""}`).join(" · ")}
        </p>
      ) : null}
      {data.hasMaintenanceTable ? (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-line px-3 py-2" data-testid="access-maintenance">
          <span className="text-[11px] text-muted">维护任务</span>
          {maintenance.map((m) => (
            <span
              key={m.jobId}
              className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-muted"
              title={[
                `${m.jobId}：${m.levelLabel}（${m.clock}）`,
                ...m.reasons,
                m.lastSuccess ? `上次成功 ${fmtTs8Full(m.lastSuccess)}` : "从未成功",
                ...Object.entries(m.lastResult).map(([k, v]) => `${k}: ${v}`),
              ].join("\n")}
            >
              <span className={`mr-1 inline-block size-1.5 rounded-full ${LEVEL_DOT[m.level]}`} />
              {m.label} {m.lastSuccess ? `${fmtAgeMs((m.ageMs ?? 0) + drift)} 前` : "未成功"}
              {m.consecutiveErrors ? <span className="text-clay"> 连续失败 {m.consecutiveErrors}</span> : null}
            </span>
          ))}
          {maintenance.length === 0 ? <span className="font-mono text-[10px] text-muted">无</span> : null}
        </div>
      ) : null}
    </section>
  );
}

function EventRow({ e, now, onOpen }: { e: AccessEvent; now: number; onOpen: (chain: string, address: string) => void }) {
  const quotes = eventQuotes(e).filter((q) => q !== "—");
  const route = [quotes.join(" / "), e.network && e.network !== e.quote.toLowerCase() ? e.network : "", e.country].filter(Boolean).join(" · ");
  return (
    <tr className={"border-b border-line/50 align-top last:border-b-0 hover:bg-surface/40 " + (e.retracted ? "opacity-50" : "")}>
      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap" title={`anchor_at ${fmtTs8Full(e.anchorAt)}\n入库 ${fmtTs8Full(e.observedAt)}`}>
        <div>{fmtTs8(e.anchorAt)}</div>
        <div className="text-[10px] text-muted">{fmtAgo(now, e.anchorAt)}</div>
      </td>
      <td className="px-3 py-2">
        <div className={`text-sm ${TONE_TEXT[e.desc.tone]}`} title={e.eventType}>
          {e.desc.severity === 3 ? <span className="mr-1">●</span> : null}
          {e.desc.label}
          {e.url && !e.evidence.some((s) => s.urls.includes(e.url!)) ? (
            <a href={e.url} target="_blank" rel="noreferrer noopener" className="ml-1 inline-flex items-center text-brass hover:underline" aria-label="公告链接">
              <ExternalLink className="size-3" />
            </a>
          ) : null}
        </div>
        <div className="font-mono text-[10px] text-muted">
          {statusLabel(e.fromStatus)} → {statusLabel(e.toStatus)}
          {e.effectiveAt ? <span className={e.effectiveAt > now ? "text-brass" : ""}> · 生效 {fmtTs8(e.effectiveAt)}</span> : null}
        </div>
      </td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap items-center gap-1">
          {e.market ? (
            <button type="button" className="text-sm font-medium hover:underline" onClick={() => onOpen(e.market!.chain, e.market!.address)}>
              {e.symbol}
            </button>
          ) : (
            <span className="text-sm font-medium">{e.symbol}</span>
          )}
          <Badge tone={e.resolution.tone} title={e.resolution.hint + (e.suggestedAssetKey ? `\n建议：${e.suggestedAssetKey}` : "")}>
            {e.resolution.label}
          </Badge>
        </div>
        <div className="max-w-56 truncate font-mono text-[10px] text-muted" title={e.globalAssetKey ?? e.assetKey}>
          {e.globalAssetKey ?? e.assetKey}
        </div>
        {e.market ? (
          <div className="font-mono text-[10px] text-muted" title={`GMGN ${e.market.table}${e.market.source ? ` / ${e.market.source}` : ""}`}>
            {MARKET_CHAIN_LABEL[e.market.chain] ?? e.market.chain} · {e.market.price == null ? "—" : `$${e.market.price.toPrecision(4)}`}
            {e.market.marketCap != null ? ` · FDV ${fmtUsdN(e.market.marketCap)}` : ""}
          </div>
        ) : null}
      </td>
      <td className="px-3 py-2">
        <div className="text-sm">{e.platformName}</div>
        <div className="font-mono text-[10px] text-muted">{route || "—"}</div>
        {e.siblings.length ? (
          <div
            className="font-mono text-[10px] text-muted"
            title={
              "同一条公告、同一资产的多条事件（例如公告未写交易对，按该平台已有的每个市场各记一条），这里合并显示：\n" +
              [{ quote: e.quote, label: e.desc.label, toStatus: e.toStatus }, ...e.siblings]
                .map((x) => `${x.quote || "—"}：${x.label}（→ ${statusLabel(x.toStatus)}）`)
                .join("\n")
            }
          >
            同一公告 · {e.siblings.length + 1} 条
            {new Set([e.eventType, ...e.siblings.map((x) => x.eventType)]).size > 1 ? " · 类型不一" : ""}
          </div>
        ) : null}
      </td>
      <td className="px-3 py-2 text-right whitespace-nowrap" title={e.confidence.text}>
        <div className={`font-mono text-sm ${TONE_TEXT[e.confidence.tone]}`}>{e.confidence.pct}</div>
        <div className="font-mono text-[10px] text-muted">
          {e.confidence.sources} 源{e.provisional ? " · 待确认" : ""}
        </div>
      </td>
      <td className="px-3 py-2">
        <ul className="space-y-0.5">
          {e.evidence.slice(0, 4).map((s) => (
            <li key={s.sourceId} className="flex flex-wrap items-center gap-1 font-mono text-[10px] text-muted" title={`${s.tierLabel} · 独立组 ${s.group} · ${s.roles.join("/")}`}>
              <span>{s.name}</span>
              <span className="text-muted/70">{s.tierLabel}</span>
              {s.urls.map((u) => (
                <a key={u} href={u} target="_blank" rel="noreferrer noopener" className="inline-flex items-center text-brass hover:underline" aria-label="来源链接">
                  <ExternalLink className="size-3" />
                </a>
              ))}
            </li>
          ))}
          {e.evidence.length === 0 ? <li className="font-mono text-[10px] text-muted">{e.firstSourceName}</li> : null}
        </ul>
      </td>
    </tr>
  );
}

export function AccessView() {
  const feedFn = useServerFn(fetchAccessFeed);
  const healthFn = useServerFn(fetchAccessHealth);
  const [win, setWin] = useState<FeedWindow>("24h");
  const [feed, setFeed] = useState<FeedResult | null>(null);
  const [health, setHealth] = useState<HealthResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [category, setCategory] = useState<EventCategory | "all">("all");
  const [platform, setPlatform] = useState("all");
  const [chain, setChain] = useState("all");
  const [grouped, setGrouped] = useState(false);
  const [detail, setDetail] = useState<{ chain: string; address: string } | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const seq = useRef(0);

  async function load() {
    const my = ++seq.current;
    setLoading(true);
    try {
      const [f, h] = await Promise.all([feedFn({ data: { window: win, limit: 500 } }), healthFn()]);
      if (my !== seq.current) return;
      setFeed(f);
      setHealth(h);
      setError(f.error ?? h.error ?? "");
    } catch (e) {
      if (my === seq.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [win]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 15_000);
    return () => clearInterval(t);
  }, []);

  const events = useMemo(
    () =>
      filterEvents(feed?.events ?? [], {
        categories: category === "all" ? undefined : [category],
        platforms: platform === "all" ? undefined : [platform],
        chain,
      }),
    [feed, category, platform, chain],
  );
  const groups = useMemo(() => (grouped ? groupEventsByAsset(events) : []), [grouped, events]);
  const catCount = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of feed?.events ?? []) m.set(e.desc.category, (m.get(e.desc.category) ?? 0) + 1);
    return m;
  }, [feed]);

  const notInit = feed != null && !feed.initialized;
  const chip = (on: boolean) => "min-h-9 rounded-full border px-3 text-sm " + (on ? "border-brass text-fg" : "border-line text-muted");

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="mr-2 text-lg font-medium">新入口</h2>
        <span className="text-xs text-muted">上币、法币通道、新链部署、暂停 / 下架。时间 {TZ_LABEL}。</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {FEED_WINDOWS.map((w) => (
            <button key={w} type="button" onClick={() => setWin(w)} className={chip(win === w)}>
              {w}
            </button>
          ))}
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

      {error ? <p className="mb-3 rounded-lg border border-clay/30 bg-clay/10 p-3 text-sm text-clay">{error}</p> : null}

      <HealthStrip data={health} now={now} />

      {notInit ? (
        <InitHint reason={feed.reason} />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => setCategory("all")} className={chip(category === "all")}>
              全部 <span className="font-mono text-xs text-muted">{feed?.events.length ?? 0}</span>
            </button>
            {EVENT_CATEGORIES.filter((c) => catCount.get(c.id)).map((c) => (
              <button key={c.id} type="button" onClick={() => setCategory(c.id)} className={chip(category === c.id)}>
                {c.label} <span className="font-mono text-xs text-muted">{catCount.get(c.id)}</span>
              </button>
            ))}
            <select
              value={platform}
              onChange={(ev) => setPlatform(ev.target.value)}
              aria-label="平台"
              className="h-9 rounded-full border border-line bg-bg px-3 text-sm text-fg"
            >
              <option value="all">全部平台</option>
              {(feed?.platforms ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}（{p.count}）
                </option>
              ))}
            </select>
            <select
              value={chain}
              onChange={(ev) => setChain(ev.target.value)}
              aria-label="链"
              className="h-9 rounded-full border border-line bg-bg px-3 text-sm text-fg"
            >
              {MARKET_CHAIN_TABS.map((c) => (
                <option key={c} value={c}>
                  {c === "all" ? "全部链" : MARKET_CHAIN_LABEL[c]}
                </option>
              ))}
            </select>
            <button type="button" aria-pressed={grouped} onClick={() => setGrouped((v) => !v)} className={chip(grouped)}>
              按资产分组
            </button>
          </div>

          {grouped ? (
            <div className="space-y-2">
              {groups.map((g) => (
                <section key={g.key} className="rounded-xl border border-line">
                  <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
                    {g.market ? (
                      <button type="button" className="font-medium hover:underline" onClick={() => setDetail({ chain: g.market!.chain, address: g.market!.address })}>
                        {g.symbol}
                      </button>
                    ) : (
                      <span className="font-medium">{g.symbol}</span>
                    )}
                    <Badge tone={g.resolution.tone} title={g.resolution.hint}>
                      {g.resolution.label}
                    </Badge>
                    <span className="font-mono text-[10px] text-muted">{g.key}</span>
                    <span className="ml-auto font-mono text-[10px] text-muted">
                      {g.platforms.join(" / ")} · {fmtAgo(now, g.latestAt)}
                    </span>
                  </div>
                  <ul className="divide-y divide-line/50">
                    {g.events.map((e) => (
                      <li key={e.id} className="flex flex-wrap items-center gap-2 px-3 py-1.5 text-xs">
                        <span className="font-mono text-muted">{fmtTs8(e.anchorAt)}</span>
                        <span className={TONE_TEXT[e.desc.tone]}>{e.desc.label}</span>
                        <span className="text-muted">
                          {e.platformName}
                          {eventQuotes(e).filter((q) => q !== "—").length ? ` · ${eventQuotes(e).filter((q) => q !== "—").join(" / ")}` : ""}
                        </span>
                        <span className={`ml-auto font-mono ${TONE_TEXT[e.confidence.tone]}`} title={e.confidence.text}>
                          {e.confidence.pct}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-line">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line bg-surface-2 font-mono text-xs text-muted">
                    <th className="px-3 py-2">时间 {TZ_LABEL}</th>
                    <th className="px-3 py-2">事件</th>
                    <th className="px-3 py-2">资产</th>
                    <th className="px-3 py-2">平台 / 交易对</th>
                    <th className="px-3 py-2 text-right" title="后端置信度 = 1 − Π(1 − 各独立来源组的最高 tier 权重)">置信度</th>
                    <th className="px-3 py-2">来源</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((e) => (
                    <EventRow key={e.id} e={e} now={now} onOpen={(c, a) => setDetail({ chain: c, address: a })} />
                  ))}
                </tbody>
              </table>
              {events.length === 0 ? (
                <p className="p-8 text-center text-sm text-muted">{feed ? `最近 ${win} 没有符合条件的事件` : "加载中…"}</p>
              ) : null}
              {feed?.truncated ? <p className="border-t border-line px-3 py-2 text-center text-xs text-muted">只显示最新 500 条，缩短时间窗看更多</p> : null}
            </div>
          )}

          <div className="mt-4 rounded-xl border border-line p-4 text-xs text-muted">
            <p className="mb-1 text-fg">怎么读</p>
            <ul className="list-inside list-disc space-y-0.5">
              <li>时间是 episode 最早已知时间（公告发布 / 来源检测 / 我方入库取最早），按它倒序。● = 现货、永续、Alpha 的上线 / 公告 / 下架。</li>
              <li>身份：已确认 = 合约地址精确匹配或人工确认；待确认 = 只按代号匹配；未解析 = 只有平台代号。点代号打开 GMGN 详情（只对能对上合约的币）。</li>
              <li>置信度和独立来源数是采集端写库的值，不在前端重算。待确认 = 证据不足的临时状态，可能被撤回。</li>
              <li>官方下架公告生效时间在未来时显示“（预告）”，到点后才算真正下架。韩国交易所的警示（유의 종목）不是暂停，不进这个列表。</li>
            </ul>
          </div>
        </>
      )}
      {detail ? <TokenDetailDrawer chain={detail.chain} address={detail.address} onClose={() => setDetail(null)} /> : null}
    </div>
  );
}
