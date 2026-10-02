import { createServerFn } from "@tanstack/react-start";
import { DatabaseSync } from "node:sqlite";
import { existsSync } from "node:fs";

// forced-trade-monitor 是独立采集链（独立 SQLite，见其 SPEC）。
// 网站只读它；路径可用 FORCED_TRADE_DB 覆盖。
const DEFAULT_DB = "/Users/zhaomosheng/Downloads/forced-trade-monitor/data/forced_trade.sqlite";
const DB_PATH = globalThis.process?.env?.FORCED_TRADE_DB || DEFAULT_DB;

const HOUR_MS = 3_600_000;
const RECENT_BARS = 30;
const RECENT_ALERT_HOURS = 48;

export interface RadarHit {
  symbol: string;
  state: string;
  reason: string | null;
  suppressed: boolean;
  // 命中当时的特征值（研究依据，不是交易建议）
  fundingPct: number | null;
  ret4hVsBtc: number | null;
  oiChg4h: number | null;
  taker4h: number | null;
  basisZ: number | null;
  absRetZ: number | null;
  oiChgZ: number | null;
  flag: string | null;
}

export interface RadarAlert {
  symbol: string;
  barOpenTs: number;
  state: string;
  suppressed: boolean;
  createdAt: number;
}

export interface RadarHealth {
  source: string;
  success: boolean;
  httpStatus: number | null;
  latencyMs: number | null;
  rowsExpected: number | null;
  rowsGot: number | null;
  nullRate: number | null;
  ageSec: number | null;
  tsSemantics: string | null;
  error: string | null;
  ts: number;
}

export interface RadarBar {
  ts: number;
  universe: number;
  hits: number;
  fired: number;
}

export interface RadarData {
  ok: boolean;
  error?: string;
  dbPath: string;
  latestBar: number | null;
  universeCount: number;
  hits: RadarHit[];
  alerts: RadarAlert[];
  health: RadarHealth[];
  bars: RadarBar[];
  readAt: number;
}

type SqlRow = Record<string, string | number | null>;

