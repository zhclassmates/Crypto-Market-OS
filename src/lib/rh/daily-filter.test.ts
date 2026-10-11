import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  MARKET_DATE_VIEWPORT,
  calendarDateWindow,
  dateTOffset,
  fmtTOffset,
  clearDailyFilters,
  compareDailyReturn,
  cycleDailyFilter,
  nextPrimarySort,
  dailyHistoryForWindow,
  dailyReturnsFromFinalized,
  finalizedDateWindow,
  formatCompactUsd,
  parseVolumeUsd,
  formatDailyReturn,
  latestFinalizedDates,
  matchesDailyFilters,
  matchesDailyReturn,
  reconcileDailyFilters,
  type DailyReturnFilters,
  type DailyReturnMap,
} from "./daily-filter.ts";
import { DAY_SEC, type DailyBar } from "./streak.ts";

const DAY0 = 1_790_000_000 - (1_790_000_000 % DAY_SEC);
const date = (day: number) => new Date((DAY0 + day * DAY_SEC) * 1000).toISOString().slice(0, 10);

describe("daily direction filters", () => {
  it("matches a single UP date", () => {
    assert.equal(matchesDailyReturn(0.01, "UP"), true);
    assert.equal(matchesDailyReturn(0, "UP"), false);
  });

  it("matches a single DOWN date", () => {
    assert.equal(matchesDailyReturn(-0.01, "DOWN"), true);
    assert.equal(matchesDailyReturn(0, "DOWN"), false);
  });

  it("requires two UP dates to both pass", () => {
    const filters: DailyReturnFilters = { "2026-09-26": "UP", "2026-09-27": "UP" };
    assert.equal(matchesDailyFilters({ "2026-09-26": 0.02, "2026-09-27": 0.03 }, filters), true);
  });

  it("requires mixed UP and DOWN dates to both pass", () => {
    const filters: DailyReturnFilters = { "2026-09-26": "UP", "2026-09-27": "DOWN" };
    assert.equal(matchesDailyFilters({ "2026-09-26": 0.02, "2026-09-27": -0.03 }, filters), true);
  });

  it("requires all three dates to pass", () => {
    const filters: DailyReturnFilters = {
      "2026-09-26": "UP",
      "2026-09-27": "DOWN",
      "2026-09-28": "UP",
    };
    assert.equal(matchesDailyFilters({
      "2026-09-26": 0.02,
      "2026-09-27": -0.03,
      "2026-09-28": 0.01,
    }, filters), true);
  });

  it("rejects a row when any selected date fails", () => {
    const filters: DailyReturnFilters = { "2026-09-26": "UP", "2026-09-27": "UP" };
    assert.equal(matchesDailyFilters({ "2026-09-26": 0.02, "2026-09-27": -0.01 }, filters), false);
  });

  it("rejects null or a missing finalized daily return", () => {
    const filters: DailyReturnFilters = { "2026-09-26": "UP", "2026-09-27": "UP" };
    assert.equal(matchesDailyFilters({ "2026-09-26": 0.02, "2026-09-27": null }, filters), false);
    assert.equal(matchesDailyFilters({ "2026-09-27": 0.02 }, filters), false);
  });

  it("cycles NONE to UP to DOWN to NONE", () => {
    const up = cycleDailyFilter({}, "2026-09-26");
    assert.deepEqual(up, { "2026-09-26": "UP" });
    const down = cycleDailyFilter(up, "2026-09-26");
    assert.deepEqual(down, { "2026-09-26": "DOWN" });
    assert.deepEqual(cycleDailyFilter(down, "2026-09-26"), {});
  });

  it("changing one date never overwrites another date", () => {
    const first = cycleDailyFilter({}, "2026-09-26");
    const second = cycleDailyFilter(first, "2026-09-27");
    assert.deepEqual(second, { "2026-09-26": "UP", "2026-09-27": "UP" });
  });

  it("applies one selected UP date only to that date", () => {
    const filters: DailyReturnFilters = { "2026-09-26": "UP" };
    assert.equal(matchesDailyFilters({ "2026-09-26": 0.01, "2026-09-27": -0.99 }, filters), true);
    assert.equal(matchesDailyFilters({ "2026-09-26": -0.01, "2026-09-27": 0.99 }, filters), false);
  });

  it("requires three selected UP dates to all be positive", () => {
    const filters: DailyReturnFilters = {
      "2026-09-26": "UP",
      "2026-09-27": "UP",
      "2026-09-28": "UP",
    };
    assert.equal(matchesDailyFilters({
      "2026-09-26": 0.01,
      "2026-09-27": 0.02,
      "2026-09-28": 0.03,
    }, filters), true);
    assert.equal(matchesDailyFilters({
      "2026-09-26": 0.01,
      "2026-09-27": 0.02,
      "2026-09-28": -0.03,
    }, filters), false);
  });

  it("changes then removes only 09/28 while preserving 09/26 and 09/27", () => {
    let filters: DailyReturnFilters = {};
    for (const date of ["2026-09-26", "2026-09-27", "2026-09-28"]) {
      filters = cycleDailyFilter(filters, date);
    }
    assert.deepEqual(filters, {
      "2026-09-26": "UP",
      "2026-09-27": "UP",
      "2026-09-28": "UP",
    });

    filters = cycleDailyFilter(filters, "2026-09-28");
    assert.deepEqual(filters, {
      "2026-09-26": "UP",
      "2026-09-27": "UP",
      "2026-09-28": "DOWN",
    });

    filters = cycleDailyFilter(filters, "2026-09-28");
    assert.deepEqual(filters, {
      "2026-09-26": "UP",
      "2026-09-27": "UP",
    });
  });

  it("keeps conditions bound to real YYYY-MM-DD keys when dates roll", () => {
    const filters: DailyReturnFilters = { "2026-09-26": "UP", "2026-09-28": "DOWN" };
    const rolled = reconcileDailyFilters(filters, ["2026-09-27", "2026-09-28", "2026-09-29"]);
    assert.deepEqual(rolled, { "2026-09-28": "DOWN" });
    assert.equal("2026-09-29" in rolled, false);
  });

  it("can still clear one or every selected date", () => {
    const filters: DailyReturnFilters = { "2026-09-26": "UP", "2026-09-27": "DOWN" };
    assert.deepEqual(clearDailyFilters(filters, "2026-09-26"), { "2026-09-27": "DOWN" });
    assert.deepEqual(clearDailyFilters(filters), {});
  });
});

