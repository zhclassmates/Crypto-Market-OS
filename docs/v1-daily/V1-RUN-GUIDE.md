# V1 Daily Collector — run guide

Patch: `v1-daily-collector.patch` (7 files, all under `rh_v2/`). The patch only adds code and DB objects. It does not touch UI, TS, plist, lock files, or sqlite files.

**What it does:** adds a `gmgn_daily` lane to the existing `market_run.py loop`. For each universe token, once per UTC day, it calls GMGN `token info`. It also fetches the daily kline when yesterday's candle is not FINALIZED yet. The existing Trending / Trenches / Security lanes now also save the first valid response of each UTC day. That costs no extra requests.

Each saved response writes to three places:

- `token_daily_snapshot`: one row per source per token per UTC day.
- `raw_responses`: the full JSON.
- `token_candle` / `daily_kline`: candles, written with the existing FINALIZED rule.

Failures go to `collection_errors`. All GMGN calls go through `market_collect.gmgn()`, so the shared `GLOBAL_GMGN_COOLDOWN` and the 429 backoff ladder apply.

> ⚠️ Restarting `com.market.collector` deploys **everything in your working tree**. That includes the Phase 4 / V1-field changes the audit left "awaiting owner decision". On the first connect, those changes also add their `token_snapshot` columns, since production still has the 36-column schema. That is existing pending work, not this patch, but it ships together with it.

All commands assume:

```bash
REPO=/Users/zhaomosheng/Desktop/ctiwvGy8hZk3VdCu-grok-workspace
cd "$REPO"
```

## 1. Apply the patch

```bash
git apply --check docs/v1-daily/v1-daily-collector.patch && git apply docs/v1-daily/v1-daily-collector.patch
git status --short   # expect: M rh_v2/market_{collect,db,health,lanes,run}.py, ?? rh_v2/market_daily.py, ?? rh_v2/test_daily_collect.py
```

Undo with `git apply -R docs/v1-daily/v1-daily-collector.patch`. The new tables are additive, so old code ignores them.

## 2. Migrate the real DB (back up first)

The migration is `CREATE TABLE/INDEX IF NOT EXISTS` for `token_daily_snapshot`, `raw_responses` and `collection_errors`. It runs inside `market_db.connect()`, is idempotent, and does not alter existing tables.

```bash
# a) stop the GMGN loop so nothing writes during backup/migration
launchctl bootout gui/$(id -u)/com.market.collector

# b) online-safe backup (handles WAL; don't use plain cp while a writer may be active)
cd "$REPO/rh_v2"
mkdir -p backups
BK="backups/market-$(date +%Y%m%d-%H%M%S)-pre-v1daily.sqlite"
sqlite3 market.sqlite ".backup '$BK'" && ls -lh "$BK"

# c) rehearse on a copy first
cp "$BK" /tmp/market-rehearsal.sqlite
time MARKET_DB=/tmp/market-rehearsal.sqlite python3 -c "
import market_db as db
c = db.connect()
print([r[0] for r in c.execute(\"select name from sqlite_master where name in ('token_daily_snapshot','raw_responses','collection_errors')\")])
print('integrity', c.execute('pragma integrity_check').fetchone()[0])
print('token_snapshot cols', len(c.execute('pragma table_info(token_snapshot)').fetchall()))"

# d) migrate the real DB (same code path the loop runs on start)
python3 -c "import market_db as db; c=db.connect(); print(c.execute('pragma integrity_check').fetchone()[0]); c.close()"
```

The real-DB schema export in `.grokbot-export/` failed ("unable to open database file"). The migration was therefore tested against a fresh DB and against a rebuilt copy of the pre-Phase-4 production schema (36-column `token_snapshot`), not against your actual file. Step (c) is the real check.

Size the universe (read-only):

```bash
sqlite3 -readonly market.sqlite "select chain, count(*) from token_registry where first_liquidity_50k_at is not null group by chain;"
sqlite3 -readonly market.sqlite "select chain, count(*) from token_registry group by chain;"
```

With the defaults, the lane handles 1 token per chain per 60 s, which is about **1,440 tokens per chain per day**. If the research universe on a chain is larger, the rest stays `pending` until the next day (`daily-status` shows it). See §5 for tuning.

## 3. Run the tests (offline; they never open `market.sqlite` and never call GMGN)

```bash
cd "$REPO/rh_v2"
python3 test_daily_collect.py      # new: 17 tests
python3 test_phase1.py             # 54
python3 test_market_health.py      # 12
python3 test_streak_fields.py      # 5
python3 test_offline.py
cd "$REPO" && npm test             # unchanged by this patch; needs Node >= 22.13 (node:sqlite)
```

