# Daily Token Intelligence Capability Map

> 问题：GMGN 能否提供"一个代币每天有多少资金、多少钱包、多少新增参与者进入"？
> 主线：volume → wallets → new wallets → holders → smart money → flow → growth / acceleration。
> 本轮没有写产品代码，没有 UI，没有 deploy。

## 结论（先看这里）

| 维度 | 结论 |
|---|---|
| **资金（成交额、买入额、卖出额、净买入）** | **能**。`token info` 直接给出 1m / 5m / 1h / 6h / 24h 滚动窗口的成交额、买入额、卖出额，并且 `买入额 + 卖出额 = 成交额` 在 raw 中精确成立。日 K 给出约 100 天的**按自然日（UTC）**成交额历史。 |
| **交易次数（总 / 买 / 卖）** | **能（滚动窗口）**；**没有**按自然日的历史，只能自己按日快照。 |
| **钱包数（活跃钱包、买家数、卖家数、交易者数）** | **NOT_AVAILABLE FROM GMGN**。所有 endpoint 都没有 unique wallet / trader / buyer / seller 计数字段；钱包列表接口最多返回 100 个钱包，无法推算总数。 |
| **新增钱包 / 首次买家** | **NOT_AVAILABLE FROM GMGN**。没有直接字段；钱包级的 `start_holding_at` 只覆盖 top 100，不能代表全体。 |
| **Holder** | 只有**当前快照** `holder_count`。日增量必须自己按日快照，得到的是**净变化**，不是"新增 holder"。 |
| **Smart Money** | 只有**当前快照计数**（当前持有的 smart / KOL / whale 钱包数）；按日快照可得**净变化**。"每天新进入的 smart money 数"和"每天 smart money 买入额"无法可靠得到（交易流只覆盖约 2 分钟）。 |

一句话：**GMGN 能回答"每天多少钱、多少笔交易、在加速吗"，不能回答"每天多少个钱包、多少个新钱包"。** 后者需要其他数据源（§9）。

## 1. 证据

| 来源 | 内容 |
|---|---|
| vendor 文档（gmgn-cli 1.6.6） | `skills/gmgn-token/SKILL.md`（info / holders / traders）、`skills/gmgn-track/SKILL.md`（kol / smartmoney）、`skills/gmgn-market/SKILL.md`；本地 `gmgn-cli --help`（不联网） |
| 本轮真实 raw（`raw/daily/`，2026-10-03 12:31–12:32 CST，5 次请求，全部经过共享冷却保护，0 次限流） | `token info`（SOL `GAwh…9S9H`、ETH `0x5607…9279`）、`token traders`（SOL，limit 100）、`token holders`（SOL，limit 100）、`track smartmoney`（SOL，limit 200） |
| 已有 raw（`raw/v1/`） | 四链 Trending / Trenches、Signal，用于跨 endpoint 比对 |
| 已有生产数据（只读） | 日 K `token_candle`（`volume` = USD，已在字段字典中验证） |

能力清单（本地 help 确认）：`token info / security / pool / holders / traders`，`market kline / trending / trenches / signal / hot-searches / search`，`track follow-tokens / follow-token-groups / follow-wallet / kol / smartmoney`，`portfolio`，`swap`，`order`，`cooking`。**没有任何 per-token 的成交明细（trades）接口。**

## 2. 每日成交数据

