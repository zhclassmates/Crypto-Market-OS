# GMGN Field Dictionary + Semantics Audit

> 本轮只做字段语义。没有写业务代码，没有 deploy / restart，没有 commit。
> 每个结论都标注证据等级。证据不足的写 `UNKNOWN` 或 `NEEDS_CONFIRMATION`，不按字段名猜。

## 结论

**FIELD SEMANTICS: PARTIAL**

- 价格、成交量、市值、交易笔数、时间戳、K 线 OHLCV、榜单名次、Signal 触发时间与触发市值：含义、单位、时间窗口都已用**独立数据**验证（见 §2）。
- 未达到 READY 的原因：
  - `liquidity` 在不同 endpoint 之间有未解释的冲突；
  - 多个安全 / 风控字段的 `false` / `0` 无法区分"已检测且安全"与"未检测 / 不适用"；
  - `signal_type` 的含义只来自 vendor 文档；
  - 若干比例字段超出 0–1；
  - 若干字段在部分链上整列为 0。

完整清单见 §14。

## 0. 证据等级

| 标记 | 含义 |
|---|---|
| **VERIFIED_BY_RAW** | 由真实 raw，或 raw 与独立数据源的定量比对证实 |
| **VERIFIED_BY_DOCS** | 只有 vendor 文档（gmgn-cli 1.6.6 自带 skill 文档）说明，raw 与之不矛盾但没有独立验证 |
| **VERIFIED_BY_BOTH** | 文档与 raw / 独立比对一致 |
| **INFERRED** | 由数据关系推出，没有直接证据 |
| **UNKNOWN** | 证据不足 |
| **NEEDS_CONFIRMATION** | 证据之间有冲突，或关键语义（如 false / 0 的含义）未能区分 |

## 1. 证据来源

| 来源 | 内容 | 用途 |
|---|---|---|
| 真实 raw（`raw/v1/`，2026-10-03 10:52–11:48 CST） | 四链 Trending（各 100 行，`--interval 24h`）、SOL Hot（98 行）、四链 Trenches（180 / 180 / 180 / 125 行）、SOL / RH Signal（各 50 条）、四链 Security（各 1 个 token） | 字段存在性、类型、null / 0 率、示例 |
| Phase 2 字段矩阵（2026-10-02） | 四链 Kline（120 根）、四链 Hot（259 行）以及其余 endpoint 的第一次采样 | Kline 与 Hot 的四链证据，以及第二次采样对照 |
| vendor 文档 | `/opt/homebrew/lib/node_modules/gmgn-cli/skills/gmgn-market/SKILL.md`、`gmgn-token/SKILL.md` | **候选**含义；只在独立数据支持时采纳 |
| 独立数据（生产库只读） | `token_snapshot.price_ds / volume_ds / liquidity_ds`（DexScreener，USD）；`hourly_price`（本地每小时价格）；`token_candle`（日 K） | 验证单位与时间窗口 |
| 结果文件 | `raw/v1/field_inventory.json`、`semantics_tests.json`、`liquidity_discrepancy.json` | 可复核 |

### 1.1 vendor 文档与 raw 冲突（raw 优先）

| 文档说法 | raw / 独立验证 | 结论 |
|---|---|---|
| Kline `time` 是 Unix **秒** | 120 根全部是 13 位**毫秒**，UTC 00:00 对齐（Phase 2） | 文档错 |
| Kline `volume` = 基础代币数量，`amount` = USD | `volume / amount / close` 中位数 **1.0015**（n=5,000）；Trending 24h `volume` / 日 K `volume` = 0.99，/ `amount` = 0.015 | **相反**：`volume` 是 USD，`amount` 是代币数量（INFERRED） |
| Hot-searches 按 `visiting_count` 排序 | 相邻行 `visiting_count` 降序 49 / 97、升序 50 / 97 | 排序依据 **UNKNOWN** |
| `hot_level` 越大越热 | 取值 0–3，ETH 全 0；与 rank 的关系不单调 | 方向 **UNKNOWN** |
| Trenches 返回 `usd_market_cap` | 665 行中出现 0 次 | 字段在本次 payload 中不存在 |
| Security `is_honeypot` / `open_source` / `owner_renounced` 是 `"yes"` / `"no"` 字符串 | `is_honeypot` 是 boolean / null；`open_source` 是数字；`owner_renounced` 不在 Security 中（只在 Trenches 中） | 文档的类型描述不可信 |
| `top_10_holder_rate` 等比例在 0–1 之间 | Trending 中 `top_10_holder_rate` 最大 2.10，`entrapment_ratio` 2.21，`bluechip_owner_percentage` 1.43 | 范围不成立，**NEEDS_CONFIRMATION** |

## 2. 关键定量验证（`raw/v1/semantics_tests.json`）

| 问题 | 方法 | 结果 | 结论 |
|---|---|---|---|
| `price` 单位 | Trending `price` / DexScreener `price_ds` | 中位数 **1.000**，98.8% 在 0.5–2 倍内（n=400） | USD（VERIFIED_BY_BOTH） |
| `liquidity` 单位 | Trending `liquidity` / `liquidity_ds` | 中位数 **0.9999**，80.6% 在 0.5–2 倍内（n=396） | 量级上是 USD；跨 endpoint 定义见 §5 |
| 24h `volume` 单位与窗口 | Trending `volume` / DexScreener 24h `volume_ds` | 中位数 **1.10**，75% 在 0.5–2 倍内 | USD、24h（VERIFIED_BY_BOTH） |
| `price_change_percent1h` 是百分数还是比例 | 用 raw 推算 1h 前价格，与本地 `hourly_price` 比对 | 按百分数解释：中位误差 0.9%，91% 在 15% 内；按比例解释：25% | **百分数**，`25` = +25%；窗口 1h（VERIFIED_BY_BOTH） |
| `price_change_percent` 窗口 | 同上，分别对比 24h 前和 1h 前的价格 | 24h 前：中位误差 0.6%（93.5%）；1h 前：9.8% | 百分数，窗口 = 请求的 `--interval`（本次 24h）（VERIFIED_BY_BOTH） |
| `market_cap` 计算方式 | `market_cap / (price × total_supply)` | Trending 99.3%、Hot 100% 等于 1 | **按总供应量计算**（FDV 口径），不是流通市值（VERIFIED_BY_RAW） |
| 活跃度字段窗口 | ETH 3 个 token：Trending（24h）`swaps / buys / sells / volume` 与 Trenches `*_24h` 比值 | 全部 **1.000** | 24h（VERIFIED_BY_RAW）；BASE 2 个 token 1.07–1.12（相隔 7.5 分钟） |
| Hot 与 Trending 是否同口径 | SOL 52 个共同 token，相隔 47 分钟 | `swaps` 1.002、`volume` 1.002、`holder_count` 0.997 | 同口径 24h |
| Kline `close` 单位 | 最新日 K `close` / `price_ds` | 中位数 **1.0036**（n=250） | USD |
| Trenches `complete_cost_time` | 与 `complete_timestamp − created_timestamp` 比较 | 151 / 151 完全相等 | 秒，派生字段 |
| Signal `data` 层的时点 | `trigger_mc` 与 `data.market_cap` 比较 | 100 / 100 相等；顶层 `market_cap` 与 `trigger_mc` 只有 18 / 100 相等 | `data` 是**触发时快照**，顶层 `market_cap` 是查询时值 |
| `signal_times` | 与 `sum(signal_times_by_type)` 比较 | 100 / 100 相等 | 各类型累计次数之和 |
| Signal 返回顺序 | `trigger_at` | 两链都严格降序 | 最新在前 |
| `rank` 排序 | 是否 1..N 连续；相邻行是否按某字段单调 | 连续 1..N，返回顺序即 rank；按 swaps / volume / visiting_count / hot_level 都不单调 | 只是**本次响应列表内的位置**，排序算法 UNKNOWN |

## 3. 核心字段字典

列：**Field**（完整路径）｜**中文含义**｜**Raw example**｜**Type**｜**Unit**｜**Window**｜**Chains**｜**证据**

路径缩写：T = `data.rank[]`（Trending），H = `[0].tokens[]`（Hot），Tr = `<bucket>[]`（Trenches，bucket ∈ new_creation / near_completion / completed），S = Signal 根数组元素 `[]`，Sec = Security 根对象，K = `list[]`（Kline）。**同名字段在不同 endpoint 分开列出，不视为同一指标。**

### 3.1 价格与涨跌

| Field | 中文含义 | Raw example | Type | Unit | Window | Chains | 证据 |
|---|---|---|---|---|---|---|---|
| `T.price` / `H.price` | 当前价格 | `0.00134326` | float | USD | snapshot（采集时刻） | SOL RH BASE ETH | VERIFIED_BY_BOTH |
| `Tr.price` | trench 行当前价格 | `0.0002832896` | float | USD（与 T 同 token 比值 1.000） | snapshot | 四链；0 值 117 / 665 行 | VERIFIED_BY_RAW（单位）；0 值含义 UNKNOWN |
| `T.price_change_percent` / `H.…` | 请求窗口内的价格涨跌 | `13.2015` = +13.2% | float，可负 | **百分数** | = 请求的 `--interval`（Hot 外层 `interval="24h"`） | 四链 | VERIFIED_BY_BOTH |
| `T.price_change_percent1h` | 近 1 小时涨跌 | `-3.5438` = −3.54% | float，可负 | 百分数 | 1h | 四链 | VERIFIED_BY_BOTH |
| `T.price_change_percent5m` | 近 5 分钟涨跌 | — | float | 百分数（与 1h 同族，INFERRED） | 5m（VERIFIED_BY_DOCS，未独立验证） | 四链 | VERIFIED_BY_DOCS |
| `T.price_change_percent1m` | 近 1 分钟涨跌 | — | float | 同上 | 1m（VERIFIED_BY_DOCS） | 四链 | VERIFIED_BY_DOCS |
| `S.data.price_volatility_rate` | 价格波动率 | — | float | UNKNOWN | UNKNOWN | SOL 5 / 50，RH 9 / 50 | UNKNOWN |
| `T.history_highest_market_cap` | 历史最高市值 | — | float | USD（VERIFIED_BY_DOCS） | lifetime | 四链 | VERIFIED_BY_DOCS |
| `S.ath` | GMGN 标注的 ATH | `2575.57` | float | USD 市值（VERIFIED_BY_DOCS） | lifetime | SOL RH | **NEEDS_CONFIRMATION**：只有 94 / 100 ≥ 当前 `market_cap`，并不总是历史最高 |

正负号：正数 = 上涨，负数 = 下跌（VERIFIED_BY_RAW：按此解释推算出的旧价格与本地历史一致）。Trenches **没有**任何 `price_change_*` 字段。

### 3.2 成交量与成交额

| Field | 中文含义 | Raw example | Type | Unit | Window | Chains | 证据 |
|---|---|---|---|---|---|---|---|
| `T.volume` | 请求窗口内的成交额 | `1279330` | float | **USD** | = 请求的 `--interval`（本次 24h） | 四链 | VERIFIED_BY_BOTH |
| `H.volume` | 同上 | — | float | USD | 外层 `interval`（24h） | SOL（本轮）；四链（Phase 2） | VERIFIED_BY_BOTH |
| `Tr.volume_24h` | 24h 成交额 | `120542.81` | float | USD（与 T 比值 1.000） | 24h | 四链；0 值 159 / 665 行 | VERIFIED_BY_RAW |
| `Tr.buy_volume_24h` / `Tr.sell_volume_24h` | 24h 买入 / 卖出成交额 | `11176.7` | float | UNKNOWN | 24h（字段名） | 部分行出现（SOL 8 / 180）；SOL / BASE 的卖出额全为 0 | **UNKNOWN**（Phase 2：与 `volume_24h` 吻合的只有 9 / 116） |
| `Tr.net_buy_24h` | 24h 净买入 | `0.06` | float | UNKNOWN（文档写"volume"） | 24h | 部分行出现 | **UNKNOWN**（公式无法复现） |
| `S.data.volume_{1m,1h,6h,24h}` | 各窗口成交额 | `0` | number | — | — | SOL RH，**100% 为 0** | 不可用 |
| `K.volume` | 日 K 成交额 | 数字字符串 | numeric-string | **USD**（与文档相反） | 1 根日 K（UTC） | 四链 | VERIFIED_BY_RAW |
| `K.amount` | 日 K 成交数量 | 数字字符串 | numeric-string | **代币数量**（INFERRED：`volume ≈ amount × close`） | 1 根日 K | 四链；生产库 4,788 行 NULL | INFERRED，与文档冲突 |

### 3.3 流动性

| Field | 中文含义 | Raw example | Type | Unit | Window | Chains | 证据 |
|---|---|---|---|---|---|---|---|
| `T.liquidity` / `H.liquidity` | 流动性 | `152132` | float | USD 量级（与 DexScreener 比值 0.9999） | snapshot | 四链 | **NEEDS_CONFIRMATION**：口径（单池还是多池汇总）未知，见 §5 |
| `Tr.liquidity` | 流动性 | `24547.67` | float | USD 量级 | snapshot | 四链；0 值 235 / 665 行 | **NEEDS_CONFIRMATION**：ETH 上与 T 相差 1.23–2.92 倍 |
| `S.cur_data.liquidity` | 查询时流动性 | `38.87` | float | USD（VERIFIED_BY_DOCS） | snapshot（查询时） | SOL RH | VERIFIED_BY_DOCS |
| `S.data.liquidity` | 触发时流动性 | — | float | 同上 | 触发时 | SOL RH | INFERRED（`data` = 触发时快照） |
| `T.initial_liquidity` | 开盘时流动性 | `27204.4` | float | USD（VERIFIED_BY_DOCS） | 开盘时 | 四链；BASE 样本中有 0 | VERIFIED_BY_DOCS |
| `T.lock_percent` | LP 锁定比例 | `0.95` | float | 比例 0–1 | snapshot | RH / BASE / ETH；**SOL 全 0** | VERIFIED_BY_DOCS；SOL 的 0 ≠ 未锁 |

