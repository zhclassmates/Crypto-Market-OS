# Phase 2 field matrix: market hot-searches

## Evidence set

- Existing raw responses only; no GMGN request was issued during this analysis.
- Files: `/tmp/gmgn-audit/raw/{sol,robinhood,base,eth}/market-hot-searches/001-response.json`
- Shape: `[{ chain, interval, version, tokens: [...] }]`.
- Top-level array length: 1 on every chain. `interval` is `24h` on every chain.
- Token rows: SOL 95, ROBINHOOD 100, BASE 32, ETH 32; 259 total.
- All 95 `tokens[]` keys are present on all 259 rows and are identical across the four chain samples.

## Requested fields

| field | JSON path | observed type | example | evidence-bound meaning | unit | nullable / missing sentinel | chains | historical or snapshot | confidence |
|---|---|---|---|---|---|---|---|---|---|
| chain | `[0].chain` and `[0].tokens[].chain` | string | `sol` | Requested/result chain label. | enum-like string | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| interval | `[0].interval` | string | `24h` | Explicit aggregate interval for this result set. | duration label | no JSON null | SOL, ROBINHOOD, BASE, ETH | query/window metadata | HIGH |
| version | `[0].version` | string | `C6D6D9820EB3D0B8` | Opaque result version. It is not a documented timestamp in the payload. | opaque string | no JSON null | SOL, ROBINHOOD, BASE, ETH | response metadata | HIGH for presence; LOW for semantics |
| address | `[0].tokens[].address` | string | `GAwh…9S9H` | Token address returned by the result row. | address | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| symbol | `[0].tokens[].symbol` | string | `www` | Token symbol. | text | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| name | `[0].tokens[].name` | string | `world wide web` | Token name. | text | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| price | `[0].tokens[].price` | number | `0.00177059` | Price value attached to the result row. The payload does not identify the quote currency. | NOT ENCODED | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| volume | `[0].tokens[].volume` | number | `35696600` | Volume for the explicitly labelled `24h` interval. Currency is not encoded. | NOT ENCODED | no JSON null | SOL, ROBINHOOD, BASE, ETH | 24h aggregate | HIGH for interval; LOW for currency |
| swaps | `[0].tokens[].swaps` | number | `258935` | GMGN-labelled 24h swap count. For all 259 rows, `swaps = buys + sells`. | count | no JSON null | SOL, ROBINHOOD, BASE, ETH | 24h aggregate | HIGH for interval/arithmetic; MEDIUM for business semantics |
| buys | `[0].tokens[].buys` | number | `137397` | Buy-side component of 24h swaps; no buyer identities or unique-buyer field are returned. | count | no JSON null | SOL, ROBINHOOD, BASE, ETH | 24h aggregate | HIGH for non-unique distinction; MEDIUM otherwise |
| sells | `[0].tokens[].sells` | number | `121538` | Sell-side component of 24h swaps; no seller identities or unique-seller field are returned. | count | no JSON null | SOL, ROBINHOOD, BASE, ETH | 24h aggregate | HIGH for non-unique distinction; MEDIUM otherwise |
| holder_count | `[0].tokens[].holder_count` | number | `9162` | Holder-count value attached to the current result row; no historical series is included. | count | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| liquidity | `[0].tokens[].liquidity` | number | `260549` | Liquidity value attached to the snapshot. Currency is not encoded. | NOT ENCODED | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| market_cap | `[0].tokens[].market_cap` | number | `1757080` | Market-cap value attached to the snapshot. Currency is not encoded. | NOT ENCODED | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| creation_timestamp | `[0].tokens[].creation_timestamp` | number | `1790911442` | Token creation timestamp value; 10-digit Unix-second shape. | Unix seconds | no JSON null | SOL, ROBINHOOD, BASE, ETH | event timestamp | MEDIUM |
| open_timestamp | `[0].tokens[].open_timestamp` | number | `1790911442` | Open timestamp when populated. Zero is used as a missing/unknown sentinel in 55/259 rows. | Unix seconds or `0` | no JSON null; 55 zeros | SOL, ROBINHOOD, BASE, ETH | event timestamp | MEDIUM |
| start_live_timestamp | `[0].tokens[].start_live_timestamp` | number | `0` | Live-start field; predominantly the zero sentinel. | Unix seconds or `0` | no JSON null; 250 zeros | SOL, ROBINHOOD, BASE, ETH | event timestamp | LOW |
| end_live_timestamp | `[0].tokens[].end_live_timestamp` | number | `0` | Live-end field; predominantly the zero sentinel. | Unix seconds or `0` | no JSON null; 252 zeros | SOL, ROBINHOOD, BASE, ETH | event timestamp | LOW |

