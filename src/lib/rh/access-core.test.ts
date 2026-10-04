import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  ACCESS_KINDS,
  COLLECTOR_STALE_MS,
  accessChainToMarket,
  buildSourceSummaries,
  classifyRunStatus,
  collapseSiblings,
  collectorState,
  confidenceDisplay,
  dedupeStateRows,
  describeEvent,
  entryLabel,
  eventQuotes,
  eventChains,
  extractUrls,
  filterEvents,
  fmtAgeMs,
  fmtAgo,
  fmtTs8,
  fmtTs8Full,
  groupEventsByAsset,
  groupStates,
  isWarningMarker,
  marketChainToAccess,
  marketRefsFor,
  normalizeContract,
  parseAssetKey,
  parseEventType,
  resolutionDisplay,
  shapeBuyEntry,
  shapeEvent,
  sortBuyEntries,
  sortEvents,
  summarizeEvidence,
  summarizeHealth,
  summarizeMaintenance,
  summarizeSource,
  warningLabel,
  windowMs,
  type MaintenanceRunRow,
  type RawAccessStateRow,
  type RawEventRow,
  type RawObservationRow,
  type SourceHealthRow,
  type SourceRunRow,
} from "./access-core.ts";

// ----------------------------------------------------------------------------- 后端 derive_event_type 的完整输出集
// 按 radar_core.derive_event_type 手工展开（kind × 迁移），用来保证每个后端类型都能解析、都有中文标签。
const ADD_LIVE: Record<string, string> = {
  SPOT: "SPOT_LISTED",
  PERP: "PERP_LISTED",
  ALPHA: "ALPHA_LISTED",
  CATALOG: "CATALOG_ADDED",
  ROADMAP: "ROADMAP_ADDED",
  CHAIN_DEPLOYMENT: "CHAIN_DEPLOYED",
  DEPOSIT_NETWORK: "DEPOSIT_ENABLED",
  WITHDRAW_NETWORK: "WITHDRAW_ENABLED",
  COLLATERAL: "COLLATERAL_ENABLED",
  LENDING: "LENDING_ENABLED",
};
const SHORT: Record<string, string> = { DEPOSIT_NETWORK: "DEPOSIT", WITHDRAW_NETWORK: "WITHDRAW" };

function backendTypes(kind: string): { type: string; action: string }[] {
  const short = SHORT[kind] ?? kind;
  const removed = ["SPOT", "PERP", "ALPHA"].includes(kind) ? `${kind}_DELISTED` : `${kind}_REMOVED`;
  const out = [
    { type: `${kind}_ANNOUNCED`, action: "ANNOUNCED" },
    { type: `${kind}_RELISTED`, action: "RELISTED" },
    { type: `${kind}_LISTED_SUSPENDED`, action: "LISTED_SUSPENDED" },
    { type: `${short}_SUSPENDED`, action: "SUSPENDED" },
    { type: `${short}_RESUMED`, action: "RESUMED" },
    { type: removed, action: removed.endsWith("DELISTED") ? "DELISTED" : "REMOVED" },
    { type: `${kind}_ANNOUNCEMENT_CANCELLED`, action: "ANNOUNCEMENT_CANCELLED" },
    { type: `${removed}_SCHEDULED`, action: removed.endsWith("DELISTED") ? "DELISTED" : "REMOVED" },
  ];
  if (kind === "FIAT_ROUTE") {
    for (const t of ["SUPPORTED", "QUOTABLE", "CONFIRMED"]) out.push({ type: `FIAT_ROUTE_${t}`, action: "FIAT_TIER" });
  } else out.push({ type: ADD_LIVE[kind], action: "LISTED" });
  return out;
}

