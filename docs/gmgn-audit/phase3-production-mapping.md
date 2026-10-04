# Phase 3 — Production Mapping

## Scope and checkpoint

- Resumed from `progress.md`; Phase 1 and Phase 2 were not repeated.
- No GMGN request was issued.
- Production code and production SQLite files are read-only for this audit.
- The previously recorded 22 raw response files are no longer present under
  `/tmp/gmgn-audit/raw/` in this resumed environment. Phase 2's preserved
  endpoint matrices are used as the raw-schema evidence instead.
- Requested aggregate files `field-matrix.md`, `kline-findings.md`, and
  `data-capabilities.md` are not present at the paths supplied in the resume
  request. The endpoint matrices under `docs/gmgn-audit/field-matrix/` and
  `phase2-field-matrix-summary.md` remain present.

## Source -> parser

### Production entry map

| GMGN source | Production request/parser | Phase 2 shape match | Mapping result |
|---|---|---|---|
| Trending | `market_collect.fetch_trending` -> `data.rank[]` | Yes | `price`, `volume`, `swaps`, `holder_count`, liquidity and market cap reach the common row writer. |
| Hot searches | `market_lanes.fetch_hot` -> wrapper `tokens[]` (fallback `rank[]`) | Yes | The 24h row fields reach the common row writer. The wrapper's explicit `interval=24h` is discarded, while production hard-codes source variant `24h`. |
| Trenches | `market_research.parse_trench_items` -> three production buckets | Bucket selection matches | The parser preserves the raw row names, but the common writer reads `volume` and `swaps`; Phase 2 established the stable trench names are `volume_24h` and `swaps_24h`. Thus trench 24h volume and swaps are not normalized into the fields consumed downstream. `buys_24h` and `sells_24h` are also not carried into a dedicated production field. |
| Signal | `market_research.parse_signal_items` | Top-level list and nested objects match | Address, current-labelled liquidity, top-level market cap, signal type and creation time are mapped. Current `cur_data.holder_count` and `cur_data.top_10_holder_rate` are dropped. The parser also probes price paths that Phase 2 did not observe, so price is normally absent. Zero-only activity fields are not promoted, which avoids fabricating activity. |
| Kline | `market_collect.fetch_kline` -> `market_research.write_daily_candles` | Yes | `time`, OHLC, `volume`, and `amount` are parsed. Milliseconds are normalized by `market_db.unix_ts`; bars are floored to UTC day. Missing OHLC components are substituted with close; rows lacking time/close are skipped. |
| Security | `market_lanes.job_security` | Request shape matches | There is no semantic parser. Production canonicalizes the full response only to compute a 16-character SHA-256 prefix stored as `security_note`; contract/security and concentration fields are not retained in queryable form. |

### Boundary findings

1. **Trench metric name mismatch:** Phase 2's direct 24h fields do not match the
   common writer's trending/hot field names. This is a deterministic lineage
   break, not an upstream-data absence.
2. **Signal current holder semantics are dropped:** the parser correctly prefers
   `cur_data.liquidity`, but does not do the analogous mapping for current
   holder count or top-10 concentration.
3. **No wallet counts are invented:** `swaps`, `buys`, `sells`,
   `fresh_wallet_rate`, and `new_wallet_volume` are not parsed as unique or
   active wallet counts. This agrees with Phase 2 evidence.
4. **Kline finality is not read from GMGN:** the raw schema has no finalized
   flag. Production derives finality later from bar-open plus observation time;
   this boundary does not claim a source-provided final flag.
5. **Security is freshness/change detection only:** a hash can show that a blob
   changed, but cannot support field-level API/UI security semantics or explain
   which risk changed.

### Module verdict

`source -> parser` is **PARTIAL**. All six production request shapes have an
entry path, but trenches lose stable 24h metric names, signal loses current
holder fields, and security is reduced to an opaque digest.

## Parser -> DB

### Storage map

