/**
 * Recent Access Radar 的纯函数层：事件类型 → 中文标签 / 方向 / 严重度、身份解析状态、置信度展示、
 * 来源健康汇总、时间格式化（UTC 毫秒 → UTC+8）。不读库、不联网；读库在 access-server.ts。
 *
 * 口径全部跟随 access_radar/schema.sql、radar_core.py、access_db.py、STATE_MACHINE.md：
 * - event_type 由 radar_core.derive_event_type 推导，这里只做反向解析，不发明新类型；
 * - confidence / independent_source_count 原样展示后端存的值，不在前端重算；
 * - 采集时钟状态与 access_db.classify_status 同一套规则（LIVE / DELAYED / STALE / FAILED / DOWN ...）。
 */
import { ACCESS_CHAIN_TO_MARKET, MARKET_TO_ACCESS_CHAINS } from "./market-chains.ts";

// ----------------------------------------------------------------------------- 后端枚举（schema.sql CHECK 约束）
export const ACCESS_KINDS = [
  "SPOT",
  "PERP",
  "CATALOG",
  "ALPHA",
  "ROADMAP",
  "FIAT_ROUTE",
  "DEPOSIT_NETWORK",
  "WITHDRAW_NETWORK",
  "COLLATERAL",
  "LENDING",
  "CHAIN_DEPLOYMENT",
] as const;
export type AccessKind = (typeof ACCESS_KINDS)[number];

export const ACCESS_STATUSES = ["NONE", "ANNOUNCED", "LIVE", "SUSPENDED", "REMOVED"] as const;
export type AccessStatus = (typeof ACCESS_STATUSES)[number];

export const EVENT_FAMILIES = ["ADD", "SUSPEND", "RESUME", "REMOVE", "TIER"] as const;
export type EventFamily = (typeof EVENT_FAMILIES)[number];

export const FIAT_TIERS = ["SUPPORTED", "QUOTABLE", "CONFIRMED"] as const;
export type FiatTier = (typeof FIAT_TIERS)[number];

export const RESOLUTION_STATUSES = ["CONFIRMED", "SUGGESTED", "UNRESOLVED"] as const;
export type ResolutionStatus = (typeof RESOLUTION_STATUSES)[number];

export const SOURCE_TIERS = [
  "OFFICIAL_STRUCTURED",
  "OFFICIAL_ANNOUNCEMENT",
  "THIRD_PARTY",
  "AGGREGATOR",
  "LLM_EXTRACTED",
] as const;
export type SourceTier = (typeof SOURCE_TIERS)[number];

/** 库未初始化时提示用户执行的命令。 */
export const ACCESS_INIT_HINT = "python3 access_radar/access_run.py once";

/** access_run.py feed --window 的取值。 */
export const FEED_WINDOWS = ["1h", "6h", "24h", "3d", "7d"] as const;
export type FeedWindow = (typeof FEED_WINDOWS)[number];
const WINDOW_MS: Record<FeedWindow, number> = {
  "1h": 3_600_000,
  "6h": 6 * 3_600_000,
  "24h": 24 * 3_600_000,
  "3d": 3 * 86_400_000,
  "7d": 7 * 86_400_000,
};

export function windowMs(w: string | null | undefined): number {
  return WINDOW_MS[(w ?? "") as FeedWindow] ?? WINDOW_MS["24h"];
}

// ----------------------------------------------------------------------------- 时间（UTC ms → UTC+8）
export const TZ_LABEL = "UTC+8";
const TZ_OFFSET_MS = 8 * 3_600_000;

function isTs(ms: number | null | undefined): ms is number {
  return typeof ms === "number" && Number.isFinite(ms) && ms > 0;
}

function parts8(ms: number) {
  const d = new Date(ms + TZ_OFFSET_MS);
  const p = (n: number) => String(n).padStart(2, "0");
  return {
    y: String(d.getUTCFullYear()),
    mo: p(d.getUTCMonth() + 1),
    d: p(d.getUTCDate()),
    h: p(d.getUTCHours()),
    mi: p(d.getUTCMinutes()),
    s: p(d.getUTCSeconds()),
  };
}

/** "10-04 20:48"（UTC+8），与运行环境时区无关。 */
export function fmtTs8(ms: number | null | undefined): string {
  if (!isTs(ms)) return "—";
  const t = parts8(ms);
  return `${t.mo}-${t.d} ${t.h}:${t.mi}`;
}

/** "2026-10-04 20:48:10 UTC+8"。 */
export function fmtTs8Full(ms: number | null | undefined): string {
  if (!isTs(ms)) return "—";
  const t = parts8(ms);
  return `${t.y}-${t.mo}-${t.d} ${t.h}:${t.mi}:${t.s} ${TZ_LABEL}`;
}

/** 相对时间："刚刚" / "5 分钟前" / "3 小时后"。 */
export function fmtAgo(now: number, ms: number | null | undefined): string {
  if (!isTs(ms)) return "—";
  const diff = now - ms;
  const future = diff < 0;
  const s = Math.floor(Math.abs(diff) / 1000);
  if (s < 30) return future ? "即将" : "刚刚";
  let v: string;
  if (s < 3600) v = `${Math.max(1, Math.floor(s / 60))} 分钟`;
  else if (s < 86400) v = `${Math.floor(s / 3600)} 小时`;
  else v = `${Math.floor(s / 86400)} 天`;
  return future ? `${v}后` : `${v}前`;
}