describe("parseEventType / describeEvent", () => {
  it("parses every backend event_type, with and without access_kind", () => {
    for (const kind of ACCESS_KINDS) {
      for (const { type, action } of backendTypes(kind)) {
        for (const hint of [kind, null]) {
          const p = parseEventType(type, hint);
          assert.equal(p.kind, kind, `${type} (hint ${hint}) kind`);
          assert.equal(p.action, action, `${type} (hint ${hint}) action`);
          assert.equal(p.scheduled, type.endsWith("_SCHEDULED"));
          const d = describeEvent(type, hint);
          assert.ok(d.label && !d.label.includes("_"), `${type} label ${d.label}`);
        }
      }
    }
  });

  it("does not let a short prefix steal a full kind", () => {
    assert.equal(parseEventType("DEPOSIT_NETWORK_ANNOUNCED").kind, "DEPOSIT_NETWORK");
    assert.equal(parseEventType("DEPOSIT_SUSPENDED").kind, "DEPOSIT_NETWORK");
    assert.equal(parseEventType("CHAIN_DEPLOYMENT_REMOVED").action, "REMOVED");
    assert.equal(parseEventType("CHAIN_DEPLOYED").kind, "CHAIN_DEPLOYMENT");
    assert.equal(parseEventType("FIAT_ROUTE_RELISTED").action, "RELISTED");
  });

  it("labels in Chinese", () => {
    assert.equal(describeEvent("SPOT_LISTED", "SPOT").label, "现货上线");
    assert.equal(describeEvent("SPOT_ANNOUNCED", "SPOT").label, "现货上线公告");
    assert.equal(describeEvent("SPOT_DELISTED_SCHEDULED", "SPOT").label, "现货下架（预告）");
    assert.equal(describeEvent("FIAT_ROUTE_QUOTABLE", "FIAT_ROUTE").label, "法币通道·可报价");
    assert.equal(describeEvent("CHAIN_DEPLOYED", "CHAIN_DEPLOYMENT").label, "新链部署");
    assert.equal(describeEvent("WITHDRAW_SUSPENDED", "WITHDRAW_NETWORK").label, "提现暂停");
    assert.equal(describeEvent("CATALOG_ANNOUNCEMENT_CANCELLED").label, "目录公告取消");
  });

  it("assigns direction, severity and category", () => {
    const listed = describeEvent("SPOT_LISTED", "SPOT", "ADD");
    assert.deepEqual([listed.direction, listed.severity, listed.category, listed.tone], ["up", 3, "listing", "up"]);
    assert.equal(describeEvent("SPOT_ANNOUNCED").severity, 3);
    assert.equal(describeEvent("SPOT_ANNOUNCED").category, "announce");
    assert.equal(describeEvent("CATALOG_ADDED").severity, 2);
    const fiat = describeEvent("FIAT_ROUTE_SUPPORTED", "FIAT_ROUTE", "ADD");
    assert.deepEqual([fiat.category, fiat.severity], ["fiat", 2]);
    assert.equal(describeEvent("FIAT_ROUTE_CONFIRMED", "FIAT_ROUTE", "TIER").severity, 1);
    assert.equal(describeEvent("CHAIN_DEPLOYED").category, "chain");
    const sus = describeEvent("SPOT_SUSPENDED");
    assert.deepEqual([sus.direction, sus.category, sus.tone], ["pause", "pause", "warn"]);
    assert.deepEqual([describeEvent("SPOT_RESUMED").direction, describeEvent("SPOT_RESUMED").severity], ["up", 1]);
    const del = describeEvent("PERP_DELISTED");
    assert.deepEqual([del.direction, del.severity, del.category], ["down", 3, "remove"]);
    assert.equal(describeEvent("LENDING_REMOVED").severity, 2);
    assert.equal(describeEvent("SPOT_ANNOUNCEMENT_CANCELLED").direction, "down");
  });

  it("never guesses unknown types", () => {
    const d = describeEvent("SOMETHING_NEW");
    assert.equal(d.action, "UNKNOWN");
    assert.equal(d.label, "SOMETHING_NEW");
    assert.equal(d.severity, 1);
    assert.equal(d.category, "other");
    assert.equal(parseEventType("SPOT_WEIRD", "SPOT").kind, "SPOT");
    assert.equal(parseEventType("", null).action, "UNKNOWN");
  });
});

describe("time formatting (UTC ms -> UTC+8)", () => {
  // 2026-10-04 12:45:30 UTC = 20:45:30 UTC+8
  const T = Date.UTC(2026, 9, 4, 12, 45, 30);
  it("formats independent of runtime timezone", () => {
    assert.equal(fmtTs8(T), "10-04 20:45");
    assert.equal(fmtTs8Full(T), "2026-10-04 20:45:30 UTC+8");
    assert.equal(fmtTs8(Date.UTC(2026, 11, 31, 16, 0, 0)), "01-01 00:00"); // 跨年
    assert.equal(fmtTs8(null), "—");
    assert.equal(fmtTs8(0), "—");
    assert.equal(fmtTs8Full(undefined), "—");
  });
  it("relative ages", () => {
    assert.equal(fmtAgo(T, T - 5_000), "刚刚");
    assert.equal(fmtAgo(T, T - 5 * 60_000), "5 分钟前");
    assert.equal(fmtAgo(T, T - 3 * 3_600_000), "3 小时前");
    assert.equal(fmtAgo(T, T - 2 * 86_400_000), "2 天前");
    assert.equal(fmtAgo(T, T + 3 * 3_600_000), "3 小时后");
    assert.equal(fmtAgo(T, null), "—");
    assert.equal(fmtAgeMs(45_000), "45s");
    assert.equal(fmtAgeMs(3 * 60_000), "3m");
    assert.equal(fmtAgeMs(2 * 3_600_000 + 5 * 60_000), "2h5m");
    assert.equal(fmtAgeMs(3 * 86_400_000), "3d");
    assert.equal(fmtAgeMs(null), "—");
  });
  it("feed windows match access_run.py", () => {
    assert.equal(windowMs("1h"), 3_600_000);
    assert.equal(windowMs("7d"), 7 * 86_400_000);
    assert.equal(windowMs("bogus"), 24 * 3_600_000);
  });
});

