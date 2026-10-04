# Recent Access Radar — 状态机与事件规则（核心层 v0.1）

本文件是 `radar_core.py` 的规则说明，代码与本文不一致时以测试 `test_radar_core.py` 为准。
所有时间为 **UTC 毫秒整数**；CLI 显示时转换为 UTC+8。

## 1. 对象：access（一个“可达性”）

一个 access = 某资产在某平台上以某种方式可达。唯一键：

```
(asset_key, platform_id, access_kind, quote, country, fiat, payment_method, network)
```

- `asset_key` 是**平台内身份**：默认 `sym:<SYMBOL>`，适配器可显式给 `ca:solana:<mint>`、`xstocks:AAPLx` 等。
  全局资产（`asset` 表，区分 AAPLx / AAPLon / NASDAQ:AAPL）通过 `asset_id` 属性关联，解析前后合并键不变。
- `access_kind`：SPOT / PERP / CATALOG / ALPHA / ROADMAP / FIAT_ROUTE / DEPOSIT_NETWORK / WITHDRAW_NETWORK /
  COLLATERAL / LENDING / CHAIN_DEPLOYMENT。
- 可选维度用 `''` 而不是 NULL（保证 UNIQUE 生效）。FIAT_ROUTE 的 `quote` 默认等于 `fiat`。
- FIAT_ROUTE 额外有 `fiat_tier`：SUPPORTED（资产/法币列表里有）< QUOTABLE（能拿到报价）< CONFIRMED（实测走通）。

## 2. 状态

| 状态 | 含义 |
|---|---|
| NONE | 系统内存在记录但从未可达（或临时新增被撤回） |
| ANNOUNCED | 只有公告/中继消息，结构化列表里还没出现 |
| LIVE | 结构化来源确认可交易/可用 |
| SUSPENDED | 仍在列表中但暂停（Coinone trade_status 0/2 或 maintenance、Korbit `stopped`、Ramp `enabled=false`/`hidden=true`、官方暂停公告） |
| REMOVED | 下架/移除 |

附加标记 **provisional**（不是独立状态）：状态已变化但证据不足，等待确认；可被确认（清除标记）或撤回（retract）。

## 3. 允许的迁移

| from \ to | ANNOUNCED | LIVE | SUSPENDED | REMOVED |
|---|---|---|---|---|
| NONE | ✅ | ✅ | ✅（上线即暂停） | ❌ |
| ANNOUNCED | — | ✅ | ✅ | ✅（公告取消） |
| LIVE | ❌ | — | ✅ | ✅ |
| SUSPENDED | ❌ | ✅ | — | ✅ |
| REMOVED | ✅（再上架公告） | ✅（重新上架） | ❌ | — |

- 同状态 = no-op（不产生事件）。
- ❌ 的迁移被拒绝：写入 `rejected_transition`，打 warning 日志，状态不变。
- 例外：LIVE/SUSPENDED 时收到“上币公告”——若 72h 窗口内存在同一 access 的 ADD episode，则视为**佐证**
  （晚到的中继，不回退状态）；否则按 LIVE→ANNOUNCED 拒绝并记录。
- 撤回（retract）是唯一绕过迁移表的回滚：provisional 新增在确认前消失 → 状态回到事件的 from_status，事件 `retracted=1`。
- 每次真实迁移都写 `access_transition`（append-only 审计）；baseline 的初始化也写一条（event_id 为空）。

## 4. 事件族与 event_type 推导

family 由 (from, to) 决定：

| 条件 | family |
|---|---|
| to=ANNOUNCED；或 to=LIVE 且 from∈{NONE,ANNOUNCED,REMOVED}；或 to=SUSPENDED 且 from≠LIVE | ADD |
| LIVE→SUSPENDED | SUSPEND |
| SUSPENDED→LIVE | RESUME |
| to=REMOVED | REMOVE |
| FIAT_ROUTE 在 LIVE 状态下 fiat_tier 升级 | TIER |

