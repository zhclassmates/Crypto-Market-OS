/**
 * 爆款发现 / 告警 / 详情的读库实现。只读 market.sqlite，不发 GMGN 请求，不写库。
 * 与 createServerFn 分开，方便离线 smoke（node --experimental-strip-types）。
 */
import type { DatabaseSync } from "node:sqlite";
import {
  activityFromMeta,
  deriveMetrics,
  discoveryScore,
  latestActivity,
  num,
  pickBaseline,
  rankMovement,
  solAuthority,
  LOOKBACK_SEC,
  LOOKBACK_TOLERANCE_SEC,
  type ActivityPoint,
  type DerivedMetrics,
  type DiscoveryScore,
  type FinalBar,
  type SolAuthority,
} from "./discovery.ts";
import { evaluateAlerts, type AlertHit, type AlertRule, type AlertSubject } from "./alerts.ts";
import {
  classifyBars,
  displayCreated,
  officialDailyMetrics,
  type DailyBar,
  type DailyStatus,
} from "./streak.ts";

/** 发现源窗口：最近这么久在 Trending / Hot / Trenches 出现过的币进入候选池。 */
export const UNIVERSE_SEC = 1800;
/** 事件回看：覆盖 1h 基准点及其容差。 */
const EVENT_WINDOW_SEC = LOOKBACK_SEC + LOOKBACK_TOLERANCE_SEC + 600;
/** 已定稿日 K 回看。 */
const BAR_WINDOW_SEC = 40 * 86400;
const DISCOVERY_SOURCES = ["trending", "hot", "trenches"] as const;
const CHANGE_DAYS = 7;

export interface DiscoveryRow {
  chain: string;
  address: string;
  symbol: string | null;
  name: string | null;
  logo: string | null;
  createdAt: number | null;
  /** GMGN READY 原始字段。null = 未观察到；0 是真实 0。 */
  price: number | null;
  pc1h: number | null; // 百分数，25 = +25%
  pc24h: number | null; // 百分数；只在窗口确认是 Trending 24h 时给出
  pcInterval: string | null; // "24h" 或 null（窗口未确认）
  pcRaw: number | null; // snapshot 中的原值（任意来源），只用于展示
  pcRawSource: string | null;
  volume24h: number | null; // USD
  buys24h: number | null; // 笔
  sells24h: number | null; // 笔
  swaps24h: number | null; // 笔
  fdv: number | null; // GMGN market_cap，FDV 口径（price × total_supply）
  holders: number | null;
  activitySource: string | null;
  activityUpdatedAt: number | null;
  trendingRank: number | null;
  trendingRankContext: string | null;
  trendingRankAt: number | null;
  hotRank: number | null;
  hotRankContext: string | null;
  hotRankAt: number | null;
  signalTriggerAt: number | null;
  signalTriggerMc: number | null;
  solMintAuthority: SolAuthority;
  solFreezeAuthority: SolAuthority;
  streak: number | null;
  changeNd: number | null;
  changeDays: number;
  lastDailyStatus: DailyStatus | null;
  lastSeenAt: number | null;
  sources: string[];
  /** 全部为本地 DERIVED 指标，不是 GMGN 字段。 */
  derived: DerivedMetrics;
  score: DiscoveryScore;
}

interface EventRow {
  chain: string;
  address: string;
  source: string;
  source_variant: string | null;
  seen_at: number;
  rank: number | null;
  metadata_json: string | null;
}

interface SnapshotRow {
  chain: string;
  address: string;
  symbol: string | null;
  name: string | null;
  logo: string | null;
  token_created_at: number | null;
  pair_created_at: number | null;
  price: string | null;
  pc_24h: string | null;
  pc_24h_source: string | null;
  volume_24h: string | null;
  market_cap: string | null;
  holders: number | null;
  swaps: number | null;
  swaps_source: string | null;
  swaps_updated_at: number | null;
  buys_24h: number | null;
  sells_24h: number | null;
  pc_1h: string | null;
  security_renounced_mint: number | null;
  security_renounced_freeze_account: number | null;
}

function optionalCols(db: DatabaseSync, table: string, wanted: string[], alias: string): string {
  const cols = db.prepare(`PRAGMA table_info(${table})`).all() as unknown as { name: string }[];
  const names = new Set(cols.map((c) => c.name));
  return wanted.map((n) => (names.has(n) ? `${alias}.${n}` : `NULL AS ${n}`)).join(", ");
}

