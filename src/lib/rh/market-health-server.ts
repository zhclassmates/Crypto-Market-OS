import { DatabaseSync } from "node:sqlite";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { catalog, classifyStatus, type HealthSource } from "@/lib/rh/market-status";

const DB_PATH = process.env.RH_MARKET_DB || join(process.cwd(), "rh_v2/market.sqlite");

function openDb(): DatabaseSync | null {
  if (!existsSync(DB_PATH)) return null;
  const db = new DatabaseSync(DB_PATH);
  db.exec("PRAGMA busy_timeout=10000");
  return db;
}

function tableExists(db: DatabaseSync, name: string): boolean {
  const row = db.prepare("SELECT 1 AS n FROM sqlite_master WHERE type='table' AND name=?").get(name) as
    | { n: number }
    | undefined;
  return !!row;
}

function age(now: number, ts: number | null): number | null {
  if (!ts) return null;
  return now - ts;
}

export function readMarketHealth(now = Math.floor(Date.now() / 1000)): { now: number; sources: HealthSource[] } {
  const empty = (source: string, chain: string, periodSec: number): HealthSource => ({
    source,
    chain,
    periodSec,
    status: classifyStatus(now, null, 0, false, periodSec, false),
    apiAgeSec: null,
    dbAgeSec: null,
    latencyMs: null,
    p95LatencyMs: null,
    hotChanged: 0,
    coldChanged: 0,
    rowsReceived: 0,
    rowsParsed: 0,
    rowsWritten: 0,
    newAddresses: 0,
    eventsWritten: 0,
    runState: null,
    requestOk: false,
    consecutiveErrors: 0,
    lastError: null,
    sourceTimestampMissing: true,
    collectorHeartbeat: null,
    lastAttempt: null,
    lastSuccess: null,
    sourceTimestamp: null,
    dbWrittenAt: null,
    uiFetchedAt: null,
    lastChangeAt: null,
    attempts: 0,
    successes: 0,
  });

  const db = openDb();
  if (!db) return { now, sources: catalog().map((c) => empty(c.source, c.chain, c.periodSec)) };
  try {
    if (!tableExists(db, "source_health")) {
      return { now, sources: catalog().map((c) => empty(c.source, c.chain, c.periodSec)) };
    }
    const rows = db.prepare("SELECT * FROM source_health").all() as unknown as Record<string, number | string | null>[];
    const byKey = new Map(rows.map((r) => [`${r.source}:${r.chain}`, r]));
    const sources = catalog().map((c) => {
      const r = byKey.get(`${c.source}:${c.chain}`);
      if (!r) return empty(c.source, c.chain, c.periodSec);
      const lastSuccess = (r.last_success as number | null) ?? null;
      const period = Number(r.period_sec ?? c.periodSec);
      const runState = (r.run_state as string | null) ?? null;
      const status = classifyStatus(
        now,
        lastSuccess,
        Number(r.consecutive_errors || 0),
        Number(r.has_display_rows || 0) === 1,
        period,
        Number(r.round_ok || 0) === 1,
        runState,
      );
      let p95: number | null = null;
      if (tableExists(db, "source_latency")) {
        const lats = db
          .prepare(
            "SELECT latency_ms FROM source_latency WHERE source=? AND chain=? AND ts>=? ORDER BY latency_ms",
          )
          .all(c.source, c.chain, now - 120) as unknown as { latency_ms: number }[];
        if (lats.length) {
          const idx = Math.min(lats.length - 1, Math.max(0, Math.ceil(0.95 * lats.length) - 1));
          p95 = lats[idx].latency_ms;
        }
      }
      return {
        source: c.source,
        chain: c.chain,
        periodSec: period,
        status,
        apiAgeSec: age(now, lastSuccess),
        dbAgeSec: age(now, (r.db_written_at as number | null) ?? null),
        latencyMs: (r.latency_ms as number | null) ?? null,
        p95LatencyMs: p95,
        hotChanged: Number(r.hot_changed || 0),
        coldChanged: Number(r.cold_changed || 0),
        rowsReceived: Number(r.rows_received || 0),
        rowsParsed: Number(r.rows_parsed || 0),
        rowsWritten: Number(r.rows_written || 0),
        newAddresses: Number(r.new_addresses || 0),
        eventsWritten: Number(r.events_written || 0),
        runState,
        requestOk: Number(r.request_ok || 0) === 1,
        consecutiveErrors: Number(r.consecutive_errors || 0),
        lastError: (r.last_error as string | null) ?? null,
        sourceTimestampMissing: Number(r.source_timestamp_missing ?? 1) === 1,
        collectorHeartbeat: (r.collector_heartbeat as number | null) ?? null,
        lastAttempt: (r.last_attempt as number | null) ?? null,
        lastSuccess,
        sourceTimestamp: (r.source_timestamp as number | null) ?? null,
        dbWrittenAt: (r.db_written_at as number | null) ?? null,
        uiFetchedAt: (r.ui_fetched_at as number | null) ?? null,
        lastChangeAt: (r.last_change_at as number | null) ?? null,
        attempts: Number(r.attempts || 0),
        successes: Number(r.successes || 0),
      } satisfies HealthSource;
    });
    return { now, sources };
  } finally {
    db.close();
  }
}

/** 只由页面上报。GET 不调用。 */
export function markUiFetched(now = Math.floor(Date.now() / 1000)): void {
  const db = openDb();
  if (!db) return;
  try {
    if (!tableExists(db, "source_health")) return;
    db.prepare("UPDATE source_health SET ui_fetched_at=?").run(now);
  } finally {
    db.close();
  }
}