event_type = f(access_kind, from, to[, fiat_tier])：

| family / 情况 | event_type |
|---|---|
| ADD → ANNOUNCED | `<KIND>_ANNOUNCED` |
| ADD → LIVE（SPOT/PERP/ALPHA） | `SPOT_LISTED` / `PERP_LISTED` / `ALPHA_LISTED` |
| ADD → LIVE（其他） | `CATALOG_ADDED`、`ROADMAP_ADDED`、`CHAIN_DEPLOYED`、`DEPOSIT_ENABLED`、`WITHDRAW_ENABLED`、`COLLATERAL_ENABLED`、`LENDING_ENABLED` |
| ADD → LIVE（FIAT_ROUTE） | `FIAT_ROUTE_SUPPORTED` / `_QUOTABLE` / `_CONFIRMED`（按 tier） |
| REMOVED → LIVE | `<KIND>_RELISTED` |
| ADD → SUSPENDED | `<KIND>_LISTED_SUSPENDED` |
| SUSPEND / RESUME | `<KIND>_SUSPENDED` / `<KIND>_RESUMED`（DEPOSIT_NETWORK→`DEPOSIT_*`，WITHDRAW_NETWORK→`WITHDRAW_*`） |
| REMOVE（from LIVE/SUSPENDED） | `SPOT_DELISTED`/`PERP_DELISTED`/`ALPHA_DELISTED`，其他 `<KIND>_REMOVED` |
| REMOVE（from ANNOUNCED） | `<KIND>_ANNOUNCEMENT_CANCELLED` |
| 官方下架公告、生效时间在未来 | `<基础类型>_SCHEDULED`，真正下架时改写为基础类型 |
| TIER 升级 | `FIAT_ROUTE_<新tier>`；**降级静默更新，不发事件** |

一个 canonical 事件 = 一个 **episode**：同一 episode 内的推进（ANNOUNCED→LIVE）会更新同一行的 `to_status`
和 `event_type`，链接角色为 PROGRESS，而不是新开事件。消费方用 `updated_at` 捕捉推进。

## 5. 新增确认规则

| 来源 | 规则 |
|---|---|
| 官方结构化市场/资产列表（`add_confirm_obs=1`），且通过健康检查 | 1 次观测即 LIVE（非 provisional） |
| 其他快照来源（聚合器、第三方，`add_confirm_obs=2`） | 首次出现 → LIVE + provisional；下一次健康快照仍在 → 确认；确认前消失 → retract |
| 官方公告 LISTING | 只到 **ANNOUNCED**（不因公告直接 LIVE）；LIVE 必须来自结构化观测 |
| 第三方/中继公告 LISTING（NewListings） | ANNOUNCED + provisional；官方公告或结构化观测到达即清除 provisional |

ANNOUNCED 之后，结构化快照出现该市场 → ANNOUNCED→LIVE（同一 episode）。

## 6. 移除确认规则

| 情况 | 结果 |
|---|---|
| 健康快照中连续缺失 `remove_confirm_misses`（默认 3）次 | REMOVED |
| 可选：`remove_min_elapsed_ms` > 0 | 还要求首次缺失起至少经过该时长（Bithumb 2s 轮询时防止 6 秒内误删） |
| 官方下架公告，无生效时间或已过 | 立即 REMOVED（1 条官方下架即够） |
| 官方下架公告，生效时间在未来 | 写 `pending_removal_at`，生成 `*_SCHEDULED` REMOVE episode；生效后首次健康缺失或 `tick`（`process_due`）即 REMOVED，并合并进同一 episode |
| 第三方下架消息 | provisional REMOVE episode，**不改状态** |
| DEGRADED/DOWN 期间的缺失 | 不计数 |
| 同一 access 仍被其他来源（present 且 miss=0）看到 | 本来源标记缺席，但不触发 REMOVED |
| 快照内有被丢弃的无效条目（≤5%） | 本轮跳过缺失计数（避免把解析失败当成下架） |

