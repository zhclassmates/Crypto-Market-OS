/**
 * 告警 V1：data → calculation → condition → alert。
 * 条件只能引用 READY 字段与本地 DERIVED 指标。值为 null（缺失）时规则不触发，也不当成 0。
 */

export type AlertField =
  | "price"
  | "pc1h"
  | "pc24h"
  | "volume24h"
  | "buys24h"
  | "sells24h"
  | "swaps24h"
  | "fdv"
  | "holders"
  | "trendingRank"
  | "streak"
  | "changeNd"
  | "buySellRatio"
  | "buysAccel1h"
  | "sellsAccel1h"
  | "swapsAccel1h"
  | "volumeAccel1h"
  | "priceAccel"
  | "trendingRankMove1h"
  | "trendingNewEntry"
  | "volumeToFdv"
  | "dailyVolumeAccel"
  | "breakout7d"
  | "discoveryScore";

export type AlertOp = ">=" | "<=" | "is_true";

export interface AlertFieldSpec {
  field: AlertField;
  label: string;
  kind: "number" | "bool";
  derived: boolean;
  unit: string;
}

export const ALERT_FIELDS: AlertFieldSpec[] = [
  { field: "price", label: "价格", kind: "number", derived: false, unit: "USD" },
  { field: "pc1h", label: "1h 涨跌", kind: "number", derived: false, unit: "%" },
  { field: "pc24h", label: "24h 涨跌（Trending 24h）", kind: "number", derived: false, unit: "%" },
  { field: "volume24h", label: "24h 成交额", kind: "number", derived: false, unit: "USD" },
  { field: "buys24h", label: "24h 买入笔数", kind: "number", derived: false, unit: "笔" },
  { field: "sells24h", label: "24h 卖出笔数", kind: "number", derived: false, unit: "笔" },
  { field: "swaps24h", label: "24h 交易笔数", kind: "number", derived: false, unit: "笔" },
  { field: "fdv", label: "FDV", kind: "number", derived: false, unit: "USD" },
  { field: "holders", label: "持币地址数", kind: "number", derived: false, unit: "地址" },
  { field: "trendingRank", label: "Trending 名次（24h）", kind: "number", derived: false, unit: "名" },
  { field: "streak", label: "日K连涨天数", kind: "number", derived: true, unit: "天" },
  { field: "changeNd", label: "7日累计（已定稿日K）", kind: "number", derived: true, unit: "%" },
  { field: "buySellRatio", label: "买入笔数占比", kind: "number", derived: true, unit: "0–1" },
  { field: "buysAccel1h", label: "买入笔数 1h 增长倍数", kind: "number", derived: true, unit: "×" },
  { field: "sellsAccel1h", label: "卖出笔数 1h 增长倍数", kind: "number", derived: true, unit: "×" },
  { field: "swapsAccel1h", label: "交易笔数 1h 增长倍数", kind: "number", derived: true, unit: "×" },
  { field: "volumeAccel1h", label: "24h 成交额 1h 增长倍数", kind: "number", derived: true, unit: "×" },
  { field: "priceAccel", label: "价格加速度", kind: "number", derived: true, unit: "百分点" },
  { field: "trendingRankMove1h", label: "Trending 名次 1h 上升", kind: "number", derived: true, unit: "名" },
  { field: "trendingNewEntry", label: "新进 Trending 榜", kind: "bool", derived: true, unit: "" },
  { field: "volumeToFdv", label: "成交额 / FDV", kind: "number", derived: true, unit: "×" },
  { field: "dailyVolumeAccel", label: "日成交额 / 前7日均值", kind: "number", derived: true, unit: "×" },
  { field: "breakout7d", label: "突破前 7 日最高", kind: "bool", derived: true, unit: "" },
  { field: "discoveryScore", label: "爆款分", kind: "number", derived: true, unit: "分" },
];

const FIELD_SET = new Set<string>(ALERT_FIELDS.map((f) => f.field));

export interface AlertRule {
  id: string;
  field: AlertField;
  op: AlertOp;
  threshold: number | null;
  enabled: boolean;
  chain: string | null;
}

export type AlertValues = Partial<Record<AlertField, number | boolean | null>>;

export interface AlertSubject {
  chain: string;
  address: string;
  symbol: string | null;
  values: AlertValues;
}

