# 六个字段语义探针（2026-10-03）

GMGN 请求 6 次（`token info` ×4、`token pool` ×2），全部走 `market_collect.gmgn()` 的共享冷却，串行，0 次限流。
脚本 `scripts/field-probe-fetch.py`，raw 在 `raw/probe/`。每次 GMGN 返回后立刻抓同一 token 的独立数据：
GeckoTerminal（全部池子的成交、笔数、独立买卖地址数、池子储备）与 Blockscout（链上持币地址数，ETH / BASE）。

样本：ETH wildebeest（`0x5773…cccc`，上轮流动性冲突 2.92× 的那个）、ETH SKY、SOL www、BASE TOSHI。

## 结论

| 字段 | 所在 endpoint | 真实含义 | 单位 / 窗口 | 证据 | 判定 |
|---|---|---|---|---|---|
| `buy_volume_{w}` / `sell_volume_{w}` | `token info` · `price.*`（窗口 1m/5m/1h/6h/24h）；Trenches 另有稀疏的 `buy_volume_24h` / `sell_volume_24h` | 窗口内**买方向 / 卖方向**成交额，**按 token 汇总所有池子**（不是只算主池） | USD；滚动窗口 | 4 个 token × 3 个窗口，`buy + sell = volume`，误差 0；GMGN 24h volume / GeckoTerminal 全部池子之和 = 0.97 / 0.96 / 0.98 / 0.90，只算主池则差很多（SKY 主池只有总量的 36%）；方向与笔数一致（TOSHI 1h：7 笔买 $124，59 笔卖 $3,180） | **CONFIRMED**（token info 版本）。Trenches 版本没有验证 |
| `unique_swap_traders` | — | **GMGN OpenAPI 不提供** | — | 4 个 token / 3 条链的 `token info` 里都没有；已保存的 Trending / Hot / Trenches / Signal / Security / Kline / Pool payload 里都没有；gmgn-cli 1.6.6 源码和全部 skill 文档里也没有这个名字（采集本来就用 `--raw`，没有被裁掉字段） | **NOT PROVIDED** |
| `new_swap_traders` | — | **GMGN OpenAPI 不提供** | — | 同上 | **NOT PROVIDED** |
| `liquidity` | `token info` 顶层 = `pool.liquidity`；`token pool` 同值 | **只算一个主池**（`biggest_pool_address`），数值 = **2 × 主池 quote 一侧的 USD 价值** | USD；快照 | `liquidity / (2 × quote_reserve_value)` = 0.9992 / 0.9999 / 1.0000 / 0.9990；TOSHI（uniswap_v3）实际两侧之和是 liquidity 的 1.19 倍，说明不是两侧相加；与 GeckoTerminal 主池储备一致（77,023 vs 77,016；152,281 vs 153,553；10.28M vs 10.26M），远小于全部池子之和（93k / 325k / 23.1M / 1.56M） | **CONFIRMED**（token info / pool） |
| `holder_count` | `token info`（= `stat.holder_count`）、Trending / Hot / Trenches、Signal `cur_data` | **当前持币地址数**（链上余额 > 0 的地址，GMGN 可能排除了一部分） | 地址数；快照 | 与 Blockscout 对比：wildebeest 1,280 = 1,280；SKY 16,057 vs 16,034（+0.1%）；TOSHI 970,985 vs 1,038,273（−6.5%，大币上 GMGN 偏少，排除规则未知） | **CONFIRMED**（含义）；大币上与链上计数有几个百分点的差 |

## 附带结论

- **`buys` / `sells` 是交易笔数，不是钱包数。** 同一窗口 GeckoTerminal 给出独立地址数：wildebeest 24h GMGN `buys = 251`，独立买家只有 165；SKY `buys = 2,864`，独立买家 946。GMGN 笔数比 GeckoTerminal 全池笔数少 4–23%（过滤规则未知）。
- **上轮"ETH liquidity 冲突"有了解释方向**：Trending 的 74,707 与这次 `token info` 的 77,023 / GeckoTerminal 主池 77,016 一致，Trending 用的是同一个主池口径。Trenches 当时给的 25,573 接近该池开盘时的 `initial_liquidity` 26,810，更像是**过期值或开盘值**。这次没有重新请求 Trenches，所以这一点仍是推断。
- **最接近"钱包数"的字段都不能顶替**：`wallet_tags_stat.fresh_wallets` / `bundler_wallets` 多次正好等于 1000（SOL www、ETH SKY 992），看起来有 **1000 的上限**；`stat.fresh_wallet_rate` 是比例。两者都不是"窗口内的独立交易者 / 新交易者"。
- 如果产品需要独立交易者数，可用的外部来源是 GeckoTerminal 每个池子的 `transactions.{m5,h1,h6,h24}.buyers / sellers`。注意它按池子统计，跨池相加会重复计算同一个钱包。

## 对 V1 的影响

- `buy_volume_{w}` / `sell_volume_{w}` 可以升为 READY，但只来自 `token info`，需要逐个 token 请求，现有采集链路不会自动拿到。
- `liquidity` 的语义已清楚（主池、2 × quote 一侧、USD），按"主池流动性"展示是安全的。Trenches 的 liquidity 仍然不要和 Trending / token info 混用。
- `unique_swap_traders` / `new_swap_traders`：GMGN 拿不到。要么接 GeckoTerminal，要么从产品里去掉。
