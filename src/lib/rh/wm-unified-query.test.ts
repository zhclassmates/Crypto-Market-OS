import assert from "node:assert/strict";
import { test } from "node:test";
import { DatabaseSync } from "node:sqlite";
import { queryUnified } from "./wm-unified-query.ts";
const queryUnifiedAt = (db: DatabaseSync, input: Parameters<typeof queryUnified>[1]) => queryUnified(db,input,new Date("2026-10-11T08:00:00Z"));
function fixture() {
  const db = new DatabaseSync(":memory:");
  db.exec(
    `CREATE TABLE wm_unified_current(canonical_asset_id TEXT PRIMARY KEY,name TEXT,symbol TEXT,market_cap REAL,volume_24h REAL,price_usd REAL,price_change_24h REAL,fdv REAL,liquidity_usd REAL,quality_status TEXT);CREATE VIEW wm_unified_market_view AS SELECT * FROM wm_unified_current;CREATE TABLE wm_unified_sources(provider TEXT,provider_id TEXT,canonical_asset_id TEXT);CREATE TABLE wm_unified_chain_tokens(chain_id TEXT,contract_address TEXT,canonical_asset_id TEXT);CREATE TABLE wm_unified_redirects(old_id TEXT PRIMARY KEY,canonical_asset_id TEXT);CREATE TABLE wm_unified_daily(canonical_asset_id TEXT,date_utc TEXT,daily_return REAL,time_basis TEXT DEFAULT 'utc_finalized',return_quality TEXT DEFAULT 'VALID');`,
  );
  db.exec("ALTER TABLE wm_unified_current ADD COLUMN chains TEXT DEFAULT '[]';ALTER TABLE wm_unified_current ADD COLUMN identity_confidence TEXT DEFAULT 'VERIFIED_CONTRACT';ALTER TABLE wm_unified_current ADD COLUMN token_created_at TEXT;ALTER TABLE wm_unified_current ADD COLUMN first_seen_utc TEXT DEFAULT '2026-10-01';ALTER TABLE wm_unified_current ADD COLUMN market_tier TEXT DEFAULT 'UNKNOWN'");
  for (let i = 0; i < 125; i++) {
    const id = "a" + String(i).padStart(3, "0");
    db.prepare("INSERT INTO wm_unified_current(canonical_asset_id,name,symbol,market_cap,volume_24h,price_usd,price_change_24h,fdv,liquidity_usd,quality_status) VALUES(?,?,?,?,?,?,?,?,?,?)").run(
      id,
      "Token " + i,
      i === 1 ? "SAME" : "T" + i,
      i,
      i * 2,
      1,
      null,
      null,
      null,
      i % 2 ? "PARTIAL" : "CONFLICT",
    );
    db.prepare("INSERT INTO wm_unified_sources VALUES(?,?,?)").run(
      i % 2 ? "cmc" : "cg",
      String(i),
      id,
    );
    db.prepare("INSERT INTO wm_unified_chain_tokens VALUES(?,?,?)").run(
      i % 2 ? "base" : "ethereum",
      "0x" + String(i).padStart(40, "0"),
      id,
    );
    if (i < 10)
      db.prepare("INSERT INTO wm_unified_daily(canonical_asset_id,date_utc,daily_return) VALUES(?,?,?)").run(
        id,
        "2026-10-10",
        i % 2 ? -i : i,
      );
  }
  db.prepare("INSERT INTO wm_unified_daily(canonical_asset_id,date_utc,daily_return) VALUES(?,?,?)").run("a001", "2026-10-09", 90);
  db.prepare("INSERT INTO wm_unified_daily(canonical_asset_id,date_utc,daily_return) VALUES(?,?,?)").run("a003", "2026-10-09", 10);
  return db;
}
const check = (name: string, fn: (db: DatabaseSync) => void) =>
  test(name, () => {
    const db = fixture();
    try {
      fn(db);
    } finally {
      db.close();
    }
  });
