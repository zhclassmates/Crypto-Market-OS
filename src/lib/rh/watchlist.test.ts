import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { parseWatchlist, toggleWatchItem, watchKey } from "./watchlist.ts";

describe("watchlist", () => {
  it("keeps chain and address apart when symbols match", () => {
    const now = 1_700_000_000;
    let items = toggleWatchItem([], { chain: "sol", address: "mintA", symbol: "SI", name: "one" }, now);
    items = toggleWatchItem(items, { chain: "eth", address: "0xabc", symbol: "SI", name: "two" }, now + 1);
    assert.deepEqual(items.map((w) => watchKey(w.chain, w.address)), ["sol:mintA", "eth:0xabc"]);
    assert.equal(items[1].addedAt, now + 1);
  });

  it("removes the same chain and address and leaves the rest", () => {
    const base = [
      { chain: "sol", address: "mintA", symbol: "SI", name: null, addedAt: 1 },
      { chain: "sol", address: "mintB", symbol: "SI", name: null, addedAt: 2 },
    ];
    const next = toggleWatchItem(base, { chain: "sol", address: "mintA", symbol: "SI", name: null }, 3);
    assert.deepEqual(next.map((w) => w.address), ["mintB"]);
  });

  it("drops broken rows and duplicate keys", () => {
    const raw = JSON.stringify([
      { chain: "sol", address: "mintA", symbol: "A", name: "n", addedAt: 5 },
      { chain: "sol", address: "mintA", symbol: "dup", addedAt: 9 },
      { chain: "", address: "x" },
      { symbol: "no-address" },
      "nope",
    ]);
    const items = parseWatchlist(raw);
    assert.equal(items.length, 1);
    assert.equal(items[0].address, "mintA");
    assert.equal(items[0].addedAt, 5);
  });

  it("returns an empty list for bad json", () => {
    assert.deepEqual(parseWatchlist(null), []);
    assert.deepEqual(parseWatchlist("{"), []);
    assert.deepEqual(parseWatchlist("{\"chain\":\"sol\"}"), []);
  });
});