describe("asset identity and chains", () => {
  it("parses asset keys", () => {
    assert.deepEqual(parseAssetKey("crypto:bsc:0xABCdef"), { type: "crypto", chain: "bsc", contract: "0xabcdef", symbol: null, issuer: null });
    const ca = parseAssetKey("ca:solana:Mint:With:Colons");
    assert.deepEqual([ca.type, ca.chain, ca.contract], ["ca", "solana", "Mint:With:Colons"]);
    assert.deepEqual([parseAssetKey("xstocks:AAPLx").type, parseAssetKey("xstocks:AAPLx").symbol], ["issuer", "AAPLx"]);
    assert.deepEqual([parseAssetKey("sym:REZ").type, parseAssetKey("sym:REZ").symbol], ["symbol", "REZ"]);
    assert.equal(parseAssetKey("crypto:bsc:").type, "other");
    assert.equal(parseAssetKey("").type, "other");
  });
  it("normalizes contracts like radar_core._norm_contract", () => {
    assert.equal(normalizeContract(" 0xAbC "), "0xabc");
    assert.equal(normalizeContract("So11111111111111111111111111111111111111112"), "So11111111111111111111111111111111111111112");
    assert.equal(normalizeContract(null), "");
  });
  it("maps access chains to market keys and back", () => {
    assert.equal(accessChainToMarket("solana"), "sol");
    assert.equal(accessChainToMarket("Ethereum"), "eth");
    assert.equal(accessChainToMarket("sol"), "sol");
    assert.equal(accessChainToMarket("arbitrum"), null);
    assert.equal(accessChainToMarket(null), null);
    assert.deepEqual(marketChainToAccess("sol"), ["solana", "sol"]);
    assert.deepEqual(marketChainToAccess("solana"), ["solana", "sol"]);
    assert.deepEqual(marketChainToAccess("arbitrum"), ["arbitrum"]);
    assert.deepEqual(marketChainToAccess(""), []);
  });
  it("collects event chains and GMGN refs", () => {
    const deps = [
      { chain: "solana", contract: "Mint1" },
      { chain: "arbitrum", contract: "0xAA" },
    ];
    assert.deepEqual(eventChains("Base", ["ca:bsc:0x1", "xstocks:AAPLx"], deps), ["base", "bsc", "solana", "arbitrum"]);
    assert.deepEqual(marketRefsFor(["ca:bsc:0xAB"], deps), [
      { chain: "bsc", address: "0xab" },
      { chain: "sol", address: "Mint1" },
    ]);
  });
  it("warning markers", () => {
    assert.equal(isWarningMarker("warning:REZ"), true);
    assert.equal(isWarningMarker("sym:REZ"), false);
    assert.match(warningLabel("SUSPEND"), /列入警示/);
    assert.match(warningLabel("RESUME"), /解除警示/);
  });
});

describe("resolution display", () => {
  it("CONFIRMED when asset_id is set or ref confirmed", () => {
    assert.equal(resolutionDisplay({ assetId: 3, refStatus: null }).status, "CONFIRMED");
    const r = resolutionDisplay({ assetId: null, refStatus: "CONFIRMED", refSource: "contract" });
    assert.equal(r.label, "已确认");
    assert.match(r.hint, /合约/);
  });
  it("SUGGESTED / UNRESOLVED", () => {
    const s = resolutionDisplay({ assetId: null, refStatus: "SUGGESTED", refSource: "symbol_alpha_live" });
    assert.deepEqual([s.status, s.label, s.tone], ["SUGGESTED", "待确认", "warn"]);
    assert.match(s.hint, /Alpha/);
    assert.equal(resolutionDisplay({ assetId: null, refStatus: "UNRESOLVED" }).label, "未解析");
    assert.equal(resolutionDisplay({ assetId: null, refStatus: null }).status, "UNRESOLVED");
  });
});

describe("confidence display (backend value, not recomputed)", () => {
  it("levels", () => {
    assert.deepEqual(
      [confidenceDisplay(0.95, 1).level, confidenceDisplay(0.9, 1).level, confidenceDisplay(0.85, 1).level, confidenceDisplay(0.5, 1).level],
      ["high", "high", "medium", "low"],
    );
    const c = confidenceDisplay(0.9925, 2);
    assert.equal(c.pct, "99%");
    assert.equal(c.text, "99% · 2 个独立来源");
    assert.equal(c.value, 0.9925);
  });
  it("provisional and missing values", () => {
    const p = confidenceDisplay(0.6, 1, true);
    assert.equal(p.tone, "warn");
    assert.match(p.text, /待确认/);
    assert.equal(confidenceDisplay(null, 0).pct, "—");
    assert.equal(confidenceDisplay(Number.NaN, 0).level, "none");
    assert.equal(confidenceDisplay(1.5, 3).pct, "100%");
  });
});

