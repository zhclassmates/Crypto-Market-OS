import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { LEGACY_WATCH_STORAGE_KEY, WATCH_STORAGE_KEY, loadWatchlist, parseWatchlist, toggleWatchItem, watchKey, writeWatchlist } from "./watchlist.ts";

describe("watchlist", () => {
  it("keeps chain and address apart when symbols match", () => {
    const now = 1_700_000_000;
    let items = toggleWatchItem([], { chain: "sol", address: "mintA", symbol: "SI", name: "one" }, now);
    items = toggleWatchItem(items, { chain: "eth", address: "0xabc", symbol: "SI", name: "two" }, now + 1);
    assert.deepEqual(items.map((w) => watchKey(w.chain, w.address)), ["sol:minta", "eth:0xabc"]);
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

  it("keeps the same address on two chains as two separate entries", () => {
    let items = toggleWatchItem([], { chain: "eth", address: "0xAbC", symbol: "X", name: null }, 1);
    items = toggleWatchItem(items, { chain: "base", address: "0xabc", symbol: "X", name: null }, 2);
    assert.equal(items.length, 2);
    items = toggleWatchItem(items, { chain: "eth", address: "0xabc", symbol: "X", name: null }, 3);
    assert.deepEqual(items.map((w) => w.chain), ["base"]);
  });

  it("persists under market_watchlist_v1 and migrates the legacy key once", () => {
    const store = new Map<string, string>();
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
    store.set(LEGACY_WATCH_STORAGE_KEY, JSON.stringify([{ chain: "sol", address: "old", addedAt: 1 }]));
    assert.equal(WATCH_STORAGE_KEY, "market_watchlist_v1");
    assert.deepEqual(loadWatchlist(storage).map((w) => w.address), ["old"]);
    writeWatchlist(storage, []);
    assert.deepEqual(loadWatchlist(storage), []);
  });
});
