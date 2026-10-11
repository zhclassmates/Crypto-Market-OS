import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, RefreshCw } from "lucide-react";
import { finalChecks, replay, T0 } from "@/lib/rh/engine";
import { num, pct, stamp, usd } from "@/lib/rh/format";
import { collect } from "@/lib/rh/live";
import { scoreBoard, type Prior, type PriorState } from "@/lib/rh/live-score";
import type { CollectOk } from "@/lib/rh/collect-core";
import type { Part, Scored } from "@/lib/rh/types";

const STATE_CLASS: Record<string, string> = {
  READY: "text-positive",
  RESEARCH: "text-primary",
  ACCELERATING: "text-fg",
  WATCH: "text-muted",
  OVERHEATED: "text-negative",
  INVALID: "text-muted",
};

const DOT: Record<string, string> = {
  READY: "bg-positive",
  RESEARCH: "bg-primary",
  ACCELERATING: "bg-fg",
  WATCH: "bg-line",
  OVERHEATED: "bg-negative",
  INVALID: "bg-line",
};

function Replay() {
  const full = useMemo(() => replay(9), []);
  const checks = useMemo(() => finalChecks(full), [full]);
  const [hour, setHour] = useState(9);
  const [play, setPlay] = useState(false);
  const [symbol, setSymbol] = useState("RISER");
  const frame = useMemo(() => replay(hour), [hour]);
  const row = frame.rows.find((r) => r.symbol === symbol) ?? frame.rows[0];

  useEffect(() => {
    if (!play) return;
    const id = window.setInterval(() => {
      setHour((h) => {
        if (h >= 9) {
          setPlay(false);
          return 9;
        }
        return h + 1;
      });
    }, 800);
    return () => window.clearInterval(id);
  }, [play]);

  return (
    <div className="flex flex-col gap-6 py-4">
      <div className="max-w-3xl text-sm text-pretty text-muted">
        <p>
          四列分开看，没有综合分。Heat 看加速度，Quality 看池子干不干净，ListingP 是频率不是回归，Entry 防止「更可能上、但已经涨完」。
          下面五条是成型行情，不连网，只用来核对公式。把滑杆拉回第 1 小时，RISER 还进不了 READY。
        </p>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => {
              if (hour >= 9) setHour(0);
              setPlay((p) => !p);
            }}
            className="inline-flex min-h-11 items-center gap-2 rounded-full border border-line px-4 text-sm"
          >
            {play ? <Pause className="size-4" /> : <Play className="size-4" />}
            {play ? "暂停" : hour >= 9 ? "从头播放" : "播放"}
          </button>
          <label className="flex min-w-48 flex-1 items-center gap-3 text-sm">
            <span className="font-mono text-xs text-muted">第 {hour + 1}/10 小时</span>
            <input
              type="range"
              min={0}
              max={9}
              value={hour}
              onChange={(e) => {
                setPlay(false);
                setHour(Number(e.target.value));
              }}
              className="w-full accent-primary"
            />
          </label>
          <span className="font-mono text-xs text-muted">{stamp(frame.now * 1000)}</span>
        </div>
        <p className="text-xs text-muted">
          剧本时钟从 {stamp(T0 * 1000)} 起。观察池门槛：池深 ≥ $25k 且 24h 成交 ≥ $20k。升级立刻生效，降级要连续 2 小时，过热和失效立刻生效。
        </p>
        {frame.alerts.length ? (
          <p className="text-sm text-positive">本小时新进入：{frame.alerts.join(" · ")}</p>
        ) : (
          <p className="text-xs text-muted">本小时没有新的 READY / RESEARCH。</p>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="max-w-full overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full min-w-max border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                {["状态", "币", "Heat", "Quality", "ListingP", "Entry", "池深", "24h", "24h%", "量比 6/18"].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {frame.rows.map((r) => (
                <tr
                  key={r.address}
                  onClick={() => setSymbol(r.symbol)}
                  className={"cursor-pointer border-t border-line " + (row?.symbol === r.symbol ? "bg-surface-2" : "hover:bg-bg")}
                >
                  <td className={"px-3 py-2 font-medium " + (STATE_CLASS[r.state] ?? "")}>{r.state}</td>
                  <td className="px-3 py-2">
                    <div className="font-mono">{r.symbol}</div>
                    <Trail states={full.history[r.symbol] ?? []} hour={hour} />
                  </td>
                  <td className="px-3 py-2 font-mono tabular-nums">{num(r.heat, 0)}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{num(r.quality, 0)}</td>
                  <td className="px-3 py-2 font-mono">{r.listingP}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{num(r.entry, 0)}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{usd(r.liq)}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{usd(r.vol24)}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{pct(r.pc24)}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{r.volAccel == null ? "–" : `${r.volAccel.toFixed(1)}x`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-3 py-2 text-xs text-muted">DUST 池深 $3k，这一小时不在表里。色点是 10 小时的状态，亮的是当前小时。</p>
        </div>
        {row ? <Inspector row={row} /> : null}
      </div>

      <section className="rounded-xl border border-line bg-surface p-4">
        <h2 className="text-sm font-medium">ListingP 频率表</h2>
        <p className="mt-1 text-xs text-pretty text-muted">
          样本不到 20 的格子写「不定」，不给一个看起来很精确的百分比。上 Alpha 还不满窗口的币不进分母。永续比 Alpha 早一天以上的，当撞名剔掉。
        </p>
        <div className="mt-3 max-w-full overflow-x-auto">
          <table className="w-full min-w-max border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="py-1 pr-3 font-medium">格子</th>
                {["7 天", "30 天", "90 天"].map((h) => (
                  <th key={h} className="px-3 py-1 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {frame.rates.map((r) => (
                <tr key={r.id} className="border-t border-line">
                  <td className="py-2 pr-3">{r.label}</td>
                  {r.cells.map((c, i) => (
                    <td key={i} className="px-3 py-2 font-mono tabular-nums">
                      {c.n == null ? "–" : c.p == null ? `${c.n} 不定` : `${c.n} · ${c.p.toFixed(0)}%`}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-xl border border-line p-4">
        <h2 className="text-sm font-medium">跑满 10 小时后的自检</h2>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {checks.map((c) => (
            <li key={c.label} className="flex items-start gap-2 text-sm">
              <span className={"mt-1 size-2 shrink-0 rounded-full " + (c.ok ? "bg-positive" : "bg-negative")} />
              <span className={c.ok ? "text-fg" : "text-negative"}>{c.label}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Trail({ states, hour }: { states: string[]; hour: number }) {
  return (
    <span className="mt-1 flex gap-0.5" aria-hidden>
      {Array.from({ length: 10 }, (_, i) => (
        <span key={i} className={"h-1.5 w-2 rounded-sm " + (i < states.length ? (DOT[states[i]!] ?? "bg-line") : "bg-line") + (i === hour ? " ring-1 ring-fg" : "")} />
      ))}
    </span>
  );
}

function Inspector({ row }: { row: Scored }) {
  return (
    <aside className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-mono text-lg">{row.symbol}</h2>
        <span className={"text-sm font-medium " + (STATE_CLASS[row.state] ?? "")}>{row.state}</span>
      </div>
      <p className="mt-1 text-xs text-pretty text-muted">{row.why.join(" · ")}</p>
      <p className="mt-2 text-xs text-pretty text-muted">
        上所 {row.venues} · 自有快照 {row.nHist}h · 持币 {row.holders?.toLocaleString("en-US") ?? "–"}
      </p>
      <p className="mt-1 text-xs text-pretty text-primary">{row.listingBasis}</p>
      <Block title="Heat" score={row.heat} parts={row.heatParts} />
      <Block title="Quality" score={row.quality} parts={row.qualityParts} />
      <div className="mt-4">
        <div className="flex items-baseline justify-between">
          <h3 className="text-xs text-muted">Entry</h3>
          <span className="font-mono tabular-nums">{num(row.entry, 1)}</span>
        </div>
        <ul className="mt-2 space-y-1 text-xs text-muted">
          {row.entryNotes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

function Block({ title, score, parts }: { title: string; score: number | null; parts: Part[] }) {
  return (
    <div className="mt-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs text-muted">{title}</h3>
        <span className="font-mono tabular-nums">{num(score, 1)}</span>
      </div>
      <ul className="mt-2 flex flex-col gap-2">
        {parts.map((p) => (
          <li key={p.label}>
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span>
                {p.label}
                <span className="text-muted"> · {p.weight}</span>
              </span>
              <span className="font-mono text-muted">{p.raw}</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-bg">
              <div className="h-full rounded-full bg-primary" style={{ width: `${(p.mapped ?? 0) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

const STORE = "rhv2-live-v1";

function loadStore(): { priors: Prior[]; states: PriorState[] } {
  try {
    const raw = localStorage.getItem(STORE);
    if (!raw) return { priors: [], states: [] };
    const d = JSON.parse(raw) as { priors?: Prior[]; states?: PriorState[] };
    return { priors: d.priors ?? [], states: d.states ?? [] };
  } catch {
    return { priors: [], states: [] };
  }
}

export function ScoreView() {
  const store = useRef(loadStore());
  const [nonce, setNonce] = useState(0);
  const [status, setStatus] = useState<"run" | "ok" | "err">("run");
  const [err, setErr] = useState("");
  const [pack, setPack] = useState<CollectOk | null>(null);
  const [rows, setRows] = useState<Scored[]>([]);
  const [symbol, setSymbol] = useState<string | null>(null);

  useEffect(() => {
    let cancel = false;
    setStatus("run");
    setErr("");
    collect()
      .then((res) => {
        if (cancel) return;
        if (!res.ok) {
          setStatus("err");
          setErr(res.error);
          return;
        }
        const { priors, states } = store.current;
        const scored = scoreBoard(res.ts, res.tokens, res.alpha, priors, states);
        const hour = res.ts - (res.ts % 3600);
        const kept = priors.filter((p) => p.ts < hour && p.ts > hour - 48 * 3600);
        for (const r of scored.rows) {
          kept.push({
            address: r.address,
            ts: hour,
            price: r.price || null,
            holders: r.holders,
            heat: r.heat,
          });
        }
        store.current = { priors: kept.slice(-2000), states: scored.nextStates };
        try {
          localStorage.setItem(STORE, JSON.stringify(store.current));
        } catch {
          /* 配额满了就只显示这一轮 */
        }
        setPack(res);
        setRows(scored.rows);
        setSymbol((cur) => (cur && scored.rows.some((r) => r.symbol === cur) ? cur : (scored.rows[0]?.symbol ?? null)));
        setStatus("ok");
      })
      .catch((e: unknown) => {
        if (cancel) return;
        setStatus("err");
        setErr(e instanceof Error ? e.message : "这一轮没跑完");
      });
    return () => {
      cancel = true;
    };
  }, [nonce]);

  const row = rows.find((r) => r.symbol === symbol) ?? rows[0];

  return (
    <div id="sec-score" className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6">
      <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-medium">这一轮是现拉的</h2>
          <p className="mt-1 max-w-2xl text-xs text-pretty text-muted">
            GeckoTerminal 找池子，DexScreener 拉近 1h / 6h / 24h 的量和笔数，币安 Alpha 按合约地址对。观察池仍然是池深 ≥ $25k 且 24h 成交 ≥ $20k。第一轮没有 6 小时自有快照，所以不会给 READY。
          </p>
        </div>
        <button
          type="button"
          onClick={() => setNonce((n) => n + 1)}
          disabled={status === "run"}
          className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-full border border-line px-4 text-sm disabled:opacity-60"
        >
          <RefreshCw className={"size-4 " + (status === "run" ? "animate-spin" : "")} />
          {status === "run" ? "正在拉" : "再跑一轮"}
        </button>
      </div>

      {status === "run" ? <p className="text-sm text-muted">正在请求 GeckoTerminal、DexScreener、币安 Alpha。</p> : null}
      {status === "err" ? <p className="text-sm text-negative">没跑成：{err}</p> : null}

      {pack ? (
        <p className="font-mono text-xs text-pretty text-muted">
          {pack.log.secs}s · {pack.log.universe} · {pack.log.gt} · {pack.log.dex} · {pack.log.alpha} · {pack.log.rhchain}
          {pack.ts ? ` · ${stamp(pack.ts * 1000)}` : ""}
        </p>
      ) : null}

      {rows.length ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="max-w-full overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full min-w-max border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  {["状态", "币", "Heat", "Quality", "ListingP", "Entry", "池深", "24h", "24h%", "量比"].map((h) => (
                    <th key={h} className="px-3 py-2 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.address}
                    onClick={() => setSymbol(r.symbol)}
                    className={"cursor-pointer border-t border-line " + (row?.address === r.address ? "bg-surface-2" : "hover:bg-bg")}
                  >
                    <td className={"px-3 py-2 font-medium " + (STATE_CLASS[r.state] ?? "")}>{r.state}</td>
                    <td className="px-3 py-2 font-mono">{r.symbol}</td>
                    <td className="px-3 py-2 font-mono tabular-nums">{num(r.heat, 0)}</td>
                    <td className="px-3 py-2 font-mono tabular-nums">{num(r.quality, 0)}</td>
                    <td className="px-3 py-2 font-mono">{r.listingP}</td>
                    <td className="px-3 py-2 font-mono tabular-nums">{num(r.entry, 0)}</td>
                    <td className="px-3 py-2 font-mono tabular-nums">{usd(r.liq)}</td>
                    <td className="px-3 py-2 font-mono tabular-nums">{usd(r.vol24)}</td>
                    <td className="px-3 py-2 font-mono tabular-nums">{pct(r.pc24)}</td>
                    <td className="px-3 py-2 font-mono tabular-nums">{r.volAccel == null ? "–" : `${r.volAccel.toFixed(1)}x`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {row ? <Inspector row={row} /> : null}
        </div>
      ) : status === "ok" ? (
        <p className="text-sm text-muted">拉到了，但没有币同时满足池深和 24h 成交门槛。</p>
      ) : null}

      <details className="rounded-xl border border-line p-4">
        <summary className="min-h-11 text-sm">公式回放（不连网，只用来核对 READY 的七条）</summary>
        <Replay />
      </details>
    </div>
  );
}
