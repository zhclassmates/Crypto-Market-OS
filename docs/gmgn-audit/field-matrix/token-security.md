# Phase 2 field matrix: token security

## Evidence set

- Existing raw responses only; no GMGN request was issued during this analysis.
- Files: `/tmp/gmgn-audit/raw/{sol,robinhood,base,eth}/token-security/001-response.json`.
- Shape: one flat security object per chain, with nested `lock_summary`.
- Rows: one tested production-selected token per chain; four objects total.
- All four objects have the same 28 top-level keys.

## Complete top-level schema

| field | JSON path | observed type | observed example/values | evidence-bound meaning | unit | nullable / missing sentinel | chains | historical or snapshot | confidence |
|---|---|---|---|---|---|---|---|---|---|
| address | `address` | string | `23Qh…pump` | Requested token address. | address | no JSON null | SOL, ROBINHOOD, BASE, ETH | identity | HIGH |
| average_tax | `average_tax` | string | `"0"` | GMGN-labelled average tax. | numeric string; scale not encoded | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| blacklist | `blacklist` | number | `-1`, `0` | Numeric blacklist flag/status. Exact enum meaning is not encoded. | enum-like number | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| burn_ratio | `burn_ratio` | string | `"0"`, `"1"` | Burn ratio. | ratio string | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| burn_status | `burn_status` | string | `""`, `"burn"` | Burn-status label. | text | 3/4 empty strings | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| buy_tax | `buy_tax` | string | `"0"` | Buy-tax value. | numeric string; scale not encoded | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| can_not_sell | `can_not_sell` | number | `0` | Numeric sell-restriction flag; all samples zero. | flag | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| can_sell | `can_sell` | number | `0` | Numeric sellability flag; all samples zero, so polarity cannot be validated. | flag | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| dev_token_burn_amount | `dev_token_burn_amount` | string | `"12043833.019004"` | GMGN-labelled developer token burn amount. Asset unit is not encoded. | numeric string; NOT ENCODED | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| dev_token_burn_ratio | `dev_token_burn_ratio` | string | `"0.011900505320087101"` | Developer token burn ratio. | ratio string | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| flags | `flags` | array | `[]` | Security flag array; empty in all four samples. | item type NOT OBSERVED | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| hide_risk | `hide_risk` | boolean | `false` | Hide-risk flag; false in all four samples. | boolean | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| high_tax | `high_tax` | string | `"0"` | GMGN-labelled high-tax value/flag. | numeric string; scale not encoded | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| honeypot | `honeypot` | number | `0` | Numeric honeypot flag/status; all samples zero. | flag | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| is_blacklist | `is_blacklist` | boolean or null | `false`, `null` | Boolean blacklist assessment when provided. | boolean | null in 3/4 | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| is_honeypot | `is_honeypot` | boolean or null | `false`, `null` | Boolean honeypot assessment when provided. | boolean | null in 1/4 | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| is_open_source | `is_open_source` | boolean or null | `true`, `null` | Boolean open-source assessment when provided. | boolean | null in 1/4 | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| is_renounced | `is_renounced` | boolean or null | `false`, `true`, `null` | Boolean renouncement assessment when provided. | boolean | null in 1/4 | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| is_show_alert | `is_show_alert` | boolean | `false` | Alert-display flag; false in all four samples. | boolean | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| lockInfo | `lockInfo` | null | `null` | Legacy/unused lock-info slot in these samples. | none | null in 4/4 | SOL, ROBINHOOD, BASE, ETH | unavailable | HIGH |
| lock_summary | `lock_summary` | object | nested object | Lock-status summary. | mixed | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| open_source | `open_source` | number | `0`, `1` | Numeric open-source flag/status. | flag | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| privileges | `privileges` | array or null | `[]`, privilege strings, `null` | Privilege labels when returned. | string list | null in 2/4 | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| renounced | `renounced` | number or null | `0`, `1`, `null` | Numeric renouncement flag/status. | flag | null in 1/4 | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| renounced_freeze_account | `renounced_freeze_account` | boolean | `true`, `false` | Freeze-account renouncement flag. | boolean | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| renounced_mint | `renounced_mint` | boolean | `true`, `false` | Mint renouncement flag. | boolean | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |
| sell_tax | `sell_tax` | string | `"0"` | Sell-tax value. | numeric string; scale not encoded | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | LOW |
| top_10_holder_rate | `top_10_holder_rate` | string | `"0.088"` | Top-10 holder concentration ratio. | ratio string | no JSON null | SOL, ROBINHOOD, BASE, ETH | snapshot | MEDIUM |

## Nested `lock_summary` schema

| field | JSON path | observed type | observed values | notes |
|---|---|---|---|---|
| is_locked | `lock_summary.is_locked` | boolean | `true`, `false` | Lock-status boolean. |
| lock_percent | `lock_summary.lock_percent` | string | numeric strings | Lock ratio string. |
| left_lock_percent | `lock_summary.left_lock_percent` | string | numeric strings | Remaining/unlocked ratio label; exact semantics are not encoded. |
| lock_tags | `lock_summary.lock_tags` | null | `null` in 4/4 | Unavailable in all samples. |
| lock_detail | `lock_summary.lock_detail` | array<object> | 1–2 items | Each item has `percent` (string), `pool` (string), and `is_blackhole` (boolean). |

Observed privilege labels are `blacklist`, `hidden_owner`, `max_tx_amount`, `mintable`, `multi_address`, and `proxy_calls`.

## Daily-metric and wallet evidence

The only key matching `wallet|trader|buyer|seller|holder|unique|new` is `top_10_holder_rate`, which is a concentration ratio, not `holder_count`.

This endpoint does **NOT PROVIDE** price, market cap, liquidity, volume, swaps, buys, sells, holder count, active wallets, unique buyers/sellers, new holders/buyers, historical values, or observation/update timestamps.

## Endpoint verdict

- Useful only as a point-in-time contract/security snapshot in this audit scope.
- Not a source for the requested daily market, transaction, holder-count, or wallet-participation metrics.
- Several overlapping security fields use different types (`number`, `boolean`, `string`, `null`), so aliases must not be collapsed without endpoint-specific normalization.
- One token per chain is insufficient to establish stability beyond the observed four objects; no extra requests were made in Phase 2.
