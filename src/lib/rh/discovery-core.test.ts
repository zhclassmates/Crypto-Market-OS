import { test } from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { buildDiscovery, buildTokenDetail } from "./discovery-core.ts";
import type { AlertRule } from "./alerts.ts";

const D = 86400;
const NOW = 100 * D + 12 * 3600;

function fixture(): DatabaseSync {
  const db = new DatabaseSync(":memory:");
  db.exec(`
    CREATE TABLE tokens(chain TEXT, address TEXT, symbol TEXT, name TEXT, creation_ts INTEGER, logo TEXT,
      token_created_at INTEGER, pair_created_at INTEGER, first_seen_at INTEGER, kline_fetched_at INTEGER);
    CREATE TABLE token_snapshot(chain TEXT, address TEXT, ts INTEGER, price TEXT, volume_24h TEXT, liquidity TEXT,
      market_cap TEXT, pc_24h TEXT, pc_24h_source TEXT, holders INTEGER, swaps INTEGER, swaps_source TEXT,
      swaps_updated_at INTEGER, buys_24h INTEGER, sells_24h INTEGER, pc_1h TEXT,
      security_renounced_mint INTEGER, security_renounced_freeze_account INTEGER);
    CREATE TABLE discovery_event(id INTEGER PRIMARY KEY, chain TEXT, address TEXT, source TEXT, source_variant TEXT,
      seen_at INTEGER, time_bucket INTEGER, liquidity REAL, price REAL, market_cap REAL, rank INTEGER, metadata_json TEXT);
    CREATE TABLE daily_kline(chain TEXT, address TEXT, ts INTEGER, open TEXT, high TEXT, low TEXT, close TEXT,
      volume TEXT, amount TEXT, fetched_at INTEGER, finalized_at INTEGER);
  `);
  const tok = db.prepare("INSERT INTO tokens(chain,address,symbol,token_created_at) VALUES(?,?,?,?)");
  tok.run("sol", "HOT", "HOT", 80 * D);
  tok.run("eth", "ZERO", "ZERO", 80 * D);
  const snap = db.prepare(
    `INSERT INTO token_snapshot(chain,address,ts,price,volume_24h,market_cap,pc_24h,pc_24h_source,holders,swaps,
      swaps_source,swaps_updated_at,buys_24h,sells_24h,pc_1h,security_renounced_mint,security_renounced_freeze_account)
     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
  );
  snap.run("sol", "HOT", NOW, "1.5", "600", "1000", "24", "trending", 50, 40, "trending", NOW, 30, 10, "5", 1, 0);
  // 真实 0 必须保留为 0；pc_24h 来自 hot（窗口未确认）不能当 24h
  snap.run("eth", "ZERO", NOW, "2", "0", "1000", "10", "hot", 0, 0, "trenches", NOW, 0, 0, "0", 0, 0);
  const ev = db.prepare(
    "INSERT INTO discovery_event(chain,address,source,source_variant,seen_at,rank,metadata_json) VALUES(?,?,?,?,?,?,?)",
  );
  ev.run("sol", "HOT", "trending", "24h", NOW - 60, 5, JSON.stringify({ buys: 30, sells: 10, swaps: 40, volume: 600 }));
  ev.run("sol", "HOT", "trending", "24h", NOW - 3600, 40, JSON.stringify({ buys: 15, sells: 10, swaps: 25, volume: 300 }));
  ev.run("sol", "HOT", "signal", "7", NOW - 300, null, JSON.stringify({ trigger_at: NOW - 400, trigger_mc: 900 }));
  ev.run("eth", "ZERO", "trenches", "completed", NOW - 60, null, JSON.stringify({ buys_24h: 0, sells_24h: 0, swaps_24h: 0, volume_24h: 0 }));
  ev.run("eth", "OLD", "trending", "24h", NOW - 5 * 3600, 1, "{}");
  const k = db.prepare("INSERT INTO daily_kline(chain,address,ts,open,high,low,close,volume,amount,fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?)");
  for (let i = 0; i < 9; i++) {
    const ts = (91 + i) * D;
    const close = i === 8 ? 3 : 1;
    // 每根都在收盘后抓取 → FINALIZED；最后一根 volume 是之前均值的 4 倍
    k.run("sol", "HOT", ts, "1", String(close), "1", String(close), i === 8 ? "40" : "10", null, ts + D + 60);
  }
  // 今天的 OPEN bar 不参与
  k.run("sol", "HOT", 100 * D, "3", "99", "3", "99", "999999", null, NOW);
  // 日历已收盘但没有观测证明 → PROVISIONAL，不得被当成已定稿
  k.run("eth", "ZERO", 99 * D, "1", "1", "1", "1", "5", null, 99 * D + 100);
  return db;
}

const RULES: AlertRule[] = [
  { id: "buys", field: "buysAccel1h", op: ">=", threshold: 1.5, enabled: true, chain: null },
  { id: "zero", field: "buys24h", op: "<=", threshold: 0, enabled: true, chain: null },
  { id: "pc24", field: "pc24h", op: ">=", threshold: 0, enabled: true, chain: null },
];

test("buildDiscovery: universe, READY fields, derived metrics and alerts", () => {
  const db = fixture();
  const r = buildDiscovery(db, NOW, RULES);
  assert.deepEqual(r.rows.map((x) => x.address).sort(), ["HOT", "ZERO"]); // OLD 超出 30 分钟窗口
  const hot = r.rows.find((x) => x.address === "HOT")!;
  assert.equal(hot.price, 1.5);
  assert.equal(hot.pc24h, 24);
  assert.equal(hot.pcInterval, "24h");
  assert.equal(hot.trendingRank, 5);
  assert.equal(hot.trendingRankContext, "trending/24h");
  assert.equal(hot.signalTriggerAt, NOW - 400);
  assert.equal(hot.signalTriggerMc, 900);
  assert.equal(hot.solMintAuthority, "RENOUNCED");
  assert.equal(hot.solFreezeAuthority, "NOT_RENOUNCED");
  assert.equal(hot.derived.buysAccel1h, 2);
  assert.equal(hot.derived.swapsAccel1h, 1.6);
  assert.equal(hot.derived.volumeAccel1h, 2);
  assert.equal(hot.derived.trendingRankMove1h, 35);
  assert.equal(hot.derived.buySellRatio, 0.75);
  assert.equal(hot.derived.priceAccel, 4);
  assert.equal(hot.derived.volumeToFdv, 0.6);
  assert.equal(hot.derived.dailyVolumeAccel, 4);
  assert.equal(hot.derived.breakout7d, true);
  assert.equal(hot.score.candidate, true);

  const zero = r.rows.find((x) => x.address === "ZERO")!;
  assert.equal(zero.buys24h, 0);
  assert.equal(zero.swaps24h, 0);
  assert.equal(zero.volume24h, 0);
  assert.equal(zero.pc1h, 0);
  assert.equal(zero.holders, 0);
  assert.equal(zero.pc24h, null); // hot 来源窗口未确认
  assert.equal(zero.pcRaw, 10);
  assert.equal(zero.solMintAuthority, "NOT_APPLICABLE");
  assert.equal(zero.derived.buySellRatio, null);
  assert.equal(zero.derived.volumeToFdv, 0);
  assert.equal(zero.derived.dailyVolumeAccel, null);
  assert.equal(zero.lastDailyStatus, "PROVISIONAL");

  const keys = r.alerts.map((a) => a.key).sort();
  assert.deepEqual(keys, ["buys|sol:HOT", "pc24|sol:HOT", "zero|eth:ZERO"]);
});

test("buildTokenDetail: candles keep status, history and signals; unknown token → null", () => {
  const db = fixture();
  const d = buildTokenDetail(db, "sol", "HOT", NOW)!;
  assert.equal(d.row.symbol, "HOT");
  assert.equal(d.candles.filter((c) => c.status === "FINALIZED").length, 9);
  assert.equal(d.candles.at(-1)!.status, "OPEN");
  assert.equal(d.candles.at(-1)!.volume, 999999);
  assert.equal(d.rankHistory.length, 2);
  assert.equal(d.signals[0]!.triggerMc, 900);
  assert.equal(buildTokenDetail(db, "sol", "NOPE", NOW), null);
});
