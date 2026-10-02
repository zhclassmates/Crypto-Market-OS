import { useEffect, useMemo, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { ArrowUp, ArrowDown, Minus, Trash2, FileJson, RefreshCw, Database } from "lucide-react";
import { fetchKlineBoard } from "@/lib/rh/kline-server";

interface Candle {
  ts: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

interface TokenStreak {
  chain: string;
  address: string;
  label: string | null;
  days: number;
  pattern: string;
  upDays: number;
  downDays: number;
  flatDays: number;
  latestClose: string;
  candles: Candle[];
}

function dateStr(ts: number): string {
  return new Date(ts * 1000).toISOString().slice(0, 10);
}

function shortAddr(a: string): string {
  return a.length > 14 ? a.slice(0, 8) + "…" + a.slice(-6) : a;
}

function MarkCell({ mark }: { mark: string }) {
  if (mark === "+")
    return (
      <span className="inline-flex items-center gap-1 text-moss">
        <ArrowUp className="size-3" />
        涨
      </span>
    );
  if (mark === "-")
    return (
      <span className="inline-flex items-center gap-1 text-clay">
        <ArrowDown className="size-3" />
        跌
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-muted">
      <Minus className="size-3" />
      平
    </span>
  );
}

function PatternBar({ pattern }: { pattern: string }) {
  if (!pattern) return <span className="text-xs text-muted">—</span>;
  return (
    <div className="flex w-max flex-nowrap gap-1">
      {pattern.split("").map((ch, i) => (
        <span
          key={i}
          className={
            "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-sm text-xs font-mono " +
            (ch === "+"
              ? "bg-moss/15 text-moss border border-moss/30"
              : ch === "-"
                ? "bg-clay/15 text-clay border border-clay/30"
                : "bg-surface-2 text-muted border border-line")
          }
        >
          {ch}
        </span>
      ))}
    </div>
  );
}

function TokenDetail({ token, days }: { token: TokenStreak; days: number }) {
  // 按天数截取最近 N 根
  const candles = token.candles.slice(-days);
  if (candles.length < 2) {
    return <p className="text-sm text-muted">数据不足 2 根</p>;
  }

  const marks: string[] = [];
  for (let i = 1; i < candles.length; i++) {
    const prev = Number(candles[i - 1].close);
    const curr = Number(candles[i].close);
    marks.push(curr > prev ? "+" : curr < prev ? "-" : "=");
  }
  const run = (t: string) => {
    let c = 0;
    for (let i = marks.length - 1; i >= 0; i--) {
      if (marks[i] !== t) break;
      c++;
    }
    return c;
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-line bg-surface p-3 text-center">
          <p className="font-mono text-xs text-muted">连涨</p>
          <p className={`mt-1 text-2xl font-mono font-medium ${run("+") > 0 ? "text-moss" : "text-muted"}`}>
            {run("+")}
          </p>
        </div>
        <div className="rounded-lg border border-line bg-surface p-3 text-center">
          <p className="font-mono text-xs text-muted">连跌</p>
          <p className={`mt-1 text-2xl font-mono font-medium ${run("-") > 0 ? "text-clay" : "text-muted"}`}>
            {run("-")}
          </p>
        </div>
        <div className="rounded-lg border border-line bg-surface p-3 text-center">
          <p className="font-mono text-xs text-muted">持平</p>
          <p className={`mt-1 text-2xl font-mono font-medium ${run("=") > 0 ? "text-brass" : "text-muted"}`}>
            {run("=")}
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-line bg-surface p-3">
        <p className="mb-2 font-mono text-xs text-muted">涨跌序列</p>
        <div className="overflow-x-auto">
          <PatternBar pattern={marks.join("")} />
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-line bg-surface-2 text-xs text-muted">
              <th className="px-3 py-2 font-mono">日期</th>
              <th className="px-3 py-2 font-mono">前收</th>
              <th className="px-3 py-2 font-mono">收盘</th>
              <th className="px-3 py-2 font-mono">标记</th>
              <th className="px-3 py-2 font-mono text-right">涨跌幅</th>
            </tr>
          </thead>
          <tbody>
            {candles.slice(1).map((c, i) => {
              const prev = candles[i];
              const mark = marks[i];
              const change = Number(c.close) - Number(prev.close);
              const pct = Number(prev.close) !== 0 ? (change / Number(prev.close)) * 100 : 0;
              return (
                <tr key={c.ts} className="border-b border-line/50 last:border-b-0">
                  <td className="px-3 py-2 font-mono text-xs">{dateStr(c.ts)}</td>
                  <td className="px-3 py-2 font-mono text-xs">{prev.close}</td>
                  <td className="px-3 py-2 font-mono text-xs">{c.close}</td>
                  <td className="px-3 py-2">
                    <MarkCell mark={mark} />
                  </td>
                  <td
                    className={`px-3 py-2 font-mono text-xs text-right ${
                      mark === "+" ? "text-moss" : mark === "-" ? "text-clay" : "text-muted"
                    }`}
                  >
                    {pct > 0 ? "+" : ""}
                    {pct.toFixed(2)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function JsonMode() {
  const [jsonText, setJsonText] = useState("");
  const [keepForming, setKeepForming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const result = useMemo(() => {
    setError(null);
    if (!jsonText.trim()) return null;
    try {
      const raw = JSON.parse(jsonText);
      let rows: unknown = raw;
      if (typeof raw === "object" && raw !== null) {
        const obj = raw as Record<string, unknown>;
        if ("list" in obj) rows = obj.list;
        else if ("ohlcv_list" in obj) rows = obj.ohlcv_list;
      }
      if (!Array.isArray(rows)) throw new Error("K 线必须是数组");
      const candles: { ts: number; close: string }[] = [];
      for (const row of rows) {
        if (typeof row === "object" && row !== null && "close" in row && "time" in row) {
          const r = row as Record<string, unknown>;
          let t = Number(r.time);
          if (t >= 1e12) t = Math.floor(t / 1000);
          candles.push({ ts: t, close: String(r.close) });
        }
      }
      candles.sort((a, b) => a.ts - b.ts);
      const used = keepForming ? candles : candles.slice(0, -1);
      if (used.length < 2) throw new Error("不足 2 根");
      const marks: string[] = [];
      for (let i = 1; i < used.length; i++) {
        const p = Number(used[i - 1].close);
        const c = Number(used[i].close);
        marks.push(c > p ? "+" : c < p ? "-" : "=");
      }
      const run = (t: string) => {
        let c = 0;
        for (let i = marks.length - 1; i >= 0; i--) {
          if (marks[i] !== t) break;
          c++;
        }
        return c;
      };
      return { pattern: marks.join(""), upDays: run("+"), downDays: run("-"), days: used.length };
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [jsonText, keepForming]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileJson className="size-4 text-brass" />
          <span className="text-sm font-medium">粘贴 JSON（GMGN / GeckoTerminal）</span>
        </div>
        <button
          type="button"
          onClick={() => setJsonText("")}
          className="inline-flex items-center gap-1 rounded-full border border-line px-3 py-1 text-xs text-muted hover:text-fg"
        >
          <Trash2 className="size-3" />
          清空
        </button>
      </div>
      <textarea
        value={jsonText}
        onChange={(e) => setJsonText(e.target.value)}
        rows={10}
        className="rounded-lg border border-line bg-bg p-3 font-mono text-xs leading-relaxed text-fg focus:border-brass focus:outline-none"
        spellCheck={false}
      />
      <label className="flex items-center gap-2 text-sm text-muted">
        <input
          type="checkbox"
          checked={keepForming}
          onChange={(e) => setKeepForming(e.target.checked)}
          className="size-4 accent-brass"
        />
        保留未收盘的今日 K
      </label>
      {error && <p className="text-sm text-clay">{error}</p>}
      {result && (
        <div className="grid grid-cols-4 gap-3">
          <div className="rounded-lg border border-line bg-surface p-3 text-center">
            <p className="font-mono text-xs text-muted">连涨</p>
            <p className={`mt-1 text-2xl font-mono ${result.upDays > 0 ? "text-moss" : "text-muted"}`}>
              {result.upDays}
            </p>
          </div>
          <div className="rounded-lg border border-line bg-surface p-3 text-center">
            <p className="font-mono text-xs text-muted">连跌</p>
            <p className={`mt-1 text-2xl font-mono ${result.downDays > 0 ? "text-clay" : "text-muted"}`}>
              {result.downDays}
            </p>
          </div>
          <div className="rounded-lg border border-line bg-surface p-3 text-center col-span-2">
            <p className="font-mono text-xs text-muted">Pattern</p>
            <p className="mt-1 font-mono text-lg text-fg">{result.pattern || "—"}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export function StreakView() {
  const [mode, setMode] = useState<"live" | "json">("live");
  const [data, setData] = useState<{ ok: boolean; tokens: TokenStreak[]; lastRun?: string; error?: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [days, setDays] = useState(15);

  const boardFn = useServerFn(fetchKlineBoard);

  async function refresh() {
    setLoading(true);
    try {
      const res = await boardFn();
      setData(res);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const selectedToken = data?.tokens.find((t) => `${t.chain}:${t.address}` === selected) ?? null;

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      {/* 模式切换 */}
      <div className="mb-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setMode("live")}
          className={
            "inline-flex items-center gap-1 rounded-full border px-3 py-1.5 text-sm " +
            (mode === "live" ? "border-brass text-fg" : "border-line text-muted")
          }
        >
          <Database className="size-4" />
          实时监控
        </button>
        <button
          type="button"
          onClick={() => setMode("json")}
          className={
            "inline-flex items-center gap-1 rounded-full border px-3 py-1.5 text-sm " +
            (mode === "json" ? "border-brass text-fg" : "border-line text-muted")
          }
        >
          <FileJson className="size-4" />
          粘贴 JSON
        </button>
      </div>

      {mode === "json" ? (
        <JsonMode />
      ) : (
        <div className="flex flex-col gap-4">
          {/* 监控列表头部 */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">监控列表</p>
              {data?.lastRun && (
                <p className="text-xs text-muted">
                  最近采集: {new Date(JSON.parse(data.lastRun).ts * 1000).toLocaleString("zh-CN")}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={refresh}
              disabled={loading}
              className="inline-flex items-center gap-1 rounded-full border border-line px-3 py-1.5 text-sm text-muted hover:text-fg disabled:opacity-50"
            >
              <RefreshCw className={"size-4 " + (loading ? "animate-spin" : "")} />
              刷新
            </button>
          </div>

          {data?.error && <p className="rounded-lg border border-clay/30 bg-clay/10 p-3 text-sm text-clay">{data.error}</p>}

          {data?.ok && data.tokens.length > 0 ? (
            <>
              {/* 监控代币表格 */}
              <div className="overflow-x-auto rounded-xl border border-line">
                <table className="w-full min-w-[840px] table-fixed text-left text-sm">
                  <thead>
                    <tr className="border-b border-line bg-surface-2 text-xs text-muted">
                      <th className="w-[22%] px-4 py-2 font-mono">代币</th>
                      <th className="w-[7%] px-4 py-2 font-mono">链</th>
                      <th className="w-[14%] px-4 py-2 font-mono text-right">最新收盘</th>
                      <th className="w-[7%] px-4 py-2 font-mono text-center">连涨</th>
                      <th className="w-[7%] px-4 py-2 font-mono text-center">连跌</th>
                      <th className="w-[35%] px-4 py-2 font-mono">Pattern</th>
                      <th className="w-[8%] px-4 py-2 font-mono text-right">天数</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.tokens.map((t) => {
                      const key = `${t.chain}:${t.address}`;
                      return (
                        <tr
                          key={key}
                          onClick={() => setSelected(selected === key ? null : key)}
                          className={
                            "cursor-pointer border-b border-line/50 last:border-b-0 transition-colors " +
                            (selected === key ? "bg-surface" : "hover:bg-surface/50")
                          }
                        >
                          <td className="px-4 py-2">
                            <span className="block truncate font-medium">{t.label || shortAddr(t.address)}</span>
                          </td>
                          <td className="px-4 py-2 font-mono text-xs text-muted">{t.chain}</td>
                          <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-right">{t.latestClose}</td>
                          <td className="px-4 py-2 text-center">
                            <span className={t.upDays > 0 ? "font-mono font-medium text-moss" : "font-mono text-muted"}>
                              {t.upDays}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-center">
                            <span className={t.downDays > 0 ? "font-mono font-medium text-clay" : "font-mono text-muted"}>
                              {t.downDays}
                            </span>
                          </td>
                          <td className="px-4 py-2">
                            <div className="w-full overflow-x-auto">
                              <PatternBar pattern={t.pattern} />
                            </div>
                          </td>
                          <td className="px-4 py-2 font-mono text-xs text-right text-muted">{t.days}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* 选中代币的详情 */}
              {selectedToken && (
                <div className="flex flex-col gap-4 rounded-xl border border-line bg-surface p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-lg font-medium">{selectedToken.label || shortAddr(selectedToken.address)}</p>
                      <p className="font-mono text-xs text-muted">
                        [{selectedToken.chain}] {selectedToken.address}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted">天数范围:</span>
                      {[7, 15, 30].map((d) => (
                        <button
                          key={d}
                          type="button"
                          onClick={() => setDays(d)}
                          className={
                            "rounded-full border px-3 py-1 text-xs " +
                            (days === d ? "border-brass text-fg" : "border-line text-muted")
                          }
                        >
                          {d} 天
                        </button>
                      ))}
                    </div>
                  </div>
                  <TokenDetail token={selectedToken} days={days} />
                </div>
              )}
            </>
          ) : (
            !loading && (
              <div className="rounded-xl border border-line bg-surface p-8 text-center">
                <p className="text-muted">暂无日 K 数据</p>
                <p className="mt-1 text-xs text-muted">
                  先跑 <code className="font-mono text-brass">python3 rh_v2/market_run.py once</code> 采集全市场日 K
                </p>
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}
