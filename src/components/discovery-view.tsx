import { useEffect, useMemo, useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { RefreshCw, Trash2, Plus, Bell } from "lucide-react";
import { fetchDiscovery, type DiscoveryResult, type DiscoveryRow } from "@/lib/rh/discovery-server";
import { CANDIDATE_MIN_SCORE, SCORE_RULES } from "@/lib/rh/discovery";
import {
  ALERT_FIELDS,
  DEFAULT_RULES,
  SEEN_STORAGE_KEY,
  loadRules,
  newHits,
  saveRules,
  type AlertField,
  type AlertHit,
  type AlertOp,
  type AlertRule,
} from "@/lib/rh/alerts";
import { TokenDetailDrawer, fmtNum, fmtPctPoints, fmtTime, fmtUsdN, fmtX, pctTone } from "@/components/token-detail";
import { MARKET_CHAIN_LABEL, MARKET_CHAIN_TABS } from "@/lib/rh/market-chains";

const REFRESH_MS = 60_000;

function useDiscovery(rules: AlertRule[] | null) {
  const fn = useServerFn(fetchDiscovery);
  const [data, setData] = useState<DiscoveryResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  const rulesSig = JSON.stringify(rules ?? []);

  async function load() {
    const my = ++seq.current;
    setLoading(true);
    try {
      const res = await fn({ data: { rules: rules ?? [] } });
      if (my !== seq.current) return;
      if (res.ok) {
        setData(res);
        setError("");
      } else setError(res.error);
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
  }, [rulesSig]);

  return { data, error, loading, reload: load };
}

function RankMove({ r }: { r: DiscoveryRow }) {
  const d = r.derived;
  if (d.trendingNewEntry) return <span className="text-brass">新进榜</span>;
  if (d.trendingRankMove1h == null) return <span className="text-muted">—</span>;
  const m = d.trendingRankMove1h;
  return <span className={m > 0 ? "text-moss" : m < 0 ? "text-clay" : "text-muted"}>{m > 0 ? `↑${m}` : m < 0 ? `↓${-m}` : "0"}</span>;
}

export function DiscoveryView() {
  const { data, error, loading, reload } = useDiscovery(null);
  const [chain, setChain] = useState<string>("all");
  const [onlyCandidates, setOnlyCandidates] = useState(true);
  const [detail, setDetail] = useState<{ chain: string; address: string } | null>(null);
  const [limit, setLimit] = useState(100);

  const rows = useMemo(() => {
    let arr = data?.rows ?? [];
    if (chain !== "all") arr = arr.filter((r) => r.chain === chain);
    if (onlyCandidates) arr = arr.filter((r) => r.score.candidate);
    return arr;
  }, [data, chain, onlyCandidates]);

  const cov = data?.coverage;

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6">
      <div className="mb-3 flex flex-wrap items-center gap-2">
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
        <button
          type="button"
          aria-pressed={onlyCandidates}
          onClick={() => setOnlyCandidates((v) => !v)}
          className={"min-h-9 rounded-full border px-3 text-sm " + (onlyCandidates ? "border-brass text-fg" : "border-line text-muted")}
        >
          只看候选（≥{CANDIDATE_MIN_SCORE} 分）
        </button>
        <button
          type="button"
          onClick={() => reload()}
          disabled={loading}
          className="ml-auto inline-flex items-center gap-1 rounded-full border border-line px-3 py-1.5 text-sm text-muted hover:text-fg disabled:opacity-50"
        >
          <RefreshCw className={"size-4 " + (loading ? "animate-spin" : "")} />
          刷新
        </button>
      </div>

      {cov ? (
        <p className="mb-3 font-mono text-xs text-muted" data-testid="discovery-coverage">
          最近 {Math.round((data!.universeSec) / 60)} 分钟出现在 Trending / Hot / Trenches 的 {cov.universe} 个 · 有活跃度 {cov.withActivity} · 有 1h 基准 {cov.withBaseline} · 有 1h 涨跌 {cov.withPc1h} · 有已定稿日K指标 {cov.withFinalBars} · 候选 {cov.candidates}
        </p>
      ) : null}
      {error ? <p className="mb-3 rounded-lg border border-clay/30 bg-clay/10 p-3 text-sm text-clay">{error}</p> : null}

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-line bg-surface-2 font-mono text-xs text-muted">
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Token</th>
              <th className="px-3 py-2 text-right" title="满足的规则数 / 有数据可评估的规则数">分</th>
              <th className="px-3 py-2">命中</th>
              <th className="px-3 py-2 text-right">Price</th>
              <th className="px-3 py-2 text-right">1H</th>
              <th className="px-3 py-2 text-right">Vol 24h</th>
              <th className="px-3 py-2 text-right" title="买入笔数占比（DERIVED）">买占比</th>
              <th className="px-3 py-2 text-right" title="24h 买入笔数 现在 / 1h 前（DERIVED）">买 1h×</th>
              <th className="px-3 py-2 text-right" title="24h 交易笔数 现在 / 1h 前（DERIVED）">笔 1h×</th>
              <th className="px-3 py-2 text-right" title="Trending 24h 名次 1h 变化（DERIVED）">名次 1h</th>
              <th className="px-3 py-2 text-right" title="24h 成交额 / FDV（DERIVED）">Vol/FDV</th>
              <th className="px-3 py-2 text-right" title="最新已定稿日成交额 / 前 7 日均值（DERIVED）">日量×</th>
              <th className="px-3 py-2 text-right">FDV</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((r, i) => (
              <tr key={`${r.chain}:${r.address}`} className="border-b border-line/50 last:border-b-0 hover:bg-surface/40">
                <td className="px-3 py-2 font-mono text-xs text-muted">{i + 1}</td>
                <td className="px-3 py-2">
                  <button type="button" onClick={() => setDetail({ chain: r.chain, address: r.address })} className="text-left">
                    <span className="block text-sm font-medium">{r.symbol || "?"}</span>
                    <span className="block font-mono text-[10px] text-muted">{r.chain} · {r.sources.join("/")}</span>
                  </button>
                </td>
                <td className="px-3 py-2 text-right font-mono text-sm">
                  <span className={r.score.candidate ? "text-moss" : "text-fg"}>{r.score.score}</span>
                  <span className="text-muted">/{r.score.evaluated}</span>
                </td>
                <td className="max-w-64 px-3 py-2 text-xs text-muted" title={r.score.reasons.join("\n")}>
                  <span className="line-clamp-2">{r.score.reasons.join(" · ") || "—"}</span>
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">{r.price == null ? "—" : `$${fmtNum(r.price)}`}</td>
                <td className={`px-3 py-2 text-right font-mono text-xs ${pctTone(r.pc1h)}`}>{fmtPctPoints(r.pc1h)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtUsdN(r.volume24h)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{r.derived.buySellRatio == null ? "—" : `${(r.derived.buySellRatio * 100).toFixed(0)}%`}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtX(r.derived.buysAccel1h)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtX(r.derived.swapsAccel1h)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs"><RankMove r={r} /></td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtX(r.derived.volumeToFdv)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtX(r.derived.dailyVolumeAccel)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtUsdN(r.fdv)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length > limit ? (
          <button type="button" onClick={() => setLimit((n) => n + 200)} className="block w-full border-t border-line py-3 text-center text-sm text-muted hover:text-fg">
            显示更多（已显示 {limit} / {rows.length}）
          </button>
        ) : null}
        {rows.length === 0 && !loading ? (
          <p className="p-8 text-center text-sm text-muted">{data ? "没有符合条件的代币" : "加载中…"}</p>
        ) : null}
      </div>

      <div className="mt-4 rounded-xl border border-line p-4 text-xs text-muted">
        <p className="mb-1 text-fg">打分规则（每条 1 分，≥{CANDIDATE_MIN_SCORE} 分为候选）</p>
        <ul className="list-inside list-disc space-y-0.5">
          {SCORE_RULES.map((r) => <li key={r.id}>{r.label}</li>)}
        </ul>
        <p className="mt-2">
          全部是本地计算的 DERIVED 指标，输入只有 GMGN 价格、涨跌、成交额、买卖笔数、FDV、名次，以及已定稿日 K。
          缺数据的规则不计分，也不算"未满足"。不使用流动性、honeypot、刷量、税率、信号类型。
          1h 倍数 = 同一发现源同一参数下，现在与约 1 小时前的 24h 笔数之比。
        </p>
      </div>
      {detail ? <TokenDetailDrawer chain={detail.chain} address={detail.address} onClose={() => setDetail(null)} /> : null}
    </div>
  );
}

function loadSeen(): Set<string> {
  try {
    const raw = window.localStorage.getItem(SEEN_STORAGE_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(arr) ? arr.filter((x) => typeof x === "string") : []);
  } catch {
    return new Set();
  }
}

function saveSeen(keys: Set<string>) {
  try {
    window.localStorage.setItem(SEEN_STORAGE_KEY, JSON.stringify([...keys].slice(-5000)));
  } catch {
    /* 忽略 */
  }
}

function describe(rule: { field: AlertField; op: AlertOp; threshold: number | null }): string {
  const spec = ALERT_FIELDS.find((f) => f.field === rule.field);
  const label = spec?.label ?? rule.field;
  if (rule.op === "is_true") return label;
  return `${label} ${rule.op === ">=" ? "≥" : "≤"} ${rule.threshold}${spec?.unit && spec.unit !== "×" ? ` ${spec.unit}` : spec?.unit ?? ""}`;
}

function fmtValue(h: AlertHit): string {
  if (typeof h.value === "boolean") return h.value ? "是" : "否";
  return fmtNum(h.value, 2);
}

export function AlertsView() {
  const [rules, setRules] = useState<AlertRule[] | null>(null);
  const [seen, setSeen] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<{ chain: string; address: string } | null>(null);
  const [field, setField] = useState<AlertField>("pc1h");
  const [op, setOp] = useState<AlertOp>(">=");
  const [threshold, setThreshold] = useState("20");
  const [ruleChain, setRuleChain] = useState("all");
  const [formErr, setFormErr] = useState("");

  useEffect(() => {
    setRules(loadRules(window.localStorage));
    setSeen(loadSeen());
  }, []);

  const { data, error, loading, reload } = useDiscovery(rules);
  const hits = data?.alerts ?? [];
  const fresh = useMemo(() => newHits(hits, seen), [hits, seen]);
  const freshKeys = useMemo(() => new Set(fresh.map((h) => h.key)), [fresh]);
  const spec = ALERT_FIELDS.find((f) => f.field === field)!;

  function update(next: AlertRule[]) {
    setRules(next);
    saveRules(window.localStorage, next);
  }

  function addRule() {
    setFormErr("");
    const isBool = spec.kind === "bool";
    const th = isBool ? null : Number(threshold);
    if (!isBool && (threshold.trim() === "" || !Number.isFinite(th))) {
      setFormErr("阈值要是数字");
      return;
    }
    const rule: AlertRule = {
      id: `r${Date.now().toString(36)}`,
      field,
      op: isBool ? "is_true" : op,
      threshold: th,
      enabled: true,
      chain: ruleChain === "all" ? null : ruleChain,
    };
    update([...(rules ?? []), rule]);
  }

  function markAllSeen() {
    const next = new Set(seen);
    for (const h of hits) next.add(h.key);
    setSeen(next);
    saveSeen(next);
  }

  const byRule = useMemo(() => {
    const m = new Map<string, AlertHit[]>();
    for (const h of hits) {
      const list = m.get(h.ruleId) ?? [];
      list.push(h);
      m.set(h.ruleId, list);
    }
    return m;
  }, [hits]);

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-6">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Bell className="size-4 text-brass" />
        <h2 className="text-lg font-medium">告警</h2>
        <span className="font-mono text-xs text-muted" data-testid="alert-count">
          命中 {hits.length} · 新 {fresh.length}
        </span>
        <div className="ml-auto flex gap-2">
          <button type="button" onClick={markAllSeen} disabled={fresh.length === 0} className="rounded-full border border-line px-3 py-1.5 text-sm text-muted hover:text-fg disabled:opacity-50">
            全部标为已读
          </button>
          <button type="button" onClick={() => reload()} disabled={loading} className="inline-flex items-center gap-1 rounded-full border border-line px-3 py-1.5 text-sm text-muted hover:text-fg disabled:opacity-50">
            <RefreshCw className={"size-4 " + (loading ? "animate-spin" : "")} />
            刷新
          </button>
        </div>
      </div>
      {error ? <p className="mb-3 rounded-lg border border-clay/30 bg-clay/10 p-3 text-sm text-clay">{error}</p> : null}

      <section className="rounded-xl border border-line p-4">
        <h3 className="text-sm font-medium">规则</h3>
        <p className="mt-0.5 text-xs text-muted">规则存在这台浏览器。每分钟用最新数据评估一次。字段缺失时不触发。</p>
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="text-xs text-muted">
            字段
            <select value={field} onChange={(e) => setField(e.target.value as AlertField)} className="mt-1 block h-9 rounded-lg border border-line bg-bg px-2 text-sm text-fg">
              {ALERT_FIELDS.map((f) => (
                <option key={f.field} value={f.field}>{f.label}{f.derived ? "（计算）" : ""}</option>
              ))}
            </select>
          </label>
          {spec.kind === "number" ? (
            <>
              <label className="text-xs text-muted">
                条件
                <select value={op} onChange={(e) => setOp(e.target.value as AlertOp)} className="mt-1 block h-9 rounded-lg border border-line bg-bg px-2 text-sm text-fg">
                  <option value=">=">≥</option>
                  <option value="<=">≤</option>
                </select>
              </label>
              <label className="text-xs text-muted">
                阈值（{spec.unit}）
                <input value={threshold} onChange={(e) => setThreshold(e.target.value)} inputMode="decimal" className="mt-1 block h-9 w-28 rounded-lg border border-line bg-bg px-2 font-mono text-sm text-fg" />
              </label>
            </>
          ) : (
            <span className="pb-2 text-xs text-muted">为"是"时触发</span>
          )}
          <label className="text-xs text-muted">
            链
            <select value={ruleChain} onChange={(e) => setRuleChain(e.target.value)} className="mt-1 block h-9 rounded-lg border border-line bg-bg px-2 text-sm text-fg">
              {MARKET_CHAIN_TABS.map((c) => <option key={c} value={c}>{MARKET_CHAIN_LABEL[c]}</option>)}
            </select>
          </label>
          <button type="button" onClick={addRule} className="inline-flex h-9 items-center gap-1 rounded-full border border-brass px-3 text-sm">
            <Plus className="size-4" /> 添加
          </button>
          <button type="button" onClick={() => update(DEFAULT_RULES)} className="h-9 rounded-full border border-line px-3 text-sm text-muted hover:text-fg">
            恢复默认
          </button>
          {formErr ? <span className="pb-2 text-xs text-clay">{formErr}</span> : null}
        </div>

        <ul className="mt-4 divide-y divide-line/60">
          {(rules ?? []).map((r) => {
            const n = byRule.get(r.id)?.length ?? 0;
            return (
              <li key={r.id} className="flex flex-wrap items-center gap-2 py-2">
                <input
                  type="checkbox"
                  checked={r.enabled}
                  aria-label="启用"
                  onChange={() => update((rules ?? []).map((x) => (x.id === r.id ? { ...x, enabled: !x.enabled } : x)))}
                  className="size-4 accent-[var(--color-brass)]"
                />
                <span className={"text-sm " + (r.enabled ? "" : "text-muted line-through")}>{describe(r)}</span>
                <span className="font-mono text-[10px] text-muted">{r.chain ? MARKET_CHAIN_LABEL[r.chain] : "全部链"}</span>
                <span className="ml-auto font-mono text-xs text-muted">命中 {n}</span>
                <button type="button" aria-label="删除规则" onClick={() => update((rules ?? []).filter((x) => x.id !== r.id))} className="inline-flex size-8 items-center justify-center rounded-full text-muted hover:bg-surface-2 hover:text-clay">
                  <Trash2 className="size-4" />
                </button>
              </li>
            );
          })}
          {rules && rules.length === 0 ? <li className="py-3 text-xs text-muted">没有规则</li> : null}
        </ul>
      </section>

      <section className="mt-4 rounded-xl border border-line">
        <h3 className="border-b border-line px-4 py-2 text-sm font-medium">当前命中</h3>
        <ul className="divide-y divide-line/50">
          {hits.slice(0, 300).map((h) => (
            <li key={h.key} className="flex flex-wrap items-center gap-2 px-4 py-2 text-sm">
              {freshKeys.has(h.key) ? <span className="rounded-full bg-brass/20 px-1.5 font-mono text-[10px] text-brass">新</span> : null}
              <button type="button" className="font-medium hover:underline" onClick={() => setDetail({ chain: h.chain, address: h.address })}>
                {h.symbol || "?"}
              </button>
              <span className="font-mono text-[10px] text-muted">{h.chain}</span>
              <span className="text-xs text-muted">{describe(h)}</span>
              <span className="ml-auto font-mono text-xs">当前 {fmtValue(h)}</span>
            </li>
          ))}
          {hits.length === 0 ? (
            <li className="px-4 py-6 text-center text-xs text-muted">{data ? "没有命中" : "加载中…"}</li>
          ) : null}
        </ul>
        {data ? <p className="border-t border-line px-4 py-2 font-mono text-[10px] text-muted">评估时间 {fmtTime(data.now)}</p> : null}
      </section>
      {detail ? <TokenDetailDrawer chain={detail.chain} address={detail.address} onClose={() => setDetail(null)} /> : null}
    </div>
  );
}
