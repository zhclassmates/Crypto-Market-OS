# V1 Field Integration

> 依据：`gmgn-field-capability-map.md` §24 / §25。只建立数据底座：不做爆款评分、不重构 UI、
> 不新增 GMGN endpoint、不 commit、**不部署**（生产 collector 未重启；生产 `market.sqlite` 的 schema 仍是 36 列，没有 V1 列）。

## 结论

**V1 FIELD INTEGRATION: PARTIAL**

- **数据链路 `GMGN raw → collector → DB → API`：12 个 V1 字段全部 PASS。** 使用真实 raw：四链 Trending / Trenches / Security，SOL Hot，SOL / RH Signal（BASE / ETH 不支持 Signal）。验证在生产库副本上完成。
- 仍然缺的层（这是 PARTIAL 的全部原因）：

| 缺失层 | 影响字段 | 说明 |
|---|---|---|
| **生产部署** | 全部 12 个 | 新代码未上线：生产 DB 没有 V1 列，生产 API 对 V1 字段返回 `null`。需要重启 `com.market.collector`（会同时上线未部署的 Phase 4 修改），由你决定。 |
| **UI 消费** | 11 个（除 `is_honeypot`） | 只有 `securityIsHoneypot` 被 UI 使用（Phase 4 加的 Security 标记）。buys / sells / swaps / pc_1h / wash / renounced_* / sell_tax / signal trigger / rank 目前只到 API。按本阶段要求没有改 UI。 |

真实数据中**从未观察到**的取值（不是集成失败，只是证据边界）：`is_wash_trading = true`（1,122 行全部是 false）、`is_honeypot = true`，以及 Hot 在 RH / BASE / ETH 的 raw（Hot 与 Trending 字段与 schema 相同，已用四链 Trending 覆盖）。

## 1. 上一轮为什么绕过了 shared cooldown

共享限流实现在 `rh_v2/market_sched.py`，网络调用入口是 `rh_v2/market_collect.py:gmgn()`：

- `gmgn()` 请求前调用 `sched.guard_or_raise()`；失败时调用 `sched.observe_error()`，遇到 429 / `RATE_LIMIT_*` 时用 `arm_cooldown()` 把 `gmgn_cooldown_until/start/step/basis` 写进 `market_meta`。
- `_state` 是**进程内缓存**，`ensure_loaded()` 每个进程只从库里读一次。

上一轮验证脚本的三个问题：

1. **直接 `subprocess` 调 `gmgn-cli`**，完全没经过 `gmgn()`：请求前不检查冷却，限流时也不武装共享冷却。
2. 只在开始前检查过一次冷却。即使走 `gmgn()`，进程内缓存也看不到生产 collector 之后新武装的冷却。
3. 当初绕开的原因是 `arm_cooldown()` 走 `market_db.connect()`，而 **`connect()` 会执行 `market_research.migrate()`**。在当前工作区代码下，一次 429 就会把未部署的 Phase 4 / V1 列写进生产库。

## 2. 修复：验证脚本复用同一套机制（未改业务代码）

`scripts/v1-verify-fetch.py`：

- 每次请求都调用 `market_collect.gmgn()`，因此 `guard_or_raise()` 和 `observe_error()` 都生效，限流会写入**同一个**共享冷却。
- **每次请求前**用只读连接 `sched.load_cooldown()` 从库里重新加载共享冷却；同时检查生产任一 `gmgn*` 车道最近 120 秒内是否 `rate_limited`。任一满足就停止，不发请求。
- `sched.db` 替换为只写 `market_meta` 的连接（`_MetaOnlyDb`）：共享冷却照常写入生产库的 4 个 `gmgn_cooldown_*` key，但不执行 SCHEMA / migrate。实测生产 `token_snapshot` 在整个过程中保持 36 列。
- 串行；请求间隔至少 20 秒；遇到限流或任何错误立即停止，不重试。
- 已存在的 raw 文件跳过；每个成功的 payload 立即落盘到 `docs/gmgn-audit/raw/v1/`，并记入 `_log.json`。

`scripts/v1-verify-apply.py`：不发请求。把已保存的 raw 原样走 collector 代码（`fetch_trending` / `fetch_hot` 的网络调用替换为已保存 raw；`apply_hot_items`、`apply_trench_payload`、`apply_signal_items`、`write_security_snapshot`、`write_gmgn_rows`），写入生产库**副本**，逐字段核对 raw → DB。副本中删除了首次抓取所在桶之后的 15,866 条 discovery_event，避免生产同桶事件因去重键冲突吞掉验证写入；这一步只在副本里做。

### 本轮请求账本