| Metric | Endpoint · Raw path | Window | Unit | 证据 | 状态 |
|---|---|---|---|---|---|
| 成交额 | `token info` · `price.volume_{1m,5m,1h,6h,24h}` | 滚动窗口（相对查询时刻） | USD（数字字符串） | raw：SOL `"31532848.18"`；与 Trending 24h `volume` 一致（ETH 相隔 43 分钟比值 1.004） | **READY**（滚动窗口） |
| 成交额 | Trending / Hot · `volume`；Trenches · `volume_24h` | 请求 interval（24h）/ 24h | USD | 字段字典 | READY |
| **按自然日的成交额** | `market kline --resolution 1d` · `list[].volume` | **UTC 自然日**，约 100 天历史 | USD | 字段字典（`volume / amount / close` ≈ 1.0015） | **READY**（唯一的原生日级历史） |
| 买入额 | `token info` · `price.buy_volume_{w}` | 滚动窗口 | USD | raw：buy + sell = volume，SOL 与 ETH 都精确相等 | **READY**（VERIFIED_BY_RAW） |
| 卖出额 | `token info` · `price.sell_volume_{w}` | 滚动窗口 | USD | 同上 | **READY** |
| 净买入额 | — | — | — | 由 buy − sell 计算 | **DERIVED · READY** |
| 净买入（Trenches） | `<bucket>[].net_buy_24h` | 24h | UNKNOWN | 公式无法复现（字段字典） | NEEDS_CONFIRMATION，不用 |
| 交易次数 | `token info` · `price.swaps_{w}`；Trending · `swaps`；Trenches · `swaps_24h` | 滚动窗口 | 笔 | `swaps = buys + sells`（SOL 210,234 = 111,875 + 98,359；ETH 5,721 = 2,869 + 2,852） | **READY**（滚动窗口） |
| 买入笔数 / 卖出笔数 | `token info` · `price.buys_{w}` / `price.sells_{w}` | 滚动窗口 | 笔 | 同上 | **READY** |
| 按自然日的交易次数 | — | — | — | 日 K **没有**笔数字段 | **NOT_AVAILABLE** 作为历史；**DERIVED**：UTC 00:00 后快照 `swaps_24h` ≈ 前一个自然日（见 §8） |

各 endpoint 一致性：Trending `swaps / buys / volume` 与 `token info` 的 `*_24h` 一致（ETH 约 1%；SOL 相隔 1.6 小时差 15–21%，符合热门币热度回落的滚动窗口）。**24h 都是滚动 24h，不是 UTC 自然日。**

## 3. 钱包参与（最高优先级）

> GMGN 能否知道某个 token 在一天内有多少个不同钱包参与交易？ → **不能。**

| 查找对象 | 结果 |
|---|---|
| unique traders / trader count / participant count | **NOT PROVIDED**。`token info` 全部 176（SOL）/ 166（ETH）个路径中没有；Trending / Hot / Trenches / Signal 中也没有 |
| buyer count / seller count / unique buyers / sellers | **NOT PROVIDED**。`buys` / `sells` 是**交易笔数**（`swaps = buys + sells` 精确成立），不是钱包数 |
| wallet count（窗口内活跃钱包） | **NOT PROVIDED** |
| `token traders` / `token holders` 能否推算 | **不能**。两者都只返回钱包列表，**上限 100**（`--limit` 最大 100）；没有总数字段；默认排序下两者结果完全相同（都按持仓占比取 top 100）。该 token 有 8,897 个 holder、24h 有 210,234 笔交易，top 100 钱包的累计买入笔数只有 2,124 笔（约 2%） |
| `track kol / smartmoney` | 只覆盖标签钱包，而且是全链最新流（见 §6），不是某个 token 的全部参与者 |

必须区分：

```text
交易次数（swaps / buys / sells）    ≠ 钱包数        → GMGN 只有前者
buyer count                        ≠ holder count  → GMGN 两者都没有按窗口的版本
holder count（当前持有）            ≠ 每日活跃钱包   → GMGN 只有前者（快照）
```

## 4. 新增钱包

| 查找对象 | 结果 | 分类 |
|---|---|---|
| new wallets / new traders / first-time buyers / new buyers / new holders | 没有字段 | **NOT_AVAILABLE** |
| 钱包级 `start_holding_at`（traders / holders 列表，"首次获得该 token 的时间"） | 存在，但只覆盖 top 100 钱包 | 只能给 top 100 做 DERIVED；**对整个 token NOT_AVAILABLE** |
| 钱包级 `is_new` / `tags` 含 `fresh_wallet` | 存在（top 100 中 6 个 `is_new`，20 个 `fresh_wallet`） | 含义是"钱包本身是新的"，不是"首次买这个 token"；而且只有 top 100 |
| `token info` · `wallet_tags_stat.fresh_wallets` | SOL `1000`，ETH `992` | 当前持有者中 fresh 钱包的数量。**疑似上限 1000**（SOL 的 `bundler_wallets` 也恰好 1000） → **NEEDS_CONFIRMATION** |
| `token info` · `stat.fresh_wallet_rate` | SOL `"0.1482"`，ETH `"0"` | ETH 有 992 个 fresh 钱包但比例为 0，**自相矛盾**；SOL 的 1000 / 8897 = 0.112 ≠ 0.1482，分母未知 → **NEEDS_CONFIRMATION** |
| Trenches `fresh_wallet_rate` / `new_wallet_volume` | 比例 / 全 0 | 不是计数（字段字典） |

