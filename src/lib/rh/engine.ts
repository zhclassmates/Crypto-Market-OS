/** RH V2 评分与状态机。公式与 collecting 规则与 scoring.py / listing_table.py 一致。 */
import type { DeskFrame, Part, RateRow, Scored } from "@/lib/rh/types";

export const T0 = 1_790_000_000 - (1_790_000_000 % 3600);

const DAY_MS = 86_400_000;
const OBS_MIN_LIQ = 25_000;
const OBS_MIN_VOL24 = 20_000;
const INVALID_LIQ = 10_000;
const READY_MIN_SNAPSHOTS = 6;
const DOWNGRADE_CONFIRM_HOURS = 2;
const OVERHEAT_PC24 = 300;
const OVERHEAT_VOL_LIQ = 10;
const OVERHEAT_PC24_HARD = 500;
const LISTING_MIN_N = 20;
const REGIME_CUTOFF_MS = 1_788_825_600_000;
const CHAIN_ID = "4663";

const RANK: Record<string, number> = {
  INVALID: 0,
  WATCH: 1,
  ACCELERATING: 2,
  RESEARCH: 3,
  READY: 4,
  OVERHEATED: 5,
};

type Kind = "accel" | "pump" | "flat" | "dust";

type Snap = {
  ts: number;
  address: string;
  symbol: string;
  price: number;
  mcap: number;
  liq: number;
  vol_h1: number;
  vol_h6: number;
  vol_h24: number;
  buys_h1: number;
  sells_h1: number;
  buys_h6: number;
  sells_h6: number;
  buys_h24: number;
  sells_h24: number;
  pc_h6: number;
  pc_h24: number;
  holders: number;
  top10_pct: number;
  buyers_h1: number;
  buyers_h24: number;
  pair_created: number;
};

type StateRow = { state: string; since: number; pending: string | null; pendingCount: number };

const CAST: { address: string; symbol: string; kind: Kind }[] = [
  { address: "0x" + "a".repeat(40), symbol: "RISER", kind: "accel" },
  { address: "0x" + "b".repeat(40), symbol: "PUMP", kind: "pump" },
  { address: "0x" + "c".repeat(40), symbol: "FLAT", kind: "flat" },
  { address: "0x" + "d".repeat(40), symbol: "DUST", kind: "dust" },
  { address: "0x" + "e".repeat(40), symbol: "ALPHA1", kind: "flat" },
];

function lin(x: number | null, lo: number, hi: number): number | null {
  if (x == null || Number.isNaN(x)) return null;
  if (hi === lo) return x >= hi ? 1 : 0;
  return Math.max(0, Math.min(1, (x - lo) / (hi - lo)));
}

function wavg(parts: { w: number; v: number | null }[]): number | null {
  const got = parts.filter((p) => p.v != null) as { w: number; v: number }[];
  if (!got.length) return null;
  const s = got.reduce((a, p) => a + p.w * p.v, 0);
  const w = got.reduce((a, p) => a + p.w, 0);
  return Math.round((100 * s) / w * 10) / 10;
}

function ratio(a: number | null, b: number | null, floor: number): number | null {
  if (a == null || b == null) return null;
  return a / Math.max(b, floor);
}

function share(b: number | null, s: number | null): number | null {
  if (b == null || s == null || b + s === 0) return null;
  return Math.round((b / (b + s)) * 1000) / 1000;
}

function snapAt(h: number, c: (typeof CAST)[number]): Snap {
  let v24: number, v6: number, v1: number, liq: number, pc24: number, pc6: number, price: number;
  if (c.kind === "accel") {
    v24 = 400e3 + 60e3 * h;
    v6 = 250e3 + 40e3 * h;
    v1 = 70e3 + 8e3 * h;
    liq = 300e3;
    pc24 = 60;
    pc6 = 25;
    price = 1 + 0.03 * h;
  } else if (c.kind === "pump") {
    v24 = 5e6;
    v6 = 3e6;
    v1 = 8e5;
    liq = 60e3;
    pc24 = 800;
    pc6 = 300;
    price = 9;
  } else if (c.kind === "dust") {
    v24 = 5e3;
    v6 = 1e3;
    v1 = 100;
    liq = 3e3;
    pc24 = 5;
    pc6 = 1;
    price = 0.1;
  } else {
    v24 = 100e3;
    v6 = 25e3;
    v1 = 4e3;
    liq = 200e3;
    pc24 = 2;
    pc6 = 0;
    price = 1;
  }
  const b6 = Math.trunc(v6 / 300);
  return {
    ts: T0 + h * 3600,
    address: c.address,
    symbol: c.symbol,
    price,
    mcap: price * 1e7,
    liq,
    vol_h1: v1,
    vol_h6: v6,
    vol_h24: v24,
    buys_h1: Math.trunc(v1 / 250),
    sells_h1: Math.trunc(v1 / 400),
    buys_h6: b6,
    sells_h6: Math.trunc(b6 * 0.7),
    buys_h24: Math.trunc(v24 / 300),
    sells_h24: Math.trunc(v24 / 400),
    pc_h6: pc6,
    pc_h24: pc24,
    holders: c.kind === "accel" ? 1500 + 60 * h : 900,
    top10_pct: 22,
    buyers_h1: 40 + 5 * h,
    buyers_h24: 400,
    pair_created: T0 - 20 * 86400,
  };
}