check("pagination bounded, deterministic and no duplicate pages", (db) => {
  const a = queryUnifiedAt(db, {}),
    b = queryUnifiedAt(db, { page: 2 });
  assert.equal(a.total, 125);
  assert.equal(a.rows.length, 50);
  assert.equal(b.rows.length, 50);
  assert.equal(a.rows[0].canonical_asset_id, "a124");
  assert.equal(new Set([...a.rows, ...b.rows].map((r) => r.canonical_asset_id)).size, 100);
});
check("server chain/source/quality filter", (db) => {
  const r = queryUnifiedAt(db, { chain: "base", source: "cmc", quality: "PARTIAL" });
  assert.equal(r.total, 62);
  assert.ok(r.rows.every((r) => Number(r.canonical_asset_id.slice(1)) % 2 === 1));
});
check("search by contract", (db) => {
  assert.equal(
    queryUnifiedAt(db, { search: "0x" + String(3).padStart(40, "0") }).rows[0].canonical_asset_id,
    "a003",
  );
});
check("search by name and symbol", (db) => {
  assert.equal(queryUnifiedAt(db, { search: "SAME" }).total, 1);
  assert.equal(queryUnifiedAt(db, { search: "Token 124" }).total, 1);
});
check("literal percent and SQL injection are not wildcards", (db) => {
  assert.equal(queryUnifiedAt(db, { search: "%" }).total, 0);
  assert.equal(queryUnifiedAt(db, { search: "' OR 1=1 --" }).total, 0);
});
check("market volume ascending sort", (db) => {
  assert.equal(
    queryUnifiedAt(db, { sort: "volume_24h", direction: "asc" }).rows[0].canonical_asset_id,
    "a000",
  );
});
check("daily sort null last and date priority", (db) => {
  const r = queryUnifiedAt(db, {
    dates: [
      { date: "2026-10-09", direction: "desc" },
      { date: "2026-10-10", direction: "asc" },
    ],
  });
  assert.deepEqual(
    r.rows.slice(0, 2).map((r) => r.canonical_asset_id),
    ["a001", "a003"],
  );
  assert.equal(r.dates.length, 7);
  assert.equal(r.dates[0], "2026-10-04");
});
check("daily direction filters exclude missing", (db) => {
  const r = queryUnifiedAt(db, { dailyFilters: [{ date: "2026-10-10", sign: "negative" }] });
  assert.equal(r.total, 5);
  assert.ok(r.rows.every((r) => r.history.some((h) => Number(h.daily_return) < 0)));
});
check("canonical and legacy hidden preferences applied before pagination", (db) => {
  const r = queryUnifiedAt(db, {
    hiddenKeys: ["unified:a124", "eth:0x" + String(122).padStart(40, "0")],
  });
  assert.equal(r.total, 123);
  assert.equal(r.rows[0].canonical_asset_id, "a123");
});
check("watch preferences and empty watch", (db) => {
  assert.equal(queryUnifiedAt(db, { watchKeys: [] }).total, 0);
  const r = queryUnifiedAt(db, {
    watchKeys: ["unified:a001", "base:0x" + String(3).padStart(40, "0")],
  });
  assert.equal(r.total, 2);
});
check("page clamped to available results", (db) => {
  assert.equal(queryUnifiedAt(db, { page: 10000 }).page, 3);
});
check("daily participation counts the whole filtered market before paging", (db) => {
  const result = queryUnifiedAt(db, { source: "cmc", page: 2 });
  assert.deepEqual(result.participation.find(r => r.date === "2026-10-10"),
    { date: "2026-10-10", valid: 5, positive: 0, negative: 5, missing: 57 });
  assert.deepEqual(result.participation.find(r => r.date === "2026-10-09"),
    { date: "2026-10-09", valid: 2, positive: 2, negative: 0, missing: 60 });
  assert.deepEqual(result.participation[0],
    { date: "2026-10-04", valid: 0, positive: 0, negative: 0, missing: 62 });
});
check("daily participation respects date filters and hidden preferences", (db) => {
  const result = queryUnifiedAt(db, {
    dailyFilters: [{date:"2026-10-10",sign:"negative"}], hiddenKeys:["unified:a001"],
  });
  assert.equal(result.total, 4);
  assert.deepEqual(result.participation.find(r => r.date === "2026-10-10"),
    { date: "2026-10-10", valid: 4, positive: 0, negative: 4, missing: 0 });
  assert.deepEqual(result.participation.find(r => r.date === "2026-10-09"),
    { date: "2026-10-09", valid: 1, positive: 1, negative: 0, missing: 3 });
});
check("sort injection falls back to allowlist", (db) => {
  assert.equal(queryUnifiedAt(db, { sort: "market_cap; DROP TABLE wm_unified_current" }).total, 125);
});