describe("evidence", () => {
  it("extracts http(s) URLs from raw JSON only", () => {
    assert.deepEqual(extractUrls(JSON.stringify({ url: "https://upbit.com/n/1", title: "x" })), ["https://upbit.com/n/1"]);
    assert.deepEqual(extractUrls(JSON.stringify({ raw: { link: "http://a.b/c" } })), ["http://a.b/c"]);
    assert.deepEqual(extractUrls(JSON.stringify({ url: "javascript:alert(1)" })), []);
    assert.deepEqual(extractUrls("not json"), []);
    assert.deepEqual(extractUrls(null), []);
    assert.deepEqual(extractUrls(JSON.stringify([{ url: "https://x.y" }])), ["https://x.y"]);
  });
  it("summarizes by source, strongest tier first", () => {
    const base: Omit<RawObservationRow, "obs_id" | "source_id" | "role" | "tier" | "observed_at" | "raw_json"> = {
      event_id: 1,
      obs_kind: "ANNOUNCEMENT",
      action: "LISTING",
      origin_group: "upbit_notice",
      announced_at: null,
      source_event_id: "",
      source_name: null,
    };
    const ev = summarizeEvidence([
      { ...base, obs_id: 1, source_id: "newlistings", role: "ORIGIN", tier: "THIRD_PARTY", observed_at: 10, raw_json: null },
      { ...base, obs_id: 2, source_id: "upbit_notice", role: "CORROBORATE", tier: "OFFICIAL_ANNOUNCEMENT", observed_at: 20, raw_json: JSON.stringify({ url: "https://u/1" }) },
      { ...base, obs_id: 3, source_id: "upbit_market", role: "PROGRESS", tier: "OFFICIAL_STRUCTURED", observed_at: 30, raw_json: null },
      { ...base, obs_id: 4, source_id: "upbit_market", role: "CONFIRM", tier: "OFFICIAL_STRUCTURED", observed_at: 25, raw_json: null },
    ]);
    assert.deepEqual(ev.map((e) => e.sourceId), ["upbit_market", "upbit_notice", "newlistings"]);
    assert.deepEqual(ev[0].roles, ["PROGRESS", "CONFIRM"]);
    assert.equal(ev[0].firstObservedAt, 25);
    assert.equal(ev[0].tierLabel, "官方结构化");
    assert.deepEqual(ev[1].urls, ["https://u/1"]);
  });
});

function eventRow(over: Partial<RawEventRow> = {}): RawEventRow {
  return {
    event_id: 1,
    access_id: 1,
    asset_key: "sym:REZ",
    platform_id: "upbit",
    access_kind: "SPOT",
    quote: "KRW",
    family: "ADD",
    from_status: "NONE",
    to_status: "LIVE",
    event_type: "SPOT_LISTED",
    fiat_tier: null,
    anchor_at: 1000,
    announced_at: null,
    source_detected_at: null,
    observed_at: 1000,
    effective_at: null,
    live_observed_at: null,
    poll_prev_at: null,
    confidence: 0.95,
    independent_source_count: 1,
    provisional: 0,
    retracted: 0,
    first_source_id: "upbit_market",
    updated_at: 1000,
    network: "",
    country: "",
    fiat: "",
    payment_method: "",
    current_status: "LIVE",
    pending_removal_at: null,
    asset_id: null,
    g_asset_key: null,
    asset_symbol: null,
    asset_name: null,
    asset_type: null,
    platform_symbol: "REZ",
    resolution_status: "UNRESOLVED",
    resolution_source: "",
    suggested_asset_id: null,
    suggested_asset_key: null,
    suggested_symbol: null,
    platform_name: "Upbit",
    platform_type: "CEX",
    first_source_name: null,
    first_source_tier: "OFFICIAL_STRUCTURED",
    ...over,
  };
}

