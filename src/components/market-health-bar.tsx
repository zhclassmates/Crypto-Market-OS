import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  CHAIN_LABEL,
  CHAINS,
  SOURCE_LABEL,
  fmtAge,
  type HealthSource,
  type MarketStatus,
} from "@/lib/rh/market-status";

const DOT: Record<MarketStatus, string> = {
  LIVE: "bg-positive",
  healthy: "bg-positive",
  DELAYED: "bg-primary",
  rate_limited: "bg-primary",
  cooldown: "bg-primary",
  STALE: "bg-negative",
  zero_write: "bg-negative",
  FAILED: "bg-negative",
  failed: "bg-negative",
  unsupported: "bg-line",
};

function clock(ts: number | null): string {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("zh-CN", { hour12: false });
}

export function MarketHealthBar() {
  const [sources, setSources] = useState<HealthSource[] | null>(null);
  const [err, setErr] = useState("");
  const [seenAt, setSeenAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let stop = false;
    async function pull() {
      try {
        const res = await fetch("/api/health/market");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await res.json();
        const reported = await fetch("/api/health/market", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ reportUi: true }),
        });
        if (!reported.ok) throw new Error(`HTTP ${reported.status}`);
        const body = (await reported.json()) as { sources: HealthSource[] };
        if (!stop) {
          setSources(body.sources);
          setSeenAt(Date.now());
          setErr("");
        }
      } catch (e) {
        if (!stop) setErr(e instanceof Error ? e.message : String(e));
      }
    }
    pull();
    const t = setInterval(pull, 5000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, []);

  return (
    <section className="mb-4 rounded-xl border border-line bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-3 py-2">
        <h2 className="font-mono text-xs tracking-wide text-fg">DATA HEALTH</h2>
        <Link to="/health-lab" className="font-mono text-xs text-primary hover:underline">
          2 分钟观测
        </Link>
      </div>
      {err && <p className="px-3 py-2 text-xs text-negative">{err}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-line text-muted">
              <th className="px-3 py-2 font-mono">链</th>
              <th className="px-3 py-2 font-mono">状态</th>
              <th className="px-3 py-2 font-mono">API age</th>
              <th className="px-3 py-2 font-mono">DB age</th>
              <th className="px-3 py-2 font-mono">hot/rows</th>
              <th className="px-3 py-2 font-mono">latency</th>
              <th className="px-3 py-2 font-mono">last_error</th>
              <th className="px-3 py-2 font-mono">心跳</th>
              <th className="px-3 py-2 font-mono">API 成功</th>
              <th className="px-3 py-2 font-mono">数据变化</th>
              <th className="px-3 py-2 font-mono">落库</th>
              <th className="px-3 py-2 font-mono">UI 拉取</th>
            </tr>
          </thead>
          <tbody>
            {CHAINS.map((chain) => {
              const group = (sources ?? []).filter((s) => s.chain === chain);
              // 链总状态只看主 GMGN。其余源只在芯片里显示，不参与汇总。
              const gmgn = group.find((s) => s.source === "gmgn");
              const status = gmgn?.status ?? null;
              const drift = Math.max(0, Math.floor((now - seenAt) / 1000));
              const liveAge = (sec: number | null) => (sec == null ? null : sec + drift);
              const apiAge = liveAge(gmgn?.apiAgeSec ?? null);
              const dbAge = liveAge(gmgn?.dbAgeSec ?? null);
              return (
                <tr key={chain} className="border-b border-line/60 align-top last:border-b-0">
                  <td className="px-3 py-2">
                    <div className="font-medium">{CHAIN_LABEL[chain]}</div>
                    <div className="mt-1 flex max-w-56 flex-wrap gap-1">
                      {group.map((s) => (
                        <span
                          key={s.source}
                          className="rounded border border-line px-1 font-mono text-[10px] text-muted"
                          title={s.lastError || s.status}
                        >
                          <span className={`mr-1 inline-block size-1.5 rounded-full ${DOT[s.status]}`} />
                          {SOURCE_LABEL[s.source] || s.source} {fmtAge(liveAge(s.apiAgeSec))}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1 font-mono">
                      <span className={`size-2 rounded-full ${DOT[status ?? "STALE"]}`} />
                      {status ?? "—"}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono">{fmtAge(apiAge == null ? null : Math.max(0, apiAge))}</td>
                  <td className="px-3 py-2 font-mono">{fmtAge(dbAge)}</td>
                  <td className="px-3 py-2 font-mono">
                    {gmgn ? `${gmgn.hotChanged}/${gmgn.rowsReceived}` : "—"}
                  </td>
                  <td className="px-3 py-2 font-mono">{gmgn?.latencyMs != null ? `${gmgn.latencyMs}ms` : "—"}</td>
                  <td className="max-w-40 truncate px-3 py-2 font-mono text-negative" title={gmgn?.lastError || ""}>
                    {gmgn?.lastError || "—"}
                  </td>
                  <td className="px-3 py-2 font-mono" title="collector_heartbeat">{clock(gmgn?.collectorHeartbeat ?? null)}</td>
                  <td className="px-3 py-2 font-mono" title="last_success">{clock(gmgn?.lastSuccess ?? null)}</td>
                  <td className="px-3 py-2 font-mono" title="last_change_at">{clock(gmgn?.lastChangeAt ?? null)}</td>
                  <td className="px-3 py-2 font-mono" title="db_written_at">{clock(gmgn?.dbWrittenAt ?? null)}</td>
                  <td className="px-3 py-2 font-mono" title="ui_fetched_at">{clock(gmgn?.uiFetchedAt ?? null)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="px-3 py-2 text-[11px] text-muted">
        主行状态和时钟都只看 GMGN。芯片是该链每个源自己的 API age。心跳活着、API 成功时间停住，就是旧数据。
      </p>
    </section>
  );
}
