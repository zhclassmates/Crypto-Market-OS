import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  applyMarketAccessDemo,
  getAccessCategory,
  getLatestAccessEvent,
  isSafeSourceUrl,
  isScheduledAccessEvent,
  isSurpriseAccessEvent,
  matchesAccessCategory,
  sortAccessEvents,
  type MarketAccessEvent,
  type MarketAccessKind,
} from "./market-access.ts";

function event(kind: MarketAccessKind, detectedAt?: number): MarketAccessEvent {
  return {
    id: `${kind}-${detectedAt ?? "unknown"}`,
    kind,
    venue: "Test venue",
    label: "Test label",
    detectedAt,
  };
}

describe("market access event ordering", () => {
  it("handles undefined and empty event arrays", () => {
    assert.deepEqual(sortAccessEvents(undefined), []);
    assert.deepEqual(sortAccessEvents([]), []);
    assert.equal(getLatestAccessEvent(undefined), undefined);
    assert.equal(getLatestAccessEvent([]), undefined);
  });

  it("returns the latest detected event", () => {
    const older = event("BINANCE_ALPHA", 100);
    const latest = event("BINANCE_ALPHA_LIVE", 300);
    assert.equal(getLatestAccessEvent([older, latest, event("BINANCE_SPOT", 200)]), latest);
  });

  it("sorts detectedAt descending without mutating input", () => {
    const input = [event("BINANCE_ALPHA", 100), event("BINANCE_SPOT", 300), event("ROBINHOOD", 200)];
    assert.deepEqual(sortAccessEvents(input).map((item) => item.detectedAt), [300, 200, 100]);
    assert.deepEqual(input.map((item) => item.detectedAt), [100, 300, 200]);
  });

  it("places events without detectedAt after timed events", () => {
    const unknown = event("OTHER");
    assert.deepEqual(sortAccessEvents([unknown, event("ROBINHOOD", 100)]).map((item) => item.kind), ["ROBINHOOD", "OTHER"]);
  });
});

describe("Alpha Live factual status", () => {
  it("marks only unscheduled Alpha Live as Surprise", () => {
    assert.equal(isSurpriseAccessEvent({ ...event("BINANCE_ALPHA_LIVE"), isScheduled: false }), true);
    assert.equal(isSurpriseAccessEvent({ ...event("BINANCE_ALPHA_LIVE"), isScheduled: true }), false);
    assert.equal(isSurpriseAccessEvent({ ...event("BINANCE_ALPHA"), isScheduled: false }), false);
  });

  it("marks scheduled Alpha Live as Scheduled", () => {
    assert.equal(isScheduledAccessEvent({ ...event("BINANCE_ALPHA_LIVE"), isScheduled: true }), true);
    assert.equal(isScheduledAccessEvent({ ...event("BINANCE_ALPHA_LIVE"), isScheduled: false }), false);
  });
});