function inObs(s: Snap) {
  return s.liq >= OBS_MIN_LIQ && s.vol_h24 >= OBS_MIN_VOL24;
}

type Feat = {
  vol_accel_6v18: number | null;
  tx_accel_6v18: number | null;
  buy_ratio_h1: number | null;
  buy_ratio_h6: number | null;
  vol_liq: number | null;
  buyer_accel: number | null;
  holder_g6: number | null;
  holder_g24: number | null;
  runup_from_low: number | null;
  dd_from_high: number | null;
  n_hist: number;
};

function features(s: Snap, hist: Snap[], nHist: number): Feat {
  const v1 = s.vol_h1 || 0;
  const v6 = s.vol_h6 || 0;
  const v24 = s.vol_h24 || 0;
  const t6 = (s.buys_h6 || 0) + (s.sells_h6 || 0);
  const t24 = (s.buys_h24 || 0) + (s.sells_h24 || 0);
  const f: Feat = {
    vol_accel_6v18: v24 ? ratio(v6 / 6, Math.max(v24 - v6, 0) / 18, 100) : null,
    tx_accel_6v18: t24 ? ratio(t6 / 6, Math.max(t24 - t6, 0) / 18, 1) : null,
    buy_ratio_h1: share(s.buys_h1, s.sells_h1),
    buy_ratio_h6: share(s.buys_h6, s.sells_h6),
    vol_liq: s.liq ? v24 / s.liq : null,
    buyer_accel:
      s.buyers_h1 != null && s.buyers_h24 ? ratio(s.buyers_h1, s.buyers_h24 / 24, 1) : null,
    holder_g6: null,
    holder_g24: null,
    runup_from_low: null,
    dd_from_high: null,
    n_hist: nHist,
  };
  if (s.holders) {
    for (const [key, hrs] of [
      ["holder_g6", 6],
      ["holder_g24", 24],
    ] as const) {
      const old = hist.filter(
        (r) => r.holders && Math.abs(r.ts - (s.ts - hrs * 3600)) <= 1800,
      );
      if (old.length) {
        f[key] = Math.round((100 * (s.holders / old[old.length - 1]!.holders - 1)) * 100) / 100;
      }
    }
  }
  const prices = hist.map((r) => r.price).filter((p) => p);
  const lows = [...prices];
  const highs = hist.filter((r) => r.price && r.ts >= s.ts - 72 * 3600).map((r) => r.price);
  if (s.price && s.pc_h24 > -99) lows.push(s.price / (1 + s.pc_h24 / 100));
  f.runup_from_low = s.price && lows.length ? Math.round((s.price / Math.min(...lows)) * 100) / 100 : null;
  const highPool = highs.length ? highs : [];
  f.dd_from_high =
    s.price && (highPool.length || s.price)
      ? Math.round(100 * (1 - s.price / Math.max(...highPool, s.price)) * 10) / 10
      : null;
  return f;
}

function part(label: string, weight: number, raw: string, mapped: number | null): Part {
  return { label, weight, raw, mapped };
}