你要的定义（"某钱包历史上从未交易 / 持有该 token，当天第一次参与"）需要该 token 的**完整成交明细或全体持有者历史**。GMGN 没有 per-token 成交明细接口 → **NOT_AVAILABLE FROM GMGN**。

## 5. Holder 增长

| Metric | 结果 |
|---|---|
| `holder_count`（`token info` 顶层与 `stat.holder_count`；Trending / Hot / Trenches；Signal `cur_data`） | **当前快照**。各 endpoint 一致（ETH 16,020 vs 16,022）。"持有"的余额门槛 UNKNOWN |
| holder 历史序列 / holder change / new holders | **NOT PROVIDED** |
| 日增量 | **DERIVED**：每天固定时刻快照 → `net_holder_change = holders_today − holders_yesterday`。这是**净增量**（新进 − 清仓），**不是新增 holder 数** |
| 集中度 | `stat.top_10_holder_rate` / `dev.top_10_holder_rate`（当前快照）；Trending 中出现过 > 1 的值（字段字典 NEEDS_CONFIRMATION） |

> 可以通过每日快照自己建立 holder 历史，但 GMGN 不直接提供历史 holder 序列。
> 生产库 `discovery_event.metadata_json.holder_count` 已有"上榜时"的机会性观测，不是固定频率。

## 6. 钱包质量

| 标签 | 来源 · 路径 | 含义 | 能否做成每日指标 |
|---|---|---|---|
| Smart money 钱包数 | `token info` · `wallet_tags_stat.smart_wallets`；Trending · `smart_degen_count`（两者相等：SOL 169 vs 170、ETH 77 vs 77） | 当前**持有**该 token 的 smart 钱包数（文档说法；"持有"未独立验证） | 按日快照 → **净变化**。"每天**新增** smart money 数"需要进出明细 → NOT_AVAILABLE |
| KOL 钱包数 | `wallet_tags_stat.renowned_wallets` = Trending `renowned_count`（19 = 19、16 = 16） | 同上 | 同上 |
| Whale 钱包数 | `wallet_tags_stat.whale_wallets`（SOL 7、ETH 513） | 当前快照；whale 的阈值 UNKNOWN | 净变化 |
| Sniper / rat trader / bundler / creator / top | `wallet_tags_stat.*` | 当前快照；`bundler_wallets = 1000` 疑似上限 | 净变化；上限问题 NEEDS_CONFIRMATION |
| Fresh 钱包 | `wallet_tags_stat.fresh_wallets` | 疑似上限 1000 | NEEDS_CONFIRMATION |
| Bot | `stat.bot_degen_count` = Trending `bot_degen_count`（1123 vs 1133） | 当前快照 | 净变化；EVM 部分链全 0（字段字典） |
| Profitable wallets / 钱包 PnL | `token traders / holders` · `profit`、`realized_profit`、`unrealized_profit` | 只有 top 100 钱包 | 只能作为详情页样本 |
| 每天 smart money 买入额 | `track smartmoney` | 全链最新流：请求 200 条只返回 **100** 条，覆盖 **1.8 分钟**（12:30:41–12:32:28），没有游标 / 时间过滤 / token 过滤 | **NOT_AVAILABLE（不可靠）**：一天约需 800 次请求且仍可能有缺口，与现有限频冲突 |
| 每天 whale 新进入数 | — | — | **NOT_AVAILABLE** |

## 7. 资金流

| Metric | 结果 |
|---|---|
| buy amount / sell amount（USD） | **DIRECT**：`token info` · `price.buy_volume_{w}` / `price.sell_volume_{w}`（滚动窗口） |
| net buy | **DERIVED**：`net_buy_usd = buy_volume − sell_volume`（SOL 24h：15.33M − 16.21M = **−0.88M**；ETH 24h：**+0.35M**） |
| net buy 占比 | **DERIVED**：`net_buy / volume`（SOL −2.8%，ETH +5.7%） |
| inflow / outflow / netflow（token 级） | 没有独立字段；上面的 buy / sell 就是交易侧流入 / 流出 |
| 钱包级 netflow / PnL | `token traders / holders` · `netflow_usd`、`realized_profit`、`unrealized_profit`：只有 top 100 |
| liquidity inflow | 没有字段；只能对**同一 endpoint** 的 liquidity 快照做差分（跨 endpoint 口径冲突，见字段字典 §5） |
| 按自然日的买入额 / 卖出额历史 | **NOT PROVIDED**（日 K 没有买卖拆分）→ 只能按日快照 `buy_volume_24h` / `sell_volume_24h` |