### 6.1 无交易对（quote 为空）的下架 / 暂停 / 恢复公告 = 通配

交易所公告常常只写币种（“OMG 거래지원 종료”），不写市场。`ingest_announcement` 里 action 为 DELISTING / SUSPEND /
RESUME 且 quote 为空（`''`/NULL/缺省）时，quote 是**通配**：

- **作用对象**：同一 `(asset_key, platform_id, access_kind)`、且 country / fiat / payment_method / network 相同的
  **所有已存在且状态 ≠ NONE** 的 access_state，不论 quote（KRW、BTC、USDT……以及无交易对上币公告留下的 `''` 占位行）。
  NONE 行不算市场（例如旧版适配器按默认 quote 展开留下的空行），会被忽略。
- **逐行按原规则处理**（与带 quote 的公告完全相同）：官方下架且无生效时间/已过 → REMOVED；生效时间在未来 →
  每行写 `pending_removal_at` 并生成 `*_SCHEDULED` episode；第三方 → provisional REMOVE episode，不改状态；
  官方暂停 LIVE/ANNOUNCED → SUSPENDED；官方恢复 SUSPENDED → LIVE。
- **已是目标状态或不允许的行不产生噪音**：已 REMOVED 的行收到下架、已 SUSPENDED 的行收到暂停、已 LIVE 的行收到恢复、
  已 REMOVED 的行收到暂停/恢复——都只作为佐证并入该行已有的 episode（72h 窗口内有的话），**不写 rejected_transition**。
- **一行都没有**（从没见过这个币在该平台的任何市场）→ 与以前一样当作一个 quote=`''` 的单一目标：只建/用一行 `''`
  （不会按 quote 各建一行）；下架仍按 NONE→REMOVED 拒绝并记录一次（一个从未见过的币的下架公告本身值得留痕），
  暂停/恢复什么也不做。
- 迁移审计的 reason 带 `(quote wildcard)` 后缀；返回值 `result["wildcard"]` 列出每个通配目标实际作用到的 quote。

**事件粒度（选择：每个受影响的 quote 一个事件）**：`KRW-OMG` 与 `BTC-OMG` 的下架各自是一个 canonical episode，
因为它们是不同的 access，后续证据（各 quote 的快照缺失、带具体 quote 的公告、`tick`）本来就按 quote 合并；
做成一个 asset 级事件会让“只下 BTC 市场”这类情况无法表达，也会破坏 §9 的合并键。“合并得当”体现在：

- 通配公告只写**一条** observation（quote=`''`，access_id 为空，即来源原话），它以 ORIGIN/CORROBORATE 链接到每个
  受影响 quote 的 episode，`access_transition.obs_id` 也指向它——消费方可按 obs_id（或 source_event_id）把同一条
  公告产生的多个 quote 事件归为一组展示。
- 另一来源再发同一条（无论带不带 quote）只会佐证对应 quote 的 episode，不会新开事件；带具体 quote 的消息只并入该 quote。
- `''` 占位行排在具体 quote 之后处理，并入具体 quote 的 episode，不单独产生事件；只有占位行（只公告过、从未上线）时，
  才在 `''` 上产生 `<KIND>_ANNOUNCEMENT_CANCELLED`。
- 定时下架：每行各自 `pending_removal_at`；生效后各 quote 的首次健康缺失或 `tick`（`process_due`）把该行移除，
  并合并进该 quote 的 `*_SCHEDULED` episode（`process_due` 也能找到 access_id 为空的通配下架 observation）。
- `resolve_ref` 确认公告来源的 ref 时，资产 id 会传播到该通配 observation 覆盖的所有 quote 行。

快照摄入不做通配：快照条目里的 `quote=''` 就是一个真实的键（例如没有交易对的充提网络）。

**暂停不是移除**：映射规则（`radar_core.map_*`）：