function heatBundle(s: Snap, f: Feat) {
  const parts = [
    part("6h/18h 量比", 35, f.vol_accel_6v18 == null ? "缺" : `${f.vol_accel_6v18.toFixed(2)}x`, lin(f.vol_accel_6v18, 1, 3)),
    part("6h/18h 笔数比", 20, f.tx_accel_6v18 == null ? "缺" : `${f.tx_accel_6v18.toFixed(2)}x`, lin(f.tx_accel_6v18, 1, 3)),
    part("买家加速", 15, f.buyer_accel == null ? "缺" : `${f.buyer_accel.toFixed(2)}x`, lin(f.buyer_accel, 1, 3)),
    part("6h 涨幅", 15, s.pc_h6 == null ? "缺" : `${s.pc_h6.toFixed(0)}%`, lin(s.pc_h6, 0, 100)),
    part("持币 6h", 15, f.holder_g6 == null ? "缺" : `${f.holder_g6.toFixed(1)}%`, lin(f.holder_g6, 0, 5)),
  ];
  return { score: wavg(parts.map((p) => ({ w: p.weight, v: p.mapped }))), parts };
}

function qualityBundle(s: Snap, f: Feat, ageDays: number | null) {
  const uniq = s.buyers_h24 && s.buys_h24 ? s.buyers_h24 / s.buys_h24 : null;
  const liq = s.liq || 0;
  const parts = [
    part(
      "池深",
      25,
      liq ? `$${(liq / 1000).toFixed(0)}k` : "缺",
      liq > 0 ? lin(Math.log10(liq), Math.log10(25_000), 6) : null,
    ),
    part(
      "Vol/LP（减分）",
      20,
      f.vol_liq == null ? "缺" : f.vol_liq.toFixed(1),
      f.vol_liq == null ? null : 1 - (lin(f.vol_liq, 3, 15) ?? 0),
    ),
    part("独立买家/笔数", 20, uniq == null ? "缺" : uniq.toFixed(2), lin(uniq, 0.15, 0.6)),
    part(
      "持币数",
      15,
      s.holders ? s.holders.toLocaleString("en-US") : "缺",
      s.holders ? lin(Math.log10(s.holders), 2.5, 4) : null,
    ),
    part(
      "Top10（减分）",
      10,
      s.top10_pct == null ? "缺" : `${s.top10_pct.toFixed(0)}%`,
      s.top10_pct == null ? null : 1 - (lin(s.top10_pct, 20, 60) ?? 0),
    ),
    part("币龄", 10, ageDays == null ? "缺" : `${ageDays.toFixed(0)}天`, lin(ageDays, 0.5, 14)),
  ];
  return { score: wavg(parts.map((p) => ({ w: p.weight, v: p.mapped }))), parts };
}

function entryBundle(s: Snap, f: Feat) {
  const notes: string[] = [];
  let pen = 0;
  if (f.runup_from_low != null) {
    const x = 40 * (lin(f.runup_from_low, 2, 10) ?? 0);
    pen += x;
    notes.push(`距 7 日低点 ${f.runup_from_low.toFixed(2)}x → −${x.toFixed(0)}`);
  } else notes.push("距低点：缺历史");
  const p24 = 25 * (lin(s.pc_h24, 100, 500) ?? 0);
  pen += p24;
  notes.push(`24h ${s.pc_h24.toFixed(0)}% → −${p24.toFixed(0)}`);
  const pv = 15 * (lin(f.vol_liq, 5, 15) ?? 0);
  pen += pv;
  notes.push(`Vol/LP ${f.vol_liq == null ? "缺" : f.vol_liq.toFixed(1)} → −${pv.toFixed(0)}`);
  if (f.buy_ratio_h1 != null && f.buy_ratio_h1 < 0.45) {
    pen += 10;
    notes.push("1h 买单占比 < 45% → −10");
  }
  if (f.dd_from_high != null && f.dd_from_high > 50) {
    pen += 15;
    notes.push(`自 72h 高点回撤 ${f.dd_from_high.toFixed(0)}% → −15`);
  }
  return { score: Math.round(Math.max(0, 100 - pen) * 10) / 10, notes };
}

type Ev = { chain_id: string; alpha_ms: number; perp_ms: number | null };

function scenarioEvents(): Ev[] {
  const rows: Ev[] = [
    { chain_id: CHAIN_ID, alpha_ms: (T0 - 3 * 86400) * 1000, perp_ms: null },
  ];
  for (let i = 0; i < 60; i++) {
    const alpha_ms = (T0 - 200 * 86400) * 1000;
    rows.push({ chain_id: "56", alpha_ms, perp_ms: alpha_ms + (i < 21 ? 10 : 60) * DAY_MS });
  }
  return rows;
}

type Cell = Record<string, number>;