describe("7-day calendar window", () => {
  const first = [
    "2026-09-27", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03",
  ];
  const second = [
    "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
  ];

  it("CASE 1: uses API T=2026-10-03 as the exact right edge", () => {
    assert.deepEqual(finalizedDateWindow("2026-10-03"), first);
  });

  it("CASE 2: moves to API T=2026-10-04 without using browser today", () => {
    assert.deepEqual(finalizedDateWindow("2026-10-04"), second);
    assert.deepEqual(second.map((date) => fmtTOffset(dateTOffset(date, "2026-10-04"))), [
      "T-6", "T-5", "T-4", "T-3", "T-2", "T-1", "T0",
    ]);
  });

  it("CASE 3: shifts the whole seven-day window forward by one natural day", () => {
    const oldWindow = finalizedDateWindow("2026-10-03");
    const newWindow = finalizedDateWindow("2026-10-04");
    assert.equal(oldWindow.length, MARKET_DATE_VIEWPORT);
    assert.equal(newWindow.length, MARKET_DATE_VIEWPORT);
    assert.equal(newWindow.includes("2026-09-27"), false);
    assert.equal(newWindow[6], "2026-10-04");
    assert.deepEqual(oldWindow.slice(1), newWindow.slice(0, 6));
  });

  it("rolls correctly across a year boundary", () => {
    const now = Date.UTC(2027, 0, 2, 0, 1) / 1000;
    const dates = calendarDateWindow(now);
    assert.equal(dates[0], "2026-12-27");
    assert.equal(dates[6], "2027-01-02");
  });

  it("renders a missing return as an em dash", () => {
    const returns: DailyReturnMap = { "2026-10-02": 0.124 };
    assert.equal(formatDailyReturn(returns["2026-10-04"]), "—");
  });

  it("renders finalized historical returns normally", () => {
    assert.equal(formatDailyReturn(0.124), "+12.4%");
    assert.equal(formatDailyReturn(-0.072), "−7.2%");
  });

  it("keeps calendar-key filters stable when API T rolls", () => {
    const filters: DailyReturnFilters = { "2026-09-27": "UP", "2026-10-03": "DOWN" };
    assert.deepEqual(reconcileDailyFilters(filters, second), { "2026-10-03": "DOWN" });
  });

  it("CASE 4: every token shares the API window and missing T/T-1 cells stay missing", () => {
    const headers = finalizedDateWindow("2026-10-03");
    const tokenA: DailyReturnMap = Object.fromEntries(headers.map((date, index) => [date, (index + 1) / 100]));
    const tokenB: DailyReturnMap = Object.fromEntries(headers.slice(0, 5).map((date, index) => [date, (index + 1) / 100]));
    const renderRow = (returns: DailyReturnMap) => headers.map((date) => formatDailyReturn(returns[date]));

    assert.equal(renderRow(tokenA).length, 7);
    assert.deepEqual(renderRow(tokenB).slice(-2), ["—", "—"]);
    assert.deepEqual(headers, first);
    assert.notDeepEqual(headers, finalizedDateWindow("2026-10-01"));
  });

  it("CASE 5: missing or invalid API T produces no guessed fallback window", () => {
    assert.deepEqual(finalizedDateWindow(null), []);
    assert.deepEqual(finalizedDateWindow(undefined), []);
    assert.deepEqual(finalizedDateWindow("not-a-date"), []);
    assert.deepEqual(finalizedDateWindow("2026-02-30"), []);
  });
});