## 8. 时间序列能力

| Metric | Snapshot | 1h | 6h | 24h | Historical Daily | Can derive |
|---|---|---|---|---|---|---|
| 成交额 | — | ✅ info | ✅ info | ✅ info / T / H / Tr | ✅ **日 K（UTC，约 100 天）** | 增长、加速 |
| 买入额 / 卖出额 | — | ✅ info | ✅ info | ✅ info | ❌ | 日快照 → 日序列 |
| 净买入 | — | 算 | 算 | 算 | ❌ | 日快照 |
| 交易次数（总 / 买 / 卖） | — | ✅ info | ✅ info | ✅ info / T / H / Tr | ❌ | 日快照 → 日序列 |
| 活跃钱包 / 买家 / 卖家 | ❌ | ❌ | ❌ | ❌ | ❌ | **NOT_AVAILABLE** |
| 新增钱包 / 新买家 | ❌ | ❌ | ❌ | ❌ | ❌ | **NOT_AVAILABLE** |
| holder_count | ✅ 全部 endpoint | — | — | — | ❌ | 日快照 → 净变化 |
| smart / KOL / whale 钱包数 | ✅ info / T | — | — | — | ❌ | 日快照 → 净变化 |
| 新增 smart money / smart 买入额 | ❌ | ❌ | ❌ | ❌ | ❌ | NOT_AVAILABLE（交易流覆盖不足） |
| 价格 | ✅ | ✅ `price_1h`（窗口起点价） | ✅ `price_6h` | ✅ `price_24h` | ✅ 日 K | 收益、连涨 |

**怎么形成"每天一行"**（DERIVED，推荐）：

1. **日 K**（已在采集）→ 每个 UTC 日的 `volume_usd`、OHLC。真正的自然日。
2. **UTC 日切快照**：每天 UTC 00:00 后尽快对目标 token 调一次 `token info`，记录 `*_24h`（成交额、买入额、卖出额、交易次数、买卖笔数）+ `holder_count` + `wallet_tags_stat.*`。
   - 滚动 24h 在 00:00 时刻 ≈ 前一个 UTC 自然日。误差 = 快照延迟（例如延迟 10 分钟，窗口就偏移 10 分钟）。必须保存 `observed_at` 并标注为"rolling-24h @ T"，**不能冒充精确自然日**。
   - holder / smart 数是时点值 → 差分得到净变化。
3. 成本：`token info` 是 per-token 调用（文档权重 1）。N 个 token 每天需要 N 次调用。生产 collector 已经在触发限频，**必须先做配额规划**（例如只覆盖候选池 / 自选 / 连涨榜中的 token）。

## 9. 可计算指标（DERIVED）的可行性

| 指标 | 公式 | 输入 | 可行性 |
|---|---|---|---|
| volume_growth_1d / 3d / 7d | `vol_d0 / vol_d−N`，或与 N 日均值比较 | 日 K `volume`（自然日） | **READY**（已有约 100 天历史） |
| 今日成交额 / 7 日均值 | `vol_today / mean(vol_d−7..d−1)` | 日 K | **READY**；盘中可用 `volume_24h` 滚动值作近似 |
| tx_growth、buy_tx_growth | 日快照序列比值 | info `*_24h` 日快照 | 有了 7 天快照后 READY；**从部署起开始积累**（无法回填） |
| buyer_seller_ratio（笔数） | `buys / sells` | info / Trending | READY（标注为"笔数比"，不是人数比） |
| 净买入占比 | `(buy_vol − sell_vol) / vol` | info | READY（滚动窗口） |
| 短期加速 | `volume_1h × 24 / volume_24h`、`swaps_1h × 24 / swaps_24h`、`volume_6h × 4 / volume_24h` | info 多窗口 | **READY（单次快照就能算）**——最有价值的"今天是否突然加速" |
| 价格多窗口 | `price / price_{1h,6h,24h} − 1` | info | READY |
| wallet_growth_1d / 3d / 7d | — | 需要钱包数 | **NOT_AVAILABLE FROM GMGN** |
| new_wallet_ratio | new_wallets / active_wallets | 两者都没有 | **NOT_AVAILABLE FROM GMGN** |
| volume_per_wallet | volume / active_wallets | 没有 active_wallets | **NOT_AVAILABLE FROM GMGN**；可用 `volume / swaps`（每笔平均成交额）替代，但含义不同，必须改名 |
| holder 净增长 1d / 3d / 7d | 快照差分 | holder_count 日快照 | 积累后 READY（净变化，不是新增） |
| smart money 净增长 | 快照差分 | `smart_wallets` 日快照 | 积累后 READY（净变化） |

