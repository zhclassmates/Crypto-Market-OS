# GMGN → Market Intelligence Capability Map

> 目的：搞清楚 **GMGN 有什么 → 能干什么 → 当前用了什么 → 还缺什么 → 最值得接什么**。
> 本文不修代码、不进入 Phase 4 production repair、不重新请求 GMGN。
>
> **阅读顺序：** Part I（§0–§18）是按 endpoint/主题整理的证据层；
> **Part II（§19–§25）是按 5 个产品模块倒推的验收视图，开发请直接看 Part II**，
> 尤其是 §24 字段接入表与 §25 V1 最小字段集合。
>
> 标记约定：**[事实]** = Phase 2 矩阵 / Phase 3 映射 / 只读查询直接记录；
> **[推导]** = 由事实计算或推理得出；**[建议]** = 产品/工程建议。

## 0. 证据来源与边界

| 证据 | 内容 | 状态 |
|---|---|---|
| Phase 1 | 22 个 `endpoint × chain` 真实 `--raw` 请求（gmgn-cli 1.6.6，2026-10-02 23:43Z 起） | 结果见 `endpoint-results.md` |
| Phase 2 | 6 个 endpoint 的字段矩阵 `field-matrix/*.md` + `phase2-field-matrix-summary.md` | **本文唯一的 raw 字段证据** |
| Phase 3 | `phase3-production-mapping.md`：source→parser→DB→API→UI 映射 | 生产使用情况依据 |
| 本轮只读查询 | 生产 `market.sqlite` 以 `mode=ro` + `query_only` 打开，只看表结构与历史深度 | 无写入 |

**证据限制（必须先读）：**

1. `/tmp/gmgn-audit/raw/` 原始 JSON 已不在当前环境（Phase 3 已记录为 P3-A01）。Phase 2
   只对"重点字段"记录了非空率/零值率；对其余字段只记录了 **key 存在率与 JSON 类型**。
   这些字段在下表中标为 `值分布未记录`，**不推断其非空率**。
2. 样本是单次快照：Trending 400 行、Hot 259 行、Trenches 633 行、Signal 100 行
   （仅 SOL/ROBINHOOD）、Kline 120 根（4 个 token）、Security 4 个对象（每链 1 个）。
   单次请求无法证明重复请求的稳定性、缓存行为或字段口径随时间不变。
3. `manifest.json` 记录 `market search`、`token info`、`token pool`、`token holders`、
   `token traders`、`track endpoints` 在 Phase 1 中**只确认了 CLI 存在、生产未使用，
   没有 raw 请求**。它们的字段在本文一律为 `UNVERIFIED`，不列入能力结论。
4. 金额单位：除 Signal `data.usd_market_cap` 外，**所有 price/volume/liquidity/market_cap
   都没有在 payload 里编码币种**。下文所有跨 token 的金额比较都带此前提。

时间属性标签（按要求固定使用）：

`实时值` · `24h rolling` · `当前快照` · `日K` · `累计值` · `排名` · `静态元数据` · `安全快照` · `事件时间` · `UNKNOWN`

---

## 1. Executive Summary

**一句话：** GMGN 足够支撑"价格/日K 动量 + 24h 活跃度快照 + 榜单注意力 + 合约风险过滤"，
但**不提供任何钱包维度（unique traders / makers / buyers / sellers / new holders）**，
也**不提供除日K OHLCV 之外的任何历史序列**。所有"变化率/加速度/放量"类信号，
除日K价格和日K成交量之外，都必须靠我们自己按固定频率历史化快照。

关键结论：

| # | 结论 | 证据强度 |
|---|---|---|
| 1 | **日K 是唯一的 GMGN 原生历史源**：OHLC + `volume` + `amount`，UTC 00:00 开盘，毫秒时间戳，无 finalized 标记。 | HIGH |
| 2 | **24h 活跃度三件套** `swaps / buys / sells`（Trending、Hot）与 `swaps_24h / buys_24h / sells_24h`（Trenches）真实存在且非空；`swaps = buys + sells` 在 1,292/1,292 行成立。它们是**交易笔数**，不是钱包数。 | HIGH |
| 3 | **短周期价格变化**直接存在：Trending/Hot 有 `price_change_percent`、`price_change_percent1h`、`price_change_percent5m`、`price_change_percent1m`。**没有 6h**。 | key 存在 HIGH；口径 MEDIUM（1h/5m/1m 由字段名表达，主字段窗口未在 payload 编码） |
| 4 | **短周期成交量（1h/6h）实际不可用**：只有 Signal `data.volume_{1m,1h,6h,24h}` 有这些 key，且 100/100 行全为 0。 | HIGH |
| 5 | **注意力信号很丰富但大多未利用**：`rank`（已入库且有历史）、`hot_level`、`visiting_count`、`square_mentions`、DexScreener 付费/趋势标记（`dexscr_*` + `_ts`）、Signal 事件（`signal_type`、`trigger_at`、`signal_times`）、Trench 阶段与 `progress`。 | key 存在 HIGH；语义多为 UNKNOWN |
| 6 | **"聪明钱/筹码结构"计数**存在：`smart_degen_count`、`renowned_count`、`sniper_count`、`bot_degen_count`、`top_10_holder_rate`、`dev_team_hold_rate`、`bundler_rate`、`rat_trader_amount_rate` 等。这是对爆发币发现最有价值的一组未利用字段。 | key 存在 HIGH；值分布未记录 |
| 7 | **FDV / 流通量不存在**；只有 `total_supply`（Trending/Hot/Trenches/Signal）。FDV 只能自己算 `price × total_supply`，且单位未编码。 | HIGH |
| 8 | **安全过滤**可覆盖 honeypot、mint/freeze 放弃、owner 放弃、开源、黑名单、税、LP 锁、Top10 集中度、特权标签；**没有** mutable metadata 字段，**没有**直接的 rug 概率（Trending/Hot/Trenches 有 `rug_ratio`，语义 UNKNOWN）。 | MEDIUM（仅 4 个样本） |
| 9 | **生产系统只用了很少一部分**：UI 只显示 price、pc_24h、volume_24h、liquidity、market_cap、holders + 日K 衍生指标；`smart_degen_count` 等 6 个字段已入库但 API 不读；`buys/sells`、短周期涨跌、`hot_level`、`total_supply`、`history_highest_market_cap` 等被丢弃。 | HIGH（Phase 3 + HEAD 代码） |
| 10 | **已存在可直接利用的本地历史**：`token_candle` 日K（2026-06-24 起，1,623 token，中位深度仅 3 根）、`hourly_price`（2026-08-30 起，13,074 token）、`discovery_event` 每 5 分钟桶的 rank/price/liquidity/market_cap + holder_count 元数据（2026-10-02 04:47Z 起）。 | HIGH（只读查询） |

**最值得接的前五项（详见 §18）：**
1. 把 `buys/sells/swaps` + `price_change_percent1h/5m` 写进 5 分钟事件历史 → 活跃度动量与买卖失衡。
2. 用已有的 `discovery_event.rank` 做 **rank velocity / 新进榜** 注意力信号（零新增采集）。
3. 用已有日K做 **成交量动量**（今日量 / 7 日均量、连续放量天数）——同 token 比率与单位无关。
4. 接入 `smart_degen_count / renowned_count / sniper_count / top_10_holder_rate` 的历史快照 → "聪明钱进场"信号。
5. 安全硬过滤：`is_honeypot`、`renounced_mint/freeze`、`buy_tax/sell_tax`、`is_wash_trading`。

---

## 2. Endpoint Overview

| Endpoint | 生产命令 | 链 | 样本 | 结构 | 主要价值 | 主要限制 |
|---|---|---|---|---|---|---|
| market trending | `market trending --interval 24h --limit 100` | SOL ROBINHOOD BASE ETH | 400 行，95 key 全行全链一致 | `data.rank[]` | 价格+多周期涨跌、24h 量与笔数、持币数、聪明钱计数、注意力、风险标记 | 窗口/币种不在 payload 里；无历史 |
| market hot-searches | `market hot-searches --limit 100` | 同上 | 259 行（SOL 95/RH 100/BASE 32/ETH 32），95 key 一致 | `[0].tokens[]` + `interval="24h"` + `version` | 与 Trending 同 schema，且**显式**标注 24h；"被搜索"本身就是注意力 | `version` 语义不明，不能当时间 |
| market trenches | `market trenches --type new_creation near_completion completed --limit 30` | 同上 | 633 行，132 key 并集、仅 65 key 全行存在 | 三个 bucket 数组 | 新币生命周期（创建→接近毕业→毕业）、`progress`、显式 `*_24h` 量/笔数、社交与创建者画像 | 链/分类间 schema 漂移大；0 值哨兵多 |
| market signal | `market signal` | SOL ROBINHOOD（BASE/ETH 生产标记 unsupported） | 100 行；12 根 key + 155 `data` key + 3 `cur_data` key | 事件数组 | 事件型注意力（类型、触发时间、触发市值、触发次数、ATH）；`cur_data` 当前持币/流动性/Top10 | 所有 1m/1h/6h/24h 活跃度字段 100% 为 0；`signal_type` 含义未编码 |
| market kline | `market kline --resolution 1d --from now-100d` | 4 链 | 120 根（SOL 1 / RH 18 / BASE 1 / ETH 100） | `list[]`，8 key | **唯一原生历史**：日 OHLC、volume、amount | 无笔数/钱包/持币/流动性/市值；无 finalized；`amount` 语义不明；只验证了 `1d` |
| token security | `token security --address` | 4 链 | 4 个对象，28 key 一致 + `lock_summary` | 平铺对象 | 合约风险、税、锁仓、特权、Top10 | 只有 4 个样本；同义字段类型不一致（bool / number / string） |
| market search / token info / token pool / token holders / token traders / track | — | — | **无 raw 证据** | — | 可能补齐钱包/池子维度 | `UNVERIFIED`，不纳入结论（见 §12） |

---

## 3. Full Field Matrix

列定义：

- **样本非空率**：Phase 2 记录的"有值行 / 总行"及 0 值数。`key 100%` = key 在全部行存在，但值分布未被记录。
- **各链一致性**：`4 链一致` = 四链 key 集合相同；其余写明缺失链。
- **能否历史化**：`GMGN 自带` = GMGN 本身返回历史；`已历史化` = 生产已有本地历史表；`可历史化` = 需要我们按频率存快照；`不需要` = 静态或低价值。
- **生产现状**（HEAD 代码，不含工作区里未部署的 Phase 4 修改）：`UI` 展示 · `API` 返回但未展示 · `DB` 入库但 API 不读 · `META` 只进 `discovery_event.metadata_json` · `DROP` 读到但丢弃/未读。

### 3.1 Trending / Hot-searches（共用 95-key schema）

两者 schema 完全一致，差异仅在：Hot 外层显式 `interval="24h"`、有 `version`；Trending 的 24h 是**请求参数**，payload 本身不标注。

#### 价格与涨跌

| 字段 | Endpoint | 实际类型 | 样本非空率 | 各链一致性 | 时间属性 | 能否历史化 | 可用于什么 | 生产现状 |
|---|---|---|---|---|---|---|---|---|
| `price` | T / H | number | 400/400、259/259，无 null | 4 链一致 | 当前快照 | 已历史化（`hourly_price` 小时桶、`discovery_event.price` 5 分钟桶） | 当前价、日内动量、与日K 收盘对照 | UI |
| `price_change_percent` | T / H | number | key 100% | 4 链一致 | UNKNOWN（T：请求 `--interval 24h`；H：外层 interval=24h；payload 本身不标注） | 可历史化 | 24h 涨跌排序、过滤 | UI（作 pc_24h） |
| `price_change_percent1h` | T / H | number | key 100% | 4 链一致 | 字段名表示 1h；payload 未定义滚动方式 → UNKNOWN（倾向 1h rolling） | 可历史化 | **加速度**：1h 涨幅 vs 24h 涨幅；启动检测 | DROP |
| `price_change_percent5m` | T / H | number | key 100% | 4 链一致 | 同上（5m） | 可历史化（需 ≤5 分钟采样才有意义） | 突发拉升告警 | DROP |
| `price_change_percent1m` | T / H | number | key 100% | 4 链一致 | 同上（1m） | 不建议历史化（噪声大、采样周期 5 分钟） | 实时告警确认 | DROP |
| `history_highest_market_cap` | T / H | number | key 100% | 4 链一致 | 累计值（历史最高市值） | 可历史化（单调值，存最新即可） | **距 ATH 距离**、新高突破 | DROP |

#### 成交量与交易笔数

| 字段 | Endpoint | 实际类型 | 样本非空率 | 各链一致性 | 时间属性 | 能否历史化 | 可用于什么 | 生产现状 |
|---|---|---|---|---|---|---|---|---|
| `volume` | T / H | number | 400/400、259/259 | 4 链一致 | 24h rolling（H 显式；T 由请求参数决定） | 可历史化（当前**无历史**：事件元数据不存 volume） | 24h 量排序、Vol/Liq、Vol/MC | UI（`$` 格式化，单位未经证实） |
| `swaps` | T / H | number | 400/400、259/259 | 4 链一致 | 24h rolling | 可历史化 | 活跃度、平均单笔金额 `volume/swaps` | DB（`token_snapshot.swaps`，API 不读） |
| `buys` | T / H | number | 400/400、259/259 | 4 链一致 | 24h rolling | 可历史化 | **买卖失衡** `buys/(buys+sells)` | DROP |
| `sells` | T / H | number | 400/400、259/259 | 4 链一致 | 24h rolling | 可历史化 | 同上；抛压 | DROP |

> `swaps = buys + sells` 在 400/400（T）与 259/259（H）成立。它们是**交易笔数**，不是钱包数。

#### 流动性 / 市值 / 供应

| 字段 | Endpoint | 实际类型 | 样本非空率 | 各链一致性 | 时间属性 | 能否历史化 | 可用于什么 | 生产现状 |
|---|---|---|---|---|---|---|---|---|
| `liquidity` | T / H | number | 400/400、259/259 | 4 链一致 | 当前快照 | 已历史化（`discovery_event.liquidity` 5 分钟桶，仅在上榜时） | 流动性门槛、Vol/Liq、流动性增长 | UI |
| `initial_liquidity` | T / H | number | key 100% | 4 链一致 | 静态元数据（开池时） | 不需要（存一次） | **流动性增长倍数** `liquidity/initial_liquidity` | DROP |
| `market_cap` | T / H | number | 400/400、259/259 | 4 链一致 | 当前快照 | 已历史化（`discovery_event.market_cap`） | 市值分层、小市值突破 | UI（`$`） |
| `total_supply` | T / H | number | key 100% | 4 链一致 | 静态元数据（可能因 burn/mint 变化） | 存最新 + 变化检测 | 自算 FDV、核对 market_cap/price | DROP |
| `burn_ratio` / `burn_status` | T / H | number / string | key 100% | 4 链一致 | 当前快照 | 存最新 | 供应风险、详情页 | DROP |
| `lock_percent` | T / H | number | key 100% | 4 链一致 | 当前快照 | 存最新 | LP 锁定比例，rug 风险 | DROP |