function parseMeta(s: string | null): Record<string, unknown> | null {
  if (!s) return null;
  try {
    const v = JSON.parse(s);
    return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function nullableFlag(v: unknown): boolean | null {
  return v == null ? null : Number(v) === 1;
}

const key = (chain: string, address: string) => `${chain}:${address}`;

function loadEvents(db: DatabaseSync, since: number, only: { chain: string; address: string } | null): EventRow[] {
  const sources = "('trending','hot','trenches','signal')";
  if (only) {
    return db
      .prepare(
        `SELECT chain, address, source, source_variant, seen_at, rank, metadata_json
         FROM discovery_event WHERE chain=? AND address=? AND seen_at >= ? AND source IN ${sources}`,
      )
      .all(only.chain, only.address, since) as unknown as EventRow[];
  }
  return db
    .prepare(
      `SELECT chain, address, source, source_variant, seen_at, rank, metadata_json
       FROM discovery_event WHERE seen_at >= ? AND source IN ${sources}`,
    )
    .all(since) as unknown as EventRow[];
}

function loadSnapshots(db: DatabaseSync, keys: Set<string>): Map<string, SnapshotRow> {
  const opt = optionalCols(
    db,
    "token_snapshot",
    [
      "pc_24h_source", "swaps", "swaps_source", "swaps_updated_at", "buys_24h", "sells_24h", "pc_1h",
      "security_renounced_mint", "security_renounced_freeze_account",
    ],
    "s",
  );
  const rows = db
    .prepare(
      `SELECT s.chain, s.address, t.symbol, t.name, t.logo, t.token_created_at, t.pair_created_at,
              s.price, s.pc_24h, s.volume_24h, s.market_cap, s.holders, ${opt}
       FROM token_snapshot s LEFT JOIN tokens t ON t.chain = s.chain AND t.address = s.address`,
    )
    .all() as unknown as SnapshotRow[];
  const out = new Map<string, SnapshotRow>();
  for (const r of rows) {
    const k = key(r.chain, r.address);
    if (keys.has(k)) out.set(k, r);
  }
  return out;
}

function loadBars(db: DatabaseSync, chain: string, address: string, since: number) {
  const cols = db.prepare("PRAGMA table_info(daily_kline)").all() as unknown as { name: string }[];
  const has = new Set(cols.map((c) => c.name));
  const sql = `SELECT ts, open, high, low, close, volume,
                 ${has.has("fetched_at") ? "fetched_at" : "NULL AS fetched_at"},
                 ${has.has("finalized_at") ? "finalized_at" : "NULL AS finalized_at"}
               FROM daily_kline WHERE address=? AND chain=? AND ts >= ? ORDER BY ts ASC`;
  return db.prepare(sql).all(address, chain, since) as unknown as {
    ts: number;
    open: string | null;
    high: string | null;
    low: string | null;
    close: string | null;
    volume: string | null;
    fetched_at: number | null;
    finalized_at: number | null;
  }[];
}

export interface CandleOut {
  ts: number;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null; // USD
  status: DailyStatus;
}

function barsFor(
  db: DatabaseSync,
  chain: string,
  address: string,
  now: number,
  createdAt: number | null,
): { daily: DailyBar[]; finals: FinalBar[]; candles: CandleOut[] } {
  const rows = loadBars(db, chain, address, now - BAR_WINDOW_SEC);
  const daily: DailyBar[] = rows.map((r) => ({
    ts: r.ts,
    high: Number(r.high),
    close: Number(r.close),
    fetchedAt: r.fetched_at ?? null,
    finalizedAt: r.finalized_at ?? null,
  }));
  const byTs = new Map(rows.map((r) => [r.ts, r]));
  // finalized 判定完全复用 streak.ts（classifyBars），这里只把 volume 按 ts 对回去。
  const classified = classifyBars(daily, now, createdAt);
  const finals: FinalBar[] = classified
    .filter((b) => b.status === "FINALIZED")
    .map((b) => ({ ts: b.ts, high: b.high, close: b.close, volume: num(byTs.get(b.ts)?.volume) }));
  const candles: CandleOut[] = classified.map((b) => {
    const r = byTs.get(b.ts);
    return {
      ts: b.ts,
      open: num(r?.open),
      high: num(r?.high),
      low: num(r?.low),
      close: num(r?.close),
      volume: num(r?.volume),
      status: b.status,
    };
  });
  return { daily, finals, candles };
}

interface Built {
  rows: DiscoveryRow[];
  candles: Map<string, CandleOut[]>;
  rankHistory: Map<string, { source: string; variant: string; seenAt: number; rank: number }[]>;
  signals: Map<string, { seenAt: number; triggerAt: number | null; triggerMc: number | null }[]>;
}

function buildRows(
  db: DatabaseSync,
  now: number,
  only: { chain: string; address: string } | null,
): Built {
  const windowStart = now - EVENT_WINDOW_SEC;
  const events = loadEvents(db, only ? now - 86400 : windowStart, only);
  const byToken = new Map<string, EventRow[]>();
  for (const e of events) {
    const k = key(e.chain, e.address);
    let list = byToken.get(k);
    if (!list) byToken.set(k, (list = []));
    list.push(e);
  }
  const universe = new Set<string>();
  if (only) universe.add(key(only.chain, only.address));
  else {
    for (const [k, list] of byToken) {
      if (list.some((e) => (DISCOVERY_SOURCES as readonly string[]).includes(e.source) && e.seen_at >= now - UNIVERSE_SEC)) {
        universe.add(k);
      }
    }
  }
  const snaps = loadSnapshots(db, universe);
  const rows: DiscoveryRow[] = [];
  const candlesOut = new Map<string, CandleOut[]>();
  const rankHistory: Built["rankHistory"] = new Map();
  const signals: Built["signals"] = new Map();

  for (const k of universe) {
    const s = snaps.get(k);
    const [chain, address] = [k.slice(0, k.indexOf(":")), k.slice(k.indexOf(":") + 1)];
    const evs = byToken.get(k) ?? [];
    const recent = evs.filter((e) => e.seen_at >= windowStart);
    const points: ActivityPoint[] = recent
      .filter((e) => (DISCOVERY_SOURCES as readonly string[]).includes(e.source))
      .map((e) => activityFromMeta(e.source, e.source_variant ?? "", e.seen_at, e.rank, parseMeta(e.metadata_json)));
    const latest = latestActivity(points);
    const baseline = latest ? pickBaseline(points, latest) : null;

    const rankPts = (source: string, variant: string) =>
      recent
        .filter((e) => e.source === source && (e.source_variant ?? "") === variant)
        .map((e) => ({ seenAt: e.seen_at, rank: e.rank }));
    const trending = rankMovement(rankPts("trending", "24h"), now, windowStart);
    const hot = rankMovement(rankPts("hot", "24h"), now, windowStart);
    const lastOf = (source: string) =>
      evs.filter((e) => e.source === source).sort((a, b) => b.seen_at - a.seen_at)[0] ?? null;
    const lastTrending = lastOf("trending");
    const lastHot = lastOf("hot");
    const lastSignal = lastOf("signal");
    const sigMeta = parseMeta(lastSignal?.metadata_json ?? null);

    const createdAt = displayCreated(s?.token_created_at ?? null, s?.pair_created_at ?? null).at;
    const { daily, finals, candles } = barsFor(db, chain, address, now, createdAt);
    if (!s && evs.length === 0 && candles.length === 0) continue;
    const metrics = officialDailyMetrics(daily, now, createdAt, CHANGE_DAYS);

    const pcRaw = num(s?.pc_24h);
    const pcSource = s?.pc_24h_source ?? null;
    // price_change_percent 的窗口 = 请求的 --interval。只有 Trending 明确传了 24h。
    const pc24h = pcSource === "trending" ? pcRaw : null;
    const pc1h = num(s?.pc_1h);
    const buys = s?.buys_24h ?? null;
    const sells = s?.sells_24h ?? null;
    const volume24h = num(s?.volume_24h);
    const fdv = num(s?.market_cap);

    const derived = deriveMetrics({
      buys,
      sells,
      latest,
      baseline,
      pc1hPct: pc1h,
      pc24hPct: pc24h,
      volume24h,
      fdv,
      trendingRank: trending,
      hotRank: hot,
      finalBars: finals,
    });

    const freshRank = (e: EventRow | null) => (e && now - e.seen_at <= 900 ? e : null);
    const ft = freshRank(lastTrending);
    const fh = freshRank(lastHot);
    rows.push({
      chain,
      address,
      symbol: s?.symbol ?? null,
      name: s?.name ?? null,
      logo: s?.logo ?? null,
      createdAt,
      price: num(s?.price),
      pc1h,
      pc24h,
      pcInterval: pc24h == null ? null : "24h",
      pcRaw,
      pcRawSource: pcSource,
      volume24h,
      buys24h: buys,
      sells24h: sells,
      swaps24h: s?.swaps ?? null,
      fdv,
      holders: s?.holders ?? null,
      activitySource: s?.swaps_source ?? null,
      activityUpdatedAt: s?.swaps_updated_at ?? null,
      trendingRank: ft?.rank ?? null,
      trendingRankContext: ft ? `trending/${ft.source_variant || "?"}` : null,
      trendingRankAt: ft?.seen_at ?? null,
      hotRank: fh?.rank ?? null,
      hotRankContext: fh ? "hot-searches/默认参数" : null,
      hotRankAt: fh?.seen_at ?? null,
      signalTriggerAt: num(sigMeta?.trigger_at),
      signalTriggerMc: num(sigMeta?.trigger_mc),
      solMintAuthority: solAuthority(chain, nullableFlag(s?.security_renounced_mint)),
      solFreezeAuthority: solAuthority(chain, nullableFlag(s?.security_renounced_freeze_account)),
      streak: metrics.streak,
      changeNd: metrics.changeNd,
      changeDays: CHANGE_DAYS,
      lastDailyStatus: metrics.lastStatus,
      lastSeenAt: evs.length ? Math.max(...evs.map((e) => e.seen_at)) : null,
      sources: [...new Set(recent.map((e) => e.source))].sort(),
      derived,
      score: discoveryScore(derived),
    });
    if (only) {
      candlesOut.set(k, candles);
      rankHistory.set(
        k,
        evs
          .filter((e) => (e.source === "trending" || e.source === "hot") && e.rank != null)
          .sort((a, b) => a.seen_at - b.seen_at)
          .map((e) => ({ source: e.source, variant: e.source_variant ?? "", seenAt: e.seen_at, rank: e.rank! })),
      );
      signals.set(
        k,
        evs
          .filter((e) => e.source === "signal")
          .sort((a, b) => b.seen_at - a.seen_at)
          .map((e) => {
            const m = parseMeta(e.metadata_json);
            return { seenAt: e.seen_at, triggerAt: num(m?.trigger_at), triggerMc: num(m?.trigger_mc) };
          }),
      );
    }
  }
  return { rows, candles: candlesOut, rankHistory, signals };
}

export function alertSubject(r: DiscoveryRow): AlertSubject {
  const d = r.derived;
  return {
    chain: r.chain,
    address: r.address,
    symbol: r.symbol,
    values: {
      price: r.price,
      pc1h: r.pc1h,
      pc24h: r.pc24h,
      volume24h: r.volume24h,
      buys24h: r.buys24h,
      sells24h: r.sells24h,
      swaps24h: r.swaps24h,
      fdv: r.fdv,
      holders: r.holders,
      trendingRank: r.trendingRank,
      streak: r.streak,
      changeNd: r.changeNd == null ? null : r.changeNd * 100,
      buySellRatio: d.buySellRatio,
      buysAccel1h: d.buysAccel1h,
      sellsAccel1h: d.sellsAccel1h,
      swapsAccel1h: d.swapsAccel1h,
      volumeAccel1h: d.volumeAccel1h,
      priceAccel: d.priceAccel,
      trendingRankMove1h: d.trendingRankMove1h,
      trendingNewEntry: d.trendingNewEntry,
      volumeToFdv: d.volumeToFdv,
      dailyVolumeAccel: d.dailyVolumeAccel,
      breakout7d: d.breakout7d,
      discoveryScore: r.score.score,
    },
  };
}

export interface DiscoveryResult {
  ok: true;
  now: number;
  universeSec: number;
  rows: DiscoveryRow[];
  alerts: AlertHit[];
  coverage: {
    universe: number;
    withActivity: number;
    withBaseline: number;
    withPc1h: number;
    withPc24h: number;
    withFinalBars: number;
    candidates: number;
  };
}

export function buildDiscovery(db: DatabaseSync, now: number, rules: AlertRule[]): DiscoveryResult {
  const { rows } = buildRows(db, now, null);
  rows.sort(
    (a, b) =>
      b.score.score - a.score.score ||
      (b.derived.buysAccel1h ?? -1) - (a.derived.buysAccel1h ?? -1) ||
      (b.volume24h ?? -1) - (a.volume24h ?? -1),
  );
  const alerts = evaluateAlerts(rows.map(alertSubject), rules);
  return {
    ok: true,
    now,
    universeSec: UNIVERSE_SEC,
    rows,
    alerts,
    coverage: {
      universe: rows.length,
      withActivity: rows.filter((r) => r.derived.activityContext != null).length,
      withBaseline: rows.filter((r) => r.derived.activityBaselineAt != null).length,
      withPc1h: rows.filter((r) => r.pc1h != null).length,
      withPc24h: rows.filter((r) => r.pc24h != null).length,
      withFinalBars: rows.filter((r) => r.derived.dailyVolumeAccel != null || r.derived.breakout7d != null).length,
      candidates: rows.filter((r) => r.score.candidate).length,
    },
  };
}

export interface TokenDetail {
  ok: true;
  row: DiscoveryRow;
  candles: CandleOut[];
  rankHistory: { source: string; variant: string; seenAt: number; rank: number }[];
  signals: { seenAt: number; triggerAt: number | null; triggerMc: number | null }[];
}

export function buildTokenDetail(db: DatabaseSync, chain: string, address: string, now: number): TokenDetail | null {
  const built = buildRows(db, now, { chain, address });
  const row = built.rows[0];
  if (!row) return null;
  const k = key(chain, address);
  return {
    ok: true,
    row,
    candles: built.candles.get(k) ?? [],
    rankHistory: built.rankHistory.get(k) ?? [],
    signals: built.signals.get(k) ?? [],
  };
}
