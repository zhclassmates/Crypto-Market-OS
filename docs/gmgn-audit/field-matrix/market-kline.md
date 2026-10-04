# Phase 2 field matrix: market kline

## Evidence set

- Existing raw responses only; no GMGN request was issued during this analysis.
- Files: `/tmp/gmgn-audit/raw/{sol,robinhood,base,eth}/market-kline/001-response.json`.
- All commands used `--resolution 1d` with a roughly 100-day range, as recorded in the existing meta files.
- Shape: `{ list: [...] }`.
- Candles: SOL 1, ROBINHOOD 18, BASE 1, ETH 100; 120 total.
- Every candle has the same eight keys and no JSON nulls.

## Complete candle schema

| field | JSON path | observed type | example | evidence-bound meaning | unit | nullable / missing sentinel | chains | historical or snapshot | confidence |
|---|---|---|---|---|---|---|---|---|---|
| time | `list[].time` | number | `1790899200000` | 1d candle timestamp. All 120 values are 13-digit millisecond timestamps aligned to 00:00:00 UTC; multi-row series step by exactly 86,400,000 ms. | Unix milliseconds | no JSON null | SOL, ROBINHOOD, BASE, ETH | historical bar timestamp | HIGH |
| open | `list[].open` | numeric string | `0.0000044178306` | Candle open price. Quote currency is not encoded. | NOT ENCODED | no null/empty string | SOL, ROBINHOOD, BASE, ETH | historical bar | HIGH for OHLC role; LOW for currency |
| high | `list[].high` | numeric string | `0.000043607078` | Candle high price. Quote currency is not encoded. | NOT ENCODED | no null/empty string | SOL, ROBINHOOD, BASE, ETH | historical bar | HIGH for OHLC role; LOW for currency |
| low | `list[].low` | numeric string | `0.0000044178306` | Candle low price. Quote currency is not encoded. | NOT ENCODED | no null/empty string | SOL, ROBINHOOD, BASE, ETH | historical bar | HIGH for OHLC role; LOW for currency |
| close | `list[].close` | numeric string | `0.0000057961466` | Candle close/latest price. The payload has no finalized flag. | NOT ENCODED | no null/empty string | SOL, ROBINHOOD, BASE, ETH | historical/current bar | HIGH for OHLC role; LOW for finalization |
| volume | `list[].volume` | numeric string | `66339.25253781` | Candle volume. The payload does not identify the asset/currency unit. | NOT ENCODED | no null/empty string | SOL, ROBINHOOD, BASE, ETH | historical/current bar | HIGH for candle-volume role; LOW for unit |
| amount | `list[].amount` | numeric string | `4042136488.820541` | A second candle quantity distinct from `volume`; the response does not define its unit. | NOT ENCODED | no null/empty string | SOL, ROBINHOOD, BASE, ETH | historical/current bar | LOW |
| source | `list[].source` | string | `""` | Source label slot. It is empty in all 120 candles. | text | 120/120 empty strings | SOL, ROBINHOOD, BASE, ETH | metadata | HIGH |

## Timestamp and finalization evidence

- `1782345600000` → `2026-06-25T00:00:00Z` → `2026-06-25 08:00:00 CST`.
- `1790899200000` → `2026-10-02T00:00:00Z` → `2026-10-02 08:00:00 CST`.
- The latest candle starts at `2026-10-02T00:00:00Z`, while the four existing collection meta records finished between `2026-10-02T23:48:30Z` and `2026-10-02T23:57:56Z`.

Inference from that timing: `time` represents the UTC daily bar open, not bar close. The latest returned candle was observed before its UTC day ended and therefore was still in progress. There is no `finalized`, `closed`, `updated_at`, or fetched-at field inside the response; collection time exists only in the audit meta file.

## Fields explicitly absent from candles

No candle key matches any of:

- trade count / swaps
- buys / sells
- buyer count / seller count
- wallet count / active wallets
- holder count
- liquidity
- market cap

The endpoint therefore provides historical OHLC plus `volume` and an undefined `amount`; it does not provide historical transaction counts, wallet participation, holder counts, liquidity, or market cap.

## Endpoint verdict

- Historical daily close: DIRECT.
- Historical daily volume: DIRECT, but unit is not encoded in raw JSON.
- Historical swaps/buys/sells: NOT PROVIDED.
- Historical active/unique buyer/unique seller wallets: NOT PROVIDED.
- Historical holder count/liquidity/market cap: NOT PROVIDED.
- Current-day bar finalization: NOT PROVIDED; the sampled latest bar was demonstrably in progress at fetch time.