#### 注意力 / 热度

| 字段 | Endpoint | 实际类型 | 样本非空率 | 各链一致性 | 时间属性 | 能否历史化 | 可用于什么 | 生产现状 |
|---|---|---|---|---|---|---|---|---|
| `rank` | T / H | number | key 100% | 4 链一致 | 排名（本次请求内） | **已历史化**（`discovery_event.rank`，T 42,467 行 / H 30,042 行，5 分钟桶） | **新进榜、rank velocity、在榜时长** | DB/META（API/UI 不读） |
| `hot_level` | T / H | number | key 100% | 4 链一致 | UNKNOWN | 可历史化 | 热度分层（语义需验证） | DROP |
| `visiting_count` | T / H | number | key 100% | 4 链一致 | UNKNOWN（可能是累计访问） | 可历史化（差分才有意义） | **页面访问增速 = 注意力领先价格** | DROP |
| `square_mentions` | T / H | number | key 100% | 4 链一致 | UNKNOWN | 可历史化 | 社区提及增速 | DROP |
| `dexscr_ad` / `dexscr_ad_ts` | T / H | number | key 100% | 4 链一致 | 事件时间（_ts） | 存事件 | 项目方付费推广 → 注意力事件；也是"付费拉盘"风险提示 | DROP |
| `dexscr_boost_fee` / `dexscr_boost_ts` | T / H | number | key 100% | 4 链一致 | 事件时间 | 存事件 | DexScreener boost 金额与时间 | DROP |
| `dexscr_trending_bar` / `_ts` | T / H | number | key 100% | 4 链一致 | 事件时间 | 存事件 | 进入 DexScreener 趋势条 | DROP |
| `dexscr_update_link` / `_ts` | T / H | number | key 100% | 4 链一致 | 事件时间 | 存事件 | 项目方更新信息（活跃项目方） | DROP |
| `is_show_alert` | T / H | boolean | key 100% | 4 链一致 | UNKNOWN | 不需要 | GMGN 告警标记（语义未知） | DROP |
| `is_token_live` / `start_live_timestamp` / `end_live_timestamp` | T / H | bool / number | key 100%；start 0 值 396/400（T）、250/259（H）；end 0 值 397/400、252/259 | 4 链一致 | 事件时间（直播） | 存事件 | 直播事件（极稀疏） | DROP |
| `twitter_username` / `website` / `telegram` | T / H | string | key 100% | 4 链一致 | 静态元数据 | 不需要 | 详情页、"有无社交"过滤 | DROP |
| `twitter_rename_count` / `twitter_change_flag` / `twitter_create_token_count` / `twitter_del_post_token_count` | T / H | number | key 100% | 4 链一致 | 累计值 | 存最新 | **社交可信度/骗局风险**（改名次数、同号发币次数、删帖） | DROP |
| `twitter_dup` / `telegram_dup` / `website_dup` / `image_dup` | T / H | number / string | key 100% | 4 链一致 | 当前快照 | 存最新 | **仿盘/复制盘过滤** | DROP |

#### 聪明钱与筹码结构

| 字段 | Endpoint | 实际类型 | 样本非空率 | 各链一致性 | 时间属性 | 能否历史化 | 可用于什么 | 生产现状 |
|---|---|---|---|---|---|---|---|---|
| `holder_count` | T / H | number | 400/400、259/259 | 4 链一致 | 当前快照 | 已部分历史化（`discovery_event.metadata_json.holder_count`，仅在上榜时，无固定节奏） | 持币增长（需固定频率）、门槛过滤 | UI |
| `smart_degen_count` | T / H | number | key 100% | 4 链一致 | 当前快照（UNKNOWN 窗口） | 可历史化 | **聪明钱进场计数与增速** | DB（API 不读） |
| `renowned_count` | T / H | number | key 100% | 4 链一致 | 当前快照 | 可历史化 | KOL/知名钱包参与 | DB（API 不读） |
| `sniper_count` | T / H | number | key 100% | 4 链一致 | 当前快照 | 可历史化 | 狙击手比例（负面） | DB（API 不读） |
| `top70_sniper_hold_rate` | T / H | number | key 100% | 4 链一致 | 当前快照 | 可历史化 | 狙击手仍持仓比例（抛压风险） | DROP |
| `bot_degen_count` / `bot_degen_rate` | T / H | number | key 100% | 4 链一致 | 当前快照 | 可历史化 | 机器人参与度（量的质量） | DROP |
| `bundler_rate` | T / H | number | key 100% | 4 链一致 | 当前快照 | 可历史化 | 捆绑买入（控盘）风险 | DB（API 不读） |
| `rat_trader_amount_rate` | T / H | number | key 100% | 4 链一致 | 当前快照 | 可历史化 | 老鼠仓交易占比 | DB（API 不读） |
| `top_10_holder_rate` | T / H | number | key 100% | 4 链一致 | 当前快照 | 可历史化 | 集中度过滤、筹码分散化趋势 | DB（API 不读） |
| `dev_team_hold_rate` | T / H | number | key 100% | 4 链一致 | 当前快照 | 可历史化 | 开发者持仓（砸盘风险） | DROP |
| `bluechip_owner_percentage` | T / H | number | key 100% | 4 链一致 | 当前快照 | 可历史化 | 蓝筹钱包持有比例（质量信号） | DROP |
| `entrapment_ratio` | T / H | number | key 100% | 4 链一致 | UNKNOWN | 存最新 | 语义未知，仅详情页 | DROP |
| `creator` / `creator_token_status` / `creator_close` | T / H | string / bool | key 100% | 4 链一致 | 静态元数据 / 当前快照 | 存最新 | 创建者已清仓等风险 | DROP |

#### 风险与安全（发现源内嵌）

| 字段 | Endpoint | 实际类型 | 样本非空率 | 各链一致性 | 时间属性 | 能否历史化 | 可用于什么 | 生产现状 |
|---|---|---|---|---|---|---|---|---|
| `is_honeypot` / `is_open_source` / `is_renounced` | T / H | **number**（Security 中是 boolean/null） | key 100% | 4 链一致 | 安全快照 | 存最新 | 无需额外请求的**预过滤** | DROP |
| `renounced_mint` / `renounced_freeze_account` | T / H | nullable number | null 300/400（T）、164/259（H） | 4 链一致 | 安全快照 | 存最新 | mint/freeze 风险（主要适用 SOL） | DROP |
| `buy_tax` / `sell_tax` | T / H | string | key 100% | 4 链一致 | 安全快照 | 存最新 | 高税过滤 | DROP |
| `rug_ratio` | T / H | number | key 100% | 4 链一致 | UNKNOWN | 存最新 | rug 风险（口径未知，只可做弱过滤） | DROP |
| `is_wash_trading` | T / H | boolean | key 100% | 4 链一致 | UNKNOWN | 存最新 | **刷量过滤**——放量信号的必备反证 | DROP |
| `dev_token_burn_amount` / `dev_token_burn_ratio` | T / H | number | key 100% | 4 链一致 | 当前快照 | 存最新 | 详情页 | DROP |
| `gas_fee` | T / H | number | key 100% | 4 链一致 | UNKNOWN | 不需要 | 低价值 | DROP |

#### 身份与静态元数据

| 字段 | Endpoint | 实际类型 | 样本非空率 | 各链一致性 | 时间属性 | 能否历史化 | 可用于什么 | 生产现状 |
|---|---|---|---|---|---|---|---|---|
| `address` / `chain` / `symbol` / `name` / `logo` | T / H | string | 全行 | 4 链一致 | 静态元数据 | 不需要 | 身份 | DB / UI |
| `creation_timestamp` | T / H | number（Unix 秒） | 全行 | 4 链一致 | 事件时间 | 不需要 | **币龄**、新币过滤、K线创建日过滤 | DB（registry） |
| `open_timestamp` | T / H | number | 0 值 140/400、55/259 | 4 链一致 | 事件时间 | 不需要 | 开盘/迁移时间 | DROP |
| `launchpad` / `launchpad_platform` / `launchpad_status` / `exchange` / `pool_type` / `pool_type_str` / `migrated_pool_exchange` / `launch_quote_address` | T / H | string / number | key 100% | 4 链一致 | 静态元数据 | 不需要 | 平台分组、毕业状态 | META（仅 `launchpad_platform`） |
| `is_og` / `cto_flag` | T / H | bool / number | key 100% | 4 链一致 | 静态元数据 | 不需要 | CTO（社区接管）币标记 | DROP |
| `trans_name(_zhcn)` / `trans_symbol(_zhcn)` / `tcid` / `id` | T / H | string / number | key 100% | 4 链一致 | 静态元数据 | 不需要 | 本地化显示 | DROP |

### 3.2 Trenches（新币生命周期，schema 漂移）

只列与 Trending/Hot **不同或独有**的字段；同名字段语义按 §3.1，但 trench 的 0 值哨兵更多。

| 字段 | Endpoint | 实际类型 | 样本非空率 | 各链一致性 | 时间属性 | 能否历史化 | 可用于什么 | 生产现状 |
|---|---|---|---|---|---|---|---|---|
| bucket（`new_creation`/`near_completion`/`completed`） | Tr | 数组名 | 633 行（ETH 仅 60/28/5） | 4 链 | 当前快照（阶段） | **已历史化**（`discovery_event.source_variant`） | **生命周期跃迁**：创建→接近毕业→毕业 | DB/META |
| `price` | Tr | number | 633/633，0 值 115 | 4 链 | 当前快照 | 已历史化（事件） | 同上 | DB |
| `volume_24h` | Tr | number | 633/633，0 值 140 | 4 链 | 24h rolling | 可历史化 | 新币量能 | **DROP（IMPLEMENTATION GAP：写入器读 `volume` 不读 `volume_24h`）** |
| `swaps_24h` / `buys_24h` / `sells_24h` | Tr | number | 633/633；0 值 130 / 155 / 252 | 4 链 | 24h rolling | 可历史化 | 新币活跃度、买卖失衡 | **DROP（同上 GAP）** |
| `buy_volume_24h` / `sell_volume_24h` | Tr | number | 116/633；0 值 53/116、109/116 | 仅 RH/BASE/ETH（SOL 无） | 24h rolling（公式不可验证：与 volume_24h 吻合 9/116） | 不建议 | 不可靠，仅详情页参考 | DROP |
| `net_buy_24h` | Tr | number | 569/633 | 4 链 | 24h rolling，单位/公式 UNKNOWN | 不建议 | 不可靠 | DROP |
| `holder_count` | Tr | number | 633/633，0 值 21 | 4 链 | 当前快照 | 已部分历史化（META） | 新币持币增长 | DB/META |
| `liquidity` | Tr | number | 633/633，0 值 209 | 4 链 | 当前快照 | 已历史化（事件） | 门槛 | DB |
| `market_cap` | Tr | number | 633/633，0 值 115 | 4 链 | 当前快照 | 已历史化（事件） | 分层 | DB |
| `progress` | Tr | number | key 存在率未记录 | 未记录 | 当前快照（bonding curve 进度，语义 UNKNOWN） | 可历史化 | **毕业速度** = Δprogress/Δt | DROP |
| `complete_timestamp` / `complete_cost_time` | Tr | number | complete_ts 0 值 448/633 | 4 链 | 事件时间 / 累计值 | 不需要 | 毕业用时（快毕业 = 强需求） | DROP |
| `created_timestamp` | Tr | number | 633/633 | 4 链 | 事件时间 | 不需要 | 币龄 | DB |
| `open_timestamp` | Tr | number | 0 值 448/633 | 4 链 | 事件时间 | 不需要 | 开盘时间 | DROP |
| `fresh_wallet_rate` | Tr | number | 633/633，0 值 473 | 4 链 | UNKNOWN（比例，分子/分母/窗口未编码） | 可历史化（谨慎） | 新钱包比例——**不是钱包数** | DROP |
| `new_wallet_volume` | Tr | number | 143/633，**全部为 0** | SOL/RH/BASE（ETH 无） | UNKNOWN | 不需要 | 不可用 | DROP |
| `x_user_follower` / `x_user_following` | Tr | number | 存在率未记录 | 未记录 | 当前快照 | 可历史化 | **推特粉丝增速**（注意力） | DROP |
| `tg_call_count` / `callout_count` | Tr | number | 存在率未记录 | 未记录 | 累计值（推测，UNKNOWN） | 可历史化 | **喊单次数增速**（注意力） | DROP |
| `tweet_publish_time` / `twitter_is_tweet` / `has_at_least_one_social` | Tr | number / bool | 存在率未记录；`has_at_least_one_social` 仅 SOL/RH/BASE | 部分链 | 事件时间 / 静态 | 不需要 | 有无社交过滤 | DROP |
| `creator_created_count` / `creator_created_open_count` / `creator_created_open_ratio` / `creator_balance_rate` | Tr | number | 存在率未记录 | 未记录 | 当前快照 | 存最新 | **连环发币者过滤**、创建者持仓 | DROP |
| `suspected_insider_hold_rate` / `private_vault_hold_rate` | Tr | number | 存在率未记录 | 未记录 | 当前快照 | 可历史化 | 内部人持仓风险 | DROP |
| `bundler_mhr` / `bundler_trader_amount_rate` | Tr | number | 存在率未记录 | 未记录 | UNKNOWN | 存最新 | 捆绑交易风险 | DROP |
| `fund_from` / `fund_from_address` / `fund_from_ts` | Tr | string / number | 存在率未记录 | 未记录 | 静态元数据 | 不需要 | 创建者资金来源（交易所/混币） | DROP |
| `is_honeypot` / `open_source` / `owner_renounced` | Tr | **string** | 仅 RH/BASE/ETH | 部分链 | 安全快照 | 存最新 | 预过滤（注意类型与 T/H、Security 不同） | DROP |
| `renounced_mint` / `renounced_freeze_account` | Tr | **string** | 存在率未记录 | 未记录 | 安全快照 | 存最新 | 同上 | DROP |
| `buy_tax` / `sell_tax` / `total_buy_tax` / `total_sell_tax` / `total_fee` / `trade_fee` / `buy_tips` / `fee_params` / `tax_allocation` | Tr | 混合 | `fee_params` 549/633；`tax_allocation` 仅 SOL/RH | 部分链 | 安全快照 | 存最新 | 税费风险 | DROP |
| `pool_address` / `quote_address` / `quote_address_type` / `route_*` / `decimals` / `standard` | Tr | string / number | `route_*` 仅 SOL/BASE/ETH | 部分链 | 静态元数据 | 不需要 | 详情页、链上核对 | DROP |
| `farcaster` / `zora_social_info` | Tr | object | 仅 BASE | 1 链 | 当前快照 | 不需要 | BASE 社交（粉丝数） | DROP |
| `status` / `launchpad_status` / `launch_flag` / `offchain` / `s_qsafe` / `mk` / `seq_index` / `bonus_category` | Tr | 混合 | `bonus_category` 仅 SOL 20 行 | 部分链 | UNKNOWN | 不需要 | 低价值 | DROP |

### 3.3 Signal（事件型注意力，仅 SOL / ROBINHOOD）

