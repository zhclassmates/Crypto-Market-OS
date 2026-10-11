import { createServerFn } from "@tanstack/react-start";
import { DatabaseSync } from "node:sqlite";
import { existsSync } from "node:fs";

// world-model-os-v1 是独立采集链（Python, 独立 SQLite）。
// 网站只读它的质量闸门结果；路径可用 WM_MARKET_DB 覆盖。
const DEFAULT_DB = "/Users/zhaomosheng/Desktop/world-model-os-v1/data/world_model_market.sqlite";
const DB_PATH = globalThis.process?.env?.WM_MARKET_DB || DEFAULT_DB;

export type WmQualityStatus = "trusted" | "degraded" | "blocked";

export interface WmQualityProvider {
  provider: string;
  status: WmQualityStatus;
  dateUtc: string;
  checkedAtUtc: string;
  published: number | null;
  knownRange: string | null;
  lastRunStatus: string | null;
  consecutiveFailures: number | null;
  retries14d: number | null;
  reasons: string[];
  notes: string[];
  fixes: string[];
}

export interface WmQualityData {
  ok: boolean;
  error?: string;
  dbPath: string;
  providers: WmQualityProvider[];
  /** 决策准入：被 BLOCKED 的源禁止进入研究模块 */
  blocked: string[];
  readAt: number;
}

type SqlRow = Record<string, string | number | null>;

function asStringArray(json: string | null): string[] {
  if (!json) return [];
  try {
    const v = JSON.parse(json);
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
}

export const fetchWmQuality = createServerFn({ method: "GET" }).handler(async (): Promise<WmQualityData> => {
  const readAt = Date.now();
  const base: WmQualityData = { ok: false, dbPath: DB_PATH, providers: [], blocked: [], readAt };
  if (!existsSync(DB_PATH)) {
    return { ...base, error: "质量库不存在：先在 world-model-os-v1 跑 market_ingest.py" };
  }
  let db: DatabaseSync;
  try {
    db = new DatabaseSync(DB_PATH, { open: true, readOnly: true });
  } catch (e) {
    return { ...base, error: e instanceof Error ? e.message : String(e) };
  }
  try {
    const table = db
      .prepare("SELECT 1 AS n FROM sqlite_master WHERE type='table' AND name='wm_quality_reports'")
      .get() as SqlRow | undefined;
    if (!table) {
      return { ...base, error: "质量闸门尚未运行（缺 wm_quality_reports 表）" };
    }
    // 每个源取最新一次评估报告
    const rows = db
      .prepare(
        `SELECT r.provider, r.date_utc, r.checked_at_utc, r.status, r.metrics, r.reasons, r.fixes
         FROM wm_quality_reports r
         JOIN (SELECT provider, MAX(checked_at_utc) AS mx FROM wm_quality_reports GROUP BY provider) m
           ON m.provider = r.provider AND m.mx = r.checked_at_utc
         ORDER BY r.provider`,
      )
      .all() as unknown as SqlRow[];

    const providers: WmQualityProvider[] = [];
    const blocked: string[] = [];
    for (const r of rows) {
      let metrics: Record<string, unknown> = {};
      try {
        metrics = JSON.parse(String(r.metrics ?? "{}")) as Record<string, unknown>;
      } catch {
        metrics = {};
      }
      const coverage = (metrics.coverage ?? {}) as Record<string, unknown>;
      const freshness = (metrics.freshness ?? {}) as Record<string, unknown>;
      const consistency = (metrics.consistency ?? {}) as Record<string, unknown>;
      const health = (metrics.health ?? {}) as Record<string, unknown>;
      const num = (v: unknown): number | null => {
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
      };
      const published =
        num(coverage.published) ?? num(coverage.records_sum) ?? num(coverage.unique) ?? num(freshness.rows) ?? num(consistency.total);
      const status = String(r.status) as WmQualityStatus;
      if (status === "blocked") blocked.push(String(r.provider));
      providers.push({
        provider: String(r.provider),
        status,
        dateUtc: String(r.date_utc),
        checkedAtUtc: String(r.checked_at_utc),
        published,
        knownRange: coverage.known_range == null ? null : String(coverage.known_range),
        lastRunStatus: health.last_run_status == null ? null : String(health.last_run_status),
        consecutiveFailures: num(health.consecutive_failures),
        retries14d: num(health.retries_14d),
        reasons: asStringArray(r.reasons === null ? null : String(r.reasons)),
        notes: asStringArray(metrics.notes == null ? null : JSON.stringify(metrics.notes)),
        fixes: asStringArray(r.fixes === null ? null : String(r.fixes)),
      });
    }
    return { ok: true, dbPath: DB_PATH, providers, blocked, readAt };
  } catch (e) {
    return { ...base, error: e instanceof Error ? e.message : String(e) };
  } finally {
    db.close();
  }
});
