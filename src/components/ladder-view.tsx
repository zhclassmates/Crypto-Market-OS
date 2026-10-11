import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";
import { LADDER } from "@/data/ladder";
import { kindLabel, shortAddr, stamp, turn, usd } from "@/lib/rh/format";
import { fetchLadder, fetchRhAlpha, type AlphaHit } from "@/lib/rh/live";
import type { Candidate, Gate, LadderToken } from "@/lib/rh/types";

const STEPS: { key: string; label: string }[] = [
  { key: "aster", label: "Aster" },
  { key: "hl", label: "Hyperliquid" },
  { key: "bnAlpha", label: "币安 Alpha" },
  { key: "bnPerp", label: "币安永续" },
  { key: "bnSpot", label: "币安现货" },
  { key: "kr", label: "韩所" },
];

const APP_STEPS = [
  { key: "rhQuoted", label: "有行情页" },
  { key: "rhSpot", label: "可交易" },
];

const KINDS = [
  { id: "all", label: "全部" },
  { id: "stock", label: "链上美股" },
  { id: "paired", label: "与股票配对" },
  { id: "meme", label: "纯 Meme" },
  { id: "eco", label: "生态币" },
];

const RULE_KIND: Record<string, string> = {
  published: "已公布硬性门槛",
  "published-vague": "只公布了原则",
  discretionary: "明示自由裁量、不接受申请",
  none: "无公开框架",
};

type Quick = "all" | "verifiable" | "liq" | "recent";

function rungCount(rungs: { key: string; count: number }[] | undefined, key: string) {
  if (!Array.isArray(rungs)) return 0;
  return rungs.find((r) => r.key === key)?.count ?? 0;
}

function verified(t: LadderToken) {
  return STEPS.concat(APP_STEPS).some((s) => t.reached[s.key]);
}

function recent(t: LadderToken) {
  if (!t.poolSeenAt) return false;
  return Date.now() - Date.parse(t.poolSeenAt) <= 72 * 3600 * 1000;
}

function withAlpha(base: LadderToken[], hits: AlphaHit[] | null): LadderToken[] {
  if (!hits?.length) return base;
  const next = base.map((t) => ({ ...t, reached: { ...t.reached } }));
  const byAddr = new Map(next.filter((t) => t.address).map((t) => [t.address!, t]));
  for (const h of hits) {
    const cur = byAddr.get(h.address);
    if (cur) {
      cur.reached.bnAlpha = true;
      continue;
    }
    const row: LadderToken = {
      symbol: h.symbol,
      address: h.address,
      kind: "meme",
      name: h.symbol,
      vol24h: null,
      liq: null,
      mcap: null,
      poolSeenAt: null,
      reached: {
        aster: false,
        hl: false,
        bnAlpha: true,
        bnPerp: false,
        bnSpot: false,
        kr: false,
        rhQuoted: false,
        rhSpot: false,
      },
    };
    next.push(row);
    byAddr.set(h.address, row);
  }
  return next;
}

function scoreCandidate(c: Candidate, gates: Record<string, Gate>) {
  const g = gates[c.gate] ?? gates.first;
  if (!g) return { score: null as number | null, checks: [] as { label: string; ok: boolean | null; title: string }[] };
  const vals: Record<string, number | null> = {
    liq: c.raw?.liq ?? null,
    holders: c.raw?.holders ?? null,
    mcap: c.raw?.mcap ?? null,
    ageD: c.raw?.ageD ?? null,
    ct: c.raw?.ct ?? null,
    vol24h: c.raw?.vol24h ?? null,
  };
  let got = 0;
  let known = 0;
  const checks: { label: string; ok: boolean | null; title: string }[] = [];
  for (const [k, cfg] of Object.entries(g.bars)) {
    const v = vals[k] ?? null;
    if (v == null) {
      checks.push({ label: cfg.label, ok: null, title: `${cfg.label} 这一项快照里没有，不进权重` });
      continue;
    }
    known += cfg.w;
    const ok = v >= cfg.bar;
    if (ok) got += cfg.w;
    const lift = cfg.lift ? ` · 毕业生相对没毕业的提升 ${cfg.lift} 倍` : "";
    checks.push({
      label: cfg.label,
      ok,
      title: `门槛 ${cfg.bar}，它是 ${v}，权重 ${cfg.w}${lift}${cfg.note ? ` · ${cfg.note}` : ""}`,
    });
  }
  return { score: known ? Math.round((got / known) * 100) : null, checks };
}

