import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const styles = readFileSync(new URL("../../styles.css", import.meta.url), "utf8");
const marketView = readFileSync(new URL("../../components/market-view.tsx", import.meta.url), "utf8");

describe("market table frozen identity columns", () => {
  it("keeps ★ / Token / Price / Age / FDV sticky with explicit left offsets and opaque background", () => {
    assert.match(styles, /\.market-star-sticky,\s*\.market-token-sticky,\s*\.market-price-col,\s*\.market-age-col,\s*\.market-fdv-col\s*\{[^}]*position:\s*sticky;[^}]*background:\s*var\(--color-bg\);/s);
    assert.match(styles, /\.market-star-sticky\s*\{[^}]*left:\s*0;/s);
    assert.match(styles, /\.market-token-sticky\s*\{[^}]*left:\s*2\.5rem;/s);
    assert.match(styles, /\.market-price-col\s*\{[^}]*left:\s*15rem;/s);
    assert.match(styles, /\.market-age-col\s*\{[^}]*left:\s*21\.25rem;/s);
    assert.match(styles, /\.market-fdv-col\s*\{[^}]*left:\s*24\.75rem;/s);
  });

  it("removes the period preset buttons", () => {
    assert.doesNotMatch(marketView, /PRESET_DAYS|MAX_CUSTOM_DAYS|applyCustom/);
  });

  it("applies the frozen classes to both header and body cells", () => {
    assert.match(marketView, /<th className="market-star-sticky/);
    assert.match(marketView, /<th className="market-token-sticky/);
    assert.match(marketView, /<td className="market-star-sticky/);
    assert.match(marketView, /<td className="market-token-sticky/);
  });
});