/** 秒数年龄的紧凑写法（与 market-status.fmtAge 一致）："45s" / "3m" / "2h5m" / "3d"。 */
export function fmtAgeMs(ageMs: number | null | undefined): string {
  if (ageMs == null || !Number.isFinite(ageMs)) return "—";
  const s = Math.max(0, Math.floor(ageMs / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) {
    const m = Math.floor((s % 3600) / 60);
    return `${Math.floor(s / 3600)}h${m ? `${m}m` : ""}`;
  }
  return `${Math.floor(s / 86400)}d`;
}

// ----------------------------------------------------------------------------- 中文标签
export const KIND_LABEL: Record<AccessKind, string> = {
  SPOT: "现货",
  PERP: "永续",
  CATALOG: "目录",
  ALPHA: "Alpha",
  ROADMAP: "路线图",
  FIAT_ROUTE: "法币通道",
  DEPOSIT_NETWORK: "充值",
  WITHDRAW_NETWORK: "提现",
  COLLATERAL: "抵押",
  LENDING: "借贷",
  CHAIN_DEPLOYMENT: "链部署",
};

export const STATUS_LABEL: Record<AccessStatus, string> = {
  NONE: "未上线",
  ANNOUNCED: "已公告",
  LIVE: "可用",
  SUSPENDED: "暂停",
  REMOVED: "已下架",
};

export type Tone = "up" | "down" | "warn" | "muted";

export const STATUS_TONE: Record<AccessStatus, Tone> = {
  NONE: "muted",
  ANNOUNCED: "warn",
  LIVE: "up",
  SUSPENDED: "warn",
  REMOVED: "down",
};

export const FIAT_TIER_LABEL: Record<FiatTier, string> = {
  SUPPORTED: "列表支持",
  QUOTABLE: "可报价",
  CONFIRMED: "实测可买",
};

export const PLATFORM_TYPE_LABEL: Record<string, string> = {
  CEX: "交易所",
  DEX: "DEX",
  ONRAMP: "法币入金",
  ONRAMP_AGGREGATOR: "入金聚合",
  ISSUER: "发行方",
  LENDING: "借贷",
  PERP_DEX: "永续 DEX",
  WALLET: "钱包",
  CHAIN: "公链",
  DATA_VENDOR: "数据商",
  OTHER: "其他",
};

export const TIER_LABEL: Record<SourceTier, string> = {
  OFFICIAL_STRUCTURED: "官方结构化",
  OFFICIAL_ANNOUNCEMENT: "官方公告",
  THIRD_PARTY: "第三方",
  AGGREGATOR: "聚合器",
  LLM_EXTRACTED: "文本抽取",
};

/** 仅用于排序 / 挑“最强来源”展示，与 radar_core.TIER_WEIGHTS 相同；置信度本身用后端存的值。 */
export const TIER_RANK: Record<SourceTier, number> = {
  OFFICIAL_STRUCTURED: 5,
  OFFICIAL_ANNOUNCEMENT: 4,
  THIRD_PARTY: 3,
  AGGREGATOR: 2,
  LLM_EXTRACTED: 1,
};

export function kindLabel(kind: string | null | undefined): string {
  if (!kind) return "—";
  return KIND_LABEL[kind as AccessKind] ?? kind;
}

export function statusLabel(s: string | null | undefined): string {
  if (!s) return "—";
  return STATUS_LABEL[s as AccessStatus] ?? s;
}

export function statusTone(s: string | null | undefined): Tone {
  return STATUS_TONE[s as AccessStatus] ?? "muted";
}

export function platformTypeLabel(t: string | null | undefined): string {
  if (!t) return "—";
  return PLATFORM_TYPE_LABEL[t] ?? t;
}

export function tierLabel(t: string | null | undefined): string {
  if (!t) return "—";
  return TIER_LABEL[t as SourceTier] ?? t;
}

// ----------------------------------------------------------------------------- event_type 解析
/** radar_core._ADD_LIVE_NAMES 的反查表。 */
const ADD_LIVE_NAMES: Record<string, AccessKind> = {
  SPOT_LISTED: "SPOT",
  PERP_LISTED: "PERP",
  ALPHA_LISTED: "ALPHA",
  CATALOG_ADDED: "CATALOG",
  ROADMAP_ADDED: "ROADMAP",
  CHAIN_DEPLOYED: "CHAIN_DEPLOYMENT",
  DEPOSIT_ENABLED: "DEPOSIT_NETWORK",
  WITHDRAW_ENABLED: "WITHDRAW_NETWORK",
  COLLATERAL_ENABLED: "COLLATERAL",
  LENDING_ENABLED: "LENDING",
};
/** radar_core._SHORT：SUSPEND / RESUME 时充值、提现网络用短前缀。 */
const SHORT_KIND: Partial<Record<AccessKind, string>> = {
  DEPOSIT_NETWORK: "DEPOSIT",
  WITHDRAW_NETWORK: "WITHDRAW",
};

export type EventAction =
  | "ANNOUNCED"
  | "LISTED"
  | "RELISTED"
  | "LISTED_SUSPENDED"
  | "FIAT_TIER"
  | "SUSPENDED"
  | "RESUMED"
  | "DELISTED"
  | "REMOVED"
  | "ANNOUNCEMENT_CANCELLED"
  | "UNKNOWN";

export interface ParsedEventType {
  eventType: string;
  kind: AccessKind | null;
  action: EventAction;
  fiatTier: FiatTier | null;
  /** 官方下架公告、生效时间在未来（`<基础类型>_SCHEDULED`）。 */
  scheduled: boolean;
}

const SUFFIX_ACTION: Record<string, EventAction> = {
  ANNOUNCED: "ANNOUNCED",
  RELISTED: "RELISTED",
  LISTED_SUSPENDED: "LISTED_SUSPENDED",
  SUSPENDED: "SUSPENDED",
  RESUMED: "RESUMED",
  DELISTED: "DELISTED",
  REMOVED: "REMOVED",
  ANNOUNCEMENT_CANCELLED: "ANNOUNCEMENT_CANCELLED",
  LIVE: "LISTED", // derive_event_type 的兜底 f"{kind}_LIVE"
};

const KINDS_BY_LEN = [...ACCESS_KINDS].sort((a, b) => b.length - a.length);

function isKind(k: string | null | undefined): k is AccessKind {
  return !!k && (ACCESS_KINDS as readonly string[]).includes(k);
}

/**
 * 反向解析 radar_core.derive_event_type 的输出。accessKind（access_event.access_kind）给出时优先用它切前缀。
 * 解析不了的类型 action = UNKNOWN，标签原样显示，不猜。
 */
export function parseEventType(eventType: string, accessKind?: string | null): ParsedEventType {
  const raw = (eventType || "").trim().toUpperCase();
  let base = raw;
  let scheduled = false;
  if (base.endsWith("_SCHEDULED")) {
    scheduled = true;
    base = base.slice(0, -"_SCHEDULED".length);
  }
  const out = (kind: AccessKind | null, action: EventAction, fiatTier: FiatTier | null = null): ParsedEventType => ({
    eventType: raw,
    kind,
    action,
    fiatTier,
    scheduled,
  });

  if (ADD_LIVE_NAMES[base] && (!isKind(accessKind) || ADD_LIVE_NAMES[base] === accessKind)) {
    return out(ADD_LIVE_NAMES[base], "LISTED");
  }
  const candidates: AccessKind[] = isKind(accessKind) ? [accessKind] : KINDS_BY_LEN;
  // 先试完整 kind，再试短前缀（DEPOSIT_NETWORK_ANNOUNCED 不能被 DEPOSIT_ 截走）
  for (const pass of ["full", "short"] as const) {
    for (const kind of candidates) {
      const prefix = pass === "full" ? kind : SHORT_KIND[kind];
      if (!prefix || !base.startsWith(prefix + "_")) continue;
      const rest = base.slice(prefix.length + 1);
      if (kind === "FIAT_ROUTE" && (FIAT_TIERS as readonly string[]).includes(rest)) {
        return out(kind, "FIAT_TIER", rest as FiatTier);
      }
      const action = SUFFIX_ACTION[rest];
      if (action) return out(kind, action);
    }
  }
  if (isKind(accessKind) && ADD_LIVE_NAMES[base]) return out(ADD_LIVE_NAMES[base], "LISTED");
  return out(isKind(accessKind) ? accessKind : null, "UNKNOWN");
}

export type EventDirection = "up" | "down" | "pause" | "neutral";
/** 3 = 可交易性的重大变化；2 = 其他入口变化 / 暂停；1 = 恢复、通道升级等次要变化。 */
export type EventSeverity = 1 | 2 | 3;

export type EventCategory = "listing" | "announce" | "fiat" | "chain" | "pause" | "remove" | "other";

export const EVENT_CATEGORIES: { id: EventCategory; label: string }[] = [
  { id: "listing", label: "上线" },
  { id: "announce", label: "公告" },
  { id: "fiat", label: "法币通道" },
  { id: "chain", label: "链部署" },
  { id: "pause", label: "暂停/恢复" },
  { id: "remove", label: "下架" },
  { id: "other", label: "其他" },
];

export interface EventDescription extends ParsedEventType {
  label: string;
  kindLabel: string;
  actionLabel: string;
  direction: EventDirection;
  severity: EventSeverity;
  tone: Tone;
  category: EventCategory;
}

const MAJOR_KINDS: readonly string[] = ["SPOT", "PERP", "ALPHA"];

const ADD_LIVE_LABEL: Record<AccessKind, string> = {
  SPOT: "现货上线",
  PERP: "永续上线",
  ALPHA: "Alpha 上线",
  CATALOG: "目录新增",
  ROADMAP: "列入路线图",
  CHAIN_DEPLOYMENT: "新链部署",
  DEPOSIT_NETWORK: "开放充值",
  WITHDRAW_NETWORK: "开放提现",
  COLLATERAL: "可作抵押",
  LENDING: "开放借贷",
  FIAT_ROUTE: "法币通道上线",
};

function actionText(p: ParsedEventType, kl: string): string {
  switch (p.action) {
    case "LISTED":
      return p.kind ? ADD_LIVE_LABEL[p.kind] : "上线";
    case "FIAT_TIER":
      return `${kl}·${p.fiatTier ? FIAT_TIER_LABEL[p.fiatTier] : "支持"}`;
    case "ANNOUNCED":
      return `${kl}上线公告`;
    case "RELISTED":
      return `${kl}重新上线`;
    case "LISTED_SUSPENDED":
      return `${kl}上线即暂停`;
    case "SUSPENDED":
      return `${kl}暂停`;
    case "RESUMED":
      return `${kl}恢复`;
    case "DELISTED":
      return `${kl}下架`;
    case "REMOVED":
      return `${kl}移除`;
    case "ANNOUNCEMENT_CANCELLED":
      return `${kl}公告取消`;
    default:
      return p.eventType || "未知事件";
  }
}

/** event_type → 中文标签、方向、严重度、分类。family（access_event.family）给出时用于 TIER 判断。 */
export function describeEvent(
  eventType: string,
  accessKind?: string | null,
  family?: string | null,
): EventDescription {
  const p = parseEventType(eventType, accessKind);
  const kl = p.kind ? KIND_LABEL[p.kind] : "";
  let label = actionText(p, kl);
  if (p.scheduled) label = `${label}（预告）`;
  const major = p.kind != null && MAJOR_KINDS.includes(p.kind);
  let direction: EventDirection = "neutral";
  let severity: EventSeverity = 1;
  let category: EventCategory = "other";
  switch (p.action) {
    case "LISTED":
    case "RELISTED":
      direction = "up";
      severity = major ? 3 : 2;
      category = p.kind === "FIAT_ROUTE" ? "fiat" : p.kind === "CHAIN_DEPLOYMENT" ? "chain" : "listing";
      break;
    case "FIAT_TIER":
      direction = "up";
      // ADD → LIVE 的法币通道是新入口（2）；LIVE 状态下 tier 升级（family TIER）是次要变化（1）
      severity = family === "TIER" ? 1 : 2;
      category = "fiat";
      break;
    case "ANNOUNCED":
      direction = "up";
      severity = major ? 3 : 2;
      category = "announce";
      break;
    case "LISTED_SUSPENDED":
      direction = "pause";
      severity = 2;
      category = p.kind === "FIAT_ROUTE" ? "fiat" : p.kind === "CHAIN_DEPLOYMENT" ? "chain" : "listing";
      break;
    case "SUSPENDED":
      direction = "pause";
      severity = 2;
      category = "pause";
      break;
    case "RESUMED":
      direction = "up";
      severity = 1;
      category = "pause";
      break;
    case "DELISTED":
    case "REMOVED":
      direction = "down";
      severity = major ? 3 : 2;
      category = "remove";
      break;
    case "ANNOUNCEMENT_CANCELLED":
      direction = "down";
      severity = 2;
      category = "remove";
      break;
    default:
      break;
  }
  const tone: Tone = direction === "up" ? "up" : direction === "down" ? "down" : direction === "pause" ? "warn" : "muted";
  return { ...p, label, kindLabel: kl || "—", actionLabel: label, direction, severity, tone, category };
}

// ----------------------------------------------------------------------------- 资产身份
export interface AssetKeyInfo {
  /** crypto / ca = 有链+合约；xstocks / ondo 等 = 发行方身份；symbol = 只有代号（sym:REZ）。 */
  type: "crypto" | "ca" | "issuer" | "symbol" | "other";
  chain: string | null;
  contract: string | null;
  symbol: string | null;
  issuer: string | null;
}

/** 与 radar_core._norm_contract 一致：去空白，0x 开头的 EVM 地址统一小写。 */
export function normalizeContract(contract: string | null | undefined): string {
  const c = (contract ?? "").trim();
  return c.startsWith("0x") || c.startsWith("0X") ? c.toLowerCase() : c;
}

/** 解析 asset_key：'crypto:<chain>:<contract>'、'ca:<chain>:<contract>'、'xstocks:AAPLx'、'sym:REZ'。合约里可能含 ':'。 */
export function parseAssetKey(key: string | null | undefined): AssetKeyInfo {
  const k = (key ?? "").trim();
  const empty: AssetKeyInfo = { type: "other", chain: null, contract: null, symbol: null, issuer: null };
  if (!k) return empty;
  const i = k.indexOf(":");
  if (i < 0) return { ...empty, symbol: k };
  const prefix = k.slice(0, i).toLowerCase();
  const rest = k.slice(i + 1);
  if (prefix === "crypto" || prefix === "ca") {
    const j = rest.indexOf(":");
    if (j <= 0 || j === rest.length - 1) return empty;
    return {
      type: prefix,
      chain: rest.slice(0, j).trim().toLowerCase(),
      contract: normalizeContract(rest.slice(j + 1)),
      symbol: null,
      issuer: null,
    };
  }
  if (prefix === "sym") return { ...empty, type: "symbol", symbol: rest || null };
  return { ...empty, type: "issuer", issuer: prefix, symbol: rest || null };
}

/**
 * 韩国交易所“유의 종목”（警示 / 投资注意）不是可达性变化：交易所适配器把市场保持 LIVE，另记一条
 * asset_key = 'warning:<SYM>' 的标记公告（action SUSPEND = 指定，RESUME = 解除），标记行状态恒为 NONE。
 * UI 不能把它显示成“暂停”。
 */
export const WARNING_ASSET_PREFIX = "warning:";

export function isWarningMarker(assetKey: string | null | undefined): boolean {
  return (assetKey ?? "").toLowerCase().startsWith(WARNING_ASSET_PREFIX);
}

/** 标记公告的 action → 文案（SUSPEND = 列入警示，RESUME = 解除警示）。 */
export function warningLabel(action: string | null | undefined): string {
  return (action ?? "").toUpperCase() === "RESUME" ? "解除警示（유의 종목）" : "列入警示（유의 종목）";
}

/** Access Radar 链名 → 市场链 key（sol / eth / bsc / base / robinhood），没有 GMGN 行情的链返回 null。 */
export function accessChainToMarket(chain: string | null | undefined): string | null {
  if (!chain) return null;
  const c = chain.trim().toLowerCase();
  if (ACCESS_CHAIN_TO_MARKET[c]) return ACCESS_CHAIN_TO_MARKET[c];
  return MARKET_TO_ACCESS_CHAINS[c] ? c : null;
}

/** 市场链 key（或 Access 链名）→ Access Radar 里可能出现的链名列表（规范名在前）。 */
export function marketChainToAccess(chain: string | null | undefined): string[] {
  if (!chain) return [];
  const c = chain.trim().toLowerCase();
  const market = MARKET_TO_ACCESS_CHAINS[c] ? c : ACCESS_CHAIN_TO_MARKET[c];
  if (!market) return [c];
  const names = MARKET_TO_ACCESS_CHAINS[market] ?? [];
  return names.length ? names : [c];
}

// ----------------------------------------------------------------------------- 身份解析状态
export interface ResolutionInput {
  /** access_state.asset_id（只在 ref CONFIRMED 时由后端写入）。 */
  assetId: number | null;
  /** source_asset_ref.resolution_status。 */
  refStatus: string | null;
  refSource?: string | null;
  suggestedAssetId?: number | null;
}

export interface ResolutionDisplay {
  status: ResolutionStatus;
  label: string;
  tone: Tone;
  hint: string;
}

const RESOLUTION_SOURCE_LABEL: Record<string, string> = {
  contract: "合约地址精确匹配",
  symbol: "代号在资产库中唯一",
  symbol_alpha_live: "代号重名，取 Binance Alpha 在线的那个",
  manual: "人工确认",
};

export function resolutionDisplay(r: ResolutionInput): ResolutionDisplay {
  const how = r.refSource ? RESOLUTION_SOURCE_LABEL[r.refSource] ?? r.refSource : "";
  if (r.assetId != null || r.refStatus === "CONFIRMED") {
    return { status: "CONFIRMED", label: "已确认", tone: "up", hint: how ? `身份已确认：${how}` : "身份已确认" };
  }
  if (r.refStatus === "SUGGESTED") {
    return {
      status: "SUGGESTED",
      label: "待确认",
      tone: "warn",
      hint: how ? `建议匹配（${how}），未人工确认` : "建议匹配，未确认",
    };
  }
  return { status: "UNRESOLVED", label: "未解析", tone: "muted", hint: "只有平台代号，尚未对应到具体合约" };
}

// ----------------------------------------------------------------------------- 置信度（只展示后端值）
export const CONFIDENCE_HIGH = 0.9;
export const CONFIDENCE_MEDIUM = 0.6;

export interface ConfidenceDisplay {
  value: number | null;
  pct: string;
  level: "high" | "medium" | "low" | "none";
  label: string;
  tone: Tone;
  sources: number;
  text: string;
  provisional: boolean;
}

/**
 * confidence = 1 − Π(1 − w_g)、independent_source_count 由 radar_core._recompute_confidence 写库，这里原样展示。
 * 档位：≥0.9 高（单个官方结构化来源 0.95 即达到），≥0.6 中（单个官方公告 0.85 / 第三方 0.60），其余低。
 */
export function confidenceDisplay(
  confidence: number | null | undefined,
  independentSourceCount: number | null | undefined,
  provisional = false,
): ConfidenceDisplay {
  const n = Math.max(0, Math.floor(Number(independentSourceCount ?? 0)) || 0);
  if (confidence == null || !Number.isFinite(confidence)) {
    return { value: null, pct: "—", level: "none", label: "—", tone: "muted", sources: n, text: "—", provisional };
  }
  const v = Math.min(1, Math.max(0, confidence));
  const level = v >= CONFIDENCE_HIGH ? "high" : v >= CONFIDENCE_MEDIUM ? "medium" : "low";
  const label = level === "high" ? "高" : level === "medium" ? "中" : "低";
  const tone: Tone = provisional ? "warn" : level === "high" ? "up" : level === "medium" ? "warn" : "down";
  const pct = `${Math.round(v * 100)}%`;
  return {
    value: v,
    pct,
    level,
    label,
    tone,
    sources: n,
    text: `${pct} · ${n} 个独立来源${provisional ? " · 待确认" : ""}`,
    provisional,
  };
}

// ----------------------------------------------------------------------------- 来源证据（链接观测）
export interface RawObservationRow {
  event_id: number;
  role: string;
  obs_id: number;
  source_id: string;
  obs_kind: string;
  action: string | null;
  origin_group: string | null;
  observed_at: number | null;
  announced_at: number | null;
  source_event_id: string | null;
  source_name: string | null;
  tier: string | null;
  raw_json: string | null;
  /** source_observation.url（公告详情页）；老库无此列时为 null/缺省。 */
  url?: string | null;
}

export interface EvidenceSource {
  sourceId: string;
  name: string;
  tier: string | null;
  tierLabel: string;
  group: string;
  roles: string[];
  urls: string[];
  firstObservedAt: number | null;
}

const URL_KEYS = ["url", "link", "href", "notice_url", "noticeUrl", "source_url", "sourceUrl", "article_url", "permalink"];

/**
 * 从原始 JSON 里挑出 http(s) 链接（只看顶层与一层嵌套的常见键）。后端没有专门的 URL 列，
 * 这是唯一能拿到“来源链接”的地方；没有就不显示，不拼接猜测的地址。
 */
export function extractUrls(rawJson: string | null | undefined, max = 3): string[] {
  if (!rawJson || rawJson.length > 200_000) return [];
  let v: unknown;
  try {
    v = JSON.parse(rawJson);
  } catch {
    return [];
  }
  const out: string[] = [];
  const push = (x: unknown) => {
    if (typeof x !== "string") return;
    const s = x.trim();
    if (!/^https?:\/\/[^\s]+$/i.test(s) || out.includes(s)) return;
    out.push(s);
  };
  const scan = (o: unknown, depth: number) => {
    if (!o || typeof o !== "object" || out.length >= max) return;
    if (Array.isArray(o)) {
      if (depth < 1) for (const x of o.slice(0, 5)) scan(x, depth + 1);
      return;
    }
    const rec = o as Record<string, unknown>;
    for (const k of URL_KEYS) push(rec[k]);
    if (depth < 1) for (const k of Object.keys(rec)) if (rec[k] && typeof rec[k] === "object") scan(rec[k], depth + 1);
  };
  scan(v, 0);
  return out.slice(0, max);
}

/** 按来源汇总链接观测；RETRACT 角色单独保留角色但不影响后端置信度（后端已排除）。 */
export function summarizeEvidence(rows: RawObservationRow[]): EvidenceSource[] {
  const by = new Map<string, EvidenceSource>();
  for (const r of rows) {
    let e = by.get(r.source_id);
    if (!e) {
      e = {
        sourceId: r.source_id,
        name: r.source_name || r.source_id,
        tier: r.tier,
        tierLabel: tierLabel(r.tier),
        group: r.origin_group || r.source_id,
        roles: [],
        urls: [],
        firstObservedAt: r.observed_at,
      };
      by.set(r.source_id, e);
    }
    if (r.role && !e.roles.includes(r.role)) e.roles.push(r.role);
    // 优先用 source_observation.url；为空（快照 / 老库）才从原始 JSON 里找链接
    const urls = r.url && /^https?:\/\//i.test(r.url) ? [r.url] : extractUrls(r.raw_json);
    for (const u of urls) if (!e.urls.includes(u) && e.urls.length < 3) e.urls.push(u);
    if (r.observed_at != null && (e.firstObservedAt == null || r.observed_at < e.firstObservedAt)) {
      e.firstObservedAt = r.observed_at;
    }
  }
  return [...by.values()].sort(
    (a, b) =>
      (TIER_RANK[b.tier as SourceTier] ?? 0) - (TIER_RANK[a.tier as SourceTier] ?? 0) ||
      (a.firstObservedAt ?? 0) - (b.firstObservedAt ?? 0),
  );
}

// ----------------------------------------------------------------------------- feed 事件
/** access-server 的 feed 查询返回的一行（snake_case = 列名）。 */
export interface RawEventRow {
  event_id: number;
  access_id: number;
  asset_key: string;
  platform_id: string;
  access_kind: string;
  quote: string;
  family: string;
  from_status: string;
  to_status: string;
  event_type: string;
  fiat_tier: string | null;
  anchor_at: number;
  announced_at: number | null;
  source_detected_at: number | null;
  observed_at: number;
  effective_at: number | null;
  live_observed_at: number | null;
  poll_prev_at: number | null;
  confidence: number;
  independent_source_count: number;
  provisional: number;
  retracted: number;
  first_source_id: string;
  updated_at: number;
  // access_state
  network: string | null;
  country: string | null;
  fiat: string | null;
  payment_method: string | null;
  current_status: string | null;
  pending_removal_at: number | null;
  // asset（已确认）
  asset_id: number | null;
  g_asset_key: string | null;
  asset_symbol: string | null;
  asset_name: string | null;
  asset_type: string | null;
  // source_asset_ref
  platform_symbol: string | null;
  resolution_status: string | null;
  resolution_source: string | null;
  suggested_asset_id: number | null;
  suggested_asset_key: string | null;
  suggested_symbol: string | null;
  // platform / first source
  platform_name: string | null;
  platform_type: string | null;
  first_source_name: string | null;
  first_source_tier: string | null;
  /** access_event.group_key（不透明字符串，不拆分）；老库无此列时缺省 → 'ev:<event_id>'。 */
  group_key?: string | null;
  /** v_recent_feed.url：事件的代表链接（公告优先）；老库缺省。 */
  url?: string | null;
}

export interface Deployment {
  chain: string;
  contract: string;
}

export interface MarketLink {
  /** 市场链 key（sol / eth / bsc / base / robinhood）。 */
  chain: string;
  address: string;
  symbol: string | null;
  name: string | null;
  price: number | null;
  marketCap: number | null;
  liquidity: number | null;
  volume24h: number | null;
  holders: number | null;
  /** unix 秒（GMGN 库口径）。 */
  observedAt: number | null;
  /** 数据来自哪张表：token_daily_snapshot（优先）/ token_snapshot / token_registry / tokens。 */
  table: string;
  /** token_daily_snapshot.source（token_info / trending ...），其余表为 null。 */
  source: string | null;
}

export interface AccessEvent {
  id: number;
  accessId: number;
  eventType: string;
  family: string;
  accessKind: string;
  desc: EventDescription;
  assetKey: string;
  globalAssetKey: string | null;
  symbol: string;
  assetName: string | null;
  assetType: string | null;
  platformId: string;
  platformName: string;
  platformType: string | null;
  quote: string;
  network: string;
  country: string;
  fiat: string;
  paymentMethod: string;
  fromStatus: string;
  toStatus: string;
  currentStatus: string | null;
  fiatTier: string | null;
  anchorAt: number;
  announcedAt: number | null;
  observedAt: number;
  effectiveAt: number | null;
  liveObservedAt: number | null;
  pollPrevAt: number | null;
  updatedAt: number;
  provisional: boolean;
  retracted: boolean;
  resolution: ResolutionDisplay;
  suggestedAssetKey: string | null;
  confidence: ConfidenceDisplay;
  firstSourceId: string;
  firstSourceName: string;
  evidence: EvidenceSource[];
  /** Access 链名（规范小写）。 */
  chains: string[];
  /** 可链接到 GMGN 的（市场链, 地址）候选，已按市场链映射。 */
  marketRefs: { chain: string; address: string }[];
  market: MarketLink | null;
  /** 展示分组键（access_event.group_key，不透明）；同一公告 + 同一资产的事件共享一个键。 */
  groupKey: string;
  /** 代表链接：v_recent_feed.url，缺省时取证据里第一条链接。 */
  url: string | null;
  /** 同组（同一 group_key，例如无交易对公告按 quote 拆出的事件，STATE_MACHINE.md §6.1）的其他事件，已折叠进本行。 */
  siblings: AccessSibling[];
}

export interface AccessSibling {
  id: number;
  accessId: number;
  eventType: string;
  label: string;
  quote: string;
  toStatus: string;
  currentStatus: string | null;
  confidencePct: string;
}

export interface ShapeContext {
  evidence?: RawObservationRow[];
  /** 已确认资产（或待确认的建议资产）的链上部署。 */
  deployments?: Deployment[];
  market?: Map<string, MarketLink>;
}

export function marketKey(chain: string, address: string): string {
  return `${chain}:${normalizeContract(address)}`;
}

function uniq<T>(arr: T[]): T[] {
  return [...new Set(arr)];
}

/** 一个事件能关联到的链：access_state.network（法币/充提/链部署）、资产部署、asset_key 里的 ca:/crypto: 链。 */
export function eventChains(network: string | null | undefined, assetKeys: (string | null | undefined)[], deployments: Deployment[]): string[] {
  const out: string[] = [];
  if (network) out.push(network.trim().toLowerCase());
  for (const k of assetKeys) {
    const info = parseAssetKey(k);
    if (info.chain) out.push(info.chain);
  }
  for (const d of deployments) out.push(d.chain.trim().toLowerCase());
  return uniq(out.filter(Boolean));
}

/** 可以拿去 GMGN 库查行情的（市场链, 合约）。只收映射得到市场链的部署。 */
export function marketRefsFor(assetKeys: (string | null | undefined)[], deployments: Deployment[]): { chain: string; address: string }[] {
  const out: { chain: string; address: string }[] = [];
  const seen = new Set<string>();
  const add = (chain: string | null, contract: string | null) => {
    const m = accessChainToMarket(chain);
    if (!m || !contract) return;
    const k = marketKey(m, contract);
    if (seen.has(k)) return;
    seen.add(k);
    out.push({ chain: m, address: normalizeContract(contract) });
  };
  for (const k of assetKeys) {
    const info = parseAssetKey(k);
    add(info.chain, info.contract);
  }
  for (const d of deployments) add(d.chain, d.contract);
  return out;
}

export function displaySymbol(row: Pick<RawEventRow, "asset_symbol" | "suggested_symbol" | "platform_symbol" | "asset_key">): string {
  if (row.asset_symbol) return row.asset_symbol;
  if (row.platform_symbol) return row.platform_symbol;
  const info = parseAssetKey(row.asset_key);
  if (info.symbol) return info.symbol;
  if (row.suggested_symbol) return row.suggested_symbol;
  return row.asset_key || "?";
}

/** 防御：后端约定警示标记不产生 access_event；万一出现，也只显示为警示，不显示为暂停 / 恢复。 */
function warningDescription(row: Pick<RawEventRow, "event_type" | "access_kind" | "family">): EventDescription {
  const base = parseEventType(row.event_type, row.access_kind);
  const label = warningLabel(row.family === "RESUME" ? "RESUME" : "SUSPEND");
  return { ...base, action: "UNKNOWN", label, kindLabel: "警示", actionLabel: label, direction: "neutral", severity: 1, tone: "warn", category: "other" };
}

/** DB 行 → UI 事件。纯函数：证据、部署、GMGN 行情由调用方查好传进来。 */
export function shapeEvent(row: RawEventRow, ctx: ShapeContext = {}): AccessEvent {
  const evidence = summarizeEvidence(ctx.evidence ?? []);
  const deployments = ctx.deployments ?? [];
  const keys = [row.asset_key, row.g_asset_key, row.suggested_asset_key];
  const chains = eventChains(row.network, keys, deployments);
  const marketRefs = marketRefsFor(keys, deployments);
  let market: MarketLink | null = null;
  for (const r of marketRefs) {
    const hit = ctx.market?.get(marketKey(r.chain, r.address));
    if (hit) {
      market = hit;
      break;
    }
  }
  const provisional = !!row.provisional;
  return {
    id: row.event_id,
    accessId: row.access_id,
    eventType: row.event_type,
    family: row.family,
    accessKind: row.access_kind,
    desc: isWarningMarker(row.asset_key) ? warningDescription(row) : describeEvent(row.event_type, row.access_kind, row.family),
    assetKey: row.asset_key,
    globalAssetKey: row.g_asset_key,
    symbol: displaySymbol(row),
    assetName: row.asset_name || null,
    assetType: row.asset_type,
    platformId: row.platform_id,
    platformName: row.platform_name || row.platform_id,
    platformType: row.platform_type,
    quote: row.quote ?? "",
    network: row.network ?? "",
    country: row.country ?? "",
    fiat: row.fiat ?? "",
    paymentMethod: row.payment_method ?? "",
    fromStatus: row.from_status,
    toStatus: row.to_status,
    currentStatus: row.current_status,
    fiatTier: row.fiat_tier,
    anchorAt: row.anchor_at,
    announcedAt: row.announced_at,
    observedAt: row.observed_at,
    effectiveAt: row.effective_at,
    liveObservedAt: row.live_observed_at,
    pollPrevAt: row.poll_prev_at,
    updatedAt: row.updated_at,
    provisional,
    retracted: !!row.retracted,
    resolution: resolutionDisplay({
      assetId: row.asset_id,
      refStatus: row.resolution_status,
      refSource: row.resolution_source,
      suggestedAssetId: row.suggested_asset_id,
    }),
    suggestedAssetKey: row.asset_id == null ? row.suggested_asset_key : null,
    confidence: confidenceDisplay(row.confidence, row.independent_source_count, provisional),
    firstSourceId: row.first_source_id,
    firstSourceName: row.first_source_name || row.first_source_id,
    evidence,
    chains,
    marketRefs,
    market,
    groupKey: row.group_key || `ev:${row.event_id}`,
    url: row.url || evidence.flatMap((x) => x.urls)[0] || null,
    siblings: [],
  };
}

/** 本行 + 折叠进来的兄弟事件的全部 quote（去重，'' 记为“全部市场”占位）。 */
export function eventQuotes(e: Pick<AccessEvent, "quote" | "siblings">): string[] {
  return uniq([e.quote, ...e.siblings.map((x) => x.quote)].map((q) => q || "—"));
}

/**
 * 按 access_event.group_key 折叠：同一条公告 + 同一资产产生的事件（例如无交易对的下架 / 暂停 / 恢复公告作用到该平台
 * 所有已存在的 quote，每个 quote 一条事件，STATE_MACHINE.md §6.1）共享一个 group_key，合成一行。group_key 当不透明
 * 字符串比较；老库没有该列时 shapeEvent 记为 'ev:<event_id>'，即不合并。保留最新（anchor_at DESC, event_id DESC）
 * 的一条为代表，其余进 siblings。
 */
export function collapseSiblings(events: AccessEvent[]): AccessEvent[] {
  const out: AccessEvent[] = [];
  const rep = new Map<string, AccessEvent>();
  for (const e of sortEvents(events)) {
    const key = e.groupKey || `ev:${e.id}`;
    const head = rep.get(key);
    if (!head) {
      const copy = { ...e, siblings: [...e.siblings] };
      rep.set(key, copy);
      out.push(copy);
      continue;
    }
    head.siblings.push(
      {
        id: e.id,
        accessId: e.accessId,
        eventType: e.eventType,
        label: e.desc.label,
        quote: e.quote,
        toStatus: e.toStatus,
        currentStatus: e.currentStatus,
        confidencePct: e.confidence.pct,
      },
      ...e.siblings,
    );
    if (!head.market && e.market) head.market = e.market;
    if (!head.url && e.url) head.url = e.url;
  }
  return out;
}

/** feed 排序：与 radar_core.recent_events 相同（anchor_at DESC, event_id DESC）。 */
export function sortEvents<T extends { anchorAt: number; id: number }>(events: T[]): T[] {
  return [...events].sort((a, b) => b.anchorAt - a.anchorAt || b.id - a.id);
}

export interface EventFilter {
  categories?: EventCategory[];
  eventTypes?: string[];
  platforms?: string[];
  /** 市场链 key 或 Access 链名。 */
  chain?: string | null;
  since?: number | null;
  includeRetracted?: boolean;
}

export function filterEvents(events: AccessEvent[], f: EventFilter): AccessEvent[] {
  const chainNames = f.chain && f.chain !== "all" ? new Set(marketChainToAccess(f.chain)) : null;
  const types = f.eventTypes?.length ? new Set(f.eventTypes.map((t) => t.toUpperCase())) : null;
  const cats = f.categories?.length ? new Set(f.categories) : null;
  const plats = f.platforms?.length ? new Set(f.platforms) : null;
  return events.filter((e) => {
    if (!f.includeRetracted && e.retracted) return false;
    if (types && !types.has(e.eventType.toUpperCase())) return false;
    if (cats && !cats.has(e.desc.category)) return false;
    if (plats && !plats.has(e.platformId)) return false;
    if (f.since != null && Math.max(e.anchorAt, e.updatedAt) < f.since) return false;
    if (chainNames && !e.chains.some((c) => chainNames.has(c))) return false;
    return true;
  });
}

export interface AssetGroup {
  key: string;
  symbol: string;
  resolution: ResolutionDisplay;
  latestAt: number;
  maxSeverity: EventSeverity;
  platforms: string[];
  events: AccessEvent[];
  market: MarketLink | null;
}

/**
 * 按资产分组：已确认的用全局 asset_key；未确认的用平台内 asset_key（sym:REZ 在不同平台是同一组，
 * 与后端“平台内身份”一致，但不跨 sym/ca 合并，避免把同名不同币并到一起）。
 */
export function groupEventsByAsset(events: AccessEvent[]): AssetGroup[] {
  const by = new Map<string, AssetGroup>();
  for (const e of sortEvents(events)) {
    const key = e.globalAssetKey ?? e.assetKey;
    let g = by.get(key);
    if (!g) {
      g = {
        key,
        symbol: e.symbol,
        resolution: e.resolution,
        latestAt: e.anchorAt,
        maxSeverity: e.desc.severity,
        platforms: [],
        events: [],
        market: e.market,
      };
      by.set(key, g);
    }
    g.events.push(e);
    if (!g.platforms.includes(e.platformId)) g.platforms.push(e.platformId);
    if (e.desc.severity > g.maxSeverity) g.maxSeverity = e.desc.severity;
    if (!g.market && e.market) g.market = e.market;
    if (e.resolution.status === "CONFIRMED") g.resolution = e.resolution;
  }
  return [...by.values()].sort((a, b) => b.latestAt - a.latestAt || b.maxSeverity - a.maxSeverity);
}

// ----------------------------------------------------------------------------- 当前可达状态 / 买入入口
export interface RawAccessStateRow {
  access_id: number;
  asset_key: string;
  asset_id: number | null;
  platform_id: string;
  access_kind: string;
  quote: string;
  country: string;
  fiat: string;
  payment_method: string;
  network: string;
  status: string;
  fiat_tier: string | null;
  provisional: number;
  pending_removal_at: number | null;
  first_seen_at: number;
  last_seen_at: number;
  status_since: number;
  created_via_baseline: number;
  g_asset_key: string | null;
  asset_symbol: string | null;
  asset_name: string | null;
  asset_type: string | null;
  platform_symbol: string | null;
  resolution_status: string | null;
  resolution_source: string | null;
  suggested_asset_id: number | null;
  platform_name: string | null;
  platform_type: string | null;
  /** buy-entry 查询：这一行是怎么匹配到代币的（asset / suggested / key）。 */
  match?: string | null;
}

export interface BuyEntry {
  accessId: number;
  platformId: string;
  platformName: string;
  platformType: string | null;
  platformTypeLabel: string;
  accessKind: string;
  kindLabel: string;
  /** "现货 · KRW" / "法币通道 · EUR · 可报价" / "链部署 · base"。 */
  entryLabel: string;
  quote: string;
  fiat: string;
  country: string;
  network: string;
  paymentMethod: string;
  status: string;
  statusLabel: string;
  statusTone: Tone;
  statusSince: number;
  firstSeenAt: number;
  lastSeenAt: number;
  fiatTier: string | null;
  provisional: boolean;
  pendingRemovalAt: number | null;
  /** 1 = 首次被看到时就已存在（基线），不知道真正上线时间；status_since 是我们开始观测的时间。 */
  sinceIsBaseline: boolean;
  assetKey: string;
  symbol: string;
  resolution: ResolutionDisplay;
  /** 该平台最近一条警示标记公告是“列入”（유의 종목）。市场仍可交易，只是提示。 */
  warning: boolean;
}

export function entryLabel(kind: string, quote: string, network: string, fiatTier: string | null, country = ""): string {
  const parts = [kindLabel(kind)];
  if (kind === "CHAIN_DEPLOYMENT" || kind === "DEPOSIT_NETWORK" || kind === "WITHDRAW_NETWORK") {
    if (network) parts.push(network);
  } else if (quote) parts.push(quote);
  if (kind === "FIAT_ROUTE") {
    if (network) parts.push(network);
    if (fiatTier) parts.push(FIAT_TIER_LABEL[fiatTier as FiatTier] ?? fiatTier);
  }
  if (country) parts.push(country);
  return parts.join(" · ");
}

export function shapeBuyEntry(row: RawAccessStateRow): BuyEntry {
  const suggested = row.match === "suggested";
  return {
    accessId: row.access_id,
    platformId: row.platform_id,
    platformName: row.platform_name || row.platform_id,
    platformType: row.platform_type,
    platformTypeLabel: platformTypeLabel(row.platform_type),
    accessKind: row.access_kind,
    kindLabel: kindLabel(row.access_kind),
    entryLabel: entryLabel(row.access_kind, row.quote, row.network, row.fiat_tier, row.country),
    quote: row.quote ?? "",
    fiat: row.fiat ?? "",
    country: row.country ?? "",
    network: row.network ?? "",
    paymentMethod: row.payment_method ?? "",
    status: row.status,
    statusLabel: statusLabel(row.status),
    statusTone: statusTone(row.status),
    statusSince: row.status_since,
    firstSeenAt: row.first_seen_at,
    lastSeenAt: row.last_seen_at,
    fiatTier: row.fiat_tier,
    provisional: !!row.provisional,
    pendingRemovalAt: row.pending_removal_at,
    sinceIsBaseline: !!row.created_via_baseline && row.status_since === row.first_seen_at,
    assetKey: row.asset_key,
    symbol: displaySymbol({
      asset_symbol: row.asset_symbol,
      suggested_symbol: null,
      platform_symbol: row.platform_symbol,
      asset_key: row.asset_key,
    }),
    resolution: suggested
      ? resolutionDisplay({ assetId: null, refStatus: "SUGGESTED", refSource: row.resolution_source })
      : resolutionDisplay({
          assetId: row.asset_id,
          // 平台内身份就是 ca:/crypto: 合约键时，身份由合约直接给出
          refStatus: row.match === "key" ? "CONFIRMED" : row.resolution_status,
          refSource: row.match === "key" ? "contract" : row.resolution_source,
        }),
    warning: false,
  };
}

const STATUS_ORDER: Record<string, number> = { LIVE: 0, ANNOUNCED: 1, SUSPENDED: 2, REMOVED: 3, NONE: 4 };
const KIND_ORDER: Record<string, number> = Object.fromEntries(
  ["SPOT", "PERP", "ALPHA", "FIAT_ROUTE", "DEPOSIT_NETWORK", "WITHDRAW_NETWORK", "LENDING", "COLLATERAL", "CATALOG", "CHAIN_DEPLOYMENT", "ROADMAP"].map(
    (k, i) => [k, i],
  ),
);

/** 可用的在前（LIVE → 已公告 → 暂停 → 已下架），同状态按入口重要性（现货 / 永续 / Alpha / 法币 ...），再按平台。 */
export function sortBuyEntries(entries: BuyEntry[]): BuyEntry[] {
  return [...entries].sort(
    (a, b) =>
      (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9) ||
      (KIND_ORDER[a.accessKind] ?? 99) - (KIND_ORDER[b.accessKind] ?? 99) ||
      a.platformName.localeCompare(b.platformName) ||
      a.entryLabel.localeCompare(b.entryLabel),
  );
}

/** 同一 access_id 可能同时被 asset / suggested / key 匹配到：保留证据最强的那条（asset > key > suggested）。 */
export function dedupeStateRows(rows: RawAccessStateRow[]): RawAccessStateRow[] {
  const rank = (m: string | null | undefined) => (m === "asset" ? 0 : m === "key" ? 1 : 2);
  const by = new Map<number, RawAccessStateRow>();
  for (const r of rows) {
    const prev = by.get(r.access_id);
    if (!prev || rank(r.match) < rank(prev.match)) by.set(r.access_id, r);
  }
  return [...by.values()];
}

export interface AccessStateGroup {
  key: string;
  symbol: string;
  assetType: string | null;
  resolution: ResolutionDisplay;
  live: number;
  entries: BuyEntry[];
}

/** 当前状态按资产 / 平台分组（全局资产优先，否则平台内身份）。 */
export function groupStates(rows: RawAccessStateRow[]): AccessStateGroup[] {
  const by = new Map<string, AccessStateGroup>();
  for (const r of rows) {
    if (isWarningMarker(r.asset_key)) continue;
    const key = r.g_asset_key ?? r.asset_key;
    const entry = shapeBuyEntry(r);
    let g = by.get(key);
    if (!g) {
      g = { key, symbol: entry.symbol, assetType: r.asset_type, resolution: entry.resolution, live: 0, entries: [] };
      by.set(key, g);
    }
    g.entries.push(entry);
    if (entry.status === "LIVE") g.live += 1;
  }
  for (const g of by.values()) g.entries = sortBuyEntries(g.entries);
  return [...by.values()].sort((a, b) => b.live - a.live || a.symbol.localeCompare(b.symbol));
}

// ----------------------------------------------------------------------------- 来源健康
/** access_db.FAIL_THRESHOLD */
export const FAIL_THRESHOLD = 3;
/** 采集进程心跳（runner_meta.collector_heartbeat，loop 模式每 5s 写一次）超过这个时长视为进程没在跑。 */
export const COLLECTOR_STALE_MS = 60_000;

export type ClockStatus =
  | "LIVE"
  | "DELAYED"
  | "STALE"
  | "FAILED"
  | "DOWN"
  | "MISSING"
  | "ERROR"
  | "NO_SOURCE"
  | "DISABLED"
  | "NOT_STARTED"
  | "UNKNOWN";

export type HealthLevel = "healthy" | "degraded" | "stale" | "down" | "off";

export const HEALTH_LABEL: Record<HealthLevel, string> = {
  healthy: "正常",
  degraded: "降级",
  stale: "过期",
  down: "故障",
  off: "未接入",
};

export const HEALTH_TONE: Record<HealthLevel, Tone> = {
  healthy: "up",
  degraded: "warn",
  stale: "warn",
  down: "down",
  off: "muted",
};

export interface SourceRunRow {
  source_id: string;
  kind: string;
  module: string;
  period_sec: number;
  adapter_state: string;
  adapter_note: string;
  collector_heartbeat: number | null;
  last_attempt: number | null;
  last_success: number | null;
  round_ok: number;
  latency_ms: number | null;
  consecutive_errors: number;
  last_error: string;
  attempts: number;
  successes: number;
  rows_received: number;
  events_written: number;
  last_event_at: number | null;
  connected: number;
  last_heartbeat: number | null;
  heartbeat_sec: number;
  updated_at: number | null;
}

export interface SourceHealthRow {
  source_id: string;
  scope: string;
  status: string;
  schema_ok: number;
  last_snapshot_size: number | null;
  baseline_done: number;
  last_fetch_at: number | null;
  last_ok_at: number | null;
  last_error: string;
}

export interface DisconnectRow {
  source_id: string;
  scope: string;
  started_at: number;
  ended_at: number | null;
  reason: string;
  backfilled: number;
}

/** access_db.classify_status 的逐行移植（时间单位 ms）。 */
export function classifyRunStatus(now: number, row: SourceRunRow): ClockStatus {
  const state = (row.adapter_state || "unknown").toLowerCase();
  if (state !== "ok") return state.toUpperCase() as ClockStatus;
  const errors = Number(row.consecutive_errors || 0);
  if (row.kind === "stream") {
    if (!row.connected) return errors >= FAIL_THRESHOLD && !row.successes ? "FAILED" : "DOWN";
    const hb = row.last_heartbeat || row.last_success;
    const limit = (row.heartbeat_sec || 60) * 1000;
    if (hb && now - hb > limit) return "DELAYED";
    return "LIVE";
  }
  const period = (row.period_sec || 60) * 1000;
  if (errors >= FAIL_THRESHOLD && !row.successes) return "FAILED";
  if (!row.last_success || !row.round_ok) return "STALE";
  const age = now - row.last_success;
  if (age > 2 * period + 2000) return "STALE";
  if (age > period + 2000) return "DELAYED";
  return "LIVE";
}

export interface CollectorState {
  heartbeatAt: number | null;
  ageMs: number | null;
  alive: boolean;
}

export function collectorState(now: number, heartbeat: number | string | null | undefined): CollectorState {
  const hb = heartbeat == null || heartbeat === "" ? null : Number(heartbeat);
  if (hb == null || !Number.isFinite(hb) || hb <= 0) return { heartbeatAt: null, ageMs: null, alive: false };
  const ageMs = Math.max(0, now - hb);
  return { heartbeatAt: hb, ageMs, alive: ageMs <= COLLECTOR_STALE_MS };
}

export interface SourceSummary {
  sourceId: string;
  kind: string;
  periodSec: number;
  clock: ClockStatus;
  level: HealthLevel;
  label: string;
  tone: Tone;
  reasons: string[];
  lastSuccess: number | null;
  lastAttempt: number | null;
  ageMs: number | null;
  consecutiveErrors: number;
  lastError: string;
  eventsWritten: number;
  scopes: { scope: string; status: string; baselineDone: boolean; size: number | null; lastError: string }[];
  openGaps: number;
}

const OFF_STATES = new Set<ClockStatus>(["MISSING", "NO_SOURCE", "DISABLED", "NOT_STARTED", "UNKNOWN"]);
const LEVEL_ORDER: Record<HealthLevel, number> = { off: 0, healthy: 1, degraded: 2, stale: 3, down: 4 };

/**
 * 单个来源的四档健康（再加“未接入”）：
 * - off：适配器不可运行（MISSING / NO_SOURCE / DISABLED / NOT_STARTED / UNKNOWN），不参与汇总；
 * - down：时钟 FAILED / DOWN / ERROR，或任一 scope 的 source_health = DOWN，或有未结束的断线区间；
 * - stale：时钟 STALE（> 2×周期+2s 无成功、本轮失败、从未成功），或流来源在采集进程心跳超过 60s 时（connected 列冻结）；
 * - degraded：时钟 DELAYED（> 周期+2s），或任一 scope DEGRADED / schema 校验失败；
 * - healthy：时钟 LIVE 且所有 scope HEALTHY。
 * run 为空（没有 source_run 表）时只按 source_health 判断。
 */
export function summarizeSource(
  now: number,
  sourceId: string,
  run: SourceRunRow | null,
  scopes: SourceHealthRow[],
  gaps: DisconnectRow[],
  collector: CollectorState,
): SourceSummary {
  const clock: ClockStatus = run ? classifyRunStatus(now, run) : "UNKNOWN";
  const reasons: string[] = [];
  let level: HealthLevel = "healthy";
  const bump = (l: HealthLevel, why: string) => {
    if (LEVEL_ORDER[l] > LEVEL_ORDER[level]) level = l;
    if (why && !reasons.includes(why)) reasons.push(why);
  };
  const openGaps = gaps.filter((g) => g.ended_at == null);

  if (run && OFF_STATES.has(clock)) {
    level = "off";
    reasons.push(run.adapter_note || `适配器 ${clock}`);
  } else {
    if (run) {
      if (clock === "FAILED") bump("down", `连续失败 ${run.consecutive_errors} 次且从未成功`);
      else if (clock === "DOWN") bump("down", "流连接断开");
      else if (clock === "ERROR") bump("down", run.adapter_note || "适配器导入失败");
      else if (clock === "STALE") bump("stale", run.round_ok ? "超过 2 个周期没有成功" : run.last_success ? "最近一轮失败" : "从未成功");
      else if (clock === "DELAYED") bump("degraded", run.kind === "stream" ? "心跳超时" : "超过 1 个周期没有成功");
    }
    for (const s of scopes) {
      const tag = s.scope ? `${s.scope}：` : "";
      if (s.status === "DOWN") bump("down", `${tag}抓取失败${s.last_error ? `（${s.last_error.slice(0, 80)}）` : ""}`);
      else if (s.status === "DEGRADED" || !s.schema_ok) bump("degraded", `${tag}${s.last_error ? s.last_error.slice(0, 80) : "快照异常，暂停 diff"}`);
    }
    if (openGaps.length) bump("down", `断线中（自 ${fmtTs8(openGaps[0].started_at)} ${TZ_LABEL}）`);
    if (run && !collector.alive) {
      const why = collector.heartbeatAt ? `采集进程心跳已 ${fmtAgeMs(collector.ageMs)}` : "采集进程没有心跳";
      // 流来源的 connected / 心跳列在进程退出后会冻结成“在线”，只能靠进程心跳识别；
      // 轮询来源的时钟本身按 last_success 年龄判断，进程停了自然会走到 STALE，这里只记原因。
      if (run.kind === "stream" && LEVEL_ORDER[level] < LEVEL_ORDER.stale) bump("stale", why);
      else if (!reasons.includes(why)) reasons.push(why);
    }
    if (!run && !scopes.length) {
      level = "off";
      reasons.push("没有运行记录");
    }
  }
  const lastSuccess = run?.kind === "stream" ? run.last_heartbeat || run.last_success : run?.last_success ?? null;
  const fallbackOk = scopes.reduce<number | null>((m, s) => (s.last_ok_at != null && (m == null || s.last_ok_at > m) ? s.last_ok_at : m), null);
  const ok = lastSuccess ?? fallbackOk;
  return {
    sourceId,
    kind: run?.kind ?? "",
    periodSec: Number(run?.period_sec ?? 0),
    clock,
    level,
    label: HEALTH_LABEL[level],
    tone: HEALTH_TONE[level],
    reasons,
    lastSuccess: ok ?? null,
    lastAttempt: run?.last_attempt ?? null,
    ageMs: ok == null ? null : Math.max(0, now - ok),
    consecutiveErrors: Number(run?.consecutive_errors ?? 0),
    lastError: run?.last_error || scopes.find((s) => s.last_error)?.last_error || "",
    eventsWritten: Number(run?.events_written ?? 0),
    scopes: scopes.map((s) => ({
      scope: s.scope,
      status: s.status,
      baselineDone: !!s.baseline_done,
      size: s.last_snapshot_size,
      lastError: s.last_error,
    })),
    openGaps: openGaps.length,
  };
}

export interface HealthSummary {
  level: HealthLevel;
  label: string;
  tone: Tone;
  counts: Record<HealthLevel, number>;
  active: number;
  collector: CollectorState;
}

/** 总状态 = 已接入来源中最差的一档；没有已接入来源时为 off。 */
export function summarizeHealth(sources: SourceSummary[], collector: CollectorState): HealthSummary {
  const counts: Record<HealthLevel, number> = { healthy: 0, degraded: 0, stale: 0, down: 0, off: 0 };
  let level: HealthLevel = "off";
  for (const s of sources) {
    counts[s.level] += 1;
    if (LEVEL_ORDER[s.level] > LEVEL_ORDER[level]) level = s.level;
  }
  const active = sources.length - counts.off;
  return { level, label: HEALTH_LABEL[level], tone: HEALTH_TONE[level], counts, active, collector };
}

/** 把 source_run / source_health / source_disconnect 三张表的行合成每个来源的汇总，按严重度排序。 */
export function buildSourceSummaries(
  now: number,
  runs: SourceRunRow[],
  scopes: SourceHealthRow[],
  gaps: DisconnectRow[],
  collector: CollectorState,
): SourceSummary[] {
  const ids = uniq([...runs.map((r) => r.source_id), ...scopes.map((s) => s.source_id)]);
  const runBy = new Map(runs.map((r) => [r.source_id, r]));
  const out = ids.map((id) =>
    summarizeSource(
      now,
      id,
      runBy.get(id) ?? null,
      scopes.filter((s) => s.source_id === id),
      gaps.filter((g) => g.source_id === id),
      collector,
    ),
  );
  return out.sort((a, b) => LEVEL_ORDER[b.level] - LEVEL_ORDER[a.level] || a.sourceId.localeCompare(b.sourceId));
}

// ----------------------------------------------------------------------------- 维护任务（maintenance_run）
/** access_db.py maintenance_run 一行。维护任务（如每小时的身份解析 resolve）不是数据来源，单独展示、不进来源汇总。 */
export interface MaintenanceRunRow {
  job_id: string;
  module: string;
  period_sec: number;
  job_state: string;
  job_note: string;
  last_attempt: number | null;
  last_success: number | null;
  round_ok: number;
  latency_ms: number | null;
  consecutive_errors: number;
  last_error: string;
  attempts: number;
  successes: number;
  last_result: string;
  updated_at: number | null;
}

export interface MaintenanceSummary {
  jobId: string;
  label: string;
  periodSec: number;
  clock: ClockStatus;
  level: HealthLevel;
  levelLabel: string;
  tone: Tone;
  reasons: string[];
  lastSuccess: number | null;
  lastAttempt: number | null;
  ageMs: number | null;
  consecutiveErrors: number;
  lastError: string;
  /** last_result JSON 里的标量字段（如 resolve 的 suggested / confirmed_contract 计数），用于提示。 */
  lastResult: Record<string, string | number | boolean | null>;
}

const MAINTENANCE_LABEL: Record<string, string> = { resolve: "身份解析" };

function scalarFields(json: string | null | undefined): Record<string, string | number | boolean | null> {
  if (!json) return {};
  try {
    const v = JSON.parse(json) as unknown;
    if (!v || typeof v !== "object" || Array.isArray(v)) return {};
    const out: Record<string, string | number | boolean | null> = {};
    for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
      if (x === null || typeof x === "string" || typeof x === "number" || typeof x === "boolean") out[k] = x;
    }
    return out;
  } catch {
    return {};
  }
}

