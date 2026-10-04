# Phase 2 FIELD MATRIX

## Status

- `raw_collection`: **done** (existing 22/22 production-applicable endpoint × chain datasets reused).
- `field_matrix`: **done** (6/6 endpoints analyzed).
- No GMGN CLI/API request was issued during Phase 2 continuation.
- Phase 3 `cross_chain`: **pending / not started**.

The preceding `peer closed connection without sending TLS close_notify` incident is classified only as an **AI/CLI session transport interruption**. It is not an endpoint failure, GMGN TLS failure, HTTP 429, or raw dataset failure.

Production SQLite integrity note: Phase 2 did not query or write the production SQLite files; final verification only read their file hashes/metadata. `market.sqlite` and `kline.sqlite` still matched the manifest baseline hashes. `rhv2.sqlite` showed out-of-band drift from its manifest baseline and had filesystem modification time `2026-10-03T00:03:42Z`; it was not restored or otherwise modified by this audit continuation.

## Endpoint matrix

| Endpoint | Tested production chains | Sample shape/size | Main usable evidence | Main limitation | Detailed output |
|---|---|---|---|---|---|
| market trending | SOL, ROBINHOOD, BASE, ETH | 400 ranked rows; 95 identical row keys | price, request-window volume/swaps/buys/sells, holder count, liquidity, market cap, creation/open timestamps | interval/currency not encoded in payload; no wallet identities/unique counts/history | `field-matrix/market-trending.md` |
| market hot-searches | SOL, ROBINHOOD, BASE, ETH | 259 token rows; 95 identical token keys | explicit `interval=24h`; volume/swaps/buys/sells; holder count; liquidity; market cap; timestamps | currency not encoded; no wallet identities/unique counts/history | `field-matrix/market-hot-searches.md` |
| market trenches | SOL, ROBINHOOD, BASE, ETH | 633 rows; 132 union fields, only 65 universal | explicit `volume_24h`, `swaps_24h`, `buys_24h`, `sells_24h`; holder count; liquidity; market cap; timestamps | material chain/category schema drift; frequent zero sentinels; wallet-labelled fields are not counts | `field-matrix/market-trenches.md` |
| market signal | SOL, ROBINHOOD | 100 signal rows; 12 root keys, 155 `data` keys, 3 `cur_data` keys | signal event timestamp; market-cap layers; `cur_data` holder count/liquidity | all 1m/1h/6h/24h activity metrics are zero in 100/100 rows; BASE/ETH unsupported by production | `field-matrix/market-signal.md` |
| market kline | SOL, ROBINHOOD, BASE, ETH | 120 daily candles; 8 identical keys | historical daily OHLC and volume; UTC-midnight millisecond bar time | no swaps/buys/sells/wallets/holders/liquidity/market cap; volume unit and finalized flag absent | `field-matrix/market-kline.md` |
| token security | SOL, ROBINHOOD, BASE, ETH | 4 objects; 28 identical root keys | point-in-time contract/security and holder-concentration fields | no requested daily market, holder-count, or wallet-participation metrics | `field-matrix/token-security.md` |

## Requested metric field matrix

Legend: `DIRECT` = populated direct field in this sample; `SNAPSHOT` = point-in-time only; `ZERO-ONLY` = field exists but all sampled values are zero; `NO` = field absent; `SPARSE` = key is optional/sparse; `N/A` = endpoint purpose does not provide it.

