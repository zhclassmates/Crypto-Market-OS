# Phase 2 field matrix: market signal

## Evidence set

- Existing raw responses only; no GMGN request was issued during this analysis.
- Files: `/tmp/gmgn-audit/raw/{sol,robinhood}/market-signal/001-response.json`.
- BASE and ETH are intentionally not tested: the manifest records that production marks this endpoint unsupported for those chains and does not issue a request.
- Shape: `[{ id, token_address, signal_type, ath, market_cap, trigger_at, trigger_mc, first_trigger_mc, signal_times, signal_times_by_type, data, cur_data }]`.
- Rows: SOL 50, ROBINHOOD 50; 100 total. All 12 top-level keys are present on every row.
- `data` is an object with 155 union fields (153 present on every row); `cur_data` always has exactly `holder_count`, `liquidity`, and `top_10_holder_rate`.

## Signal-level fields

| field | JSON path | observed type | coverage | example | evidence-bound meaning | unit | nullable / missing sentinel | chains | historical or snapshot | confidence |
|---|---|---|---:|---|---|---|---|---|---|---|
| id | `[].id` | string | 100/100 | UUID-shaped string | Signal row identifier. | identifier | no JSON null | SOL, ROBINHOOD | event identity | HIGH |
| token_address | `[].token_address` | string | 100/100 | `731t…jigs` | Token address attached to the signal. | address | no JSON null | SOL, ROBINHOOD | identity | HIGH |
| signal_type | `[].signal_type` | number | 100/100 | `7` | Opaque signal-type code. Values observed: 1, 6, 7, 8, 18, 21. | enum-like number | no JSON null | SOL, ROBINHOOD | event classification | HIGH for values; LOW for meanings |
| trigger_at | `[].trigger_at` | number | 100/100 | `1790984873` | Signal trigger timestamp. | Unix seconds | no JSON null | SOL, ROBINHOOD | event timestamp | HIGH |
| trigger_mc | `[].trigger_mc` | number | 100/100 | `2575.5718` | GMGN-labelled market cap at the represented trigger. Currency is not encoded at this level. | NOT ENCODED | no JSON null | SOL, ROBINHOOD | event value | MEDIUM |
| first_trigger_mc | `[].first_trigger_mc` | number | 100/100 | `2575.5718` | GMGN-labelled market cap for the first trigger. Currency is not encoded at this level. | NOT ENCODED | no JSON null | SOL, ROBINHOOD | event value | MEDIUM |
| signal_times | `[].signal_times` | number | 100/100 | `1` | Signal occurrence count. | count | no JSON null | SOL, ROBINHOOD | accumulated event count | MEDIUM |
| signal_times_by_type | `[].signal_times_by_type` | object | 100/100 | `{ "7": 1 }` | Counts keyed by opaque signal-type strings. Observed keys: 1, 3, 6, 7, 8, 10, 11, 12, 13, 18, 19, 21. | counts | no JSON null | SOL, ROBINHOOD | accumulated event counts | MEDIUM |
| ath | `[].ath` | number | 100/100 | `2575.5718` | GMGN-labelled ATH value. Currency is not encoded. | NOT ENCODED | no JSON null; 2 zeros | SOL, ROBINHOOD | accumulated/event-related | LOW |
| market_cap | `[].market_cap` | number | 100/100 | `2575.5718` | Top-level market-cap value. It equals `data.market_cap` in only 18/100 rows, so the two paths must not be treated as aliases. | NOT ENCODED | no JSON null | SOL, ROBINHOOD | unspecified layer | MEDIUM for distinction; LOW for time semantics |

## Embedded token metrics

