# GMGN RAW collection progress

Request plan: 22 production-applicable `endpoint x chain` requests.

## sol

- [x] market trending
- [x] market hot-searches
- [x] market trenches
- [x] market signal
- [x] market kline
- [x] token security

## robinhood

- [x] market trending
- [x] market hot-searches
- [x] market trenches
- [x] market signal
- [x] market kline
- [x] token security

## base

- [x] market trending
- [x] market hot-searches
- [x] market trenches
- [x] market signal — N/A: production marks this chain unsupported and does not issue a request
- [x] market kline
- [x] token security

## eth

- [x] market trending
- [x] market hot-searches
- [x] market trenches
- [x] market signal — N/A: production marks this chain unsupported and does not issue a request
- [x] market kline
- [x] token security

Last completed request: `eth / token-security`

Next request: none — Phase 1 request plan complete

# FIELD MATRIX

- [x] market trending
- [x] market hot-searches
- [x] market trenches
- [x] market signal
- [x] market kline
- [x] token security

Last analyzed endpoint: `token security`

Next endpoint: none — Phase 2 endpoint analysis complete

Phase 2 output: `docs/gmgn-audit/phase2-field-matrix-summary.md`

Phase 2 status: complete — stop before Phase 3

Session transport note: the reported WebSocket fallback / HTTPS `peer closed connection without sending TLS close_notify` was an AI/CLI session transport interruption only. It was not counted as a GMGN endpoint failure, GMGN TLS failure, HTTP 429, or raw dataset failure.

SQLite integrity note: Phase 2 did not query or write SQLite; final verification only read file hashes/metadata. `market.sqlite` and `kline.sqlite` match the manifest baseline; `rhv2.sqlite` showed out-of-band drift with mtime `2026-10-03T00:03:42Z` and was not modified or restored by this continuation.

# PHASE 3 — PRODUCTION MAPPING

- [x] source → parser — PARTIAL; see `phase3-production-mapping.md`
- [x] parser → DB — PARTIAL; see `phase3-production-mapping.md`
- [x] DB → API — PARTIAL; see `phase3-production-mapping.md`
- [x] API → UI — PARTIAL; see `phase3-production-mapping.md`
- [x] complete lineage — only finalized N-day/streak are complete; see `phase3-production-mapping.md`
- [x] Kline finalization — PASS for canonical market lineage
- [x] N-day return — visible path PASS; materialized returns FAIL stale at UTC rollover
- [x] streak — visible official path PASS; materialized streak FAIL stale at UTC rollover
- [x] volume — rolling 24h FAIL; daily candle volume PARTIAL
- [x] wallet / holder — snapshot-only holders; no GMGN wallet-count lineage
- [x] rhv2 drift — expected independent collector drift; integrity PASS
- [x] issue grading — 1 HIGH, 5 MEDIUM, 2 LOW, 2 INFO

Phase 3 status: complete — audit only; no repair performed

# PHASE 4 — REPAIR

- [x] resume audit of partial Phase 4 changes (09:51–10:04) — accepted; dry-run oracle creation-day filter fixed
- [x] P3-01 snapshot patch / trench normalization / signal holders
- [x] P3-02 UTC-day materialized metrics refresh + request-time API returns
- [x] P3-03 streak board finalized-only aggregates
- [x] P3-04 volume unit/missingness display
- [x] P3-05 per-field source/updated_at through DB → API → UI
- [x] P3-06 security semantic fields
- [x] P3-07 is_closed derived from finalized_at
- [x] verification: py 46/46, ts 54/54, oracle 6/6, typecheck, build, read-only prod dry-run, prod-copy rehearsal, dev render
- [ ] deployment (collector restart) — NOT performed; awaiting owner decision

Phase 4 output: `docs/gmgn-audit/phase4-repair.md`

Phase 4 status: code complete and verified — not deployed; production SQLite not written

# CAPABILITY MAP (docs only; Phase 4 repair NOT continued)

- [x] reused Phase 2 field matrices + Phase 3 mapping; no GMGN request; production SQLite read-only
- [x] `gmgn-field-capability-map.md` — 18 sections + IMPLEMENTATION GAP appendix

# CAPABILITY MAP ACCEPTANCE

- [x] acceptance review against 5 product modules — gaps found (module view, SCAN→CANDIDATE→ALERT→RESEARCH, P0/P1/P2/GAP table, V1 minimal set)
- [x] appended Part II (§19–§25) to `gmgn-field-capability-map.md`; Part I evidence unchanged
- Result: CAPABILITY MAP: UPDATED