describe("feed shaping, filtering, grouping", () => {
  it("shapes a row with deployments and a market link", () => {
    const market = new Map([
      ["bsc:0xbeef", { chain: "bsc", address: "0xBEEF", symbol: "REZ", name: null, price: 1, marketCap: null, liquidity: null, volume24h: null, holders: null, observedAt: 1, table: "token_snapshot", source: null }],
    ]);
    const e = shapeEvent(
      eventRow({ asset_id: null, resolution_status: "SUGGESTED", suggested_asset_id: 7, suggested_asset_key: "crypto:bsc:0xbeef", suggested_symbol: "REZ" }),
      { deployments: [{ chain: "bsc", contract: "0xbeef" }], market },
    );
    assert.equal(e.symbol, "REZ");
    assert.equal(e.platformName, "Upbit");
    assert.equal(e.resolution.status, "SUGGESTED");
    assert.equal(e.suggestedAssetKey, "crypto:bsc:0xbeef");
    assert.deepEqual(e.chains, ["bsc"]);
    assert.equal(e.market?.address, "0xBEEF");
    assert.equal(e.desc.label, "现货上线");
    assert.equal(e.firstSourceName, "upbit_market");
  });

  it("collapses events sharing a group_key (STATE_MACHINE.md §6.1) into one row; group_key is opaque", () => {
    const del = { event_type: "SPOT_DELISTED", family: "REMOVE", from_status: "LIVE", to_status: "REMOVED", anchor_at: 1000, updated_at: 1000 };
    const gk = "ann:upbit_notice:upbit:notice:5200:sym:OMG"; // contains ':' inside parts — must not be split
    const evs = [
      shapeEvent(eventRow({ ...del, event_id: 11, access_id: 1, quote: "KRW", group_key: gk })),
      shapeEvent(eventRow({ ...del, event_id: 12, access_id: 2, quote: "BTC", group_key: gk, event_type: "SPOT_ANNOUNCEMENT_CANCELLED", from_status: "ANNOUNCED" })),
      shapeEvent(eventRow({ ...del, event_id: 13, access_id: 3, quote: "USDT", group_key: gk })),
      // a key that only differs after a ':' → different group
      shapeEvent(eventRow({ ...del, event_id: 14, access_id: 4, quote: "KRW", platform_id: "bithumb", group_key: gk + "X" })),
      // explicit ev: keys / old DB without the column → never merged
      shapeEvent(eventRow({ ...del, event_id: 15, access_id: 5, quote: "KRW", anchor_at: 900, group_key: "ev:15" })),
      shapeEvent(eventRow({ ...del, event_id: 16, access_id: 6, quote: "BTC", anchor_at: 900 })),
      shapeEvent(eventRow({ ...del, event_id: 17, access_id: 7, quote: "USDT", anchor_at: 900, group_key: null })),
    ];
    assert.equal(evs[5].groupKey, "ev:16");
    assert.equal(evs[6].groupKey, "ev:17");
    const out = collapseSiblings(evs);
    assert.equal(out.length, 5);
    const head = out.find((e) => e.siblings.length)!;
    assert.equal(head.id, 13); // newest by event_id at equal anchor
    assert.deepEqual(head.siblings.map((x) => x.id).sort(), [11, 12]);
    assert.equal(head.siblings.find((x) => x.id === 12)?.label, describeEvent("SPOT_ANNOUNCEMENT_CANCELLED").label);
    assert.deepEqual(eventQuotes(head).sort(), ["BTC", "KRW", "USDT"]);
    assert.equal(evs[2].siblings.length, 0, "input events are not mutated");
    assert.deepEqual(collapseSiblings([]), []);
  });

  it("source links: observation url first, raw-JSON extraction only when url is null", () => {
    const obs = (over: Partial<RawObservationRow>): RawObservationRow => ({
      event_id: 1, role: "ORIGIN", obs_id: 1, source_id: "upbit_notice", obs_kind: "ANNOUNCEMENT", action: "LISTING", origin_group: "upbit",
      observed_at: 1, announced_at: 1, source_event_id: "n", source_name: "Upbit 公告", tier: "OFFICIAL_ANNOUNCEMENT",
      raw_json: JSON.stringify({ url: "https://raw.example/a" }), ...over,
    });
    assert.deepEqual(summarizeEvidence([obs({ url: "https://upbit.com/n/1" })])[0].urls, ["https://upbit.com/n/1"]);
    assert.deepEqual(summarizeEvidence([obs({ url: null })])[0].urls, ["https://raw.example/a"]);
    assert.deepEqual(summarizeEvidence([obs({})])[0].urls, ["https://raw.example/a"]); // old DB: no url key
    const e = shapeEvent(eventRow({ url: "https://view.example/x" }), { evidence: [obs({ url: "https://upbit.com/n/1" })] });
    assert.equal(e.url, "https://view.example/x");
    assert.equal(shapeEvent(eventRow({}), { evidence: [obs({ url: null })] }).url, "https://raw.example/a");
  });

  it("relabels a (hypothetical) warning-marker event instead of showing it as suspended", () => {
    const e = shapeEvent(eventRow({ asset_key: "warning:REZ", event_type: "SPOT_SUSPENDED", family: "SUSPEND" }));
    assert.notEqual(e.desc.category, "pause");
    assert.match(e.desc.label, /警示/);
  });

  it("prefers confirmed asset symbol, then platform symbol, then key", () => {
    assert.equal(shapeEvent(eventRow({ asset_symbol: "AAPLx", platform_symbol: "AAPLX" })).symbol, "AAPLx");
    assert.equal(shapeEvent(eventRow({ platform_symbol: null, asset_key: "xstocks:TSLAx" })).symbol, "TSLAx");
  });

  it("sorts newest first and filters", () => {
    const evs = [
      shapeEvent(eventRow({ event_id: 1, anchor_at: 100, updated_at: 100 })),
      shapeEvent(eventRow({ event_id: 2, anchor_at: 300, updated_at: 300, platform_id: "bithumb", event_type: "SPOT_SUSPENDED", family: "SUSPEND" })),
      shapeEvent(eventRow({ event_id: 3, anchor_at: 300, updated_at: 300, network: "solana", access_kind: "FIAT_ROUTE", event_type: "FIAT_ROUTE_SUPPORTED", platform_id: "ramp" })),
      shapeEvent(eventRow({ event_id: 4, anchor_at: 50, retracted: 1 })),
    ];
    assert.deepEqual(sortEvents(evs).map((e) => e.id), [3, 2, 1, 4]);
    assert.deepEqual(filterEvents(evs, {}).map((e) => e.id), [1, 2, 3]);
    assert.deepEqual(filterEvents(evs, { includeRetracted: true }).length, 4);
    assert.deepEqual(filterEvents(evs, { platforms: ["bithumb"] }).map((e) => e.id), [2]);
    assert.deepEqual(filterEvents(evs, { categories: ["fiat"] }).map((e) => e.id), [3]);
    assert.deepEqual(filterEvents(evs, { eventTypes: ["spot_listed"] }).map((e) => e.id), [1]);
    assert.deepEqual(filterEvents(evs, { chain: "sol" }).map((e) => e.id), [3]);
    assert.deepEqual(filterEvents(evs, { chain: "all" }).length, 3);
    assert.deepEqual(filterEvents(evs, { since: 200 }).map((e) => e.id), [2, 3]);
    // radar_core.recent_events：episode 在窗口内被推进（updated_at）也算
    assert.deepEqual(filterEvents([shapeEvent(eventRow({ anchor_at: 100, updated_at: 500 }))], { since: 200 }).length, 1);
  });

  it("groups by global asset when confirmed, else by platform-local key", () => {
    const evs = [
      shapeEvent(eventRow({ event_id: 1, anchor_at: 100, platform_id: "upbit" })),
      shapeEvent(eventRow({ event_id: 2, anchor_at: 200, platform_id: "bithumb", event_type: "SPOT_DELISTED", family: "REMOVE" })),
      shapeEvent(eventRow({ event_id: 3, anchor_at: 150, asset_key: "xstocks:AAPLx", asset_id: 9, g_asset_key: "xstocks:AAPLx", asset_symbol: "AAPLx" })),
    ];
    const g = groupEventsByAsset(evs);
    assert.deepEqual(g.map((x) => x.key), ["sym:REZ", "xstocks:AAPLx"]);
    assert.deepEqual(g[0].platforms, ["bithumb", "upbit"]);
    assert.equal(g[0].events.length, 2);
    assert.equal(g[0].maxSeverity, 3);
    assert.equal(g[1].resolution.status, "CONFIRMED");
  });
});

