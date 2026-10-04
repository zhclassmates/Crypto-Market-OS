import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { describe, it } from "node:test";
import { DAY_SEC } from "./streak.ts";
import { readMarketInclusionStats, readMarketTierStats } from "./market-stats.ts";

const DAY0 = 1_790_000_000 - (1_790_000_000 % DAY_SEC);

describe("market inclusion stats", () => {
  it("deduplicates total_tokens by chain and contract address", () => {
    const db = new DatabaseSync(":memory:");
    db.exec("CREATE TABLE token_registry(chain TEXT, address TEXT, first_seen_at INTEGER, updated_at INTEGER)");
    const insert = db.prepare("INSERT INTO token_registry VALUES(?,?,?,?)");
    insert.run("sol", "A", DAY0 - 10, DAY0 + 100);
    insert.run("sol", "A", DAY0 + 100, DAY0 + 100);
    insert.run("eth", "A", DAY0 + 100, DAY0 + 100);
    insert.run("sol", "B", DAY0 + 200, DAY0 + 200);

    assert.equal(readMarketInclusionStats(db, DAY0 + 300).totalTokens, 3);
    db.close();
  });

  it("counts today_new_tokens from the earliest first_seen_at only", () => {
    const db = new DatabaseSync(":memory:");
    db.exec("CREATE TABLE token_registry(chain TEXT, address TEXT, first_seen_at INTEGER, updated_at INTEGER)");
    const insert = db.prepare("INSERT INTO token_registry VALUES(?,?,?,?)");
    insert.run("sol", "OLD", DAY0 - DAY_SEC, DAY0 + 500);
    insert.run("sol", "OLD", DAY0 + 100, DAY0 + 500);
    insert.run("sol", "NEW", DAY0, DAY0 + 500);
    insert.run("eth", "NEW", DAY0 + DAY_SEC - 1, DAY0 + 500);
    insert.run("base", "FUTURE", DAY0 + DAY_SEC, DAY0 + DAY_SEC);
    insert.run("base", "UNKNOWN", null, DAY0 + 500);

    const stats = readMarketInclusionStats(db, DAY0 + 600);
    assert.equal(stats.todayNewTokens, 2);
    db.close();
  });
});

describe("market tier stats", () => {
  it("splits registry into MAIN / EARLY / IGNORE by the K-line gate", () => {
    const db = new DatabaseSync(":memory:");
    db.exec(`CREATE TABLE token_registry(chain TEXT, address TEXT, first_seen_at INTEGER,
      first_liquidity_50k_at INTEGER, kline_backfilled_at INTEGER)`);
    db.exec("CREATE TABLE token_snapshot(chain TEXT, address TEXT, liquidity TEXT, liquidity_num REAL)");
    const reg = db.prepare("INSERT INTO token_registry VALUES(?,?,?,?,?)");
    const snap = db.prepare("INSERT INTO token_snapshot VALUES(?,?,?,?)");
    reg.run("sol", "MAIN_NOW", DAY0, null, null); snap.run("sol", "MAIN_NOW", "60000", 60_000);
    reg.run("sol", "MAIN_HIST", DAY0, DAY0, DAY0); snap.run("sol", "MAIN_HIST", "30000", 30_000);
    reg.run("sol", "EARLY_LO", DAY0, null, null); snap.run("sol", "EARLY_LO", "20000", 20_000);
    reg.run("sol", "EARLY_HI", DAY0, null, null); snap.run("sol", "EARLY_HI", "49999", null);
    reg.run("sol", "IGN", DAY0, null, null); snap.run("sol", "IGN", "19999", 19_999);
    reg.run("sol", "ZERO", DAY0, null, null); snap.run("sol", "ZERO", "0", 0);
    reg.run("sol", "NOSNAP", DAY0, null, null);

    assert.deepEqual(readMarketTierStats(db), { mainTokens: 2, earlyTokens: 2, ignoreTokens: 3 });
    db.close();
  });
});