| 时间 | 请求 | 结果 |
|---|---|---|
| 10:52:14 / 10:52:17 | 上一轮直连：SOL Trending ✓ / SOL Hot ✗ 429 BANNED | 上一轮事件，保留 SOL Trending raw，**未重抓** |
| 11:39:39–11:40:43 | SOL Hot、SOL / RH / BASE Trenches | 4 × 成功 |
| 11:40:43 之后 | — | 生产 collector 武装了共享冷却 → 脚本**在发出 ETH Trenches 之前停止**，没有请求 |
| 11:43:48–11:45:55 | ETH Trenches、SOL / RH Signal、四链 Security | 7 × 成功（冷却 + 120 秒静默期后续跑，已存在的文件跳过） |
| 11:47:54–11:48:37 | RH / BASE / ETH Trending（补四链 pc_1h） | 3 × 成功 |

本轮共 **14 次**请求，**0 次限流**，1 次因共享冷却而主动停在请求前。

## 3. 逐字段验证（V1 FIELD SET）

"数据链路"列 = raw → collector → DB → API 是否全部一致；"整体"列同时考虑部署和 UI。

| 字段 | 来源 endpoint | raw 真实存在 | 代码读取 | DB 保存（副本） | API 暴露 | UI 使用 | 数据链路 | 整体 |
|---|---|---|---|---|---|---|---|---|
| buys | Trending ×4 链、Hot SOL（`buys`）；Trenches ×4 链（`buys_24h`） | 是：T 400/400、H 98/98、Tr 624/624 | 是（`snapshot_patch`） | `buys_24h` + source / updated_at；事件元数据 | `buys24h` | 否 | **PASS**（raw=DB 1,122/1,122；DB=API 1,134/1,134） | PARTIAL |
| sells | 同上（`sells` / `sells_24h`） | 是 | 是 | `sells_24h` + source / updated_at | `sells24h` | 否 | **PASS** | PARTIAL |
| swaps_24h | 同上（`swaps` / `swaps_24h`） | 是；`swaps = buys + sells` | 是（Trench 经 `normalize_trench_row`） | `swaps` + `swaps_source` / `swaps_updated_at` | `swaps24h`、`activitySource`、`activityUpdatedAt` | 否 | **PASS** | PARTIAL |
| volume 24h | Trending / Hot（`volume`）、Trenches（`volume_24h`） | 是 | 是 | `volume_24h` + source / updated_at | `volume24h`、`volume24hSource` | **是**（`volume24h` 已在表格中显示） | **PASS** | PARTIAL（缺部署） |
| price_change_percent1h | Trending ×4 链、Hot SOL | 是：500/500 + 98/98（RH 3、BASE 4、ETH 1 个真实 0） | 是 | `pc_1h`（TEXT）+ source / updated_at | `pc1h`、`pc1hUpdatedAt` | 否 | **PASS** | PARTIAL |
| is_wash_trading | Trending ×4、Hot SOL、Trenches ×4 | 是：1,122 行，全部 `false` | 是（只接受 boolean） | `is_wash_trading`（0 / 1 / NULL）+ source | `isWashTrading` | 否 | **PASS**（`true` 在真实数据中未出现，只有单测覆盖） | PARTIAL |
| signal trigger_at | Signal SOL / RH | 是：SOL 50 / 50，RH 45 / 45（另有 5 条同类型重复被去重） | 是（`parse_signal_items`） | `discovery_event.metadata_json.trigger_at` | `lastSignalTriggerAt` | 否 | **PASS** | PARTIAL |
| signal trigger_mc | Signal SOL / RH | 同上 | 是 | `metadata_json.trigger_mc` | `lastSignalTriggerMc` | 否 | **PASS** | PARTIAL |
| is_honeypot | Security ×4 | 是：SOL `null`，RH / BASE / ETH `false` | 是 | `security_is_honeypot` | `securityIsHoneypot` | **是**（Security 标记） | **PASS** | PARTIAL（缺部署） |
| renounced_mint | Security ×4 | 是：SOL `true`，其余 `false` | 是 | `security_renounced_mint` | `securityRenouncedMint` | 否 | **PASS** | PARTIAL |
| renounced_freeze_account | Security ×4 | 是：SOL `true`，其余 `false` | 是 | `security_renounced_freeze_account` | `securityRenouncedFreezeAccount` | 否 | **PASS** | PARTIAL |
| sell_tax | Security ×4 | 是：四链都是 `"0"` | 是（原样字符串） | `security_sell_tax` | `securitySellTax` | 否 | **PASS**（刻度未编码） | PARTIAL |