## 10. 字段记录（本轮新确认）

| Field | Endpoint | Raw path | Meaning | Window | Unit | Chain coverage | Null semantics | Example | Kind | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| volume_{w} | token info | `price.volume_1m/5m/1h/6h/24h` | 窗口成交额 | 滚动 1m–24h | USD（字符串） | SOL ETH（RH / BASE NOT TESTED） | 无窗口内成交时为 `"0"`（ETH 1m） | `"31532848.18052814"` | DIRECT | READY |
| buy_volume_{w} / sell_volume_{w} | token info | `price.buy_volume_*` / `price.sell_volume_*` | 买入 / 卖出成交额 | 同上 | USD | SOL ETH | `"0"` = 无成交 | `"15326734.89"` | DIRECT | READY（相加 = volume） |
| swaps_{w} / buys_{w} / sells_{w} | token info | `price.swaps_*` / `price.buys_*` / `price.sells_*` | 交易笔数 / 买入笔数 / 卖出笔数 | 同上 | 笔 | SOL ETH | 0 = 无交易 | `210234` | DIRECT | READY（swaps = buys + sells） |
| price_{w} | token info | `price.price_1m/5m/1h/6h/24h` | 窗口**起点**的价格（文档） | 滚动 | USD | SOL ETH | — | `"0.0026972093"` | DIRECT | VERIFIED_BY_DOCS；与 Trending pc 的一致性未测 |
| holder_count | token info | `holder_count`、`stat.holder_count` | 当前持有地址数 | 快照 | 地址数 | SOL ETH | — | `8897` | DIRECT | READY（快照） |
| smart_wallets | token info | `wallet_tags_stat.smart_wallets` | 当前持有的 smart 钱包数（文档） | 快照 | 钱包数 | SOL ETH | — | `170` | DIRECT | READY（= Trending `smart_degen_count`）；"持有"只有文档证据 |
| renowned / whale / sniper / rat_trader / creator / top_wallets | token info | `wallet_tags_stat.*` | 各标签钱包数 | 快照 | 钱包数 | SOL ETH | — | `7` | DIRECT | renowned / sniper READY（与 Trending 相等）；whale 阈值 UNKNOWN |
| fresh_wallets / bundler_wallets | token info | `wallet_tags_stat.fresh_wallets` / `bundler_wallets` | 标签钱包数 | 快照 | 钱包数 | SOL ETH | — | `1000` | DIRECT | **NEEDS_CONFIRMATION**（疑似上限 1000） |
| fresh_wallet_rate | token info | `stat.fresh_wallet_rate` | fresh 钱包比例 | 快照 | 比例 | SOL ETH | ETH 为 `"0"` 而 fresh_wallets = 992 | `"0.1482"` | DIRECT | **NEEDS_CONFIRMATION** |
| bot_degen_count | token info | `stat.bot_degen_count` | 机器人钱包数 | 快照 | 钱包数 | SOL ETH（ETH 为 0） | — | `1123` | DIRECT | 与 Trending 一致；EVM 上的 0 含义不明 |
| liquidity / pool.liquidity | token info | `liquidity`、`pool.liquidity` | 流动性（文档："最大池"） | 快照 | USD | SOL ETH | — | `156995.05` | DIRECT | **NEEDS_CONFIRMATION**（跨 endpoint 口径，见字段字典 §5） |
| signal_count / degen_call_count | token info | `stat.signal_count` / `stat.degen_call_count` | 信号次数 / 喊单次数 | UNKNOWN | 次 | SOL ETH（两者都是 0） | — | `0` | DIRECT | UNKNOWN |
| start_holding_at / last_active_timestamp | token traders / holders | `list[].start_holding_at` 等 | 钱包首次获得 / 最近活跃时间 | 事件 | Unix 秒 | SOL | — | `1790911442` | DIRECT（钱包级） | 只覆盖 top 100 → token 级 NOT_AVAILABLE |
| buy_tx_count_cur / sell_tx_count_cur | token traders / holders | `list[].buy_tx_count_cur` | 钱包的买 / 卖笔数 | "cur" 的时间段 UNKNOWN | 笔 | SOL | 最大持有者为 0 | `0` | DIRECT（钱包级） | UNKNOWN（窗口） |
| list 长度 | token traders / holders | `list` | — | — | — | SOL | — | 100 | — | 上限 100，没有总数 |
| smartmoney trade | track smartmoney | `list[].{maker, side, base_address, amount_usd, timestamp, is_open_or_close}` | smart 钱包单笔交易 | 全链最新 100 条（约 1.8 分钟） | USD / Unix 秒 | SOL | — | `amount_usd 51.80` | DIRECT（事件） | 覆盖不足 → 每日聚合 NOT_AVAILABLE |

