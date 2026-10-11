import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  HIDDEN_TOKENS_STORAGE_KEY,
  addHiddenToken,
  hiddenTokenKey,
  loadHiddenTokens,
  parseHiddenTokens,
  removeHiddenToken,
  writeHiddenTokens,
} from "./hidden-tokens.ts";

describe("hidden token UI state", () => {
  it("uses chain + normalized address as identity", () => {
    assert.equal(hiddenTokenKey("BASE", "0xAbC"), "base:0xabc");
    assert.notEqual(hiddenTokenKey("base", "0xabc"), hiddenTokenKey("eth", "0xabc"));
    assert.notEqual(hiddenTokenKey("sol", "SoLAddr"), hiddenTokenKey("sol", "soladdr"));
  });

  it("hides the same address on only the selected chain", () => {
    const keys = addHiddenToken([], "base", "0x123");
    assert.deepEqual(keys, ["base:0x123"]);
    assert.equal(keys.includes(hiddenTokenKey("eth", "0x123")), false);
  });

  it("deduplicates, validates and normalizes stored keys", () => {
    assert.deepEqual(
      parseHiddenTokens(JSON.stringify(["BASE:0xABC", "base:0xabc", "sol:SoLAddr", "broken", 3])),
      ["base:0xabc", "sol:SoLAddr"],
    );
    assert.deepEqual(parseHiddenTokens("not json"), []);
  });

  it("restores one token without touching another chain", () => {
    const keys = ["base:0x123", "eth:0x123"];
    assert.deepEqual(removeHiddenToken(keys, "base:0x123"), ["eth:0x123"]);
  });

  it("persists and reloads the exact storage key", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };
    writeHiddenTokens(storage, ["base:0x123", "eth:0x123"]);
    assert.equal(values.has(HIDDEN_TOKENS_STORAGE_KEY), true);
    assert.deepEqual(loadHiddenTokens(storage), ["base:0x123", "eth:0x123"]);
  });
});