| 字段 | Endpoint | 实际类型 | 样本非空率 | 各链一致性 | 时间属性 | 能否历史化 | 可用于什么 | 生产现状 |
|---|---|---|---|---|---|---|---|---|
| `id` | S | string | 100/100 | 2 链 | 事件标识 | 存事件 | 去重 | DROP |
| `token_address` | S | string | 100/100 | 2 链 | 静态 | — | 身份 | DB |
| `signal_type` | S | number | 100/100；Phase 2 见 1/6/7/8/18/21；生产库已见 1,3,5–13,17–21 | 2 链 | 事件分类（**含义未编码 = UNKNOWN**） | **已历史化**（`discovery_event.source_variant`） | 按类型统计触发频率；需逐类回测才能赋义 | DB/META |
| `trigger_at` | S | number（Unix 秒） | 100/100 | 2 链 | 事件时间 | 可历史化 | **信号时间 → 之后 N 日收益回测** | DROP（事件用 `seen_at` 代替） |
| `trigger_mc` / `first_trigger_mc` | S | number | 100/100 | 2 链 | 事件时间点的值 | 可历史化 | 当前 MC / 首次触发 MC = 信号后涨幅 | DROP |
| `signal_times` / `signal_times_by_type` | S | number / object | 100/100 | 2 链 | 累计值 | 可历史化 | **重复触发次数**（注意力累积） | DROP |
| `ath` | S | number | 100/100，0 值 2 | 2 链 | 累计值（UNKNOWN 是价格还是市值） | 存最新 | 距 ATH | DROP |
| `market_cap`（顶层） | S | number | 100/100 | 2 链 | UNKNOWN（与 `data.market_cap` 仅 18/100 相同） | 已历史化（事件） | 市值 | DB |
| `data.usd_market_cap` | S | number | 100/100 | 2 链 | UNKNOWN 层（与 `data.market_cap` 100/100 相同） | — | **唯一显式 USD 的市值**，可用来交叉验证单位 | DROP |
| `cur_data.holder_count` | S | number | 100/100（与 `data.holder_count` 不同 82/100） | 2 链 | 当前快照 | 可历史化 | 当前持币 | **DROP（IMPLEMENTATION GAP：parser 未映射）** |
| `cur_data.liquidity` | S | number | 100/100，0 值 7 | 2 链 | 当前快照 | 已历史化（事件） | 当前流动性 | DB |
| `cur_data.top_10_holder_rate` | S | number | 100/100，0 值 29 | 2 链 | 当前快照 | 可历史化 | 集中度 | **DROP（GAP）** |
| `data.volume_/swaps_/buys_/sells_/net_buy_{1m,1h,6h,24h}` | S | number | 100/100，**全部为 0** | 2 链 | 字段名表示窗口；实际不可用 | 不要历史化 | **不可用**——不能作为短周期量能来源 | DROP（正确） |
| `data.price_volatility_rate` | S | number | 25/100 | 2 链 | UNKNOWN | 不建议 | 稀疏 | DROP |
| `data.created_timestamp` | S | number | 100/100 | 2 链 | 事件时间 | — | 币龄 | DB |
| `data.created_timestamp_us` / `open_timestamp_us` | S | number | 100/100 但全 0 | 2 链 | 不可用 | — | 无 | DROP |
| `data.fresh_wallet_rate` | S | number | 100/100，0 值 66 | 2 链 | UNKNOWN | 谨慎 | 比例，不是计数 | DROP |
| `data.claim_*`（`claim_wallet_address` 等） | S | string | 100/100 | 2 链 | 静态 | 不需要 | 费用认领方（详情页） | DROP |
| `data.trigger_count` / `callout_count` / `tg_call_count` / `x_user_follower` | S | number | key 100%（153/155 key 全行） | 2 链 | UNKNOWN / 累计 | 可历史化 | 注意力 | DROP |
| `data.*` 其余（与 Trenches 同名的风险、税、社交字段） | S | 混合 | 153/155 key 全行存在 | 2 链 | 同 §3.2 | 同 §3.2 | 同 §3.2 | DROP |

### 3.4 Kline（唯一原生历史）

| 字段 | Endpoint | 实际类型 | 样本非空率 | 各链一致性 | 时间属性 | 能否历史化 | 可用于什么 | 生产现状 |
|---|---|---|---|---|---|---|---|---|
| `time` | K | number（Unix **毫秒**，UTC 00:00 对齐） | 120/120 | 4 链一致 | 日K（bar **开盘**时间） | GMGN 自带 | 日序列键 | DB（`token_candle.candle_open_ts`） |
| `open` / `high` / `low` / `close` | K | **numeric string** | 120/120，无空串 | 4 链一致 | 日K | GMGN 自带（约 100 日） | N 日收益、连涨、新高、波动率、回撤 | DB → API/UI（衍生指标） |
| `volume` | K | numeric string | 120/120 | 4 链一致 | 日K（单位 UNKNOWN） | GMGN 自带 | **日成交量历史、放量** | DB → API（Kline-board 返回但 UI 不显示） |
| `amount` | K | numeric string | 120/120（生产库 4,788 行 NULL） | 4 链一致 | 日K（含义 UNKNOWN，与 volume 不同） | GMGN 自带 | 待定义；可能是 base-token 数量 | DB（API 不读） |
| `source` | K | string | 120/120 **全空串** | 4 链 | — | — | 无 | DROP |
| finalized / closed 标记 | K | **不存在** | — | — | — | — | 生产用观察时间自行推导（Phase 3 PASS） | 派生 |

> 只验证了 `--resolution 1d`。1h / 4h 等分辨率是否可用**未验证**（UNVERIFIED）。

### 3.5 Token Security

| 字段 | Endpoint | 实际类型 | 样本非空率（n=4） | 各链一致性 | 时间属性 | 能否历史化 | 可用于什么 | 生产现状 |
|---|---|---|---|---|---|---|---|---|
| `is_honeypot` | Sec | boolean / null | null 1/4 | 4 链 | 安全快照 | 存最新 + 变化事件 | **硬过滤** | DROP（只存 hash） |
| `honeypot` | Sec | number | 4/4（全 0） | 4 链 | 安全快照 | 同上 | 与上者不可合并 | DROP |
| `is_blacklist` / `blacklist` | Sec | bool/null（null 3/4）/ number（-1, 0） | — | 4 链 | 安全快照 | 同上 | 黑名单函数风险 | DROP |
| `is_open_source` / `open_source` | Sec | bool/null（null 1/4）/ number | — | 4 链 | 安全快照 | 同上 | 未开源过滤（EVM） | DROP |
| `is_renounced` / `renounced` | Sec | bool/null（null 1/4）/ number/null | — | 4 链 | 安全快照 | 同上 | owner 放弃 | DROP |
| `renounced_mint` | Sec | boolean | 4/4 | 4 链 | 安全快照 | 同上 | **mint 权限风险**（SOL 关键） | DROP |
| `renounced_freeze_account` | Sec | boolean | 4/4 | 4 链 | 安全快照 | 同上 | **freeze 权限风险**（SOL 关键） | DROP |
| `buy_tax` / `sell_tax` / `average_tax` / `high_tax` | Sec | numeric string（刻度未编码） | 4/4 | 4 链 | 安全快照 | 同上 | 高税过滤（需先确定 0–1 还是百分数） | DROP |
| `can_sell` / `can_not_sell` | Sec | number | 4/4（全 0，极性无法验证） | 4 链 | 安全快照 | 同上 | 不可卖风险（待验证） | DROP |
| `top_10_holder_rate` | Sec | string | 4/4 | 4 链 | 安全快照 | 可历史化 | 集中度 | DROP |
| `privileges` | Sec | array / null（null 2/4） | 观察到 `blacklist`、`hidden_owner`、`max_tx_amount`、`mintable`、`multi_address`、`proxy_calls` | 4 链 | 安全快照 | 存最新 | **特权风险标签**（EVM） | DROP |
| `lock_summary.is_locked` / `lock_percent` / `left_lock_percent` / `lock_detail[]` | Sec | bool / string / array | 4/4；`lock_tags` 全 null | 4 链 | 安全快照 | 存最新 | LP 锁、是否 blackhole | DROP |
| `burn_ratio` / `burn_status` / `dev_token_burn_amount` / `dev_token_burn_ratio` | Sec | string | 4/4（burn_status 空串 3/4） | 4 链 | 安全快照 | 存最新 | 详情页 | DROP |
| `hide_risk` / `is_show_alert` / `flags` | Sec | bool / bool / array | 4/4（全 false / 空） | 4 链 | 安全快照 | 存最新 | 语义未验证 | DROP |
| `lockInfo` | Sec | null | 4/4 null | 4 链 | — | — | 不可用 | DROP |

---

## 4. Time Semantics

| 时间属性 | 字段 | 使用规则 |
|---|---|---|
| **日K** | Kline OHLCV、`amount` | 唯一可直接回溯的序列。今天的 bar 是进行中的；正式指标只用观察时间证明已收盘的 bar（Phase 3 契约）。 |
| **24h rolling** | Hot `volume/swaps/buys/sells`（显式）；Trenches `*_24h`（字段名显式）；Trending 同名字段（请求参数 24h） | 滚动窗口 ≠ UTC 日。**不能**与日K volume 互换或相减。 |
| **短周期变化** | `price_change_percent1h/5m/1m` | 字段名给出窗口，滚动方式 payload 未定义 → 按 rolling 使用但标注 UNKNOWN。 |
| **当前快照** | price、liquidity、market_cap、holder_count、聪明钱计数、各类 rate | 只表示"被观察的那一刻"；变化率必须由我们存快照计算。payload 不含观测时间，只能用我们的采集时间。 |
| **排名** | `rank`（T/H 本次请求内） | 依赖请求参数（链、interval、limit）；不同请求间可比，需固定参数。 |
| **累计值** | `history_highest_market_cap`、`signal_times`、`ath`、`twitter_*_count`、`complete_cost_time`；`visiting_count` / `callout_count` 推测为累计（UNKNOWN） | 用差分得到增量。 |
| **事件时间** | `creation_timestamp`、`created_timestamp`、`open_timestamp`、`complete_timestamp`、`trigger_at`、`dexscr_*_ts`、`tweet_publish_time` | 0 是"未发生/未知"哨兵，不是 1970。 |
| **静态元数据** | 名称、logo、launchpad、creator、社交链接、pool/route 地址、decimals、`initial_liquidity` | 存一次，变化检测即可。 |
| **安全快照** | Security 全部字段；T/H/Tr 内嵌的风险字段 | 低频刷新；保存变化事件。 |
| **UNKNOWN** | `price_change_percent`（主字段窗口）、`hot_level`、`visiting_count`、`square_mentions`、`rug_ratio`、`entrapment_ratio`、`fresh_wallet_rate`、`net_buy_24h`、`progress`、`signal_type` 含义、Kline `amount`、所有金额单位 | 只能做相对比较（同 token 自身变化、同 endpoint 内排序），不能做跨源绝对比较。 |

---

## 5. Price Fields

| 能力 | GMGN 直接提供？ | 来源 | 需要自己算？ |
|---|---|---|---|
| 当前价格 | **是** | T/H/Tr `price`；Kline 当日 `close` | — |
| 1h change | **是** | T/H `price_change_percent1h` | — |
| 6h change | **否** | — | 用 `hourly_price`（已有，2026-08-30 起）算 `p_now/p_6h_ago − 1` |
| 24h change | **是**（窗口未在 payload 编码） | T/H `price_change_percent` | 也可用 `hourly_price` 自算校验 |
| 5m / 1m change | **是** | T/H `price_change_percent5m/1m` | — |
| N 日累计涨跌 | 否 | Kline `close` | **是**（生产已实现 `changeNd`，仅 FINALIZED bar） |
| 日K | **是** | Kline | — |
| 连续上涨天数 | 否 | Kline `close` | **是**（生产已实现 official streak） |
| 新高 | 部分 | `history_highest_market_cap`（MC 口径）、Signal `ath`（口径 UNKNOWN） | 价格新高需用 Kline `high` 自算 `close ≥ max(high[−N..−1])` |
| 加速上涨 | 否 | `price_change_percent1h` vs `price_change_percent`；Kline 日收益 | **是**（见 §14） |
| 波动率 | 否（Signal `price_volatility_rate` 25/100，口径未知） | Kline OHLC | **是**：日收益标准差、`(high−low)/close` |

---

## 6. Volume Fields

| 能力 | 状态 | 来源 / 说明 |
|---|---|---|
| volume 1h | **不可用** | 仅 Signal `data.volume_1h`，100/100 为 0 |
| volume 6h | **不可用** | 仅 Signal `data.volume_6h`，100/100 为 0 |
| volume 24h | **可用** | T/H `volume`、Tr `volume_24h`（Tr 当前被生产丢弃） |
| daily volume | **可用** | Kline `volume`（GMGN 自带约 100 日历史） |
| buy volume / sell volume | **不可靠** | 仅 Tr `buy_volume_24h/sell_volume_24h`，116/633 存在、SOL 无、与 volume_24h 吻合仅 9/116 |
| volume change | 自算 | Kline 日量差分；24h rolling 需自存快照 |
| volume acceleration | 自算 | Kline 日量二阶差分 / 比率 |

可构造的放量信号：

| 信号 | 能否现在就算 | 公式（同 token 内比率，与单位无关） |
|---|---|---|
| 24h 放量 | **能**（日K）；rolling 版需历史 | `vol_d0 / mean(vol_d−7..d−1)`，d0 = 最新 FINALIZED bar |
| 连续多日放量 | **能** | 连续满足 `vol_d > vol_{d−1}` 的天数（与 streak 同算法） |
| 今日量 / 过去 7 日均量 | **能**（今日为进行中 bar，需按已过时间折算或只用 FINALIZED） | `vol_today / (elapsed_h/24) / mean7`（盘中版，标注 PROVISIONAL） |
| 价涨 + 量增 | **能** | `ret_1d > 0 AND vol_ratio_7d > 1.5` |
| 量价背离 | **能** | `price streak ≥ 2 AND vol 连续下降`（上涨乏力）；或 `价格跌 AND 量放大`（出货） |

> 局限：Kline 中位 token 只有 **3 根**日K（新币多），7 日均量对大部分新币不可算；
> 需要 "可用天数 < 窗口 → NULL" 规则，不得用 0 填充。

---

## 7. Activity Fields

| 指标 | 是否存在 | 来源 | 说明 |
|---|---|---|---|
| swaps | **存在** | T/H `swaps`、Tr `swaps_24h` | 24h 交易笔数 |
| buys | **存在** | T/H `buys`、Tr `buys_24h` | 买入**笔数** |
| sells | **存在** | T/H `sells`、Tr `sells_24h` | 卖出**笔数** |
| tx count | 等价于 swaps | 同上 | 无独立字段 |
| traders | **不存在** | — | Trenches 有 `bundler_trader_amount_rate`、`rat_trader_amount_rate`，均为比例 |
| makers | **不存在** | — | — |
| buyers / sellers（unique） | **不存在** | — | `buys/sells` 不能替代 |
| unique trader / participant | **不存在** | — | — |
| active wallets / new holders / new buyers | **不存在** | — | `fresh_wallet_rate` 是比例；`new_wallet_volume` 全 0 |
| 历史笔数 | **不存在** | Kline 无笔数 | 必须自己存快照 |