check("watch and hidden canonical preferences survive multi-step identity merges", (db) => {
  db.exec("INSERT INTO wm_unified_redirects VALUES('old','middle'),('middle','a001')");
  const r = queryUnifiedAt(db, { watchKeys: ["unified:old"] });
  assert.equal(r.total, 1);
  assert.equal(r.rows[0].canonical_asset_id, "a001");
  assert.deepEqual(JSON.parse(r.rows[0].preference_aliases).sort(), ["middle", "old"]);
  assert.equal(queryUnifiedAt(db, { hiddenKeys: ["unified:old"] }).total, 124);
});

check("open, invalid and future bars cannot rank finalized days", db => {
  db.exec("INSERT INTO wm_unified_daily VALUES('a124','2026-10-10',99999,'intraday','VALID'),('a123','2026-10-10',99998,'utc_finalized','LOW_BASE_PRICE'),('a122','2026-10-11',99997,'utc_finalized','VALID')");
  const r=queryUnifiedAt(db,{dates:[{date:'2026-10-10',direction:'desc'}]});
  assert.equal(r.rows[0].canonical_asset_id,'a008');
  assert.equal(r.dates[6],'2026-10-10');
  assert.equal(r.latestFinalizedDate,'2026-10-10');
  const invalid=queryUnifiedAt(db,{only:['a123']}).rows[0];
  assert.equal(invalid.history[0].daily_return,null);
  assert.equal(queryUnifiedAt(db,{only:['a124']}).rows[0].history.length,0);
});
check("new and historical-gap assets remain visible; tier and hidden-only intersect", db => {
  db.exec("UPDATE wm_unified_current SET first_seen_utc='2026-10-11T01:00:00Z',market_tier='EARLY' WHERE canonical_asset_id='a124'");
  assert.equal(queryUnifiedAt(db,{}).total,125);
  assert.equal(queryUnifiedAt(db,{tier:'NEW'}).rows[0].is_new,1);
  assert.equal(queryUnifiedAt(db,{tier:'EARLY'}).total,1);
  assert.equal(queryUnifiedAt(db,{onlyHiddenKeys:['unified:a124'],watchKeys:['unified:a124','unified:a123']}).total,1);
  assert.equal(queryUnifiedAt(db,{onlyHiddenKeys:[]}).total,0);
});
check("zero is valid; numeric ties use deterministic identity on all pages", db => {
  db.exec("UPDATE wm_unified_current SET market_cap=0");
  const r=queryUnifiedAt(db,{dates:[{date:'2026-10-10',direction:'asc'}]});
  assert.equal(r.rows[5].canonical_asset_id,'a000');
  assert.equal(r.rows[5].history[0].daily_return,0);
  assert.deepEqual(queryUnifiedAt(db,{page:2}).rows.map(x=>x.canonical_asset_id),queryUnifiedAt(db,{page:2}).rows.map(x=>x.canonical_asset_id));
});

check("daily filters are AND independently of sorting; new short histories sort their own day",db=>{
 const r=queryUnifiedAt(db,{dailyFilters:[{date:'2026-10-09',sign:'positive'},{date:'2026-10-10',sign:'negative'}],dates:[{date:'2026-10-10',direction:'asc'}]});
 assert.equal(r.total,2);assert.deepEqual(r.rows.map(x=>x.canonical_asset_id),['a003','a001']);
 assert.equal(r.rows[0].history.length,2);
});
check("same symbol on distinct contracts is not collapsed by global pagination",db=>{
 db.exec("UPDATE wm_unified_current SET symbol='SAME' WHERE canonical_asset_id IN ('a123','a124')");
 const r=queryUnifiedAt(db,{search:'SAME'});assert.equal(r.total,3);
 assert.equal(new Set(r.rows.map(x=>x.canonical_asset_id)).size,3);
});

check("Solana contract searches preserve case-sensitive identity",db=>{
 db.exec("INSERT INTO wm_unified_chain_tokens VALUES('solana','MintAddressAbC','a123'),('solana','mintaddressabc','a124')");
 assert.deepEqual(queryUnifiedAt(db,{search:'MintAddressAbC'}).rows.map(r=>r.canonical_asset_id),['a123']);
 assert.deepEqual(queryUnifiedAt(db,{search:'mintaddressabc'}).rows.map(r=>r.canonical_asset_id),['a124']);
});