describe("finalized daily presentation series", () => {
  it("uses only finalized bars and rolls to the latest seven real dates", () => {
    const bars: DailyBar[] = Array.from({ length: 9 }, (_, day) => ({
      ts: DAY0 + day * DAY_SEC,
      high: day + 1,
      close: day + 1,
      fetchedAt: DAY0 + (day + 1) * DAY_SEC,
    }));
    bars.push({
      ts: DAY0 + 9 * DAY_SEC,
      high: 50,
      close: 50,
      fetchedAt: DAY0 + 9 * DAY_SEC + 60,
    });
    const now = DAY0 + 10 * DAY_SEC + 60;
    const series = dailyReturnsFromFinalized(bars, now, null);
    const visible = latestFinalizedDates(series.dates);

    assert.deepEqual(visible, Array.from({ length: 7 }, (_, i) => date(i + 2)));
    assert.equal(series.returns[date(8)], 9 / 8 - 1);
    assert.equal(series.returns[date(9)], undefined);
  });
});

describe("daily primary sort (last clicked date only)", () => {
  it("last click owns the sort; earlier dates only filter", () => {
    let filters: DailyReturnFilters = {};
    let sort = null as ReturnType<typeof nextPrimarySort>;
    for (const d of ["2026-09-28", "2026-09-29", "2026-10-03"]) {
      filters = cycleDailyFilter(filters, d);
      sort = nextPrimarySort(sort, d, filters[d]);
    }
    assert.deepEqual(filters, { "2026-09-28": "UP", "2026-09-29": "UP", "2026-10-03": "UP" });
    assert.deepEqual(sort, { date: "2026-10-03", dir: "desc" });
    filters = cycleDailyFilter(filters, "2026-09-29");
    sort = nextPrimarySort(sort, "2026-09-29", filters["2026-09-29"]);
    assert.equal(filters["2026-09-29"], "DOWN");
    assert.deepEqual(sort, { date: "2026-09-29", dir: "asc" });
    // 其他日期点回 NONE 不动主排序；主排序那列点回 NONE 则取消
    assert.deepEqual(nextPrimarySort(sort, "2026-09-28", undefined), sort);
    assert.equal(nextPrimarySort(sort, "2026-09-29", undefined), null);
  });

  it("sorts by raw numbers, not formatted strings, and puts missing values last", () => {
    const rows: DailyReturnMap[] = [
      { d: 0.05 }, { d: 1.234 }, { d: null }, { d: 0.2 }, { d: -0.5 }, {},
    ];
    const desc = [...rows].sort((a, b) => compareDailyReturn(a, b, { date: "d", dir: "desc" })).map((r) => r.d ?? null);
    assert.deepEqual(desc, [1.234, 0.2, 0.05, -0.5, null, null]);
    const asc = [...rows].sort((a, b) => compareDailyReturn(a, b, { date: "d", dir: "asc" })).map((r) => r.d ?? null);
    assert.deepEqual(asc, [-0.5, 0.05, 0.2, 1.234, null, null]);
  });
});