> ⚠️ **不要把 transaction count、swap count、holders 或 makers 当作 wallet count。**
> `holder_count` 是持币地址快照，不是交易者；`swaps` 是笔数，一个钱包可贡献任意多笔。
> `token traders` / `token holders` endpoint 可能提供钱包维度，但**本次审计没有 raw 证据**（§12）。

---

## 8. Liquidity Fields

| 能力 | 状态 | 来源 |
|---|---|---|
| liquidity | **存在**（当前快照） | T/H/Tr `liquidity`、Signal `cur_data.liquidity` |
| initial liquidity | **存在** | T/H `initial_liquidity` |
| liquidity change | 自算 | `discovery_event.liquidity`（5 分钟桶，仅上榜时）；`token_snapshot.liquidity_updated_at` |
| pool liquidity / quote liquidity | **不存在于已验证 endpoint** | `token pool` UNVERIFIED |
| LP 锁 | **存在** | T/H `lock_percent`；Security `lock_summary` |
| market cap / liquidity | 自算 | `market_cap / liquidity`（同源同刻，单位一致性未验证） |

可构造：

| 信号 | 公式 | 状态 |
|---|---|---|
| 最低流动性门槛 | `liquidity ≥ L_min`（生产已用 50k 门槛） | 已实现 |
| 流动性快速增加 | `liq_now / liq_6h_ago`（事件历史） | 能算（仅限持续上榜 token）；固定频率需新增快照 |
| 流动性成长倍数 | `liquidity / initial_liquidity` | 能算（需接入 `initial_liquidity`） |
| Volume / Liquidity（周转） | `volume_24h / liquidity` | 能算（同源同刻）；单位假设需验证 |
| MC / Liquidity | `market_cap / liquidity` | 能算；值很大 = 深度薄 |
| 流动性不足风险 | `liquidity < L_min OR mc/liq > X` | 能算 |
| 爆量但深度不足（假信号） | `vol/liq > 20 AND liquidity < L_min`；或 `is_wash_trading = true` | 能算（需接 `is_wash_trading`） |

---

## 9. Market Cap / Supply

| 字段 | 状态 | 说明 |
|---|---|---|
| market cap | **存在** | T/H/Tr `market_cap`；Signal 有三层（顶层、`data.market_cap`、`data.usd_market_cap`）且顶层与 data 层仅 18/100 相同 |
| FDV | **不存在** | 自算 `price × total_supply`（单位 UNKNOWN；需与 market_cap 交叉验证） |
| circulating supply | **不存在** | — |
| total supply | **存在** | T/H/Tr/Signal `total_supply` |
| 历史最高市值 | **存在** | T/H `history_highest_market_cap` |
| 历史市值 | 自存 | `discovery_event.market_cap`（上榜时）；日K × total_supply 可近似（假设供应不变） |

用途：

| 用途 | 公式 | 状态 |
|---|---|---|
| 小市值突破 | `mc < 1M AND ret_1d > 0.3 AND vol_ratio > 2` | 能算 |
| 市值分层 | `<100k / 100k–1M / 1M–10M / >10M` | 能算 |
| 市值快速扩张 | `mc_now / mc_24h_ago`（事件历史或日K close 比率代理） | 能算（代理） |
| Volume / MC | `volume_24h / market_cap` | 能算（单位假设） |
| Liquidity / MC | `liquidity / market_cap` | 能算 |
| 距 ATH | `market_cap / history_highest_market_cap` | 能算（需接入） |

---

## 10. Attention Fields

| 字段 / 来源 | 存在 | 历史 | 用途 |
|---|---|---|---|
| Trending `rank` | **是** | **已历史化**（`discovery_event`，5 分钟桶，2026-10-02 04:47Z 起，606 个 token 有 ≥2 次观测） | 新进榜、rank velocity、在榜时长 |
| Hot-search 出现 / `rank` | **是** | **已历史化**（30,042 事件） | "被搜索" = 注意力；首次上 Hot = 注意力事件 |
| `hot_level` | 是（语义 UNKNOWN） | 否 | 热度分层 |
| `visiting_count` | 是（UNKNOWN，疑似累计） | 否 | 差分 = 访问增速 |
| `square_mentions` | 是（UNKNOWN） | 否 | 提及增速 |
| `dexscr_*` + `_ts` | 是 | 否 | 付费推广/趋势条事件 |
| Signal 事件 | **是**（SOL/RH） | **已历史化**（按 `signal_type` 存于 `source_variant`） | 信号触发、重复触发 |
| `x_user_follower`、`tg_call_count`、`callout_count`（Tr/S） | 是（存在率未记录） | 否 | 社交增长 |
| Trench 阶段 | **是** | **已历史化** | 生命周期跃迁 |
| search rank / popularity 分数 | **不存在**（除上述） | — | `market search` UNVERIFIED |

可构造：

| 信号 | 公式 | 现在能算？ |
|---|---|---|
| 新进入热榜 | 该 token 在 source=trending/hot 的首个事件 `first_seen` 落在最近 1h | **能** |
| 排名快速上升 | `rank(t−1h) − rank(t)` ≥ 30 | **能** |
| 热度增加但价格未启动 | 新进 Hot 或 rank velocity 高 AND `|price_change_percent1h| < 5%` | **能**（需接 1h 涨跌） |
| 价格上涨 + 热度同步 | `ret_1h > 0.1 AND rank velocity > 0` | **能** |
| 注意力领先价格候选 | 过去 6h 内出现 ≥2 种注意力事件（Hot、Signal、rank↑、dexscr）且 6h 价格涨幅 < 10% | **能**（6h 价格用 `hourly_price`） |

> 注意：在榜 token 才有 rank 观测；不在榜 ≠ rank 为 0，应视为 "rank > limit（100）"，不要填 0。

---

## 11. Security Fields

| 风险类别 | GMGN 字段 | 有/无 |
|---|---|---|
| honeypot | Sec `is_honeypot` / `honeypot`；T/H `is_honeypot`（number）；Tr `is_honeypot`（string，仅 RH/BASE/ETH） | **有** |
| mint | Sec `renounced_mint`；T/H `renounced_mint`（null 多）；`privileges` 含 `mintable` | **有** |
| freeze | Sec `renounced_freeze_account`；T/H 同名 | **有** |
| top holder concentration | `top_10_holder_rate`（Sec/T/H/Tr/S cur_data）；`dev_team_hold_rate`、`suspected_insider_hold_rate`、`top70_sniper_hold_rate` | **有** |
| ownership | `is_renounced` / `renounced`；Tr `owner_renounced`；`privileges` 含 `hidden_owner` | **有** |
| mutable metadata | — | **无** |
| suspicious tax | `buy_tax`、`sell_tax`、`average_tax`、`high_tax`（刻度未编码）；Tr `total_*_tax` | **有**（刻度需验证） |
| blacklist | `is_blacklist`（null 3/4）、`blacklist`（−1/0）；`privileges` 含 `blacklist` | **有**（覆盖弱） |
| rug risk | T/H/Tr `rug_ratio`（UNKNOWN 口径）；LP 锁 `lock_summary`、`lock_percent`；`creator_close`；`creator_created_count` | **部分**（无直接 rug 评分） |
| proxy / upgradeable | `privileges` 含 `proxy_calls` | **有**（EVM，样本少） |
| wash trading | T/H/Tr `is_wash_trading` | **有**（UNKNOWN 口径） |
| 仿盘 | `*_dup` 字段 | **有** |

**类型陷阱（IMPLEMENTATION GAP 风险，非 bug 报告）：** 同名风险字段在不同 endpoint 类型不同
（Security boolean/null、Trending number、Trenches string），`honeypot` 与 `is_honeypot`
不是别名。必须按 endpoint 分别解析，`null` 表示"未评估"而不是"安全"。

---

## 12. Missing Important Fields

| 想要的能力 | GMGN 已验证 endpoint 中 | 替代 / 下一步 |
|---|---|---|
| unique traders / makers / buyers / sellers | **无** | `token traders` 可能有——**UNVERIFIED**，需一次经你批准的 raw 验证请求 |
| active wallets / new holders / new buyers | **无** | 同上；`token holders` UNVERIFIED。rhv2 管线另有 Blockscout 持币快照（非 GMGN） |
| 1h / 6h volume | **无可用值**（Signal 全 0） | 自存 24h rolling 快照做差分不可行（rolling 差分≠窗口量）；可试 Kline 小分辨率（UNVERIFIED） |
| 6h price change | **无** | `hourly_price` 自算 |
| FDV / circulating supply | **无** | 自算 FDV；流通量无 |
| 历史 holder / liquidity / market cap / swaps | **无** | 必须自己固定频率历史化 |
| pool / quote liquidity、多池 | **无** | `token pool` UNVERIFIED |
| 观测/更新时间戳 | **无** | 只能用采集时间 |
| 金额单位 | **无**（仅 `usd_market_cap`） | 用 Signal `usd_market_cap == data.market_cap`（100/100）作单位旁证，仍需更多验证 |
| mutable metadata | **无** | — |
| `signal_type` 含义 | **无** | 用历史事件回测每类信号的后续收益来赋义 |
| 小时/4h K 线 | **未验证** | 一次 raw 验证 |

---

## 13. Unused But Valuable Fields

"现状"按 HEAD 生产代码。`DB` = 已入库但 API 不读；`DROP` = 未读或被丢弃。

### HIGH — 明显提升早期发现能力

| 字段 | Endpoint | 现状 | 价值 | 处理方式 |
|---|---|---|---|---|
| `buys` / `sells`（`buys_24h` / `sells_24h`） | T/H/Tr | DROP | 买卖失衡、活跃度动量 | **入库 + 5 分钟历史快照** |
| `swaps` / `swaps_24h` | T/H/Tr | T/H DB（API 不读）；Tr DROP（GAP） | 交易笔数增速 | 入库 + 历史快照 + API |
| Tr `volume_24h` | Tr | DROP（GAP：字段名不匹配） | 新币量能 | 修映射后入库（留到实现阶段） |
| `price_change_percent1h` / `5m` | T/H | DROP | 启动/加速检测 | 入库 + 历史快照（5m 仅实时告警） |
| `rank`（API 化） | T/H | DB（`discovery_event`，API 不读） | 新进榜、rank velocity | **零新增采集**，只需 API/计算层 |
| `smart_degen_count` / `renowned_count` | T/H/Tr | DB（API 不读）/ DROP | 聪明钱进场 | 历史快照 + API |
| Signal `trigger_at` / `trigger_mc` / `first_trigger_mc` / `signal_times` | S | DROP | 信号回测、重复触发 | 事件表增加列 |
| Kline `volume`（UI 化） | K | DB + API，UI 不显示 | 放量、量价 | 只需计算层 + UI |
| `is_wash_trading` | T/H/Tr | DROP | 放量信号反证 | 存最新 |
| `history_highest_market_cap` | T/H | DROP | 新高突破、距 ATH | 存最新 |

### MEDIUM — 详情页、二次筛选、风控

| 字段 | Endpoint | 现状 | 用途 | 处理方式 |
|---|---|---|---|---|
| Security 语义字段（`is_honeypot`、`renounced_mint/freeze`、`is_renounced`、`is_open_source`、`buy/sell_tax`、`privileges`、`lock_summary`） | Sec | 只存 hash | 硬过滤、详情页 | 存最新 + 变化事件 |
| T/H 内嵌风险字段（`is_honeypot`、`renounced_*`、`buy_tax/sell_tax`、`rug_ratio`） | T/H | DROP | 免额外请求的预过滤 | 存最新 |
| `top_10_holder_rate`、`dev_team_hold_rate`、`sniper_count`、`top70_sniper_hold_rate`、`bundler_rate`、`rat_trader_amount_rate`、`bot_degen_rate`、`bluechip_owner_percentage` | T/H/Tr | 部分 DB（API 不读）/ DROP | 筹码质量 | 低频历史快照（1h） |
| Signal `cur_data.holder_count` / `cur_data.top_10_holder_rate` | S | DROP（GAP） | 当前持币 | 映射 |
| `initial_liquidity` | T/H | DROP | 流动性成长倍数 | 存一次 |
| `total_supply` | T/H/Tr/S | DROP | FDV、单位交叉验证 | 存最新 |
| `visiting_count`、`square_mentions`、`hot_level` | T/H | DROP | 注意力（语义待验证） | 历史快照，先观察相关性 |
| `dexscr_*` + `_ts` | T/H | DROP | 推广事件 | 存事件 |
| Trench `progress`、`complete_timestamp`、`complete_cost_time` | Tr | DROP | 毕业速度 | 历史快照 |
| `creator_created_count`、`creator_created_open_ratio`、`creator_balance_rate`、`creator_close`、`fund_from` | Tr/T/H | DROP | 连环发币者过滤 | 存最新 |
| `x_user_follower`、`tg_call_count`、`callout_count` | Tr/S | DROP | 社交增长 | 历史快照（1h） |
| `*_dup`、`twitter_rename_count`、`twitter_create_token_count` | T/H/Tr | DROP | 仿盘/骗局过滤 | 存最新 |
| `price_change_percent1m` | T/H | DROP | 实时告警确认 | 只实时计算，不入库 |

### LOW — 信息价值低或与已有字段重复

| 字段 | 原因 |
|---|---|
| `buy_volume_24h` / `sell_volume_24h` / `net_buy_24h` | 稀疏、公式不可验证 |
| `new_wallet_volume` | 全部为 0 |
| Signal `data.volume_/swaps_/buys_/sells_/net_buy_*` | 全部为 0 |
| `created_timestamp_us` / `open_timestamp_us` | 全部为 0 |
| Kline `source` | 全空串 |
| `start/end_live_timestamp`、`is_token_live` | 极稀疏 |
| `trans_*`、`tcid`、`id`、`logo_small_base64`、`seq_index`、`mk`、`s_qsafe` | 展示/内部字段 |
| `route_*`、`pool_type`、`decimals`、`standard`、`quote_address_type` | 仅链上核对用 |
| `gas_fee`、`buy_tips`、`fee_params`、`tax_allocation`、`entrapment_ratio` | 语义不明或低价值 |
| Signal `data.market_cap` 层 | 与顶层不一致、与 usd 层重复 |
| `farcaster` / `zora_social_info` | 仅 BASE |

---

## 14. Derived Metrics We Can Build

格式：**原始字段 · 公式 · 窗口 · 缺失处理 · 现在能算？ · 需新增历史？**

### Price Momentum