export interface AlertHit {
  key: string;
  ruleId: string;
  chain: string;
  address: string;
  symbol: string | null;
  field: AlertField;
  op: AlertOp;
  threshold: number | null;
  value: number | boolean;
}

export const DEFAULT_RULES: AlertRule[] = [
  { id: "d-score", field: "discoveryScore", op: ">=", threshold: 4, enabled: true, chain: null },
  { id: "d-buys", field: "buysAccel1h", op: ">=", threshold: 1.5, enabled: true, chain: null },
  { id: "d-rank", field: "trendingRankMove1h", op: ">=", threshold: 20, enabled: true, chain: null },
  { id: "d-pc1h", field: "pc1h", op: ">=", threshold: 30, enabled: true, chain: null },
  { id: "d-breakout", field: "breakout7d", op: "is_true", threshold: null, enabled: true, chain: null },
];

export function ruleMatches(rule: AlertRule, value: number | boolean | null | undefined): boolean {
  if (!rule.enabled || value == null) return false;
  if (rule.op === "is_true") return value === true;
  if (typeof value !== "number" || !Number.isFinite(value) || rule.threshold == null) return false;
  return rule.op === ">=" ? value >= rule.threshold : value <= rule.threshold;
}

export function evaluateAlerts(subjects: AlertSubject[], rules: AlertRule[]): AlertHit[] {
  const hits: AlertHit[] = [];
  for (const rule of rules) {
    if (!rule.enabled) continue;
    for (const s of subjects) {
      if (rule.chain && s.chain !== rule.chain) continue;
      const value = s.values[rule.field];
      if (!ruleMatches(rule, value)) continue;
      hits.push({
        key: `${rule.id}|${s.chain}:${s.address}`,
        ruleId: rule.id,
        chain: s.chain,
        address: s.address,
        symbol: s.symbol,
        field: rule.field,
        op: rule.op,
        threshold: rule.threshold,
        value: value as number | boolean,
      });
    }
  }
  return hits;
}

/** 外部输入（localStorage / API 参数）→ 合法规则。丢弃无法识别的条目，不抛错。 */
export function sanitizeRules(raw: unknown): AlertRule[] {
  if (!Array.isArray(raw)) return [];
  const out: AlertRule[] = [];
  for (const r of raw.slice(0, 50)) {
    if (!r || typeof r !== "object") continue;
    const o = r as Record<string, unknown>;
    if (typeof o.id !== "string" || !o.id || o.id.length > 64) continue;
    if (typeof o.field !== "string" || !FIELD_SET.has(o.field)) continue;
    const op = o.op;
    if (op !== ">=" && op !== "<=" && op !== "is_true") continue;
    const threshold = typeof o.threshold === "number" && Number.isFinite(o.threshold) ? o.threshold : null;
    if (op !== "is_true" && threshold == null) continue;
    const spec = ALERT_FIELDS.find((f) => f.field === o.field)!;
    if (spec.kind === "bool" && op !== "is_true") continue;
    if (spec.kind === "number" && op === "is_true") continue;
    out.push({
      id: o.id,
      field: o.field as AlertField,
      op,
      threshold: op === "is_true" ? null : threshold,
      enabled: o.enabled !== false,
      chain: typeof o.chain === "string" && o.chain ? o.chain : null,
    });
  }
  return out;
}

export const RULES_STORAGE_KEY = "rh.alerts.rules.v1";
export const SEEN_STORAGE_KEY = "rh.alerts.seen.v1";

export function loadRules(storage: Pick<Storage, "getItem"> | null): AlertRule[] {
  try {
    const raw = storage?.getItem(RULES_STORAGE_KEY);
    if (raw == null) return DEFAULT_RULES;
    return sanitizeRules(JSON.parse(raw));
  } catch {
    return DEFAULT_RULES;
  }
}

export function saveRules(storage: Pick<Storage, "setItem"> | null, rules: AlertRule[]): void {
  try {
    storage?.setItem(RULES_STORAGE_KEY, JSON.stringify(rules));
  } catch {
    /* 浏览器存储不可用时只在本次会话生效 */
  }
}

/** 本次命中里，之前没见过的 key。 */
export function newHits(hits: AlertHit[], seen: ReadonlySet<string>): AlertHit[] {
  return hits.filter((h) => !seen.has(h.key));
}