function stateRow(over: Partial<RawAccessStateRow> = {}): RawAccessStateRow {
  return {
    access_id: 1,
    asset_key: "sym:REZ",
    asset_id: null,
    platform_id: "upbit",
    access_kind: "SPOT",
    quote: "KRW",
    country: "",
    fiat: "",
    payment_method: "",
    network: "",
    status: "LIVE",
    fiat_tier: null,
    provisional: 0,
    pending_removal_at: null,
    first_seen_at: 10,
    last_seen_at: 20,
    status_since: 15,
    created_via_baseline: 0,
    g_asset_key: null,
    asset_symbol: null,
    asset_name: null,
    asset_type: null,
    platform_symbol: "REZ",
    resolution_status: "UNRESOLVED",
    resolution_source: "",
    suggested_asset_id: null,
    platform_name: "Upbit",
    platform_type: "CEX",
    match: "asset",
    ...over,
  };
}

describe("buy entries / current state", () => {
  it("entry labels", () => {
    assert.equal(entryLabel("SPOT", "KRW", "", null), "现货 · KRW");
    assert.equal(entryLabel("FIAT_ROUTE", "EUR", "solana", "QUOTABLE", "DE"), "法币通道 · EUR · solana · 可报价 · DE");
    assert.equal(entryLabel("CHAIN_DEPLOYMENT", "", "base", null), "链部署 · base");
    assert.equal(entryLabel("DEPOSIT_NETWORK", "", "bsc", null), "充值 · bsc");
  });

  it("shapes entries with resolution by match kind", () => {
    const sug = shapeBuyEntry(stateRow({ match: "suggested", resolution_status: "SUGGESTED", resolution_source: "symbol" }));
    assert.equal(sug.resolution.status, "SUGGESTED");
    const key = shapeBuyEntry(stateRow({ match: "key", asset_key: "ca:solana:Mint" }));
    assert.equal(key.resolution.status, "CONFIRMED");
    const asset = shapeBuyEntry(stateRow({ asset_id: 3, asset_symbol: "REZ" }));
    assert.deepEqual([asset.resolution.status, asset.statusLabel, asset.statusTone, asset.platformTypeLabel, asset.warning], ["CONFIRMED", "可用", "up", "交易所", false]);
    assert.equal(shapeBuyEntry(stateRow({ created_via_baseline: 1, status_since: 10 })).sinceIsBaseline, true);
    assert.equal(shapeBuyEntry(stateRow({ created_via_baseline: 1, status_since: 15 })).sinceIsBaseline, false);
  });

  it("sorts LIVE first, then by entry importance; dedupes by strongest match", () => {
    const rows = [
      stateRow({ access_id: 1, status: "REMOVED", platform_id: "bithumb", platform_name: "Bithumb" }),
      stateRow({ access_id: 2, access_kind: "FIAT_ROUTE", platform_id: "ramp", platform_name: "Ramp", quote: "EUR" }),
      stateRow({ access_id: 3, status: "ANNOUNCED", platform_id: "korbit", platform_name: "Korbit" }),
      stateRow({ access_id: 4 }),
    ];
    assert.deepEqual(sortBuyEntries(rows.map(shapeBuyEntry)).map((e) => e.accessId), [4, 2, 3, 1]);
    const d = dedupeStateRows([stateRow({ access_id: 9, match: "suggested" }), stateRow({ access_id: 9, match: "asset" }), stateRow({ access_id: 9, match: "key" })]);
    assert.deepEqual(d.map((r) => r.match), ["asset"]);
  });

  it("groups current state and skips warning markers", () => {
    const g = groupStates([
      stateRow({ access_id: 1 }),
      stateRow({ access_id: 2, platform_id: "bithumb", status: "SUSPENDED" }),
      stateRow({ access_id: 3, asset_key: "warning:REZ", status: "NONE" }),
      stateRow({ access_id: 4, asset_key: "xstocks:AAPLx", g_asset_key: "xstocks:AAPLx", asset_id: 5, asset_symbol: "AAPLx", status: "SUSPENDED" }),
    ]);
    assert.deepEqual(g.map((x) => [x.key, x.live, x.entries.length]), [
      ["sym:REZ", 1, 2],
      ["xstocks:AAPLx", 0, 1],
    ]);
  });
});