| field | JSON path | observed type | coverage | example | evidence-bound meaning | unit | nullable / missing sentinel | chains | historical or snapshot | confidence |
|---|---|---|---:|---|---|---|---|---|---|---|
| market_cap | `[].data.market_cap` | number | 100/100 | `2575.5718` | Embedded market-cap value. | NOT ENCODED | no JSON null | SOL, ROBINHOOD | embedded row value | LOW for time semantics |
| usd_market_cap | `[].data.usd_market_cap` | number | 100/100 | `2575.5718` | Explicitly USD-labelled market cap. It equals `data.market_cap` in 100/100 rows. | USD | no JSON null | SOL, ROBINHOOD | embedded row value | HIGH for sample equality/unit label; LOW for time semantics |
| holder_count | `[].data.holder_count` | number | 100/100 | `1` | Holder count in the embedded `data` layer. | count | no JSON null; 3 ROBINHOOD zeros | SOL, ROBINHOOD | embedded row value | LOW for time semantics |
| liquidity | `[].data.liquidity` | number | 100/100 | `1.8532361624` | Liquidity in the embedded `data` layer. Currency is not encoded. | NOT ENCODED | no JSON null; 18 zeros | SOL, ROBINHOOD | embedded row value | LOW for time semantics |
| holder_count | `[].cur_data.holder_count` | number | 100/100 | `2` | Holder count in the explicitly named `cur_data` layer. It differs from `data.holder_count` in 82/100 rows. | count | no JSON null | SOL, ROBINHOOD | current-labelled snapshot | MEDIUM |
| liquidity | `[].cur_data.liquidity` | number | 100/100 | `38.865770664427615` | Liquidity in the explicitly named `cur_data` layer. It differs from `data.liquidity` in 91/100 rows. | NOT ENCODED | no JSON null; 7 zeros | SOL, ROBINHOOD | current-labelled snapshot | MEDIUM |
| top_10_holder_rate | `[].cur_data.top_10_holder_rate` | number | 100/100 | `0.0075` | Current-layer top-10 holder ratio. | ratio | no JSON null; 29 zeros | SOL, ROBINHOOD | current-labelled snapshot | MEDIUM |
| created_timestamp | `[].data.created_timestamp` | number | 100/100 | `1790984873` | Token creation timestamp value; 10-digit Unix-second shape. | Unix seconds | no JSON null | SOL, ROBINHOOD | event timestamp | MEDIUM |
| created_timestamp_us | `[].data.created_timestamp_us` | number | 100/100 | `0` | Microsecond-labelled field, but every sampled value is zero. | unknown / zero sentinel | no JSON null; 100 zeros | SOL, ROBINHOOD | unusable in sample | HIGH |
| open_timestamp | `[].data.open_timestamp` | number | 100/100 | `1790734354` | Open timestamp when populated. | Unix seconds or `0` | no JSON null; 71 zeros | SOL, ROBINHOOD | event timestamp | MEDIUM |
| open_timestamp_us | `[].data.open_timestamp_us` | number | 100/100 | `0` | Microsecond-labelled field, but every sampled value is zero. | unknown / zero sentinel | no JSON null; 100 zeros | SOL, ROBINHOOD | unusable in sample | HIGH |
| fresh_wallet_rate | `[].data.fresh_wallet_rate` | number | 100/100 | `0.144` | Wallet-related rate; no numerator, denominator, or window definition is encoded. | ratio | no JSON null; 66 zeros | SOL, ROBINHOOD | embedded window/snapshot metric | LOW |

## Interval metrics are structurally present but unusable in this sample

The following 20 numeric fields are present on all 100 rows and are zero on all 100 rows:

- `data.volume_{1m,1h,6h,24h}`
- `data.swaps_{1m,1h,6h,24h}`
- `data.buys_{1m,1h,6h,24h}`
- `data.sells_{1m,1h,6h,24h}`
- `data.net_buy_{1m,1h,6h,24h}`

Consequently this sample does **not** demonstrate usable activity values from `market signal`, even though the keys exist. The `swaps = buys + sells` relation holds only trivially because all components are zero.

## Wallet-field evidence

The only `data` keys matching `wallet|trader|buyer|seller|holder|unique|new` are `bundler_trader_amount_rate`, `claim_wallet_address`, `fresh_wallet_rate`, `holder_count`, `rat_trader_amount_rate`, `top_10_holder_rate`, and `top_10_holder_rate_snp`.

`claim_wallet_address` is a claim-related address field, not a transaction-participant series. `active_wallets`, `unique_buyers`, `unique_sellers`, `new_holders`, `new_buyers`, buyer/seller addresses, and per-trade records are **NOT PROVIDED**.

## Exhaustive observed `data` schema