### 3.4 市值与供应

| Field | 中文含义 | Raw example | Type | Unit | Window | Chains | 证据 |
|---|---|---|---|---|---|---|---|
| `T.market_cap` / `H.market_cap` | 市值 = `price × total_supply` | `1319350` | float | USD | snapshot | 四链 | VERIFIED_BY_BOTH（单位）；**计算口径 VERIFIED_BY_RAW：按总供应量（FDV 口径）** |
| `Tr.market_cap` | 同上 | `283289.6` | float | USD（与 T 比值 1.000） | snapshot | 四链 | VERIFIED_BY_RAW |
| `S.market_cap` | 查询时市值 | `2575.57` | float | USD（VERIFIED_BY_DOCS） | 查询时 | SOL RH | VERIFIED_BY_BOTH（与 `trigger_mc` 不同的有 82 / 100） |
| `S.data.market_cap` / `S.data.usd_market_cap` | 触发时市值 | — | float | USD（两者 100 / 100 相等，一个显式标 USD） | 触发时 | SOL RH | VERIFIED_BY_RAW |
| `*.total_supply` | 总供应量 | — | number | 代币数量 | snapshot | T / H / Tr / S | VERIFIED_BY_DOCS；与 market_cap 的关系 VERIFIED_BY_RAW |
| FDV | — | — | — | — | — | — | **GMGN 不提供独立字段**；`market_cap` 本身就是 FDV 口径 |
| 流通量（circulating supply） | — | — | — | — | — | — | **NOT PROVIDED** |

### 3.5 交易活动：交易笔数、钱包数、独立钱包数、交易者数

| 类别 | GMGN 字段 | 结论 |
|---|---|---|
| **交易笔数（transaction count）** | `T.swaps`、`T.buys`、`T.sells`（H 同）；`Tr.swaps_24h`、`Tr.buys_24h`、`Tr.sells_24h` | **存在**。`swaps = buys + sells` 在全部行成立（Phase 2：1,292 行；本轮 T 400 行）。单位：笔。窗口：T / H = 请求的 interval（24h），Tr = 24h。证据：VERIFIED_BY_BOTH |
| 钱包数（wallet count） | — | **NOT PROVIDED** |
| 独立钱包数（unique wallets） | — | **NOT PROVIDED** |
| 交易者数（trader count） | — | **NOT PROVIDED**（`rat_trader_amount_rate`、`bundler_trader_amount_rate` 是成交额比例，不是人数） |
| 独立买家 / 卖家数 | — | **NOT PROVIDED**；`buys` / `sells` 不能替代 |
| 新钱包数 | — | **NOT PROVIDED**；`Tr.fresh_wallet_rate` 是比例（BASE / ETH 全 0），`Tr.new_wallet_volume` 全为 0 |
| `S.data.swaps_* / buys_* / sells_*` | 1m / 1h / 6h / 24h | 存在但 **100% 为 0**，不可用 |

### 3.6 持币与"标签钱包"计数

| Field | 中文含义 | Raw example | Type | Unit | Window | Chains | 证据 |
|---|---|---|---|---|---|---|---|
| `T.holder_count` / `H.holder_count` / `Tr.holder_count` | 当前持币地址数 | `3209` | integer | 地址数 | snapshot | 四链 | VERIFIED_BY_BOTH（跨 endpoint 比值 1.000 / 0.997）。"持币"的余额门槛 UNKNOWN |
| `S.cur_data.holder_count` | 查询时持币地址数 | `2` | integer | 地址数 | 查询时 | SOL RH | VERIFIED_BY_DOCS；与 `S.data.holder_count`（触发时）不同的有 76 / 100 |
| `T.smart_degen_count` | GMGN 标记的"聪明钱"钱包**数量** | `5` | integer | 钱包数 | UNKNOWN（文档："holding or trading"，持有还是交易未定义） | 四链；Tr 中 BASE 全 0 | **NEEDS_CONFIRMATION**（窗口与定义）。**不是资金流** |
| `T.renowned_count` | GMGN 标记的 KOL 钱包数量 | — | integer | 钱包数 | UNKNOWN | 四链 | NEEDS_CONFIRMATION |
| `T.sniper_count` | 狙击钱包数量 | — | integer | 钱包数 | 开盘时（VERIFIED_BY_DOCS） | 四链；Tr 中 BASE / ETH 全 0 | VERIFIED_BY_DOCS |
| `T.bot_degen_count` / `T.bot_degen_rate` | 机器人钱包数量 / 比例 | `715` / `0.3` | int / float | 钱包数 / 比例 | UNKNOWN | SOL RH 有值；**BASE / ETH 全 0** | NEEDS_CONFIRMATION（EVM 上的 0 不等于"没有机器人"） |

### 3.7 Rank

| Field | 是在什么集合里的名次 | 证据 |
|---|---|---|
| `T.rank` | **本次 Trending 请求返回列表中的位置**。集合由链 + `--interval` + `--limit` + 过滤条件决定；1..N 连续，返回顺序就是 rank | VERIFIED_BY_BOTH（文档："Position in this trending list"）。**不是全市场排名。** 排序算法 UNKNOWN（不按任何单个暴露字段单调） |
| `H.rank` | 本次 Hot-searches 请求返回列表中的位置 | VERIFIED_BY_RAW；文档说按 `visiting_count` 排序，但被 raw 否定 |
| `T.hot_level` | 0–3 的整数，大多数为 0；ETH 全 0 | **UNKNOWN**（方向与含义） |
| Trenches 名次 | **ABSENT**：Trenches 没有 rank 字段；数组顺序的含义 UNKNOWN | — |
| Signal 名次 | **ABSENT**：按 `trigger_at` 降序返回，不是排名 | VERIFIED_BY_RAW |
| `rank_change` | **NOT PROVIDED**，只能自己算 | — |

### 3.8 Signal / Trigger

| Field | 中文含义 | Raw example | Type | Unit | 证据 |
|---|---|---|---|---|---|
| `S.id` | 信号事件 ID | UUID | string | — | VERIFIED_BY_RAW |
| `S.signal_type` | 信号类型代码 | `7` | integer | 枚举 | 数值 VERIFIED_BY_RAW（本轮见 1 / 3 / 6 / 7 / 8 / 9 / 10 / 11 / 18 / 21）；**含义只有 VERIFIED_BY_DOCS**：1 = K 线价格异动，3 = Dex 社交链接更新，6 = 价格急涨，7 = 价格 ATH，8 = 市值关键位，9 = 直播，10 = Bundler 卖出，11 = CTO，12 = 聪明钱买入，13 / 19 = 平台喊单，18 = Pump claim，20 = KOL 买入，21 = Banker claim。触发条件与阈值 **UNKNOWN** |
| `S.trigger_at` | 信号触发时间 | `1790984873` | integer | Unix **秒** | VERIFIED_BY_BOTH |
| `S.trigger_mc` | 触发时市值 | `2575.57` | float | USD（= `data.usd_market_cap`） | VERIFIED_BY_BOTH |
| `S.first_trigger_mc` | 该 token **首次**触发时的市值 | — | float | USD | VERIFIED_BY_DOCS；73 / 100 等于 `trigger_mc` |
| `S.signal_times` | 该 token 的信号累计次数 | `1` | integer | 次 | VERIFIED_BY_RAW（= 各类型之和）。累计起点 UNKNOWN |
| `S.signal_times_by_type` | 按类型拆分的累计次数 | `{"7":1}` | object | 次 | VERIFIED_BY_RAW |
| `S.data.*` | 触发时的完整快照（155 个字段） | — | object | — | VERIFIED_BY_RAW（`trigger_mc = data.market_cap` 100 / 100） |
| `S.cur_data.*` | 查询时的 3 个当前值 | — | object | — | VERIFIED_BY_DOCS |

GMGN 用 signal_type 表达的类别（按文档，NEEDS_CONFIRMATION）：

| 类别 | 类型 |
|---|---|
| 价格变动 | 1、6、7 |
| 市值阈值 | 8 |
| 热度 / 营销事件 | 2、3、4、5、9、13、19 |
| 聪明钱 / KOL | 12、20 |
| 大额买入 | 14–16，API 拒绝查询 |
| 风险 | 10 |
| 社区接管 | 11 |
| 平台费用领取 | 17、18、21 |

**没有**技术指标类信号，**没有**安全类信号。BASE / ETH：生产不请求（CLI 不支持）→ NOT TESTED。

### 3.9 Security、税与权限

Security 每链只有 1 个 token（与 Phase 2 是同一批 token，两次采样一致）。

| Field（Sec） | true / 1 表示 | false / 0 表示 | null / −1 表示 | 观察值 SOL / RH / BASE / ETH | 证据 |
|---|---|---|---|---|---|
| `is_honeypot` | 是貔貅盘（**危险**） | 文档说"不是"，但**未能证明已做过检测** | 未评估 / 不适用 | null / false / false / false | true 的含义 VERIFIED_BY_DOCS；**false 的含义 NEEDS_CONFIRMATION**（文档说只覆盖 BSC / Base，RH / ETH 的 false 是否经过检测 UNKNOWN）；从未观察到 true |
| `honeypot` | UNKNOWN | **不等于"安全"**：SOL 在 `is_honeypot = null` 时它是 0 | — | 0 / 0 / 0 / 0 | **UNKNOWN**（数字别名不可用） |
| `is_blacklist` | 有黑名单功能（危险） | 无 | 未评估 | null / null / false / null | VERIFIED_BY_DOCS；3 / 4 为 null |
| `blacklist` | — | 0 时 `is_blacklist` 既有 false 也有 null，含义不确定 | −1 与 `is_blacklist = null` 同时出现 | 0 / −1 / 0 / −1 | **NEEDS_CONFIRMATION** |
| `is_open_source` | 合约已开源验证（安全） | 未开源 | 不适用（SOL） | null / true / true / true | VERIFIED_BY_DOCS |
| `open_source` | 1 = 开源 | **SOL 上的 0 是"不适用"**，不是"未开源" | — | 0 / 1 / 1 / 1 | NEEDS_CONFIRMATION（0 有歧义） |
| `is_renounced` / `renounced` | 合约所有权已放弃（较安全） | 未放弃 | 不适用（SOL） | null / false / true / true（数字版 null / 0 / 1 / 1） | VERIFIED_BY_DOCS；两者 4 / 4 一致 |
| `renounced_mint` | 已放弃 mint 权限（安全） | **EVM 上恒为 false = 不适用**（不是"能增发"） | — | true / false / false / false | VERIFIED_BY_DOCS + raw 一致；**仅 SOL 有意义** |
| `renounced_freeze_account` | 已放弃冻结权限（安全） | 同上 | — | true / false / false / false | 同上 |
| `buy_tax` / `sell_tax` | — | `"0"` = 0 税 | — | 四链都是 `"0"` | 单位：比例（`0.03` = 3%，VERIFIED_BY_DOCS + T 中取值 0.0099 / 0.0299 / 0.03 / 0.05 的分布）。**Security 中从未观察到非 0 值** |
| `average_tax` / `high_tax` | UNKNOWN | — | — | 全 `"0"` | UNKNOWN |
| `can_sell` / `can_not_sell` | — | 两者同时为 0（自相矛盾） | — | 四链都是 0 / 0 | **UNKNOWN**，不可用 |
| `privileges` | 特权标签列表（如 `mintable`、`blacklist`、`proxy_calls`、`hidden_owner`） | `[]` = 无特权 | null = 未评估 | null / [5 项] / null / [] | VERIFIED_BY_RAW（标签值）。注意：RH 有 `mintable`，但 `renounced_mint = false` 在 EVM 上不适用，两者不冲突 |
| `lock_summary.is_locked` / `lock_percent` / `left_lock_percent` / `lock_detail[]` | LP 已锁定 | 未锁 | — | true / false / true / true | VERIFIED_BY_DOCS；`left_lock_percent` 的含义 UNKNOWN |
| `burn_status` / `burn_ratio` | `"burn"` = LP 已销毁 | `""` = 未销毁 | — | burn / "" / "" / "" | VERIFIED_BY_DOCS |
| `top_10_holder_rate` | 前 10 地址持仓占比 | — | — | 0.088 / 0.1863 / 0.01 / 0.3786 | 比例；但 T 中出现 2.10 → **NEEDS_CONFIRMATION** |
| `hide_risk` / `is_show_alert` / `flags` | UNKNOWN | 全 false / 空 | — | — | UNKNOWN |
| `lockInfo` | — | — | 全 null | — | 不可用 |
| **mutable metadata** | — | — | — | — | **NOT PROVIDED** |
| **proxy** | 只能从 `privileges` 中的 `proxy_calls` 看到 | — | — | RH 有 | VERIFIED_BY_RAW（标签存在）；含义 VERIFIED_BY_DOCS |

发现源内嵌的同名风险字段**与 Security 不是同一字段**，类型和取值都不同：

| Field | 类型 / 观察值 | 结论 |
|---|---|---|
| `T.is_honeypot` | number，四链（包括 SOL）全部为 0 | 0 不表示"安全"，**UNKNOWN** |
| `T.is_open_source` / `T.is_renounced` | number；SOL 全 0 | SOL 上的 0 = 不适用 |
| `T.renounced_mint` / `T.renounced_freeze_account` | SOL = 1；EVM = null | 与 Sec 语义一致，但类型不同 |
| `T.is_wash_trading` | boolean；T / H / Tr 共 1,163 行**全部 false** | 无法区分"检测为否"与"未检测" → **NEEDS_CONFIRMATION** |
| `T.rug_ratio` | 0–1 | 文档称"rug 风险分"；**RH / ETH 全 0**，SOL / BASE 有值 → EVM 部分链未计算 |
| `Tr.is_honeypot` / `Tr.open_source` / `Tr.owner_renounced` | string | 文档："yes" / "no" / "unknown"，SOL 为空串；SOL 只有 8 / 180 行出现 |