- Coinone `trade_status` 1/3 → LIVE，0/2 → SUSPENDED；`maintenance_status=1` → SUSPENDED（写适配器时再次核对值含义）。
- Korbit `/v2/currencyPairs` `status=stopped` → SUSPENDED。
- Ramp：必须带 `withDisabled=true&withHidden=true` 拉取，`enabled=false` → SUSPENDED；`hidden=true` → SUSPENDED（判断性选择：隐藏但仍存在，按暂停处理而不是移除）。

## 7. 健康门控（每个 source + scope）

处理顺序：**校验 → 健康 → baseline 或 diff → 状态更新 → 事件**。

1. **Schema 校验**：每条必须有已注册 platform、symbol/asset_key、合法 access_kind、状态 LIVE/SUSPENDED，FIAT_ROUTE 必须有 fiat。
   无效比例 > 5% → `schema_ok=0`、DEGRADED、暂停 diff；≤5% → 丢弃无效条目继续，但本轮不计缺失。
2. **规模检查**：与上次被接受的规模比较，`|Δ| > max(20% × last, size_min_abs=3)` → DEGRADED、暂停 diff（不新增、不移除、不计缺失）。
   - 返回 0 条（之前非空）→ 永远 DEGRADED，不会自动接受。
   - 连续 3 次异常且彼此规模一致（非空）→ 接受新规模（outcome=SIZE_ACCEPTED）并正常 diff；缩水因此只会开始缺失计数，仍需再 3 次健康缺失才 REMOVED。
3. 适配器抓取失败 → `report_fetch_error` → DOWN。WebSocket 断线 → `mark_disconnected` / `mark_reconnected`
   写 `source_disconnect` 区间，适配器据此用 REST/History 补数。
4. 恢复正常快照 → HEALTHY。

## 8. Baseline

- 每个 **(source, scope)** 第一份健康、非空快照 = baseline：静默建立状态，**不发任何事件**，写 `source_scope_baseline`。
- 已有状态（由其他来源建立）在 baseline 中保持不变。
- 之后新增的 scope（例如 Upbit 新开 BTC 市场 scope、Ramp 新增国家）有自己的 baseline，同样不发事件。
- 若某状态是 ANNOUNCED 而新来源的 baseline 已显示 LIVE：baseline 不动它，下一次 diff 时推进为 LIVE（产生事件）。

## 9. 跨来源合并

- 合并键：`(asset_key, platform_id, access_kind, quote)` + 相同 family + **72h 窗口**。
  窗口以 episode 的 `anchor_at`（最早已知时间）或 `effective_at` 为中心，因此提前一周公告的下架也能与真实下架合并。
- `quote=''` 是通配：无交易对的公告（“将上线 ZORA”）可与之后的 KRW-ZORA 合并；episode 随之绑定到 `KRW`，
  占位的 `''` 状态被提升为 LIVE。无交易对的下架/暂停/恢复公告作用于所有已存在的 quote，见 §6.1。FIAT_ROUTE 的 quote=fiat，所以同一法币多个国家合并成一个事件。
- 每个观测通过 `event_observation_link` 链接（ORIGIN / PROGRESS / CORROBORATE / CONFIRM / RETRACT）。
- 公告幂等：`(source_id, source_event_id)` 已存在则忽略。NewListings 各端点的事件 ID 不稳定，适配器必须自建
  稳定 ID（如 `nl:<exchange>:<symbol>:<type>:<quote>`）。

### 9.1 展示分组 `group_key` 与链接 `url`

`access_event.group_key`（有索引 `ix_event_group`，永不为 NULL）只用于**展示分组**，不参与合并：

| 事件是怎么建出来的 | group_key |
|---|---|
| 由公告创建（ORIGIN 是一条公告观测） | `ann:<source_id>:<source_event_id>:<asset_key>`，例如 `ann:upbit_notice:upbit:notice:5101:sym:OMG` |
| 其他（快照 diff、`tick`、手动迁移……） | `ev:<event_id>`（自己一组） |

