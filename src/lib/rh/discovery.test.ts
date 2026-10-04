import { test } from "node:test";
import assert from "node:assert/strict";
import {
  activityFromMeta,
  breakout,
  dailyVolumeAccel,
  deriveMetrics,
  discoveryScore,
  latestActivity,
  num,
  pickBaseline,
  priceAccel,
  rankMovement,
  ratio,
  solAuthority,
  type DerivedInput,
  type FinalBar,
} from "./discovery.ts";
import {
  DEFAULT_RULES,
  evaluateAlerts,
  loadRules,
  newHits,
  ruleMatches,
  sanitizeRules,
  type AlertRule,
} from "./alerts.ts";

const D = 86400;

test("num keeps real zero and rejects empty / non-numeric", () => {
  assert.equal(num(0), 0);
  assert.equal(num("0"), 0);
  assert.equal(num(""), null);
  assert.equal(num("  "), null);
  assert.equal(num(null), null);
  assert.equal(num(undefined), null);
  assert.equal(num("abc"), null);
  assert.equal(num(false), null);
  assert.equal(num("12.5"), 12.5);
});

test("ratio returns null on missing or zero denominator, keeps zero numerator", () => {
  assert.equal(ratio(0, 10), 0);
  assert.equal(ratio(5, 0), null);
  assert.equal(ratio(null, 1), null);
  assert.equal(ratio(1, null), null);
});

test("activityFromMeta reads trending vs trenches keys and keeps zero", () => {
  const t = activityFromMeta("trending", "24h", 100, 3, { buys: 0, sells: 4, swaps: 4, volume: "12.5" });
  assert.deepEqual([t.buys, t.sells, t.swaps, t.volume], [0, 4, 4, 12.5]);
  const tr = activityFromMeta("trenches", "completed", 100, null, { buys_24h: 7, sells_24h: 0, swaps_24h: 7, volume_24h: 1 });
  assert.deepEqual([tr.buys, tr.sells, tr.swaps, tr.volume], [7, 0, 7, 1]);
  const missing = activityFromMeta("trending", "24h", 100, null, { rank: 1 });
  assert.equal(missing.buys, null);
});

test("pickBaseline: same source+variant, nearest to latest-1h within tolerance", () => {
  const mk = (seenAt: number, source = "trending", variant = "24h") =>
    activityFromMeta(source, variant, seenAt, null, { buys: seenAt });
  const latest = mk(10_000);
  const pts = [mk(6_000), mk(6_500), mk(6_500, "hot"), mk(6_400, "trending", "1h"), latest];
  assert.equal(pickBaseline(pts, latest)?.seenAt, 6_500);
  assert.equal(pickBaseline([mk(1_000), latest], latest), null);
});

test("latestActivity prefers trending, ignores rows with no activity", () => {
  const a = activityFromMeta("trenches", "completed", 200, null, { buys_24h: 1 });
  const b = activityFromMeta("trending", "24h", 100, null, { buys: 2 });
  const c = activityFromMeta("trending", "24h", 300, null, {});
  assert.equal(latestActivity([a, b, c])?.source, "trending");
  assert.equal(latestActivity([a, b, c])?.seenAt, 100);
  assert.equal(latestActivity([c]), null);
});

test("rankMovement: up is positive, entered needs a comparable window", () => {
  const now = 10_000;
  const up = rankMovement([{ seenAt: 9_900, rank: 5 }, { seenAt: 6_400, rank: 30 }], now, 3_000);
  assert.equal(up.move, 25);
  assert.equal(up.entered, false);
  const entered = rankMovement([{ seenAt: 9_900, rank: 5 }], now, 3_000);
  assert.equal(entered.move, null);
  assert.equal(entered.entered, true);
  const tooShort = rankMovement([{ seenAt: 9_900, rank: 5 }], now, 8_000);
  assert.equal(tooShort.entered, false);
  const stale = rankMovement([{ seenAt: 5_000, rank: 5 }], now, 1_000);
  assert.equal(stale.current, null);
});

const bars = (closes: number[], vols: (number | null)[]): FinalBar[] =>
  closes.map((c, i) => ({ ts: i * D, high: c, close: c, volume: vols[i] ?? null }));

test("dailyVolumeAccel uses last vs mean of previous 7 contiguous finalized bars", () => {
  const b = bars([1, 1, 1, 1, 1, 1, 1, 1], [10, 10, 10, 10, 10, 10, 10, 30]);
  assert.equal(dailyVolumeAccel(b), 3);
  assert.equal(dailyVolumeAccel(b.slice(1)), null);
  const gap = b.map((x, i) => (i === 7 ? { ...x, ts: x.ts + D } : x));
  assert.equal(dailyVolumeAccel(gap), null);
  const missing = bars([1, 1, 1, 1, 1, 1, 1, 1], [10, null, 10, 10, 10, 10, 10, 30]);
  assert.equal(dailyVolumeAccel(missing), null);
  const zeroBase = bars([1, 1, 1, 1, 1, 1, 1, 1], [0, 0, 0, 0, 0, 0, 0, 30]);
  assert.equal(dailyVolumeAccel(zeroBase), null);
  const zeroLast = bars([1, 1, 1, 1, 1, 1, 1, 1], [10, 10, 10, 10, 10, 10, 10, 0]);
  assert.equal(dailyVolumeAccel(zeroLast), 0);
});

test("breakout compares last close to prior 7 highs", () => {
  assert.equal(breakout(bars([1, 2, 3, 2, 2, 2, 2, 3], [])), true);
  assert.equal(breakout(bars([1, 2, 4, 2, 2, 2, 2, 3], [])), false);
  assert.equal(breakout(bars([1, 2, 3], [])), null);
});