describe("daily volume beside each daily return", () => {
  const finalizedBar = (day: number, close: number, volumeUsd: number | null | undefined): DailyBar => ({
    ts: DAY0 + day * DAY_SEC,
    high: close,
    close,
    fetchedAt: DAY0 + (day + 1) * DAY_SEC + 60,
    volumeUsd,
  });
  const now = DAY0 + 20 * DAY_SEC;

  it("returns volumeUsd in the same object as that day's return", () => {
    const series = dailyReturnsFromFinalized(
      [finalizedBar(0, 10, 100), finalizedBar(1, 12, 2_000), finalizedBar(2, 6, 3_000)],
      now,
      null,
    );
    assert.deepEqual(series.history[date(1)], { date: date(1), returnPct: 12 / 10 - 1, volumeUsd: 2_000 });
    assert.deepEqual(series.history[date(2)], { date: date(2), returnPct: 6 / 12 - 1, volumeUsd: 3_000 });
    // 第一根没有前一天收盘：收益缺，但这一天的成交量仍然属于它自己
    assert.deepEqual(series.history[date(0)], { date: date(0), returnPct: null, volumeUsd: 100 });
  });

  it("history return equals the dailyReturns value used by sort and filter", () => {
    const series = dailyReturnsFromFinalized(
      [finalizedBar(0, 10, 1), finalizedBar(1, 11, 2), finalizedBar(3, 13, 4), finalizedBar(4, 9, 5)],
      now,
      null,
    );
    for (const d of series.dates) assert.equal(series.history[d]!.returnPct, series.returns[d]);
    // 缺了 day 2：day 3 的收益缺，成交量仍是 day 3 自己的，不是 day 2 / day 4 的
    assert.deepEqual(series.history[date(3)], { date: date(3), returnPct: null, volumeUsd: 4 });
  });

  it("never takes volume from a neighbouring day", () => {
    const series = dailyReturnsFromFinalized(
      [finalizedBar(5, 1, 111), finalizedBar(6, 2, 222), finalizedBar(7, 3, 333)],
      now,
      null,
    );
    const window = dailyHistoryForWindow(series.history, [date(5), date(6), date(7)]);
    assert.deepEqual(window.map((e) => [e.date, e.volumeUsd]), [[date(5), 111], [date(6), 222], [date(7), 333]]);
  });

  it("does not expose volume of an unfinalized bar", () => {
    const provisional: DailyBar = { ts: DAY0 + 9 * DAY_SEC, high: 5, close: 5, fetchedAt: DAY0 + 9 * DAY_SEC + 60, volumeUsd: 999 };
    const series = dailyReturnsFromFinalized([finalizedBar(8, 4, 1), provisional], DAY0 + 10 * DAY_SEC + 60, null);
    assert.equal(series.history[date(9)], undefined);
    const [cell] = dailyHistoryForWindow(series.history, [date(9)]);
    assert.deepEqual(cell, { date: date(9), returnPct: null, volumeUsd: null });
  });

  it("missing candle, null and empty-string volume stay null; real 0 stays 0", () => {
    assert.equal(parseVolumeUsd(null), null);
    assert.equal(parseVolumeUsd(undefined), null);
    assert.equal(parseVolumeUsd(""), null);
    assert.equal(parseVolumeUsd("  "), null);
    assert.equal(parseVolumeUsd("abc"), null);
    assert.equal(parseVolumeUsd("-5"), null);
    assert.equal(parseVolumeUsd("0"), 0);
    assert.equal(parseVolumeUsd(0), 0);
    assert.equal(parseVolumeUsd("428000.5"), 428000.5);

    const series = dailyReturnsFromFinalized([finalizedBar(0, 1, 0), finalizedBar(1, 2, null)], now, null);
    const cells = dailyHistoryForWindow(series.history, [date(0), date(1), date(2)]);
    assert.deepEqual(cells.map((c) => formatCompactUsd(c.volumeUsd)), ["$0", "—", "—"]);
    assert.deepEqual(cells.map((c) => formatDailyReturn(c.returnPct)), ["—", "+100.0%", "—"]);
  });

  it("keeps same address on different chains apart", () => {
    const address = "0x1111111111111111111111111111111111111111";
    const byKey = new Map<string, DailyBar[]>([
      [`base:${address}`, [finalizedBar(0, 10, 1_000), finalizedBar(1, 20, 2_000)]],
      [`eth:${address}`, [finalizedBar(0, 10, 7), finalizedBar(1, 5, 8)]],
    ]);
    const cell = (chain: string) =>
      dailyHistoryForWindow(dailyReturnsFromFinalized(byKey.get(`${chain}:${address}`)!, now, null).history, [date(1)])[0]!;
    assert.deepEqual(cell("base"), { date: date(1), returnPct: 1, volumeUsd: 2_000 });
    assert.deepEqual(cell("eth"), { date: date(1), returnPct: -0.5, volumeUsd: 8 });
  });

  it("window cells follow the API window end with no hard-coded date", () => {
    const series = dailyReturnsFromFinalized(
      Array.from({ length: 10 }, (_, day) => finalizedBar(day, day + 1, (day + 1) * 1_000)),
      now,
      null,
    );
    const end = date(9);
    const cells = dailyHistoryForWindow(series.history, finalizedDateWindow(end));
    assert.equal(cells.length, 7);
    assert.deepEqual(cells.map((c) => c.date), Array.from({ length: 7 }, (_, i) => date(i + 3)));
    assert.deepEqual(cells.map((c) => c.volumeUsd), Array.from({ length: 7 }, (_, i) => (i + 4) * 1_000));
    const rolled = dailyHistoryForWindow(series.history, finalizedDateWindow(date(8)));
    assert.equal(rolled.at(-1)!.date, date(8));
    assert.equal(rolled.at(-1)!.volumeUsd, 9_000);
  });

  it("formats compact USD", () => {
    const cases: [number | null | undefined, string][] = [
      [0, "$0"], [842, "$842"], [1_240, "$1.24K"], [12_400, "$12.4K"], [428_000, "$428K"],
      [1_823_400, "$1.82M"], [23_400_000, "$23.4M"], [923_000_000, "$923M"], [1_210_000_000, "$1.21B"],
      [1_000, "$1K"], [999_999, "$1M"], [999.6, "$1K"], [0.4, "<$1"],
      [null, "—"], [undefined, "—"], [Number.NaN, "—"], [-1, "—"],
    ];
    for (const [input, expected] of cases) assert.equal(formatCompactUsd(input), expected, String(input));
  });

  it("date sort only reads returns: volume cannot change the order", () => {
    const rows = [
      { returns: { d: 0.1 } as DailyReturnMap, volume: 1 },
      { returns: { d: 0.5 } as DailyReturnMap, volume: 1_000_000_000 },
      { returns: { d: -0.2 } as DailyReturnMap, volume: 5_000_000_000 },
    ];
    const order = (list: typeof rows) =>
      [...list].sort((a, b) => compareDailyReturn(a.returns, b.returns, { date: "d", dir: "desc" })).map((r) => r.returns.d);
    const swapped = rows.map((r, i) => ({ ...r, volume: rows[rows.length - 1 - i]!.volume }));
    assert.deepEqual(order(rows), [0.5, 0.1, -0.2]);
    assert.deepEqual(order(swapped), order(rows));
  });
});