### 3.10 K 线 OHLCV（`market kline --resolution 1d`）

| Field | 中文含义 | 示例 | Type | Unit | Window | Chains | 证据 |
|---|---|---|---|---|---|---|---|
| `K.time` | bar **开盘**时间 | `1790899200000` | integer | Unix **毫秒** | UTC 00:00 对齐，步长 86,400,000 | 四链 | VERIFIED_BY_RAW（文档说秒，错） |
| `K.open / high / low / close` | 开 / 高 / 低 / 收 | 数字字符串 | numeric-string | **USD**（close 与 DexScreener 比值 1.0036） | 当日 UTC；**最新一根进行中，没有 finalized 标记** | 四链 | VERIFIED_BY_BOTH |
| `K.volume` | 当日成交额 | 数字字符串 | numeric-string | **USD** | 当日 UTC | 四链 | VERIFIED_BY_RAW（与文档相反） |
| `K.amount` | 当日成交数量 | 数字字符串 | numeric-string | 代币数量（INFERRED） | 当日 UTC | 四链 | INFERRED |
| `K.source` | — | `""` | string | — | — | 120 / 120 为空串 | 不可用 |

### 3.11 生命周期与时间

| Field | 中文含义 | Unit | 证据 |
|---|---|---|---|
| `T.creation_timestamp` / `Tr.created_timestamp` / `S.data.created_timestamp` | 代币创建时间 | Unix 秒 | VERIFIED_BY_BOTH |
| `T.open_timestamp` / `Tr.open_timestamp` | 开放交易（上 DEX）时间；0 = 未开放 / 未知 | Unix 秒 | VERIFIED_BY_DOCS（0 是哨兵值） |
| `Tr.complete_timestamp` | bonding curve 完成时间；0 = 未完成 | Unix 秒 | VERIFIED_BY_DOCS |
| `Tr.complete_cost_time` | 从创建到完成的秒数 | 秒 | VERIFIED_BY_RAW（151 / 151 = 差值） |
| `Tr.progress` | bonding curve 进度 | 比例 0–1（观察范围 0.0–1.0） | VERIFIED_BY_BOTH |
| Trench bucket | 生命周期阶段（新建 / 接近毕业 / 已毕业） | 枚举 | VERIFIED_BY_BOTH |

## 4. 同名不同义（禁止跨 endpoint 合并）

| 字段名 | 差异 |
|---|---|
| `liquidity` | T / H 与 Tr 在 ETH 上数值不同（§5）；S 有 `data`（触发时）与 `cur_data`（查询时）两层 |
| `market_cap` | S 顶层 = 查询时；S `data` = 触发时；T / H / Tr = 采集时，FDV 口径 |
| `holder_count` | S `data`（触发时）与 `cur_data`（查询时）不同的有 76 / 100 |
| `is_honeypot` | Sec：boolean / null；T：number（全 0）；Tr：string（SOL 多为不出现） |
| `renounced_mint` | Sec：boolean（EVM false = 不适用）；T：number / null；Tr：string |
| `open_source` / `is_open_source` | Sec 两者并存，SOL 上值不一致（0 与 null） |
| `swaps` vs `swaps_24h` | 同一 token 数值相等（ETH 3 / 3），但 T 的窗口取决于请求参数 |
| `volume` | T / H = 窗口成交额（USD）；K = 单根日 K 成交额（USD）；两者不能互换 |
| `top_10_holder_rate` | Sec：字符串；T / S `cur_data`：数字；T 中出现 > 1 的值 |

## 5. 流动性冲突记录（NEEDS_CONFIRMATION）

| Chain | Token | A：`data.rank[].liquidity`（Trending，11:48:37） | B：`completed[].liquidity`（Trenches，11:43:48） | A / B | 同时比较的其他字段 |
|---|---|---|---|---|---|
| ETH | `0x9f14215dd4c57b5eae0c6f69a5bf74fcaf13cccc` | 60,190.8 | 24,547.67 | **2.452** | price 比值 1.000，market_cap 1.000，volume 1.000；A 的 `initial_liquidity` = 27,204.4 |
| ETH | `0xd305785d98f72868d047ce8d4cbaec6dcb6acccc` | 35,001.9 | 28,506.77 | **1.228** | price / mcap / volume 都是 1.000；A 的 `initial_liquidity` = 27,376.2 |
| ETH | `0x57737ded3870e43fed7d80d31e0ced3d5fb0cccc` | 74,706.6 | 25,573.26 | **2.921** | price 0.993，volume 0.995；A 的 `initial_liquidity` = 26,809.6 |
| BASE | `0x3a512627b7a23bf9dd38597925267f4f42fa0ba3` | 76,937.7 | 74,014.71 | 1.040 | 相隔 7.5 分钟 |
| BASE | `0x6055568f6ad85fd1ac9416a1e4fa1ce1d80eeba3` | 13,173.0 | 13,260.97 | 0.993 | — |

可能的解释（都是**假设**，未证实）：

1. **范围不同**：B 带有单一 `pool_address`（uniswap_v2），可能只是单池；A 可能是多池汇总。
2. **计算方式不同**：B 的值接近 A 的 `initial_liquidity`，B 可能只计 quote 一侧，或者是旧值。
3. **报价币种 / 换算不同**：两者 quote 都是 `0x0000…0000`（ETH 原生），币种差异的可能性较低，但不能排除。

处理：在确认之前，`liquidity` **不得**作为跨 endpoint 统一的 V1 字段；每个值必须带来源 endpoint。

## 6. Chain Coverage（核心字段）

状态说明：PRESENT = 有非零值；**PRESENT·ALL0** = 字段存在但整列为 0 / false（**不能**当作"GMGN 支持"）；NULL = 存在但全为 null；ABSENT = 未出现；NOT TESTED = 未请求。

| Field | SOL | BASE | ETH | RH | Notes |
|---|---|---|---|---|---|
| T.price / volume / swaps / buys / sells / liquidity / market_cap / holder_count / rank | PRESENT | PRESENT | PRESENT | PRESENT | 四链各 100 行 |
| T.price_change_percent / 1h / 5m / 1m | PRESENT | PRESENT | PRESENT | PRESENT | — |
| H.*（同 T 字段） | PRESENT | PRESENT（Phase 2） | PRESENT（Phase 2） | PRESENT（Phase 2） | 本轮只请求了 SOL；Phase 2 的四链 key 完全一致 |
| Tr.volume_24h / swaps_24h / buys_24h / sells_24h / holder_count / progress | PRESENT | PRESENT | PRESENT | PRESENT | — |
| Tr.price_change_* / Tr.rank / Tr.usd_market_cap | ABSENT | ABSENT | ABSENT | ABSENT | endpoint 不提供 |
| T.smart_degen_count / renowned_count | PRESENT | PRESENT | PRESENT | PRESENT | Tr.smart_degen_count：BASE PRESENT·ALL0 |
| T.bot_degen_count / rate, bundler_rate, rat_trader_amount_rate | PRESENT | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT | EVM 部分链没有计算 |
| T.bluechip_owner_percentage | PRESENT | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | — |
| T.rug_ratio | PRESENT | PRESENT | PRESENT·ALL0 | PRESENT·ALL0 | — |
| T.hot_level | PRESENT | PRESENT | PRESENT·ALL0 | PRESENT | — |
| T.square_mentions / dexscr_trending_bar / is_show_alert | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | 不可用 |
| T.is_wash_trading / Tr.is_wash_trading | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | false 的含义未确认 |
| T.is_honeypot | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | SCHEMA DIFFERENT（与 Sec 相比） |
| T.renounced_mint / freeze | PRESENT | NULL | NULL | NULL | SOL-only 概念 |
| T.is_open_source / is_renounced / lock_percent | PRESENT·ALL0 | PRESENT | PRESENT | PRESENT | SOL 的 0 = 不适用 |
| Tr.is_honeypot / open_source / owner_renounced | PRESENT（8 / 180） | PRESENT | PRESENT | PRESENT | SCHEMA DIFFERENT（字符串） |
| Tr.fresh_wallet_rate | PRESENT | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT | — |
| Tr.new_wallet_volume | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | — |
| Tr.buy_volume_24h / sell_volume_24h | 部分行 | 部分行（卖出额全 0） | 部分行 | 部分行 | UNKNOWN |
| S.*（全部） | PRESENT | NOT TESTED | NOT TESTED | PRESENT | CLI 不支持 BASE / ETH |
| S.data.volume_* / swaps_* / smart_degen_count | PRESENT·ALL0 | NOT TESTED | NOT TESTED | PRESENT·ALL0 | — |
| Sec.is_honeypot | NULL | PRESENT（false） | PRESENT（false） | PRESENT（false） | 从未观察到 true |
| Sec.renounced_mint / freeze | PRESENT（true） | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | EVM = 不适用 |
| Sec.is_open_source / is_renounced | NULL | PRESENT | PRESENT | PRESENT（renounced = false） | — |
| Sec.privileges | NULL | NULL | PRESENT（[]） | PRESENT（5 项） | — |
| Sec.sell_tax / buy_tax | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | PRESENT·ALL0 | 非 0 值未观察到 |
| K.time / OHLC / volume / amount | PRESENT | PRESENT | PRESENT | PRESENT | Phase 2 |

"没有观察到"≠"GMGN 不支持"。例如 Security 的 `is_honeypot = true` 只是在 4 个 token 中没出现。

## 7. 字段稳定性

| 等级 | 字段 |
|---|---|
| **STABLE**（两次采样、四链、多 token，schema 一致） | T / H：price、price_change_percent*、volume、swaps、buys、sells、market_cap、total_supply、holder_count、rank、creation_timestamp；Tr：volume_24h、swaps_24h、buys_24h、sells_24h、holder_count、market_cap、price、progress、created_timestamp；K：time、OHLC、volume；S：id、signal_type、trigger_at、trigger_mc、signal_times(_by_type)、cur_data.* |
| **PARTIAL**（部分链整列为 0 / null，或存在跨 endpoint 冲突） | liquidity（冲突）；smart_degen_count、renowned_count、bot_degen_*、bundler_rate、rat_trader_amount_rate、rug_ratio、bluechip_owner_percentage、fresh_wallet_rate、hot_level；Sec 的全部字段（每链只有 1 个 token）；renounced_*（SOL-only） |
| **UNSTABLE**（类型漂移或公式不可复现） | is_honeypot / open_source / renounced_* 跨 endpoint 类型不同；buy_volume_24h、sell_volume_24h、net_buy_24h；top_10_holder_rate（字符串 / 数字，且 > 1）；Tr 的可选字段（132 个字段的并集中只有 65 个全行出现） |
| **UNKNOWN** | hot_level 的方向、visiting_count、entrapment_ratio、price_volatility_rate、can_sell / can_not_sell、honeypot、blacklist、average_tax、high_tax、hide_risk、K.amount |

## 8. GMGN DIRECT vs DERIVED

**GMGN DIRECT**（原始字段）：price、price_change_percent / 1h / 5m / 1m、volume（窗口）、volume_24h、swaps / buys / sells（及 `_24h` 版本）、liquidity、initial_liquidity、market_cap（GMGN 按总供应量算出）、total_supply、history_highest_market_cap、holder_count、rank、hot_level、smart_degen_count / renowned_count / sniper_count、各类比例字段、安全字段、signal_type / trigger_at / trigger_mc / first_trigger_mc / signal_times、K 线 OHLCV、创建 / 开放 / 完成时间、progress。

注意：`market_cap` 和 `complete_cost_time` 虽然是 GMGN 直接返回，但实际是**GMGN 自己算出来的派生值**（分别等于 price × total_supply 与时间差）。

**DERIVED**（GMGN 不提供，由我们计算）：

| 指标 | 输入 | 公式 |
|---|---|---|
| N 日累计涨幅 | K.close | `close_d0 / close_d−N − 1`（只用已定稿 bar） |
| 连涨天数 | K.close | 尾部连续 `close_d > close_d−1` 的天数 |
| 日成交额加速度 | K.volume（USD） | `vol_d0 / mean(vol_d−7..d−1)` |
| 买卖笔数比 | buys、sells | `buys / (buys + sells)` |
| 笔数加速度 | swaps 快照 | `swaps_now / swaps_{t−Δ}`（需要快照历史） |
| 流动性变化 | **同一 endpoint** 的 liquidity 快照 | `liq_now / liq_{t−Δ}`（不得跨 endpoint） |
| 名次变化 | 同一请求参数下的 rank 事件 | `rank_{t−Δ} − rank_now`（不在榜 ≠ 名次 0） |
| 热度加速度 | 上榜事件 / signal_times | 窗口内事件数的差分 |
| 突破 | K.high / K.close | `close ≥ max(high_{N 日})` |
| 价格加速度 | price_change_percent1h、price_change_percent | `pc1h − pc24h / 24` |
| 成交额 / 流动性 | volume、liquidity（同一 endpoint、同一时刻） | 相除（liquidity 有冲突，见 §5） |
| 换手率（成交额 / 市值） | volume、market_cap | 相除；market_cap 是 FDV 口径 |
| 6h 价格变化 | 本地 hourly_price | `p_now / p_6h − 1` |

## 9. V1 当前字段重审