test("priceAccel is pc1h minus hourly average of pc24h, null when either missing", () => {
  assert.equal(priceAccel(5, 24), 4);
  assert.equal(priceAccel(0, 0), 0);
  assert.equal(priceAccel(null, 24), null);
  assert.equal(priceAccel(5, null), null);
});

test("solAuthority: EVM is NOT_APPLICABLE, never false", () => {
  assert.equal(solAuthority("eth", false), "NOT_APPLICABLE");
  assert.equal(solAuthority("sol", false), "NOT_RENOUNCED");
  assert.equal(solAuthority("sol", true), "RENOUNCED");
  assert.equal(solAuthority("sol", null), "UNKNOWN");
});

function input(over: Partial<DerivedInput> = {}): DerivedInput {
  return {
    buys: null, sells: null, latest: null, baseline: null, pc1hPct: null, pc24hPct: null,
    volume24h: null, fdv: null, trendingRank: null, hotRank: null, finalBars: [], ...over,
  };
}

test("deriveMetrics: all-missing input gives nulls and zero evaluated score", () => {
  const d = deriveMetrics(input());
  assert.equal(d.buySellRatio, null);
  assert.equal(d.buysAccel1h, null);
  assert.equal(d.volumeToFdv, null);
  const s = discoveryScore(d);
  assert.deepEqual([s.score, s.evaluated, s.candidate], [0, 0, false]);
});

test("deriveMetrics: real zeros stay zero; ratio uses counts", () => {
  const latest = activityFromMeta("trending", "24h", 10_000, 1, { buys: 30, sells: 10, swaps: 40, volume: 0 });
  const baseline = activityFromMeta("trending", "24h", 6_400, 9, { buys: 20, sells: 10, swaps: 30, volume: 0 });
  const d = deriveMetrics(input({ buys: 30, sells: 0, latest, baseline, volume24h: 0, fdv: 100 }));
  assert.equal(d.buySellRatio, 1);
  assert.equal(d.buysAccel1h, 1.5);
  assert.equal(d.sellsAccel1h, 1);
  assert.equal(d.volumeAccel1h, null); // baseline volume 0 → 无法计算倍数
  assert.equal(d.volumeToFdv, 0);
  assert.equal(d.activityContext, "trending/24h");
  const zero = deriveMetrics(input({ buys: 0, sells: 0 }));
  assert.equal(zero.buySellRatio, null);
});

test("discoveryScore counts only evaluable rules; candidate at 3", () => {
  const d = deriveMetrics(input({
    buys: 70, sells: 30, volume24h: 60, fdv: 100,
    finalBars: bars([1, 1, 1, 1, 1, 1, 1, 2], [1, 1, 1, 1, 1, 1, 1, 5]),
  }));
  const s = discoveryScore(d);
  assert.equal(s.evaluated, 4);
  assert.equal(s.score, 4);
  assert.equal(s.candidate, true);
});

test("alerts: null never fires, zero can fire, bool rule needs true", () => {
  const ge: AlertRule = { id: "a", field: "buys24h", op: ">=", threshold: 0, enabled: true, chain: null };
  assert.equal(ruleMatches(ge, null), false);
  assert.equal(ruleMatches(ge, 0), true);
  const le: AlertRule = { ...ge, op: "<=", threshold: 0 };
  assert.equal(ruleMatches(le, 0), true);
  const b: AlertRule = { id: "b", field: "breakout7d", op: "is_true", threshold: null, enabled: true, chain: null };
  assert.equal(ruleMatches(b, false), false);
  assert.equal(ruleMatches(b, null), false);
  assert.equal(ruleMatches(b, true), true);
  assert.equal(ruleMatches({ ...ge, enabled: false }, 5), false);
});

test("evaluateAlerts respects chain filter and builds stable keys", () => {
  const rules: AlertRule[] = [
    { id: "r1", field: "pc1h", op: ">=", threshold: 10, enabled: true, chain: "sol" },
  ];
  const hits = evaluateAlerts(
    [
      { chain: "sol", address: "A", symbol: "a", values: { pc1h: 12 } },
      { chain: "eth", address: "B", symbol: "b", values: { pc1h: 50 } },
      { chain: "sol", address: "C", symbol: "c", values: { pc1h: null } },
    ],
    rules,
  );
  assert.deepEqual(hits.map((h) => h.key), ["r1|sol:A"]);
  assert.deepEqual(newHits(hits, new Set(["r1|sol:A"])), []);
});

test("sanitizeRules drops unknown fields, BLOCKED fields and mismatched ops", () => {
  const out = sanitizeRules([
    { id: "ok", field: "volumeToFdv", op: ">=", threshold: 1 },
    { id: "liq", field: "liquidity", op: ">=", threshold: 1 },
    { id: "hp", field: "is_honeypot", op: "is_true" },
    { id: "bad-op", field: "breakout7d", op: ">=", threshold: 1 },
    { id: "no-th", field: "pc1h", op: ">=" },
    { id: "bool", field: "breakout7d", op: "is_true", threshold: 99 },
    "junk",
  ]);
  assert.deepEqual(out.map((r) => r.id), ["ok", "bool"]);
  assert.equal(out[1]!.threshold, null);
  assert.deepEqual(sanitizeRules("x"), []);
});

test("loadRules falls back to defaults on missing or broken storage", () => {
  assert.deepEqual(loadRules(null), DEFAULT_RULES);
  assert.deepEqual(loadRules({ getItem: () => null }), DEFAULT_RULES);
  assert.deepEqual(loadRules({ getItem: () => "{not json" }), DEFAULT_RULES);
  assert.deepEqual(loadRules({ getItem: () => "[]" }), []);
});