## Wallet-field evidence

The only returned token keys matching `wallet|trader|buyer|seller|holder|unique|new` are `holder_count`, `rat_trader_amount_rate`, and `top_10_holder_rate`.

`active_wallets`, `unique_buyers`, `unique_sellers`, `new_holders`, `new_buyers`, buyer/seller addresses, and per-trade records are **NOT PROVIDED**. `buys` and `sells` must not be interpreted as unique wallet counts.

## Exhaustive observed token schema

All paths below are `[0].tokens[].<field>` and were present on all four tested chains.

- Boolean (5): `creator_close`, `is_og`, `is_show_alert`, `is_token_live`, `is_wash_trading`.
- Nullable number (2): `renounced_freeze_account`, `renounced_mint`. Each was JSON `null` in 164/259 rows.
- Number (62): `bluechip_owner_percentage`, `bot_degen_count`, `bot_degen_rate`, `bundler_rate`, `burn_ratio`, `buys`, `creation_timestamp`, `cto_flag`, `dev_team_hold_rate`, `dev_token_burn_amount`, `dev_token_burn_ratio`, `dexscr_ad`, `dexscr_ad_ts`, `dexscr_boost_fee`, `dexscr_boost_ts`, `dexscr_trending_bar`, `dexscr_trending_bar_ts`, `dexscr_update_link`, `dexscr_update_link_ts`, `end_live_timestamp`, `entrapment_ratio`, `gas_fee`, `history_highest_market_cap`, `holder_count`, `hot_level`, `id`, `initial_liquidity`, `is_honeypot`, `is_open_source`, `is_renounced`, `liquidity`, `lock_percent`, `market_cap`, `open_timestamp`, `pool_type`, `price`, `price_change_percent`, `price_change_percent1h`, `price_change_percent1m`, `price_change_percent5m`, `rank`, `rat_trader_amount_rate`, `renowned_count`, `rug_ratio`, `sells`, `smart_degen_count`, `sniper_count`, `square_mentions`, `start_live_timestamp`, `swaps`, `telegram_dup`, `top70_sniper_hold_rate`, `top_10_holder_rate`, `total_supply`, `twitter_change_flag`, `twitter_create_token_count`, `twitter_del_post_token_count`, `twitter_dup`, `twitter_rename_count`, `visiting_count`, `volume`, `website_dup`.
- String (26): `address`, `burn_status`, `buy_tax`, `chain`, `creator`, `creator_token_status`, `exchange`, `image_dup`, `launch_quote_address`, `launchpad`, `launchpad_platform`, `launchpad_status`, `logo`, `migrated_pool_exchange`, `name`, `pool_type_str`, `sell_tax`, `symbol`, `tcid`, `telegram`, `trans_name`, `trans_name_zhcn`, `trans_symbol`, `trans_symbol_zhcn`, `twitter_username`, `website`.

The result wrapper adds `[0].chain`, `[0].interval`, `[0].version` (strings), and `[0].tokens` (array).

## Endpoint verdict

- Directly present: price, explicit 24h volume/swaps/buys/sells, current holder count, liquidity, market cap, and creation/open timestamps.
- Not present: fetched/updated timestamp, explicit monetary unit, historical observations, active wallets, unique buyers/sellers, new holders/buyers.
- `version` may support response-change comparison, but its semantics are not encoded and it must not be treated as time.
- A single Phase 1 response cannot establish repeat-query stability or cache behavior; no extra requests were made in Phase 2.