| Field | 含义清楚？ | 窗口清楚？ | 单位清楚？ | 稳定？ | 产品有用？ | V1？ |
|---|---|---|---|---|---|---|
| buys / sells（T / H / Tr） | 是：交易笔数 | 是：24h（T 依赖 `--interval 24h`） | 是：笔 | STABLE | 是 | **SAFE** |
| swaps / swaps_24h | 是 | 是 | 是 | STABLE | 是 | **SAFE** |
| volume / volume_24h（T / H / Tr） | 是：成交额 | 是：24h | 是：USD | STABLE | 是 | **SAFE** |
| price_change_percent1h（T / H） | 是 | 是：1h | 是：百分数 | STABLE | 是 | **SAFE** |
| is_wash_trading | 文档有定义 | UNKNOWN | boolean | 1,163 行全部 false | 是 | **BLOCKED_BY_SEMANTICS**：false 是否表示"已检测" |
| signal trigger_at | 是 | 事件时间 | Unix 秒 | STABLE | 是 | **SAFE**（仅 SOL / RH） |
| signal trigger_mc | 是：触发时市值 | 触发时 | USD | STABLE | 是 | **SAFE**（仅 SOL / RH；FDV 口径） |
| Sec.is_honeypot | true 的含义清楚；**false 不清楚** | snapshot | boolean / null | PARTIAL | 是 | **BLOCKED_BY_SEMANTICS** |
| Sec.renounced_mint | SOL 上清楚；EVM 上 false = 不适用 | snapshot | boolean | PARTIAL | 是 | **SAFE（仅 SOL；EVM 必须映射为 NOT_APPLICABLE）** |
| Sec.renounced_freeze_account | 同上 | snapshot | boolean | PARTIAL | 是 | **SAFE（仅 SOL）** |
| Sec.sell_tax | 比例（文档） | snapshot | 比例（Security 中只观察到 "0"） | PARTIAL | 是 | **BLOCKED_BY_SEMANTICS**：Security 中没有非 0 样本；T 中 `""` 的含义未确认 |
| price（T / H / Tr） | 是 | snapshot | USD | STABLE | 是 | **SAFE** |
| liquidity | 口径冲突 | snapshot | USD 量级 | PARTIAL | 是 | **BLOCKED_BY_SEMANTICS**（§5） |
| market_cap（T / H / Tr） | 是：price × total_supply | snapshot | USD | STABLE | 是 | **SAFE（标注为 FDV 口径）** |
| holder_count（T / H / Tr） | 是：当前持币地址数 | snapshot | 地址数 | STABLE | 是 | **SAFE**（不是新增钱包） |
| rank（T / H） | 是：本次请求列表中的位置 | 随请求参数 | 名次 | STABLE | 是 | **SAFE（带请求参数；不是全市场排名）** |
| creation_timestamp | 是 | 事件时间 | Unix 秒 | STABLE | 是 | **SAFE** |
| K.time / OHLC / volume | 是 | 1 根 UTC 日 K | ms / USD / USD | STABLE | 是 | **SAFE** |

## 10. V1 SAFE FIELD SET

只收录满足全部条件的字段：含义明确、窗口明确、单位明确、raw 已观察、跨 endpoint 没有未解释冲突。

| # | Field（完整路径） | 含义 | 单位 | 窗口 | 链 | 使用条件 |
|---|---|---|---|---|---|---|
| 1 | `data.rank[].price`、`[0].tokens[].price`、`<bucket>[].price` | 当前价格 | USD | snapshot | 四链 | Tr 中 price = 0 视为缺失 |
| 2 | `data.rank[].price_change_percent` | 窗口涨跌 | % | = 请求的 `--interval` | 四链 | 必须同时保存请求 interval |
| 3 | `data.rank[].price_change_percent1h`、`[0].tokens[].price_change_percent1h` | 1h 涨跌 | % | 1h | 四链 | — |
| 4 | `data.rank[].volume`、`[0].tokens[].volume`、`<bucket>[].volume_24h` | 成交额 | USD | 24h（T 依赖 interval） | 四链 | 保存 interval |
| 5 | `data.rank[].swaps`、`<bucket>[].swaps_24h`（H 同） | 交易笔数 | 笔 | 24h | 四链 | 不是钱包数 |
| 6 | `data.rank[].buys` / `sells`、`<bucket>[].buys_24h` / `sells_24h`（H 同） | 买 / 卖笔数 | 笔 | 24h | 四链 | 不是买家 / 卖家数 |
| 7 | `data.rank[].market_cap`、`[0].tokens[].market_cap`、`<bucket>[].market_cap` | 市值（按总供应量） | USD | snapshot | 四链 | 标注为 FDV 口径 |
| 8 | `*.total_supply` | 总供应量 | 代币数 | snapshot | 四链 | — |
| 9 | `*.holder_count`（T / H / Tr） | 当前持币地址数 | 地址数 | snapshot | 四链 | 不是新增钱包，不是交易者数 |
| 10 | `data.rank[].rank`、`[0].tokens[].rank` | 本次列表中的位置 | 名次 | 随请求参数 | 四链 | 必须带 endpoint 与请求参数；不在榜 ≠ 0 |
| 11 | `data.rank[].creation_timestamp`、`<bucket>[].created_timestamp` | 创建时间 | Unix 秒 | 事件 | 四链 | — |
| 12 | `<bucket>[].progress`、trench bucket | 毕业进度 / 阶段 | 0–1 / 枚举 | snapshot | 四链 | — |
| 13 | `[].signal_type`（作为原始代码） | 信号类型代码 | 枚举 | 事件 | SOL RH | **只存代码**，含义标注为"文档定义，未确认" |
| 14 | `[].trigger_at` | 信号触发时间 | Unix 秒 | 事件 | SOL RH | — |
| 15 | `[].trigger_mc` | 触发时市值 | USD（FDV 口径） | 触发时 | SOL RH | — |
| 16 | `renounced_mint`、`renounced_freeze_account`（Security 根对象） | mint / freeze 权限是否已放弃 | boolean | snapshot | **仅 SOL** | EVM 一律映射为 NOT_APPLICABLE |
| 17 | `list[].time` | 日 K 开盘时间 | Unix **ms** | UTC 日 | 四链 | 按毫秒解析 |
| 18 | `list[].open/high/low/close` | 日 K 价格 | USD | UTC 日 | 四链 | 最新一根进行中，需要本地判定 finalized |
| 19 | `list[].volume` | 日 K 成交额 | USD | UTC 日 | 四链 | 不要按文档当作代币数量 |

## 11. BLOCKED FIELD SET

| Field | 阻塞原因 |
|---|---|
| `liquidity`（T / H / Tr；S 的两层） | 跨 endpoint 数值冲突（ETH 1.23–2.92 倍），口径未确认（§5） |
| `is_wash_trading`（T / H / Tr） | 1,163 行全部 false，无法区分"检测为否"与"未检测" |
| `is_honeypot`（Sec） | 从未观察到 true；RH / ETH 的 false 是否经过检测未确认（文档只写 BSC / Base）；SOL 为 null |
| `is_honeypot`（T）、`honeypot`（Sec） | 四链全部为 0（包括 SOL 不适用的情况），0 有歧义 |
| `sell_tax` / `buy_tax`（Sec） | Security 中只观察到 "0"；刻度依赖文档 |
| `sell_tax` / `buy_tax`（T） | SOL 上为 `""`，空串 = 0 税还是未评估未确认 |
| `blacklist` / `is_blacklist` | 3 / 4 为 null；数字 0 / −1 的含义不确定 |
| `open_source`（数字） | SOL 上 0 = 不适用，与"未开源"混淆 |
| `can_sell` / `can_not_sell` | 两者同时为 0，自相矛盾 |
| `average_tax` / `high_tax` / `hide_risk` / `is_show_alert` / `flags` | 含义 UNKNOWN，或全为默认值 |
| `top_10_holder_rate` | 出现 > 1 的值（最大 2.10），类型在字符串 / 数字之间漂移 |
| `entrapment_ratio` / `bluechip_owner_percentage` | 出现 > 1 的值；bluechip 在 EVM 链全 0 |
| `smart_degen_count` / `renowned_count` | "持有"还是"交易"、时间窗口未定义；Tr 中 BASE 全 0 |
| `bot_degen_*` / `bundler_rate` / `rat_trader_amount_rate` / `rug_ratio` | 部分 EVM 链整列为 0，0 ≠ 无风险 |
| `hot_level` | 0–3，方向与含义 UNKNOWN，ETH 全 0 |
| `visiting_count` / `square_mentions` | 含义与窗口 UNKNOWN；square_mentions 全 0 |
| `buy_volume_24h` / `sell_volume_24h` / `net_buy_24h` | 稀疏，公式无法复现 |
| `fresh_wallet_rate` / `new_wallet_volume` | 是比例或全 0，不是钱包数 |
| `S.data.*` 的 1m / 1h / 6h / 24h 活跃度字段 | 100% 为 0 |
| `S.ath` | 不总是 ≥ 当前市值，含义 NEEDS_CONFIRMATION |
| `signal_type` 的**语义解释**（代码本身可存） | 含义只来自文档，触发条件 UNKNOWN |
| `K.amount` | 单位只是推断，且与文档冲突 |
| `price_change_percent5m` / `1m` | 窗口只有文档证据（1h / 24h 已独立验证，5m / 1m 没有） |
| `history_highest_market_cap` / `initial_liquidity` / `lock_percent` | 只有文档证据（lock_percent 在 SOL 全 0） |
| `S.data.price_volatility_rate` | 稀疏，口径 UNKNOWN |

## 12. 对上一轮 V1 字段集合的影响

上一轮 V1 接入的 12 个字段中：

- **仍然 SAFE**：buys、sells、swaps_24h、volume、price_change_percent1h、trigger_at、trigger_mc、renounced_mint（仅 SOL）、renounced_freeze_account（仅 SOL）。
- **现在 BLOCKED_BY_SEMANTICS**：`is_wash_trading`、`is_honeypot`、`sell_tax`。这三个字段的 collector / DB / API 实现可以保留（原值存储），但**不得**用于过滤、评分或"安全"标记，直到 false / 0 的语义得到确认。
- 另外，`liquidity` 是 V1 之前就存在的字段，现在也标记为 BLOCKED：只能按 endpoint 分开显示，不能作为统一指标或跨 endpoint 求变化。

（本轮只记录，不修改代码。）

## 13. PRODUCT CAPABILITY MAP（只使用 SAFE 字段）

| 模块 | 可用 SAFE 字段 | 被阻塞的部分 |
|---|---|---|
| 市场排行 | price、pc（窗口 / 1h）、volume 24h、swaps / buys / sells、market_cap（FDV 口径）、holder_count、rank（按 endpoint）、创建时间 | 流动性排序与门槛（liquidity 冲突）、聪明钱排序 |
| 日 K 连涨 | K.time（ms）/ OHLC / volume（USD）→ N 日涨幅、streak、量比、突破 | K.amount |
| 爆款发现 | pc1h 加速度、24h 笔数与买卖笔数比、volume、rank 变化（同一请求参数）、trench 阶段 / progress、signal 事件（SOL / RH） | Vol / Liq、流动性扩张、聪明钱、刷量过滤 |
| 代币详情页 | 以上全部 + total_supply + signal 时间线 + SOL 的 mint / freeze 权限 | honeypot / 税 / 黑名单 / 开源只能"原样展示 + 未确认"标注 |
| 告警 | 市值跨阈值、rank 急升、新进榜、trench 毕业、signal 触发、连涨 N 天、日成交额放大 | 流动性告警、安全恶化告警、聪明钱告警 |

`gmgn-field-capability-map.md` 已同步加入"语义修订"一节。

## 14. UNKNOWN / NEEDS_CONFIRMATION 清单（未达 READY 的全部原因）

**NEEDS_CONFIRMATION**

| 项 | 待确认内容 |
|---|---|
| liquidity | 跨 endpoint 的口径 |
| is_wash_trading | false 的语义 |
| is_honeypot（Sec） | false 的语义，以及 RH / ETH 是否做过检测 |
| blacklist / is_blacklist | 数字值与 null 的语义 |
| open_source（数字） | SOL 上 0 的语义 |
| sell_tax / buy_tax | 空串的语义；Security 中非 0 值的刻度 |
| top_10_holder_rate | 取值 > 1 |
| entrapment_ratio / bluechip_owner_percentage | 取值 > 1 |
| smart_degen_count / renowned_count | 定义与时间窗口 |
| bot_degen_* / bundler_rate / rat_trader_amount_rate / rug_ratio / fresh_wallet_rate | 部分链整列为 0 的语义 |
| S.ath | 是否真是历史最高 |
| signal_type | 各代码的含义与触发条件 |

**UNKNOWN**

hot_level、visiting_count、square_mentions、price_volatility_rate、can_sell / can_not_sell、honeypot（数字）、average_tax、high_tax、hide_risk、flags、left_lock_percent、K.amount（INFERRED）、buy_volume_24h / sell_volume_24h / net_buy_24h 的公式、rank 的排序算法、holder_count 的余额门槛、Trenches 数组顺序、price_change_percent5m / 1m 的独立验证。

**确认途径（不在本轮执行）**：

- 对 BLOCKED 字段找已知的反例 token（例如已知貔貅盘、已知有税、已知刷量），做少量 raw 请求；
- 比较同一 token 在 `token pool` 中各池的流动性（`token pool` 目前未验证，需要你批准请求）；
- 向 GMGN 确认文档与 raw 不一致的地方。

---

## Appendix: ALL RAW FIELD PATHS

由 `raw/v1/field_inventory.json` 生成（本轮 15 份 raw）。列：Example（自由文本字段以 `‹text›` 遮蔽，这类内容由代币创建者控制，不可信）、Type、Null rate（null / 出现次数；`0×n` = 数值 0 的次数，`""×n` = 空串的次数）、Chains（出现次数 / 该链行数）。Kline 字段来自 Phase 2，列在最后。

### market trending（95 个路径）

