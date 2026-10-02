import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  DAY_SEC,
  DEFAULT_DAYS,
  PRESET_DAYS,
  anchorDeviation,
  closedBars,
  compareStreakThenReturn,
  displayCreated,
  fmtRelativeAge,
  formalStreakEligible,
  klineIsStale,
  parseDays,
  returnOverClosedCandles,
  streakBoardEligible,
  streakMetrics,
  type DailyBar,
} from "./streak.ts";

const DAY0 = 1_790_000_000 - (1_790_000_000 % DAY_SEC);

function bar(dayIndex: number, close: number, high = close): DailyBar {
  return { ts: DAY0 + dayIndex * DAY_SEC, close, high };
}

describe("streakMetrics", () => {
  const now = DAY0 + 4 * DAY_SEC + 3600;
  const fetched = DAY0 + 4 * DAY_SEC + 10;

  it("uses the close before the streak, not the live price", () => {
    const bars = [bar(0, 1, 1), bar(1, 1.2, 1.3), bar(2, 1.5, 1.6), bar(3, 1.8, 2)];
    const m = streakMetrics(bars, now, fetched, null);
    assert.equal(m.streak, 3);
    assert.ok(Math.abs((m.streakReturn ?? 0) - 0.8) < 1e-12);
    assert.ok(Math.abs((m.streakDrawdown ?? 0) - (1 - 1.8 / 2)) < 1e-12);
    assert.ok(Math.abs((m.change1d ?? 0) - (1.8 / 1.5 - 1)) < 1e-12);
  });

  it("stops when a close does not make a higher close", () => {
    const bars = [bar(0, 1), bar(1, 1.4), bar(2, 1.2), bar(3, 1.5)];
    const m = streakMetrics(bars, now, fetched, null);
    assert.equal(m.streak, 1);
    assert.ok(Math.abs((m.streakReturn ?? 0) - (1.5 / 1.2 - 1)) < 1e-12);
  });

  it("counts only the adjacent up tail, not up-days inside a window", () => {
    const later = DAY0 + 6 * DAY_SEC + 3600;
    const fetchedLater = DAY0 + 6 * DAY_SEC + 10;
    const bars = [bar(0, 100), bar(1, 105), bar(2, 110), bar(3, 108), bar(4, 112), bar(5, 118)];
    const m = streakMetrics(bars, later, fetchedLater, null);
    assert.equal(m.streak, 2);
    assert.ok(Math.abs((m.change1d ?? 0) - (118 / 112 - 1)) < 1e-12);
  });

  it("does not count the candle that has not closed", () => {
    const bars = [bar(0, 1), bar(1, 2), bar(4, 50, 80)];
    const m = streakMetrics(bars, now, fetched, null);
    assert.equal(m.streak, 1);
    assert.equal(m.closedCount, 2);
    assert.ok(Math.abs((m.streakReturn ?? 0) - 1) < 1e-12);
  });

  it("caps a one-candle token below a fake multi-day streak", () => {
    const created = DAY0 + 3 * DAY_SEC + 1000;
    const bars = [bar(0, 0.001, 0.002), bar(3, 1, 2), bar(4, 20, 40)];
    const m = streakMetrics(bars, now, fetched, created);
    assert.equal(m.closedCount, 1);
    assert.equal(m.streak, 0);
    assert.equal(m.streakReturn, null);
    assert.equal(m.change1d, null);
  });

  it("drops a candle fetched before that day closed", () => {
    const bars = [bar(0, 1), bar(1, 2), bar(2, 3)];
    const fetchedEarly = DAY0 + 2 * DAY_SEC - 10;
    const m = streakMetrics(bars, now, fetchedEarly, null);
    assert.equal(m.closedCount, 1);
    assert.equal(m.streak, 0);
    assert.equal(klineIsStale(now, fetchedEarly), true);
    assert.equal(klineIsStale(now, fetched), false);
  });

  it("returns nothing when the daily fetch time is unknown", () => {
    const m = streakMetrics([bar(0, 1), bar(1, 2)], now, null, null);
    assert.equal(m.streak, 0);
    assert.equal(m.closedCount, 0);
  });

  it("stops when the previous calendar day is missing", () => {
    const bars = [bar(0, 1), bar(1, 1.2), bar(3, 2)];
    const m = streakMetrics(bars, now, fetched, null);
    assert.equal(m.closedCount, 3);
    assert.equal(m.streak, 0);
    assert.equal(m.streakReturn, null);
    assert.equal(m.change1d, null);
  });

  it("keeps only the adjacent tail after a hole", () => {
    const bars = [bar(0, 1), bar(2, 1.1, 1.2), bar(3, 1.4, 1.5)];
    const m = streakMetrics(bars, now, fetched, null);
    assert.equal(m.streak, 1);
    assert.ok(Math.abs((m.streakReturn ?? 0) - (1.4 / 1.1 - 1)) < 1e-12);
    assert.ok(Math.abs((m.change1d ?? 0) - (1.4 / 1.1 - 1)) < 1e-12);
    assert.ok(m.streak <= m.closedCount);
  });

  it("drawdown above 40% stays a streak", () => {
    const bars = [bar(0, 4), bar(1, 5, 5), bar(2, 6, 20), bar(3, 7, 8)];
    const m = streakMetrics(bars, now, fetched, null);
    assert.equal(m.streak, 3);
    assert.ok((m.streakDrawdown ?? 0) > 0.4);
  });
});

