# Phase 2 field matrix: market trenches

## Evidence set

- Existing raw responses only; no GMGN request was issued during this analysis.
- Files: `/tmp/gmgn-audit/raw/{sol,robinhood,base,eth}/market-trenches/001-response.json`
- Shape: `{ new_creation: [...], near_completion: [...], completed: [...] }`.
- Rows: SOL 60/60/60, ROBINHOOD 60/60/60, BASE 60/60/60, ETH 60/28/5; 633 total.
- Union: 132 top-level row fields. Only 65 fields are present on every sampled row; schema presence varies by chain and trench category.

## Requested fields

The row path below is abbreviated as `<bucket>[]`, where `<bucket>` is `new_creation`, `near_completion`, or `completed`.

| field | JSON path | observed type | coverage | example | evidence-bound meaning | unit | nullable / missing sentinel | chains | historical or snapshot | confidence |
|---|---|---|---:|---|---|---|---|---|---|---|
| address | `<bucket>[].address` | string | 633/633 | `7Q5e…pump` | Token address returned by a trench row. | address | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| chain | `<bucket>[].chain` | string | 633/633 | `sol` | Chain label. | enum-like string | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| symbol | `<bucket>[].symbol` | string | 633/633 | `UGF` | Token symbol. | text | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| name | `<bucket>[].name` | string | 633/633 | `Unemployed Frog` | Token name. | text | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| price | `<bucket>[].price` | number | 633/633 | `0.0000033182279659372656` | Price attached to the trench snapshot. Quote currency is not encoded. | NOT ENCODED | no JSON null; 115 zeros | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| volume_24h | `<bucket>[].volume_24h` | number | 633/633 | `0.06` | Explicitly labelled 24h volume. Currency is not encoded. | NOT ENCODED | no JSON null; 140 zeros | SOL, ROBINHOOD, BASE, ETH | 24h aggregate | HIGH for interval; LOW for currency |
| swaps_24h | `<bucket>[].swaps_24h` | number | 633/633 | `1` | GMGN-labelled 24h swap count. `swaps_24h = buys_24h + sells_24h` in all 633 rows. | count | no JSON null; 130 zeros | SOL, ROBINHOOD, BASE, ETH | 24h aggregate | HIGH for arithmetic/interval; MEDIUM for business semantics |
| buys_24h | `<bucket>[].buys_24h` | number | 633/633 | `1` | Buy-side component of `swaps_24h`; no buyer identities or unique-buyer field are returned. | count | no JSON null; 155 zeros | SOL, ROBINHOOD, BASE, ETH | 24h aggregate | HIGH for non-unique distinction; MEDIUM otherwise |
| sells_24h | `<bucket>[].sells_24h` | number | 633/633 | `2` | Sell-side component of `swaps_24h`; no seller identities or unique-seller field are returned. | count | no JSON null; 252 zeros | SOL, ROBINHOOD, BASE, ETH | 24h aggregate | HIGH for non-unique distinction; MEDIUM otherwise |
| buy_volume_24h | `<bucket>[].buy_volume_24h` | number | 116/633 | `11176.704` | Sparse buy-volume field. It is absent on SOL and on most sampled rows. | NOT ENCODED | key absent on 517 rows; 53 of 116 present values are zero | ROBINHOOD, BASE, ETH | 24h aggregate | LOW |
| sell_volume_24h | `<bucket>[].sell_volume_24h` | number | 116/633 | `25250.74230996` | Sparse sell-volume field. It is absent on SOL and on most sampled rows. | NOT ENCODED | key absent on 517 rows; 109 of 116 present values are zero | ROBINHOOD, BASE, ETH | 24h aggregate | LOW |
| net_buy_24h | `<bucket>[].net_buy_24h` | number | 569/633 | `0.06` | Sparse GMGN-labelled 24h net-buy value. The payload does not encode its unit/formula. | NOT ENCODED | key absent on 64 rows | SOL, ROBINHOOD, BASE, ETH | 24h aggregate | LOW |
| holder_count | `<bucket>[].holder_count` | number | 633/633 | `2` | Holder-count value attached to the current trench row; no historical series is included. | count | no JSON null; 21 zeros | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| liquidity | `<bucket>[].liquidity` | number | 633/633 | `1.85` | Liquidity attached to the current trench row. Currency is not encoded. | NOT ENCODED | no JSON null; 209 zeros | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| market_cap | `<bucket>[].market_cap` | number | 633/633 | `3318.23` | Market cap attached to the current trench row. Currency is not encoded. | NOT ENCODED | no JSON null; 115 zeros | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| created_timestamp | `<bucket>[].created_timestamp` | number | 633/633 | `1790984846` | Token creation timestamp value; 10-digit Unix-second shape. | Unix seconds | no JSON null | SOL, ROBINHOOD, BASE, ETH | event timestamp | MEDIUM |
| complete_timestamp | `<bucket>[].complete_timestamp` | number | 633/633 | `1790984825` | Completion timestamp when populated. Zero is heavily used as a missing/not-complete sentinel. | Unix seconds or `0` | no JSON null; 448 zeros | SOL, ROBINHOOD, BASE, ETH | event timestamp | MEDIUM |
| open_timestamp | `<bucket>[].open_timestamp` | number | 633/633 | `1790984826` | Open timestamp when populated. Zero is heavily used as a missing/not-open sentinel. | Unix seconds or `0` | no JSON null; 448 zeros | SOL, ROBINHOOD, BASE, ETH | event timestamp | MEDIUM |
| fresh_wallet_rate | `<bucket>[].fresh_wallet_rate` | number | 633/633 | `0.1879` | A wallet-related rate, not a wallet count. The numerator, denominator, and window are not encoded in the response. | ratio | no JSON null; 473 zeros | SOL, ROBINHOOD, BASE, ETH | snapshot/window metric, semantics unverified | LOW |
| new_wallet_volume | `<bucket>[].new_wallet_volume` | number | 143/633 | `0` only | Sparse field; every one of the 143 present values is zero. It is not evidence of a new-wallet count. | NOT ENCODED | absent on 490 rows; all present values zero | SOL, ROBINHOOD, BASE; absent on ETH | unknown | LOW |