## DAILY TOKEN INTELLIGENCE CAPABILITY MAP

| 指标 | GMGN 直接提供 | 可否自己计算 | 数据源 | 推荐方案 | V1 |
|---|---|---|---|---|---|
| 每日成交量（USD） | **是**：日 K 自然日约 100 天；info 有滚动 24h | — | `market kline 1d` · `list[].volume`；`token info` · `price.volume_24h` | 日 K 作为正式日序列；info 24h 用于盘中 | **V1** |
| 每日交易次数 | 只有滚动 24h | **可以**：UTC 00:00 后快照 `swaps_24h` | `token info` · `price.swaps_24h`（Trending `swaps` 也行，但只覆盖在榜 token） | 日切快照，存 `observed_at` | **V1** |
| 每日买入 / 卖出笔数 | 只有滚动 24h | 同上 | `price.buys_24h` / `price.sells_24h` | 日切快照 | **V1** |
| 每日活跃钱包 | **否** | **否** | — | **NOT_AVAILABLE FROM GMGN** → 需要链上成交明细（§11） | 否 |
| 每日新增钱包 | **否** | **否** | — | **NOT_AVAILABLE FROM GMGN** → 需要完整成交历史 | 否 |
| 每日买家数 | **否**（buys 是笔数） | **否** | — | **NOT_AVAILABLE FROM GMGN** | 否 |
| 每日卖家数 | **否** | **否** | — | **NOT_AVAILABLE FROM GMGN** | 否 |
| 每日新增买家 | **否** | **否** | — | **NOT_AVAILABLE FROM GMGN** | 否 |
| Holder 总数 | **是**（当前快照） | — | `token info` · `holder_count`；T / H / Tr | 日切快照 | **V1** |
| Holder 日增量 | **否** | **可以，净变化**：快照差分 | 同上 | `holders_d − holders_d−1`，命名为 `holder_net_change`（不是 new_holders） | **V1**（从部署日开始积累） |
| Smart Money 数 | **是**（当前持有数快照） | — | `wallet_tags_stat.smart_wallets` = Trending `smart_degen_count` | 日切快照 | **V1** |
| Smart Money 新增 | **否** | **只有净变化**；真正的"新进入数" NOT_AVAILABLE | 快照差分 | 命名为 `smart_wallets_net_change` | **V1**（净变化） |
| Buy Volume | **是**（滚动窗口） | — | `price.buy_volume_{1h,6h,24h}` | 日切快照 + 盘中窗口 | **V1** |
| Sell Volume | **是**（滚动窗口） | — | `price.sell_volume_{w}` | 同上 | **V1** |
| Net Buy | 否 | **可以**：buy − sell（raw 验证相加精确） | 同上 | `net_buy_usd`、`net_buy_ratio` | **V1** |
| 成交加速度（今天 vs 过去） | 否 | **可以**：日 K 量比；info 的 1h / 6h / 24h 比值 | 日 K + info | `vol_ratio_7d`、`vol_1h×24 / vol_24h`、`swaps_1h×24 / swaps_24h` | **V1** |
| 钱包增长 / 新钱包比例 / 每钱包成交额 | 否 | 否 | — | **NOT_AVAILABLE FROM GMGN** | 否 |