| Parsed fact | Production storage | Preservation result |
|---|---|---|
| Discovery identity, price, liquidity, market cap, rank | `discovery_event` plus `token_registry` | Preserved per source and 300-second bucket. |
| Discovery volume / swaps / buys / sells | `token_snapshot` only for the common `volume` / `swaps` names | No historical preservation. `discovery_event` has no columns for these metrics and its compact metadata excludes them. There are no buy/sell columns. |
| Current holder count | `token_snapshot.holders`; optionally compact event metadata | Snapshot only. Trending/hot/trench metadata can retain the observed count, but signal's parser drops both holder layers before persistence. |
| Kline OHLCV/amount | Canonical `token_candle`, mirrored into `daily_kline` | Preserved with per-bar observation/finalization timestamps in `market.sqlite`. |
| Security response | `token_snapshot.security_note` | Only a 16-character digest is stored; security fields and the full response are not stored. |
| Derived streak/returns | `daily_metrics` | Materialized current result, not raw GMGN data and not a full history. |

### Deterministic write behavior

- `write_gmgn_rows` uses a full UPSERT for GMGN snapshot columns. Missing
  parser values become empty strings or NULL and replace the prior snapshot;
  unlike `upsert_snapshot_numbers`, this path does not use `COALESCE` to retain
  prior non-empty values.
- Therefore a trench row writes empty `volume_24h` and NULL `swaps` despite the
  source having `volume_24h`/`swaps_24h`; a signal row normally writes empty
  price/volume and NULL holders/swaps while updating liquidity/market cap.
- `token_snapshot` has no last-source/provenance column. Once overwritten, the
  database cannot distinguish upstream absence from parser-name mismatch or
  source precedence.
- `fresh_wallet_rate` and `new_wallet_volume` have no wallet-count destination.
  This is semantically safer than coercing them into counts.

### Read-only production DB evidence

Observed from `market.sqlite` during this module:

- `token_snapshot`: 12,584 rows; `discovery_event`: 131,938;
  `token_candle` and `daily_kline`: 45,674 each; `daily_metrics`: 12,585.
- Blank snapshot `volume_24h`: BASE 2,092/2,240, ETH 197/477,
  ROBINHOOD 818/1,207, SOL 8,001/8,660. NULL `swaps` has a nearly identical
  footprint. This is consistent with the overwrite path, though lack of row
  provenance prevents attributing every blank to a specific source.
- All 59,508 trench events have no volume field in `metadata_json`, even though
  Phase 2 established the raw rows contain `volume_24h`. No discovery source
  stores volume in event metadata.
- All 8,517 signal events have NULL event price and no holder metadata; all do
  have liquidity.
- The two market Kline tables currently have no missing mirror rows, no
  `is_closed=1` row lacking `finalized_at`, no open row with `finalized_at`, and
  no cross-table `finalized_at` mismatch.

### Separate `kline.sqlite`

The legacy `kline_collect.py` path writes `kline.sqlite.daily_kline` with only
OHLCV and no `fetched_at`, `finalized_at`, `amount`, or closed/provisional
state. It is therefore not semantically equivalent to the canonical
`market.sqlite.token_candle` lineage used by the current research metrics.

### Module verdict

`parser -> DB` is **PARTIAL**. Kline canonical storage is internally mirrored,
but discovery activity fields lack history/provenance, trench/signal writes can
erase richer current snapshots, holder history is unavailable, and security is
stored only as an opaque change digest.

## DB -> API

### Server-function map

| DB data | Server surface | API behavior |
|---|---|---|
| Registry + snapshot + daily Kline | `fetchMarketRank` | Returns market fields, snapshot holders/volume, TypeScript-recomputed finalized-candle metrics, and separately the Python-materialized `return2d/3d/5d`. |
| Snapshot hot columns | `fetchMarketHot` | Returns price, volume and liquidity updates, but no holders, swaps, security, or row-source provenance. |
| Daily Kline | `fetchKlineBoard` | Returns non-OPEN candles with volume plus pattern/streak summaries. PROVISIONAL candles remain in the candle/pattern payload, while official streak comes from finalized candles. |
| Source health | `/api/health/market` and rank/hot clocks | Health route exposes every source; rank/hot's compact `gmgn` clock exposes only `source='gmgn'` (Trending). |

