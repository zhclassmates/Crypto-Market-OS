/** 把一轮真快照打成四列。公式与 scoring.py 相同；缺的项跳过并重新归一。 */
import type { Part, Scored } from "@/lib/rh/types";
import type { RawTok } from "@/lib/rh/collect-core";

export type Prior = { address: string; ts: number; price: number | null; holders: number | null; heat: number | null };
export type PriorState = { address: string; state: string; pending: string | null; pendingCount: number };

const RANK: Record<string, number> = { INVALID: 0, WATCH: 1, ACCELERATING: 2, RESEARCH: 3, READY: 4, OVERHEATED: 5 };

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
  return Math.round(((100 * s) / w) * 10) / 10;
}

function ratio(a: number | null, b: number | null, floor: number): number | null {
  if (a == null || b == null) return null;
  return a / Math.max(b, floor);
}

function share(b: number | null, s: number | null): number | null {
  if (b == null || s == null || b + s === 0) return null;
  return Math.round((b / (b + s)) * 1000) / 1000;
}

function step(cur: PriorState | undefined, target: string, now: number): PriorState {
  if (!cur) return { address: "", state: target, pending: null, pendingCount: 0 };
  if (target === cur.state) return { ...cur, pending: null, pendingCount: 0 };
  const immediate =
    target === "INVALID" ||
    target === "OVERHEATED" ||
    (RANK[target] ?? 0) > (RANK[cur.state] ?? 0) ||
    cur.state === "INVALID" ||
    cur.state === "OVERHEATED";
  if (immediate) return { ...cur, state: target, pending: null, pendingCount: 0 };
  const cnt = cur.pending === target ? cur.pendingCount + 1 : 1;
  if (cnt >= 2) return { ...cur, state: target, pending: null, pendingCount: 0 };
  return { ...cur, pending: target, pendingCount: cnt };
}