| Endpoint | Field | Example | Type | Null rate | Chains（出现/总行） |
|---|---|---|---|---|---|
| trending | `data.rank[].address` | "0x07b3d902783c3c12b077508c3b5c… | string | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].bluechip_owner_percentage` | 0.110448 | float/integer | 0/400 · 0×360 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].bot_degen_count` | 715 | integer | 0/400 · 0×200 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].bot_degen_rate` | 0.3 | float/integer | 0/400 · 0×200 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].bundler_rate` | 0.0589 | float/integer | 0/400 · 0×241 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].burn_ratio` | 0.2055 | float/integer | 0/400 · 0×354 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].burn_status` | "no" | string | 0/400 · ""×1 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].buy_tax` | "0" | numeric-string/string | 0/400 · 0×293 ""×89 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].buys` | 444713 | integer | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].chain` | "base" | string | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].creation_timestamp` | 1784612419 | integer | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].creator` | "0xd594681e88e8b8d1a9bb2df739e3… | string | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].creator_close` | true | boolean | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].creator_token_status` | "creator_close" | string | 0/400 · ""×62 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].cto_flag` | 1 | integer | 0/400 · 0×211 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].dev_team_hold_rate` | 0.0041434419 | float/integer | 0/400 · 0×323 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].dev_token_burn_amount` | 111 | float/integer | 0/400 · 0×352 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].dev_token_burn_ratio` | 0.2055 | float/integer | 0/400 · 0×354 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].dexscr_ad` | 1 | integer | 0/400 · 0×393 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].dexscr_ad_ts` | 1755704799 | integer | 0/400 · 0×393 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].dexscr_boost_fee` | 99 | integer | 0/400 · 0×340 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].dexscr_boost_ts` | 1786854815 | integer | 0/400 · 0×340 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].dexscr_trending_bar` | — | integer | 0/400 · 0×400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].dexscr_trending_bar_ts` | — | integer | 0/400 · 0×400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].dexscr_update_link` | 1 | integer | 0/400 · 0×125 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].dexscr_update_link_ts` | 1786820608 | integer | 0/400 · 0×125 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].end_live_timestamp` | 1790978175 | integer | 0/400 · 0×397 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].entrapment_ratio` | 0.992 | float/integer | 0/400 · 0×3 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].exchange` | "0x33128a8fc17869897dce68ed026d… | string | 0/400 · ""×1 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].gas_fee` | 16.661154309986834 | float/integer | 0/400 · 0×1 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].history_highest_market_cap` | 417003630 | integer | 0/400 · 0×10 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].holder_count` | 13868 | integer | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].hot_level` | 3 | integer | 0/400 · 0×371 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].id` | — | integer | 0/400 · 0×400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].image_dup` | ‹text› | numeric-string | 0/400 · 0×198 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].initial_liquidity` | 1464.77 | float/integer | 0/400 · 0×181 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].is_honeypot` | — | integer | 0/400 · 0×400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].is_og` | true | boolean | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].is_open_source` | 1 | integer | 0/400 · 0×100 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].is_renounced` | 1 | integer | 0/400 · 0×122 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].is_show_alert` | — | boolean | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].is_token_live` | true | boolean | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].is_wash_trading` | — | boolean | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].launch_quote_address` | "0x833589fcd6edb6e08f4c7c32d4f7… | string | 0/400 · ""×127 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].launchpad` | "o1" | string | 0/400 · ""×189 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].launchpad_platform` | "pool_aerodrome" | string | 0/400 · ""×3 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].launchpad_status` | "1" | numeric-string | 0/400 · 0×10 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].liquidity` | 1814720 | float/integer | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].lock_percent` | 0.95 | float/integer | 0/400 · 0×136 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].logo` | ‹text› | string | 0/400 · ""×26 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].market_cap` | 196167000 | float/integer | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].migrated_pool_exchange` | "o1" | string | 0/400 · ""×200 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].name` | ‹text› | numeric-string/string | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].open_timestamp` | 1786817259 | integer | 0/400 · 0×143 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].pool_type` | — | integer | 0/400 · 0×400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].pool_type_str` | — | string | 0/400 · ""×400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].price` | 0.0196167 | float | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].price_change_percent` | 0.939935 | float | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].price_change_percent1h` | 0.301359 | float/integer | 0/400 · 0×8 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].price_change_percent1m` | -0.057907 | float/integer | 0/400 · 0×221 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].price_change_percent5m` | 0.0195586 | float/integer | 0/400 · 0×101 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].rank` | 1 | integer | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].rat_trader_amount_rate` | 0.0041 | float/integer | 0/400 · 0×357 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].renounced_freeze_account` | 1 | integer/null | 300/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].renounced_mint` | 1 | integer/null | 300/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].renowned_count` | 8 | integer | 0/400 · 0×26 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].rug_ratio` | 0.5 | float/integer | 0/400 · 0×291 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].sell_tax` | "0" | numeric-string/string | 0/400 · 0×293 ""×89 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].sells` | 443672 | integer | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].smart_degen_count` | 15 | integer | 0/400 · 0×35 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].sniper_count` | 1000 | integer | 0/400 · 0×122 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].square_mentions` | — | integer | 0/400 · 0×400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].start_live_timestamp` | 1790974182 | integer | 0/400 · 0×396 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].swaps` | 888385 | integer | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].symbol` | ‹text› | numeric-string/string | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].tcid` | ‹text› | numeric-string/string | 0/400 · ""×394 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].telegram` | ‹text› | string | 0/400 · ""×316 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].telegram_dup` | 2 | integer | 0/400 · 0×390 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].top70_sniper_hold_rate` | 8.576e-07 | float/integer | 0/400 · 0×265 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].top_10_holder_rate` | 0.9553 | float/integer | 0/400 · 0×1 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].total_supply` | 10000000000 | integer | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].trans_name` | ‹text› | string | 0/400 · ""×398 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].trans_name_zhcn` | ‹text› | string | 0/400 · ""×207 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].trans_symbol` | ‹text› | string | 0/400 · ""×398 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].trans_symbol_zhcn` | ‹text› | string | 0/400 · ""×202 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].twitter_change_flag` | 1 | integer | 0/400 · 0×290 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].twitter_create_token_count` | 17 | integer | 0/400 · 0×120 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].twitter_del_post_token_count` | 1 | integer | 0/400 · 0×369 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].twitter_dup` | 3 | integer | 0/400 · 0×325 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].twitter_rename_count` | 1 | integer | 0/400 · 0×290 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].twitter_username` | ‹text› | string | 0/400 · ""×91 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].visiting_count` | 1 | integer | 0/400 · 0×137 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].volume` | 302127000 | float/integer | 0/400 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].website` | ‹text› | string | 0/400 · ""×118 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |
| trending | `data.rank[].website_dup` | 4 | integer | 0/400 · 0×348 | SOL 100/100 · RH 100/100 · BASE 100/100 · ETH 100/100 |

### market hot-searches（95 个路径）

