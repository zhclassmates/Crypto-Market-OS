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
  dailyReturnsFromFinalized,
  formatDailyReturn,
  latestFinalizedDates,
  matchesDailyFilters,
  matchesDailyReturn,
  reconcileDailyFilters,
  utcDateKey,
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

describe("15-day calendar window", () => {
  it("ends on today with 15 dates and no future dates", () => {
    const now = Date.UTC(2026, 9, 4, 12) / 1000;
    const dates = calendarDateWindow(now);
    assert.equal(dates.length, 15);
    assert.equal(dates[0], "2026-09-20");
    assert.equal(dates[14], "2026-10-04");
    assert.ok(!dates.includes("2026-10-05"));
  });

  it("default 7-day viewport is the last 7 dates, today rightmost as T+3", () => {
    const now = Date.UTC(2026, 9, 4, 12) / 1000;
    const today = utcDateKey(now);
    const view = calendarDateWindow(now).slice(-MARKET_DATE_VIEWPORT);
    assert.deepEqual(view, [
      "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
    ]);
    assert.deepEqual(view.map((d) => fmtTOffset(dateTOffset(d, today))), ["T-3", "T-2", "T-1", "T0", "T+1", "T+2", "T+3"]);
  });

  it("rolls correctly across a year boundary", () => {
    const now = Date.UTC(2027, 0, 2, 0, 1) / 1000;
    const dates = calendarDateWindow(now);
    assert.equal(dates[0], "2026-12-19");
    assert.equal(dates[14], "2027-01-02");
  });

  it("renders a missing return as an em dash", () => {
    const returns: DailyReturnMap = { "2026-10-02": 0.124 };
    assert.equal(formatDailyReturn(returns["2026-10-04"]), "—");
  });

  it("renders finalized historical returns normally", () => {
    assert.equal(formatDailyReturn(0.124), "+12.4%");
    assert.equal(formatDailyReturn(-0.072), "−7.2%");
  });

  it("shifts by one day and T0 moves with it, keeping calendar keys stable", () => {
    const today = Date.UTC(2026, 9, 4, 12) / 1000;
    const tomorrow = today + DAY_SEC;
    const first = calendarDateWindow(today);
    const second = calendarDateWindow(tomorrow);
    assert.equal(first[1], second[0]);
    assert.equal(second[14], "2026-10-05");
    assert.equal(dateTOffset("2026-10-02", utcDateKey(tomorrow)), 0);

    const filters: DailyReturnFilters = { "2026-09-20": "UP", "2026-10-03": "DOWN" };
    assert.deepEqual(reconcileDailyFilters(filters, second), { "2026-10-03": "DOWN" });
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
