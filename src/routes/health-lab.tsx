import { useEffect, useRef, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  CHAIN_LABEL,
  SOURCE_LABEL,
  fmtAge,
  labVerdict,
  type HealthSource,
} from "@/lib/rh/market-status";

export const Route = createFileRoute("/health-lab")({
  component: HealthLab,
});

const WINDOW_SEC = 120;

function HealthLab() {
  const started = useRef(Date.now());
  const baseline = useRef<Record<string, number> | null>(null);
  const [sources, setSources] = useState<HealthSource[]>([]);
  const [err, setErr] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const t = setInterval(() => {
      const sec = Math.floor((Date.now() - started.current) / 1000);
      setElapsed(sec);
      if (sec >= WINDOW_SEC) setDone(true);
    }, 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let stop = false;
    async function pull() {
      try {
        const res = await fetch("/api/health/market");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as { sources: HealthSource[] };
        if (stop) return;
        if (!baseline.current) {
          baseline.current = Object.fromEntries(body.sources.map((s) => [`${s.source}:${s.chain}`, s.successes]));
        }
        setSources(body.sources);
        setErr("");
        await fetch("/api/health/market", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ reportUi: true }),
        });
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

  const left = Math.max(0, WINDOW_SEC - elapsed);

  return (
    <main className="mx-auto max-w-[1400px] px-4 py-6">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-lg font-medium">数据源观测</h1>
          <p className="mt-1 text-sm text-muted">
            {done ? "2 分钟窗口已结束，表继续刷新。" : `连续观察中，还剩 ${left}s。`}
            通过条件是成功次数在涨，并且 api_age 落在该源周期内。价格不跳不算失败。
          </p>
        </div>
        <Link to="/" hash="sec-market" className="font-mono text-sm text-brass hover:underline">
          返回市场
        </Link>
      </div>
      {err && <p className="mb-3 rounded-lg border border-clay/30 bg-clay/10 p-3 text-sm text-clay">{err}</p>}
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-line bg-surface-2 text-muted">
              <th className="px-3 py-2 font-mono">source</th>
              <th className="px-3 py-2 font-mono">chain</th>
              <th className="px-3 py-2 font-mono text-right">attempts</th>
              <th className="px-3 py-2 font-mono text-right">successes</th>
              <th className="px-3 py-2 font-mono text-right">hot</th>
              <th className="px-3 py-2 font-mono text-right">cold</th>
              <th className="px-3 py-2 font-mono text-right">api_age</th>
              <th className="px-3 py-2 font-mono text-right">db_age</th>
              <th className="px-3 py-2 font-mono text-right">p95</th>
              <th className="px-3 py-2 font-mono">last_error</th>
              <th className="px-3 py-2 font-mono">判定</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => {
              const key = `${s.source}:${s.chain}`;
              const base = baseline.current?.[key] ?? s.successes;
              const delta = s.successes - base;
              const verdict = labVerdict({
                periodSec: s.periodSec,
                successDelta: delta,
                apiAgeSec: s.apiAgeSec,
                windowDone: done,
              });
              const tone =
                verdict.state === "pass"
                  ? "text-moss"
                  : verdict.state === "fail"
                    ? "text-clay"
                    : "text-muted";
              return (
                <tr key={key} className="border-b border-line/50">
                  <td className="px-3 py-2">{SOURCE_LABEL[s.source] || s.source}</td>
                  <td className="px-3 py-2">{CHAIN_LABEL[s.chain] || s.chain}</td>
                  <td className="px-3 py-2 text-right font-mono">{s.attempts}</td>
                  <td className="px-3 py-2 text-right font-mono">{s.successes}</td>
                  <td className="px-3 py-2 text-right font-mono">{s.hotChanged}</td>
                  <td className="px-3 py-2 text-right font-mono">{s.coldChanged}</td>
                  <td className="px-3 py-2 text-right font-mono">{fmtAge(s.apiAgeSec)}</td>
                  <td className="px-3 py-2 text-right font-mono">{fmtAge(s.dbAgeSec)}</td>
                  <td className="px-3 py-2 text-right font-mono">{s.p95LatencyMs != null ? `${s.p95LatencyMs}ms` : "—"}</td>
                  <td className="max-w-64 truncate px-3 py-2 font-mono text-clay" title={s.lastError || ""}>
                    {s.lastError || "—"}
                  </td>
                  <td className={`px-3 py-2 font-mono ${tone}`}>{verdict.text}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {sources.length === 0 && !err && <p className="p-8 text-center text-muted">正在读取健康表</p>}
      </div>
    </main>
  );
}
