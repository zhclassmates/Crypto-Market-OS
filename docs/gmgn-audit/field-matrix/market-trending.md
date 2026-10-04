# Phase 2 field matrix: market trending

## Evidence set

- Existing raw responses only; no GMGN request was issued during this analysis.
- Files: `/tmp/gmgn-audit/raw/{sol,robinhood,base,eth}/market-trending/001-response.json`
- Response status: `code = 0`, `message = "success"`, `reason = ""` on all four chains.
- Shape: `{ code, message, reason, data: { rank: [...] } }`.
- Rows: 100 per chain, 400 total.
- All 95 `data.rank[]` keys are present on all 400 rows and are identical across the four chain samples.

## Requested fields

| field | JSON path | observed type | example | evidence-bound meaning | unit | nullable / missing sentinel | chains | historical or snapshot | confidence |
|---|---|---|---|---|---|---|---|---|---|
| address | `data.rank[].address` | string | `GAwh…9S9H` | Token address returned by the ranked row. | address | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| chain | `data.rank[].chain` | string | `sol` | Chain label. | enum-like string | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| symbol | `data.rank[].symbol` | string | `www` | Token symbol. | text | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| name | `data.rank[].name` | string | `world wide web` | Token name. | text | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| price | `data.rank[].price` | number | `0.00177109` | Price value attached to the ranked snapshot. The payload does not identify the quote currency. | NOT ENCODED | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| volume | `data.rank[].volume` | number | `35696500` | Volume value for a request made with `--interval 24h`; the JSON itself does not name the interval or currency. | NOT ENCODED | no JSON null | SOL, ROBINHOOD, BASE, ETH | rolling/request-window aggregate | MEDIUM |
| swaps | `data.rank[].swaps` | number | `258931` | GMGN-labelled swap count. For all 400 rows, `swaps = buys + sells`. | count | no JSON null | SOL, ROBINHOOD, BASE, ETH | rolling/request-window aggregate | HIGH for arithmetic relation; MEDIUM for business semantics |
| buys | `data.rank[].buys` | number | `137394` | Buy-side component of `swaps`; it is not evidence of unique buyers because no buyer address or unique-buyer field is returned. | count | no JSON null | SOL, ROBINHOOD, BASE, ETH | rolling/request-window aggregate | HIGH for non-unique distinction; MEDIUM otherwise |
| sells | `data.rank[].sells` | number | `121537` | Sell-side component of `swaps`; it is not evidence of unique sellers because no seller address or unique-seller field is returned. | count | no JSON null | SOL, ROBINHOOD, BASE, ETH | rolling/request-window aggregate | HIGH for non-unique distinction; MEDIUM otherwise |
| holder_count | `data.rank[].holder_count` | number | `9162` | Holder-count value attached to the current ranked row; no historical series is included. | count | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| liquidity | `data.rank[].liquidity` | number | `260599` | Liquidity value attached to the snapshot. The payload does not identify the currency. | NOT ENCODED | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| market_cap | `data.rank[].market_cap` | number | `1757570` | Market-cap value attached to the snapshot. The payload does not identify the currency. | NOT ENCODED | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| creation_timestamp | `data.rank[].creation_timestamp` | number | `1790911442` | Token creation timestamp value; 10-digit Unix-second shape. | Unix seconds | no JSON null | SOL, ROBINHOOD, BASE, ETH | event timestamp | MEDIUM |
| open_timestamp | `data.rank[].open_timestamp` | number | `1790911442` | Open timestamp when populated. Zero is used as a missing/unknown sentinel in 140/400 rows. | Unix seconds or `0` | no JSON null; 140 zeros | SOL, ROBINHOOD, BASE, ETH | event timestamp | MEDIUM |
| start_live_timestamp | `data.rank[].start_live_timestamp` | number | `0` | Live-start field; nearly all sampled values are the zero sentinel. | Unix seconds or `0` | no JSON null; 396 zeros | SOL, ROBINHOOD, BASE, ETH | event timestamp | LOW |
| end_live_timestamp | `data.rank[].end_live_timestamp` | number | `0` | Live-end field; nearly all sampled values are the zero sentinel. | Unix seconds or `0` | no JSON null; 397 zeros | SOL, ROBINHOOD, BASE, ETH | event timestamp | LOW |

## Wallet-field evidence

The only returned keys matching `wallet|trader|buyer|seller|holder|unique|new` are:

- `holder_count`
- `rat_trader_amount_rate`
- `top_10_holder_rate`

`active_wallets`, `unique_buyers`, `unique_sellers`, `new_holders`, `new_buyers`, buyer/seller addresses, and per-trade records are **NOT PROVIDED** by this endpoint sample. `buys` and `sells` therefore must not be mapped to unique wallet counts.

## Exhaustive observed row schema

All paths below are `data.rank[].<field>` and were present on all four tested chains.

- Boolean (5): `creator_close`, `is_og`, `is_show_alert`, `is_token_live`, `is_wash_trading`.
- Nullable number (2): `renounced_freeze_account`, `renounced_mint`. Each was JSON `null` in 300/400 rows.
- Number (62): `bluechip_owner_percentage`, `bot_degen_count`, `bot_degen_rate`, `bundler_rate`, `burn_ratio`, `buys`, `creation_timestamp`, `cto_flag`, `dev_team_hold_rate`, `dev_token_burn_amount`, `dev_token_burn_ratio`, `dexscr_ad`, `dexscr_ad_ts`, `dexscr_boost_fee`, `dexscr_boost_ts`, `dexscr_trending_bar`, `dexscr_trending_bar_ts`, `dexscr_update_link`, `dexscr_update_link_ts`, `end_live_timestamp`, `entrapment_ratio`, `gas_fee`, `history_highest_market_cap`, `holder_count`, `hot_level`, `id`, `initial_liquidity`, `is_honeypot`, `is_open_source`, `is_renounced`, `liquidity`, `lock_percent`, `market_cap`, `open_timestamp`, `pool_type`, `price`, `price_change_percent`, `price_change_percent1h`, `price_change_percent1m`, `price_change_percent5m`, `rank`, `rat_trader_amount_rate`, `renowned_count`, `rug_ratio`, `sells`, `smart_degen_count`, `sniper_count`, `square_mentions`, `start_live_timestamp`, `swaps`, `telegram_dup`, `top70_sniper_hold_rate`, `top_10_holder_rate`, `total_supply`, `twitter_change_flag`, `twitter_create_token_count`, `twitter_del_post_token_count`, `twitter_dup`, `twitter_rename_count`, `visiting_count`, `volume`, `website_dup`.
- String (26): `address`, `burn_status`, `buy_tax`, `chain`, `creator`, `creator_token_status`, `exchange`, `image_dup`, `launch_quote_address`, `launchpad`, `launchpad_platform`, `launchpad_status`, `logo`, `migrated_pool_exchange`, `name`, `pool_type_str`, `sell_tax`, `symbol`, `tcid`, `telegram`, `trans_name`, `trans_name_zhcn`, `trans_symbol`, `trans_symbol_zhcn`, `twitter_username`, `website`.

The response envelope adds `code` (number), `message` (string), `reason` (string), `data` (object), and `data.rank` (array).

## Endpoint verdict

- Directly present in this one-shot response: price, interval volume, swaps, buys, sells, current holder count, liquidity, market cap, and token creation/open timestamps.
- Not present: fetched/updated timestamp, explicit monetary unit, historical observations, active wallets, unique buyers/sellers, new holders/buyers.
- A single Phase 1 response cannot establish repeat-query stability or cache behavior; no extra requests were made in Phase 2.