`test_daily_collect.py` reads the recorded payloads in `docs/gmgn-audit/raw/`. It mocks `gmgn-cli` through `subprocess.run`.

## 4. Tiny real smoke test (1–3 tokens, through the guarded entrypoint)

Keep the loop stopped from step 2. `market_run.py daily` uses the same collector lock and refuses to run while the loop is up. It uses the same `gmgn()` wrapper (cooldown guard + 429 handling) and waits 1.05 s between requests. Each token costs at most 2 GMGN requests.

```bash
cd "$REPO/rh_v2"
sqlite3 -readonly market.sqlite "select k,v from market_meta where k like 'gmgn_cooldown%';" ; date +%s
# if gmgn_cooldown_until is in the future, wait — do not force it.

# pick tokens (one SOL, one EVM, and one Robinhood — RH `token info` was never tested in the audit)
sqlite3 -readonly market.sqlite "select chain,address,symbol from token_registry where first_liquidity_50k_at is not null and chain in ('sol','robinhood','base') group by chain order by chain;"

python3 market_run.py daily --token sol:<SOL_ADDR> --token robinhood:<RH_ADDR> --token base:<BASE_ADDR>
#   or: python3 market_run.py daily --chain sol --limit 1      (next pending universe token)

python3 market_run.py daily-status
sqlite3 -header -readonly market.sqlite "select chain,token_address,source,datetime(fetched_at,'unixepoch') utc,price,market_cap,liquidity,total_supply,volume_24h,buys_24h,sells_24h,swaps_24h,buy_volume_24h,sell_volume_24h,holder_count,fresh_wallet_rate,bundler_rate from token_daily_snapshot order by id desc limit 5;"
sqlite3 -header -readonly market.sqlite "select id,chain,token_address,endpoint,request_args,fetched_at,length(payload_json) bytes from raw_responses order by id desc limit 6;"
sqlite3 -header -readonly market.sqlite "select * from collection_errors order by id desc limit 5;"
sqlite3 -header -readonly market.sqlite "select datetime(candle_open_ts,'unixepoch') day, fetched_at, finalized_at, is_closed from token_candle where address='<SOL_ADDR>' order by candle_open_ts desc limit 3;"
```

Expected results:

- One `token_info` row per token, with `market_cap` NULL.
- `buy_volume_24h + sell_volume_24h ≈ volume_24h`.
- `fresh_wallet_rate` / `bundler_rate` NULL on base/eth.
- A `token_info` raw row and a `market_kline` raw row per token.
- The **today** candle has `finalized_at` NULL and `is_closed` 0. Yesterday's is finalized.

If the output shows `rate_limited` / `cooldown`, the shared cooldown is now armed. Stop and wait. Re-running the same tokens the same day does not create duplicate rows.

Then restart the loop. The lane then runs automatically:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.market.collector.plist
tail -f "$REPO/rh_v2/logs/market.log" | grep --line-buffered -E "gmgn_daily|GLOBAL_GMGN_COOLDOWN"
python3 market_run.py status | grep -A1 gmgn_daily
```

Watch the first hour for any rise in `GLOBAL_GMGN_COOLDOWN`. If it rises, slow the lane down (§5).

## 5. Daily scheduling

The project already has the pattern: the launchd agent `com.market.collector` runs `market_run.py loop` with `KeepAlive`. `gmgn_daily` is registered as a lane in that loop (`market_health.catalog` + `market_lanes.GMGN_JOBS`, lowest priority). So **nothing new needs scheduling**. Do not add a cron job for `market_run.py daily`. It would just exit with `lock_busy` while the loop runs, which is intended: it avoids two processes hitting GMGN.

Optional tuning goes in the plist's `EnvironmentVariables`, followed by bootout/bootstrap:

| env | default | meaning |
|---|---|---|
| `MARKET_DAILY_PERIOD_SEC` | 60 | seconds between lane ticks per chain |
| `MARKET_DAILY_BATCH` | 1 | tokens per tick (1–2 GMGN requests each, 1.05 s apart) |
| `MARKET_DAILY_UNIVERSE` | `research` | `research` = `token_registry` with a recorded ≥$50k liquidity observation (permanent ledger) + seed tokens; `registry` = every registry token |
| `MARKET_DAILY_MAX_ATTEMPTS` | 3 | non-rate-limit `token_info` failures per token per UTC day before it waits for tomorrow |

Load is at most about 4 chains × 2 requests / 60 s ≈ 0.13 req/s on top of the existing lanes (about 0.14 req/s). Kline requests are skipped when the kline lane has already finalized yesterday's candle.

Raw storage is roughly 5 KB per `token info` plus 0.2–17 KB per kline response (100-day window, the existing request). That is at most about 30–120 MB/day at full default throughput. Check the `raw_today` bytes in `daily-status`.
