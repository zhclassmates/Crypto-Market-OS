import { useEffect, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { fetchWmQuality, type WmQualityData, type WmQualityStatus } from "@/lib/rh/wm-quality-server";

const POLL_MS = 60_000;

const PROVIDER_LABEL: Record<string, string> = {
  cg: "CoinGecko",
  cmc: "CoinMarketCap",
  dex: "DEX Screener",
};

const STATUS_UI: Record<WmQualityStatus, { label: string; dot: string; text: string }> = {
  trusted: { label: "TRUSTED", dot: "bg-positive", text: "text-positive" },
  degraded: { label: "DEGRADED", dot: "bg-primary", text: "text-primary" },
  blocked: { label: "BLOCKED", dot: "bg-negative", text: "text-negative" },
};

function fmtNum(v: number | null): string {
  return v == null ? "—" : v.toLocaleString("en-US");
}

export function WmQualityBar() {
  const qualityFn = useServerFn(fetchWmQuality);
  const [data, setData] = useState<WmQualityData | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let stop = false;
    async function pull() {
      try {
        const res = await qualityFn();
        if (stop) return;
        setData(res);
        setErr(res.ok ? "" : res.error || "读取失败");
      } catch (e) {
        if (!stop) setErr(e instanceof Error ? e.message : String(e));
      }
    }
    pull();
    const t = setInterval(pull, POLL_MS);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [qualityFn]);

  return (
    <section className="mb-4 rounded-xl border border-line bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-3 py-2">
        <h2 className="font-mono text-xs tracking-wide text-fg">数据质量闸门 · WORLD MODEL OS</h2>
        <span className="font-mono text-[10px] text-muted">采集完成 ≠ 数据可信 ≠ 可用于决策 · 每 60s 重读</span>
      </div>
      {err && <p className="px-3 py-2 text-xs text-negative">{err}</p>}
      {data && data.blocked.length > 0 ? (
        <p className="border-b border-line bg-negative/10 px-3 py-2 text-xs text-negative">
          决策准入：{data.blocked.map((p) => PROVIDER_LABEL[p] || p).join("、")} 被 BLOCKED，禁止进入研究模块
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-line text-muted">
              <th className="px-3 py-2 font-mono font-normal">来源</th>
              <th className="px-3 py-2 font-mono font-normal">质量状态</th>
              <th className="px-3 py-2 font-mono font-normal">数据日期</th>
              <th className="px-3 py-2 text-right font-mono font-normal">覆盖资产</th>
              <th className="px-3 py-2 font-mono font-normal">采集</th>
              <th className="px-3 py-2 text-right font-mono font-normal" title="近 14 天 API 重试次数">14天重试</th>
              <th className="px-3 py-2 font-mono font-normal">检查时间 UTC</th>
              <th className="px-3 py-2 font-mono font-normal">原因 / 备注 / 修复</th>
            </tr>
          </thead>
          <tbody>
            {(data?.providers ?? []).map((p) => {
              const ui = STATUS_UI[p.status] ?? STATUS_UI.degraded;
              return (
                <tr key={p.provider} className="border-b border-line/60 align-top last:border-b-0" data-quality-provider={p.provider} data-quality-status={p.status}>
                  <td className="px-3 py-2 font-medium">{PROVIDER_LABEL[p.provider] || p.provider}</td>
                  <td className="px-3 py-2">
                    <span className={`inline-flex items-center gap-1 font-mono ${ui.text}`}>
                      <span className={`size-2 rounded-full ${ui.dot}`} />
                      {ui.label}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono">{p.dateUtc}</td>
                  <td className="px-3 py-2 text-right font-mono" title={p.knownRange ?? undefined}>{fmtNum(p.published)}</td>
                  <td className="px-3 py-2 font-mono">
                    {p.lastRunStatus ?? "—"}
                    {p.consecutiveFailures ? <span className="text-negative"> ×{p.consecutiveFailures}</span> : null}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{p.retries14d == null ? "—" : p.retries14d}</td>
                  <td className="px-3 py-2 font-mono">{p.checkedAtUtc.slice(0, 16).replace("T", " ")}</td>
                  <td className="max-w-105 px-3 py-2">
                    {p.reasons.map((r, i) => (
                      <p key={`r${i}`} className="text-primary">{r}</p>
                    ))}
                    {p.notes.map((n, i) => (
                      <p key={`n${i}`} className="text-muted" title={n}>{n.length > 60 ? n.slice(0, 60) + "…" : n}</p>
                    ))}
                    {p.fixes.filter((f) => f !== "无需动作").map((f, i) => (
                      <p key={`f${i}`} className="text-fg">&gt; {f}</p>
                    ))}
                    {p.reasons.length === 0 && p.notes.length === 0 ? <span className="text-muted">—</span> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {data && data.providers.length === 0 && !err ? (
          <p className="p-6 text-center text-xs text-muted">暂无质量报告，先在 world-model-os-v1 跑 market_ingest.py</p>
        ) : null}
      </div>
      <p className="px-3 py-2 text-[11px] text-muted">
        只读 world-model-os-v1 的 wm_quality_reports：TRUSTED 可进研究模块，DEGRADED 可用但需留意原因，BLOCKED 禁止进决策。备注为基线内常态标注，不降级。
      </p>
    </section>
  );
}
