import { createServerFn } from "@tanstack/react-start";
import { DatabaseSync } from "node:sqlite";
import { existsSync } from "node:fs";

export interface ReasoningData {
  ok: boolean;
  error?: string;
  at: string;
  events: Record<string, unknown>[];
  hypotheses: Record<string, unknown>[];
  evidence: Record<string, unknown>[];
  costs: Record<string, unknown>;
  dailyCosts: Record<string, unknown>;
  checkpoints: Record<string, unknown>[];
  queue: Record<string, unknown>[];
  checks: Record<string, unknown>[];
  audits: Record<string, unknown>[];
  alerts: Record<string, unknown>[];
  runs: Record<string, unknown>[];
}

async function readReasoning(): Promise<ReasoningData> {
  const base: ReasoningData = { ok: false, at: new Date().toISOString(), events: [], hypotheses: [], evidence: [], costs: {}, dailyCosts: {}, checkpoints: [], queue: [], checks: [], audits: [], alerts: [], runs: [] };
  const path = process.env.WM_RESEARCH_DB || "/Users/zhaomosheng/Desktop/world-model-os-v1/data/research.sqlite";
  if (!existsSync(path)) return { ...base, error: "研究库尚未连接，推演记录会在本地扫描后出现。" };
  let db: DatabaseSync | undefined;
  try {
    db = new DatabaseSync(path, { readOnly: true });
    const read = (sql: string, ...args: (string | number)[]) => db!.prepare(sql).all(...args) as Record<string, unknown>[];
    if (!read("SELECT name FROM sqlite_master WHERE type='table' AND name='hypotheses'").length) return { ...base, error: "推演引擎尚未初始化。" };
    const hypotheses: Record<string, unknown>[] = read(`SELECT h.*, e.entity, e.metric, e.score FROM hypotheses h JOIN events e ON e.id=h.event_id WHERE e.is_mock=0 ORDER BY e.score DESC,h.updated_at DESC LIMIT 12`).map((h) => ({
      ...h,
      versions: read("SELECT * FROM hypothesis_versions WHERE hypothesis_id=? ORDER BY id DESC LIMIT 30", String(h.id)).map((v) => ({ ...v, conclusion: JSON.parse(String(v.conclusion)), trigger_evidence: JSON.parse(String(v.trigger_evidence)) })),
    }));
    // Attribution details are restricted to displayed hypotheses, so full private databases are never exported.
    const evidence: Record<string, unknown>[] = [];
    for (const h of hypotheses) {
      for (const row of read("SELECT * FROM event_evidence WHERE event_id=? ORDER BY observed_at DESC LIMIT 5", String(h.event_id))) {
        evidence.push({ ...row, payload: JSON.parse(String(row.payload)) });
      }
    }
    const budgetSql = `SELECT count(*) calls, coalesce(sum(charged_microusd),0) settled, coalesce(sum(CASE WHEN charged_microusd IS NULL THEN reserved_microusd ELSE 0 END),0) reserved FROM ai_cost_ledger WHERE substr(at,1,?)=? OR status IN ('RESERVED','UNCERTAIN')`;
    return { ...base, ok: true, hypotheses, evidence,
      events: read("SELECT * FROM events WHERE is_mock=0 AND date(first_seen)=date('now') ORDER BY score DESC,first_seen DESC LIMIT 12").map((v) => ({ ...v, labels: JSON.parse(String(v.labels)) })),
      costs: { ...read(budgetSql, 7, base.at.slice(0, 7))[0], saved: read("SELECT coalesce(sum(saved_microusd),0) saved FROM reasoning_runs WHERE is_mock=0")[0]?.saved ?? 0 },
      dailyCosts: read(budgetSql, 10, base.at.slice(0, 10))[0] ?? {},
      queue: read("SELECT state,count(*) count FROM reasoning_jobs GROUP BY state"),
      checkpoints: read("SELECT * FROM job_checkpoints ORDER BY updated_at DESC LIMIT 6"),
      checks: read("SELECT c.* FROM hypothesis_checks c JOIN hypotheses h ON h.id=c.hypothesis_id JOIN events e ON e.id=h.event_id WHERE e.is_mock=0 ORDER BY due_at DESC LIMIT 12"),
      audits: read("SELECT a.* FROM reasoning_audits a LEFT JOIN events e ON e.id=a.event_id WHERE coalesce(e.is_mock,0)=0 ORDER BY at DESC LIMIT 8"),
      alerts: read("SELECT a.* FROM reasoning_alerts a JOIN hypotheses h ON h.id=a.hypothesis_id JOIN events e ON e.id=h.event_id WHERE e.is_mock=0 ORDER BY at DESC LIMIT 8"),
      runs: read("SELECT r.event_id,r.tier,r.provider,r.model,r.status,r.at,r.result,r.cache_hits FROM reasoning_runs r WHERE r.is_mock=0 AND r.tier!='L0' ORDER BY r.at DESC LIMIT 5").map((v) => ({ ...v, result: v.result ? JSON.parse(String(v.result)) : null })),
    };
  } catch {
    return { ...base, error: "推演数据暂不可读，稍后重试；现有行情与 Radar 可继续使用。" };
  } finally { db?.close(); }
}

export const fetchWmReasoning = createServerFn({ method: "GET" }).handler(async () => JSON.stringify(await readReasoning()));