function baseRates(now: number, firstObs: { address: string; t0: number }[], alphaSince: Map<string, number>) {
  const nowMs = now * 1000;
  const windows: [string, number][] = [
    ["7", 7],
    ["30", 30],
    ["90", 90],
  ];
  const cells = new Map<string, Cell>();
  for (const e of scenarioEvents()) {
    if (e.perp_ms === -1) continue;
    const eras = ["all"];
    if (e.alpha_ms >= REGIME_CUTOFF_MS) eras.push("post");
    if (e.alpha_ms >= nowMs - 180 * DAY_MS) eras.push("recent");
    const chains = ["*", ...(e.chain_id === CHAIN_ID ? [CHAIN_ID] : [])];
    for (const ch of chains) {
      for (const era of eras) {
        const k = `${ch}|${era}`;
        let c = cells.get(k);
        if (!c) {
          c = {};
          for (const [w] of windows) {
            c["n" + w] = 0;
            c["h" + w] = 0;
          }
          cells.set(k, c);
        }
        for (const [w, d] of windows) {
          if (e.alpha_ms + d * DAY_MS > nowMs) continue;
          c["n" + w] = (c["n" + w] ?? 0) + 1;
          if (e.perp_ms && e.perp_ms - e.alpha_ms <= d * DAY_MS) c["h" + w] = (c["h" + w] ?? 0) + 1;
        }
      }
    }
  }
  const out = new Map<string, Record<string, number>>();
  for (const [k, c] of cells) {
    const row: Record<string, number> = {};
    for (const [w] of windows) {
      const n = c["n" + w] ?? 0;
      const h = c["h" + w] ?? 0;
      row["n" + w] = n;
      row["p" + w] = n ? (100 * h) / n : 0;
    }
    out.set(k, row);
  }
  let n = 0;
  let h = 0;
  for (const r of firstObs) {
    const t0 = r.t0 * 1000;
    const since = alphaSince.get(r.address);
    if (t0 + 30 * DAY_MS > nowMs || (since != null && since <= t0)) continue;
    n += 1;
    if (since != null && since <= t0 + 30 * DAY_MS) h += 1;
  }
  out.set("own|post", { n30: n, p30: n ? (100 * h) / n : 0 });
  return out;
}

function listingP(venues: Set<string>, rates: Map<string, Record<string, number>>) {
  const tags = [...venues].sort().join(",") || "无";
  if ([...venues].some((v) => v.startsWith("binance_perp"))) return { p: "已上币安永续", basis: tags };
  if ([...venues].some((v) => v.startsWith("binance_alpha"))) {
    const order: [string, string][] = [
      [CHAIN_ID, "post"],
      ["*", "recent"],
      ["*", "all"],
    ];
    for (const [ch, era] of order) {
      const r = rates.get(`${ch}|${era}`);
      if (r && (r.n30 ?? 0) >= LISTING_MIN_N) {
        const label = ch === CHAIN_ID ? "RH链" : "全链";
        const eraLabel = era === "post" ? "9/8后" : era === "recent" ? "近180天" : "全时段";
        return {
          p: `${Math.round(r.p30 ?? 0)}%`,
          basis: `Alpha→永续30天 ${label}${eraLabel} n=${r.n30} | ${tags}`,
        };
      }
    }
    return { p: "不确定", basis: `Alpha→永续样本不足 | ${tags}` };
  }
  const own = rates.get("own|post");
  if (own && (own.n30 ?? 0) >= LISTING_MIN_N) {
    return { p: `${Math.round(own.p30 ?? 0)}%`, basis: `RH观察池→Alpha30天 n=${own.n30} | ${tags}` };
  }
  return { p: "不确定", basis: `纯链上，自有样本不足 | ${tags}` };
}