| 指标 | 原始字段 | 公式 | 窗口 | 缺失处理 | 现在能算 | 需新增历史 |
|---|---|---|---|---|---|---|
| Return N 日（1/3/7/14D） | Kline `close` | `close_d0 / close_d−N − 1`，仅 FINALIZED、连续 | 1/3/7/14 日 | 缺 bar 或尾部 PROVISIONAL → NULL | **是**（已实现 `changeNd`） | 否 |
| Streak | Kline `close` | 尾部连续 `close_d > close_d−1` 的天数 | 全部 | <2 根相邻 → NULL；平/跌 → 0 | **是**（已实现） | 否 |
| 日内加速度 | T/H `price_change_percent1h`、`price_change_percent` | `acc = pc1h − pc24h/24` | 1h vs 24h 均速 | 任一缺 → NULL | 是（需接入字段） | 否 |
| 日K 加速度 | Kline | `ret_1d(d0) − ret_1d(d−1)`，或 `ret_3d − 3·ret_1d(d−3..)` | 2–3 日 | 同上 | **是** | 否 |
| 新高突破 | Kline `close/high` | `close_d0 ≥ max(high_{d−N..d−1})` | N=7/14/30 | 可用 bar < N → NULL | **是** | 否 |
| 6h return | `hourly_price` | `p_now / p_{now−6h} − 1` | 6h | 小时桶缺 → NULL | **是**（已有表） | 否 |
| 波动率 | Kline | `stdev(ln(close_d/close_d−1))` | 7/14 日 | 不足 → NULL | **是** | 否 |
| 距 ATH | `market_cap`、`history_highest_market_cap` | `mc / hh_mc` | — | 缺 → NULL | 需接入 | 否 |

### Volume Momentum

| 指标 | 原始字段 | 公式 | 窗口 | 缺失处理 | 现在能算 | 需新增历史 |
|---|---|---|---|---|---|---|
| 日量比 | Kline `volume` | `vol_d0 / mean(vol_d−7..d−1)` | 7 日 | 可用 <7 → NULL（可选 ≥3 降级并标注） | **是** | 否 |
| 连续放量天数 | Kline `volume` | 尾部连续 `vol_d > vol_d−1` | 全部 | 同 streak | **是** | 否 |
| 量加速度 | Kline `volume` | `ratio(d0) − ratio(d−1)` | 2 日 | — | **是** | 否 |
| 24h rolling 量增速 | T/H `volume`、Tr `volume_24h` | `vol24_now / vol24_{now−6h}` | 6h | 两点必须都有观测 | 否 | **是**（5 分钟或 1h 快照） |
| 盘中量投影 | Kline 当日 `volume` | `vol_today × 86400/elapsed / mean7` | 当日 | 标 PROVISIONAL，不进正式榜 | **是** | 否 |

### Attention Momentum

| 指标 | 原始字段 | 公式 | 窗口 | 缺失处理 | 现在能算 | 需新增历史 |
|---|---|---|---|---|---|---|
| Rank delta | `discovery_event.rank`（trending/hot） | `rank_{t−Δ} − rank_t` | Δ = 1h / 6h | 不在榜 → 视为 101（不是 0）；从未上榜 → NULL | **是** | 否 |
| Rank velocity | 同上 | 窗口内 rank 对时间的线性斜率 | 1h | ≥3 观测才算 | **是** | 否 |
| Hot-search 首次进入 | `discovery_event` source=hot | `first_seen_hot ∈ (now−1h, now]` | 1h | — | **是** | 否 |
| 在榜时长 | `discovery_event` | 窗口内在榜 5 分钟桶数 × 5 分钟 | 24h | — | **是** | 否 |
| 信号密度 | Signal 事件 | 窗口内事件数、不同 `signal_type` 数 | 6h / 24h | 仅 SOL/RH；其他链 NULL | **是**（事件已存） | 否 |
| 重复触发 | `signal_times` | 差分 | 24h | — | 否 | **是** |
| 访问增速 | `visiting_count` | `Δvisiting / Δt` | 1h | 语义未验证 | 否 | **是** |

### Activity Momentum

| 指标 | 原始字段 | 公式 | 窗口 | 缺失处理 | 现在能算 | 需新增历史 |
|---|---|---|---|---|---|---|
| 买卖失衡 | `buys`、`sells` | `buys / (buys + sells)` | 24h rolling 快照 | 和为 0 → NULL | 否（未入库） | 否（单点即可）——入库即可算 |
| 笔数增速 | `swaps` | `swaps_now / swaps_{t−6h}` | 6h | 两点需有 | 否 | **是** |
| 交易加速度 | `swaps` | 增速的差分 | 6h + 6h | — | 否 | **是** |
| 平均单笔 | `volume`、`swaps` | `volume / swaps` | 24h | swaps=0 → NULL | 否 | 否 |
| 聪明钱增量 | `smart_degen_count` | `Δcount` | 6h / 24h | — | 否 | **是** |

> 失衡只说明**笔数**偏买，不说明**买家数量**更多。

### Liquidity Quality

| 指标 | 原始字段 | 公式 | 窗口 | 缺失处理 | 现在能算 | 需新增历史 |
|---|---|---|---|---|---|---|
| Volume / Liquidity | `volume`、`liquidity` | 同源同刻相除 | 24h | 任一缺或 liq=0 → NULL | 是（单点） | 否 |
| Liquidity / MC | `liquidity`、`market_cap` | 相除 | 当前 | 同上 | 是 | 否 |
| 流动性增长 | `liquidity` | `liq_now / liq_{t−24h}` | 24h | 需两点 | 部分（事件历史有缺口） | **是**（固定频率） |
| 流动性成长倍数 | `liquidity`、`initial_liquidity` | 相除 | — | 缺 → NULL | 需接入 | 否 |

### Breakout Combination

```
BurstScore = w1·PriceMom + w2·VolumeMom + w3·AttentionMom + w4·ActivityMom + w5·LiquidityQ
           且必须通过 SafetyGate
```

- 每个分量先做**分链、分市值层的百分位**（避免 SOL 新币与 ETH 老币直接比）。
- 任一分量为 NULL → 该分量不贡献，同时输出 `coverage = 有效分量数 / 5`；coverage < 0.6 不进正式榜。
- **SafetyGate**（硬过滤）：`is_honeypot ≠ true`，`renounced_mint ≠ false`（SOL），
  `sell_tax` 不高于阈值，`is_wash_trading ≠ true`，`liquidity ≥ L_min`，`top_10_holder_rate ≤ T`。
- 权重先等权，之后用历史回测（§17 的快照）校准。

---

## 15. Burst / Breakout Detection Signals

| 信号 | 条件（示例阈值，需回测） | 所需字段 | 现在能算？ |
|---|---|---|---|
| **S1 日K 量价齐升** | `ret_1d > 0.15 AND vol_ratio_7d > 2 AND streak ≥ 2` | Kline | **是** |
| **S2 连续放量连涨** | `streak ≥ 3 AND 连续放量天数 ≥ 3` | Kline | **是** |
| **S3 新高突破** | `close ≥ max(high_14d) AND vol_ratio_7d > 1.5` | Kline | **是** |
| **S4 注意力领先价格** | 1h 内新进 Hot 或 rank 上升 ≥30，且 `pc1h < 5%` | `discovery_event` + `price_change_percent1h` | 需接 pc1h |
| **S5 盘中启动** | `pc1h > 10% AND pc5m > 0 AND buys/(buys+sells) > 0.6` | T/H | 需接字段 |
| **S6 聪明钱进场** | `Δsmart_degen_count(6h) ≥ 3 AND 价格 6h 涨幅 < 20%` | `smart_degen_count` 历史 | 需历史 |
| **S7 新币毕业加速** | trench 阶段 `new_creation → near_completion → completed` 在 X 小时内完成，且 `holder_count` 增长 | `discovery_event` + META | **是**（阶段 + holder 元数据已存） |
| **S8 多源共振** | 6h 内同时出现：Trending 上榜、Hot 上榜、Signal 触发 | `discovery_event` | **是** |
| **反证 F1 假放量** | `vol/liq > 20 AND liquidity < L_min` 或 `is_wash_trading` | T/H | 部分 |
| **反证 F2 筹码集中** | `top_10_holder_rate > 0.5 OR dev_team_hold_rate > 0.2 OR bundler_rate 高` | T/H/Sec | 需接字段 |
| **反证 F3 付费推广** | `dexscr_ad_ts` / `dexscr_boost_ts` 在 1h 内且没有自然 rank 上升 | T/H | 需接字段 |

**能立即上线（零新采集）的组合：** S1、S2、S3、S7、S8。

---

## 16. Token Detail Page Design

图例：**G** = GMGN 直接提供（当前快照）· **GH** = GMGN 自带历史 · **L** = 本地已有历史 · **N** = 需要新增历史化 · **✗** = 无数据源

### 头部 / 基础

| 字段 | 来源 | 状态 |
|---|---|---|
| price、`price_change_percent`、1h / 5m | T/H | G |
| market cap | T/H/Tr/S | G（单位未编码，标注） |
| FDV | `price × total_supply` | 自算（标注"估算"） |
| liquidity、LP 锁 | T/H、Sec | G |
| 币龄、launchpad、创建者 | T/H/Tr | G |
| 社交链接、粉丝数 | T/H/Tr | G |
| 每个数值的来源与观测时间 | 本地 | N（目前不完整，Phase 3 P3-05） |

### Momentum

| 字段 | 来源 | 状态 |
|---|---|---|
| 1D / 3D / 7D / 14D return | Kline | GH → 已实现 |
| streak、streak return、回撤 | Kline | GH → 已实现 |
| 6h return | `hourly_price` | L |
| 新高状态、距 ATH | Kline、`history_highest_market_cap` | GH + G |
| 波动率 | Kline | GH |

### Volume

| 字段 | 来源 | 状态 |
|---|---|---|
| 24h volume | T/H/Tr | G |
| 日成交量柱状图 | Kline | GH（已入库未展示） |
| 日量比、连续放量 | Kline | GH 自算 |
| 24h rolling 量曲线 | — | N |

### Activity

| 字段 | 来源 | 状态 |
|---|---|---|
| swaps、buys、sells（24h） | T/H/Tr | G（需接入） |
| 买卖笔数比 | 自算 | G |
| 笔数趋势 | — | N |
| traders / makers / unique buyers | — | **✗**（标注"GMGN 未提供"，不显示替代值） |

### Attention

| 字段 | 来源 | 状态 |
|---|---|---|
| Trending rank 曲线 | `discovery_event` | L |
| Hot-search 出现时间线 | `discovery_event` | L |
| Signal 事件时间线（类型、触发 MC） | `discovery_event`（类型已存）+ `trigger_mc` | L + N |
| `hot_level`、`visiting_count`、`square_mentions` | T/H | G（语义标注 UNKNOWN） |
| DexScreener 推广事件 | T/H | G |
| Trench 生命周期 | `discovery_event` | L |

### Holders / 筹码

| 字段 | 来源 | 状态 |
|---|---|---|
| holder_count（当前） | T/H/Tr/S | G |
| holder 曲线 | `discovery_event.metadata_json` | L（不定时，仅上榜时）→ 固定频率需 N |
| 聪明钱 / KOL / 狙击 / 机器人 / 捆绑 | T/H | G（需接入）；趋势 N |
| Top10、dev、insider 持仓 | T/H/Tr/Sec | G |

### Security

| 字段 | 来源 | 状态 |
|---|---|---|
| honeypot、mint、freeze、owner、开源、黑名单、税、特权、LP 锁 | Sec（+ T/H 内嵌） | G（当前只存 hash，需接入） |
| 刷量、仿盘、rug_ratio | T/H/Tr | G（语义标注） |
| 安全变化时间线 | — | N |
| mutable metadata | — | ✗ |

### History（图表）

| 图 | 来源 | 状态 |
|---|---|---|
| 日K（OHLC + 量） | Kline | GH，已入库 |
| 小时价格线 | `hourly_price` | L |
| rank 历史 | `discovery_event` | L |
| liquidity 历史 | `discovery_event`（上榜时） | L（有缺口）→ N |
| market cap 历史 | `discovery_event` | L（有缺口） |
| volume 24h / swaps / buys / sells 历史 | — | N |

---

## 17. Recommended Historical Snapshots

原则：**GMGN 唯一自带的历史是日K**；其他一切变化率都需要我们按固定节奏存。
`discovery_event` 已是"上榜时"的机会性历史（5 分钟桶），但它**只在 token 出现在某个榜时**
才有记录，不适合做固定窗口差分。

| 快照 | 字段 | 频率 | 覆盖对象 | 原因 |
|---|---|---|---|---|
| **H1 活跃度快照** | `volume`/`volume_24h`、`swaps`、`buys`、`sells`、`price`、`price_change_percent`、`price_change_percent1h`、`liquidity`、`market_cap`、`holder_count`、source、observed_at | 5 分钟（随现有发现源节奏） | 当次返回的所有行 | 活跃度与 rolling 量的唯一历史来源 |
| **H2 事件元数据补全** | 把 `volume_24h`、`swaps_24h`、`buys`、`sells`、`price_change_percent1h` 加进 `discovery_event` 的紧凑元数据 | 随事件 | 同上 | 成本最低的实现方式（只多几个 key） |
| **H3 筹码/聪明钱快照** | `smart_degen_count`、`renowned_count`、`sniper_count`、`bot_degen_count`、`top_10_holder_rate`、`dev_team_hold_rate`、`bundler_rate`、`rat_trader_amount_rate`、`top70_sniper_hold_rate` | 1h | 已入册 token 的最新观测 | 变化慢，1h 足够 |
| **H4 注意力快照** | `rank`（已有）、`hot_level`、`visiting_count`、`square_mentions`、`x_user_follower`、`tg_call_count`、`callout_count`、`signal_times` | 随事件（rank）/ 1h（其余） | 同上 | 注意力增速 |
| **H5 Signal 事件补全** | `trigger_at`、`trigger_mc`、`first_trigger_mc`、`signal_times`、`ath`、`id` | 随事件 | SOL/RH | 信号回测 |
| **H6 安全变化日志** | Security 全部语义字段 + 原始 JSON | 状态变化时 | 安全 lane 覆盖的 token | 风险变化时间线 |
| **H7 日终固定快照** | 每个已入册 token 在 UTC 00:00 后第一次观测的 holder/liquidity/mc/swaps | 每日 | 全部已入册 | 提供**固定节奏**的日级非价格历史，可与日K 对齐 |

**不值得入库（只实时计算）：** `price_change_percent1m`、Vol/Liq、MC/Liq、买卖失衡、平均单笔
（都可由 H1 当场计算）。

---

## 18. Recommended Next Implementation Order

按"价值 / 成本"排序；每步都基于已确认存在的字段。