| Metric | Trending | Hot searches | Trenches | Signal | Kline | Security | Phase 2 evidence conclusion |
|---|---|---|---|---|---|---|---|
| price / OHLC | DIRECT `price` | DIRECT `price` | DIRECT `price` | NO price field | DIRECT OHLC history | NO | Snapshot price exists in discovery; historical OHLC exists in kline. |
| volume_24h | DIRECT `volume`, request used 24h | DIRECT `volume`, wrapper says 24h | DIRECT `volume_24h` | ZERO-ONLY `volume_24h` | DIRECT daily `volume` history | NO | Daily/history volume exists, but raw JSON does not encode its currency/unit. |
| swaps_24h | DIRECT `swaps`, request used 24h | DIRECT `swaps`, wrapper says 24h | DIRECT `swaps_24h` | ZERO-ONLY | NO | NO | Available in discovery snapshots, not in historical candles. |
| buys_24h | DIRECT `buys`, request used 24h | DIRECT `buys`, wrapper says 24h | DIRECT `buys_24h` | ZERO-ONLY | NO | NO | Count component of swaps; not unique buyers. |
| sells_24h | DIRECT `sells`, request used 24h | DIRECT `sells`, wrapper says 24h | DIRECT `sells_24h` | ZERO-ONLY | NO | NO | Count component of swaps; not unique sellers. |
| buy/sell volume | NO | NO | SPARSE `buy_volume_24h` / `sell_volume_24h`; formula/unit unverified | NO dedicated populated values | NO | NO | Not stable enough for a common field contract from Phase 2 samples. |
| holder_count | SNAPSHOT | SNAPSHOT | SNAPSHOT | SNAPSHOT in `data` and `cur_data`; layers differ | NO | NO (`top_10_holder_rate` only) | Current snapshots exist; GMGN kline does not provide holder history. |
| liquidity | SNAPSHOT | SNAPSHOT | SNAPSHOT | SNAPSHOT in `data` and `cur_data`; layers differ | NO | NO | Current snapshots exist; no historical kline liquidity. |
| market_cap | SNAPSHOT | SNAPSHOT | SNAPSHOT | multiple market-cap layers; only `data.usd_market_cap` explicitly names USD | NO | NO | Current/event values exist; no historical kline market cap. |
| token creation time | `creation_timestamp` | `creation_timestamp` | `created_timestamp` | `data.created_timestamp` | NO | NO | Unix-second-shaped creation timestamps exist in discovery/signal rows. |
| active_wallets | NO | NO | NO | NO | NO | NO | NOT PROVIDED. |
| unique_buyers | NO | NO | NO | NO | NO | NO | NOT PROVIDED; `buys*` must not be substituted. |
| unique_sellers | NO | NO | NO | NO | NO | NO | NOT PROVIDED; `sells*` must not be substituted. |
| new_holders | NO | NO | NO | NO | NO | NO | NOT PROVIDED. |
| new_buyers | NO | NO | NO | NO | NO | NO | NOT PROVIDED. |
| observation/update time | NO | NO (`version` is opaque) | NO | trigger time only, not general observation time | bar time only | NO | Response-level `fetched_at`/`updated_at` is NOT PROVIDED; audit fetch time is only in sidecar meta. |

## High-confidence structural findings

1. `swaps = buys + sells` in 400/400 trending rows and 259/259 hot-search rows; `swaps_24h = buys_24h + sells_24h` in 633/633 trench rows. These are transaction-side counts, not evidence of unique wallets.
2. `market kline` is an OHLCV history source only. Its complete schema is `time`, `open`, `high`, `low`, `close`, `volume`, `amount`, `source`.
3. Kline `time` is Unix milliseconds aligned to 00:00 UTC. The latest sampled candle began at `2026-10-02T00:00:00Z` and was fetched before that UTC day ended, so it was in progress; no finalized flag exists.
4. `holder_count` is available only as discovery/signal snapshot data. Historical holder counts are absent from daily candles.
5. `fresh_wallet_rate` is a ratio, not a wallet count. `new_wallet_volume` is sparse and all 143 present values are zero. Neither can implement active, unique, or new-wallet counts.
6. Monetary units are generally not encoded in raw payloads. The only requested-metric path explicitly naming a currency is `market signal -> data.usd_market_cap`.

## Phase boundary

Phase 2 is complete. This document does not perform the Phase 3 cross-chain YES/NO/NULL/UNSTABLE matrix, production mapping, data-health evaluation, database recommendation, or final audit verdict.