function Chip({
  on,
  children,
  onClick,
}: {
  on: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "min-h-11 rounded-full border px-3 text-sm " +
        (on ? "border-primary text-primary" : "border-line text-muted hover:text-fg")
      }
    >
      {children}
    </button>
  );
}

export function LadderView() {
  const [book, setBook] = useState(LADDER);
  const [fresh, setFresh] = useState("正在拉最新台阶…");
  const [kind, setKind] = useState("all");
  const [quick, setQuick] = useState<Quick>("liq");
  const [query, setQuery] = useState("");
  const [rung, setRung] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<"vol" | "liq" | "symbol">("vol");
  const [sortDir, setSortDir] = useState<-1 | 1>(-1);
  const [pick, setPick] = useState<string | null>(null);
  const [hits, setHits] = useState<AlphaHit[] | null>(null);
  const [alphaNote, setAlphaNote] = useState("可以再对一次币安 Alpha 的合约地址。");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let stop = false;
    fetchLadder().then((res) => {
      if (stop) return;
      if (!res.ok) {
        setFresh(`最新列表没拉到（${res.error}），先用上次核对过的快照。`);
        return;
      }
      setBook(res.book);
      setFresh(`台阶已重新拉过 · ${stamp(res.book.ts)}`);
    });
    return () => {
      stop = true;
    };
  }, []);

  const tokens = useMemo(() => withAlpha(book.tokens, hits), [book, hits]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = tokens.filter((t) => kind === "all" || t.kind === kind);
    if (quick === "verifiable") list = list.filter(verified);
    else if (quick === "liq") list = list.filter((t) => (t.liq || 0) >= 100_000);
    else if (quick === "recent") list = list.filter(recent);
    if (rung) list = list.filter((t) => t.reached[rung]);
    if (q) list = list.filter((t) => t.symbol.toLowerCase().includes(q) || (t.name || "").toLowerCase().includes(q));
    const val = (t: LadderToken) => (sortKey === "vol" ? t.vol24h || 0 : sortKey === "liq" ? t.liq || 0 : t.symbol);
    return [...list].sort((a, b) => {
      const x = val(a);
      const y = val(b);
      if (typeof x === "string" && typeof y === "string") return x.localeCompare(y) * sortDir;
      return ((x as number) - (y as number)) * sortDir;
    });
  }, [tokens, kind, quick, query, rung, sortKey, sortDir]);

  const selected = tokens.find((t) => t.address === pick) ?? null;

  async function refreshAlpha() {
    setBusy(true);
    const res = await fetchRhAlpha();
    setBusy(false);
    if (!res.ok) {
      setAlphaNote(res.error);
      return;
    }
    setHits(res.tokens);
    const snap = rungCount(book.rungs, "bnAlpha");
    setAlphaNote(
      res.n === snap
        ? `币安 Alpha 现有 ${res.n} 个 RH 链合约，与台阶计数一致。核对于 ${stamp(res.fetchedAt)}。`
        : `币安 Alpha 现有 ${res.n} 个 RH 链合约，快照台阶记的是 ${snap}。表里的点已按合约地址改过来。核对于 ${stamp(res.fetchedAt)}。`,
    );
  }

  function toggleSort(key: "vol" | "liq" | "symbol") {
    if (sortKey === key) setSortDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(key);
      setSortDir(key === "symbol" ? 1 : -1);
    }
  }

  const first = book.candidates
    .filter((c) => c.gate === "first")
    .map((c) => ({ c, s: scoreCandidate(c, book.gates) }))
    .filter((x) => x.s.score != null)
    .sort((a, b) => (b.s.score ?? 0) - (a.s.score ?? 0))
    .slice(0, 6);
  const cex = book.candidates
    .filter((c) => c.gate === "cex")
    .map((c) => ({ c, s: scoreCandidate(c, book.gates) }))
    .filter((x) => x.s.score != null)
    .sort((a, b) => (b.s.score ?? 0) - (a.s.score ?? 0))
    .slice(0, 4);

  return (
    <div id="sec-ladder" className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6">
      <p className="max-w-3xl text-sm text-pretty text-muted">
        只统计 Robinhood 链上的币。每一格是这些币里有多少个走到了那一级 —— 链上谁都能发，能在 App 里真正买到的是个位数。
        交易所那一路和 Robinhood App 那一路从链上分出去，互不为前提。身份按合约地址或报价偏离 8% 以内核对，只对上符号不算。
      </p>

      <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
        <Track
          label="基线"
          steps={[{ key: "onchain", label: "链上有量的币", count: rungCount(book.rungs, "onchain") }]}
          rung={rung}
          onPick={setRung}
        />
        <Track
          label="交易所"
          steps={STEPS.map((s) => ({ ...s, count: rungCount(book.rungs, s.key) }))}
          rung={rung}
          onPick={setRung}
          joiner={["dot", "dot", "arrow", "arrow", "arrow", "arrow"]}
        />
        <Track
          label="Robinhood App"
          steps={APP_STEPS.map((s) => ({ ...s, count: rungCount(book.rungs, s.key) }))}
          rung={rung}
          onPick={setRung}
          joiner={["arrow", "arrow"]}
        />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-pretty text-muted">{fresh} {alphaNote}</p>
          <button
            type="button"
            onClick={refreshAlpha}
            disabled={busy}
            className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-full border border-line px-4 text-sm text-fg hover:border-primary disabled:opacity-60"
          >
            <RefreshCw className={"size-4 " + (busy ? "animate-spin" : "")} />
            {busy ? "正在对币安" : "对一次币安 Alpha"}
          </button>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <GateCard title="离「上第一个交易所」最近" gate={book.gates.first} rows={first} onPick={setPick} />
        <GateCard title="离「从 Alpha 进币安 CEX」最近" gate={book.gates.cex} rows={cex} onPick={setPick} />
      </div>

      <section className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-line bg-surface p-4">
          <h2 className="text-sm font-medium text-negative">别被成交额骗了</h2>
          <p className="mt-1 text-xs text-muted">成交额排在前面，但换手、池深或币龄过不了硬门槛。</p>
          <ul className="mt-3 flex flex-col gap-2">
            {book.ruledOut.map((r, i) => (
              <li key={r.symbol + i} className="text-sm">
                <span className="font-mono text-fg">{r.symbol}</span>
                <span className="ml-2 font-mono text-xs text-muted">
                  24h {usd(r.vol24h)} · 池深 {usd(r.liq)}
                </span>
                <span className="mt-0.5 block text-xs text-pretty text-muted">{r.why}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl border border-line bg-surface p-4">
          <h2 className="text-sm font-medium">现实里，发射台出身的币上过几家</h2>
          <p className="mt-1 text-xs text-pretty text-muted">{book.listingHistory.note}</p>
          <ul className="mt-3 flex flex-col gap-2 text-sm">
            {(
              [
                ["币安现货", book.listingHistory.bnSpot],
                ["币安永续", book.listingHistory.bnPerp],
                ["韩所", book.listingHistory.kr],
                ["Coinbase", book.listingHistory.coinbase],
              ] as const
            ).map(([name, x]) => (
              <li key={name}>
                <span className="text-fg">{name}</span>
                <span className="ml-2 font-mono text-primary">{x.n}</span>
                <span className="mt-0.5 block text-xs text-pretty text-muted">{x.detail}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-pretty text-muted">{book.listingHistory.insight}</p>
          <p className="mt-2 text-xs text-pretty text-muted">{book.listingHistory.pons}</p>
        </div>
      </section>

      <section>
        <h2 className="text-sm font-medium">各场所自己写了什么</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {Object.values(book.venueRules).map((v) => (
            <article key={v.venue} className="rounded-xl border border-line bg-surface p-4">
              <div className="flex flex-wrap items-baseline gap-2">
                <h3 className="text-sm font-medium">{v.venue}</h3>
                <span className="text-xs text-primary">{RULE_KIND[v.kind] ?? v.kind}</span>
                <span className="text-xs text-muted">{v.src}</span>
              </div>
              <ul className="mt-2 list-disc pl-4 text-sm text-fg">
                {v.must.map((m) => (
                  <li key={m.text} className="text-pretty">
                    {m.text}
                  </li>
                ))}
              </ul>
              {v.note ? <p className="mt-2 text-xs text-pretty text-muted">{v.note}</p> : null}
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-xl border border-line bg-surface">
        <div className="flex flex-col gap-3 border-b border-line p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-medium">台阶名册</h2>
            <p className="font-mono text-xs text-muted">
              {rows.length} 行 · 快照 {stamp(book.ts)} · 样本 {book.coverage.active}/{book.coverage.universe}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {KINDS.map((k) => (
              <Chip key={k.id} on={kind === k.id} onClick={() => setKind(k.id)}>
                {k.label}
                <span className="ml-1 font-mono text-xs">{k.id === "all" ? book.coverage.active : (book.kinds[k.id] ?? 0)}</span>
              </Chip>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <Chip on={quick === "liq"} onClick={() => setQuick("liq")}>
              池深 ≥ $100k
            </Chip>
            <Chip on={quick === "verifiable"} onClick={() => setQuick("verifiable")}>
              已核实到某一级
            </Chip>
            <Chip on={quick === "recent"} onClick={() => setQuick("recent")}>
              72h 内新池
            </Chip>
            <Chip on={quick === "all"} onClick={() => setQuick("all")}>
              名册全部
            </Chip>
            {rung ? (
              <Chip on onClick={() => setRung(null)}>
                清除台阶筛选
              </Chip>
            ) : null}
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜符号或名字"
              className="min-h-11 min-w-40 flex-1 rounded-full border border-line bg-bg px-4 text-sm text-fg outline-none placeholder:text-muted focus:border-primary"
            />
          </div>
        </div>
        <div className="max-w-full overflow-x-auto">
          <table className="w-full min-w-max border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="px-4 py-2 font-medium">
                  <button type="button" className="min-h-11" onClick={() => toggleSort("symbol")}>
                    代币
                  </button>
                </th>
                <th className="px-2 py-2 font-medium">类型</th>
                <th className="px-2 py-2 text-right font-medium">
                  <button type="button" className="min-h-11" onClick={() => toggleSort("vol")}>
                    24h 成交
                  </button>
                </th>
                <th className="px-2 py-2 text-right font-medium">
                  <button type="button" className="min-h-11" onClick={() => toggleSort("liq")}>
                    池深
                  </button>
                </th>
                <th className="px-2 py-2 text-right font-medium">换手</th>
                {STEPS.concat(APP_STEPS).map((s) => (
                  <th key={s.key} className="px-2 py-2 text-center font-medium">
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 80).map((t) => {
                const on = t.address === pick;
                const tv = turn(t.vol24h, t.liq);
                return (
                  <tr
                    key={(t.address || t.symbol) + (t.vol24h || 0)}
                    onClick={() => setPick(t.address)}
                    className={"cursor-pointer border-t border-line " + (on ? "bg-surface-2" : "hover:bg-bg")}
                  >
                    <td className="px-4 py-2">
                      <div className="font-mono text-fg">{t.symbol}</div>
                      <div className="max-w-48 truncate text-xs text-muted">{(t.name || "").replace(/\s*•\s*Robinhood Token$/i, "")}</div>
                    </td>
                    <td className="px-2 py-2 text-xs text-muted">{kindLabel(t.kind)}</td>
                    <td className="px-2 py-2 text-right font-mono tabular-nums">{usd(t.vol24h)}</td>
                    <td className="px-2 py-2 text-right font-mono tabular-nums">{usd(t.liq)}</td>
                    <td className={"px-2 py-2 text-right font-mono tabular-nums " + ((tv ?? 0) > 20 ? "text-negative" : "")}>
                      {tv == null ? "–" : `${tv.toFixed(1)}x`}
                    </td>
                    {STEPS.concat(APP_STEPS).map((s) => (
                      <td key={s.key} className="px-2 py-2 text-center">
                        <span className={t.reached[s.key] ? "text-positive" : "text-line"}>{t.reached[s.key] ? "●" : "·"}</span>
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {rows.length > 80 ? (
          <p className="px-4 py-3 text-xs text-muted">只展开成交靠前的 80 行，共 {rows.length} 行。用筛选或搜索收窄。</p>
        ) : null}
        {!rows.length ? <p className="px-4 py-6 text-sm text-muted">这个筛选下没有币。</p> : null}
      </section>

      {selected ? (
        <aside className="rounded-xl border border-primary/40 bg-surface p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-mono text-lg">{selected.symbol}</h2>
            <div className="flex flex-wrap gap-3 text-sm">
              {selected.address ? (
                <a className="inline-flex min-h-11 items-center gap-1 text-primary" href={`https://dexscreener.com/robinhood/${selected.address}`} target="_blank" rel="noreferrer">
                  DexScreener <ExternalLink className="size-3.5" />
                </a>
              ) : null}
              {selected.address ? (
                <a className="inline-flex min-h-11 items-center gap-1 text-primary" href={`https://robinscan.io/token/${selected.address}`} target="_blank" rel="noreferrer">
                  {shortAddr(selected.address)} <ExternalLink className="size-3.5" />
                </a>
              ) : null}
            </div>
          </div>
          <p className="text-sm text-muted">{kindLabel(selected.kind)} · {(selected.name || "").replace(/\s*•\s*Robinhood Token$/i, "")}</p>
          <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat k="24h 成交" v={usd(selected.vol24h)} />
            <Stat k="池深" v={usd(selected.liq)} />
            <Stat k="换手" v={turn(selected.vol24h, selected.liq) == null ? "–" : `${turn(selected.vol24h, selected.liq)!.toFixed(1)}x`} />
            <Stat k="市值" v={usd(selected.mcap)} />
          </dl>
          <div className="mt-3 flex flex-wrap gap-2">
            {STEPS.concat(APP_STEPS).map((s) => (
              <span key={s.key} className={"rounded-full border px-3 py-1 text-xs " + (selected.reached[s.key] ? "border-positive text-positive" : "border-line text-muted")}>
                {s.label}
                {s.key === "kr" && selected.krVenue && selected.reached.kr ? ` · ${selected.krVenue}` : ""}
              </span>
            ))}
          </div>
        </aside>
      ) : (
        <p className="text-xs text-muted">点名册里的一行，看它走到了哪一级。</p>
      )}

      <details className="text-sm text-muted">
        <summary className="min-h-11 cursor-pointer text-fg">口径</summary>
        <div className="mt-2 max-w-3xl space-y-2 text-xs text-pretty leading-relaxed">
          <p>
            台阶计数是快照时刻的全样本（{book.coverage.active} / 宇宙 {book.coverage.universe}），不是下面这张表的行数。名册为了能点开，只留下池深 ≥ $20k、或 24h 成交 ≥ $8k、或已经核实到某一级的币。
          </p>
          <p>
            两道门用两套标准，权重来自已上币的实证，不是一把尺子量所有人。第一道门（上第一个交易所）基线 {book.gates.first?.base}% ，{book.gates.first?.note}：持币地址是唯一没有明显反向因果的领先指标。第二道门（Alpha → 币安 CEX）基线 {book.gates.cex?.base}% ，{book.gates.cex?.note}，几乎只看体量。
          </p>
          <p>
            硬性排除：换手（成交 ÷ 池深）超过 20 倍、池深低于 $5 万、开池不足 3 天。Aster 的公开规则要求先有币安 Alpha 或 Tier 2，所以图上它和 Hyperliquid 并排，并不表示它是 Alpha 的上游。
          </p>
          <p>
            币安 Alpha 进 CEX 的年龄切片（样本 n={book.alphaRef.n}）：
            {Object.entries(book.alphaRef.ageConversion)
              .map(([k, v]) => ` ${k} ${v.cex}/${v.n}`)
              .join(" ·")}
            。近 30 天新上的还没有一个进 CEX。
          </p>
        </div>
      </details>
    </div>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{k}</dt>
      <dd className="font-mono tabular-nums">{v}</dd>
    </div>
  );
}

function Track({
  label,
  steps,
  rung,
  onPick,
  joiner,
}: {
  label: string;
  steps: { key: string; label: string; count: number }[];
  rung: string | null;
  onPick: (k: string | null) => void;
  joiner?: string[];
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="w-28 shrink-0 font-mono text-xs text-muted">{label}</div>
      <div className="flex flex-wrap items-center gap-1">
        {steps.map((s, i) => {
          const join = joiner?.[i] ?? (i === 0 ? "none" : "arrow");
          const on = rung === s.key;
          return (
            <span key={s.key} className="inline-flex items-center gap-1">
              {i > 0 && join === "arrow" ? <span className="px-0.5 text-muted">→</span> : null}
              {i > 0 && join === "dot" ? <span className="px-0.5 text-muted">·</span> : null}
              <button
                type="button"
                onClick={() => onPick(on ? null : s.key)}
                className={
                  "flex min-h-11 min-w-16 flex-col items-start rounded-lg border px-3 py-1 " +
                  (on ? "border-primary bg-bg" : "border-line hover:border-primary")
                }
              >
                <span className="font-mono text-xl leading-none tabular-nums text-fg">{s.count}</span>
                <span className="text-xs text-muted">{s.label}</span>
              </button>
            </span>
          );
        })}
      </div>
    </div>
  );
}

function GateCard({
  title,
  gate,
  rows,
  onPick,
}: {
  title: string;
  gate: Gate | undefined;
  rows: { c: Candidate; s: ReturnType<typeof scoreCandidate> }[];
  onPick: (addr: string) => void;
}) {
  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <h2 className="text-sm font-medium">{title}</h2>
      <p className="mt-1 text-xs text-pretty text-muted">
        {gate ? `基线 ${gate.base}% · ${gate.note}。悬停标签看门槛。缺数据的项不进分。` : "没有这道门的参数。"}
      </p>
      <ul className="mt-3 flex flex-col gap-3">
        {rows.map(({ c, s }) => (
          <li key={c.address + c.gate}>
            <button type="button" onClick={() => onPick(c.address)} className="w-full text-left">
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="font-mono">{c.symbol}</span>
                <span className={"font-mono tabular-nums " + ((s.score ?? 0) >= 70 ? "text-positive" : (s.score ?? 0) >= 40 ? "text-primary" : "text-muted")}>
                  {s.score}
                </span>
                <span className="text-xs text-muted">下一级 {c.next}</span>
                {c.already?.length ? <span className="text-xs text-muted">已在 {c.already.join(" + ")}</span> : null}
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                {s.checks.map((ch) => (
                  <span
                    key={ch.label}
                    title={ch.title}
                    className={
                      "rounded-full border px-2 py-0.5 text-xs " +
                      (ch.ok ? "border-positive text-positive" : ch.ok === false ? "border-negative text-negative" : "border-line text-muted")
                    }
                  >
                    {ch.label}
                  </span>
                ))}
                {c.alphaPct?.mcap != null ? (
                  <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted" title="在币安 Alpha 在架币里的市值分位">
                    Alpha 分位 {c.alphaPct.mcap}%
                  </span>
                ) : null}
              </div>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