### Findings

1. Snapshot blanks cross the boundary as ordinary empty strings. Neither rank
   nor hot attaches field-level availability, source, observation time, or a
   reason for missing volume/holders.
2. Rank/hot freshness metadata cannot describe the mixed-source row. The row
   can be last overwritten by Hot, Trenches, or Signal, while the attached
   `gmgn` clock is Trending-only. `chainTs` is only `MAX(token_snapshot.ts)` per
   chain, not the timestamp of each returned field or row.
3. `token_snapshot.swaps` and `security_note` are not selected. Buys/sells and
   wallet counts have no DB columns and therefore no API path. The API does not
   mislabel swaps as wallets, but it also cannot expose transaction or security
   semantics collected upstream.
4. `fetchMarketRank` computes `changeNd`, `change1d`, streak and streak return
   in TypeScript from `daily_kline`, while also returning Python-materialized
   `return2d/3d/5d` from `daily_metrics`. This is a dual implementation and a
   possible drift boundary; detailed equivalence is audited in the dedicated
   return/streak modules.
5. `fetchKlineBoard` explicitly removes only `OPEN` rows from its raw candle
   list. It labels and returns `PROVISIONAL` rows, but its `pattern`, `days`,
   `downDays`, and `flatDays` are computed from all non-OPEN rows. The official
   `upDays` uses finalized-only logic. The response therefore mixes official
   and provisional aggregates in one object.
6. `market.sqlite` is the API source. The separate `kline.sqlite` and
   `rhv2.sqlite` are not read by these market/Kline server functions.

### Module verdict

`DB -> API` is **PARTIAL**. Finalized Kline fields reach the server functions,
but source/freshness semantics do not follow mutable snapshot fields, activity
and security data are absent, and the Kline-board contract mixes finalized and
provisional aggregates.

## API -> UI

### UI map

| API field/group | UI consumer | Presentation result |
|---|---|---|
| Price, rolling 24h change, volume, liquidity, market cap, holders | `MarketView` table | All are sortable/displayed. Price and 24h change get Trending-clock staleness; liquidity gets its DB observation age. Volume, market cap and holders do not get field-level age/source. |
| Finalized daily metrics | `MarketView` | `change1d`, streak, N-day cumulative, streak return and drawdown are labelled as finalized-Kline metrics and distinguish missing streak from zero. |
| Python `return2d/3d/5d` | `MarketView` type only | Carried in the rank payload/type but not rendered or used for sorting/filtering. The visible N-day value is the TypeScript `changeNd`. |
| Kline-board candles and mixed aggregates | `StreakView` | Displays latest close, days, pattern, down/flat runs and official up-streak. Candle status/finalization timestamps are not represented in the component's local type or detail display. |
| Source health | `MarketHealthBar` / health lab | Separate health UI exists for per-source status, but it is not attached to individual volume/holder cells. |

### Findings

1. `Volume(24h)` uses `fmtUsd`, which always adds `$` for non-zero values.
   Phase 2 established that the GMGN payload does not encode the volume unit.
   The UI therefore presents an unverified currency semantic as certain.
2. Empty, invalid, and numeric zero volume all render as the same dash. This
   hides the distinction between missing data, parser-induced blank values, and
   a real upstream zero.
3. Volume and holder cells have no stale/source badge. Their containing row is
   decorated with a Trending-only clock, but even that clock is shown only on
   Price/24H. Current holder count is consequently presented without an as-of
   time despite being snapshot-only evidence.
4. The main market table correctly labels N-day cumulative and streak as based
   on FINALIZED UTC daily bars, shows Provisional/Final status, and distinguishes
   insufficient streak data (`—`) from a valid zero.