| 顺序 | 内容 | 新采集？ | 影响模块 | 理由 |
|---|---|---|---|---|
| **1** | 日K 成交量动量（日量比、连续放量、量价齐升/背离）+ 新高突破 + 波动率 | 否 | 日K连涨、爆款发现、详情页 | 数据已在库，同 token 比率不受单位问题影响 |
| **2** | 注意力层：基于 `discovery_event` 的新进榜、rank velocity、在榜时长、多源共振（S8）、trench 毕业加速（S7） | 否 | 爆款发现、告警 | 历史已在库，只缺计算与 API |
| **3** | 发现源字段补全：`buys/sells/swaps`、`price_change_percent1h/5m`、`history_highest_market_cap`、`initial_liquidity`、`total_supply`、`is_wash_trading`；并修复 Trench `*_24h` 与 Signal `cur_data` 映射（IMPLEMENTATION GAP，与 Phase 3 P3-01 重叠） | 否（同一请求的已有字段） | 市场排行、爆款发现 | 零额外 GMGN 调用 |
| **4** | H1/H2 历史快照（活跃度 + rolling 量） | 否 | 爆款发现、详情页 | 积累 ≥7 天后才能做活跃度动量 |
| **5** | 安全语义字段入库 + SafetyGate 硬过滤 | 否 | 市场排行、爆款发现、告警 | 降低假阳性 |
| **6** | H3/H4 筹码与注意力快照 → 聪明钱进场（S6）、注意力领先价格（S4） | 否 | 爆款发现、告警 | 最有"提前量"的信号 |
| **7** | 代币详情页（§16），先接 G/GH/L 数据，N 类数据随快照积累上线 | 否 | 详情页 | — |
| **8** | 告警：S1–S8 + 反证 F1–F3，按回测命中率调阈值 | 否 | 告警 | 需要 4–6 积累的历史回测 |
| **9** | （需你批准）对 `token traders`、`token holders`、`token pool`、Kline 1h 分辨率做**一次性 raw 验证** | **是**（少量请求） | 钱包维度、短周期量 | 唯一可能补齐"unique traders / 1h volume"的路径 |

### 各模块应接入的字段一览

| 模块 | 立即接入 | 积累历史后接入 |
|---|---|---|
| **市场排行** | `price_change_percent1h`、`buys/sells`、`swaps`、Vol/Liq、MC/Liq、日量比、安全 Gate | 24h 量增速、聪明钱增量 |
| **日K 连涨** | 连续放量天数、日量比、新高突破、波动率（全部来自 Kline） | — |
| **爆款发现** | S1、S2、S3、S7、S8 | S4、S5、S6 |
| **代币详情页** | §16 的 G / GH / L 项 | §16 的 N 项 |
| **告警** | S1、S3、S8 + F1 | S4、S6 + F2、F3 |

---

## Appendix A — IMPLEMENTATION GAP 记录（只记录，不修）

| ID | 现象 | 来源 |
|---|---|---|
| GAP-1 | Trenches `volume_24h/swaps_24h` 未映射到通用写入器读取的 `volume/swaps` | Phase 3 P3-01 |
| GAP-2 | Signal `cur_data.holder_count` / `top_10_holder_rate` 未映射 | Phase 3 P3-01 |
| GAP-3 | 通用 snapshot UPSERT 用缺失值覆盖其他源写入的值 | Phase 3 P3-01 |
| GAP-4 | `smart_degen_count` 等 6 个字段已入库但 API 不读 | 本轮 HEAD 代码检查 |
| GAP-5 | `discovery_event.rank` 已有历史但 API/UI 不读 | 本轮只读查询 |
| GAP-6 | Security 只保存 16 位 hash | Phase 3 P3-06 |
| GAP-7 | Kline `volume` 已由 API 返回但 UI 不显示；`amount` 不返回 | Phase 3 |
| GAP-8 | `volume_24h` / `market_cap` 在 UI 上加 `$`，payload 未编码币种 | Phase 3 P3-04 |

> 注：工作区中存在一组未部署的 Phase 4 修改（针对 GAP-1/2/3/6/8 等）。本文按 HEAD 生产代码
> 描述现状，未依赖、也未改动这些修改。

## Appendix B — 本地已有历史（只读查询，2026-10-03 约 02:15 UTC）

| 表 | 内容 | 范围 |
|---|---|---|
| `token_candle` | 日K OHLCV + amount + fetched/finalized | 2026-06-24 起；1,623 token；46,502 根；每 token 中位 3 根、P90 101 根 |
| `hourly_price` | 小时价格 | 2026-08-30 起；13,074 token；313,087 点 |
| `discovery_event` | 每源每 5 分钟桶：rank（T/H）、price、liquidity、market_cap、metadata（含 holder_count、trench 阶段、signal_type） | 2026-10-02 04:47Z 起；trending 42,467、hot 30,042、trenches 67,886、signal 9,751 |
| `daily_metrics` | 物化 streak / 2·3·5 日收益 | 当前值，非历史 |
| `token_snapshot` | 当前快照（会被覆盖） | 非历史 |

---

# Part II — 按产品模块的验收视图

通用说明（适用于本部分所有表）：

- **链验证**：S = SOL，R = ROBINHOOD，B = BASE，E = ETH。Signal 只有 S/R（生产对 B/E 标记 unsupported）。
- **完整度**：引用 Phase 2 记录的"有值/总行（0 值数）"；`key 100%/分布未记录` 表示 key 在全部行存在，但 Phase 2 没有记录值分布，**可靠性 = UNKNOWN**，需在接入后先观察分布再进正式指标。
- **生产适用**：`YES` = 可进正式指标；`YES*` = 可进，但必须带单位/口径标注；`OBSERVE` = 先入库观察分布，不进正式排序；`NO` = 只展示或不接。
- 路径缩写：T = `data.rank[]`（Trending），H = `[0].tokens[]`（Hot-searches），Tr = `<bucket>[]`（Trenches），S = Signal 根对象，K = `list[]`（Kline），Sec = Security 根对象。
- **[事实] 覆盖面限制：** 生产 `token_candle` 只有 **1,623** 个 token 有日K，而注册表约 **13.9k** 个 token（只读查询）；每个 token 日K 根数中位数 **3**、P90 **101**。依赖日K 的模块（2、3 的确认层、4 的图表）当前只覆盖约 12% 的 token。

---

## 19. 模块 1：市场排行

### 19.A 可以直接使用的 GMGN 字段

| 指标 | Endpoint · 路径 | 含义 | 时间窗口 | 链验证 | 完整度 | 生产适用 |
|---|---|---|---|---|---|---|
| 当前价格 | T/H `.price`；Tr `.price` | 快照价，币种未编码 | 当前快照 | SRBE | T 400/400、H 259/259；Tr 633/633（0 值 115） | YES* |
| 24h 涨跌 | T/H `.price_change_percent` | GMGN 计算的涨跌 | T：请求 `--interval 24h`；H：外层 `interval="24h"`；payload 字段本身未标注 | SRBE | key 100%/分布未记录 | YES*（标"滚动，非日K"） |
| 1h 涨跌 | T/H `.price_change_percent1h` | 字段名表示 1h | 1h（滚动方式 UNKNOWN） | SRBE | key 100%/分布未记录 | OBSERVE → YES |
| 24h 成交量 | T/H `.volume`；Tr `.volume_24h` | 24h 成交量，币种未编码 | 24h rolling | SRBE | T/H 全行；Tr 633/633（0 值 140） | YES*（不加 `$`） |
| 24h 交易笔数 | T/H `.swaps`；Tr `.swaps_24h` | **笔数**，= buys + sells | 24h rolling | SRBE | T/H 全行；Tr 633/633（0 值 130） | YES |
| 24h 买/卖笔数 | T/H `.buys` `.sells`；Tr `.buys_24h` `.sells_24h` | **笔数**，不是买家/卖家数 | 24h rolling | SRBE | T/H 全行；Tr 0 值 155 / 252 | YES |
| 流动性 | T/H/Tr `.liquidity`；S `.cur_data.liquidity` | 快照，币种未编码 | 当前快照 | SRBE（S 仅 SR） | T/H 全行；Tr 0 值 209；S 0 值 7 | YES* |
| 市值 | T/H/Tr `.market_cap` | 快照，币种未编码 | 当前快照 | SRBE | 全行；Tr 0 值 115 | YES* |
| 持币地址数 | T/H/Tr `.holder_count`；S `.cur_data.holder_count` | 当前持币地址数，非历史 | 当前快照 | SRBE（S 仅 SR） | 全行；Tr 0 值 21 | YES（只做当前值） |
| 榜单名次 | T/H `.rank` | 本次请求内名次 | 排名 | SRBE | key 100%；生产已存 T 42,467 / H 30,042 事件 | YES |
| 币龄 | T/H `.creation_timestamp`；Tr `.created_timestamp` | Unix 秒 | 事件时间 | SRBE | 全行 | YES |
| 聪明钱计数 | T/H `.smart_degen_count`；`.renowned_count` | GMGN 标注的聪明钱/知名钱包**数量** | 当前快照（窗口 UNKNOWN） | SRBE | key 100%/分布未记录 | OBSERVE |

### 19.B 需要计算的指标

| 最终指标 | 原始字段 → 计算方法 | 现在能算 |
|---|---|---|
| N 日涨幅 | K `.close` → 仅用 FINALIZED 且连续的 bar，`close_d0 / close_d−N − 1` → `changeNd` | **能**（已实现） |
| 买卖方向 | `buys`, `sells` → `buys / (buys + sells)` → 笔数买入占比 | 接入后能 |
| 交易活跃度 | `swaps`（同链内百分位）→ 活跃度名次 | 接入后能 |
| 周转率 | `volume`, `liquidity` → `volume / liquidity` → 周转率 | 能（单位假设：两者同币种） |
| 新币榜 | `creation_timestamp` → `now − created` ≤ X 小时且 `liquidity ≥ L_min` → 新币名次 | 能 |
| 热度 | `discovery_event.rank` → 窗口内在榜时长、最好名次、Δrank → 热度分 | 能（历史已在库） |
| 参与者增长 | `holder_count` 的固定频率快照 → `Δholders / Δt` | **需新增快照**（现有只在上榜时记录） |
| Smart Money 增长 | `smart_degen_count` 快照 → Δcount | 需新增快照 + 先验证分布 |

### 19.C GMGN 没有的数据

unique traders、buyer/seller 数、active wallets、新钱包数 → **GAP**。
"参与者增长"只能用 `holder_count` 的变化近似，并且必须标注为"持币地址数变化"，**不能**叫"交易者增长"。

### 19.D Market Ranking Recommended Schema [建议]

`chain, address, symbol, created_at, price, pc_24h, pc_1h, volume_24h, swaps_24h, buys_24h, sells_24h, liquidity, market_cap, holder_count, trending_rank, hot_rank, rank_delta_1h, buy_ratio, vol_liq_ratio, change_nd, streak, smart_degen_count (OBSERVE), per-field source + observed_at`

---

## 20. 模块 2：日K 连涨

### 20.A GMGN Kline 真正提供什么 [事实]

| 字段 | 路径 | 含义 | 窗口 | 链验证 | 完整度 | 生产适用 |
|---|---|---|---|---|---|---|
| bar 开盘时间 | K `.time` | Unix **毫秒**，UTC 00:00 对齐，步长 86,400,000 | 日K | SRBE | 120/120 | YES |
| OHLC | K `.open/.high/.low/.close` | 数字字符串，币种未编码 | 日K | SRBE | 120/120，无空串 | YES |
| 日成交量 | K `.volume` | 数字字符串，单位未编码 | 日K | SRBE | 120/120（生产库全部非空非零） | YES（同 token 内比较） |
| `amount` | K `.amount` | 与 volume 不同的数量，含义 UNKNOWN | 日K | SRBE | 120/120；生产库 4,788 行 NULL | NO（只存原始值） |
| finalized 标记 | — | **不存在** | — | — | — | 必须本地推导 |

只验证了 `--resolution 1d` 和约 100 日的范围。**Kline 不提供**笔数、买卖、持币、流动性、市值。

### 20.B 必须本地计算的指标

| 最终指标 | 原始字段 → 方法 | 注意 |
|---|---|---|
| 1D / 3D / 7D / 14D / 30D return | `close` → FINALIZED 且连续，`close_d0/close_d−N − 1` | 缺 bar 或尾部 PROVISIONAL → NULL；30D 需要 ≥31 根，中位 token 只有 3 根 |
| 连续上涨天数 | `close` → 尾部连续 `close_d > close_d−1` | 已实现；<2 根相邻 → NULL，平/跌 → 0 |
| 日成交量 | `volume` → 直接展示 | 单位未知，只能同 token 内比较 |
| 连续放量 | `volume` → 尾部连续 `vol_d > vol_d−1` 的天数 | 算法与 streak 相同 |
| 量比 | `volume` → `vol_d0 / mean(vol_d−7..d−1)` | 可用 bar 不足 → NULL |
| 加速上涨 | `close` → `ret_1d(d0) − ret_1d(d−1) > 0`，且最近 3 天中至少 2 天收益递增 | [推导] |
| 过热 | `close/high/volume` → `ret_7d > X`、或 `close / SMA7 > Y`、或 streak ≥ N 且量比回落（量价背离） | 阈值 [建议] 需回测 |

**不要混淆** [事实]：

| 名称 | 来源 | 窗口 |
|---|---|---|
| 当前价格变化（1m/5m/1h） | T/H `price_change_percent{1m,5m,1h}` | 滚动，相对当下 |
| 24h change | T/H `price_change_percent` | 滚动 24h，**不是** UTC 日 |
| 日K close-to-close | K `close_d / close_d−1 − 1` | UTC 日，仅已定稿 bar |
| N 日累计收益 | K `close_d0 / close_d−N − 1` | N 个 UTC 日；**不是**日收益相加 |
| streak | K 连续 close 上升天数 | UTC 日 |

### 20.C GMGN 没有的数据

日级笔数、日级持币、日级流动性、日级市值、finalized 标记 → GAP（或者需要本地日终快照，见 §17 H7）。

### 20.D Daily Metrics Schema [建议]

`chain, address, as_of_date (最后一根 FINALIZED bar), last_status, close, ret_1d, ret_3d, ret_7d, ret_14d, ret_30d, streak, streak_return, streak_drawdown, volume_d0, vol_ratio_7d, vol_up_days, accel_flag, overheat_flag, high_14d_breakout, bars_available, calculated_at`

---

## 21. 模块 3：爆款发现（最重要）

### 21.A 按信号族重新检查