## V1 推荐字段

目标问题："一个代币过去 7 天，每一天有多少成交量、多少参与钱包、多少新增钱包、多少买家 / 卖家，这些指标是不是在加速？"

GMGN 能回答其中的**资金与交易活跃度部分**；**钱包部分无法回答**。V1 只采集以下内容：

| # | 字段 | 来源 | 频率 | 用途 |
|---|---|---|---|---|
| 1 | `list[].volume`、`close`、`time` | `market kline 1d`（已采集） | 现有节奏 | 自然日成交额序列、量比、加速度 |
| 2 | `price.volume_24h`、`price.buy_volume_24h`、`price.sell_volume_24h` | `token info` | 每日 UTC 00:00 后一次 + 候选池按需 | 每日买入 / 卖出 / 净买入 |
| 3 | `price.swaps_24h`、`price.buys_24h`、`price.sells_24h` | `token info` | 同上 | 每日交易次数、买卖笔数 |
| 4 | `price.volume_1h`、`price.volume_6h`、`price.swaps_1h`、`price.swaps_6h` | `token info`（同一次调用） | 同上 | 盘中加速度（1h、6h 相对 24h） |
| 5 | `holder_count` | `token info`（同一次调用） | 同上 | holder 净变化序列 |
| 6 | `wallet_tags_stat.smart_wallets`、`renowned_wallets`、`whale_wallets` | `token info`（同一次调用） | 同上 | smart / KOL / whale 净变化 |
| 7 | `observed_at`（采集时间） | 本地 | 每次 | 标明滚动 24h 的实际终点 |

一次 `token info` 调用就能覆盖 #2–#6。V1 新增成本 = 每个目标 token 每天 1 次调用（另加可选的盘中调用），需要先确定覆盖哪些 token 并规划配额。

**不进 V1**：fresh_wallets / bundler_wallets / fresh_wallet_rate（疑似上限且自相矛盾）、traders / holders 列表（top 100 样本）、track smartmoney（覆盖约 2 分钟）、Trenches `net_buy_24h`、跨 endpoint 的 liquidity。

**V1 能回答**："过去 7 天每天成交额多少（日 K）；从开始采集起每天多少笔交易、买卖笔数、净买入、holder 净变化、smart money 净变化；今天是否在加速。"

**V1 不能回答**："多少个钱包、多少个新钱包、多少个买家 / 卖家"。这部分 **NOT_AVAILABLE FROM GMGN**。

## 11. 缺口与下一步数据源

| 缺口 | 需要的数据 | 候选来源（**均未验证**） |
|---|---|---|
| 每日活跃钱包、买家数、卖家数 | 某个 token 的完整 swap 明细（按 maker 去重） | 链上索引服务（如 Bitquery、Dune、Helius / 各链 RPC + 自建 indexer）；部分 DEX 数据商提供按窗口的 unique buyers / sellers（例如 GeckoTerminal 的 pool transactions）。本仓库 `rhv2` 管线已经从 GeckoTerminal 拉取 buyer 相关字段（Phase 3 记录），可以优先评估这条路，但其口径需要单独验证 |
| 每日新增钱包 / 首次买家 | 完整成交历史 + 每个钱包对该 token 的首次交易时间 | 只能自建 indexer，或用提供"first buy"维度的链上分析服务 |
| 新增 holder | 持有者集合的逐日差集 | 链上 holder 快照（Blockscout / Helius 等）。rhv2 已有 Blockscout holder 快照（独立管线） |
| 新增 smart money / smart money 买入额 | 标签钱包的完整交易流 | GMGN 交易流覆盖不足；需要更高配额，或者链上数据 + 自建 smart 钱包名单 |

## 12. 未决项（NEEDS_CONFIRMATION / NOT TESTED）

- `token info` 在 ROBINHOOD / BASE 上**未测试**。字段结构预计一致，但不能当作已验证。
- `wallet_tags_stat` 的 1000 上限；`fresh_wallet_rate` 的分母与 ETH 上的矛盾。
- `price.price_{w}` 是"窗口起点价"只有文档证据。
- traders / holders 的 `*_cur` 指哪个时间段。
- 日切快照的配额：目标 token 数量 × 1 次 / 天，需要与生产 collector 的限频共同规划。