5. The separate Streak view mixes contracts: `upDays` is official finalized
   streak, while Pattern, down/flat run counts, day count and `latestClose`
   include PROVISIONAL bars (all non-OPEN rows). The UI does not surface candle
   status, so users cannot see which displayed pattern point is provisional.
6. No UI labels swaps/buys/sells as wallet counts. There is no active-wallet,
   unique-buyer/seller, or historical-holder UI lineage.

### Module verdict

`API -> UI` is **PARTIAL**. The main finalized-Kline labels are strong, but
snapshot freshness/provenance is lost at the cells, the 24h volume currency is
asserted without source evidence, and the Streak page presents a mixed
finalized/provisional pattern without disclosure.

## Complete lineage

| Metric / fact | Raw -> parser -> DB -> API -> UI | End-to-end verdict |
|---|---|---|
| Snapshot price | Discovery rows -> common writer -> snapshot -> rank/hot -> table | **PARTIAL**: value reaches UI, but mixed-source row provenance/freshness is not preserved. |
| Snapshot liquidity / market cap | Discovery rows -> snapshot/event -> rank/hot -> table | **PARTIAL**: liquidity has observation age; source/unit still not encoded. Market cap has neither field-level age nor source. |
| Rolling 24h volume | Trending/hot `volume`; trench `volume_24h` | **BROKEN/PARTIAL**: trending/hot can reach UI, trench name is lost, snapshot can be blank-overwritten, history/source/unit are lost, and UI asserts USD. |
| Daily candle volume | Kline `volume` -> both Kline tables -> Kline-board API | **PARTIAL, not visible**: field reaches the component payload but is not rendered; unit remains unknown. |
| Swaps / buys / sells | Discovery raw activity fields | **INCOMPLETE**: trending/hot swaps can reach snapshot only; trench suffixes are not normalized; API/UI omit swaps; buys/sells have no production columns. |
| Current holder count | Discovery snapshot -> snapshot/event metadata -> rank -> table | **PARTIAL**: visible current snapshot for several sources, but Signal current holder is dropped and no row-level as-of/source is shown. |
| Historical holders / new holders | No historical source series | **NO LINEAGE**. A current snapshot must not be used to derive historical holder change. |
| Active/unique/new wallets | No direct raw count | **NO LINEAGE**. Rates, volumes and swap-side counts are not wallet counts. |
| Kline finalization | Bar open + audit observation time -> DB derived status -> API classifier -> UI | **DERIVED LINEAGE**: defensible observation-time contract; not a GMGN-provided flag. Dedicated audit follows. |
| N-day return | Kline close history -> finalized bars -> server calculation -> market table | **COMPLETE for visible `changeNd`**, subject to finalization/continuity/quality rules. Python materialized returns form a separate, unused UI branch. |
| Positive streak | Kline close history -> finalized bars -> server calculation -> market table | **COMPLETE on the main market table**. The separate Streak page mixes provisional pattern aggregates with the official up-streak. |
| Security semantics | Security object -> digest -> no API/UI | **BROKEN** for semantic lineage; only change detection survives. |

### Module verdict

The only complete user-visible GMGN research lineages are the main table's
finalized-candle N-day return and official positive streak. Snapshot market
fields are operationally visible but not semantically complete because source,
unit, and field-level observation time do not travel with the values.

## Kline finalization

### Contract

- GMGN supplies a UTC-midnight bar open and no finalized flag.
- Production defines `bar_end = bar_open + 86400` and accepts a bar as
  FINALIZED only when that bar's observation timestamp is at or after bar end
  and the bar lies inside the 100-day request window associated with that
  observation.
- Current UTC-day bars are OPEN. Calendar-closed bars without post-close proof
  are PROVISIONAL indefinitely; current time or migration time cannot promote
  them.
- Python write/repair logic and TypeScript read classification use the same
  86,400-second end boundary and 100-day observation window.

### Read-only DB evidence at `2026-10-03T01:22Z`

- Current-day (`2026-10-03`) bars: 598, all not finalized.
- Previous-day (`2026-10-02`) bars: 1,255; 703 finalized by post-close
  observation and 552 provisional.
