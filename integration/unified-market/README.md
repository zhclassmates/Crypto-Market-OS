# Unified Market Data Layer V1.7

Local SQLite only. `python3 unified_market.py --db data/world_model_market.sqlite`.
The existing collector calls this after its unchanged quality gate; an integration
failure is isolated from ingestion. `--full` forces a repair; `--stats` is read-only.

Identity: source IDs are vertices; valid same-chain contracts form edges. Symbols
and names never form edges. Solana retains case. Only Ethereum, BSC, Base,
Robinhood valid EVM addresses and valid Solana base58 are supported in V1.
Unknown/invalid contracts retain independent UNRESOLVED source identities.
A reviewed official mapping can be added to `wm_unified_identity_links` with
nonempty evidence and verified=1, followed by sync. Cross-chain contracts remain
separate chain tokens. No reviewed official links were invented for this dataset.
Canonical IDs survive a new source; merges retain redirects. All source IDs and
contract evidence remain queryable. Same-source official-ID collisions become
identity conflicts rather than disappearing.

Selection: finite, nonnegative values (signed 24h percent allowed), then source
quality, field scope, quote freshness, finalized tie-break, deterministic ID.
CG/CMC supply asset totals. The read-only GMGN adapter retains chain-level reported fields with field provenance; local GMGN provenance alone never raises provider health to TRUSTED. DEX supplies maximum returned-pool liquidity and
pool price fallback only; returned-pool volume and reported caps remain in
`pool_data_json`, never asset total columns. Pool addresses/activity are absent
upstream and remain missing. Rank/24h percentage come only from retained complete
CG staged payloads. No ranking, supply, price-change or history is fabricated.
Source field selection includes source ID, source quality, timestamp, time basis,
market/volume scope, raw version reference, and reason. Missing is SQL NULL.

CG/CMC field disagreements are evaluated only on same UTC close or intraday
quotes <=15 minutes apart; volume basis must also agree. Ratio is
abs(a-b)/max(abs(a),abs(b)). Thresholds: price 5%, MC/FDV/rank 10%, volume 25%,
24h percentage 25%. Different windows are NOT_COMPARABLE, with NULL ratio and
both original values; they are not counted as synchronous field conflicts.

Daily grid: UTC date primary key. UTC-finalized observations win over display-only
intraday quotes. A provider quote from a different UTC date cannot fill the
collection-date history cell; its current reported value remains traceable.
Timestamp provenance distinguishes provider_quote, collection_proxy and
normalized_utc_eod. A daily return requires adjacent same-source/same-source-ID
UTC-finalized closes with positive prior close. Unified daily_return and CG
price_change_24h use percentage points; the legacy UI ratio formatter receives
daily_return / 100 explicitly. No cross-source or intraday
returns. T-6..T0 uses latest actual observed UTC date. Each cell displays a real
price with its basis and nullable daily return. `wm_unified_raw_versions` retains
versions observed at each integration; upstream overwrite history predating this
layer cannot be reconstructed.

Incremental: scan local input metadata and fingerprint each source ID, then only
recompute changed assets. Per-date version fingerprints recompute only changed
dates and the next day (whose return may depend on that close); existing daily
rows supply unchanged neighboring closes. Version, identity or source-health
changes explicitly trigger the necessary repair. Unchanged rows and synced_at are not
rewritten. No daily rebuild or API calls. Indices support identity joins, paging,
field sort and date sort. BEGIN IMMEDIATE publishes all changes/checkpoints
atomically and SQLite serializes competing writers. The source tables and health
reports are never modified by integration. V1 scans local inputs to detect even
backdated edits; no unreliable timestamp-only watermark is used.

`wm_unified_market_view` is the query contract. `wm_unified_research_view` admits
only VALID, resolved records. V1.7 evaluates current quote eligibility separately
from seven-day completeness: price, market cap, volume and 24h change must be
present; chain/pool assets additionally need liquidity; selected providers must
have TRUSTED health. Unknown identities, source conflicts and blocked data cannot
pass. Missing optional FDV/rank or missing historical days remain explicit in
`missing_fields` and the daily grid; they do not veto an otherwise eligible
current quote. Missing daily returns are never synthesized.
The existing reviewed native CG/CMC links for Bitcoin, Ethereum and Solana are
retained; wrapped contracts do not merge into those native identities. No new reasoning or trading system is introduced.

UI: existing health panel stays mounted; unified table is first, old onchain
observation controls remain below in an on-demand expansion, preventing its
synchronous full-history query from blocking the unified paginated interface. SQLite LIMIT/OFFSET, server filters/sort,
seven-date sorting priority, per-date direction filters, search, detail drawer,
shared browser watch/hidden storage, new asset stars use a unified:canonical key; pre-existing chain stars remain
recognized. Canonical redirects preserve old stars/hidden keys after a merge.

Deployment: run install_unified.py from the app checkout. It backs up the source
DB with SQLite backup, verifies original table hashes and source revision, installs
this module/tests/docs and a small post-quality collector hook, syncs the real DB
transactionally, then verifies original tables and TRUSTED reports unchanged.


Recovery (2026-10-11): the authoritative core module already contained V1.7,
but its persisted projection was still V1.6. `resume_v17.py` preserves a SQLite
backup, hashes original ingestion tables, freezes only the three onchain input
tables through a read-only source transaction, and applies the existing sync.
It checks canonical identity preservation and a second no-op sync on the same
frozen input, then restores the live source path for future ingestion-triggered
syncs. No recollection, API calls or project reinstall. The fixture is an audit
checkpoint, not another live collector. Normal later updates read the live input
and may legitimately recompute records changed by the collector.

The frontend aggregates daily participation for all seven days in one grouped
query. Tests ensure these counts use the whole filtered market before pagination
and respect source, daily-direction and hidden preferences. The browser QA reads
current SQLite results rather than stale V1.5 counters and validates all native
assets against the current-quote gate.
