import { useCallback, useEffect, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { RefreshCw } from "lucide-react";
import { fetchRadar, type RadarData } from "@/lib/rh/radar-server";

const HOUR_MS = 3_600_000;

const STATE_LABEL: Record<string, string> = {
  crowded_long_under_pressure: "S1 多头拥挤承压",
  crowded_short_under_pressure: "S2 空头拥挤承压",
  deleveraging_in_progress: "S3 去杠杆进行中",
  delever_done: "S4 去杠杆结束",
  basis_distortion: "S5 基差异常",
};

function barUtc(ts: number): string {
  return (
    new Date(ts).toLocaleString("zh-CN", {
      timeZone: "UTC",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }) + " UTC"
  );
}

function pct(v: number | null, digits = 2): string {
  if (v === null) return "—";
  const s = v >= 0 ? "+" : "";
  return s + (v * 100).toFixed(digits) + "%";
}

function pctile(v: number | null): string {
  if (v === null) return "—";
  return (v * 100).toFixed(0) + "%";
}

function z(v: number | null): string {
  return v === null ? "—" : v.toFixed(2);
}

function fmtAgeSec(v: number | null): string {
  if (v === null) return "—";
  if (v < 60) return `${Math.round(v)}s`;
  if (v < 3600) return `${Math.round(v / 60)}m`;
  return `${(v / 3600).toFixed(1)}h`;
}

function Th({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <th className="px-2 py-2 text-right font-mono text-[10px] font-normal tracking-wide text-muted" title={title}>
      {children}
    </th>
  );
}

function Card({
  title,
  right,
  children,
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-line bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-3 py-2">
        <h2 className="font-mono text-xs tracking-wide text-fg">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

export function RadarView() {
  const radarFn = useServerFn(fetchRadar);
  const [data, setData] = useState<RadarData | null>(null);
  const [loading, setLoading] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData(await radarFn());
    } finally {
      setLoading(false);
    }
  }, [radarFn]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 60_000); // 60s 静默重读
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(t);
      clearInterval(tick);
    };
  }, [refresh]);

  const readDrift = data ? Math.max(0, Math.floor((now - data.readAt) / 1000)) : null;
  const latestBar = data?.latestBar ?? null;
  const nextBarAt = latestBar !== null ? latestBar + 2 * HOUR_MS : null; // 下一轮最早（收盘+延迟）
  const secondsToNext = nextBarAt ? Math.round((nextBarAt - now) / 1000) : null;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      {/* 总览条 */}
      <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
        <span className="font-mono text-muted">
          BAR {latestBar !== null ? barUtc(latestBar) : "—"}
        </span>
        <span className="font-mono text-muted">
          在榜 <span className="text-fg">{data?.universeCount ?? "—"}</span>
        </span>
        <span className="font-mono text-muted">
          命中 <span className="text-primary">{data?.hits.length ?? "—"}</span>
        </span>
        {readDrift !== null && (
          <span className="font-mono text-muted">
            {readDrift < 5 ? "刚刚读取" : `${readDrift}s 前读取`}
          </span>
        )}
        {secondsToNext !== null && secondsToNext > 0 && (
          <span className="font-mono text-muted">距下一轮 ≈ {fmtAgeSec(secondsToNext)}</span>
        )}
        <button
          type="button"
          onClick={() => refresh()}
          className="ml-auto inline-flex items-center gap-1 rounded-full border border-line px-3 py-1 text-muted hover:border-primary hover:text-fg"
        >
          <RefreshCw className={"size-3.5 " + (loading ? "animate-spin" : "")} />
          刷新
        </button>
      </div>

      {data?.error && (
        <p className="mb-4 rounded-lg border border-negative/40 bg-negative/10 px-3 py-2 text-xs text-negative">
          {data.error}
        </p>
      )}

      <div className="flex flex-col gap-4">
        {/* 最新 bar 命中 */}
        <Card
          title="最新状态命中（研究依据，不是交易建议）"
          right={<span className="font-mono text-[10px] text-muted">冷却只压通知，不删 state</span>}
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-xs">
              <thead className="border-b border-line">
                <tr>
                  <Th>币</Th>
                  <Th>状态</Th>
                  <Th>通知</Th>
                  <Th title="资金费率 30 日分位（仅 Regular）">funding 分位</Th>
                  <Th title="4h 收益相对 BTC">ret 4h vs BTC</Th>
                  <Th title="持仓量（oi_qty）4h 变化">OI 4h</Th>
                  <Th title="官方 taker 4h 失衡，不用 K 线顶替">taker 4h</Th>
                  <Th title="基差率 7 日 z">basis z</Th>
                  <Th title="|1h 收益| 7 日 z">|ret| z</Th>
                  <Th title="OI 1h 变化 7 日 z">OIΔ z</Th>
                  <Th>标记</Th>
                </tr>
              </thead>
              <tbody>
                {data?.hits.map((h) => (
                  <tr key={`${h.symbol}-${h.state}`} className="border-b border-line/60 last:border-b-0">
                    <td className="px-2 py-2 font-mono">{h.symbol}</td>
                    <td className="px-2 py-2">{STATE_LABEL[h.state] || h.state}</td>
                    <td className="px-2 py-2">
                      {h.suppressed ? (
                        <span className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-muted">
                          冷却抑制
                        </span>
                      ) : (
                        <span className="rounded border border-positive/40 px-1.5 py-0.5 font-mono text-[10px] text-positive">
                          放行
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-2 text-right font-mono">{pctile(h.fundingPct)}</td>
                    <td className="px-2 py-2 text-right font-mono">{pct(h.ret4hVsBtc)}</td>
                    <td className="px-2 py-2 text-right font-mono">{pct(h.oiChg4h)}</td>
                    <td className="px-2 py-2 text-right font-mono">{pct(h.taker4h)}</td>
                    <td className="px-2 py-2 text-right font-mono">{z(h.basisZ)}</td>
                    <td className="px-2 py-2 text-right font-mono">{z(h.absRetZ)}</td>
                    <td className="px-2 py-2 text-right font-mono">{z(h.oiChgZ)}</td>
                    <td className="px-2 py-2 text-right font-mono text-[10px] text-muted">{h.flag ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data && data.hits.length === 0 && (
              <p className="px-3 py-6 text-center text-xs text-muted">
                {data.ok ? "本小时没有状态命中" : "等待数据"}
              </p>
            )}
          </div>
        </Card>

        {/* 数据源健康 */}
        <Card title="数据源健康（每源一行）" right={<span className="font-mono text-[10px] text-muted">失败不中断其他源</span>}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-xs">
              <thead className="border-b border-line">
                <tr>
                  <Th>源</Th>
                  <Th>结果</Th>
                  <Th>HTTP</Th>
                  <Th>latency</Th>
                  <Th>rows got/expected</Th>
                  <Th>null rate</Th>
                  <Th>age</Th>
                  <Th>时间戳语义</Th>
                  <Th>error</Th>
                </tr>
              </thead>
              <tbody>
                {data?.health.map((h) => (
                  <tr key={h.source} className="border-b border-line/60 last:border-b-0">
                    <td className="px-2 py-2 font-mono">{h.source}</td>
                    <td className="px-2 py-2">
                      <span className="inline-flex items-center gap-1.5 font-mono">
                        <span className={`size-2 rounded-full ${h.success ? "bg-positive" : "bg-negative"}`} />
                        {h.success ? "ok" : "dead"}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-right font-mono">{h.httpStatus ?? "—"}</td>
                    <td className="px-2 py-2 text-right font-mono">{h.latencyMs !== null ? `${h.latencyMs}ms` : "—"}</td>
                    <td className="px-2 py-2 text-right font-mono">
                      {h.rowsGot ?? "—"}/{h.rowsExpected ?? "—"}
                    </td>
                    <td className="px-2 py-2 text-right font-mono">{h.nullRate !== null ? (h.nullRate * 100).toFixed(0) + "%" : "—"}</td>
                    <td className="px-2 py-2 text-right font-mono">{fmtAgeSec(h.ageSec)}</td>
                    <td className="px-2 py-2 text-right font-mono text-muted">{h.tsSemantics ?? "—"}</td>
                    <td className="max-w-56 truncate px-2 py-2 font-mono text-[10px] text-negative" title={h.error ?? ""}>
                      {h.error ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data && data.health.length === 0 && (
              <p className="px-3 py-6 text-center text-xs text-muted">
                {data.ok ? "还没有健康行" : "等待数据"}
              </p>
            )}
          </div>
        </Card>

        {/* 最近 bar 摘要 + 告警流水 */}
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="最近 30 个小时">
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 border-b border-line bg-surface">
                  <tr>
                    <Th>bar (UTC)</Th>
                    <Th>在榜</Th>
                    <Th>命中</Th>
                    <Th>放行</Th>
                  </tr>
                </thead>
                <tbody>
                  {data?.bars.map((b) => (
                    <tr key={b.ts} className="border-b border-line/60 last:border-b-0">
                      <td className="px-2 py-1.5 font-mono">{barUtc(b.ts)}</td>
                      <td className="px-2 py-1.5 text-right font-mono">{b.universe}</td>
                      <td className="px-2 py-1.5 text-right font-mono text-primary">{b.hits}</td>
                      <td className="px-2 py-1.5 text-right font-mono text-positive">{b.fired}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="告警流水（最近 48 小时）">
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 border-b border-line bg-surface">
                  <tr>
                    <Th>时间 (UTC)</Th>
                    <Th>币</Th>
                    <Th>状态</Th>
                    <Th>通知</Th>
                  </tr>
                </thead>
                <tbody>
                  {data?.alerts.slice(0, 80).map((a) => (
                    <tr key={`${a.symbol}-${a.barOpenTs}-${a.state}`} className="border-b border-line/60 last:border-b-0">
                      <td className="px-2 py-1.5 font-mono">{barUtc(a.barOpenTs)}</td>
                      <td className="px-2 py-1.5 font-mono">{a.symbol}</td>
                      <td className="px-2 py-1.5">{STATE_LABEL[a.state] || a.state}</td>
                      <td className="px-2 py-1.5 text-right font-mono text-[10px] text-muted">
                        {a.suppressed ? "抑制" : "放行"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data && data.alerts.length === 0 && (
                <p className="px-3 py-6 text-center text-xs text-muted">{data.ok ? "48 小时内无告警" : "等待数据"}</p>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