保留字段核对（同一批 raw）：

| 字段 | raw → DB | DB → API | UI |
|---|---|---|---|
| rank（Trending / Hot） | 498/498 一致（事件表） | `trendingRank` / `hotRank` 1,134/1,134 | 否（新 API 字段） |
| price / liquidity / market_cap / holder_count | 一致（上一轮 SOL 已逐行核对） | 一致 | 是 |
| creation_timestamp | 经 `db.rank_times` 写 `tokens` | `tokenCreatedAt` | 是 |
| daily candles | 本轮未请求（V1 不涉及），Phase 3 已 PASS | `changeNd` / `streak` | 是 |

**DB → API**（`fetchMarketRank`，临时 dev server 指向副本，传入 1,134 个本轮涉及的 token）：20 个 V1 API 字段 × 1,134 个 token 全部与副本 DB 一致（`raw/v1/verify_api.json`）。

## 4. null / 0 / unknown 区分（真实数据验证）

| 状态 | 真实证据 |
|---|---|
| 合法 0 | `pc_1h` 在 RH / BASE / ETH 共 8 个真实 0 → `"0"`；Trenches `sells_24h` 有 254 个 0 → `0`；四链 `sell_tax="0"`；wash `false` → `0` → `false` |
| 显式 null | SOL Security `is_honeypot: null` → NULL → `null`（不是"安全"） |
| endpoint 不支持 | Trenches 无 `price_change_percent1h` → 只出现在 Trenches 的 token，`pc1h=null` 且 `pc1hUpdatedAt=null`（API 中 SOL 146 个 token 有 pc1h，323 个有活跃度）；BASE / ETH 不请求 Signal → `lastSignal*` 全为 null |
| 尚未观察到 | 生产历史中旧代码写入的 signal 事件：API 中 169 个 token 有 `lastSignalType`，只有 81 个有 `lastSignalTriggerAt`，其余 88 个是旧事件，没有 trigger 字段；2 个 token 有旧代码写的 `swaps` 但 `activitySource=null` |
| 缺 key 不覆盖 | 单测 `test_missing_keys_stay_unobserved`、`test_signal_does_not_touch_activity_and_keeps_trigger` |

读 API 的规则：值为 null 时看对应的 `*Source` / `*UpdatedAt`。两者都是 null 表示"从未观察到"；有 source 而值为 null 表示"来源明确返回 null"。

## 5. 已知限制（不影响 PASS，必须知道）

1. **同一 token、同一 `signal_type` 在一个 5 分钟桶内只保留一条事件**（去重键）。真实 RH payload 中有 5 条这样的重复。GMGN 返回顺序是最新在前，落库的是最新一条；同桶内较早的触发会丢失。
2. `sell_tax` 刻度未编码，不能直接做阈值。
3. `buys` / `sells` / `swaps` 是**笔数**；`holder_count` 是当前持币地址数，不是新增钱包。V1 没有接 `smart_degen_count`。
4. Trending / Hot 内嵌的同名风险字段没有接：类型与 Security endpoint 不一致。
5. 活跃度历史以事件元数据保存，只在 token 出现在发现源时才记录，不是固定频率快照。
6. `RH_MARKET_DB` 环境变量覆盖（`market-server.ts:30`）是为离线验证加的，默认行为不变。

## 6. 回归

本轮没有改业务代码，只新增两个验证脚本。上一轮的结果仍然有效：Python 54/54、TypeScript 54/54、oracle 一致、`tsc` / `build` 通过。

## 7. 要到 COMPLETE 还差什么

1. **部署**（需要你批准）：重启 `com.market.collector`。等一个完整采集周期后，用**只读**查询核对生产库的 V1 列与 `*_source`，不需要额外的 GMGN 请求。
2. **UI 消费**：把 11 个字段接进排行 / 详情 / 告警的展示层。这属于下一阶段，本阶段按要求不改 UI。

## 8. 证据文件（`docs/gmgn-audit/raw/v1/`）

| 文件 | 内容 |
|---|---|
| `{chain}-{endpoint}.json` | 15 份真实 raw（四链 Trending / Trenches / Security，SOL Hot，SOL / RH Signal） |
| `_log.json` | 全部请求的时间、参数、结果，以及是否经过 `market_collect.gmgn` |
| `verify_db.json` | 逐 endpoint × chain × 字段的 raw → DB 核对（present / null / zero / true / 一致数） |
| `verify_api.json`、`api-all.json` | DB → API 核对，以及按链统计的 API 非空计数 |
| `api-sol-trending.json`、`apply_result.json`、`api_compare.json` | 上一轮 SOL Trending 的结果 |