function targetState(s: Snap, f: Feat, heat: number | null, quality: number | null, entry: number | null, persist: number) {
  const liq = s.liq || 0;
  if (liq < INVALID_LIQ) return { state: "INVALID", why: [`池深 $${Math.round(liq).toLocaleString("en-US")} < $${INVALID_LIQ.toLocaleString("en-US")}`] };
  const pc24 = s.pc_h24 || 0;
  const vl = f.vol_liq || 0;
  if ((pc24 > OVERHEAT_PC24 && vl > OVERHEAT_VOL_LIQ) || pc24 > OVERHEAT_PC24_HARD || (entry != null && entry < 25)) {
    return {
      state: "OVERHEATED",
      why: [`24h ${pc24 >= 0 ? "+" : ""}${pc24.toFixed(0)}%`, `Vol/LP ${vl.toFixed(1)}`, `Entry ${entry ?? "–"}`],
    };
  }
  const H = heat ?? 0;
  const Q = quality ?? 0;
  const E = entry ?? 0;
  const checks: [string, boolean][] = [
    [`Heat≥55(${H.toFixed(0)})`, H >= 55],
    [`Quality≥60(${Q.toFixed(0)})`, Q >= 60],
    [`Entry≥60(${E.toFixed(0)})`, E >= 60],
    [`自有快照≥${READY_MIN_SNAPSHOTS}h(${f.n_hist})`, f.n_hist >= READY_MIN_SNAPSHOTS],
    [`连续3h热(${persist})`, persist >= 3],
    ["持币不降", f.holder_g6 == null || f.holder_g6 >= 0],
    ["6h买单占优", (f.buy_ratio_h6 ?? 0) >= 0.5],
  ];
  if (checks.every(([, ok]) => ok)) return { state: "READY", why: checks.map(([k]) => k) };
  if (H >= 55 && Q >= 50) {
    return { state: "RESEARCH", why: ["未满足: " + checks.filter(([, ok]) => !ok).map(([k]) => k).join("、")] };
  }
  if ((f.vol_accel_6v18 ?? 0) >= 2 && (f.buy_ratio_h1 ?? 0) >= 0.5) {
    return { state: "ACCELERATING", why: [`6h/18h 量比 ${(f.vol_accel_6v18 ?? 0).toFixed(1)}x`] };
  }
  return { state: "WATCH", why: ["量能或买盘还没形成连续加速"] };
}

function step(cur: StateRow | undefined, target: string, now: number): StateRow {
  if (!cur) return { state: target, since: now, pending: null, pendingCount: 0 };
  if (target === cur.state) return { ...cur, pending: null, pendingCount: 0 };
  const immediate =
    target === "INVALID" ||
    target === "OVERHEATED" ||
    (RANK[target] ?? 0) > (RANK[cur.state] ?? 0) ||
    cur.state === "INVALID" ||
    cur.state === "OVERHEATED";
  if (immediate) return { state: target, since: now, pending: null, pendingCount: 0 };
  const cnt = cur.pending === target ? cur.pendingCount + 1 : 1;
  if (cnt >= DOWNGRADE_CONFIRM_HOURS) return { state: target, since: now, pending: null, pendingCount: 0 };
  return { ...cur, pending: target, pendingCount: cnt };
}

function rateRows(rates: Map<string, Record<string, number>>): RateRow[] {
  const names: Record<string, string> = { "*": "全链", [CHAIN_ID]: "RH链" };
  const eras: Record<string, string> = { all: "全时段", post: "9/8 后", recent: "近 180 天" };
  const keys = [...rates.keys()].filter((k) => k !== "own|post").sort((a, b) => {
    const [ca, ea] = a.split("|");
    const [cb, eb] = b.split("|");
    if ((ca === "*") !== (cb === "*")) return ca === "*" ? -1 : 1;
    return ea!.localeCompare(eb!);
  });
  const pack = (n: number | undefined, p: number | undefined) => ({
    n: n ?? null,
    p: n != null && n >= LISTING_MIN_N ? (p ?? null) : null,
  });
  const rows: RateRow[] = keys.map((k) => {
    const [ch, era] = k.split("|");
    const r = rates.get(k)!;
    return {
      id: k,
      label: `Alpha→永续 · ${names[ch!] ?? ch} · ${eras[era!] ?? era}`,
      cells: [pack(r.n7, r.p7), pack(r.n30, r.p30), pack(r.n90, r.p90)],
    };
  });
  const own = rates.get("own|post");
  rows.push({
    id: "own",
    label: "RH 观察池 → Alpha（自有样本）",
    cells: [
      { n: null, p: null },
      { n: own?.n30 ?? 0, p: (own?.n30 ?? 0) >= LISTING_MIN_N ? (own?.p30 ?? 0) : null },
      { n: null, p: null },
    ],
  });
  return rows;
}

