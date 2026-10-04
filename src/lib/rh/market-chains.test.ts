import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import {
  ACCESS_CHAIN_TO_MARKET,
  MARKET_CHAINS,
  MARKET_CHAIN_LABEL,
  MARKET_CHAIN_TABS,
  MARKET_TO_ACCESS_CHAINS,
} from "./market-chains.ts";
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

describe("access radar chain mapping", () => {
  it("maps every market chain to at least one Access Radar chain name", () => {
    for (const id of MARKET_CHAINS) {
      assert.ok(MARKET_TO_ACCESS_CHAINS[id]?.length, `${id} has no access mapping`);
      for (const name of MARKET_TO_ACCESS_CHAINS[id]) assert.equal(ACCESS_CHAIN_TO_MARKET[name], id);
    }
  });

  it("maps canonical and alias names to market keys", () => {
    assert.equal(ACCESS_CHAIN_TO_MARKET.solana, "sol");
    assert.equal(ACCESS_CHAIN_TO_MARKET.sol, "sol");
    assert.equal(ACCESS_CHAIN_TO_MARKET.ethereum, "eth");
    assert.equal(ACCESS_CHAIN_TO_MARKET.eth, "eth");
    assert.equal(ACCESS_CHAIN_TO_MARKET.bsc, "bsc");
    assert.equal(ACCESS_CHAIN_TO_MARKET.base, "base");
    assert.equal(ACCESS_CHAIN_TO_MARKET.robinhood, "robinhood");
    assert.equal(ACCESS_CHAIN_TO_MARKET.arbitrum, undefined);
  });

  it("uses the canonical names emitted by access_radar/adapters/chains.py first", () => {
    const src = readFileSync(new URL("../../../access_radar/adapters/chains.py", import.meta.url), "utf8");
    for (const id of MARKET_CHAINS) {
      const canonical = MARKET_TO_ACCESS_CHAINS[id][0];
      assert.match(src, new RegExp(`^\\s*"${canonical}": \\(`, "m"), `${canonical} is not canonical in chains.py`);
    }
  });
});