- Older bars: 43,861; 43,693 finalized and 168 provisional.
- No finalized timestamp precedes bar end; no finalized bar is outside the
  100-day proof window; no candle lacks `fetched_at`; no bar is off UTC
  midnight; no candle has a non-positive/missing close.
- `token_candle` and `daily_kline` have no finalization mismatch and no missing
  mirror rows at the checkpoint.

### Verification

- Python temporary-DB suite: 39/39 passed.
- TypeScript streak/finalization suite: 49/49 passed.
- Tests cover intraday/provisional persistence, exact bar-end finalization,
  post-close refetch, missing observation time, request-window bounds, creation
  date filtering, and exclusion of unfinished bars from official returns.

### Residual boundaries

1. `kline.sqlite.daily_kline` has no `fetched_at`/`finalized_at`; it must not be
   treated as interchangeable with the market research Kline tables.
2. In the canonical UPSERT, `finalized_at` is sticky via `COALESCE`, while
   `is_closed` is replaced by the newest computed value. An unusual later row
   outside the proof window could make those columns disagree. No such row
   exists now, and API classification uses timestamps rather than `is_closed`.
3. `DailyBar.sourceClosed` is documented in TypeScript but intentionally not
   used by `barStatus`; this is compatible with Phase 2 because GMGN supplies
   no final flag, but the comment overstates current behavior.

### Module verdict

Kline finalization is **PASS for the canonical `market.sqlite` research
lineage**. The rule is conservative and evidence-based. The separate legacy
Kline database and the Streak page's provisional pattern aggregates remain
outside that pass.

## N-day return

### Formula and eligibility

- Both Python and TypeScript define return N-day as
  `latest finalized close / close N contiguous finalized UTC bars earlier - 1`.
- The calculation requires N+1 positive-close bars and exact 86,400-second
  adjacency across the complete window. Missing or provisional bars yield
  NULL, not zero. Returns are not sums of daily percentages.
- A PROVISIONAL last calendar-closed bar disables all official returns even if
  an older finalized subsequence is available.
- TypeScript adds `LOW_BASE` and `EXTREME_RETURN` quality flags without changing
  the raw ratio. The formal all-market board excludes flagged rows.

### Two production branches

1. `fetchMarketRank` loads daily bars and recomputes the visible `changeNd` at
   request time. This branch observes the current UTC day boundary and current
   PROVISIONAL tail.
2. Python materializes only 2d/3d/5d into `daily_metrics`. The API also returns
   these as `return2d/3d/5d`, but `MarketView` does not render or sort on them.

### Read-only materialization reconciliation

An integrity-checked temporary copy of production `market.sqlite` was used;
the production file was not modified. At the checkpoint:

- Registry and `daily_metrics` each contained 12,602 tokens; no metric row was
  missing and no `as_of_date` differed from the last finalized bar.
- 674 tokens had a PROVISIONAL last calendar-closed bar.
- 82 tokens had stale materialized returns: 82 `return_2d`, 61 `return_3d`,
  and 50 `return_5d` values (193 fields total) were non-NULL while a current
  contract recomputation required NULL.
- All 82 stale rows had `calculated_at` before the current UTC day. Distribution:
  ETH 34, ROBINHOOD 28, SOL 20, BASE 0.

Cause: a calendar transition can turn yesterday's OPEN candle into today's
PROVISIONAL tail without any database write. `daily_metrics` is refreshed on a
token write, not globally at UTC rollover, so an older non-NULL return remains
until that token is refreshed. This is materialization staleness, not a formula
error.

### Module verdict

- Visible request-time `changeNd`: **PASS**.
- Python `daily_metrics.return_2d/3d/5d`: **FAIL (UTC-rollover staleness)**.
- Current UI impact: none found, because those materialized return fields are
  carried by the API but unused by `MarketView`; other/future API consumers
  could observe them.

## Streak

### Official definition