function num(v: string | number | null): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export const fetchRadar = createServerFn({ method: "GET" }).handler(async (): Promise<RadarData> => {
  const readAt = Date.now();
  const base: RadarData = {
    ok: false,
    dbPath: DB_PATH,
    latestBar: null,
    universeCount: 0,
    hits: [],
    alerts: [],
    health: [],
    bars: [],
    readAt,
  };
  if (!existsSync(DB_PATH)) {
    return { ...base, error: "雷达库不存在：先在 forced-trade-monitor 跑 scripts/init_db.py 和 jobs/run_hourly.py" };
  }
  let db: DatabaseSync;
  try {
    db = new DatabaseSync(DB_PATH, { open: true, readOnly: true });
  } catch (e) {
    return { ...base, error: e instanceof Error ? e.message : String(e) };
  }
  try {
    const latest = db.prepare("SELECT MAX(bar_open_ts) AS ts FROM features_1h").get() as SqlRow | undefined;
    const latestBar = latest ? num(latest.ts) : null;

    let universeCount = 0;
    if (latestBar !== null) {
      const u = db
        .prepare("SELECT COUNT(*) AS c FROM universe_snapshot WHERE ts=?")
        .get(latestBar) as SqlRow | undefined;
      universeCount = u ? Number(u.c ?? 0) : 0;
    }

    // 最新 bar 的命中：states 是事实，alerts 的 suppressed 只影响通知频率。
    const hits: RadarHit[] = [];
    if (latestBar !== null) {
      const rows = db
        .prepare(
          `SELECT s.symbol, s.state, s.reason,
                  COALESCE(a.cooldown_suppressed, 0) AS suppressed,
                  f.funding_pct_30d, f.ret_4h_vs_btc, f.oi_qty_chg_4h,
                  f.taker_imbalance_4h, f.basis_z_7d, f.abs_ret_1h_z,
                  f.oi_chg_1h_z, f.data_quality_flag
           FROM states_1h s
           LEFT JOIN alerts a
             ON a.symbol = s.symbol AND a.bar_open_ts = s.bar_open_ts AND a.state = s.state
           LEFT JOIN features_1h f
             ON f.symbol = s.symbol AND f.bar_open_ts = s.bar_open_ts
           WHERE s.bar_open_ts = ? AND s.hit = 1
           ORDER BY s.symbol, s.state`,
        )
        .all(latestBar) as unknown as SqlRow[];
      for (const r of rows) {
        hits.push({
          symbol: String(r.symbol),
          state: String(r.state),
          reason: r.reason === null ? null : String(r.reason),
          suppressed: Number(r.suppressed ?? 0) === 1,
          fundingPct: num(r.funding_pct_30d),
          ret4hVsBtc: num(r.ret_4h_vs_btc),
          oiChg4h: num(r.oi_qty_chg_4h),
          taker4h: num(r.taker_imbalance_4h),
          basisZ: num(r.basis_z_7d),
          absRetZ: num(r.abs_ret_1h_z),
          oiChgZ: num(r.oi_chg_1h_z),
          flag: r.data_quality_flag === null ? null : String(r.data_quality_flag),
        });
      }
    }

    // 最近 48 小时告警（含冷却抑制行；它们仍记录在案）
    const since = (latestBar ?? readAt) - RECENT_ALERT_HOURS * HOUR_MS;
    const alertRows = db
      .prepare(
        `SELECT symbol, bar_open_ts, state, cooldown_suppressed, created_at
         FROM alerts
         WHERE bar_open_ts >= ?
         ORDER BY bar_open_ts DESC, symbol
         LIMIT 200`,
      )
      .all(since) as unknown as SqlRow[];
    const alerts: RadarAlert[] = alertRows.map((r) => ({
      symbol: String(r.symbol),
      barOpenTs: Number(r.bar_open_ts),
      state: String(r.state),
      suppressed: Number(r.cooldown_suppressed ?? 0) === 1,
      createdAt: Number(r.created_at),
    }));

    // 每个源最新一行健康：不是一句“API 正常”
    const healthRows = db
      .prepare(
        `SELECT h.ts, h.source, h.success, h.http_status, h.latency_ms,
                h.rows_expected, h.rows_got, h.null_rate, h.age_sec,
                h.ts_semantics, h.error
         FROM data_health h
         JOIN (SELECT source, MAX(id) AS id FROM data_health GROUP BY source) m
           ON m.id = h.id
         ORDER BY h.source`,
      )
      .all() as unknown as SqlRow[];
    const health: RadarHealth[] = healthRows.map((r) => ({
      source: String(r.source),
      success: Number(r.success ?? 0) === 1,
      httpStatus: num(r.http_status),
      latencyMs: num(r.latency_ms),
      rowsExpected: num(r.rows_expected),
      rowsGot: num(r.rows_got),
      nullRate: num(r.null_rate),
      ageSec: num(r.age_sec),
      tsSemantics: r.ts_semantics === null ? null : String(r.ts_semantics),
      error: r.error === null ? null : String(r.error),
      ts: Number(r.ts),
    }));

    // 最近 30 个 bar 摘要
    const uniRows = db
      .prepare(
        "SELECT ts, COUNT(*) AS c FROM universe_snapshot GROUP BY ts ORDER BY ts DESC LIMIT ?",
      )
      .all(RECENT_BARS) as unknown as SqlRow[];
    const hitRows = db
      .prepare(
        `SELECT bar_open_ts, COUNT(*) AS c
         FROM states_1h WHERE hit = 1 GROUP BY bar_open_ts`,
      )
      .all() as unknown as SqlRow[];
    const firedRows = db
      .prepare(
        `SELECT bar_open_ts, COUNT(*) AS c
         FROM alerts WHERE cooldown_suppressed = 0 GROUP BY bar_open_ts`,
      )
      .all() as unknown as SqlRow[];
    const hitMap = new Map<number, number>();
    for (const r of hitRows) hitMap.set(Number(r.bar_open_ts), Number(r.c));
    const firedMap = new Map<number, number>();
    for (const r of firedRows) firedMap.set(Number(r.bar_open_ts), Number(r.c));
    const bars: RadarBar[] = uniRows.map((r) => {
      const ts = Number(r.ts);
      return {
        ts,
        universe: Number(r.c),
        hits: hitMap.get(ts) ?? 0,
        fired: firedMap.get(ts) ?? 0,
      };
    });

    return {
      ok: true,
      dbPath: DB_PATH,
      latestBar,
      universeCount,
      hits,
      alerts,
      health,
      bars,
      readAt,
    };
  } catch (e) {
    return { ...base, error: e instanceof Error ? e.message : String(e) };
  } finally {
    db.close();
  }
});