# V1 FIELD INTEGRATION

- [x] pre-checks: state.json valid; writer processes listed; Phase 4 working-tree changes preserved (V1 built on top)
- [x] collector → DB → API for 12 V1 fields (not deployed)
- [x] unit tests 54/54, TS 54/54, oracle, typecheck, build
- [x] real raw end-to-end: SOL Trending 100/100
- [ ] Hot / Trenches / Signal / Security real raw — blocked: GMGN RATE_LIMIT_BANNED at 10:52:18 (verification request sent during production cooldown); no further requests sent
- [ ] deployment — awaiting owner decision

Result: V1 FIELD INTEGRATION: PARTIAL — see `v1-field-integration.md`

# V1 FIELD INTEGRATION — guarded re-verification

- [x] root cause: previous script bypassed `market_collect.gmgn()` (no guard / no shared cooldown); `market_sched` cooldown is cached per process; `market_db.connect()` runs migrate on 429 path
- [x] `scripts/v1-verify-fetch.py`: every request via `market_collect.gmgn()`, cooldown reloaded from DB before each request, production-lane quiet check, serial ≥20s, stop on any limit, skip existing raw, meta-only cooldown writes (prod schema stayed 36 cols)
- [x] 14 requests this round, 0 rate-limited, 1 pre-request stop on shared cooldown
- [x] `scripts/v1-verify-apply.py`: raw → collector → DB copy, all 15 endpoint×chain PASS; DB → API 20 fields × 1,134 tokens PASS
- [ ] production deployment (all 12 fields) — awaiting owner decision
- [ ] UI consumption (11 of 12 fields) — out of V1 scope

Result: V1 FIELD INTEGRATION: PARTIAL (data chain PASS; missing layers: deployment, UI)

# FIELD SEMANTICS AUDIT

- [x] vendor docs (gmgn-cli 1.6.6 skills) read as candidate meanings; 7 doc-vs-raw conflicts recorded (raw wins)
- [x] field inventory from 15 real raw payloads (~555 paths) + Phase 2 kline
- [x] quantitative semantics tests vs DexScreener / hourly_price / token_candle (read-only): price & volume & market_cap USD, pc = percent, interval windows, market_cap = price × total_supply, kline volume = USD
- [x] liquidity cross-endpoint conflict documented (ETH 1.23–2.92×) — NEEDS_CONFIRMATION
- [x] `gmgn-field-dictionary.md` (dictionary, coverage, stability, DIRECT vs DERIVED, V1 re-review, SAFE / BLOCKED sets, appendix of all raw paths)
- [x] `gmgn-field-capability-map.md` Part III semantics revisions (old content kept)
- No code, no deploy, no restart, no commit, no new GMGN requests

Result: FIELD SEMANTICS: PARTIAL

# DAILY TOKEN INTELLIGENCE CAPABILITY

- [x] vendor docs + local CLI help reviewed (token info/holders/traders, track, market)
- [x] 5 guarded raw requests (`scripts/daily-capability-fetch.py`, shared cooldown, 0 rate limits): token info SOL/ETH, traders, holders, track smartmoney
- [x] token info windows (1m–24h) for volume / buy_volume / sell_volume / swaps / buys / sells verified; buy+sell = total exactly
- [x] wallet counts / unique traders / new wallets: NOT_AVAILABLE FROM GMGN; traders/holders capped at 100; smartmoney feed covers ~1.8 min
- [x] `daily-token-intelligence-capability-map.md`

# SIX-FIELD PROBE (buy/sell volume, unique/new swap traders, liquidity, holders)

- [x] 6 guarded GMGN requests (`scripts/field-probe-fetch.py`; token info ×4, token pool ×2), 0 rate limits; GeckoTerminal + Blockscout snapshots taken right after each
- [x] buy_volume / sell_volume: CONFIRMED (USD, rolling window, all pools, buy+sell = volume exactly)
- [x] liquidity: CONFIRMED (main pool only, = 2 × quote-side USD)
- [x] holder_count: CONFIRMED (current holder addresses; ≈ Blockscout, −6.5% on a ~1M-holder token)
- [x] unique_swap_traders / new_swap_traders: NOT PROVIDED by GMGN OpenAPI
- Output: `field-probe-six.md`