| Endpoint | Field | Example | Type | Null rate | Chains（出现/总行） |
|---|---|---|---|---|---|
| hot | `[0].tokens[].address` | "GAwhcphCqCv5bKHmCiN4VDdNWfbXJL… | string | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].bluechip_owner_percentage` | 0.111259 | float/integer | 0/98 · 0×34 | SOL 98/98 |
| hot | `[0].tokens[].bot_degen_count` | 1128 | integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].bot_degen_rate` | 0.4667 | float | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].bundler_rate` | 0.4057 | float/integer | 0/98 · 0×2 | SOL 98/98 |
| hot | `[0].tokens[].burn_ratio` | 0.062496043112845706 | float/integer | 0/98 · 0×86 | SOL 98/98 |
| hot | `[0].tokens[].burn_status` | "burn" | string | 0/98 · ""×1 | SOL 98/98 |
| hot | `[0].tokens[].buy_tax` | "0.01" | numeric-string/string | 0/98 · ""×79 | SOL 98/98 |
| hot | `[0].tokens[].buys` | 137327 | integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].chain` | "sol" | string | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].creation_timestamp` | 1790911442 | integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].creator` | "FTaeCBK9fhv1rsnx91yAPKLax5RoHv… | string | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].creator_close` | true | boolean | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].creator_token_status` | "creator_close" | string | 0/98 · ""×9 | SOL 98/98 |
| hot | `[0].tokens[].cto_flag` | 1 | integer | 0/98 · 0×40 | SOL 98/98 |
| hot | `[0].tokens[].dev_team_hold_rate` | 0.0006444521 | float/integer | 0/98 · 0×67 | SOL 98/98 |
| hot | `[0].tokens[].dev_token_burn_amount` | 56233654.98502218 | float/integer | 0/98 · 0×86 | SOL 98/98 |
| hot | `[0].tokens[].dev_token_burn_ratio` | 0.062496043112845706 | float/integer | 0/98 · 0×86 | SOL 98/98 |
| hot | `[0].tokens[].dexscr_ad` | 1 | integer | 0/98 · 0×95 | SOL 98/98 |
| hot | `[0].tokens[].dexscr_ad_ts` | 1789922885 | integer | 0/98 · 0×95 | SOL 98/98 |
| hot | `[0].tokens[].dexscr_boost_fee` | 249 | integer | 0/98 · 0×65 | SOL 98/98 |
| hot | `[0].tokens[].dexscr_boost_ts` | 1790965227 | integer | 0/98 · 0×65 | SOL 98/98 |
| hot | `[0].tokens[].dexscr_trending_bar` | — | integer | 0/98 · 0×98 | SOL 98/98 |
| hot | `[0].tokens[].dexscr_trending_bar_ts` | — | integer | 0/98 · 0×98 | SOL 98/98 |
| hot | `[0].tokens[].dexscr_update_link` | 1 | integer | 0/98 · 0×10 | SOL 98/98 |
| hot | `[0].tokens[].dexscr_update_link_ts` | 1790911777 | integer | 0/98 · 0×10 | SOL 98/98 |
| hot | `[0].tokens[].end_live_timestamp` | 1790989097 | integer | 0/98 · 0×91 | SOL 98/98 |
| hot | `[0].tokens[].entrapment_ratio` | 0.0737 | float | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].exchange` | "meteora_dlmm" | string | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].gas_fee` | 828.3411752950683 | float | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].history_highest_market_cap` | 8270118 | integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].holder_count` | 8982 | integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].hot_level` | 2 | integer | 0/98 · 0×91 | SOL 98/98 |
| hot | `[0].tokens[].id` | — | integer | 0/98 · 0×98 | SOL 98/98 |
| hot | `[0].tokens[].image_dup` | ‹text› | numeric-string | 0/98 · 0×50 | SOL 98/98 |
| hot | `[0].tokens[].initial_liquidity` | 3287.12 | float/integer | 0/98 · 0×3 | SOL 98/98 |
| hot | `[0].tokens[].is_honeypot` | — | integer | 0/98 · 0×98 | SOL 98/98 |
| hot | `[0].tokens[].is_og` | true | boolean | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].is_open_source` | — | integer | 0/98 · 0×98 | SOL 98/98 |
| hot | `[0].tokens[].is_renounced` | — | integer | 0/98 · 0×98 | SOL 98/98 |
| hot | `[0].tokens[].is_show_alert` | — | boolean | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].is_token_live` | true | boolean | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].is_wash_trading` | — | boolean | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].launch_quote_address` | "So1111111111111111111111111111… | string | 0/98 · ""×7 | SOL 98/98 |
| hot | `[0].tokens[].launchpad` | "pump" | string | 0/98 · ""×2 | SOL 98/98 |
| hot | `[0].tokens[].launchpad_platform` | "Pump.fun" | string | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].launchpad_status` | "1" | numeric-string | 0/98 · 0×3 | SOL 98/98 |
| hot | `[0].tokens[].liquidity` | 185457 | float/integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].lock_percent` | — | integer | 0/98 · 0×98 | SOL 98/98 |
| hot | `[0].tokens[].logo` | ‹text› | string | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].market_cap` | 1513950 | float/integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].migrated_pool_exchange` | "pump_amm" | string | 0/98 · ""×5 | SOL 98/98 |
| hot | `[0].tokens[].name` | ‹text› | string | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].open_timestamp` | 1790911442 | integer | 0/98 · 0×4 | SOL 98/98 |
| hot | `[0].tokens[].pool_type` | — | integer | 0/98 · 0×98 | SOL 98/98 |
| hot | `[0].tokens[].pool_type_str` | — | string | 0/98 · ""×98 | SOL 98/98 |
| hot | `[0].tokens[].price` | 0.0015256 | float | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].price_change_percent` | 284.202 | float | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].price_change_percent1h` | 0.135625 | float | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].price_change_percent1m` | -0.0751269 | float/integer | 0/98 · 0×14 | SOL 98/98 |
| hot | `[0].tokens[].price_change_percent5m` | 0.771472 | float | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].rank` | 1 | integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].rat_trader_amount_rate` | 0.0002 | float/integer | 0/98 · 0×82 | SOL 98/98 |
| hot | `[0].tokens[].renounced_freeze_account` | 1 | integer | 0/98 · 0×2 | SOL 98/98 |
| hot | `[0].tokens[].renounced_mint` | 1 | integer | 0/98 · 0×3 | SOL 98/98 |
| hot | `[0].tokens[].renowned_count` | 19 | integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].rug_ratio` | 0.264 | float/integer | 0/98 · 0×11 | SOL 98/98 |
| hot | `[0].tokens[].sell_tax` | "0.01" | numeric-string/string | 0/98 · ""×79 | SOL 98/98 |
| hot | `[0].tokens[].sells` | 122075 | integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].smart_degen_count` | 170 | integer | 0/98 · 0×1 | SOL 98/98 |
| hot | `[0].tokens[].sniper_count` | 28 | integer | 0/98 · 0×28 | SOL 98/98 |
| hot | `[0].tokens[].square_mentions` | — | integer | 0/98 · 0×98 | SOL 98/98 |
| hot | `[0].tokens[].start_live_timestamp` | 1790985435 | integer | 0/98 · 0×90 | SOL 98/98 |
| hot | `[0].tokens[].swaps` | 259402 | integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].symbol` | ‹text› | string | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].tcid` | ‹text› | numeric-string/string | 0/98 · ""×84 | SOL 98/98 |
| hot | `[0].tokens[].telegram` | ‹text› | string | 0/98 · ""×84 | SOL 98/98 |
| hot | `[0].tokens[].telegram_dup` | — | integer | 0/98 · 0×98 | SOL 98/98 |
| hot | `[0].tokens[].top70_sniper_hold_rate` | 6.66e-08 | float/integer | 0/98 · 0×54 | SOL 98/98 |
| hot | `[0].tokens[].top_10_holder_rate` | 0.1443 | float | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].total_supply` | 992366389 | integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].trans_name` | ‹text› | string | 0/98 · ""×97 | SOL 98/98 |
| hot | `[0].tokens[].trans_name_zhcn` | ‹text› | string | 0/98 · ""×24 | SOL 98/98 |
| hot | `[0].tokens[].trans_symbol` | ‹text› | string | 0/98 · ""×97 | SOL 98/98 |
| hot | `[0].tokens[].trans_symbol_zhcn` | ‹text› | string | 0/98 · ""×13 | SOL 98/98 |
| hot | `[0].tokens[].twitter_change_flag` | 1 | integer | 0/98 · 0×50 | SOL 98/98 |
| hot | `[0].tokens[].twitter_create_token_count` | 428 | integer | 0/98 · 0×24 | SOL 98/98 |
| hot | `[0].tokens[].twitter_del_post_token_count` | 1 | integer | 0/98 · 0×75 | SOL 98/98 |
| hot | `[0].tokens[].twitter_dup` | 102 | integer | 0/98 · 0×70 | SOL 98/98 |
| hot | `[0].tokens[].twitter_rename_count` | 4 | integer | 0/98 · 0×50 | SOL 98/98 |
| hot | `[0].tokens[].twitter_username` | ‹text› | string | 0/98 · ""×13 | SOL 98/98 |
| hot | `[0].tokens[].visiting_count` | 276 | integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].volume` | 35770200 | float/integer | 0/98 | SOL 98/98 |
| hot | `[0].tokens[].website` | ‹text› | string | 0/98 · ""×17 | SOL 98/98 |
| hot | `[0].tokens[].website_dup` | 44 | integer | 0/98 · 0×67 | SOL 98/98 |

### market trenches（146 个路径）

| Endpoint | Field | Example | Type | Null rate | Chains（出现/总行） |
|---|---|---|---|---|---|
| trenches | `<bucket>[].address` | "0x3a512627b7a23bf9dd3859792526… | string | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].bonus_category` | — | array | 0/18 | SOL 18/180 · RH 0/180 · BASE 0/180 · ETH 0/125 |
| trenches | `<bucket>[].bot_degen_count` | 1482 | integer | 0/665 · 0×462 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].bot_degen_rate` | 0.0018 | float/integer | 0/665 · 0×496 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].bundler_mhr` | 0.3457374833756521 | float/integer | 0/305 · 0×220 | SOL 123/180 · RH 104/180 · BASE 69/180 · ETH 9/125 |
| trenches | `<bucket>[].bundler_trader_amount_rate` | 0.0545 | float/integer | 0/665 · 0×597 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].burn_status` | "yes" | string | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].buy_tax` | -1 | float/integer | 0/569 · 0×520 | SOL 180/180 · RH 180/180 · BASE 84/180 · ETH 125/125 |
| trenches | `<bucket>[].buy_tips` | — | integer | 0/117 · 0×117 | SOL 39/180 · RH 66/180 · BASE 9/180 · ETH 3/125 |
| trenches | `<bucket>[].buy_volume_24h` | 0.91881581 | float/integer | 0/219 · 0×151 | SOL 8/180 · RH 61/180 · BASE 84/180 · ETH 66/125 |
| trenches | `<bucket>[].buys_24h` | 772 | integer | 0/665 · 0×155 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].callout_count` | 19 | integer | 0/665 · 0×630 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].chain` | "base" | string | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].co_d` | true | boolean | 0/255 | SOL 74/180 · RH 104/180 · BASE 69/180 · ETH 8/125 |
| trenches | `<bucket>[].complete_cost_time` | 4068 | integer | 0/222 | SOL 50/180 · RH 95/180 · BASE 69/180 · ETH 8/125 |
| trenches | `<bucket>[].complete_timestamp` | 1790997485 | integer | 0/665 · 0×480 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].created_timestamp` | 1790993417 | integer | 0/665 · 0×1 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].creation_tool` | ‹text› | string | 0/665 · ""×661 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].creator` | "0xcad088f9e01c359473c27623836d… | string | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].creator_balance_rate` | 0.0062 | float/integer | 0/665 · 0×424 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].creator_created_count` | 1 | integer | 0/575 · 0×2 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 35/125 |
| trenches | `<bucket>[].creator_created_inner_count` | 10 | integer | 0/656 · 0×198 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 116/125 |
| trenches | `<bucket>[].creator_created_open_count` | 1 | integer | 0/656 · 0×408 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 116/125 |
| trenches | `<bucket>[].creator_created_open_ratio` | 1 | float/integer | 0/656 · 0×439 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 116/125 |
| trenches | `<bucket>[].creator_token_status` | "creator_close" | string | 0/665 · ""×176 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].cto_flag` | true | boolean | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].decimals` | 18 | integer | 0/351 | SOL 180/180 · RH 54/180 · BASE 74/180 · ETH 43/125 |
| trenches | `<bucket>[].dev_team_hold_rate` | 4.1229e-06 | float/integer | 0/665 · 0×548 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].dev_token_burn_amount` | 1000000 | float/integer | 0/665 · 0×651 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].dev_token_burn_ratio` | 0.2089 | float/integer | 0/665 · 0×655 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].dexscr_ad` | — | boolean | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].dexscr_boost_fee` | 249 | integer | 0/665 · 0×657 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].dexscr_trending_bar` | — | integer | 0/665 · 0×665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].dexscr_update_link` | true | boolean | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].end_live_timestamp` | 1790967832 | integer | 0/391 · 0×389 | SOL 180/180 · RH 61/180 · BASE 84/180 · ETH 66/125 |
| trenches | `<bucket>[].entrapment_ratio` | 0.9986 | float/integer | 0/665 · 0×453 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].exchange` | "0x498581ff718922c3f8e6a244956a… | string | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].fee_params` | — | array | 0/580 | SOL 180/180 · RH 180/180 · BASE 95/180 · ETH 125/125 |
| trenches | `<bucket>[].fresh_wallet_rate` | 0.0004 | float/integer | 0/665 · 0×517 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].fund_from` | "Binance" | string | 0/205 · ""×180 | SOL 80/180 · RH 60/180 · BASE 60/180 · ETH 5/125 |
| trenches | `<bucket>[].fund_from_address` | "0x59b76c89fde653e3436ba429c3ab… | string | 0/522 · ""×53 | SOL 176/180 · RH 170/180 · BASE 73/180 · ETH 103/125 |
| trenches | `<bucket>[].fund_from_ts` | 1790524293 | integer | 0/522 · 0×53 | SOL 176/180 · RH 170/180 · BASE 73/180 · ETH 103/125 |
| trenches | `<bucket>[].has_at_least_one_social` | true | boolean | 0/117 | SOL 39/180 · RH 66/180 · BASE 9/180 · ETH 3/125 |
| trenches | `<bucket>[].holder_count` | 374 | integer | 0/665 · 0×16 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].image_dup` | 7 | integer | 0/665 · 0×404 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].instagram` | ‹text› | string | 0/187 · ""×185 | SOL 60/180 · RH 60/180 · BASE 62/180 · ETH 5/125 |
| trenches | `<bucket>[].is_honeypot` | "unknown" | string | 0/493 | SOL 8/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].is_og` | true | boolean | 0/352 | SOL 81/180 · RH 117/180 · BASE 122/180 · ETH 32/125 |
| trenches | `<bucket>[].is_token_live` | true | boolean | 0/391 | SOL 180/180 · RH 61/180 · BASE 84/180 · ETH 66/125 |
| trenches | `<bucket>[].is_wash_trading` | — | boolean | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].launch_creator` | "ATZgVpafELFZx7b6WJqKbC3oM83bEA… | string | 0/153 · ""×93 | SOL 60/180 · RH 30/180 · BASE 58/180 · ETH 5/125 |
| trenches | `<bucket>[].launch_flag` | true | boolean | 0/185 | SOL 60/180 · RH 60/180 · BASE 60/180 · ETH 5/125 |
| trenches | `<bucket>[].launchpad` | "bankr" | string | 0/665 · ""×111 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].launchpad_platform` | "bankr" | string | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].launchpad_status` | 1 | integer | 0/665 · 0×480 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].liquidity` | 74014.70749572106 | float/integer | 0/665 · 0×235 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].logo` | ‹text› | string | 0/525 · ""×6 | SOL 180/180 · RH 168/180 · BASE 163/180 · ETH 14/125 |
| trenches | `<bucket>[].logo_small_base64` | ‹text› | string | 0/327 | SOL 104/180 · RH 95/180 · BASE 115/180 · ETH 13/125 |
| trenches | `<bucket>[].market_cap` | 207831.79 | float/integer | 0/665 · 0×117 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].mk` | — | object | 0/537 | SOL 175/180 · RH 139/180 · BASE 120/180 · ETH 103/125 |
| trenches | `<bucket>[].mk.o` | ‹text› | string | 0/537 | SOL 175/180 · RH 139/180 · BASE 120/180 · ETH 103/125 |
| trenches | `<bucket>[].mk.v` | — | array | 0/537 | SOL 175/180 · RH 139/180 · BASE 120/180 · ETH 103/125 |
| trenches | `<bucket>[].name` | ‹text› | numeric-string/string | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].net_buy_24h` | -1635.29 | float/integer | 0/574 · 0×82 | SOL 175/180 · RH 166/180 · BASE 130/180 · ETH 103/125 |
| trenches | `<bucket>[].new_wallet_volume` | — | integer | 0/117 · 0×117 | SOL 39/180 · RH 66/180 · BASE 9/180 · ETH 3/125 |
| trenches | `<bucket>[].offchain` | true | boolean | 0/240 | SOL 180/180 · RH 21/180 · BASE 38/180 · ETH 1/125 |
| trenches | `<bucket>[].open_source` | "yes" | string | 0/493 | SOL 8/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].open_timestamp` | 1790997485 | integer | 0/665 · 0×480 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].owner_renounced` | "yes" | string | 0/493 | SOL 8/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].pool_address` | "0xa96f46b537a19c672e3576ce79d4… | string | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].price` | 2.0783179e-06 | float/integer | 0/665 · 0×117 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].private_vault_hold_rate` | — | integer | 0/386 · 0×386 | SOL 175/180 · RH 61/180 · BASE 84/180 · ETH 66/125 |
| trenches | `<bucket>[].progress` | 1 | float/integer | 0/665 · 0×244 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].quote_address` | "0x4200000000000000000000000000… | string | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].quote_address_type` | 11 | integer | 0/665 · 0×62 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].rat_trader_amount_rate` | 0.0062 | float/integer | 0/665 · 0×580 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].renounced_freeze_account` | "0" | numeric-string | 0/384 · 0×204 | SOL 180/180 · RH 55/180 · BASE 83/180 · ETH 66/125 |
| trenches | `<bucket>[].renounced_mint` | "0" | numeric-string | 0/384 · 0×204 | SOL 180/180 · RH 55/180 · BASE 83/180 · ETH 66/125 |
| trenches | `<bucket>[].renowned_count` | 3 | integer | 0/665 · 0×620 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].route_mint_a` | "1790998790858:452814556:AAAAAA… | string | 0/140 · ""×2 | SOL 138/180 · RH 0/180 · BASE 1/180 · ETH 1/125 |
| trenches | `<bucket>[].route_mint_b` | "1790998790861:452814556:AAAAAA… | string | 0/62 · ""×2 | SOL 60/180 · RH 0/180 · BASE 1/180 · ETH 1/125 |
| trenches | `<bucket>[].route_pool` | "1790998797244:452814580:8ZptBB… | string | 0/140 · ""×2 | SOL 138/180 · RH 0/180 · BASE 1/180 · ETH 1/125 |
| trenches | `<bucket>[].route_vault_a` | "1790998792725:452814563:259186… | string | 0/48 · ""×36 | SOL 46/180 · RH 0/180 · BASE 1/180 · ETH 1/125 |
| trenches | `<bucket>[].route_vault_b` | "1790998792725:452814563:662052… | string | 0/48 · ""×36 | SOL 46/180 · RH 0/180 · BASE 1/180 · ETH 1/125 |
| trenches | `<bucket>[].rug_ratio` | 0.10638297872340426 | float/integer | 0/391 · 0×301 | SOL 180/180 · RH 61/180 · BASE 84/180 · ETH 66/125 |
| trenches | `<bucket>[].s_qsafe` | "yes" | string | 0/510 | SOL 180/180 · RH 152/180 · BASE 178/180 · ETH 0/125 |
| trenches | `<bucket>[].sell_tax` | -1 | float/integer | 0/569 · 0×518 | SOL 180/180 · RH 180/180 · BASE 84/180 · ETH 125/125 |
| trenches | `<bucket>[].sell_volume_24h` | 24365.26134936 | float/integer | 0/219 · 0×208 | SOL 8/180 · RH 61/180 · BASE 84/180 · ETH 66/125 |
| trenches | `<bucket>[].sells_24h` | 646 | integer | 0/665 · 0×270 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].seq_index` | "000000052073310_000816" | numeric-string/string | 0/665 · ""×125 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].show_sharing_fee` | true | boolean | 0/391 | SOL 180/180 · RH 61/180 · BASE 84/180 · ETH 66/125 |
| trenches | `<bucket>[].smart_degen_count` | 51 | integer | 0/547 · 0×435 | SOL 175/180 · RH 165/180 · BASE 101/180 · ETH 106/125 |
| trenches | `<bucket>[].sniper_count` | 2 | integer | 0/117 · 0×108 | SOL 39/180 · RH 66/180 · BASE 9/180 · ETH 3/125 |
| trenches | `<bucket>[].standard` | "erc20" | numeric-string/string | 0/487 · ""×113 | SOL 180/180 · RH 61/180 · BASE 180/180 · ETH 66/125 |
| trenches | `<bucket>[].start_live_timestamp` | 1790966632 | integer | 0/391 · 0×388 | SOL 180/180 · RH 61/180 · BASE 84/180 · ETH 66/125 |
| trenches | `<bucket>[].status` | 1 | integer | 0/665 · 0×480 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].suspected_insider_hold_rate` | 0.0047 | float/integer | 0/665 · 0×603 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].swaps_24h` | 1418 | integer | 0/665 · 0×132 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].symbol` | ‹text› | numeric-string/string | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].tax_allocation` | — | object | 0/67 | SOL 17/180 · RH 50/180 · BASE 0/180 · ETH 0/125 |
| trenches | `<bucket>[].tax_allocation.dividend` | 0.51 | float/integer | 0/18 | SOL 17/180 · RH 1/180 · BASE 0/180 · ETH 0/125 |
| trenches | `<bucket>[].tax_allocation.dividend_tokens` | — | array | 0/18 | SOL 17/180 · RH 1/180 · BASE 0/180 · ETH 0/125 |
| trenches | `<bucket>[].tax_allocation.dividend_tokens[].address` | "0x0bd7d308f8e1639fab988df18a80… | string | 0/18 | SOL 17/180 · RH 1/180 · BASE 0/180 · ETH 0/125 |
| trenches | `<bucket>[].tax_allocation.dividend_tokens[].distribution_type` | "direct" | string | 0/18 | SOL 17/180 · RH 1/180 · BASE 0/180 · ETH 0/125 |
| trenches | `<bucket>[].tax_allocation.dividend_tokens[].share` | 1 | integer | 0/18 | SOL 17/180 · RH 1/180 · BASE 0/180 · ETH 0/125 |
| trenches | `<bucket>[].tax_allocation.market_address` | "0xd2a5f750d1eff0dca91dff0eaf68… | string | 0/50 | SOL 0/180 · RH 50/180 · BASE 0/180 · ETH 0/125 |
| trenches | `<bucket>[].tax_allocation.marketing` | 1 | float/integer | 0/50 | SOL 0/180 · RH 50/180 · BASE 0/180 · ETH 0/125 |
| trenches | `<bucket>[].telegram` | ‹text› | string | 0/665 · ""×612 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].telegram_dup` | 1 | integer | 0/665 · 0×644 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].tg_call_count` | 3 | integer | 0/665 · 0×633 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].tiktok` | ‹text› | string | 0/186 · ""×185 | SOL 60/180 · RH 60/180 · BASE 61/180 · ETH 5/125 |
| trenches | `<bucket>[].top70_sniper_hold_rate` | 0.0042892429 | float/integer | 0/665 · 0×532 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].top_10_holder_rate` | 0.2147 | float/integer | 0/665 · 0×232 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].total_buy_tax` | 0.0175 | float/integer | 0/665 · 0×141 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].total_fee` | 1.0634286647469189 | float/integer | 0/665 · 0×61 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].total_sell_tax` | 0.0175 | float/integer | 0/665 · 0×141 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].total_supply` | 100000000000 | float/integer | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].trade_fee` | 0.0015 | float/integer | 0/117 · 0×51 | SOL 39/180 · RH 66/180 · BASE 9/180 · ETH 3/125 |
| trenches | `<bucket>[].trans_name` | ‹text› | string | 0/202 · ""×182 | SOL 63/180 · RH 73/180 · BASE 60/180 · ETH 6/125 |
| trenches | `<bucket>[].trans_name_zhcn` | ‹text› | string | 0/481 · ""×38 | SOL 137/180 · RH 154/180 · BASE 95/180 · ETH 95/125 |
| trenches | `<bucket>[].trans_symbol` | ‹text› | string | 0/208 · ""×174 | SOL 65/180 · RH 76/180 · BASE 61/180 · ETH 6/125 |
| trenches | `<bucket>[].trans_symbol_zhcn` | ‹text› | string | 0/515 · ""×57 | SOL 141/180 · RH 157/180 · BASE 157/180 · ETH 60/125 |
| trenches | `<bucket>[].tweet_publish_time` | 1790711837556 | integer | 0/191 | SOL 61/180 · RH 103/180 · BASE 20/180 · ETH 7/125 |
| trenches | `<bucket>[].twitter` | ‹text› | string | 0/665 · ""×346 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].twitter_change_flag` | — | boolean | 0/665 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].twitter_community_id` | "1976698345482539516" | numeric-string/string | 0/186 · ""×185 | SOL 61/180 · RH 60/180 · BASE 60/180 · ETH 5/125 |
| trenches | `<bucket>[].twitter_community_name` | ‹text› | string | 0/186 · ""×185 | SOL 61/180 · RH 60/180 · BASE 60/180 · ETH 5/125 |
| trenches | `<bucket>[].twitter_create_token_count` | 11 | integer | 0/196 · 0×97 | SOL 75/180 · RH 90/180 · BASE 26/180 · ETH 5/125 |
| trenches | `<bucket>[].twitter_del_post_token_count` | 8 | integer | 0/665 · 0×662 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].twitter_dup` | 9 | integer | 0/665 · 0×452 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].twitter_handle` | ‹text› | string | 0/397 · ""×94 | SOL 128/180 · RH 170/180 · BASE 88/180 · ETH 11/125 |
| trenches | `<bucket>[].twitter_is_tweet` | true | boolean | 0/274 | SOL 134/180 · RH 112/180 · BASE 20/180 · ETH 8/125 |
| trenches | `<bucket>[].twitter_rename_count` | 1 | integer | 0/665 · 0×636 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].visiting_count` | 134 | integer | 0/470 · 0×358 | SOL 153/180 · RH 164/180 · BASE 98/180 · ETH 55/125 |
| trenches | `<bucket>[].volume_24h` | 238152.48 | float/integer | 0/665 · 0×159 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].website` | ‹text› | string | 0/665 · ""×337 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].website_dup` | 4 | integer | 0/665 · 0×527 | SOL 180/180 · RH 180/180 · BASE 180/180 · ETH 125/125 |
| trenches | `<bucket>[].x_user_follower` | 12968423 | integer | 0/418 · 0×122 | SOL 136/180 · RH 172/180 · BASE 96/180 · ETH 14/125 |
| trenches | `<bucket>[].x_user_following` | 1235 | integer | 0/418 · 0×148 | SOL 136/180 · RH 172/180 · BASE 96/180 · ETH 14/125 |
| trenches | `<bucket>[].zora_social_info` | — | object | 0/135 | SOL 0/180 · RH 0/180 · BASE 135/180 · ETH 0/125 |
| trenches | `<bucket>[].zora_social_info.bio` | ‹text› | string | 0/7 | SOL 0/180 · RH 0/180 · BASE 7/180 · ETH 0/125 |
| trenches | `<bucket>[].zora_social_info.display_name` | ‹text› | string | 0/82 | SOL 0/180 · RH 0/180 · BASE 82/180 · ETH 0/125 |
| trenches | `<bucket>[].zora_social_info.follower_count` | 4 | integer | 0/17 | SOL 0/180 · RH 0/180 · BASE 17/180 · ETH 0/125 |
| trenches | `<bucket>[].zora_social_info.following_count` | 5 | integer | 0/14 | SOL 0/180 · RH 0/180 · BASE 14/180 · ETH 0/125 |
| trenches | `<bucket>[].zora_social_info.logo` | ‹text› | string | 0/82 | SOL 0/180 · RH 0/180 · BASE 82/180 · ETH 0/125 |
| trenches | `<bucket>[].zora_social_info.username` | ‹text› | string | 0/82 | SOL 0/180 · RH 0/180 · BASE 82/180 · ETH 0/125 |

### market signal（183 个路径）

| Endpoint | Field | Example | Type | Null rate | Chains（出现/总行） |
|---|---|---|---|---|---|
| signal | `[].ath` | 5112.2738 | float/integer | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].cur_data` | — | object | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].cur_data.holder_count` | 2 | integer | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].cur_data.liquidity` | 0.0007515181224039741 | float | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].cur_data.top_10_holder_rate` | 0.1943 | float/integer | 0/100 · 0×24 | SOL 50/50 · RH 50/50 |
| signal | `[].data` | — | object | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.address` | "0xc636009aa7e135ad9547edd9a2d3… | string | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.binance_charity_tax` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.bonus_category` | — | null | 100/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.bot_degen_count` | 1 | integer | 0/100 · 0×41 | SOL 50/50 · RH 50/50 |
| signal | `[].data.bot_degen_rate` | 0.0108 | float/integer | 0/100 · 0×53 | SOL 50/50 · RH 50/50 |
| signal | `[].data.bundle_sell_rate` | 0.2948838035314283 | float | 0/1 | SOL 1/50 · RH 0/50 |
| signal | `[].data.bundler_mhr` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.bundler_trader_amount_rate` | 0.0589 | float/integer | 0/100 · 0×80 | SOL 50/50 · RH 50/50 |
| signal | `[].data.burn_status` | "yes" | string | 0/100 · ""×1 | SOL 50/50 · RH 50/50 |
| signal | `[].data.burn_tax` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.buy_tax` | 0.0899 | float/integer | 0/100 · 0×89 | SOL 50/50 · RH 50/50 |
| signal | `[].data.buys_1h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.buys_1m` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.buys_24h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.buys_6h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.callout_count` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.callout_declaration` | — | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.chain` | "robinhood" | string | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.claim_avatar` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.claim_fee_is_first` | — | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.claim_fee_sol_amount` | "0.000000226581290611" | numeric-string/string | 0/100 · ""×92 | SOL 50/50 · RH 50/50 |
| signal | `[].data.claim_platform` | "twitter" | string | 0/100 · ""×98 | SOL 50/50 · RH 50/50 |
| signal | `[].data.claim_platform_avatar` | ‹text› | string | 0/100 · ""×98 | SOL 50/50 · RH 50/50 |
| signal | `[].data.claim_platform_username` | ‹text› | string | 0/100 · ""×98 | SOL 50/50 · RH 50/50 |
| signal | `[].data.claim_twitter_user_name` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.claim_wallet_address` | "0x4ce22979ae30c7e03f34c806546c… | string | 0/100 · ""×92 | SOL 50/50 · RH 50/50 |
| signal | `[].data.complete_cost_time` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.complete_timestamp` | 1790996260 | integer | 0/100 · 0×86 | SOL 50/50 · RH 50/50 |
| signal | `[].data.created_timestamp` | 1790996577 | integer | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.created_timestamp_us` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.creation_tool` | ‹text› | string | 0/100 · ""×99 | SOL 50/50 · RH 50/50 |
| signal | `[].data.creator` | "0x120bf8c773ace604ee50ec861fb4… | string | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.creator_balance_rate` | 0.0001 | float/integer | 0/100 · 0×77 | SOL 50/50 · RH 50/50 |
| signal | `[].data.creator_created_count` | 50 | integer | 0/100 · 0×41 | SOL 50/50 · RH 50/50 |
| signal | `[].data.creator_created_open_count` | 233 | integer | 0/100 · 0×65 | SOL 50/50 · RH 50/50 |
| signal | `[].data.creator_created_open_ratio` | 0.015 | float/integer | 0/100 · 0×65 | SOL 50/50 · RH 50/50 |
| signal | `[].data.creator_token_status` | "creator_close" | string | 0/100 · ""×18 | SOL 50/50 · RH 50/50 |
| signal | `[].data.cto_flag` | true | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.decimals` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.dev_tax` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.dev_team_hold_rate` | 0.0299447353 | float/integer | 0/100 · 0×66 | SOL 50/50 · RH 50/50 |
| signal | `[].data.dev_token_burn_amount` | 10742196.642668309 | float/integer | 0/100 · 0×99 | SOL 50/50 · RH 50/50 |
| signal | `[].data.dev_token_burn_ratio` | 0.0107 | float/integer | 0/100 · 0×99 | SOL 50/50 · RH 50/50 |
| signal | `[].data.dexscr_ad` | — | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.dexscr_boost_fee` | 399 | integer | 0/100 · 0×99 | SOL 50/50 · RH 50/50 |
| signal | `[].data.dexscr_trending_bar` | — | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.dexscr_update_link` | true | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.dividend_tax` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.end_live_timestamp` | 1790998989 | integer | 0/100 · 0×99 | SOL 50/50 · RH 50/50 |
| signal | `[].data.entrapment_ratio` | 0.5225 | float/integer | 0/100 · 0×54 | SOL 50/50 · RH 50/50 |
| signal | `[].data.exchange` | "0x26605f322f7ff986f381bb9a6e3f… | string | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.fee_params` | — | null | 100/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.fracaster` | — | null | 100/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.fresh_wallet_rate` | 0.0064 | float/integer | 0/100 · 0×64 | SOL 50/50 · RH 50/50 |
| signal | `[].data.fund_from` | "Bitget" | string | 0/100 · ""×96 | SOL 50/50 · RH 50/50 |
| signal | `[].data.fund_from_address` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.fund_from_ts` | 1789493482 | integer | 0/100 · 0×42 | SOL 50/50 · RH 50/50 |
| signal | `[].data.giggle_charity_tax` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.has_at_least_one_social` | — | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.holder_count` | 2 | integer | 0/100 · 0×6 | SOL 50/50 · RH 50/50 |
| signal | `[].data.image_dup` | 39 | integer | 0/100 · 0×84 | SOL 50/50 · RH 50/50 |
| signal | `[].data.instagram` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.is_honeypot` | "no" | string | 0/100 · ""×50 | SOL 50/50 · RH 50/50 |
| signal | `[].data.is_og` | — | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.is_token_live` | — | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.is_wash_trading` | — | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.launchpad` | "flap" | string | 0/100 · ""×19 | SOL 50/50 · RH 50/50 |
| signal | `[].data.launchpad_platform` | "flap" | string | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.liquidity` | 0.0007518211912454145 | float/integer | 0/100 · 0×4 | SOL 50/50 · RH 50/50 |
| signal | `[].data.liquidity_tax` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.logo` | ‹text› | string | 0/100 · ""×11 | SOL 50/50 · RH 50/50 |
| signal | `[].data.market_cap` | 5112.2738 | float/integer | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.max_amount` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.migrated_pool_exchange` | "pons" | string | 0/17 | SOL 15/50 · RH 2/50 |
| signal | `[].data.min_amount` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.name` | ‹text› | string | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.net_buy_1h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.net_buy_1m` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.net_buy_24h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.net_buy_6h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.offchain` | — | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.open_source` | "yes" | string | 0/100 · ""×50 | SOL 50/50 · RH 50/50 |
| signal | `[].data.open_timestamp` | 1784102401 | integer | 0/100 · 0×83 | SOL 50/50 · RH 50/50 |
| signal | `[].data.open_timestamp_us` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.other_tax` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.owner_renounced` | "yes" | string | 0/100 · ""×50 | SOL 50/50 · RH 50/50 |
| signal | `[].data.pool_address` | "0xc636009aa7e135ad9547edd9a2d3… | string | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.price_volatility_rate` | 0.4266143911209298 | float | 0/14 | SOL 5/50 · RH 9/50 |
| signal | `[].data.priority_fee` | 0.000148635971288 | float/integer | 0/100 · 0×13 | SOL 50/50 · RH 50/50 |
| signal | `[].data.private_vault_hold_rate` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.progress` | 2.8061929763e-08 | float/integer | 0/100 · 0×20 | SOL 50/50 · RH 50/50 |
| signal | `[].data.quote_address` | "0x0000000000000000000000000000… | string | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.quote_is_safe` | — | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.rat_trader_amount_rate` | 0.0041 | float/integer | 0/100 · 0×74 | SOL 50/50 · RH 50/50 |
| signal | `[].data.renounced_freeze_account` | true | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.renounced_mint` | true | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.renowned_count` | 171 | integer | 0/100 · 0×90 | SOL 50/50 · RH 50/50 |
| signal | `[].data.rug_ratio` | 0.43478260869565216 | float/integer | 0/100 · 0×80 | SOL 50/50 · RH 50/50 |
| signal | `[].data.sell_tax` | 0.0899 | float/integer | 0/100 · 0×89 | SOL 50/50 · RH 50/50 |
| signal | `[].data.sells_1h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.sells_1m` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.sells_24h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.sells_6h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.seq_index` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.show_sharing_fee` | — | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.smart_degen_count` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.sniper_count` | 2 | integer | 0/100 · 0×61 | SOL 50/50 · RH 50/50 |
| signal | `[].data.standard` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.start_live_timestamp` | 1790998999 | integer | 0/100 · 0×98 | SOL 50/50 · RH 50/50 |
| signal | `[].data.status` | 1 | integer | 0/100 · 0×83 | SOL 50/50 · RH 50/50 |
| signal | `[].data.suspected_insider_hold_rate` | 0.0041 | float/integer | 0/100 · 0×79 | SOL 50/50 · RH 50/50 |
| signal | `[].data.swaps_1h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.swaps_1m` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.swaps_24h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.swaps_6h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.symbol` | ‹text› | string | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.tc_name` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.tcid` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.telegram` | ‹text› | string | 0/100 · ""×88 | SOL 50/50 · RH 50/50 |
| signal | `[].data.telegram_dup` | 1 | integer | 0/100 · 0×96 | SOL 50/50 · RH 50/50 |
| signal | `[].data.tg_call_count` | 43 | integer | 0/100 · 0×95 | SOL 50/50 · RH 50/50 |
| signal | `[].data.tiktok` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.tip_fee` | 2.8607769761666666 | float/integer | 0/100 · 0×61 | SOL 50/50 · RH 50/50 |
| signal | `[].data.top70_sniper_hold_rate` | 0.1349361679 | float/integer | 0/100 · 0×58 | SOL 50/50 · RH 50/50 |
| signal | `[].data.top_10_holder_rate` | 0.1943 | float/integer | 0/100 · 0×24 | SOL 50/50 · RH 50/50 |
| signal | `[].data.top_10_holder_rate_snp` | 0.1943 | float/integer | 0/100 · 0×24 | SOL 50/50 · RH 50/50 |
| signal | `[].data.total_buy_tax` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.total_fee` | 0.000148635971288 | float/integer | 0/100 · 0×27 | SOL 50/50 · RH 50/50 |
| signal | `[].data.total_sell_tax` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.total_supply` | 1000000000 | integer | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.trade_fee` | 0.00083723503546266 | float/integer | 0/100 · 0×57 | SOL 50/50 · RH 50/50 |
| signal | `[].data.trans_name` | ‹text› | string | 0/100 · ""×99 | SOL 50/50 · RH 50/50 |
| signal | `[].data.trans_name_zhcn` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.trans_symbol` | ‹text› | string | 0/100 · ""×99 | SOL 50/50 · RH 50/50 |
| signal | `[].data.trans_symbol_zhcn` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.trigger_count` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.tweet_publish_time` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.twitter` | ‹text› | string | 0/100 · ""×65 | SOL 50/50 · RH 50/50 |
| signal | `[].data.twitter_create_token_count` | 1681 | integer | 0/100 · 0×88 | SOL 50/50 · RH 50/50 |
| signal | `[].data.twitter_del_post_token_count` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.twitter_dup` | 2 | integer | 0/100 · 0×83 | SOL 50/50 · RH 50/50 |
| signal | `[].data.twitter_handle` | — | string | 0/100 · ""×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.twitter_is_tweet` | true | boolean | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.twitter_rename_count` | 1 | integer | 0/100 · 0×95 | SOL 50/50 · RH 50/50 |
| signal | `[].data.usd_market_cap` | 5112.2738 | float/integer | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.vault_tax` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.visiting_count` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.volume_1h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.volume_1m` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.volume_24h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.volume_6h` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.website` | ‹text› | string | 0/100 · ""×69 | SOL 50/50 · RH 50/50 |
| signal | `[].data.website_dup` | 25 | integer | 0/100 · 0×87 | SOL 50/50 · RH 50/50 |
| signal | `[].data.x_user_follower` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.x_user_following` | — | integer | 0/100 · 0×100 | SOL 50/50 · RH 50/50 |
| signal | `[].data.zora_social_info` | — | null | 100/100 | SOL 50/50 · RH 50/50 |
| signal | `[].first_trigger_mc` | 5112.2738 | float | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].id` | "e2c7a5f0-0d24-41aa-8458-f69d82… | string | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].market_cap` | 4228.853 | float/integer | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].signal_times` | 1 | integer | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].signal_times_by_type` | — | object | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].signal_times_by_type.1` | 1 | integer | 0/7 | SOL 7/50 · RH 0/50 |
| signal | `[].signal_times_by_type.10` | 1 | integer | 0/6 | SOL 6/50 · RH 0/50 |
| signal | `[].signal_times_by_type.11` | 1 | integer | 0/10 | SOL 1/50 · RH 9/50 |
| signal | `[].signal_times_by_type.13` | 1 | integer | 0/1 | SOL 1/50 · RH 0/50 |
| signal | `[].signal_times_by_type.18` | 36 | integer | 0/6 | SOL 6/50 · RH 0/50 |
| signal | `[].signal_times_by_type.21` | 2 | integer | 0/4 | SOL 0/50 · RH 4/50 |
| signal | `[].signal_times_by_type.3` | 1 | integer | 0/10 | SOL 1/50 · RH 9/50 |
| signal | `[].signal_times_by_type.5` | 1 | integer | 0/1 | SOL 1/50 · RH 0/50 |
| signal | `[].signal_times_by_type.6` | 1 | integer | 0/40 | SOL 14/50 · RH 26/50 |
| signal | `[].signal_times_by_type.7` | 1 | integer | 0/91 | SOL 46/50 · RH 45/50 |
| signal | `[].signal_times_by_type.8` | 1 | integer | 0/34 | SOL 11/50 · RH 23/50 |
| signal | `[].signal_times_by_type.9` | 4 | integer | 0/2 | SOL 2/50 · RH 0/50 |
| signal | `[].signal_type` | 7 | integer | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].token_address` | "0xc636009aa7e135ad9547edd9a2d3… | string | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].trigger_at` | 1790996615 | integer | 0/100 | SOL 50/50 · RH 50/50 |
| signal | `[].trigger_mc` | 5112.2738 | float/integer | 0/100 | SOL 50/50 · RH 50/50 |