- 因此同一条公告对同一资产产生的多个事件共用一个 key：无交易对公告通配到 KRW/BTC/USDT（§6.1），以及标题里明确
  写了多个市场的上币公告（KRW、BTC、USDT 各一个事件）。同一公告里的不同币种各自一组（key 含 asset_key）；
  key 请当作不透明字符串（source_event_id 和 asset_key 本身都含 `:`）；要按整条公告分组，用链接观测的
  `source_observation.source_id + source_event_id`。
- group_key 在事件创建时确定，之后不变：快照先建的事件即使后来被公告佐证，仍是 `ev:<event_id>`。
- 老库迁移时按同一规则回填（ORIGIN 观测是带 source_event_id 的公告 → `ann:…`，否则 `ev:<event_id>`）。

`source_observation.url`：公告 dict 的 `url` 键（target 级 `url` 优先；兼容 `pc_url`）；没有则 NULL（快照观测通常为 NULL）。
`v_recent_feed.url` = 该事件链接观测里的代表链接：公告观测优先，其次 ORIGIN，再按 obs_id；都没有则 NULL。

### 9.2 `v_recent_feed` 列

前 23 列与 v0.1 相同且顺序不变：`event_id, anchor_at, event_type, platform_id, asset_key, quote, from_status, to_status,
fiat_tier, confidence, independent_source_count, provisional, retracted, announced_at, source_detected_at, observed_at,
effective_at, live_observed_at, poll_prev_at, asset_id, asset_symbol, asset_type, obs_count`。之后追加：
`access_id, access_kind, family, group_key, first_source_id, updated_at, network, country, fiat, payment_method,
current_status`（access_state.status）`, pending_removal_at, g_asset_key`（全局资产 asset_key）`, asset_name, ref_id,
ref_source_id, platform_symbol, native_id, resolution_status, resolution_source, suggested_asset_id, url`。
ref 选取：该 access 或该事件的观测所带 ref 中最强的（CONFIRMED > SUGGESTED，同级取最小 ref_id），都没有则
`access_state.ref_id`。`asset_id` 为空表示还未 CONFIRMED（SUGGESTED 只在 `suggested_asset_id`）。

## 10. 置信度

```
independent_source_count = 链接观测中不同 independence_group 的数量（RETRACT 不计）
confidence = 1 − Π_g (1 − w_g)，w_g = 该组内观测来源 tier_weight 的最大值
```

tier 权重：OFFICIAL_STRUCTURED 0.95，OFFICIAL_ANNOUNCEMENT 0.85，THIRD_PARTY 0.60，AGGREGATOR 0.50，LLM_EXTRACTED 0.30。

- 每个 source 默认独立组 = source_id。`is_relay=1` 的来源（NewListings）可在每条消息上带 `origin_group`，
  转述 Upbit 公告时记为 `upbit_notice` 组 → NewListings + Upbit 公告 = **1** 个独立来源；再加 Upbit 市场列表
  （`upbit_market` 组）= **2**。
- source（谁告诉我们）与 platform（发生在哪）分开：一个 source 可以报告多个 platform。

## 11. 时间语义（全部 UTC ms）

| 字段 | 含义 |
|---|---|
| announced_at | 公告自身的发布时间（Bithumb `published_at` 无时区，适配器须按 KST 转换） |
| source_detected_at | 来源方发现的时间（如 NewListings 的检测时间，FREE 版有 3s 延迟） |
| observed_at | 我方首次入库时间 |
| effective_at | 公告给出的开盘/生效/下架时间，可在未来 |
| live_observed_at | 首次在结构化快照中看到目标状态的时间（REMOVE：首次缺失时间） |
| poll_prev_at | 上一次健康轮询时间；真实变化发生在 `(poll_prev_at, live_observed_at]` 区间内（REMOVE：上次看到的时间） |
| anchor_at | episode 最早已知时间 = min(announced_at, source_detected_at, observed_at)，用于排序与 72h 窗口 |