`buy_volume_24h + sell_volume_24h` matched `volume_24h` within one cent on only 9/116 rows where all three keys were present. `net_buy_24h` matched `buy_volume_24h - sell_volume_24h` within one cent on only 3 matching-key rows. These sparse fields therefore cannot be assigned a reliable formula or common unit from this sample.

## Wallet-field evidence

The union of keys matching `wallet|trader|buyer|seller|holder|unique|new` is:

- `bundler_trader_amount_rate`
- `fresh_wallet_rate`
- `holder_count`
- `new_wallet_volume`
- `rat_trader_amount_rate`
- `top_10_holder_rate`

`active_wallets`, `unique_buyers`, `unique_sellers`, `new_holders`, `new_buyers`, wallet addresses, buyer/seller addresses, and per-trade records are **NOT PROVIDED**. The two wallet-labelled fields are a rate and a sparse all-zero volume field, not counts.

## Exhaustive observed row schema

All paths below are `<bucket>[].<field>`; presence is not universal unless stated above.

- Array (2): `bonus_category` (20 rows, one string item), `fee_params` (549 rows, string items, lengths 0/5/6/8/33).
- Boolean (13): `co_d`, `cto_flag`, `dexscr_ad`, `dexscr_update_link`, `has_at_least_one_social`, `is_og`, `is_token_live`, `is_wash_trading`, `launch_flag`, `offchain`, `show_sharing_fee`, `twitter_change_flag`, `twitter_is_tweet`.
- Number (70): `bot_degen_count`, `bot_degen_rate`, `bundler_mhr`, `bundler_trader_amount_rate`, `buy_tax`, `buy_tips`, `buy_volume_24h`, `buys_24h`, `callout_count`, `complete_cost_time`, `complete_timestamp`, `created_timestamp`, `creator_balance_rate`, `creator_created_count`, `creator_created_inner_count`, `creator_created_open_count`, `creator_created_open_ratio`, `decimals`, `dev_team_hold_rate`, `dev_token_burn_amount`, `dev_token_burn_ratio`, `dexscr_boost_fee`, `dexscr_trending_bar`, `end_live_timestamp`, `entrapment_ratio`, `fresh_wallet_rate`, `fund_from_ts`, `holder_count`, `image_dup`, `launchpad_status`, `liquidity`, `market_cap`, `net_buy_24h`, `new_wallet_volume`, `open_timestamp`, `price`, `private_vault_hold_rate`, `progress`, `quote_address_type`, `rat_trader_amount_rate`, `renowned_count`, `rug_ratio`, `sell_tax`, `sell_volume_24h`, `sells_24h`, `smart_degen_count`, `sniper_count`, `start_live_timestamp`, `status`, `suspected_insider_hold_rate`, `swaps_24h`, `telegram_dup`, `tg_call_count`, `top70_sniper_hold_rate`, `top_10_holder_rate`, `total_buy_tax`, `total_fee`, `total_sell_tax`, `total_supply`, `trade_fee`, `tweet_publish_time`, `twitter_create_token_count`, `twitter_del_post_token_count`, `twitter_dup`, `twitter_rename_count`, `visiting_count`, `volume_24h`, `website_dup`, `x_user_follower`, `x_user_following`.
- Object (4): `farcaster`, `mk`, `tax_allocation`, `zora_social_info`.
- String (43): `address`, `burn_status`, `chain`, `creation_tool`, `creator`, `creator_token_status`, `exchange`, `fund_from`, `fund_from_address`, `instagram`, `is_honeypot`, `launch_creator`, `launchpad`, `launchpad_platform`, `logo`, `logo_small_base64`, `name`, `open_source`, `owner_renounced`, `pool_address`, `quote_address`, `renounced_freeze_account`, `renounced_mint`, `route_mint_a`, `route_mint_b`, `route_pool`, `route_vault_a`, `route_vault_b`, `s_qsafe`, `seq_index`, `standard`, `symbol`, `telegram`, `tiktok`, `trans_name`, `trans_name_zhcn`, `trans_symbol`, `trans_symbol_zhcn`, `twitter`, `twitter_community_id`, `twitter_community_name`, `twitter_handle`, `website`.