describe("market access categories", () => {
  it("matches all Binance Wallet event kinds", () => {
    for (const kind of ["BINANCE_WALLET_ASSET", "BINANCE_WALLET_CONTRACT", "BINANCE_WALLET_TRADABLE"] as const) {
      assert.equal(matchesAccessCategory(event(kind), "wallet"), true);
    }
  });

  it("keeps Alpha and Alpha Live separate", () => {
    assert.equal(matchesAccessCategory(event("BINANCE_ALPHA"), "alpha"), true);
    assert.equal(matchesAccessCategory(event("BINANCE_ALPHA"), "alpha-live"), false);
    assert.equal(matchesAccessCategory(event("BINANCE_ALPHA_LIVE"), "alpha-live"), true);
    assert.equal(matchesAccessCategory(event("BINANCE_ALPHA_LIVE"), "alpha"), false);
  });

  it("matches Binance Futures", () => {
    assert.equal(matchesAccessCategory(event("BINANCE_FUTURES"), "futures"), true);
  });

  it("keeps Spot exclusive to Binance Spot", () => {
    assert.equal(matchesAccessCategory(event("BINANCE_SPOT"), "spot"), true);
    assert.equal(matchesAccessCategory(event("COINBASE_SPOT"), "spot"), false);
  });

  it("aggregates Coinbase Spot and Roadmap in Coinbase", () => {
    assert.equal(matchesAccessCategory(event("COINBASE_SPOT"), "coinbase"), true);
    assert.equal(matchesAccessCategory(event("COINBASE_ROADMAP"), "coinbase"), true);
    assert.equal(matchesAccessCategory(event("BINANCE_SPOT"), "coinbase"), false);
  });

  it("matches Pre-market only to Binance Pre-market", () => {
    assert.equal(matchesAccessCategory(event("BINANCE_PRE_MARKET"), "pre-market"), true);
    assert.equal(matchesAccessCategory(event("BINANCE_SPOT"), "pre-market"), false);
  });

  it("matches all Upbit quote markets", () => {
    for (const kind of ["UPBIT_BTC", "UPBIT_USDT", "UPBIT_KRW"] as const) {
      assert.equal(matchesAccessCategory(event(kind), "upbit"), true);
    }
  });

  it("assigns every concrete kind one primary category and prevents Spot/Coinbase overlap", () => {
    const expected = new Map<MarketAccessKind, string>([
      ["BINANCE_WALLET_ASSET", "wallet"],
      ["BINANCE_WALLET_CONTRACT", "wallet"],
      ["BINANCE_WALLET_TRADABLE", "wallet"],
      ["BINANCE_ALPHA", "alpha"],
      ["BINANCE_ALPHA_LIVE", "alpha-live"],
      ["BINANCE_FUTURES", "futures"],
      ["BINANCE_SPOT", "spot"],
      ["BINANCE_PRE_MARKET", "pre-market"],
      ["COINBASE_ROADMAP", "roadmap"],
      ["COINBASE_SPOT", "coinbase"],
      ["UPBIT_BTC", "upbit"],
      ["UPBIT_USDT", "upbit"],
      ["UPBIT_KRW", "upbit"],
      ["ROBINHOOD", "robinhood"],
      ["OTHER", "all"],
    ]);
    for (const [kind, category] of expected) {
      assert.equal(getAccessCategory(event(kind)), category);
    }
    assert.equal(matchesAccessCategory(event("BINANCE_SPOT"), "coinbase"), false);
    assert.equal(matchesAccessCategory(event("COINBASE_SPOT"), "spot"), false);
  });
});

describe("market access source URL safety", () => {
  it("accepts http URLs", () => {
    assert.equal(isSafeSourceUrl("http://example.com/announcement"), true);
  });

  it("accepts https URLs", () => {
    assert.equal(isSafeSourceUrl("https://example.com/announcement"), true);
  });

  it("rejects javascript URLs", () => {
    assert.equal(isSafeSourceUrl("javascript:alert(1)"), false);
  });

  it("rejects data URLs", () => {
    assert.equal(isSafeSourceUrl("data:text/html,unsafe"), false);
  });
});

describe("applyMarketAccessDemo", () => {
  it("binds only the exact chain + address and never substitutes another token", () => {
    const tokens: { chain: string; address: string; marketAccess?: MarketAccessEvent[] }[] = [
      { chain: "base", address: "0x0000000000000000000000000000000000000001" },
      { chain: "eth", address: "0x6e252dfa99884c6f613f31387798b55ed95150f6" },
      { chain: "base", address: "0x6e252dfa99884c6f613f31387798b55ed95150f6" },
    ];
    const out = applyMarketAccessDemo(tokens, 1_800_000_000);
    assert.equal(out[0].marketAccess, undefined);
    assert.equal(out[1].marketAccess, undefined);
    assert.equal(out[2].marketAccess?.[0]?.kind, "BINANCE_FUTURES");
  });
});