// ----------------------------------------------------------------------------- health
const NOW = 2_000_000_000_000;
function run(over: Partial<SourceRunRow> = {}): SourceRunRow {
  return {
    source_id: "upbit_market",
    kind: "snapshot",
    module: "adapters.upbit",
    period_sec: 30,
    adapter_state: "ok",
    adapter_note: "",
    collector_heartbeat: NOW,
    last_attempt: NOW - 5_000,
    last_success: NOW - 4_000,
    round_ok: 1,
    latency_ms: 100,
    consecutive_errors: 0,
    last_error: "",
    attempts: 10,
    successes: 10,
    rows_received: 100,
    events_written: 0,
    last_event_at: null,
    connected: 0,
    last_heartbeat: null,
    heartbeat_sec: 0,
    updated_at: NOW,
    ...over,
  };
}
function scope(over: Partial<SourceHealthRow> = {}): SourceHealthRow {
  return {
    source_id: "upbit_market",
    scope: "KRW",
    status: "HEALTHY",
    schema_ok: 1,
    last_snapshot_size: 200,
    baseline_done: 1,
    last_fetch_at: NOW - 4_000,
    last_ok_at: NOW - 4_000,
    last_error: "",
    ...over,
  };
}
const alive = collectorState(NOW, NOW - 2_000);
const dead = collectorState(NOW, NOW - COLLECTOR_STALE_MS - 1);

describe("classifyRunStatus (port of access_db.classify_status)", () => {
  it("polling sources", () => {
    assert.equal(classifyRunStatus(NOW, run()), "LIVE");
    assert.equal(classifyRunStatus(NOW, run({ last_success: NOW - 32_000 })), "LIVE"); // period + 2s 边界
    assert.equal(classifyRunStatus(NOW, run({ last_success: NOW - 32_001 })), "DELAYED");
    assert.equal(classifyRunStatus(NOW, run({ last_success: NOW - 62_001 })), "STALE");
    assert.equal(classifyRunStatus(NOW, run({ round_ok: 0, consecutive_errors: 1 })), "STALE");
    assert.equal(classifyRunStatus(NOW, run({ last_success: null, successes: 0, consecutive_errors: 3 })), "FAILED");
    assert.equal(classifyRunStatus(NOW, run({ last_success: null, successes: 0, consecutive_errors: 2 })), "STALE");
    assert.equal(classifyRunStatus(NOW, run({ period_sec: 0, last_success: NOW - 62_001 })), "DELAYED"); // 默认周期 60s
  });
  it("streams", () => {
    const s = { kind: "stream", period_sec: 0, heartbeat_sec: 60 };
    assert.equal(classifyRunStatus(NOW, run({ ...s, connected: 1, last_heartbeat: NOW - 1_000 })), "LIVE");
    assert.equal(classifyRunStatus(NOW, run({ ...s, connected: 1, last_heartbeat: NOW - 61_000 })), "DELAYED");
    assert.equal(classifyRunStatus(NOW, run({ ...s, connected: 0 })), "DOWN");
    assert.equal(classifyRunStatus(NOW, run({ ...s, connected: 0, successes: 0, consecutive_errors: 3 })), "FAILED");
  });
  it("adapter states", () => {
    assert.equal(classifyRunStatus(NOW, run({ adapter_state: "missing" })), "MISSING");
    assert.equal(classifyRunStatus(NOW, run({ adapter_state: "error" })), "ERROR");
    assert.equal(classifyRunStatus(NOW, run({ adapter_state: "no_source" })), "NO_SOURCE");
  });
});