### token security（36 个路径）

| Endpoint | Field | Example | Type | Null rate | Chains（出现/总行） |
|---|---|---|---|---|---|
| security | `address` | "0x0c583e4b9b1ebdb09a8e01fa6fd4… | string | 0/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `average_tax` | "0" | numeric-string | 0/4 · 0×4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `blacklist` | -1 | integer | 0/4 · 0×2 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `burn_ratio` | "0" | numeric-string | 0/4 · 0×3 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `burn_status` | "burn" | string | 0/4 · ""×3 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `buy_tax` | "0" | numeric-string | 0/4 · 0×4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `can_not_sell` | — | integer | 0/4 · 0×4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `can_sell` | — | integer | 0/4 · 0×4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `dev_token_burn_amount` | "0" | numeric-string | 0/4 · 0×3 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `dev_token_burn_ratio` | "0" | numeric-string | 0/4 · 0×3 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `flags` | — | array | 0/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `hide_risk` | — | boolean | 0/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `high_tax` | "0" | numeric-string | 0/4 · 0×4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `honeypot` | — | integer | 0/4 · 0×4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `is_blacklist` | — | boolean/null | 3/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `is_honeypot` | — | boolean/null | 1/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `is_open_source` | true | boolean/null | 1/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `is_renounced` | true | boolean/null | 1/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `is_show_alert` | — | boolean | 0/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `lockInfo` | — | null | 4/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `lock_summary` | — | object | 0/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `lock_summary.is_locked` | true | boolean | 0/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `lock_summary.left_lock_percent` | "0" | numeric-string | 0/4 · 0×2 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `lock_summary.lock_detail` | — | array | 0/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `lock_summary.lock_detail[].is_blackhole` | true | boolean | 0/5 | SOL 1/1 · RH 2/1 · BASE 1/1 · ETH 1/1 |
| security | `lock_summary.lock_detail[].percent` | "0.95" | numeric-string | 0/5 · 0×2 | SOL 1/1 · RH 2/1 · BASE 1/1 · ETH 1/1 |
| security | `lock_summary.lock_detail[].pool` | "0x0000000000000000000000000000… | string | 0/5 | SOL 1/1 · RH 2/1 · BASE 1/1 · ETH 1/1 |
| security | `lock_summary.lock_percent` | "0" | numeric-string | 0/4 · 0×3 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `lock_summary.lock_tags` | — | null | 4/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `open_source` | 1 | integer | 0/4 · 0×1 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `privileges` | — | array/null | 2/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `renounced` | 1 | integer/null | 1/4 · 0×1 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `renounced_freeze_account` | true | boolean | 0/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `renounced_mint` | true | boolean | 0/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `sell_tax` | "0" | numeric-string | 0/4 · 0×4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |
| security | `top_10_holder_rate` | "0.01" | numeric-string | 0/4 | SOL 1/1 · RH 1/1 · BASE 1/1 · ETH 1/1 |