- The official positive streak is the adjacent tail of FINALIZED UTC daily
  closes satisfying `close[d] > close[d-1]`.
- A missing day, equal/down close, or loss of adjacency stops the streak.
- Fewer than two adjacent finalized bars is insufficient (NULL / `—`), while
  an adjacent last pair that did not rise is a valid zero.
- A PROVISIONAL last calendar-closed bar makes the official result unavailable;
  production does not fall back silently to an older finalized tail.

Python and TypeScript implement the same comparison and adjacency rules. The
main market table computes streak, streak return, and drawdown from current
bars at request time. Existing Python and TypeScript tests pass the missing vs
zero, unfinished-day, missing-day, long-streak, and high-drawdown cases.

### Materialized streak reconciliation

Against the same integrity-checked snapshot used for N-day returns:

- 105/12,602 `daily_metrics.streak` rows retained a numeric value where a
  current recomputation required NULL because the newest calendar-closed bar
  was PROVISIONAL.
- All 105 were calculated before the current UTC day. Distribution: ROBINHOOD
  42, ETH 38, SOL 25, BASE 0.
- This is the same UTC-rollover invalidation gap as materialized returns.
  `fetchMarketRank` does not select `daily_metrics.streak`, so the main table is
  not using the stale column.

### Streak-page divergence

`fetchKlineBoard.upDays` uses the official finalized-only implementation.
However, `pattern`, `downDays`, `flatDays`, `days`, and `latestClose` use every
non-OPEN bar, including PROVISIONAL. `StreakView` presents them together without
status labels. Consequently the displayed pattern and latest close can move on
an unfinalized candle while the displayed up-streak remains unchanged.

### Module verdict

- Main market-table official streak: **PASS**.
- `daily_metrics.streak`: **FAIL (UTC-rollover staleness)**.
- Separate Streak-page pattern/down/flat/day aggregates: **PARTIAL / mixed
  finalization contract**.

## Volume

### Distinct volume facts

| Fact | Source/window | Production result |
|---|---|---|
| GMGN rolling/request 24h volume | Trending/hot `volume`; trenches `volume_24h`; signal activity zero-only | Trending/hot can populate `token_snapshot.volume_24h`. Trench name is not normalized, and signal/common writes can replace it with blank. |
| GMGN daily candle volume | Kline `list[].volume` | Stored in both market Kline tables and returned by the Kline-board API. Not rendered by `StreakView`. |
| GMGN candle `amount` | Kline `list[].amount` | Stored in the canonical/mirror tables but not exposed by current APIs. Unit/meaning is undefined. |
| DexScreener 24h volume | `token_snapshot.volume_ds` | Separate field/source. It does not repair or validate GMGN volume lineage and is not the table's `Volume(24h)` cell. |

### Preservation and current footprint

From the fixed read-only snapshot:

- 11,119 of 12,601 snapshot rows had blank `volume_24h`: BASE 2,089/2,241,
  ETH 194/477, ROBINHOOD 818/1,207, SOL 8,018/8,676.
- None of 132,599 discovery events retained `volume` or `volume_24h` in compact
  metadata. There is no historical audit trail for the rolling value.
- All 45,848 canonical candle rows had non-NULL, non-zero daily volume; 4,788
  had NULL `amount`. Presence does not establish either field's unit.

### Semantic findings

1. Rolling/request-window volume and UTC daily candle volume are different
   measurements and cannot substitute for each other.
2. Phase 2 found no currency/unit field for either. The market UI nevertheless
   formats GMGN `volume_24h` as dollars.
3. The current schema cannot explain blank rolling volume because it stores no
   row source and no volume history. A blank may reflect a parser suffix
   mismatch, signal overwrite, or true absence.
4. A real zero and a missing/invalid value both render as `–`, removing another
   useful distinction.

### Module verdict

- GMGN rolling 24h volume: **FAIL end-to-end reliability**.
- GMGN daily candle volume: **PARTIAL** (stored and API-carried, but unit is
  unknown and current UI does not display it).
