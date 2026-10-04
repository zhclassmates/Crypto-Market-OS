import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  DAY_SEC,
  DEFAULT_DAYS,
  EXTREME_ABS_RETURN,
  LOW_BASE_CLOSE,
  PRESET_DAYS,
  anchorDeviation,
  barEligibleByCreation,
  barStatus,
  calcNDayReturn,
  calcStreak,
  classifyBars,
  observationProvesFinal,
  streakFromClosed,
  closedBars,
  compareStreakThenReturn,
  displayCreated,
  fmtRelativeAge,
  formalStreakEligible,
  isPositiveStreak,
  getFinalizedDailyBars,
  hasContiguousDays,
  isCurrentDaysRequest,
  klineIsStale,
  KLINE_FETCH_WINDOW_SEC,
  canonicalWindowEndTs,
  ndWindowDays,
  officialDailyMetrics,
  parseDays,
  patternFromFinalized,
  qualityFlagsFor,
  rankingQualityOk,
  returnOverClosedCandles,
  shouldCommitRankWrite,
  streakBoardEligible,
  streakMetrics,
  type DailyBar,
  type RankWriteChannel,
} from "./streak.ts";

const DAY0 = 1_790_000_000 - (1_790_000_000 % DAY_SEC);

function bar(
  dayIndex: number,
  close: number,
  high = close,
  fetchedAt: number | null | undefined = undefined,
): DailyBar {
  const ts = DAY0 + dayIndex * DAY_SEC;
  const end = ts + DAY_SEC;
  return { ts, close, high, fetchedAt: fetchedAt === undefined ? end : fetchedAt };
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
    assert.equal(m.streak, null);
    assert.equal(m.streakStatus, "INSUFFICIENT_DATA");
    assert.equal(m.streakReturn, null);
    assert.equal(m.change1d, null);
  });

  it("stale fetch does not drop a finalized calendar-closed candle", () => {
    const bars = [bar(0, 1), bar(1, 2), bar(2, 3)];
    const fetchedEarly = DAY0 + 2 * DAY_SEC - 10;
    const m = streakMetrics(bars, now, fetchedEarly, null);
    assert.equal(m.closedCount, 3);
    assert.equal(m.streak, 2);
    assert.equal(m.lastStatus, "FINALIZED");
    assert.equal(klineIsStale(now, fetchedEarly), true);
    assert.equal(klineIsStale(now, fetched), false);
  });

  it("still uses per-bar fetchedAt when token-level fetch time is unknown", () => {
    const m = streakMetrics([bar(0, 1), bar(1, 2)], now, null, null);
    assert.equal(m.closedCount, 2);
    assert.equal(m.streak, 1);
    assert.equal(klineIsStale(now, null), true);
  });

  it("stops when the previous calendar day is missing", () => {
    const bars = [bar(0, 1), bar(1, 1.2), bar(3, 2)];
    const m = streakMetrics(bars, now, fetched, null);
    assert.equal(m.closedCount, 3);
    assert.equal(m.streak, null);
    assert.equal(m.streakStatus, "INSUFFICIENT_DATA");
    assert.equal(m.streakReturn, null);
    assert.equal(m.change1d, null);
  });

  it("keeps only the adjacent tail after a hole", () => {
    const bars = [bar(0, 1), bar(2, 1.1, 1.2), bar(3, 1.4, 1.5)];
    const m = streakMetrics(bars, now, fetched, null);
    assert.equal(m.streak, 1);
    assert.ok(Math.abs((m.streakReturn ?? 0) - (1.4 / 1.1 - 1)) < 1e-12);
    assert.ok(Math.abs((m.change1d ?? 0) - (1.4 / 1.1 - 1)) < 1e-12);
    assert.ok((m.streak ?? 0) <= m.closedCount);
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

  it("sorts unavailable streak after numeric streaks", () => {
    const rows = [
      { streak: null, streakReturn: 9 },
      { streak: 0, streakReturn: null },
      { streak: 1, streakReturn: 0.1 },
    ];
    const sorted = [...rows].sort((a, b) => compareStreakThenReturn(a, b));
    assert.deepEqual(sorted.map((r) => r.streak), [1, 0, null]);
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

  it("formal streak board only accepts a positive streak status", () => {
    assert.equal(isPositiveStreak("POSITIVE_STREAK"), true);
    assert.equal(isPositiveStreak("VALID_ZERO"), false);
    assert.equal(isPositiveStreak("INSUFFICIENT_DATA"), false);
    assert.equal(isPositiveStreak(null), false);
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

  it("ignores bars whose UTC day is before the token creation day", () => {
    const created = DAY0 + 2 * DAY_SEC + 10;
    const kept = closedBars([bar(0, 1), bar(1, 2), bar(2, 3)], DAY0 + 4 * DAY_SEC, DAY0 + 4 * DAY_SEC, created);
    assert.deepEqual(kept.map((b) => b.close), [3]);
    assert.equal(barEligibleByCreation(DAY0 + DAY_SEC, created), false);
    assert.equal(barEligibleByCreation(DAY0 + 2 * DAY_SEC, created), true);
  });
});

describe("N-day window vs consecutive-up streak", () => {
  it("CASE 1: 6-day up streak with selectedDays=5 keeps streak=6 and a 5D return", () => {
    const now = DAY0 + 7 * DAY_SEC + 3600;
    const fetched = DAY0 + 7 * DAY_SEC + 10;
    const bars = [
      bar(0, 1.0),
      bar(1, 1.1),
      bar(2, 1.2),
      bar(3, 1.3),
      bar(4, 1.4),
      bar(5, 1.5),
      bar(6, 1.6),
      bar(7, 9.9),
    ];
    const finalized = getFinalizedDailyBars(bars, now, null);
    const m = streakMetrics(bars, now, fetched, null);
    const selectedDays = 5;
    const ret5 = calcNDayReturn(finalized, selectedDays);
    assert.equal(m.streak, 6);
    assert.notEqual(m.streak, selectedDays);
    assert.ok((m.streak ?? 0) > selectedDays);
    assert.ok(Math.abs((ret5 ?? 0) - (1.6 / 1.1 - 1)) < 1e-12);
    assert.equal(finalized.at(-1)?.close, 1.6);
  });

  it("CASE 2: up up down up up → streak=2", () => {
    const now = DAY0 + 6 * DAY_SEC + 3600;
    const fetched = DAY0 + 6 * DAY_SEC + 10;
    const bars = [bar(0, 1.0), bar(1, 1.1), bar(2, 1.2), bar(3, 1.0), bar(4, 1.1), bar(5, 1.2)];
    const m = streakMetrics(bars, now, fetched, null);
    assert.equal(m.streak, 2);
  });

  it("CASE 3: unfinished huge up day does not change streak", () => {
    const now = DAY0 + 2 * DAY_SEC + 3600;
    const fetched = now;
    const bars = [bar(0, 1.0), bar(1, 1.1), bar(2, 50)];
    const m = streakMetrics(bars, now, fetched, null);
    const closed = closedBars(bars, now, fetched, null);
    assert.deepEqual(closed.map((b) => b.close), [1.0, 1.1]);
    assert.equal(m.streak, 1);
    assert.ok(Math.abs((m.change1d ?? 0) - 0.1) < 1e-12);
    assert.equal(barStatus(bars[2]!, now), "OPEN");
  });

  it("CASE 4: only 5 finalized bars makes 5D cumulative unavailable", () => {
    const now = DAY0 + 5 * DAY_SEC + 3600;
    const fetched = now;
    const bars = [bar(0, 1), bar(1, 1.1), bar(2, 1.2), bar(3, 1.3), bar(4, 1.4)];
    const finalized = getFinalizedDailyBars(bars, now, null);
    assert.equal(finalized.length, 5);
    assert.equal(hasContiguousDays(finalized, 5), false);
    assert.equal(calcNDayReturn(finalized, 5), null);
    assert.ok(calcNDayReturn(finalized, 4) != null);
  });

  it("CASE 5: equal close terminates streak", () => {
    const now = DAY0 + 3 * DAY_SEC + 3600;
    const fetched = now;
    const bars = [bar(0, 1.0), bar(1, 1.2), bar(2, 1.2), bar(3, 1.2)];
    const m = streakMetrics(bars, now, fetched, null);
    assert.equal(m.streak, 0);
    assert.equal(m.streakStatus, "VALID_ZERO");
    assert.equal(m.streakReturn, null);
  });

  it("CASE 6: an older days request must not apply after a newer one", () => {
    let latest = 0;
    const selected = { days: 1 };
    const apply = (seq: number, requestDays: number) => {
      if (!isCurrentDaysRequest(seq, latest, requestDays, selected.days)) return false;
      return true;
    };
    const first = ++latest;
    selected.days = 1;
    const second = ++latest;
    selected.days = 30;
    const third = ++latest;
    selected.days = 3;
    const fourth = ++latest;
    selected.days = 14;
    const fifth = ++latest;
    selected.days = 5;
    assert.equal(apply(first, 1), false);
    assert.equal(apply(second, 30), false);
    assert.equal(apply(third, 3), false);
    assert.equal(apply(fourth, 14), false);
    assert.equal(apply(fifth, 5), true);
    assert.equal(isCurrentDaysRequest(fifth, latest, 5, 5), true);
    assert.equal(isCurrentDaysRequest(fifth, latest, 14, 5), false);
  });
});

describe("finalization contract", () => {
  it("CASE 7: calendar closed with fetched_at < bar.end is PROVISIONAL and stays in the series", () => {
    const now = DAY0 + 3 * DAY_SEC + 3600;
    const bars = [
      bar(0, 1),
      bar(1, 1.2),
      bar(2, 1.5, 1.5, DAY0 + 2 * DAY_SEC + 12 * 3600),
    ];
    const classified = classifyBars(bars, now, null);
    assert.equal(classified[2]!.status, "PROVISIONAL");
    assert.equal(barStatus(bars[2]!, now), "PROVISIONAL");
    const calendar = closedBars(bars, now, null, null);
    assert.equal(calendar.length, 3);
    const m = officialDailyMetrics(bars, now, null, 2);
    assert.equal(m.lastStatus, "PROVISIONAL");
    assert.equal(m.streak, null);
    assert.equal(m.changeNd, null);
    assert.equal(m.change1d, null);
  });

  it("CASE 8: the same bar becomes FINALIZED after a post-close refetch", () => {
    const now = DAY0 + 3 * DAY_SEC + 3600;
    const bars = [
      bar(0, 1),
      bar(1, 1.2),
      bar(2, 1.5, 1.5, DAY0 + 3 * DAY_SEC + 120),
    ];
    assert.equal(barStatus(bars[2]!, now), "FINALIZED");
    const m = officialDailyMetrics(bars, now, null, 2);
    assert.equal(m.lastStatus, "FINALIZED");
    assert.equal(m.streak, 2);
    assert.ok(Math.abs((m.changeNd ?? 0) - (1.5 / 1 - 1)) < 1e-12);
  });

  it("CASE 9: one provisional bar inside a 5D window makes 5D null", () => {
    const now = DAY0 + 6 * DAY_SEC + 3600;
    const bars = [
      bar(0, 1),
      bar(1, 1.1),
      bar(2, 1.2, 1.2, DAY0 + 2 * DAY_SEC + 100),
      bar(3, 1.3),
      bar(4, 1.4),
      bar(5, 1.5),
    ];
    const m = officialDailyMetrics(bars, now, null, 5);
    assert.equal(m.lastStatus, "FINALIZED");
    assert.equal(m.changeNd, null);
    assert.ok(m.streak != null);
  });

  it("CASE 10: a provisional tail is not the official last bar", () => {
    const now = DAY0 + 4 * DAY_SEC + 3600;
    const bars = [
      bar(0, 1),
      bar(1, 1.2),
      bar(2, 1.4),
      bar(3, 1.8, 1.8, DAY0 + 3 * DAY_SEC + 100),
    ];
    const m = officialDailyMetrics(bars, now, null, 3);
    assert.equal(m.lastStatus, "PROVISIONAL");
    assert.equal(m.streak, null);
    assert.equal(m.changeNd, null);
    assert.equal(getFinalizedDailyBars(bars, now, null).at(-1)?.close, 1.4);
    assert.equal(calcStreak(getFinalizedDailyBars(bars, now, null)), 2);
  });

  it("CASE 11: bars before the token creation day are dropped", () => {
    const now = DAY0 + 4 * DAY_SEC + 3600;
    const created = DAY0 + 2 * DAY_SEC + 100;
    const bars = [bar(0, 1), bar(1, 2), bar(2, 3), bar(3, 4)];
    const m = officialDailyMetrics(bars, now, created, 3);
    assert.equal(m.closedCount, 2);
    assert.equal(m.streak, 1);
    assert.equal(calcNDayReturn(getFinalizedDailyBars(bars, now, created), 3), null);
  });

  it("CASE 12: market and streak share calcStreak on the same bars", () => {
    const now = DAY0 + 5 * DAY_SEC + 3600;
    const bars = [bar(0, 1), bar(1, 1.1), bar(2, 1.05), bar(3, 1.2), bar(4, 1.3)];
    const market = officialDailyMetrics(bars, now, null, 5);
    const streakBoard = calcStreak(getFinalizedDailyBars(bars, now, null));
    assert.equal(market.streak, streakBoard);
    assert.equal(market.streak, 2);
  });
});

describe("rank request seq covers every write channel", () => {
  function applyAll(
    seq: number,
    latest: number,
    requestDays: number,
    selectedDays: number,
  ): Record<RankWriteChannel, boolean> {
    const channels: RankWriteChannel[] = ["data", "error", "loading", "eligibility"];
    const out = {} as Record<RankWriteChannel, boolean>;
    for (const ch of channels) {
      out[ch] = shouldCommitRankWrite(seq, latest, requestDays, selectedDays, ch);
    }
    return out;
  }

  it("old success does not overwrite a newer success", () => {
    const latest = 2;
    assert.equal(shouldCommitRankWrite(1, latest, 1, 5, "data"), false);
    assert.equal(shouldCommitRankWrite(2, latest, 5, 5, "data"), true);
  });

  it("old failure does not overwrite a newer success", () => {
    const latest = 2;
    const staleFail = applyAll(1, latest, 1, 5);
    const freshOk = applyAll(2, latest, 5, 5);
    assert.deepEqual(staleFail, { data: false, error: false, loading: false, eligibility: false });
    assert.deepEqual(freshOk, { data: true, error: true, loading: true, eligibility: true });
  });

  it("old success does not overwrite a newer failure", () => {
    const latest = 2;
    assert.equal(shouldCommitRankWrite(1, latest, 7, 3, "data"), false);
    assert.equal(shouldCommitRankWrite(2, latest, 3, 3, "error"), true);
    assert.equal(shouldCommitRankWrite(2, latest, 3, 3, "eligibility"), true);
    assert.equal(shouldCommitRankWrite(2, latest, 3, 3, "loading"), true);
  });
});

describe("quality flags do not rewrite raw returns", () => {
  it("marks LOW_BASE and EXTREME_RETURN and leaves the ratio intact", () => {
    const now = DAY0 + 2 * DAY_SEC + 3600;
    const bars = [bar(0, LOW_BASE_CLOSE / 10), bar(1, 1)];
    const m = officialDailyMetrics(bars, now, null, 1);
    const raw = 1 / (LOW_BASE_CLOSE / 10) - 1;
    assert.ok(Math.abs((m.changeNd ?? 0) - raw) < 1e-6);
    assert.ok(m.qualityFlags.includes("LOW_BASE"));
    assert.ok(m.qualityFlags.includes("EXTREME_RETURN"));
    assert.equal(rankingQualityOk(m.qualityFlags), false);
    assert.ok(raw > EXTREME_ABS_RETURN);
    assert.deepEqual(qualityFlagsFor(bars, raw, raw, 1).sort(), ["EXTREME_RETURN", "LOW_BASE"]);
  });
});

describe("observation timestamp is the only finalized proof", () => {
  const ts = DAY0;
  const end = ts + DAY_SEC;

  it("intraday observed_at < bar_end is NOT_FINALIZED", () => {
    const during = ts + 12 * 3600;
    const later = end + 86400;
    assert.equal(observationProvesFinal(ts, during), false);
    assert.equal(barStatus({ ts, close: 1, high: 1, fetchedAt: during }, later), "PROVISIONAL");
  });

  it("the same intraday candle stays NOT_FINALIZED a day and a year later", () => {
    const during = ts + 12 * 3600;
    const bar = { ts, close: 1, high: 1, fetchedAt: during };
    assert.equal(barStatus(bar, end + DAY_SEC), "PROVISIONAL");
    assert.equal(barStatus(bar, end + 365 * DAY_SEC), "PROVISIONAL");
    assert.equal(observationProvesFinal(ts, during), false);
  });

  it("observed_at > bar_end is FINALIZED", () => {
    assert.equal(observationProvesFinal(ts, end + 120), true);
    assert.equal(barStatus({ ts, close: 1, high: 1, fetchedAt: end + 120 }, end + 120), "FINALIZED");
  });

  it("observed_at == bar_end is FINALIZED", () => {
    assert.equal(observationProvesFinal(ts, end), true);
    assert.equal(barStatus({ ts, close: 1, high: 1, fetchedAt: end }, end + 1), "FINALIZED");
  });

  it("missing observed_at is NOT_FINALIZED", () => {
    const later = end + 86400;
    assert.equal(observationProvesFinal(ts, null), false);
    assert.equal(barStatus({ ts, close: 1, high: 1, fetchedAt: null }, later), "PROVISIONAL");
    assert.equal(barStatus({ ts, close: 1, high: 1 }, later), "PROVISIONAL");
  });

  it("a stamp older than the fetch window cannot finalize the bar", () => {
    const fake = ts + 200 * DAY_SEC;
    assert.equal(ts < fake - KLINE_FETCH_WINDOW_SEC, true);
    assert.equal(observationProvesFinal(ts, fake), false);
    assert.equal(barStatus({ ts, close: 1, high: 1, fetchedAt: fake }, fake + 10), "PROVISIONAL");
  });

  it("migration-time now does not finalize an intraday bar", () => {
    const during = ts + 10 * 3600;
    const migrateNow = end + 10 * DAY_SEC;
    assert.equal(barStatus({ ts, close: 1, high: 1, fetchedAt: during }, migrateNow), "PROVISIONAL");
    assert.equal(barStatus({ ts, close: 1, high: 1, fetchedAt: during }, end + 365 * DAY_SEC), "PROVISIONAL");
    assert.equal(observationProvesFinal(ts, during), false);
  });
});

describe("missing vs zero streak", () => {
  it("missing previous day is INSUFFICIENT_DATA not zero", () => {
    const closed = [
      { ts: DAY0, close: 1 },
      { ts: DAY0 + 2 * DAY_SEC, close: 2 },
    ];
    assert.deepEqual(streakFromClosed(closed), { streak: null, status: "INSUFFICIENT_DATA" });
    assert.equal(calcStreak(closed), null);
  });

  it("previous day exists and last close did not rise is VALID_ZERO", () => {
    const closed = [
      { ts: DAY0, close: 2 },
      { ts: DAY0 + DAY_SEC, close: 2 },
    ];
    assert.deepEqual(streakFromClosed(closed), { streak: 0, status: "VALID_ZERO" });
    assert.equal(calcStreak(closed), 0);
  });

  it("adjacent up tail is POSITIVE_STREAK", () => {
    const closed = [
      { ts: DAY0, close: 1 },
      { ts: DAY0 + DAY_SEC, close: 1.1 },
      { ts: DAY0 + 2 * DAY_SEC, close: 1.2 },
    ];
    assert.deepEqual(streakFromClosed(closed), { streak: 2, status: "POSITIVE_STREAK" });
  });
});

describe("N-day uses finalized candles only", () => {
  it("does not fall back to a provisional close", () => {
    const now = DAY0 + 6 * DAY_SEC + 3600;
    const bars = [
      bar(0, 1),
      bar(1, 1.1),
      bar(2, 1.2),
      bar(3, 1.3),
      bar(4, 1.4),
      bar(5, 9.9, 9.9, DAY0 + 5 * DAY_SEC + 100),
    ];
    const m = officialDailyMetrics(bars, now, null, 5);
    assert.equal(m.lastStatus, "PROVISIONAL");
    assert.equal(m.changeNd, null);
    assert.equal(m.streak, null);
    assert.equal(m.streakStatus, "INSUFFICIENT_DATA");
    assert.equal(calcNDayReturn(getFinalizedDailyBars(bars, now, null), 5), null);
  });
});

describe("PUMPGU regression: intraday close must not mint +1975.3%", () => {
  it("uses the finalized 10-01 close", () => {
    const d = DAY0;
    const trueClose = 7.7301777e-05;
    const intraday = 0.00015835;
    const base = trueClose / 10.130812;
    const bars: DailyBar[] = [];
    for (let i = 0; i < 5; i++) {
      bars.push(bar(i, base * (1 + i * 0.01)));
    }
    bars.push({
      ts: d + 5 * DAY_SEC,
      close: trueClose,
      high: trueClose,
      fetchedAt: d + 6 * DAY_SEC + 120,
    });
    const now = d + 6 * DAY_SEC + 3600;
    const m = officialDailyMetrics(bars, now, null, 5);
    assert.ok(m.changeNd != null);
    assert.ok(Math.abs((m.changeNd ?? 0) * 100 - 913.0812) < 1);
    assert.ok(((m.changeNd ?? 0) * 100) < 1900);
    const bogus = officialDailyMetrics(
      bars.map((b, i) => (i === 5 ? { ...b, close: intraday, high: intraday } : b)),
      now,
      null,
      5,
    );
    assert.ok(((bogus.changeNd ?? 0) * 100) > 1900);
  });
});

describe("Phase 4 UTC materialization oracle boundaries", () => {
  const midnight = DAY0 + 4 * DAY_SEC;
  const provisionalObservedAt = midnight - 12 * 3600;
  const bars: DailyBar[] = [
    bar(0, 1),
    bar(1, 2),
    bar(2, 3),
    bar(3, 4, 4, provisionalObservedAt),
  ];

  it("23:59 uses only the prior finalized tail", () => {
    const m = officialDailyMetrics(bars, midnight - 1, null, 2);
    assert.equal(m.lastStatus, "FINALIZED");
    assert.equal(m.streak, 2);
    assert.equal(m.changeNd, 2);
  });

  it("00:00 and 00:01 invalidate a newly provisional tail", () => {
    for (const now of [midnight, midnight + 60]) {
      const m = officialDailyMetrics(bars, now, null, 2);
      assert.equal(m.lastStatus, "PROVISIONAL");
      assert.equal(m.streak, null);
      assert.equal(m.changeNd, null);
    }
  });

  it("a post-close observation publishes the new finalized result", () => {
    const updated = bars.map((b, i) => i === 3 ? { ...b, fetchedAt: midnight + 60 } : b);
    const m = officialDailyMetrics(updated, midnight + 60, null, 2);
    assert.equal(m.lastStatus, "FINALIZED");
    assert.equal(m.streak, 3);
    assert.equal(m.changeNd, 1);
  });

  it("historical replay does not use a future finalized observation", () => {
    const updated = bars.map((b, i) => i === 3 ? { ...b, finalizedAt: midnight + 60 } : b);
    const m = officialDailyMetrics(updated, midnight - 1, null, 2);
    assert.equal(m.lastStatus, "FINALIZED");
    assert.equal(m.streak, 2);
    assert.equal(m.changeNd, 2);
  });

  it("streak-board pattern is derived from finalized rows only", () => {
    const finalized = getFinalizedDailyBars(bars, midnight, null);
    assert.equal(finalized.length, 3);
    assert.deepEqual(patternFromFinalized(finalized), {
      pattern: "++",
      downDays: 0,
      flatDays: 0,
    });
  });
});

describe("canonical ND window", () => {
  // D = 10/03 的 UTC 0 点；now = 10/04 03:00，10/04 日K 仍是 OPEN。
  const D = 1_790_000_000 - (1_790_000_000 % DAY_SEC);
  const now = D + DAY_SEC + 3 * 3600;
  const fin = (ts: number, close: number): DailyBar => ({ ts, high: close, close, fetchedAt: ts + DAY_SEC + 60 });
  const day = (k: number) => D + k * DAY_SEC; // k=0 → 10/03, -1 → 10/02 …
  const end = canonicalWindowEndTs(now);
  const nd = (bars: DailyBar[], n: number) => officialDailyMetrics(bars, now, null, n, end).changeNd;

  it("10/04 OPEN → canonical end is 10/03", () => {
    assert.equal(end, D);
    assert.equal(barStatus({ ts: day(1), high: 1, close: 1, fetchedAt: now }, now), "OPEN");
  });

  it("canonical end is calendar-only: no token data can push or pull it", () => {
    assert.equal(canonicalWindowEndTs(D + DAY_SEC), D);
    assert.equal(canonicalWindowEndTs(D + 2 * DAY_SEC - 1), D);
    // 即使某个 token 声称 10/04 已 finalized（finalizedAt 提前），它也是 OPEN，且终点不随数据变化。
    const early = { ts: day(1), high: 9, close: 9, fetchedAt: now, finalizedAt: now };
    assert.equal(barStatus(early, now), "OPEN");
    assert.equal(nd([fin(day(-1), 2), fin(day(0), 3), early], 1), 3 / 2 - 1);
  });

  it("10/02 + 10/03 → 1D = close(10/03)/close(10/02) − 1", () => {
    assert.equal(nd([fin(day(-1), 2), fin(day(0), 3)], 1), 3 / 2 - 1);
  });

  it("missing 10/03 → 1D null, no fallback to 10/02", () => {
    assert.equal(nd([fin(day(-2), 1), fin(day(-1), 2)], 1), null);
  });

  it("10/03 present but 10/02 missing → 1D null", () => {
    assert.equal(nd([fin(day(-2), 1), fin(day(0), 3)], 1), null);
  });

  it("10/03 only PROVISIONAL → 1D null", () => {
    const prov = { ts: day(0), high: 3, close: 3, fetchedAt: day(0) + 3600 };
    assert.equal(nd([fin(day(-1), 2), prov], 1), null);
  });

  it("N-day return needs exactly N+1 consecutive finalized candles ending at canonical end", () => {
    const bars = [fin(day(-3), 1), fin(day(-2), 2), fin(day(-1), 4), fin(day(0), 8)];
    assert.equal(nd(bars, 1), 1);
    assert.equal(nd(bars, 2), 3);
    assert.equal(nd(bars, 3), 7);
    assert.equal(nd(bars, 4), null); // 只有 4 根，4D 需要 5 根
    assert.deepEqual(ndWindowDays(end, 3), { display: [day(-2), day(-1), day(0)], required: [day(-3), day(-2), day(-1), day(0)] });
  });

  it("regression fixture sol 7Vertk…Vpump (created 10/01; 10/01–10/03 finalized; 10/04 OPEN)", () => {
    // 真实库数据（daily_kline，fetched/finalized 10/04 00:07 UTC）。日期平移到测试用的 D。
    const fetched = day(1) + 7 * 60;
    const bars: DailyBar[] = [
      { ts: day(-2), high: 0.00054010872, close: 0.00011167495, fetchedAt: fetched, finalizedAt: fetched },
      { ts: day(-1), high: 0.0053375729, close: 0.0022515295, fetchedAt: fetched, finalizedAt: fetched },
      { ts: day(0), high: 0.021343439, close: 0.014355324, fetchedAt: fetched, finalizedAt: fetched },
      { ts: day(1), high: 0.014800588, close: 0.013286084, fetchedAt: fetched },
    ];
    const createdAt = day(-2) + 3600;
    const m = (n: number) => officialDailyMetrics(bars, now, createdAt, n, end);
    assert.ok(Math.abs(m(1).changeNd! - (0.014355324 / 0.0022515295 - 1)) < 1e-12);
    assert.ok(Math.abs(m(2).changeNd! - (0.014355324 / 0.00011167495 - 1)) < 1e-9);
    assert.equal(m(3).changeNd, null); // 缺 09/30（代币 10/01 才创建）
    assert.equal(m(1).streak, 2);
  });
});