- Boolean (16): `callout_declaration`, `claim_fee_is_first`, `cto_flag`, `dexscr_ad`, `dexscr_trending_bar`, `dexscr_update_link`, `has_at_least_one_social`, `is_og`, `is_token_live`, `is_wash_trading`, `offchain`, `quote_is_safe`, `renounced_freeze_account`, `renounced_mint`, `show_sharing_fee`, `twitter_is_tweet`.
- Always null (4): `bonus_category`, `fee_params`, `fracaster`, `zora_social_info`.
- Number (94): `binance_charity_tax`, `bot_degen_count`, `bot_degen_rate`, `bundler_mhr`, `bundler_trader_amount_rate`, `burn_tax`, `buy_tax`, `buys_1h`, `buys_1m`, `buys_24h`, `buys_6h`, `callout_count`, `complete_cost_time`, `complete_timestamp`, `created_timestamp`, `created_timestamp_us`, `creator_balance_rate`, `creator_created_count`, `creator_created_open_count`, `creator_created_open_ratio`, `decimals`, `dev_tax`, `dev_team_hold_rate`, `dev_token_burn_amount`, `dev_token_burn_ratio`, `dexscr_boost_fee`, `dividend_tax`, `end_live_timestamp`, `entrapment_ratio`, `fresh_wallet_rate`, `fund_from_ts`, `giggle_charity_tax`, `holder_count`, `image_dup`, `liquidity`, `liquidity_tax`, `market_cap`, `max_amount`, `min_amount`, `net_buy_1h`, `net_buy_1m`, `net_buy_24h`, `net_buy_6h`, `open_timestamp`, `open_timestamp_us`, `other_tax`, `price_volatility_rate`, `priority_fee`, `private_vault_hold_rate`, `progress`, `rat_trader_amount_rate`, `renowned_count`, `rug_ratio`, `sell_tax`, `sells_1h`, `sells_1m`, `sells_24h`, `sells_6h`, `smart_degen_count`, `sniper_count`, `start_live_timestamp`, `status`, `suspected_insider_hold_rate`, `swaps_1h`, `swaps_1m`, `swaps_24h`, `swaps_6h`, `telegram_dup`, `tg_call_count`, `tip_fee`, `top70_sniper_hold_rate`, `top_10_holder_rate`, `top_10_holder_rate_snp`, `total_buy_tax`, `total_fee`, `total_sell_tax`, `total_supply`, `trade_fee`, `trigger_count`, `tweet_publish_time`, `twitter_create_token_count`, `twitter_del_post_token_count`, `twitter_dup`, `twitter_rename_count`, `usd_market_cap`, `vault_tax`, `visiting_count`, `volume_1h`, `volume_1m`, `volume_24h`, `volume_6h`, `website_dup`, `x_user_follower`, `x_user_following`.
- String (41): `address`, `burn_status`, `chain`, `claim_avatar`, `claim_fee_sol_amount`, `claim_platform`, `claim_platform_avatar`, `claim_platform_username`, `claim_twitter_user_name`, `claim_wallet_address`, `creation_tool`, `creator`, `creator_token_status`, `exchange`, `fund_from`, `fund_from_address`, `instagram`, `is_honeypot`, `launchpad`, `launchpad_platform`, `logo`, `migrated_pool_exchange`, `name`, `open_source`, `owner_renounced`, `pool_address`, `quote_address`, `seq_index`, `standard`, `symbol`, `tc_name`, `tcid`, `telegram`, `tiktok`, `trans_name`, `trans_name_zhcn`, `trans_symbol`, `trans_symbol_zhcn`, `twitter`, `twitter_handle`, `website`.

`price_volatility_rate` is present on 25/100 rows and `migrated_pool_exchange` on 29/100; all other `data` keys are present on every row.

## Endpoint verdict

- The signal event layer and trigger timestamp are populated.
- The sample exposes two distinct holder/liquidity layers (`data` and `cur_data`); only `cur_data` is explicitly current-labelled.
- All activity-window metrics are zero in both chain samples, so this endpoint cannot be accepted as evidence for daily volume/swaps/buys/sells.
- It provides no unique-wallet or wallet-history series.
- No BASE/ETH call was made because production does not call this endpoint for those chains.