/** 时钟规则同 access_db.classify_maintenance（= 轮询来源规则，以 job_state 作适配器状态）；分档同 summarizeSource。 */
export function summarizeMaintenance(now: number, row: MaintenanceRunRow): MaintenanceSummary {
  const clock = classifyRunStatus(now, {
    source_id: row.job_id,
    kind: "maintenance",
    module: row.module,
    period_sec: row.period_sec,
    adapter_state: row.job_state,
    adapter_note: row.job_note,
    collector_heartbeat: null,
    last_attempt: row.last_attempt,
    last_success: row.last_success,
    round_ok: row.round_ok,
    latency_ms: row.latency_ms,
    consecutive_errors: row.consecutive_errors,
    last_error: row.last_error,
    attempts: row.attempts,
    successes: row.successes,
    rows_received: 0,
    events_written: 0,
    last_event_at: null,
    connected: 0,
    last_heartbeat: null,
    heartbeat_sec: 0,
    updated_at: row.updated_at,
  });
  const reasons: string[] = [];
  let level: HealthLevel;
  if (OFF_STATES.has(clock)) {
    level = "off";
    reasons.push(row.job_note || `任务 ${clock}`);
  } else if (clock === "ERROR" || clock === "FAILED") {
    level = "down";
    reasons.push(clock === "ERROR" ? row.job_note || "任务模块导入失败" : `连续失败 ${row.consecutive_errors} 次且从未成功`);
  } else if (clock === "STALE") {
    level = "stale";
    reasons.push(row.round_ok ? "超过 2 个周期没有成功" : row.last_success ? "最近一轮失败" : "从未成功");
  } else if (clock === "DELAYED") {
    level = "degraded";
    reasons.push("超过 1 个周期没有成功");
  } else {
    level = "healthy";
  }
  if (row.consecutive_errors > 0 && row.last_error) reasons.push(`连续失败 ${row.consecutive_errors} 次：${row.last_error.slice(0, 80)}`);
  return {
    jobId: row.job_id,
    label: MAINTENANCE_LABEL[row.job_id] ?? row.job_id,
    periodSec: Number(row.period_sec || 0),
    clock,
    level,
    levelLabel: HEALTH_LABEL[level],
    tone: HEALTH_TONE[level],
    reasons,
    lastSuccess: row.last_success,
    lastAttempt: row.last_attempt,
    ageMs: row.last_success ? Math.max(0, now - row.last_success) : null,
    consecutiveErrors: Number(row.consecutive_errors || 0),
    lastError: row.last_error || "",
    lastResult: scalarFields(row.last_result),
  };
}
