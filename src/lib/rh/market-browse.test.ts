import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { compareNewness, mergeSearchHits, type NewnessSortable } from "./market-browse.ts";
import { compareDailyReturn, type DailyReturnMap } from "./daily-filter.ts";

const tok = (id: string, newnessAt: number | null, volume24h = "", liquidity: number | null = null) => ({
  id,
  newnessAt,
  volume24h,
  liquidityNum: liquidity,
  liquidity: liquidity == null ? "" : String(liquidity),
});
const ids = (rows: { id: string }[]) => rows.map((r) => r.id);

describe("全市场 default newness sort", () => {
  it("newest first, then 24h volume, then liquidity; missing values last at every level", () => {
    const rows = [
      tok("old", 100, "999999", 1e9),
      tok("new-lowvol", 300, "10", 5),
      tok("new-highvol", 300, "5000", 1),
      tok("new-samevol-deep", 300, "5000", 900),
      tok("mid", 200),
      tok("no-time", null, "1e12", 1e12),
      tok("new-novol", 300, "", 7),
    ];
    assert.deepEqual(ids([...rows].sort(compareNewness)), [
      "new-samevol-deep",
      "new-highvol",
      "new-lowvol",
      "new-novol",
      "mid",
      "old",
      "no-time",
    ]);
  });

  it("does not require any daily history or 7D value", () => {
    const short: NewnessSortable & { changeNd: null; dailyReturns: DailyReturnMap } = {
      ...tok("short", 500), changeNd: null, dailyReturns: {},
    };
    assert.ok(compareNewness(short, tok("older-full", 100)) < 0);
  });
});

describe("date sort on 全市场 rows", () => {
  const rows: { id: string; r: DailyReturnMap }[] = [
    { id: "a", r: { d: 0.2 } }, { id: "b", r: { d: 5 } }, { id: "c", r: {} },
    { id: "d", r: { d: 0 } }, { id: "e", r: { d: -0.05 } }, { id: "f", r: { d: -0.8 } }, { id: "g", r: { d: null } },
  ];
  it("↑ = DESC, missing last", () => {
    assert.deepEqual(ids([...rows].sort((x, y) => compareDailyReturn(x.r, y.r, { date: "d", dir: "desc" }))), ["b", "a", "d", "e", "f", "c", "g"]);
  });
  it("↓ = ASC, missing still last", () => {
    assert.deepEqual(ids([...rows].sort((x, y) => compareDailyReturn(x.r, y.r, { date: "d", dir: "asc" }))), ["f", "e", "d", "a", "b", "c", "g"]);
  });
});

describe("full-registry search merge", () => {
  const base = [{ chain: "eth", address: "0xa", v: "list" }, { chain: "sol", address: "S1", v: "list" }];
  it("appends hits outside the browse set", () => {
    const merged = mergeSearchHits(base, [{ chain: "eth", address: "0xz", v: "search" }]);
    assert.deepEqual(merged.map((t) => `${t.chain}:${t.address}`), ["eth:0xa", "sol:S1", "eth:0xz"]);
  });
  it("keeps the list copy when the hit is already present", () => {
    const merged = mergeSearchHits(base, [{ chain: "eth", address: "0xa", v: "search" }]);
    assert.equal(merged, base);
  });
  it("same address on another chain is a different token", () => {
    const merged = mergeSearchHits(base, [{ chain: "base", address: "0xa", v: "search" }]);
    assert.deepEqual(merged.map((t) => `${t.chain}:${t.address}`), ["eth:0xa", "sol:S1", "base:0xa"]);
  });
});