| 信号族 | 信号 | 类型 | 原始字段 | 计算 | 链 | 可靠性 | 角色 |
|---|---|---|---|---|---|---|---|
| **Price acceleration** | 短周期加速 | DIRECT + DERIVED | T/H `price_change_percent1h`, `price_change_percent` | `pc1h − pc24h/24 > 0` | SRBE | 分布 UNKNOWN | SCAN |
| | 6h 涨幅 | DERIVED | 本地 `hourly_price` | `p_now/p_6h − 1` | SRBE | 高（本地） | SCAN |
| | 多周期同步上涨 | DERIVED | `pc5m`, `pc1h`, `pc24h`, `ret_1d` | 四者 > 0 | SRBE | 中 | CANDIDATE 确认 |
| | Breakout | DERIVED | K `close`, `high` | `close ≥ max(high_14d)` | 有日K 的 token | 高 | ALERT 确认 |
| **Volume acceleration** | 日量突增 | DERIVED | K `volume` | `vol_ratio_7d > 2` | 有日K 的 token | 高 | CANDIDATE / ALERT |
| | rolling 量加速 | DERIVED | T/H `volume`，Tr `volume_24h` 的快照 | `vol24_now / vol24_6h_ago` | SRBE | 需快照 | SCAN（快照积累后） |
| | Vol / Liq | DERIVED | `volume`, `liquidity` | 相除 | SRBE | 中（单位假设） | SCAN；也是 F1 反证 |
| **Liquidity expansion** | 流动性增加 | DERIVED | `liquidity` 快照 / `discovery_event.liquidity` | `liq_now / liq_24h_ago` | SRBE | 只在上榜时有观测 | CANDIDATE |
| | 流动性撤出 | DERIVED | 同上 | `liq_now / liq_1h_ago < 0.5` | SRBE | 同上 | ALERT（风险） |
| | 成长倍数 | DERIVED | T/H `initial_liquidity`, `liquidity` | 相除 | SRBE | 分布 UNKNOWN | RESEARCH |
| | Liq / MC | DERIVED | `liquidity`, `market_cap` | 相除 | SRBE | 中 | 过滤 |
| **Attention acceleration** | Signal 触发 | DIRECT | S `signal_type`, `trigger_at` | 事件 | **仅 SR** | 事件真实；类型含义 UNKNOWN | SCAN |
| | Signal 重复触发 | DIRECT + DERIVED | S `signal_times`, `signal_times_by_type` | 差分 | 仅 SR | 中 | CANDIDATE |
| | 信号后涨幅 | DERIVED | S `market_cap`, `first_trigger_mc` | 相除 | 仅 SR | 中（层级不一致） | RESEARCH |
| **Ranking acceleration** | 新进 Trending | DERIVED | `discovery_event` source=trending | 首次 `seen_at` 落在最近 1h | SRBE | 高（已在库） | SCAN |
| | rank 急升 | DERIVED | `discovery_event.rank` | `rank_1h_ago − rank_now ≥ 30`；不在榜按 101 计 | SRBE | 高 | SCAN |
| | 在榜时长 | DERIVED | `discovery_event` | 24h 内的在榜桶数 | SRBE | 高 | CANDIDATE |
| **Search / hotness** | 新进 Hot-search | DERIVED | `discovery_event` source=hot | 首次出现 | SRBE（B/E 仅 32 行，覆盖窄） | 高 | SCAN |
| | `hot_level` / `visiting_count` / `square_mentions` 变化 | DERIVED | T/H 同名字段的快照 | 差分 | SRBE | **语义 UNKNOWN** | OBSERVE（不进 v1） |
| **New listing / trenches** | 阶段跃迁 | DIRECT + DERIVED | Tr bucket（已存 `source_variant`） | `new_creation → near_completion → completed` 的用时 | SRBE（E 只有 28/5 行） | 高 | SCAN |
| | 毕业进度速度 | DERIVED | Tr `progress` | Δprogress/Δt | 存在率未记录 | UNKNOWN | OBSERVE |
| | 币龄 | DIRECT | `creation_timestamp` / `created_timestamp` | — | SRBE | 高 | 过滤 |
| **Flow** | 买卖笔数失衡 | DERIVED | `buys`, `sells`（Tr 用 `_24h`） | `buys/(buys+sells)` | SRBE | 高（全行） | SCAN |
| | net buy | 存在但不可靠 | Tr `net_buy_24h` | — | 569/633，公式不可验证 | 低 | NO |
| | smart money | DIRECT（仅计数） | T/H `smart_degen_count`, `renowned_count` | Δcount | SRBE | 分布 UNKNOWN | OBSERVE → CANDIDATE |
| | whale activity | **UNAVAILABLE** | — | — | — | — | GAP |
| **Participants** | holder 增长 | DERIVED | `holder_count` 快照 | Δholders | SRBE | 需固定频率快照 | CANDIDATE（快照后） |
| | trader / buyer / unique / new wallet 增长 | **UNAVAILABLE** | — | — | — | — | GAP |
| **Cross-signal** | 多源共振 | DERIVED | `discovery_event`（trending + hot + signal + trenches） | 6h 内 ≥2 个**不同**来源 | SRBE | 高 | CANDIDATE |

### 21.B SCAN → CANDIDATE → ALERT → RESEARCH [建议]

| 阶段 | 目的 | 输入（只用已验证字段） | 进入条件 |
|---|---|---|---|
| **SCAN**（每 5 分钟，所有发现源行） | 宽口径捕捉异常 | 新进 Trending/Hot、rank 急升、trench 阶段跃迁、Signal 事件、`pc1h` 加速、买卖笔数失衡 > 0.6、Vol/Liq | 任一触发即打标 |
| **CANDIDATE** | 去噪、确认 | SCAN 标记 + 至少 **2 个不同信号族** + SafetyGate（`is_honeypot ≠ true`、`renounced_mint ≠ false`（SOL）、`sell_tax` 不超阈值、`is_wash_trading ≠ true`）+ `liquidity ≥ L_min` | 6h 窗口内满足 |
| **ALERT** | 推送 | CANDIDATE + 一个**持续性**确认：在榜 ≥ 3 个桶，或日K 量比 > 2，或 breakout，或 streak ≥ 2；带冷却与去重 | 每个 token 每类告警每 X 小时最多一次 |
| **RESEARCH** | 人工判断 | 详情页：日K、量比、rank 曲线、Signal 时间线、安全、筹码结构（Top10、dev、bundler、sniper） | — |

**只能展示、不能作为早期信号的字段** [推导]：
- 绝对水平：`price`、`market_cap`、`liquidity`、`holder_count` 的单点值（没有变化就不是"异常"）。
- 慢变量或静态：`total_supply`、`launchpad*`、社交链接、`creator`、`decimals`。
- 语义未知：`hot_level`、`visiting_count`、`square_mentions`、`rug_ratio`、`entrapment_ratio`、`fresh_wallet_rate`。在完成分布观察和回测之前只做展示或观察。
- 不可靠/全零：`net_buy_24h`、`buy/sell_volume_24h`、`new_wallet_volume`、Signal `data.*_{1m,1h,6h,24h}`。
- 风险字段用作 **Gate/过滤**，不是上涨信号。

### 21.C Viral Discovery Feature Set v1 [建议]

只使用全行存在、或已在本地历史中的数据：

1. `is_new_trending_1h`、`is_new_hot_1h`、`rank_delta_1h`、`time_on_board_24h`（discovery_event）
2. `trench_stage_transition` 与用时（discovery_event）
3. `signal_event_count_6h`、`distinct_signal_types_6h`（仅 S/R）
4. `buy_ratio_24h = buys/(buys+sells)`（T/H/Tr）
5. `pc_1h`、`accel = pc1h − pc24h/24`（T/H）
6. `ret_6h`（hourly_price）
7. `vol_liq_ratio`（T/H/Tr）
8. `vol_ratio_7d`、`breakout_14d`、`streak`（Kline，覆盖面有限）
9. `cross_source_count_6h`
10. SafetyGate：`is_honeypot`、`renounced_mint`、`renounced_freeze_account`、`sell_tax`、`is_wash_trading`、`liquidity ≥ L_min`

### 21.D Viral Discovery Missing Sensors（需要其他数据源）

| 缺失传感器 | 为什么重要 | 可能来源 |
|---|---|---|
| unique traders / buyers / sellers | 区分"一个人刷单"和"很多人进场" | 链上 swap 日志、DEX 聚合 API；GMGN `token traders` UNVERIFIED |
| 新钱包 / 首次买入钱包数 | 真正的新资金 | 链上数据 |
| 鲸鱼 / 大额交易流 | 早期资金进场 | 链上 swap 明细 |
| smart money 身份与流向 | 现在只有计数，没有是谁、买了多少 | GMGN `track` UNVERIFIED；链上标注库 |
| 1h / 6h 成交量 | 比 24h 更早反映放量 | Signal 字段全为 0；Kline 小周期 UNVERIFIED；DEX API |
| 固定频率的持币历史 | holder 增长 | 自建快照；rhv2 已有 Blockscout 持币快照（独立管线） |
| 社交 / KOL 发帖时间线 | 注意力领先价格 | X / Telegram 数据源 |
| 跨池流动性、quote 侧流动性 | 判断真实深度 | GMGN `token pool` UNVERIFIED；DEX API |

---

## 22. 模块 4：代币详情页

图例：**G** = GMGN 直接提供 · **L** = 本地计算或本地已有历史 · **✗** = 暂时缺失

| 分区（按判断顺序） | 内容 | 来源 |
|---|---|---|
| **1 Overview** | price（G）、market cap（G，标"币种未编码"）、liquidity（G）、24h volume（G）、币龄（G）、FDV 估算 `price × total_supply`（L，标"估算"）、每个值的来源与观测时间（L） | T/H/Tr |
| **2 Momentum** | 1D/3D/7D/14D/30D return（L）、streak（L）、volume trend 与量比（L）、6h return（L）、距 ATH `market_cap / history_highest_market_cap`（G+L） | K、hourly_price、T/H |
| **3 Participation** | holders 当前值（G）；buys/sells **笔数**（G）；买卖笔数比（L）；smart / renowned / sniper / bot **计数**（G，OBSERVE）；holder 曲线（L，有缺口）；traders / unique buyers（**✗，明确显示"GMGN 未提供"**） | T/H/Tr/S |
| **4 Liquidity / Trading Structure** | liquidity、initial_liquidity、Vol/Liq、Liq/MC（G+L）；LP 锁 `lock_summary`、`lock_percent`（G）；Top10、dev、insider、bundler、sniper 持仓（G）；流动性历史（L，有缺口）；多池（✗） | T/H/Tr/Sec |
| **5 Security** | honeypot、mint/freeze、owner、开源、黑名单、税、`privileges`（G）；刷量、仿盘、`rug_ratio`（G，标语义）；安全变化时间线（L，需新增）；mutable metadata（✗） | Sec、T/H/Tr |
| **6 Attention** | Trending/Hot rank 曲线（L）、Signal 时间线（L + 补 `trigger_at/trigger_mc`）、trench 阶段（L）、DexScreener 推广事件（G）、社交链接与粉丝（G）、`hot_level` 等（G，标 UNKNOWN） | discovery_event、T/H/Tr/S |
| **7 History（图表）** | 日K + 量（G 历史）、小时价（L）、rank（L）、liquidity / MC（L，有缺口）、24h 量 / 笔数历史（✗，需快照） | — |

**Token Detail Recommended Schema [建议]：** 复用 §19.D 的排行字段 + §20.D 的日指标，再加：
`initial_liquidity, total_supply, history_highest_market_cap, top_10_holder_rate, dev_team_hold_rate, bundler_rate, sniper_count, renowned_count, security{is_honeypot, renounced_mint, renounced_freeze_account, is_renounced, is_open_source, buy_tax, sell_tax, privileges, lock_summary, observed_at, raw_json}, socials{twitter, website, telegram}, launchpad_platform, creator`，
以及时间线视图：`rank_history`、`signal_events`、`trench_stages`、`daily_kline`、`hourly_price`。

---

## 23. 模块 5：告警系统

**适合做变化检测的字段**（不是看板字段）[推导]：`rank` 及进榜/出榜事件、trench bucket 跃迁、Signal `trigger_at` / `signal_times`、`buys/sells`（比率）、`price_change_percent1h`、Kline `volume` / `close`（定稿后）、`liquidity`（突变）、`market_cap`（越过阈值）、安全字段（状态翻转）、`smart_degen_count`（增量，OBSERVE）。

| Alert | Required fields | Trigger logic | GMGN support | 缺口 |
|---|---|---|---|---|
| 市值首次突破阈值 | `market_cap` | 上一次观测 < M 且本次 ≥ M；每个阈值只触发一次 | DIRECT | 币种未编码；观测只在上榜时 |
| 24h 量急剧放大 | `volume`（快照） | `vol24_now / vol24_6h_ago > 3` | DERIVED | 需快照历史 |
| 日量放大（定稿） | K `volume` | 新 FINALIZED bar 的 `vol_ratio_7d > 3` | DERIVED | 日K 覆盖约 12% 的 token |
| 1h 量急剧放大 | — | — | **UNAVAILABLE** | Signal 全 0；GAP |
| 流动性快速增加 | `liquidity` | `liq_now / liq_24h_ago > 2` 且 `≥ L_min` | DERIVED | 观测有缺口 |
| 流动性突然撤走（风险） | `liquidity` | `liq_now / liq_1h_ago < 0.5` | DERIVED | 同上 |
| 连涨 N 天 | K `close` | 新 FINALIZED bar 使 `streak` 达到 N | DERIVED（已实现） | 覆盖面 |
| N 日涨幅突破 | K `close` | `ret_Nd` 首次 > X | DERIVED（已实现） | 覆盖面 |
| Trending 排名急升 | `discovery_event.rank` | `rank_1h_ago − rank_now ≥ 30`，或首次进入前 20 | DERIVED（历史在库） | — |
| 新进 Hot-search | `discovery_event` source=hot | 首次出现 | DERIVED | B/E 的 Hot 只有 32 行 |
| 多源共振 | `discovery_event` | 6h 内 ≥ 3 个不同来源 | DERIVED | — |
| 买入笔数失衡 | `buys`, `sells` | `buy_ratio > 0.65` 且 `swaps ≥ S_min` | DERIVED | 笔数 ≠ 人数 |
| Trader 数快速增加 | — | — | **UNAVAILABLE** | GAP |
| Holder 数快速增加 | `holder_count` 快照 | `Δholders(6h) / holders > 30%` | DERIVED | 需固定频率快照 |
| Smart-money 活动 | `smart_degen_count` | `Δcount(6h) ≥ 3` | DERIVED（仅计数） | 分布 UNKNOWN；无身份/流向 |
| Signal 触发 | S `signal_type`, `trigger_at` | 新事件（按类型过滤） | DIRECT（仅 S/R） | 类型含义 UNKNOWN |
| Trench 毕业 | Tr bucket | 进入 `completed` | DIRECT（阶段已存） | — |
| 新币首次达到可交易规模 | `liquidity`, `created_at`, Security | 币龄 < 24h 且首次 `liquidity ≥ L_min` 且通过 SafetyGate | DERIVED | 安全字段需接入 |
| 安全状态恶化 | Security 字段 | 任一风险字段由安全变为风险 | DERIVED | 需存安全变化日志 |

---

## 24. 最终字段接入表

优先级：**P0** 现在就接 · **P1** 第二阶段 · **P2** 补充展示 · **GAP** GMGN 无法提供。
当前可用性：`在用` = 生产已用于 UI/API · `已存未用` = 已入库但未使用 · `同次响应已返回` = collector 已请求，字段被丢弃 · `需快照` = 需要新增本地历史 · `UNVERIFIED` · `—`。