export function scoreBoard(
  now: number,
  tokens: RawTok[],
  alpha: string[],
  priors: Prior[],
  states: PriorState[],
): { rows: Scored[]; nextStates: PriorState[] } {
  const alphaSet = new Set(alpha);
  const order = ["READY", "RESEARCH", "ACCELERATING", "WATCH", "OVERHEATED", "INVALID"];
  const nextStates: PriorState[] = [];
  const rows: Scored[] = tokens.map((t) => {
    const hist = priors.filter((p) => p.address === t.address && p.ts < now);
    const hours = new Set(hist.map((p) => p.ts - (p.ts % 3600)));
    hours.add(now - (now % 3600));
    const nHist = hours.size;
    const v1 = t.volH1 ?? 0;
    const v6 = t.volH6 ?? 0;
    const v24 = t.volH24 ?? 0;
    const t6 = (t.buysH6 ?? 0) + (t.sellsH6 ?? 0);
    const t24 = (t.buysH24 ?? 0) + (t.sellsH24 ?? 0);
    const volAccel =
      v24 && v6 <= v24 * 1.05 ? ratio(v6 / 6, Math.max(v24 - v6, 0) / 18, 100) : null;
    const txAccel =
      t6 && t24 && t6 <= t24 * 1.05 ? ratio(t6 / 6, Math.max(t24 - t6, 0) / 18, 1) : null;
    const buy1 = share(t.buysH1, t.sellsH1);
    const buy6 = share(t.buysH6, t.sellsH6);
    const volLiq = t.liq ? v24 / t.liq : null;
    const buyerAccel = t.buyersH1 != null && t.buyersH24 ? ratio(t.buyersH1, t.buyersH24 / 24, 1) : null;
    let holderG6: number | null = null;
    if (t.holders) {
      const old = hist.filter((p) => p.holders && Math.abs(p.ts - (now - 6 * 3600)) <= 1800);
      if (old.length) holderG6 = Math.round((100 * (t.holders / old[old.length - 1]!.holders! - 1)) * 100) / 100;
    }
    const pastPx = hist.map((p) => p.price).filter((p): p is number => p != null && p > 0);
    const lows = [...pastPx];
    if (t.price && t.pcH24 != null && t.pcH24 > -99) lows.push(t.price / (1 + t.pcH24 / 100));
    const runup = t.price && lows.length ? Math.round((t.price / Math.min(...lows)) * 100) / 100 : null;
    const highs = hist.filter((p) => p.price && p.ts >= now - 72 * 3600).map((p) => p.price!);
    const dd =
      t.price && (highs.length || t.price)
        ? Math.round(100 * (1 - t.price / Math.max(...highs, t.price)) * 10) / 10
        : null;

    const heatParts: Part[] = [
      { label: "6h/18h 量比", weight: 35, raw: volAccel == null ? "缺" : `${volAccel.toFixed(2)}x`, mapped: lin(volAccel, 1, 3) },
      { label: "6h/18h 笔数比", weight: 20, raw: txAccel == null ? "缺" : `${txAccel.toFixed(2)}x`, mapped: lin(txAccel, 1, 3) },
      { label: "买家加速", weight: 15, raw: buyerAccel == null ? "缺" : `${buyerAccel.toFixed(2)}x`, mapped: lin(buyerAccel, 1, 3) },
      { label: "6h 涨幅", weight: 15, raw: t.pcH6 == null ? "缺" : `${t.pcH6.toFixed(0)}%`, mapped: lin(t.pcH6, 0, 100) },
      { label: "持币 6h", weight: 15, raw: holderG6 == null ? "缺" : `${holderG6.toFixed(1)}%`, mapped: lin(holderG6, 0, 5) },
    ];
    const heat = wavg(heatParts.map((p) => ({ w: p.weight, v: p.mapped })));

    const uniq = t.buyersH24 && t.buysH24 ? t.buyersH24 / t.buysH24 : null;
    const age = t.pairCreated ? (now - t.pairCreated) / 86400 : null;
    const liq = t.liq ?? 0;
    const qualityParts: Part[] = [
      { label: "池深", weight: 25, raw: liq ? `$${(liq / 1000).toFixed(0)}k` : "缺", mapped: liq > 0 ? lin(Math.log10(liq), Math.log10(25_000), 6) : null },
      { label: "Vol/LP（减分）", weight: 20, raw: volLiq == null ? "缺" : volLiq.toFixed(1), mapped: volLiq == null ? null : 1 - (lin(volLiq, 3, 15) ?? 0) },
      { label: "独立买家/笔数", weight: 20, raw: uniq == null ? "缺" : uniq.toFixed(2), mapped: lin(uniq, 0.15, 0.6) },
      { label: "持币数", weight: 15, raw: t.holders ? t.holders.toLocaleString("en-US") : "缺", mapped: t.holders ? lin(Math.log10(t.holders), 2.5, 4) : null },
      { label: "Top10（减分）", weight: 10, raw: "缺", mapped: null },
      { label: "币龄", weight: 10, raw: age == null ? "缺" : `${age.toFixed(0)}天`, mapped: lin(age, 0.5, 14) },
    ];
    const quality = wavg(qualityParts.map((p) => ({ w: p.weight, v: p.mapped })));

    const entryNotes: string[] = [];
    let pen = 0;
    const pr = runup == null ? 0 : 40 * (lin(runup, 2, 10) ?? 0);
    pen += pr;
    entryNotes.push(runup == null ? "距低点：缺" : `距低点 ${runup.toFixed(2)}x → −${pr.toFixed(0)}`);
    const p24 = 25 * (lin(t.pcH24, 100, 500) ?? 0);
    pen += p24;
    entryNotes.push(`24h ${t.pcH24 == null ? "缺" : t.pcH24.toFixed(0) + "%"} → −${p24.toFixed(0)}`);
    const pv = 15 * (lin(volLiq, 5, 15) ?? 0);
    pen += pv;
    entryNotes.push(`Vol/LP ${volLiq == null ? "缺" : volLiq.toFixed(1)} → −${pv.toFixed(0)}`);
    if (buy1 != null && buy1 < 0.45) {
      pen += 10;
      entryNotes.push("1h 买单占比 < 45% → −10");
    }
    if (dd != null && dd > 50) {
      pen += 15;
      entryNotes.push(`自 72h 高点回撤 ${dd.toFixed(0)}% → −15`);
    }
    const entry = Math.round(Math.max(0, 100 - pen) * 10) / 10;

    const prevHeats = hist.filter((p) => p.heat != null).sort((a, b) => b.ts - a.ts).slice(0, 2);
    let persist = (heat ?? 0) >= 55 ? 1 : 0;
    if (persist) {
      for (const p of prevHeats) {
        if ((p.heat ?? 0) >= 55) persist += 1;
        else break;
      }
    }

    const onAlpha = alphaSet.has(t.address);
    const listingP = onAlpha ? "已在 Alpha" : "不确定";
    const listingBasis = onAlpha
      ? "合约地址对上币安 Alpha。永续升档频率要全链 onboardDate，这一轮没算进百分比。"
      : "纯链上。入池不满 30 天，没有自有分母。";

    const pc24 = t.pcH24 ?? 0;
    const vl = volLiq ?? 0;
    let target = "WATCH";
    let why: string[] = ["量能或买盘还没形成连续加速"];
    if (liq < 10_000) {
      target = "INVALID";
      why = [`池深 $${Math.round(liq).toLocaleString("en-US")} < $10,000`];
    } else if ((pc24 > 300 && vl > 10) || pc24 > 500 || entry < 25) {
      target = "OVERHEATED";
      why = [`24h ${pc24 >= 0 ? "+" : ""}${pc24.toFixed(0)}%`, `Vol/LP ${vl.toFixed(1)}`, `Entry ${entry}`];
    } else {
      const H = heat ?? 0;
      const Q = quality ?? 0;
      const E = entry ?? 0;
      const checks: [string, boolean][] = [
        [`Heat≥55(${H.toFixed(0)})`, H >= 55],
        [`Quality≥60(${Q.toFixed(0)})`, Q >= 60],
        [`Entry≥60(${E.toFixed(0)})`, E >= 60],
        [`自有快照≥6h(${nHist})`, nHist >= 6],
        [`连续3h热(${persist})`, persist >= 3],
        ["持币不降", holderG6 == null || holderG6 >= 0],
        ["6h买单占优", (buy6 ?? 0) >= 0.5],
      ];
      if (checks.every(([, ok]) => ok)) {
        target = "READY";
        why = checks.map(([k]) => k);
      } else if (H >= 55 && Q >= 50) {
        target = "RESEARCH";
        why = ["未满足: " + checks.filter(([, ok]) => !ok).map(([k]) => k).join("、")];
      } else if ((volAccel ?? 0) >= 2 && (buy1 ?? 0) >= 0.5) {
        target = "ACCELERATING";
        why = [`6h/18h 量比 ${volAccel!.toFixed(1)}x`];
      }
    }

    const prev = states.find((s) => s.address === t.address);
    const stepped = step(prev, target, now);
    stepped.address = t.address;
    nextStates.push(stepped);
    if (stepped.state !== target) why = [...why, `目标 ${target}，降级待确认`];

    const row: Scored = {
      address: t.address,
      symbol: t.symbol,
      state: stepped.state,
      target,
      heat,
      quality,
      entry,
      listingP,
      listingBasis,
      venues: onAlpha ? "binance_alpha" : "无",
      why: t.fromDex ? why : [...why, "这笔 6h 窗口不是本轮 DexScreener 直拉"],
      liq,
      vol24: v24,
      pc24,
      pc6: t.pcH6 ?? 0,
      price: t.price ?? 0,
      holders: t.holders,
      volAccel,
      volLiq,
      holderG6,
      runup,
      nHist,
      heatParts,
      qualityParts,
      entryNotes,
    };
    return row;
  });
  rows.sort((a, b) => order.indexOf(a.state) - order.indexOf(b.state) || (b.heat ?? 0) - (a.heat ?? 0));
  return { rows, nextStates };
}
