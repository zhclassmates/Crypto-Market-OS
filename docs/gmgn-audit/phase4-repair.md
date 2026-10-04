# Phase 4 — Repair (code + verification, not deployed)

## Resume note

- Resumed after a quota interruption. Phase 1/2/3 were not repeated; no GMGN
  request was issued by this audit.
- The original Phase 4 instruction text was not available in this resume; the
  scope below is taken from the partial Phase 4 changes found in the working
  tree (written 2026-10-03 09:51–10:04 local, after the Phase 3 checkpoint at
  09:31) and from the Phase 3 issue grading.
- Those partial changes were audited before continuing (see "Audit of partial
  work").

## Changes mapped to Phase 3 issues

| Issue | Fix | Files |
|---|---|---|
| P3-01 HIGH | Endpoint-owned snapshot *patch*: only keys an endpoint actually returned are written; absent key = untouched, explicit null = cleared, 0 = valid value. Trench `volume_24h`/`swaps_24h` normalized; Signal maps `cur_data.holder_count` / `top_10_holder_rate` and no longer writes price/activity. Event metadata keeps `volume_24h`/`swaps_24h`. | `rh_v2/market_lanes.py`, `rh_v2/market_research.py` |
| P3-02 MEDIUM | `refresh_daily_metrics_for_utc_day` recomputes all materialized metrics once per UTC day (startup, every heartbeat check, `run_pass`); API `return2d/3d/5d` now recomputed at request time from finalized candles instead of reading `daily_metrics`. | `rh_v2/market_research.py`, `rh_v2/market_lanes.py`, `src/lib/rh/market-server.ts` |
| P3-03 MEDIUM | Streak board pattern/down/flat/days/latestClose use FINALIZED rows only; a token whose newest calendar-closed bar is PROVISIONAL is omitted until finalized. | `src/lib/rh/kline-server.ts`, `src/lib/rh/streak.ts` |
| P3-04 MEDIUM | Volume(24h) rendered without `$`; real `0` shown as `0`, missing/invalid as `—`. | `src/components/market-view.tsx` |
| P3-05 MEDIUM | Per-field `*_source` / `*_updated_at` columns (price, pc_24h, volume_24h, liquidity, market_cap, holders, swaps); API returns them; UI tooltips + stale badges per cell; price age uses its own field timestamp when present. API reads the columns only if they exist (safe before migration). | all of the above |
| P3-06 MEDIUM | Security keeps full canonical JSON plus nullable `is_honeypot/is_blacklist/is_open_source/is_renounced/top_10_holder_rate`; UI shows "Security checked / SECURITY RISK" with details. | `rh_v2/market_lanes.py`, `rh_v2/market_research.py`, UI |
| P3-07 LOW | Canonical candle UPSERT derives `is_closed` from the sticky `finalized_at`, so they cannot diverge. | `rh_v2/market_research.py` |

Not addressed (out of repair scope / no lineage): P3-A01, P3-L01, P3-L02.
History of rolling volume/swaps lost before this fix is **unrecoverable** from
the current DB; it refills by normal collection after deployment.

## Audit of partial work

- Field semantics checked against Phase 2 matrices: security flags are
  boolean-or-null (matches `_optional_bool`); market cap never null in any
  sampled endpoint (present-key selection is safe); Signal `cur_data` always
  carries holder/liquidity/top10.
- Defect found and fixed in `scripts/phase4-repair-dry-run.py`: its oracle did
  not apply the token-creation-day candle filter that production uses, which
  produced 22 false-positive mismatch rows (all 22 had bars before the
  creation day). After adding an independent `after_creation` rule the
  oracle and production agree exactly.

## Verification

| Check | Result |
|---|---|
| Python suite `rh_v2/test_phase1.py` (temp SQLite) | 46/46 pass |
| TypeScript `src/lib/rh/streak.test.ts` | 54/54 pass |
| `scripts/phase4-oracle.py` (synthetic fixtures, temp DB) | 6/6 checks; production == independent oracle |
| `npm run typecheck` / `npm run build` | pass / pass |
| Read-only prod dry-run (`mode=ro`, `query_only`), integrity | `ok`; 13,888 snapshots, 12,383 blank `volume_24h`, 12,451 NULL `swaps`, 2,836 NULL holders; 0 materialized value mismatches; 9,977 rows not yet recomputed today |
| Rehearsal on a backup copy of prod (scratchpad) | migration 0.09 s; UTC-day refresh of 13,889 tokens 0.26 s; second call no-op; integrity `ok`; oracle afterwards: 0 stale, 0 mismatches |
| Dev render (market table, unmigrated prod DB) | renders 104 rows, no `$` on volume, source/age tooltips present, no horizontal overflow; only console error is the cross-origin branding script on localhost |

`production_write_performed: false` — production `market.sqlite` was opened
read-only only.

## Operational observation

`com.market.collector` (GMGN) and `com.cryptoos.market-structure` are running
again (started 2026-10-03 08:57 local, i.e. before the Phase 4 edits), despite
`pause-log.txt` recording them paused on 10-02. They therefore run
**pre-Phase-4 code**; production schema has none of the new columns. GMGN
traffic seen in the health panel comes from that collector, not this audit.

## Deployment (not performed — needs owner decision)

1. Restart `com.market.collector` so it loads the new code; first `with_db`
   migrates columns, `run_loop` startup performs the UTC-day refresh.
2. Re-run `scripts/phase4-repair-dry-run.py` read-only: expect 0 mismatches.

## Known trade-offs to review

- Until migration + recollection, every volume/holder/market-cap cell shows a
  stale badge (age unknown). This is honest but noisy.
- The streak board hides tokens with a PROVISIONAL tail. Right after UTC
  midnight this can be a large share of rows (Phase 3 saw 552/1,255
  previous-day bars still provisional at 01:22 UTC) until the Kline lane
  refetches.
- Market cap is still formatted with `$` though Phase 2 found its currency
  unencoded for Trending/Hot/Trenches (only Signal `usd_market_cap` is
  labelled USD). Not part of P3-04.
