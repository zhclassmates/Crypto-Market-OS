import type { DatabaseSync, SQLInputValue } from "node:sqlite";
import { completedUtcWindow } from "./wm-unified-display.ts";
export type UnifiedSqlRow = Record<string, string | number | null>;
export interface UnifiedMarketRow {
  canonical_asset_id: string;
  name: string | null;
  symbol: string | null;
  chains: string;
  contracts: string;
  cg_id: string;
  cmc_id: string;
  dex_token_id: string;
  source_list: string;
  source_count: number;
  primary_source: string | null;
  identity_confidence: string;
  price_usd: number | null;
  market_cap: number | null;
  fdv: number | null;
  volume_24h: number | null;
  liquidity_usd: number | null;
  market_cap_rank: number | null;
  price_change_24h: number | null;
  first_seen_utc: string | null;
  latest_data_time: string | null;
  quality_status: string;
  data_timestamp: string | null;
  source_conflict: number;
  missing_fields: string;
  selection_json: string;
  pool_data_json: string;
  history: UnifiedSqlRow[];
  preference_aliases: string;
  token_created_at: string | null;
  gmgn_id: string;
  market_tier: "MAIN" | "EARLY" | "OBSERVE" | "UNKNOWN";
  is_new: number;
}
export interface UnifiedQuery {
  search?: string;
  chain?: string;
  source?: string;
  quality?: string;
  identity?: string;
  tier?: "NEW" | "EARLY" | "MAIN";
  onlyHiddenKeys?: string[];
  minMarketCap?: number; maxMarketCap?: number;
  minVolume?: number; maxVolume?: number;
  minLiquidity?: number; maxLiquidity?: number;
  minAgeDays?: number; maxAgeDays?: number;
  page?: number;
  sort?: string;
  direction?: string;
  dates?: { date: string; direction: "asc" | "desc" }[];
  dailyFilters?: { date: string; sign: "positive" | "negative" }[];
  excluded?: string[];
  only?: string[];
  hiddenKeys?: string[];
  watchKeys?: string[];
}
export function queryUnified(db: DatabaseSync, input: UnifiedQuery, now = new Date()) {
  const dates = completedUtcWindow(now);
  const todayUtc = now.toISOString().slice(0, 10);
  const validDaily = (alias: string) => `${alias}.time_basis='utc_finalized' AND ${alias}.return_quality='VALID' AND ${alias}.date_utc<'${todayUtc}'`;
  const where: string[] = [];
  const args: SQLInputValue[] = [];
  const redirectRows = db
    .prepare("SELECT old_id,canonical_asset_id FROM wm_unified_redirects")
    .all() as { old_id: string; canonical_asset_id: string }[];
  const redirects = new Map(redirectRows.map((r) => [r.old_id, r.canonical_asset_id]));
  const resolveId = (id: string) => {
    const seen = new Set<string>();
    while (redirects.has(id) && !seen.has(id)) {
      seen.add(id);
      id = redirects.get(id)!;
    }
    return id;
  };
  const aliases = new Map<string, string[]>();
  for (const r of redirectRows) {
    const id = resolveId(r.old_id);
    aliases.set(id, [...(aliases.get(id) ?? []), r.old_id]);
  }
  const resolveKeys = (keys: string[]) => {
    const ids = new Set<string>();
    for (const key of keys) {
      const i = key.indexOf(":");
      const chain = key.slice(0, i),
        address = key.slice(i + 1);
      if (chain === "unified") {
        ids.add(resolveId(address));
        continue;
      }
      const normalized =
        ({ eth: "ethereum", sol: "solana", rh: "robinhood" } as Record<string, string>)[chain] ??
        chain;
      for (const r of db
        .prepare(
          "SELECT canonical_asset_id FROM wm_unified_chain_tokens WHERE chain_id=? AND contract_address=?",
        )
        .all(normalized, address) as { canonical_asset_id: string }[])
        ids.add(r.canonical_asset_id);
    }
    return [...ids];
  };
  input = {
    ...input,
    excluded: [...(input.excluded ?? []), ...resolveKeys(input.hiddenKeys ?? [])],
    only: input.watchKeys ? resolveKeys(input.watchKeys) : input.only,
  };
  if (input.search) {
    where.push(
      `(u.name LIKE ? ESCAPE '\\' OR u.symbol LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM wm_unified_chain_tokens t WHERE t.canonical_asset_id=u.canonical_asset_id AND ((t.chain_id='solana' AND instr(t.contract_address,?)>0) OR (t.chain_id!='solana' AND t.contract_address LIKE ? ESCAPE '\\'))) OR u.canonical_asset_id=?)`,
    );
    const q = "%" + input.search.replace(/[\\%_]/g, "\\$&") + "%";
    args.push(q, q, input.search, q, input.search);
  }
  if (input.chain) {
    where.push(
      "(EXISTS (SELECT 1 FROM wm_unified_chain_tokens t WHERE t.canonical_asset_id=u.canonical_asset_id AND t.chain_id=?) OR EXISTS(SELECT 1 FROM json_each(u.chains) j WHERE j.value=?))",
    );
    args.push(input.chain,input.chain);
  }
  if (input.source) {
    where.push(
      "EXISTS (SELECT 1 FROM wm_unified_sources s WHERE s.canonical_asset_id=u.canonical_asset_id AND s.provider=?)",
    );
    args.push(input.source);
  }
  if (input.quality) {
    where.push("u.quality_status=?");
    args.push(input.quality);
  }
  if (input.identity) { where.push("u.identity_confidence=?"); args.push(input.identity); }
  if (input.tier === "NEW") {
    where.push("u.first_seen_utc>=? AND u.first_seen_utc<?");
    const tomorrow = new Date(todayUtc + "T00:00:00Z");
    tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
    args.push(todayUtc, tomorrow.toISOString().slice(0, 10));
  } else if (input.tier) {
    where.push("u.market_tier=?");
    args.push(input.tier);
  }
  for (const [lower,upper,column] of [
    [input.minMarketCap,input.maxMarketCap,"u.market_cap"],
    [input.minVolume,input.maxVolume,"u.volume_24h"],
    [input.minLiquidity,input.maxLiquidity,"u.liquidity_usd"],
    [input.minAgeDays,input.maxAgeDays,"(julianday('now')-julianday(u.token_created_at))"],
  ] as const) {
    if (lower !== undefined && Number.isFinite(lower)) {where.push(column+">=?");args.push(lower);}
    if (upper !== undefined && Number.isFinite(upper)) {where.push(column+"<=?");args.push(upper);}
  }
  for (const f of input.dailyFilters ?? []) {
    where.push(
      `EXISTS (SELECT 1 FROM wm_unified_daily d WHERE d.canonical_asset_id=u.canonical_asset_id AND ${validDaily("d")} AND d.date_utc=? AND d.daily_return ${f.sign === "positive" ? ">" : "<"} 0)`,
    );
    args.push(f.date);
  }
  for (const [ids, negate] of [
    [input.excluded, true],
    [input.only, false],
    [input.onlyHiddenKeys ? resolveKeys(input.onlyHiddenKeys) : undefined, false],
  ] as const) {
    if (ids) {
      if (!ids.length && !negate) where.push("0");
      else if (ids.length) {
        where.push(
          `u.canonical_asset_id ${negate ? "NOT " : ""}IN (${ids.map(() => "?").join(",")})`,
        );
        args.push(...ids);
      }
    }
  }
  const clause = where.length ? " WHERE " + where.join(" AND ") : "";
  const total = Number(
    (
      db.prepare("SELECT COUNT(*) n FROM wm_unified_market_view u" + clause).get(...args) as {
        n: number;
      }
    ).n,
  );
  const order: string[] = [];
  const joins: string[] = [];
  for (const [index,d] of (input.dates ?? []).entries()) {
    if (!dates.includes(d.date)) continue;
    const alias="rank_day_"+index;
    joins.push(`LEFT JOIN wm_unified_daily ${alias} ON ${alias}.canonical_asset_id=u.canonical_asset_id AND ${alias}.date_utc='${d.date}' AND ${validDaily(alias)}`);
    order.push(`${alias}.daily_return IS NULL ASC`,`${alias}.daily_return ${d.direction === "asc" ? "ASC" : "DESC"}`);
  }
  const field = [
    "market_cap",
    "volume_24h",
    "price_change_24h",
    "price_usd",
    "fdv",
    "liquidity_usd",
  ].includes(input.sort ?? "")
    ? input.sort!
    : "market_cap";
  // SQLite DESC naturally puts NULL last and can use the existing cap/volume index.
  if (input.direction === "asc") order.push(`u.${field} IS NULL ASC`);
  order.push(`u.${field} ${input.direction === "asc" ? "ASC" : "DESC"}`, "u.canonical_asset_id ASC");
  const page = Math.min(Math.max(1, input.page ?? 1), Math.max(1, Math.ceil(total / 50)));
  // Whole filtered relation is ranked BEFORE pagination; no JavaScript row sort.
  // Rank only narrow identity keys; sorting large provenance JSON for 200k rows
  // otherwise spills to disk even though just 50 records are requested.
  const capOnly = field === "market_cap" && !input.search && !input.chain && !input.quality && !input.identity && !input.tier &&
    input.minVolume === undefined && input.maxVolume === undefined && input.minLiquidity === undefined && input.maxLiquidity === undefined && input.minAgeDays === undefined && input.maxAgeDays === undefined;
  // For date ranking SQLite otherwise scans the identity PK and fetches every
  // wide current row for the cap tie-break. The cap index covers both keys.
  const rankFrom = capOnly && db.prepare("SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_unified_cap'").get()
    ? "wm_unified_current u INDEXED BY idx_unified_cap" : "wm_unified_market_view u";
  const pageSql="SELECT u.canonical_asset_id FROM "+rankFrom+" "+joins.join(" ")+clause+" ORDER BY "+order.join(",")+" LIMIT 50 OFFSET ?";
  const ids=db.prepare(pageSql).all(...args,(page-1)*50).map(r=>String(r.canonical_asset_id));
  const pageRows=ids.length ? db.prepare(`SELECT u.*,CASE WHEN u.first_seen_utc>='${todayUtc}' AND u.first_seen_utc<date('${todayUtc}','+1 day') THEN 1 ELSE 0 END is_new FROM wm_unified_market_view u WHERE canonical_asset_id IN (${ids.map(()=>"?").join(",")})`).all(...ids) as UnifiedSqlRow[] : [];
  const rowById=new Map(pageRows.map(r=>[String(r.canonical_asset_id),r]));
  const rows=ids.map(id=>rowById.get(id)!);
  const latestFinalizedDate = (
    db.prepare("SELECT MAX(date_utc) d FROM wm_unified_daily WHERE time_basis='utc_finalized' AND date_utc<?").get(todayUtc) as { d: string | null }
  ).d;
  const history = rows.length
    ? (db
        .prepare(
          `SELECT * FROM wm_unified_daily WHERE canonical_asset_id IN (${rows.map(() => "?").join(",")}) AND time_basis='utc_finalized' AND date_utc>=? AND date_utc<=? ORDER BY date_utc`,
        )
        .all(
          ...rows.map((r) => String(r.canonical_asset_id)),
          dates[0],
          dates[6],
        ) as UnifiedSqlRow[])
    : [];
  // Aggregate the seven-day grid in one scan of the filtered relation.
  const participationRows = dates.length
    ? db.prepare(
        "SELECT d.date_utc date,COUNT(*) valid,SUM(d.daily_return>0) positive,SUM(d.daily_return<0) negative " +
        "FROM wm_unified_daily d JOIN wm_unified_market_view u USING(canonical_asset_id)" +
        (clause ? clause + " AND " : " WHERE ") +
        validDaily("d") + " AND d.date_utc>=? AND d.date_utc<=? AND d.daily_return IS NOT NULL GROUP BY d.date_utc",
      ).all(...args, dates[0], dates[6]) as { date: string; valid: number; positive: number; negative: number }[]
    : [];
  const participationByDate = new Map(participationRows.map(row => [row.date, row]));
  return {
    rows: rows.map(
      (r) =>
        ({
          ...r,
          preference_aliases: JSON.stringify(aliases.get(String(r.canonical_asset_id)) ?? []),
          history: history.filter((h) => h.canonical_asset_id === r.canonical_asset_id).map(h => ({...h,daily_return:h.return_quality === "VALID" ? h.daily_return : null})),
        }) as unknown as UnifiedMarketRow,
    ),
    participation: dates.map((date) => {
      const n = participationByDate.get(date);
      const valid = Number(n?.valid ?? 0);
      return {date,valid,positive:Number(n?.positive ?? 0),negative:Number(n?.negative ?? 0),missing:total-valid};
    }),
    // Exposed for local SQL/page verification; parameters remain bound.
    total,
    page,
    pageSize: 50,
    dates,
    latestFinalizedDate,
    windowEndUtc: dates[6],
  };
}