/** 从第 0 小时重放到 lastHour（含）。状态机每小时递推，不跳步。 */
export function replay(lastHour: number): DeskFrame {
  const hour = Math.max(0, Math.min(9, lastHour));
  const historySnaps = new Map<string, Snap[]>();
  const states = new Map<string, StateRow>();
  const heats = new Map<string, number[]>();
  const history: Record<string, string[]> = {};
  const firstObs: { address: string; t0: number }[] = [];
  const alphaSince = new Map<string, number>([["0x" + "e".repeat(40), (T0 - 3 * 86400) * 1000]]);
  let rows: Scored[] = [];
  let rates: RateRow[] = [];
  let alerts: string[] = [];
  let now = T0;

  for (let h = 0; h <= hour; h++) {
    now = T0 + h * 3600;
    const snaps = CAST.map((c) => snapAt(h, c));
    const obs = snaps.filter(inObs);
    const prevStates = new Map([...states.entries()].map(([a, s]) => [a, s.state]));
    alerts = [];
    const ratesMap = baseRates(now, firstObs, alphaSince);
    rates = rateRows(ratesMap);
    rows = [];

    for (const s of obs) {
      if (!firstObs.some((f) => f.address === s.address)) firstObs.push({ address: s.address, t0: s.ts });
      const hist = historySnaps.get(s.address) ?? [];
      const nHist = hist.length + 1;
      const f = features(s, hist, nHist);
      const age = (now - s.pair_created) / 86400;
      const hb = heatBundle(s, f);
      const qb = qualityBundle(s, f, age);
      const eb = entryBundle(s, f);
      const prev = (heats.get(s.address) ?? []).slice(-2).reverse();
      let persist = (hb.score ?? 0) >= 55 ? 1 : 0;
      if (persist) {
        for (const p of prev) {
          if (p >= 55) persist += 1;
          else break;
        }
      }
      const venues = new Set<string>();
      if (s.symbol === "ALPHA1") venues.add("binance_alpha");
      if (s.symbol === "RISER" && s.mcap >= 1_000_000) venues.add("aster_perp?");
      const lp = listingP(venues, ratesMap);
      const tgt = targetState(s, f, hb.score, qb.score, eb.score, persist);
      const next = step(states.get(s.address), tgt.state, now);
      states.set(s.address, next);
      const why = next.state === tgt.state ? tgt.why : [...tgt.why, `目标 ${tgt.state}，降级待确认`];
      const series = heats.get(s.address) ?? [];
      series.push(hb.score ?? 0);
      heats.set(s.address, series);
      const stHist = history[s.symbol] ?? [];
      stHist.push(next.state);
      history[s.symbol] = stHist;
      if ((next.state === "READY" || next.state === "RESEARCH") && prevStates.get(s.address) !== next.state) {
        alerts.push(`${next.state} ${s.symbol}`);
      }
      rows.push({
        address: s.address,
        symbol: s.symbol,
        state: next.state,
        target: tgt.state,
        heat: hb.score,
        quality: qb.score,
        entry: eb.score,
        listingP: lp.p,
        listingBasis: lp.basis,
        venues: [...venues].sort().join(" ") || "无",
        why,
        liq: s.liq,
        vol24: s.vol_h24,
        pc24: s.pc_h24,
        pc6: s.pc_h6,
        price: s.price,
        holders: s.holders,
        volAccel: f.vol_accel_6v18,
        volLiq: f.vol_liq,
        holderG6: f.holder_g6,
        runup: f.runup_from_low,
        nHist,
        heatParts: hb.parts,
        qualityParts: qb.parts,
        entryNotes: eb.notes,
      });
    }
    for (const s of snaps) {
      const arr = historySnaps.get(s.address) ?? [];
      arr.push(s);
      historySnaps.set(s.address, arr);
    }
  }

  const order = ["READY", "RESEARCH", "ACCELERATING", "WATCH", "OVERHEATED", "INVALID"];
  rows.sort((a, b) => order.indexOf(a.state) - order.indexOf(b.state) || (b.heat ?? 0) - (a.heat ?? 0));
  return { hour, now, rows, rates, history, alerts };
}

export function finalChecks(frame: DeskFrame) {
  const by = Object.fromEntries(frame.rows.map((r) => [r.symbol, r]));
  const risen = by.RISER?.state;
  const alpha = by.ALPHA1;
  return [
    { ok: by.PUMP?.state === "OVERHEATED", label: "PUMP 为 OVERHEATED（24h 硬顶）" },
    { ok: risen === "READY" || risen === "RESEARCH", label: `RISER 为 ${risen ?? "—"}（READY 或 RESEARCH）` },
    { ok: !by.DUST, label: "DUST 池深不够，不进观察池" },
    { ok: alpha?.listingP === "35%", label: `ALPHA1 的 ListingP 为 ${alpha?.listingP ?? "—"}（全链 30 天 21/60）` },
  ];
}