describe("board rules", () => {
  it("sorts by streak days before cumulative return", () => {
    const rows = [
      { streak: 2, streakReturn: 3 },
      { streak: 3, streakReturn: 0.2 },
      { streak: 3, streakReturn: 0.5 },
    ];
    const sorted = [...rows].sort((a, b) => compareStreakThenReturn(a, b));
    assert.deepEqual(sorted.map((r) => r.streakReturn), [0.5, 0.2, 3]);
  });

  it("liquidity is a gate, not a score", () => {
    assert.equal(streakBoardEligible(50_000), true);
    assert.equal(streakBoardEligible(49_999), false);
    assert.equal(streakBoardEligible(116_500), true);
    assert.equal(streakBoardEligible("116500"), true);
  });

  it("formal board also requires liquidity age within 300s", () => {
    assert.equal(formalStreakEligible(100_000, 30), true);
    assert.equal(formalStreakEligible(100_000, 1000), false);
    assert.equal(formalStreakEligible(30_000, 20), false);
    assert.equal(formalStreakEligible(100_000, null), false);
  });

  it("return over N closed candles is null when a day is missing", () => {
    const closed = [
      { ts: 0, close: 10 },
      { ts: DAY_SEC, close: 12 },
      { ts: 2 * DAY_SEC, close: 15 },
      { ts: 4 * DAY_SEC, close: 20 },
    ];
    assert.equal(returnOverClosedCandles(closed.slice(0, 3), 2), 15 / 10 - 1);
    assert.equal(returnOverClosedCandles(closed, 2), null);
    assert.notEqual(returnOverClosedCandles(closed, 2), 0);
  });

  it("N-day cumulative is a close ratio, not a sum of daily percents", () => {
    const closed = [
      { ts: 0, close: 100 },
      { ts: DAY_SEC, close: 110 },
      { ts: 2 * DAY_SEC, close: 121 },
      { ts: 3 * DAY_SEC, close: 108.9 },
    ];
    assert.ok(Math.abs((returnOverClosedCandles(closed, 1) ?? 0) - (108.9 / 121 - 1)) < 1e-12);
    assert.ok(Math.abs((returnOverClosedCandles(closed, 3) ?? 0) - (108.9 / 100 - 1)) < 1e-12);
    assert.equal(returnOverClosedCandles(closed, 7), null);
  });

  it("parseDays falls back to 7 and keeps one default", () => {
    assert.equal(DEFAULT_DAYS, 7);
    assert.deepEqual([...PRESET_DAYS], [1, 2, 3, 5, 7, 10, 14, 30]);
    assert.equal(parseDays(3), 3);
    assert.equal(parseDays(10), 10);
    assert.equal(parseDays(undefined), 7);
    assert.equal(parseDays("abc"), 7);
    assert.equal(parseDays(0), 7);
    assert.equal(parseDays(-1), 7);
    assert.equal(parseDays(999), 7);
    assert.equal(parseDays(NaN), 7);
  });

  it("created display never falls through to first-seen", () => {
    assert.deepEqual(displayCreated(10, 20), { at: 10, source: "token" });
    assert.deepEqual(displayCreated(null, 20), { at: 20, source: "pair" });
    assert.deepEqual(displayCreated(null, null), { at: null, source: null });
  });

  it("formats age the way the board shows it", () => {
    const now = 1_000_000;
    assert.equal(fmtRelativeAge(now, now - 23 * 60), "23m");
    assert.equal(fmtRelativeAge(now, now - 6 * 3600), "6h");
    assert.equal(fmtRelativeAge(now, now - 2 * DAY_SEC), "2d");
    assert.equal(fmtRelativeAge(now, now - 31 * DAY_SEC), "31d");
  });

  it("anchor deviation is pool over anchor, and drops non-positive prices", () => {
    assert.ok(Math.abs((anchorDeviation(100.7, 100) ?? 0) - 0.007) < 1e-12);
    assert.equal(anchorDeviation(null, 100), null);
  });

  it("ignores bars that ended before the token or the pair existed", () => {
    const created = DAY0 + 2 * DAY_SEC + 10;
    const kept = closedBars([bar(0, 1), bar(1, 2), bar(2, 3)], DAY0 + 4 * DAY_SEC, DAY0 + 4 * DAY_SEC, created);
    assert.deepEqual(kept.map((b) => b.close), [3]);
  });
});