describe("source health summary", () => {
  it("collector heartbeat threshold", () => {
    assert.equal(alive.alive, true);
    assert.equal(collectorState(NOW, NOW - COLLECTOR_STALE_MS).alive, true);
    assert.equal(dead.alive, false);
    assert.deepEqual(collectorState(NOW, null), { heartbeatAt: null, ageMs: null, alive: false });
    assert.equal(collectorState(NOW, String(NOW - 1000)).ageMs, 1000); // runner_meta.v 是 TEXT
  });

  it("levels per rule", () => {
    const lvl = (r: SourceRunRow | null, sc: SourceHealthRow[] = [scope()], c = alive, gaps = []) =>
      summarizeSource(NOW, "upbit_market", r, sc, gaps, c).level;
    assert.equal(lvl(run()), "healthy");
    assert.equal(lvl(run({ last_success: NOW - 40_000 })), "degraded");
    assert.equal(lvl(run(), [scope({ status: "DEGRADED", last_error: "size 200 -> 0" })]), "degraded");
    assert.equal(lvl(run(), [scope({ schema_ok: 0 })]), "degraded");
    assert.equal(lvl(run({ round_ok: 0, consecutive_errors: 1 })), "stale");
    assert.equal(lvl(run(), [scope({ status: "DOWN" })]), "down");
    assert.equal(lvl(run({ adapter_state: "error", adapter_note: "ImportError" })), "down");
    assert.equal(lvl(run({ adapter_state: "missing" })), "off");
    assert.equal(
      summarizeSource(NOW, "x", run(), [scope()], [{ source_id: "x", scope: "", started_at: NOW - 1000, ended_at: null, reason: "", backfilled: 0 }], alive).level,
      "down",
    );
    assert.equal(lvl(null, [scope()]), "healthy"); // 没有 source_run 表
    assert.equal(lvl(null, []), "off");
  });

  it("dead collector: stream goes stale, polling keeps its own clock", () => {
    const stream = run({ kind: "stream", period_sec: 0, connected: 1, last_heartbeat: NOW - 1000, heartbeat_sec: 60 });
    assert.equal(summarizeSource(NOW, "s", stream, [], [], alive).level, "healthy");
    const s = summarizeSource(NOW, "s", stream, [], [], dead);
    assert.equal(s.level, "stale");
    assert.match(s.reasons.join(" "), /采集进程/);
    const p = summarizeSource(NOW, "p", run(), [scope()], [], dead);
    assert.equal(p.level, "healthy");
    assert.match(p.reasons.join(" "), /采集进程/);
  });

  it("aggregates and sorts worst first, off excluded", () => {
    const sources = buildSourceSummaries(
      NOW,
      [run(), run({ source_id: "korbit_pairs", round_ok: 0, consecutive_errors: 2 }), run({ source_id: "onramper", adapter_state: "missing" })],
      [scope(), scope({ source_id: "bithumb_market", status: "DOWN" })],
      [],
      alive,
    );
    assert.deepEqual(sources.map((s) => [s.sourceId, s.level]), [
      ["bithumb_market", "down"],
      ["korbit_pairs", "stale"],
      ["upbit_market", "healthy"],
      ["onramper", "off"],
    ]);
    const sum = summarizeHealth(sources, alive);
    assert.deepEqual([sum.level, sum.active, sum.counts.off, sum.label], ["down", 3, 1, "故障"]);
    assert.equal(summarizeHealth([], alive).level, "off");
    assert.equal(summarizeHealth(sources.filter((s) => s.level === "healthy" || s.level === "off"), alive).level, "healthy");
  });
});

describe("maintenance jobs (maintenance_run)", () => {
  const m = (over: Partial<MaintenanceRunRow> = {}): MaintenanceRunRow => ({
    job_id: "resolve",
    module: "resolve",
    period_sec: 3600,
    job_state: "ok",
    job_note: "",
    last_attempt: NOW - 600_000,
    last_success: NOW - 590_000,
    round_ok: 1,
    latency_ms: 10_000,
    consecutive_errors: 0,
    last_error: "",
    attempts: 3,
    successes: 3,
    last_result: JSON.stringify({ suggested: 3, ambiguous_symbols: { X: 2 }, alpha_error: "" }),
    updated_at: NOW,
    ...over,
  });
  it("uses polling clock rules keyed on job_state", () => {
    const ok = summarizeMaintenance(NOW, m());
    assert.deepEqual([ok.label, ok.level, ok.clock], ["身份解析", "healthy", "LIVE"]);
    assert.deepEqual(ok.lastResult, { suggested: 3, alpha_error: "" }); // 只留标量
    assert.equal(summarizeMaintenance(NOW, m({ last_success: NOW - 3_700_000 })).level, "degraded");
    assert.equal(summarizeMaintenance(NOW, m({ last_success: NOW - 7_300_000 })).level, "stale");
    const failing = summarizeMaintenance(NOW, m({ round_ok: 0, consecutive_errors: 2, last_error: "HTTP 503" }));
    assert.equal(failing.level, "stale");
    assert.match(failing.reasons.join(" "), /连续失败 2 次：HTTP 503/);
    assert.equal(summarizeMaintenance(NOW, m({ last_success: null, successes: 0, consecutive_errors: 3, round_ok: 0 })).level, "down");
    assert.equal(summarizeMaintenance(NOW, m({ job_state: "missing", job_note: "resolve not found" })).level, "off");
    assert.equal(summarizeMaintenance(NOW, m({ job_state: "error" })).level, "down");
    assert.deepEqual(summarizeMaintenance(NOW, m({ last_result: "not json" })).lastResult, {});
    assert.equal(summarizeMaintenance(NOW, m({ job_id: "other" })).label, "other");
  });
});
