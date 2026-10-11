import { createServerFn } from "@tanstack/react-start";
import { DatabaseSync } from "node:sqlite";
import { z } from "zod";
import { revisionCache } from "./wm-unified-cache";
import { queryUnified } from "./wm-unified-query";
const path =
  process.env.WM_MARKET_DB ||
  "/Users/zhaomosheng/Desktop/world-model-os-v1/data/world_model_market.sqlite";
const coverageCache = revisionCache<ReturnType<typeof readCoverage>>();
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const amount=z.number().finite().min(0).optional();
const schema = z.object({
  tier:z.enum(["NEW","EARLY","MAIN"]).optional(),
  onlyHiddenKeys:z.array(z.string().max(200)).max(5000).optional(),
  identity:z.enum(["VERIFIED_MAPPING","CONTRACT_MATCH","VERIFIED_CONTRACT","UNRESOLVED"]).optional(),
  minMarketCap:amount,maxMarketCap:amount,minVolume:amount,maxVolume:amount,
  minLiquidity:amount,maxLiquidity:amount,minAgeDays:amount,maxAgeDays:amount,
  search: z.string().max(200).optional(),
  chain: z.string().max(30).optional(),
  source: z.enum(["cg", "cmc", "dex", "gmgn"]).optional(),
  quality: z.enum(["VALID", "PARTIAL", "CONFLICT", "BLOCKED"]).optional(),
  page: z.number().int().min(1).max(100000).optional(),
  sort: z.string().max(30).optional(),
  direction: z.enum(["asc", "desc"]).optional(),
  dates: z
    .array(z.object({ date, direction: z.enum(["asc", "desc"]) }))
    .max(7)
    .optional(),
  dailyFilters: z
    .array(z.object({ date, sign: z.enum(["positive", "negative"]) }))
    .max(7)
    .optional(),
  hiddenKeys: z.array(z.string().max(200)).max(5000).optional(),
  watchKeys: z.array(z.string().max(200)).max(5000).optional(),
  excluded: z.array(z.string().max(80)).max(5000).optional(),
  only: z.array(z.string().max(80)).max(5000).optional(),
});
export const fetchUnifiedMarket = createServerFn({ method: "POST" })
  .inputValidator(schema)
  .handler(async ({ data }) => {
    const db = new DatabaseSync(path, { readOnly: true });
    db.exec("PRAGMA busy_timeout=5000; BEGIN");
    try {
      const result = queryUnified(db, data);
      const revision = (db.prepare("SELECT value FROM wm_unified_meta WHERE key='synced_at'").get() as {value:string})?.value ?? "";
      const stats = coverageCache(path+":"+revision, () => readCoverage(db));
      const defaultWatch = db.prepare("SELECT u.canonical_asset_id,u.name,u.symbol FROM wm_unified_sources s JOIN wm_unified_current u USING(canonical_asset_id) WHERE s.provider='cg' AND s.provider_id IN ('bitcoin','ethereum','solana') AND u.identity_confidence='VERIFIED_MAPPING'").all() as {canonical_asset_id:string;name:string|null;symbol:string|null}[];
      return { ...result, stats, defaultWatch };
    } finally {
      db.exec("ROLLBACK");
      db.close();
    }
  });
export const fetchUnifiedDetail = createServerFn({ method: "GET" })
  .inputValidator(z.object({ id: z.string().max(80) }))
  .handler(async ({ data }) => {
    const db = new DatabaseSync(path, { readOnly: true });
    db.exec("PRAGMA busy_timeout=5000; BEGIN");
    try {
      let id = data.id;
      const seen = new Set<string>();
      while (!seen.has(id)) {
        seen.add(id);
        const redirect = db
          .prepare("SELECT canonical_asset_id FROM wm_unified_redirects WHERE old_id=?")
          .get(id) as { canonical_asset_id: string } | undefined;
        if (!redirect) break;
        id = redirect.canonical_asset_id;
      }
      const current = db
        .prepare("SELECT * FROM wm_unified_current WHERE canonical_asset_id=?")
        .get(id);
      const mappings = db
        .prepare("SELECT * FROM wm_unified_sources WHERE canonical_asset_id=?")
        .all(id);
      const raw = db
        .prepare(
          "SELECT v.* FROM wm_unified_raw_versions v JOIN wm_unified_sources s ON s.provider=v.provider AND s.provider_id=v.provider_id WHERE s.canonical_asset_id=? ORDER BY v.date_utc DESC,v.collected_at_utc DESC",
        )
        .all(id);
      const conflicts = db
        .prepare("SELECT * FROM wm_unified_conflicts WHERE canonical_asset_id=?")
        .all(id);
      const history = db
        .prepare("SELECT * FROM wm_unified_daily WHERE canonical_asset_id=? ORDER BY date_utc DESC")
        .all(id);
      return { current, mappings, raw, conflicts, history };
    } finally {
      db.exec("ROLLBACK");
      db.close();
    }
  });

function readCoverage(db: DatabaseSync) {
      const get = (sql: string) => Number((db.prepare(sql).get() as { n: number }).n);
      const counts = Object.fromEntries(
        ["cg", "cmc", "dex", "gmgn"].map((p) => [
          p,
          Number(
            (
              db
                .prepare(
                  "SELECT COUNT(DISTINCT provider_id) n FROM wm_market_observations WHERE provider=? AND date_utc=(SELECT MAX(date_utc) FROM wm_market_observations WHERE provider=?)",
                )
                .get(p, p) as { n: number }
            ).n,
          ),
        ]),
      );
      return {
        cg: get("SELECT COUNT(*) n FROM wm_unified_sources WHERE provider='cg'"),
        cmc: get("SELECT COUNT(*) n FROM wm_unified_sources WHERE provider='cmc'"),
        dex: counts.dex,
        gmgn: get("SELECT COUNT(*) n FROM wm_unified_sources WHERE provider='gmgn'"),
        onchain_audit: JSON.parse((db.prepare("SELECT value FROM wm_unified_meta WHERE key='onchain_audit'").get() as {value:string}|undefined)?.value ?? "{}"),
        unique_assets: get("SELECT COUNT(*) n FROM wm_unified_current"),
        chain_tokens: get("SELECT COUNT(*) n FROM wm_unified_chain_tokens"),
        multi_source_matches: get("SELECT COUNT(*) n FROM wm_unified_current WHERE source_count>1"),
        unresolved: get(
          "SELECT COUNT(*) n FROM wm_unified_current WHERE identity_confidence='UNRESOLVED'",
        ),
        field_conflicts: get(
          "SELECT COUNT(*) n FROM wm_unified_conflicts WHERE comparison_status='CONFLICT' AND field!='identity'",
        ),
        identity_conflicts: get(
          "SELECT COUNT(*) n FROM wm_unified_conflicts WHERE field='identity'",
        ),
        synced_at: (
          db.prepare("SELECT value FROM wm_unified_meta WHERE key='synced_at'").get() as {
            value: string;
          }
        )?.value,
      };
}
