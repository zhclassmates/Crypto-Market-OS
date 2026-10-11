import { useQuery } from "@tanstack/react-query";
import { Activity, RefreshCw } from "lucide-react";
import { fetchWmReasoning, type ReasoningData } from "@/lib/rh/wm-reasoning-server";

const dimensions: Record<string, string> = { funding: "新资金", people: "新人物", scenario: "新场景", protocol: "新协议", distribution: "新分配方式", productivity: "新生产力" };
type Row = Record<string, unknown>;
const obj = (v: unknown): Row => v && typeof v === "object" && !Array.isArray(v) ? v as Row : {};
const arr = (v: unknown): Row[] => Array.isArray(v) ? v as Row[] : [];
const usd = (v: unknown) => `$${(Number(v ?? 0) / 1e6).toFixed(4)}`;
const time = (v: unknown) => v ? new Date(String(v)).toLocaleString("zh-CN", { hour12: false }) : "尚未运行";
const stateNames: Record<string, string> = { NEW: "新假设", UNVERIFIED: "证据不足", TESTING: "验证中", SUPPORTED: "新增支持", WEAKENED: "受到削弱", INVALIDATED: "已失效", EXPIRED: "已过期", CLOSED: "停止跟踪" };

export function WmReasoningView() {
  const q = useQuery({ queryKey: ["wm-reasoning"], queryFn: async () => JSON.parse(await fetchWmReasoning()) as ReasoningData, refetchInterval: 60_000 });
  const d = q.data;
  const heartbeat = d?.checkpoints.find((v) => v.name === "worker-heartbeat");
  const stale = !heartbeat || Date.now() - new Date(String(heartbeat.updated_at)).getTime() > 10 * 60_000;
  return <section className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><h2 className="text-lg font-semibold">World Model OS · 推演</h2><p className="mt-1 text-sm text-muted">证据积累 → 待验证假设 → 后续数据检查 → 保留修订历史</p></div>
      <button className="min-h-11 rounded-lg border border-border px-4 text-sm" onClick={() => void q.refetch()} disabled={q.isFetching}><RefreshCw className="mr-2 inline size-4" />{q.isFetching ? "更新中" : "刷新证据"}</button>
    </div>
    {q.isPending ? <p className="text-muted">正在读取推演记录…</p> : q.isError || !d?.ok ? <p role="status" className="rounded-xl border border-border bg-surface p-6 text-sm">{d?.error || "暂时无法读取推演记录，请刷新重试。"}</p> : <>
      <div className="grid gap-4 md:grid-cols-3">
        {[ ["资金正在流向哪里？", "尚无法确认。TVL、成交额和市值不能证明资金净流向。"], ["最大的新趋势是什么？", "尚无已核验的结构性趋势。需补充连续快照、真实用户与收入。"], ["最值得验证的新机会是什么？", "免费核对来源冲突、下一期同口径数据，以及真实需求和收费归属。"] ].map(([title, body]) => <article key={title} className="rounded-xl border border-border bg-surface p-5"><h3 className="font-medium">{title}</h3><p className="mt-3 text-sm leading-relaxed text-muted">{body}</p></article>)}
      </div>
      <div className="flex flex-wrap gap-x-8 gap-y-3 rounded-xl border border-border p-5 text-sm">
        <span>今日付费请求 <b>{String(d.dailyCosts.calls ?? 0)}</b></span><span>本月按用量计费 <b>{usd(d.costs.settled)}</b></span><span>待结算预留 <b>{usd(d.costs.reserved)}</b></span><span>缓存节约估算 <b>{usd(d.costs.saved)}</b></span><span className="text-muted">软预算 $5 · 硬上限 $10 · 默认规则扫描</span>
      </div>
      <section className="space-y-3"><h3 className="font-medium">今日新增证据 · 六维变化</h3><p className="text-xs text-muted">首次导入的历史观测也计入今日新增；不等于事件发生于今天。标签表示变化类别，不能证明资金流向。</p>
        <div className="flex flex-wrap gap-2">{Object.entries(dimensions).map(([id,label]) => <span className="rounded-lg border border-border px-3 py-2 text-xs" key={id}>{label} · {d.events.filter((e) => Array.isArray(e.labels) && e.labels.includes(id)).length}</span>)}</div>
        {d.events.slice(0, 5).map((e) => <div key={String(e.id)} className="flex flex-wrap justify-between gap-2 border-b border-border py-3 text-sm"><span className="break-all">{String(e.entity)} · {String(e.metric)}</span><span className="text-muted">{String(e.disposition)} · 发生 {time(e.occurred_at)}</span></div>)}
        {!d.events.length && <p className="text-sm text-muted">今日尚无新增事件；请查看采集与队列状态。</p>}
      </section>
      <section className="space-y-3"><h3 className="font-medium">关键假设与最低成本验证动作</h3>
        {!d.hypotheses.length && <p className="text-sm text-muted">尚无达到跟踪门槛的假设。基线不足时保持未知。</p>}
        {d.hypotheses.map((h) => {
          const versions = arr(h.versions), latest = versions[0], conclusion = obj(latest?.conclusion);
          const frozen = versions.find((v) => obj(v.conclusion).prediction);
          const model = obj(frozen?.conclusion), inference = obj(model.inferences), prediction = obj(model.prediction);
          const evidence = d.evidence.filter((e) => e.event_id === h.event_id);
          return <article key={String(h.id)} className="rounded-xl border border-border bg-surface p-5">
            <div className="flex flex-wrap justify-between gap-2"><h4 className="break-all font-medium">{String(h.entity)} · {String(h.metric)}</h4><span className="text-sm text-muted">{stateNames[String(h.state)] ?? String(h.state)} · 研究信度 {Math.round(Number(h.confidence) * 100)}%</span></div>
            <p className="mt-2 text-xs text-muted">研究信度为规则设定，尚未做概率校准。资金操作始终需人工明确批准。</p>
            <p className="mt-3 text-sm">下一步：{String(model.next_action ?? "重新核验来源和关键前提")}</p>
            <div className="mt-4 grid gap-4 md:grid-cols-2"><div><p className="text-sm font-medium">事实与来源</p>{evidence.slice(0,2).map((e) => { const p = obj(e.payload); return <p key={String(e.id)} className="mt-2 break-all text-xs leading-relaxed text-muted">{p.value == null ? "缺失 / 定性" : Number(p.value).toLocaleString("zh-CN", {maximumFractionDigits:2})} {String(p.unit)} · {String(e.verification)} · {time(e.observed_at)}<br /><a className="text-primary underline" href={String(e.source_url)} target="_blank" rel="noreferrer">原始来源</a> · 证据 {String(e.id).slice(0,12)}</p>; })}</div>
              <div><p className="text-sm font-medium">预测与反证</p><p className="mt-2 text-xs leading-relaxed text-muted">{prediction.direction === "unknown" ? "缺少跨期基准，不做方向预测。" : `待验证持续性假设：${prediction.direction}，最低幅度 ${Number(prediction.min_fraction) * 100}%，7 / 30 天检查。`}</p><p className="mt-2 text-xs leading-relaxed text-muted">{String(model.falsifier ?? conclusion.outcome ?? "等待区分性反证")}</p></div></div>
            <details className="mt-4"><summary className="min-h-11 cursor-pointer py-3 text-sm text-primary">条件机制、机会与历史版本（{versions.length}）</summary>
              <p className="text-xs text-muted">以下均为推测，尚未获得因果验证：{String(inference.cause ?? "未知")}</p>
              {Array.isArray(inference.causal_chain) && <ul className="my-3 list-inside list-disc space-y-2 text-sm text-muted">{inference.causal_chain.map((v: unknown) => <li key={String(v)}>{String(v)}</li>)}</ul>}
              {[ ["受益者",inference.beneficiaries], ["受损者",inference.losers], ["替代者",inference.substitutes], ["价值创造",inference.value_creation], ["价值捕获",inference.value_capture], ["代币传导",inference.token_transmission], ["产品机会",inference.product_opportunity], ["投资候选",inference.investment_opportunity], ["竞争优势",inference.moat], ["失效条件",inference.invalidation] ].map(([label,value]) => <p key={String(label)} className="mt-2 text-xs leading-relaxed"><span className="text-muted">{String(label)}：</span>{String(value ?? "待核验")}</p>)}
              {versions.map((v) => <div className="mt-3 border-t border-border pt-3 text-xs" key={String(v.id)}><p>{time(v.at)} · {String(v.old_state)} → {String(v.new_state)} · 触发证据 {Array.isArray(v.trigger_evidence) ? v.trigger_evidence.map((x: unknown) => String(x).slice(0,12)).join("、") : "无"}</p><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all text-muted">{JSON.stringify(v.conclusion, null, 2)}</pre></div>)}
            </details>
          </article>;
        })}
      </section>
      <div className="grid gap-5 md:grid-cols-2"><section className="rounded-xl border border-border p-5"><h3 className="font-medium">新增支持、反证与失效记录</h3>{d.alerts.length ? d.alerts.map((a) => <p className="mt-3 text-xs text-muted" key={String(a.id)}>{time(a.at)} · {String(a.old_state)} → {String(a.new_state)}</p>) : <p className="mt-3 text-sm text-muted">暂无实质状态变化。重复消息不触发提醒。</p>}<p className="mt-3 text-xs text-muted">当前失效假设：{d.hypotheses.filter((h) => h.state === "INVALIDATED").length} · 支持和反证须绑定真实后续证据。</p></section>
        <section className="rounded-xl border border-border p-5"><h3 className="font-medium">队列、采集与验证</h3><p className="mt-3 text-sm"><Activity className="mr-2 inline size-4" />{stale ? "扫描心跳过期 / 尚未运行" : "扫描心跳正常"}</p><p className="mt-2 text-xs text-muted">最近执行：{time(heartbeat?.updated_at)}</p><div className="mt-3 flex flex-wrap gap-3 text-xs">{d.queue.map((r) => <span key={String(r.state)}>{String(r.state)} {String(r.count)}</span>)}</div><p className="mt-3 text-xs text-muted">验证检查点 {d.checks.length} · 抽样漏报待人工复核。{d.checks.some((c) => c.status === "PENDING") ? "7 / 30 天验证尚未到期。" : "缺失数据不计为零。"}</p></section></div>
      {d.runs.length > 0 && <details><summary className="min-h-11 cursor-pointer py-3 text-sm">AI 解释与调用记录</summary>{d.runs.map((r, i) => <div className="border-t border-border py-3 text-xs" key={i}>{String(r.tier)} · {String(r.provider)} / {String(r.model)} · {String(r.status)}<pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all text-muted">{JSON.stringify(r.result,null,2)}</pre></div>)}</details>}
    </>}
  </section>;
}