### market kline（8 个路径，来源：Phase 2 raw，2026-10-02，四链共 120 根）

| Endpoint | Field | Example | Type | Null rate | Chains（出现/总行） |
|---|---|---|---|---|---|
| kline | `list[].time` | 1790899200000 | integer（Unix ms） | 0/120 | SOL 1/1 · RH 18/18 · BASE 1/1 · ETH 100/100 |
| kline | `list[].open` | "0.0000044178306" | numeric-string | 0/120 | 同上 |
| kline | `list[].high` | "0.000043607078" | numeric-string | 0/120 | 同上 |
| kline | `list[].low` | "0.0000044178306" | numeric-string | 0/120 | 同上 |
| kline | `list[].close` | "0.0000057961466" | numeric-string | 0/120 | 同上 |
| kline | `list[].volume` | "66339.25253781" | numeric-string | 0/120 | 同上 |
| kline | `list[].amount` | "4042136488.820541" | numeric-string | 0/120 | 同上 |
| kline | `list[].source` | "" | string | 0/120 · ""×120 | 同上 |

### 响应外壳

| Endpoint | Field | Example | Type |
|---|---|---|---|
| trending | `code` / `message` / `reason` / `data` | 0 / "success" / "" / `{rank:[…]}` | integer / string / string / object |
| hot | `[0].chain` / `[0].interval` / `[0].version` / `[0].tokens` | "sol" / "24h" / "C6D73F1E2E236120" / array | string / string / string（不透明，非时间）/ array |
| trenches | `new_creation` / `near_completion` / `completed` | array | array |
| signal | 根数组 | array | array |
| kline | `list` | array | array |