- No evidence supports treating either as a wallet count or deriving one from
  volume.

## Wallet / holder

### GMGN semantics

- `holder_count` is a point-in-time discovery/signal snapshot. GMGN Kline has
  no holder field, and the audited endpoints supply no historical holder
  series.
- `swaps = buys + sells` is a transaction-side count identity, not a unique
  wallet identity. The GMGN payload supplies no active-wallet, unique-buyer,
  unique-seller, new-holder, or new-buyer count.
- `fresh_wallet_rate` is a ratio with an unspecified denominator/window.
  `new_wallet_volume` is a sparse volume-like field and was zero-only in the
  Phase 2 sample. Neither is a wallet count.

### Production preservation

- Trending/hot/trench holder snapshots reach `token_snapshot.holders` and
  `discovery_event.metadata_json`. Signal's explicitly current
  `cur_data.holder_count` and `top_10_holder_rate` are dropped by its parser.
- The common snapshot UPSERT replaces holders with NULL when a source does not
  map the field. The fixed snapshot had 2,560 NULL holder rows and 281 explicit
  zero rows. The API/UI exposes the surviving value without source/as-of time.
- Repeated collection creates an opportunistic observation log: Trending had
  37,600 holder observations, Hot 26,764, and Trenches 59,508. In total 5,381
  tokens had two or more observations. This is conditional on discovery-source
  membership, has no guaranteed cadence, and is not consumed by the API/UI; it
  is not an upstream GMGN historical-holder series.
- `token_snapshot.swaps` was populated on only 1,414 of 12,601 snapshot rows in
  the fixed copy. It is not selected by current APIs. There are no production
  GMGN columns for buys, sells, or unique/active/new wallet counts.

### Separate non-GMGN pipeline

`rhv2.sqlite` scoring has a distinct lineage: periodic `snapshots.holders` are
filled from Blockscout, and buyer fields come from GeckoTerminal pool flows.
Its 6h/24h holder-growth and buyer/transaction ratios must be attributed to
those sources, not to GMGN. GMGN's lack of a historical holder endpoint does
not invalidate that independent observation history, but the two pipelines
cannot be used as evidence for each other.

### Module verdict

- Current GMGN holder count: **PARTIAL snapshot-only lineage**.
- GMGN historical holder series: **NOT PROVIDED**; production has only
  opportunistic repeated observations.
- GMGN active/unique/new wallet counts: **NOT PROVIDED / no lineage**.
- Swap-side counts are not mislabelled as wallet counts in the audited GMGN
  path: **PASS on semantic non-substitution**.

## `rhv2.sqlite` drift

### Evidence

- Manifest baseline SHA-256: `9c4890f1a962e6600b9d265220f9395e5b0d744eef7e6e20250fd1bd357edbfc`.
- Phase 3 observed SHA-256: `034d7ec0971690e37b41e0cd11c3094451731223265712579122360d1ba03ee5`.
- Phase 2 had already recorded drift and mtime `2026-10-03T00:03:42Z`.
  Phase 3 observed a later mtime `2026-10-03T01:04:56Z`.
- `PRAGMA integrity_check` returned `ok`.
- The file is not tracked in Git HEAD, and the audit retained only the baseline
  hash, not a baseline database copy. Exact row-by-row baseline diff is
  therefore unavailable.

### Attribution

`pause-log.txt` records that `com.rhv2.collector` was intentionally not paused
because it does not use GMGN. The current database corroborates an hourly
production run:

- `meta.last_run.ts = 1790989200` (`2026-10-03T01:00:00Z`), phase `done`.
- Latest snapshot timestamp is 01:00 UTC with 179 rows; latest score timestamp
  is 01:00 UTC with 125 rows.
- The database mtime is 01:04:56 UTC, consistent with that run finishing.

This is high-confidence expected out-of-band production drift from the separate
collector, not a write by this audit. No restore was attempted.

### Lineage impact

