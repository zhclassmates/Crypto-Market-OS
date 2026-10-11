import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");
const marketView = readFileSync(new URL("../../components/market-view.tsx", import.meta.url), "utf8");
const marketServer = readFileSync(new URL("./market-server.ts", import.meta.url), "utf8");

describe("market table frozen identity columns", () => {
  it("keeps ★ / × / Token / Price / Age / FDV sticky with explicit left offsets and opaque background", () => {
    assert.match(styles, /\.market-star-sticky,\s*\.market-hide-sticky,\s*\.market-token-sticky,\s*\.market-price-col,\s*\.market-age-col,\s*\.market-fdv-col\s*\{[^}]*position:\s*sticky;[^}]*background:\s*var\(--color-bg\);/s);
    assert.match(styles, /\.market-star-sticky\s*\{[^}]*left:\s*0;/s);
    assert.match(styles, /\.market-hide-sticky\s*\{[^}]*left:\s*2\.5rem;/s);
    assert.match(styles, /\.market-token-sticky\s*\{[^}]*left:\s*4\.25rem;/s);
    assert.match(styles, /\.market-price-col\s*\{[^}]*left:\s*16\.75rem;/s);
    assert.match(styles, /\.market-age-col\s*\{[^}]*left:\s*23rem;/s);
    assert.match(styles, /\.market-fdv-col\s*\{[^}]*left:\s*26\.5rem;/s);
  });

  it("removes the period preset buttons", () => {
    assert.doesNotMatch(marketView, /PRESET_DAYS|MAX_CUSTOM_DAYS|applyCustom/);
  });

  it("applies the frozen classes to both header and body cells", () => {
    assert.match(marketView, /<th className="market-star-sticky/);
    assert.match(marketView, /<th className="market-hide-sticky/);
    assert.match(marketView, /<th className="market-token-sticky/);
    assert.match(marketView, /<td className="market-star-sticky/);
    assert.match(marketView, /<td className="market-hide-sticky/);
    assert.match(marketView, /<td className="market-token-sticky/);
  });

  it("renders every qualified row without a frontend pagination slice", () => {
    assert.match(marketView, /\{tableRows\.map\(\(row\) =>/);
    assert.doesNotMatch(marketView, /PAGE_ROWS|tableRows\.slice\(0,\s*limit\)/);
  });

  it("does not render stale labels in market cells", () => {
    assert.doesNotMatch(marketView, />stale</i);
    assert.doesNotMatch(marketView, /<FieldStale/);
  });

  it("derives the shared seven-day header only from API ndWindowEnd", () => {
    assert.match(marketView, /finalizedDateWindow\(ndWindowEnd\)/);
    assert.match(marketView, /data-window-end=\{latestFinalizedDate \?\? ""\}/);
    assert.doesNotMatch(marketView, /calendarDateWindow\(now\)/);
    assert.doesNotMatch(marketView, /Math\.floor\(now \/ DAY_SEC\).*DAY_SEC/s);
    assert.doesNotMatch(marketView, /2026-\d{2}-\d{2}/);
  });
});

describe("daily return + volume cells", () => {
  it("renders return then volume, both from the same per-date history object", () => {
    assert.match(marketView, /t\.dailyHistory\?\.find\(\(entry\) => entry\.date === date\)/);
    assert.match(marketView, /const dailyReturn = day\?\.returnPct \?\? null;\s*const volumeUsd = day\?\.volumeUsd \?\? null;/);
    assert.match(marketView, /<div>\{formatDailyReturn\(dailyReturn\)\}<\/div>\s*<div className="market-daily-volume">\{formatCompactUsd\(volumeUsd\)\}<\/div>/);
    assert.match(styles, /\.market-daily-volume\s*\{[^}]*font-size:\s*10px;[^}]*color:\s*var\(--color-muted\);/s);
  });

  it("keeps date sort and filters on dailyReturns only", () => {
    assert.match(marketView, /compareDailyReturn\(a\.dailyReturns, b\.dailyReturns, primarySort\)/);
    assert.match(marketView, /matchesDailyFilters\(t\.dailyReturns \?\? \{\}, dailyFilters\)/);
    assert.doesNotMatch(marketView, /volumeUsd[^\n]*sort|sort[^\n]*volumeUsd/i);
  });

  it("server window comes from canonicalWindowEndTs, not a hard-coded date", () => {
    assert.match(marketServer, /const windowEndTs = canonicalWindowEndTs\(now\);/);
    assert.match(marketServer, /const windowDates = finalizedDateWindow\(ndWindowEnd\);/);
    assert.match(marketServer, /dailyHistoryForWindow\(dailySeries\.history, windowDates\)/);
    assert.match(marketServer, /SELECT chain, address, ts, high, close, volume,/);
    assert.doesNotMatch(marketServer, /20\d{2}-\d{2}-\d{2}/);
  });
});

describe("全市场 high-recall browse", () => {
  it("全市场 admits every delivered token; 连涨榜 stays on the pre-change candidate pool", () => {
    assert.match(marketView, /if \(board === "streak"\) return t\.streakPool !== false && formalStreakEligible\(/);
    assert.doesNotMatch(marketView, /return t\.changeNd != null && rankingQualityOk/);
  });

  it("defaults 全市场 to newness and returns to it when the date sort is cleared", () => {
    assert.match(marketView, /useState<SortMode>\(watchProp \? "added" : "newness"\)/);
    assert.match(marketView, /next === "streak" \? "streak" : "newness"/);
    assert.match(marketView, /if \(primarySort && !nextSort && board === "all" && !watchOnly\) \{\s*setSortKey\("newness"\);/);
  });

  it("server browse set = legacy prefilter ∪ has daily K ∪ newest N; search goes to the full registry", () => {
    const browseLimit = Number(marketServer.match(/export const MARKET_BROWSE_NEWEST = (\d+);/)?.[1]);
    assert.ok(browseLimit > 0 && browseLimit <= 3000, 'bounded initial browse keeps full-registry search');
    assert.match(marketServer, /const MARKET_BROWSE_SQL = `\(\$\{BOARD_PREFILTER\}\s*OR EXISTS \(SELECT 1 FROM daily_kline k/);
    assert.match(marketServer, /OR EXISTS \(SELECT 1 FROM market_newest w/);
    assert.match(marketServer, /search\s*\?\s*`WHERE \$\{MARKET_SEARCH_SQL\}/);
    // 不能再按 N 日累计 / 连涨在服务端剔除全市场 token
    assert.doesNotMatch(marketServer, /if \(!watch && changeNd == null && !streakBoardEligible\(liq\) && metrics\.streak == null\) continue;/);
  });

  it("全市场 daily cells never trim real candles by creation time; streak metrics keep their cutoff", () => {
    assert.match(marketServer, /dailyReturnsFromFinalized\(tokenBars, now, null\)/);
    assert.match(marketServer, /officialDailyMetrics\(tokenBars, now, created\.at, days, windowEndTs\)/);
  });

  it("uses a generic empty state because 全市场 no longer requires a complete N-day window", () => {
    assert.match(marketView, /没有匹配当前条件的代币/);
    assert.doesNotMatch(marketView, /没有具备完整.*涨跌数据的代币/);
  });
});