| 产品模块 | 指标 | GMGN endpoint | 原始字段 | 直接/计算 | 优先级 | 当前可用性 |
|---|---|---|---|---|---|---|
| 排行 | 价格 | T/H/Tr | `price` | 直接 | P0 | 在用 |
| 排行 | 24h 涨跌 | T/H | `price_change_percent` | 直接 | P0 | 在用 |
| 排行 | 1h 涨跌 | T/H | `price_change_percent1h` | 直接 | P0 | 同次响应已返回 |
| 排行 | 24h 成交量 | T/H · Tr | `volume` · `volume_24h` | 直接 | P0 | T/H 在用；Tr 被丢弃（GAP-1） |
| 排行 | 24h 笔数 | T/H · Tr | `swaps` · `swaps_24h` | 直接 | P0 | T/H 已存未用；Tr 被丢弃 |
| 排行 / 发现 | 买卖笔数 | T/H · Tr | `buys`,`sells` · `buys_24h`,`sells_24h` | 直接 | P0 | 同次响应已返回 |
| 排行 / 发现 | 买入占比 | 同上 | `buys`,`sells` | 计算 | P0 | 字段接入后可算 |
| 排行 | 流动性 | T/H/Tr/S | `liquidity` · `cur_data.liquidity` | 直接 | P0 | 在用 |
| 排行 | 市值 | T/H/Tr | `market_cap` | 直接 | P0 | 在用 |
| 排行 | 持币地址数 | T/H/Tr · S | `holder_count` · `cur_data.holder_count` | 直接 | P0 | 在用；S 被丢弃（GAP-2） |
| 排行 / 发现 / 告警 | 榜单名次 | T/H | `rank` | 直接 | P0 | 已存未用 |
| 发现 / 告警 | rank 变化、新进榜、在榜时长 | T/H | `rank` + 事件时间 | 计算 | P0 | 历史已在库 |
| 排行 / 发现 | 币龄 | T/H · Tr · S | `creation_timestamp` · `created_timestamp` · `data.created_timestamp` | 直接 | P0 | 在用（registry） |
| 发现 / 告警 | trench 阶段跃迁 | Tr | bucket 名 | 直接 + 计算 | P0 | 历史已在库 |
| 发现 / 告警 | Signal 事件 | S | `signal_type` | 直接 | P0 | 历史已在库（仅 S/R） |
| 发现 / 告警 | Signal 时间 / 触发市值 | S | `trigger_at`, `trigger_mc`, `first_trigger_mc` | 直接 | P1 | 同次响应已返回 |
| 发现 / 告警 | 重复触发 | S | `signal_times`, `signal_times_by_type` | 直接 + 计算 | P1 | 同次响应已返回 |
| 连涨 | N 日收益、streak | K | `close`, `time` | 计算 | P0 | 在用 |
| 连涨 / 发现 / 告警 | 日量比、连续放量 | K | `volume` | 计算 | P0 | 已存，API 返回，UI 未用 |
| 连涨 / 发现 | breakout、加速、过热 | K | `high`, `close`, `volume` | 计算 | P0 | 已存 |
| 连涨 | 30D 收益 | K | `close` | 计算 | P1 | 多数 token 根数不足 |
| 连涨 | `amount` | K | `amount` | 直接 | P2（只存原始值） | 已存未用 |
| 发现 | 6h 收益 | 本地 | `hourly_price` | 计算 | P0 | 历史已在库 |
| 发现 | 短周期加速 | T/H | `price_change_percent1h`, `price_change_percent` | 计算 | P0 | 同次响应已返回 |
| 发现 | 5m 涨跌 | T/H | `price_change_percent5m` | 直接 | P1（实时，不进正式指标） | 同次响应已返回 |
| 发现 | Vol/Liq、Liq/MC | T/H/Tr | `volume`, `liquidity`, `market_cap` | 计算 | P0 | 现在能算 |
| 发现 / 告警 | rolling 量加速 | T/H/Tr | `volume` 快照 | 计算 | P1 | 需快照 |
| 发现 / 告警 | 流动性扩张 / 撤出 | T/H/Tr | `liquidity` 快照 | 计算 | P1 | 只在上榜时有观测；需快照 |
| 发现 / 告警 | holder 增长 | T/H/Tr | `holder_count` 快照 | 计算 | P1 | 需快照 |
| 发现 / 告警 | 聪明钱计数增量 | T/H | `smart_degen_count`, `renowned_count` | 计算 | P1（先观察） | 部分已存未用；分布 UNKNOWN |
| 发现（Gate） | 刷量 | T/H/Tr | `is_wash_trading` | 直接 | P0 | 同次响应已返回 |
| 发现（Gate） / 详情 | honeypot / mint / freeze / 卖出税 | Sec（T/H 也有） | `is_honeypot`, `renounced_mint`, `renounced_freeze_account`, `sell_tax` | 直接 | P0 | 只存 hash（GAP-6） |
| 详情 | 其他安全字段 | Sec | `is_renounced`, `is_open_source`, `is_blacklist`, `buy_tax`, `privileges`, `lock_summary` | 直接 | P1 | 只存 hash |
| 详情 | 筹码结构 | T/H/Tr | `top_10_holder_rate`, `dev_team_hold_rate`, `bundler_rate`, `sniper_count`, `top70_sniper_hold_rate` | 直接 | P1 | 部分已存未用 |
| 详情 | 距 ATH | T/H | `history_highest_market_cap` | 直接 + 计算 | P1 | 同次响应已返回 |
| 详情 | 流动性成长倍数 | T/H | `initial_liquidity` | 直接 + 计算 | P2 | 同次响应已返回 |
| 详情 | FDV 估算 | T/H/Tr/S | `total_supply` × `price` | 计算 | P2 | 同次响应已返回 |
| 详情 | 社交 / launchpad / 创建者 | T/H/Tr | `twitter_username`, `website`, `telegram`, `launchpad_platform`, `creator` | 直接 | P2 | 部分进 META |
| 详情 | 创建者画像 | Tr | `creator_created_count`, `creator_created_open_ratio`, `creator_balance_rate` | 直接 | P2 | 同次响应已返回 |
| 详情 / 观察 | 热度字段 | T/H | `hot_level`, `visiting_count`, `square_mentions` | 直接 | P2（OBSERVE） | 语义 UNKNOWN |
| 详情 | DexScreener 推广 | T/H | `dexscr_*`, `*_ts` | 直接 | P2 | 同次响应已返回 |
| 详情 | 社交增长 | Tr/S | `x_user_follower`, `tg_call_count`, `callout_count` | 直接 | P2 | 存在率未记录 |
| — | 买/卖成交额 | Tr | `buy_volume_24h`, `sell_volume_24h`, `net_buy_24h` | — | 不接 | 稀疏，公式不可验证 |
| — | 短周期活跃度 | S | `data.volume/swaps/buys/sells/net_buy_{1m,1h,6h,24h}` | — | 不接 | 全部为 0 |
| — | 新钱包 | Tr/S | `new_wallet_volume`, `fresh_wallet_rate` | — | 不接（rate 只做 P2 展示） | 全 0 / 语义 UNKNOWN |
| 排行 / 发现 / 告警 | unique traders / buyers / sellers | — | — | — | **GAP** | `token traders` UNVERIFIED |
| 排行 / 发现 / 告警 | active / new wallets | — | — | — | **GAP** | — |
| 发现 / 告警 | 1h / 6h 成交量 | — | — | — | **GAP** | Kline 小周期 UNVERIFIED |
| 发现 | whale / smart money 流向 | — | — | — | **GAP** | `track` UNVERIFIED |
| 排行 / 详情 | holder 历史（GMGN 原生） | — | — | — | **GAP**（只能自建快照） | — |
| 详情 | 流通量、多池流动性 | — | — | — | **GAP** | `token pool` UNVERIFIED |
| 详情 | mutable metadata | — | — | — | **GAP** | — |

---

## 25. V1 最小字段集合 [建议]

目标：用最少的字段打通 **发现爆款 → 排名 → 连涨 → 详情 → 告警**。
原则：**不新增任何 GMGN 请求**，只取 collector 已请求的响应中的字段，再加上本地已有的历史。

### 25.1 已在库，只需要计算 / API 化（0 采集改动）

| 字段 | 用途 |
|---|---|
| `discovery_event.rank`、`source`、`source_variant`（trench 阶段 / signal 类型）、`seen_at` | 新进榜、rank 急升、在榜时长、trench 跃迁、Signal 事件、多源共振 |
| `token_candle.close/high/volume/time` + finalized 契约 | N 日收益、streak、日量比、连续放量、breakout |
| `hourly_price.price` | 6h 收益 |
| `token_snapshot.price/pc_24h/volume_24h/liquidity/market_cap/holders` | 排行与详情基础 |

### 25.2 需要新接入 collector 和数据库（同一请求，零额外调用）——共 12 个字段

| # | 字段 | Endpoint | 支撑的闭环环节 |
|---|---|---|---|
| 1 | `buys` / `buys_24h` | T/H · Tr | 发现（失衡）、排行、告警 |
| 2 | `sells` / `sells_24h` | T/H · Tr | 同上 |
| 3 | `swaps_24h`（Trench 映射） | Tr | 排行、发现 |
| 4 | `volume_24h`（Trench 映射） | Tr | 排行、发现 |
| 5 | `price_change_percent1h` | T/H | 发现（加速）、排行 |
| 6 | `is_wash_trading` | T/H/Tr | SafetyGate |
| 7 | `trigger_at` | S | 告警、回测 |
| 8 | `trigger_mc` | S | 详情、回测 |
| 9 | `is_honeypot` | Sec | SafetyGate |
| 10 | `renounced_mint` | Sec | SafetyGate（SOL） |
| 11 | `renounced_freeze_account` | Sec | SafetyGate（SOL） |
| 12 | `sell_tax` | Sec | SafetyGate（刻度待确认） |

**历史化：** 把 #1–#5 连同 `holder_count`、`liquidity` 写入每次发现事件的紧凑元数据（§17 H2）。这样不用新建表，也能积累 rolling 量、笔数、持币、流动性的变化历史。

### 25.3 刻意不进 V1

`smart_degen_count` 等聪明钱计数（先观察分布 → P1）、`hot_level` / `visiting_count` / `square_mentions`（语义 UNKNOWN）、`price_change_percent5m/1m`（只做实时）、筹码结构与其余安全字段（详情页，P1）、`total_supply` / `initial_liquidity` / `history_highest_market_cap`（P1/P2）、所有稀疏、全零或公式不明的字段。

> 注：#3、#4、`cur_data.holder_count` 以及安全语义字段，与工作区里未部署的 Phase 4 修改有重叠。本文不评估、也不依赖那组修改。

---

# Part III — 语义修订（2026-10-03，依据 `gmgn-field-dictionary.md`）

> Part I / II 原文保留。下表中的修订**优先于** Part I / II 中的相应描述。
> 依据：15 份新的真实 raw（`raw/v1/`），以及与 DexScreener、本地小时价、日 K 的定量比对。

## 26. 被推翻或补全的结论

| 原描述（Part I / II） | 修订 | 证据 |
|---|---|---|
| Kline `volume` 单位 UNKNOWN，`amount` 含义 UNKNOWN | `volume` = **USD 成交额**；`amount` = 代币数量（INFERRED）。vendor 文档写反了 | `volume / amount / close` 中位数 1.0015；Trending 24h volume / 日 K volume = 0.99 |
| Kline `time` 为毫秒（Phase 2） | 维持：**毫秒**；vendor 文档写秒是错的 | raw 120 / 120 |
| price / volume / liquidity / market_cap 币种未编码 | price、volume、market_cap = **USD**（已独立验证）；liquidity 量级为 USD，但口径 **NEEDS_CONFIRMATION** | DexScreener 比值 1.000 / 1.10 / 0.9999 |
| `price_change_percent` 的窗口 UNKNOWN | **百分数**（25 = +25%），窗口 = 请求的 `--interval`；`price_change_percent1h` 为 1h 百分数 | 与本地小时价比对，误差中位数 0.6% / 0.9% |
| FDV 不存在，只能自己算 | `market_cap` **本身就是 `price × total_supply`（FDV 口径）**；流通市值不提供 | 99.3% / 100% 精确相等 |
| Hot-searches 的 rank：注意力 | rank = **本次请求列表内的位置**；不按 `visiting_count` 排序（文档说法被 raw 否定），排序算法 UNKNOWN | 相邻行单调性约 50 / 50 |
| `smart_degen_count` 等可做"聪明钱进场"信号 | 定义（持有还是交易）与窗口 **NEEDS_CONFIRMATION**；Trenches 中 BASE 全 0 | §3.6 |
| 发现源中的 `bundler_rate`、`rat_trader_amount_rate`、`bot_degen_*`、`rug_ratio` 可做风控 | BASE / ETH（以及部分 RH）**整列为 0**，0 ≠ 无风险 | §6 |
| `signal_type` 含义 UNKNOWN | vendor 文档给出了映射（6 = 价格急涨、7 = ATH、12 = 聪明钱买入……），但触发条件未确认 → 只存代码，含义标"文档定义" | `gmgn-market/SKILL.md` |
| 同名字段可按名字合并 | **禁止**：`is_honeypot`、`renounced_mint`、`open_source`、`liquidity`、`market_cap`、`holder_count` 在不同 endpoint / 层级的语义或类型不同 | §4 |

## 27. 对 Part II 的修订

### 27.1 SafetyGate（§21.B / §25）

原 SafetyGate 使用 `is_honeypot`、`sell_tax`、`is_wash_trading`。这三个字段现在都是 **BLOCKED_BY_SEMANTICS**：

- `is_wash_trading`：1,163 行全部为 false，无法区分"检测为否"与"未检测"。
- `is_honeypot`（Security）：从未观察到 true；RH / ETH 的 false 是否经过检测未确认；SOL 为 null。
- `sell_tax`（Security）：只观察到 "0"；Trending 中 SOL 为 `""`。

修订后的 SafetyGate v1 只能使用：

- SOL：`renounced_mint`、`renounced_freeze_account`（Security，true = 已放弃）；EVM 一律视为 NOT_APPLICABLE。
- 正向风险标记：任一来源出现 `is_honeypot = true` / `is_wash_trading = true` 时**可以**拦截（true 的含义清楚），但 false / 0 / null **不能**作为"安全"的证据。

### 27.2 流动性相关指标

以下指标暂停，直到 §5 的口径确认：

- Vol / Liq、Liq / MC
- 流动性扩张、撤出
- 最低流动性门槛**跨 endpoint 统一**（同一 endpoint 内比较仍可展示）

### 27.3 V1 字段集合（§25）

| 字段 | 新状态 |
|---|---|
| buys、sells、swaps_24h、volume、price_change_percent1h、trigger_at、trigger_mc | SAFE |
| renounced_mint、renounced_freeze_account | SAFE（仅 SOL） |
| is_wash_trading、is_honeypot、sell_tax | **BLOCKED_BY_SEMANTICS**：原值可以存储，但不得用于过滤、评分或"安全"标记 |
| liquidity（V1 之前已存在） | **BLOCKED**：只能按 endpoint 分开展示 |

完整的 SAFE / BLOCKED 字段集见 `gmgn-field-dictionary.md` §10 / §11。

## 28. 修订后的模块能力（只使用 SAFE 字段）

见 `gmgn-field-dictionary.md` §13。主要变化：

- 爆款发现：去掉 Vol / Liq、流动性扩张、聪明钱、刷量过滤；保留 pc1h 加速度、买卖笔数比、rank 变化、trench 阶段、signal 事件、日 K 成交额放大。
- 告警：去掉流动性告警与安全恶化告警。