Nested object keys observed: `farcaster.{display_name,follower_count,username}`, `mk.{o,v}`, `tax_allocation.{dividend,dividend_tokens,is_vault,market_address,marketing,marketing_recipients,type,vault_factory}`, and `zora_social_info.{bio,display_name,follower_count,following_count,logo,username}`.

## Chain-level field presence

- All four chain unions: 112/132 fields.
- ROBINHOOD/BASE/ETH only: `buy_volume_24h`, `sell_volume_24h`, `is_honeypot`, `open_source`, `owner_renounced`.
- SOL/BASE/ETH only: `route_mint_a`, `route_mint_b`, `route_pool`, `route_vault_a`, `route_vault_b`.
- SOL/ROBINHOOD/BASE only: `buy_tips`, `has_at_least_one_social`, `new_wallet_volume`, `s_qsafe`, `sniper_count`, `trade_fee`.
- SOL/ROBINHOOD only: `tax_allocation`.
- BASE only: `farcaster`, `zora_social_info`.
- SOL only: `bonus_category`.

This is union availability: many listed keys occur only in some rows/categories on a chain.

## Endpoint verdict

- The main daily snapshot candidates are present and numeric on all 633 rows, but zero is common and no monetary unit is encoded.
- This endpoint provides 24h transaction-side counts, not distinct buyer/seller counts.
- It provides a current `holder_count`, but no holder history.
- Schema presence is materially variable by chain/category; optional-field handling is mandatory.
- A single Phase 1 response cannot establish repeat-query stability or cache behavior; no extra requests were made in Phase 2.
