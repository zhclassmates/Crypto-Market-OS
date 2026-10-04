/**
 * 爆款发现 V1：只用 READY 字段，以及由 READY 字段在本地计算的 DERIVED 指标。
 *
 * 所有 DERIVED 指标都是本地计算，不是 GMGN 原始字段。
 * 数据规则：缺失 = null；真实 0 = 0；分母为 0 或缺失 → null（不当成 0，也不当成无穷大）。
 * 不读 liquidity / honeypot / wash / tax / signal_type / renounced(EVM) / K.amount。
 */

export const DAY_SEC = 86400;
/** 活跃度与名次对比的回看距离。 */
export const LOOKBACK_SEC = 3600;
/** 基准事件允许偏离回看点的范围（事件不是固定频率快照）。 */
export const LOOKBACK_TOLERANCE_SEC = 1800;
/** 日成交额加速度：最新已定稿日 / 之前 N 根已定稿日的均值。 */
export const DAILY_VOLUME_BASE_DAYS = 7;
/** 突破：最新已定稿收盘 ≥ 之前 N 根已定稿日的最高价。 */
export const BREAKOUT_DAYS = 7;
export const CANDIDATE_MIN_SCORE = 3;

/** "" / null / undefined / 非数字 → null；"0" / 0 → 0。 */
export function num(v: unknown): number | null {
  if (v == null) return null;
  if (typeof v === "string" && v.trim() === "") return null;
  if (typeof v === "boolean") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** a / b；任一缺失或 b ≤ 0 → null。 */
export function ratio(a: number | null, b: number | null): number | null {
  if (a == null || b == null || b <= 0) return null;
  return a / b;
}

/** 某个发现源事件里携带的 24h 活跃度快照（笔数，不是人数）。 */
export interface ActivityPoint {
  seenAt: number;
  source: string;
  variant: string;
  rank: number | null;
  buys: number | null;
  sells: number | null;
  swaps: number | null;
  volume: number | null;
}

type Meta = Record<string, unknown>;

function pick(meta: Meta, ...keys: string[]): number | null {
  for (const k of keys) {
    if (k in meta) return num(meta[k]);
  }
  return null;
}

/**
 * discovery_event.metadata_json → 活跃度点。
 * Trending / Hot 用 buys / sells / swaps / volume；Trenches 用 *_24h。
 */
export function activityFromMeta(
  source: string,
  variant: string,
  seenAt: number,
  rank: number | null,
  meta: Meta | null,
): ActivityPoint {
  const m = meta ?? {};
  const trench = source === "trenches";
  return {
    seenAt,
    source,
    variant,
    rank,
    buys: trench ? pick(m, "buys_24h") : pick(m, "buys"),
    sells: trench ? pick(m, "sells_24h") : pick(m, "sells"),
    swaps: trench ? pick(m, "swaps_24h", "swaps") : pick(m, "swaps"),
    volume: trench ? pick(m, "volume_24h", "volume") : pick(m, "volume"),
  };
}

/**
 * 同 source + variant 中，seenAt 最接近 (latest − lag) 的点，且偏差 ≤ tolerance。
 * points 可乱序。找不到 → null（不是 0）。
 */
export function pickBaseline(
  points: ActivityPoint[],
  latest: ActivityPoint,
  lag = LOOKBACK_SEC,
  tolerance = LOOKBACK_TOLERANCE_SEC,
): ActivityPoint | null {
  const target = latest.seenAt - lag;
  let best: ActivityPoint | null = null;
  let bestGap = Infinity;
  for (const p of points) {
    if (p.source !== latest.source || p.variant !== latest.variant) continue;
    if (p.seenAt >= latest.seenAt) continue;
    const gap = Math.abs(p.seenAt - target);
    if (gap <= tolerance && gap < bestGap) {
      best = p;
      bestGap = gap;
    }
  }
  return best;
}

/** 最新一个带活跃度的点。优先 trending，其次 hot，再次 trenches；同级取最新。 */
export function latestActivity(points: ActivityPoint[]): ActivityPoint | null {
  const prio: Record<string, number> = { trending: 0, hot: 1, trenches: 2 };
  let best: ActivityPoint | null = null;
  for (const p of points) {
    if (p.buys == null && p.sells == null && p.swaps == null && p.volume == null) continue;
    if (!(p.source in prio)) continue;
    if (
      best == null ||
      prio[p.source]! < prio[best.source]! ||
      (prio[p.source] === prio[best.source] && p.seenAt > best.seenAt)
    ) {
      best = p;
    }
  }
  return best;
}

export interface RankMove {
  /** 名次上升为正：baseline − current。新进榜或掉榜为 null，用 entered 表示。 */
  move: number | null;
  current: number | null;
  baseline: number | null;
  /** 回看点不在榜、现在在榜。 */
  entered: boolean;
  /** 有没有可比的回看窗口（最早事件早于回看点）。没有就不能说"新进榜"。 */
  comparable: boolean;
}

/**
 * 同一 endpoint + 同一请求参数（variant）的名次变化。不同 endpoint 的名次不可比。
 * points 只含该 source + variant 的事件。
 */
export function rankMovement(
  points: { seenAt: number; rank: number | null }[],
  now: number,
  windowStart: number,
  lag = LOOKBACK_SEC,
  tolerance = LOOKBACK_TOLERANCE_SEC,
  freshSec = 900,
): RankMove {
  const ranked = points.filter((p) => p.rank != null).sort((a, b) => b.seenAt - a.seenAt);
  const latest = ranked[0];
  const current = latest && now - latest.seenAt <= freshSec ? latest.rank : null;
  const target = (latest?.seenAt ?? now) - lag;
  let baseline: number | null = null;
  let gap = Infinity;
  for (const p of ranked) {
    const g = Math.abs(p.seenAt - target);
    if (g <= tolerance && g < gap && p !== latest) {
      baseline = p.rank;
      gap = g;
    }
  }
  const comparable = windowStart <= target - tolerance;
  return {
    move: current != null && baseline != null ? baseline - current : null,
    current,
    baseline,
    entered: comparable && current != null && baseline == null,
    comparable,
  };
}

/** 已定稿日 K（只读这里，不改 finalized 规则；调用方传入 getFinalizedDailyBars 的结果）。 */
export interface FinalBar {
  ts: number;
  high: number;
  close: number;
  volume: number | null;
}

/** 最新已定稿日成交额 / 之前 N 根已定稿日的均值。要求 N+1 根连续。 */
export function dailyVolumeAccel(bars: FinalBar[], n = DAILY_VOLUME_BASE_DAYS): number | null {
  if (bars.length < n + 1) return null;
  const tail = bars.slice(-(n + 1));
  for (let i = 1; i < tail.length; i++) {
    if (tail[i]!.ts - tail[i - 1]!.ts !== DAY_SEC) return null;
  }
  const last = tail[tail.length - 1]!.volume;
  const base = tail.slice(0, n).map((b) => b.volume);
  if (last == null || base.some((v) => v == null)) return null;
  const mean = (base as number[]).reduce((s, v) => s + v, 0) / n;
  return ratio(last, mean);
}

/** 最新已定稿收盘 ≥ 之前 N 根已定稿日最高价。数据不足 → null。 */
export function breakout(bars: FinalBar[], n = BREAKOUT_DAYS): boolean | null {
  if (bars.length < n + 1) return null;
  const tail = bars.slice(-(n + 1));
  for (let i = 1; i < tail.length; i++) {
    if (tail[i]!.ts - tail[i - 1]!.ts !== DAY_SEC) return null;
  }
  const last = tail[tail.length - 1]!;
  const prevHigh = Math.max(...tail.slice(0, n).map((b) => b.high));
  return last.close >= prevHigh;
}

/** pc1h − pc24h / 24，单位：百分点。两者都是 GMGN 百分数（25 = +25%）。 */
export function priceAccel(pc1hPct: number | null, pc24hPct: number | null): number | null {
  if (pc1hPct == null || pc24hPct == null) return null;
  return pc1hPct - pc24hPct / 24;
}

export type SolAuthority = "RENOUNCED" | "NOT_RENOUNCED" | "UNKNOWN" | "NOT_APPLICABLE";

/** renounced_mint / renounced_freeze_account 只在 SOL 有意义；EVM 的 false 是"不适用"。 */
export function solAuthority(chain: string, renounced: boolean | null): SolAuthority {
  if (chain !== "sol") return "NOT_APPLICABLE";
  if (renounced == null) return "UNKNOWN";
  return renounced ? "RENOUNCED" : "NOT_RENOUNCED";
}

export interface DerivedInput {
  buys: number | null;
  sells: number | null;
  latest: ActivityPoint | null;
  baseline: ActivityPoint | null;
  pc1hPct: number | null;
  /** 只有窗口确认是 24h（Trending --interval 24h）时才传；否则 null。 */
  pc24hPct: number | null;
  volume24h: number | null;
  fdv: number | null;
  trendingRank: RankMove | null;
  hotRank: RankMove | null;
  finalBars: FinalBar[];
}

export interface DerivedMetrics {
  buySellRatio: number | null;
  buysAccel1h: number | null;
  sellsAccel1h: number | null;
  swapsAccel1h: number | null;
  volumeAccel1h: number | null;
  activityBaselineAt: number | null;
  activityContext: string | null;
  priceAccel: number | null;
  trendingRankMove1h: number | null;
  trendingNewEntry: boolean;
  hotRankMove1h: number | null;
  hotNewEntry: boolean;
  volumeToFdv: number | null;
  dailyVolumeAccel: number | null;
  breakout7d: boolean | null;
}

export function deriveMetrics(input: DerivedInput): DerivedMetrics {
  const { latest, baseline } = input;
  const accel = (k: "buys" | "sells" | "swaps" | "volume") =>
    latest && baseline ? ratio(latest[k], baseline[k]) : null;
  return {
    buySellRatio: input.buys != null && input.sells != null ? ratio(input.buys, input.buys + input.sells) : null,
    buysAccel1h: accel("buys"),
    sellsAccel1h: accel("sells"),
    swapsAccel1h: accel("swaps"),
    volumeAccel1h: accel("volume"),
    activityBaselineAt: baseline?.seenAt ?? null,
    activityContext: latest ? `${latest.source}${latest.variant ? `/${latest.variant}` : ""}` : null,
    priceAccel: priceAccel(input.pc1hPct, input.pc24hPct),
    trendingRankMove1h: input.trendingRank?.move ?? null,
    trendingNewEntry: input.trendingRank?.entered ?? false,
    hotRankMove1h: input.hotRank?.move ?? null,
    hotNewEntry: input.hotRank?.entered ?? false,
    volumeToFdv: ratio(input.volume24h, input.fdv),
    dailyVolumeAccel: dailyVolumeAccel(input.finalBars),
    breakout7d: breakout(input.finalBars),
  };
}

export interface ScoreRule {
  id: string;
  label: string;
  test: (d: DerivedMetrics) => boolean | null;
}

/** 每条 1 分。test 返回 null = 输入缺失，不计分也不计入"已评估"。 */
export const SCORE_RULES: ScoreRule[] = [
  { id: "buys_accel", label: "买入笔数 1h 增长 ≥ 20%", test: (d) => (d.buysAccel1h == null ? null : d.buysAccel1h >= 1.2) },
  { id: "swaps_accel", label: "交易笔数 1h 增长 ≥ 20%", test: (d) => (d.swapsAccel1h == null ? null : d.swapsAccel1h >= 1.2) },
  { id: "volume_accel", label: "24h 成交额 1h 增长 ≥ 20%", test: (d) => (d.volumeAccel1h == null ? null : d.volumeAccel1h >= 1.2) },
  { id: "buy_pressure", label: "买入笔数占比 ≥ 60%", test: (d) => (d.buySellRatio == null ? null : d.buySellRatio >= 0.6) },
  { id: "price_accel", label: "1h 涨幅比 24h 均速快 ≥ 2 个百分点", test: (d) => (d.priceAccel == null ? null : d.priceAccel >= 2) },
  {
    id: "rank_up",
    label: "Trending 名次 1h 上升 ≥ 10 或新进榜",
    test: (d) => (d.trendingNewEntry ? true : d.trendingRankMove1h == null ? null : d.trendingRankMove1h >= 10),
  },
  { id: "turnover", label: "24h 成交额 / FDV ≥ 0.5", test: (d) => (d.volumeToFdv == null ? null : d.volumeToFdv >= 0.5) },
  { id: "daily_volume", label: "最新已定稿日成交额 ≥ 前 7 日均值 2 倍", test: (d) => (d.dailyVolumeAccel == null ? null : d.dailyVolumeAccel >= 2) },
  { id: "breakout", label: "已定稿收盘突破前 7 日最高", test: (d) => d.breakout7d },
];

export interface DiscoveryScore {
  score: number;
  evaluated: number;
  reasons: string[];
  candidate: boolean;
}

export function discoveryScore(d: DerivedMetrics, minScore = CANDIDATE_MIN_SCORE): DiscoveryScore {
  let score = 0;
  let evaluated = 0;
  const reasons: string[] = [];
  for (const r of SCORE_RULES) {
    const hit = r.test(d);
    if (hit == null) continue;
    evaluated += 1;
    if (hit) {
      score += 1;
      reasons.push(r.label);
    }
  }
  return { score, evaluated, reasons, candidate: score >= minScore };
}