- GMGN market and Kline server functions read `market.sqlite`, not
  `rhv2.sqlite`; this drift does not alter the audited GMGN rank/Kline rows.
- `rhv2.sqlite` backs a separate scoring lineage with its own external sources.
  Its changing holder/buyer observations must not be used to validate GMGN raw
  semantics.
- Because the database remained live, its hash alone is not a stable audit
  invariant unless that independent collector is paused or a transactionally
  consistent snapshot is captured at baseline.

### Module verdict

`rhv2.sqlite` drift is **EXPECTED LIVE-COLLECTOR DRIFT, integrity PASS**. Exact
content delta from the manifest baseline is **UNRESOLVABLE** from the retained
hash alone. Production SQLite was not modified or restored by this audit.

## Issue grading

Severity convention: **HIGH** = broad/current user-visible data correctness or
lineage break; **MEDIUM** = incorrect/stale secondary output or material
semantic ambiguity; **LOW** = latent/unconsumed inconsistency or auditability
gap; **INFO** = confirmed upstream capability limit, not a production defect.

| ID | Severity | Finding | Evidence / impact |
|---|---|---|---|
| P3-01 | **HIGH** | Shared snapshot UPSERT destructively mixes sources; trench 24h suffixes are not normalized and signal omits price/volume/holders. | Missing values overwrite richer rows with no last-source column. Fixed snapshot: 11,119/12,601 blank GMGN 24h volumes; swaps similarly sparse; Signal current holders are dropped. These fields reach the visible market table. |
| P3-02 | **MEDIUM** | Materialized `daily_metrics` does not invalidate at UTC rollover. | Fixed snapshot: 82 tokens / 193 return fields and 105 streak fields retained values when the current contract required NULL due a PROVISIONAL tail. Main UI recomputes safely, but stale values remain in API/DB. |
| P3-03 | **MEDIUM** | Streak page combines finalized official streak with provisional pattern/down/flat/day/latest-close aggregates without disclosure. | A single UI row presents aggregates from different finalization sets; users cannot see candle status. |
| P3-04 | **MEDIUM** | Volume unit and missingness are overstated in UI. | GMGN does not encode volume currency, but the cell adds `$`; zero, invalid and missing all render as a dash. Rolling 24h volume has no event history/provenance. |
| P3-05 | **MEDIUM** | Mutable snapshot fields lack row/field source and observation time. | Rank/hot attach a Trending-only clock even though Hot/Trenches/Signal may have overwritten the row; holders and market cap have no cell-level freshness. |
| P3-06 | **MEDIUM** | Security endpoint semantics collapse to an opaque digest. | Contract/security and holder-concentration fields cannot reach API/UI or explain which risk changed. Only change detection survives. |
| P3-07 | **LOW** | Legacy/latent Kline state is not fully uniform. | Separate `kline.sqlite` has no finalization metadata. Canonical UPSERT can theoretically diverge sticky `finalized_at` from replaceable `is_closed`; current DB has zero such rows and APIs ignore `is_closed`. |
| P3-A01 | **LOW** | Raw audit evidence is no longer present in `/tmp`. | The 22 results remain documented in Phase 2 endpoint matrices, but independent raw replay cannot be performed from this resumed environment. |
| P3-L01 | **INFO** | GMGN provides no active/unique/new-wallet count and no historical holder series. | Production correctly avoids substituting swaps/rates/volume for wallet counts. Repeated holder observations are conditional local snapshots, not an upstream history feed. |
| P3-L02 | **INFO** | `rhv2.sqlite` hash drift is expected independent-collector activity. | Integrity passes; timestamps and `meta.last_run` align with the unpaused hourly collector. It is not evidence of GMGN lineage corruption. |

### Overall Phase 3 verdict

**PARTIAL / NOT READY for a fully auditable market-data contract.** The
canonical finalized-Kline path and request-time N-day/streak computations are
sound. Snapshot activity, holder, freshness, unit, provenance, and security
lineages are incomplete, with one broad HIGH-severity destructive overwrite
boundary. No repair was performed.
