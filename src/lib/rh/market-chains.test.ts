import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { MARKET_CHAINS, MARKET_CHAIN_LABEL, MARKET_CHAIN_TABS } from "./market-chains.ts";
import { matchesDailyFilters } from "./daily-filter.ts";

describe("market chain configuration", () => {
  it("keeps the four existing chains and adds BSC once", () => {
    assert.deepEqual(MARKET_CHAINS, ["sol", "robinhood", "base", "eth", "bsc"]);
    assert.equal(new Set(MARKET_CHAINS).size, 5);
  });

  it("drives frontend tabs and labels from the shared configuration", () => {
    assert.deepEqual(MARKET_CHAIN_TABS, ["all", "sol", "robinhood", "base", "eth", "bsc"]);
    assert.equal(MARKET_CHAIN_LABEL.bsc, "BSC");
  });

  it("applies the existing finalized-date AND filter to BSC rows", () => {
    const token = {
      chain: "bsc",
      dailyReturns: { "2026-09-26": 0.05, "2026-09-27": -0.02, "2026-09-28": 0.03 },
    };
    assert.equal(
      token.chain === "bsc" && matchesDailyFilters(token.dailyReturns, {
        "2026-09-26": "UP",
        "2026-09-27": "DOWN",
        "2026-09-28": "UP",
      }),
      true,
    );
    assert.equal(
      matchesDailyFilters(token.dailyReturns, {
        "2026-09-26": "UP",
        "2026-09-27": "UP",
      }),
      false,
    );
  });
});
