# Recent Access Radar

## 适配器接口（最终版，所有适配器按此实现）

适配器 = `access_radar/adapters/<name>.py` 里的一个模块。**适配器不直接写正式库**：它只负责抓取 + 映射，
运行器（`access_run.py` → `access_sched.Runner`）通过唯一的写线程（`access_db.Writer`）写入 `radar_core`。
支持两种写法，任选其一：

### A. 原生写法（推荐）

```python
# adapters/example.py —— 单来源模块
SOURCE_ID  = "upbit_market"                 # 必须与 access_sched.CATALOG 中的 source_id 一致
KIND       = "snapshot"                     # "snapshot" | "announcement" | "stream"
PERIOD_SEC = 30                             # 可选；CATALOG 里有该来源时以 CATALOG 为准
PLATFORMS  = [{"platform_id": "upbit", "name": "Upbit", "platform_type": "CEX", "country": "KR"}]
SOURCE     = {"tier": "OFFICIAL_STRUCTURED", "origin_platform_id": "upbit"}   # radar_core.register_source 的参数
HEARTBEAT_SEC = 60                          # 仅 stream：超过该时长没有 ctx.heartbeat() 就要求重连

def fetch(http):                            # snapshot / announcement
    ...
def run(ctx):                               # stream
    ...
def backfill(http, since_ms, until_ms):     # 可选：断线区间的公告补数 -> [announcement, ...]
    ...
```

一个模块提供多个来源时用 `SOURCES`（键同上，小写）：

```python
SOURCES = {
    "upbit_market": {"kind": "snapshot", "fetch": fetch_markets},
    "upbit_notice": {"kind": "stream", "run": run_notice_ws, "backfill": backfill_notices, "heartbeat_sec": 60,
                     "source": {"kind": "ANNOUNCEMENT", "tier": "OFFICIAL_ANNOUNCEMENT", "origin_platform_id": "upbit"}},
}
PLATFORMS = [...]          # 模块级 PLATFORMS 作为所有 SOURCES 的默认值
```

返回值约定：

| KIND | 调用 | 返回 |
|---|---|---|
| snapshot | `fetch(http)`，按周期 | `{scope: [item, ...]}`；直接返回 list 视为 scope `"default"`。每个 scope 必须是**完整列表**（缺失会计 miss）。某个 scope 的值可以是 `Exception` 实例 → 只把该 scope 记为 DOWN。条目格式见下文 `ingest_snapshot`。 |
| announcement | `fetch(http)`，按周期 | `[announcement, ...]`（`ingest_announcement` 格式）。`source_event_id` 必须稳定，重复轮询同一条公告是幂等的。 |
| stream | `run(ctx)`，常驻线程 | 连接期间阻塞；断线时 return 或 raise。运行器记录断线区间、1s→30s 指数退避重连（连接稳定 60s 后退避复位），重连后用 `backfill` 补该区间。 |

`ctx`（stream）：`ctx.connected()`（握手/订阅成功后调用一次）、`ctx.heartbeat()`（每条消息/pong 调用）、
`ctx.should_stop()`（接收循环里轮询：停止或心跳超时）、`ctx.emit_announcement(ann)`、`ctx.emit_snapshot(scope, items)`、
`ctx.http`、`ctx.source_id`、`ctx.log`、`ctx.stop_event`。标准库没有 WebSocket 客户端，适配器需自带最小实现，
接收要设超时以便轮询 `should_stop()`。

`http` 是共享的 `access_http.HttpClient`：`http.get_json(url, params=None, headers=None)`、`http.post_json(url, body)`、
`http.get_text(url)`。按 host 限速、熔断、4xx 不重试、5xx/超时退避重试；失败抛 `HttpError` / `CircuitOpen` / `TransportError`。
`fetch()` 抛异常 = 本轮失败（`source_run` 记错误，该来源已知 scope 记 DOWN，不会产生 REMOVE）。

### B. conn 写法（`adapters/ramp.py`、`adapters/xstocks.py` 当前使用）

```python
SOURCE_ID = "ramp_assets"                                  # 不写 KIND
def register(conn, at=None): ...                           # 可选：注册 platform + source
def run_once(conn, fetch=None, fetched_at=None):           # -> {scope: ingest 结果 | {"error": msg}}
    d = fetch(url)                                         # fetch(url, headers=None) -> 解析后的 JSON
```

运行器传入基于共享 HttpClient 的 `fetch`。为了不让网络 I/O 占住唯一写线程，运行器先在来源线程里用一个临时
内存库跑一遍 `run_once` 并录下所有 fetch（网络在这里发生），再在写线程里对正式库重放（只用录下的响应，不联网）。
因此 `run_once` 必须只通过 `fetch` 联网、只通过传入的 `conn` 写库，且对同一组响应的行为是确定的。`SOURCES` 条目
也可以用 `"run_once"` / `"register"` 键。

### C. 维护任务（maintenance，不是数据来源）

`CATALOG` 里 `kind="maintenance"` 的条目，例如 `Entry("resolve", 3600, "resolve", kind="maintenance")`（每小时一次的身份解析）。
它不建 `source` 行，也不建雷达的 `source_health` 行；运行记录写在运行器表 `maintenance_run` 里，`status` 单独显示在
"maintenance" 一节。每个任务有自己的线程 `access-maint-<job_id>`，周期从开始时计，分两步执行：

```python
def prepare(http): ...            # 任务线程：只联网，返回 payload（不碰库）
def apply(conn, payload): ...     # access-writer 线程：只写库，返回结果 dict（会以 JSON 存进 last_result）
```

- 结果里任何以 `error` 结尾、值非空的键（例如 `alpha_error`），或任一步抛出异常，都算这次运行失败
  （更新 consecutive_errors / last_error，不更新 last_success）。
- `resolve.py` 不需要改：运行器内置一个适配层，`prepare` 调用 `resolve.fetch_alpha(http)`（共享 HttpClient），
  `apply` 调用 `register_alpha(conn, tokens)` 和 `resolve_pending(conn, alpha_tokens=tokens)`。语义与 `resolve.run`
  一致：Alpha 拉取失败时解析照常对现有资产表跑一遍，但这次运行记为失败（带 `alpha_error`）。
- 模块不存在 → 跳过并打一行日志（MISSING），运行器照常工作；模块存在但没有 `prepare`/`apply` → ERROR。
- `once` 只跑数据来源，不跑维护任务；手动跑一次用 `access_run.py maintenance [job ...]`。

### 运行器保证

- 每个来源一个线程，周期从**请求开始**计；`CATALOG`（`access_sched.py`）给出周期：Bithumb 公告 2s、交易所市场列表
  30–60s、Korbit 网络/公告 60s、xStocks 10min、Ramp 20min、Onramper/Transak 30min、Ondo 30min、Circle/Superstate 6h；
  stream 来源（`upbit_notice`、`newlistings`）周期为 0。
- 模块文件不存在 → 跳过并打一行日志（状态 MISSING），运行器照常工作；模块导入失败 → ERROR；模块存在但没有该
  source_id → NO_SOURCE（日志列出模块实际提供的 id）。`adapters/` 里声明了 CATALOG 之外来源的模块会被自动发现并用其 `PERIOD_SEC` 调度。
- stream 断线区间（`source_disconnect`）：重连时对 `backfilled=0` 的已关闭区间调用 `backfill(http, since, until)`
  （最旧优先、每轮最多 3 个、只补 7 天内结束的区间）；失败写入 `source_run.last_error` 和 `source_health.last_error`
  （"backfill failed for gap …"），由 `access-backfill` 线程每 5 分钟重试，成功后置 `backfilled=1`、清掉该错误。
- 所有写库都在 `access-writer` 线程里串行执行；读（status/feed/UI）用独立连接（WAL）。
- 条目里出现未注册的 platform_id 会自动注册为 `OTHER` 并告警——请在 `PLATFORMS` 里声明。

---

独立的 `access.sqlite`，检测“可达性”结构变化（新上币、法币通道、新链部署、代币化股票/RWA 等），之后喂给 GMGN。
纯 Python 3 标准库（sqlite3 + urllib），SQLite ≥ 3.37（STRICT 表）。

## 文件

| 文件 | 说明 |
|---|---|
| `schema.sql` | 领域表结构（WAL、外键、STRICT） |
| `STATE_MACHINE.md` | 状态机、迁移表、event_type 推导、确认/移除/健康/baseline/合并/置信度/时间语义 |
| `radar_core.py` | 核心库（状态机、快照/公告摄入、跨源合并）+ 演示 CLI |
| `access_db.py` | `DB_PATH`（env `ACCESS_DB`，默认本目录 `access.sqlite`，见下“库路径”）、`connect()`、单写线程 `Writer`、`with_db()`、运行器表 `source_run` / `runner_meta` / `maintenance_run` |
| `access_http.py` | HTTP 客户端（按 host 限速、熔断、重试、代理 `ACCESS_PROXY`、UA `ACCESS_UA`；发送 `Accept-Encoding: gzip, deflate` 并解码；正文分块读到 EOF 并核对 Content-Length，截断/断连/RST 视为临时错误最多重试 3 次；超时 `ACCESS_HTTP_TIMEOUT`=20s 是每次 socket 读写的超时，不是总时长；可选 `deadline=` 秒数为每次尝试的总时长上限，超时按一次临时失败计）。不叫 `http.py`：同目录的 `http.py` 会遮蔽标准库 `http` 包，导致 urllib 全部失效 |
| `access_sched.py` | `CATALOG`、适配器加载/发现、每来源线程、stream 监督（心跳看门狗、退避重连、断线区间、补数）、维护任务（`load_maintenance`、`run_maintenance`） |
| `access_run.py` | 入口：`once` / `loop` / `status [--json]` / `feed --window` / `tick` / `maintenance [job ...]`，fcntl 锁，日志 |
| `com.access.collector.plist` | launchd KeepAlive 配置（`__REPO__` 占位符，安装时替换） |
| `test_radar_core.py`、`test_runner.py` | 单元测试（模拟数据 / 假适配器 / 本地 HTTP 服务器，不访问外网） |

## 运行

```bash
cd access_radar
python3 -m unittest test_radar_core test_runner        # 核心 + 运行器测试
python3 access_run.py once                              # 每个轮询适配器跑一轮 + tick，输出 JSON
python3 access_run.py loop                              # 常驻（launchd 用这个）
python3 access_run.py status                            # 每个来源：适配器状态、时钟状态、各 scope 健康、断线区间
python3 access_run.py status --json
python3 access_run.py feed --window 24h                 # 1h | 6h | 24h | 3d | 7d，时间显示 UTC+8
python3 access_run.py feed --window 3d --json
python3 access_run.py tick                              # 执行已到生效时间的官方下架
python3 access_run.py maintenance resolve               # 手动跑一次维护任务（不写 job 名 = 全部）；loop 持锁时拒绝（exit 3），未知 job 名 exit 2
python3 access_run.py --db /tmp/x.sqlite status         # 指定库
python3 radar_core.py --db demo.sqlite demo --reset     # 不联网的模拟数据演示
```

- 库路径：所有入口（`access_run.py`、`access_db.py`、`radar_core.py` CLI、`resolve.py`、`ops/nightly.py`）都读 `ACCESS_DB`，
  未设置时回退旧名 `ACCESS_RADAR_DB`（仅为兼容），再默认 `access_radar/access.sqlite`——相对本包目录，与 cwd 无关
  （`rc.default_db_path()`）。`--db` 优先于环境变量。
- 升级：`radar_core.init_db`（`access_db.connect` 也会调用）对老库幂等迁移：补 `access_event.group_key`、
  `source_observation.url` 列，回填 group_key，建 `ix_event_group`，`v_recent_feed` 缺列时重建。
- 锁：`loop`/`once`/`maintenance` 持有 `logs/access_collector.lock`（env `ACCESS_LOCK`）；第二个实例直接退出（loop 先睡 20s，避免 launchd 空转）。
- 日志：`logs/access.log`（滚动，env `ACCESS_LOG_DIR`、`ACCESS_LOG_LEVEL`）+ stderr。
- 状态口径同 rh_v2：轮询来源 LIVE / DELAYED（>周期+2s）/ STALE（>2×周期+2s、本轮失败或从未成功）/ FAILED（连续 3 次失败且从未成功）；
  stream 来源 LIVE / DELAYED（心跳超时）/ DOWN（断开）；适配器不可用时 MISSING / ERROR / NO_SOURCE / NOT_STARTED。
  失败只更新 last_attempt / consecutive_errors / last_error，不动 last_success。
- launchd：见 plist 顶部注释（`sed "s#__REPO__#$(pwd)#g"` 安装，先 `mkdir -p access_radar/logs`）。

## radar_core 摄入格式（适配器返回的条目）

快照条目字段：`platform_id`（默认 source 的 origin_platform_id）、`symbol` 或 `asset_key`、`access_kind`、
`status`（LIVE/SUSPENDED）、`quote`、`country`、`fiat`、`payment_method`、`network`、`fiat_tier`、
`native_id`、`chain`/`contract`（可选，用于自动解析到全局资产）、`origin_group`（仅中继来源）、`source_detected_at`、`raw`。

公告：

```python
{
    "action": "LISTING",            # LISTING / DELISTING / SUSPEND / RESUME
    "platform_id": "upbit",
    "targets": [{"symbol": "REZ", "quote": "KRW", "access_kind": "SPOT"}],
    "announced_at": ..., "source_detected_at": ..., "observed_at": ..., "effective_at": ...,   # UTC ms
    "source_event_id": "upbit:notice:5101",   # 必须稳定；NewListings / Bithumb 需自建
    "url": "https://upbit.com/service_center/notice?id=5101",   # 可选：公告详情页（Bithumb 传 pc_url 的值）
    "origin_group": None,                     # NewListings 转述 Upbit 时填 "upbit_notice"
    "raw": msg,
}
```

- `url`（可选）：公告详情页链接，存进 `source_observation.url`，`v_recent_feed.url` 取它作为事件的代表链接。
  键名就是 `url`（顶层；单个 target 也可带自己的 `url` 覆盖顶层）。为兼容也接受 `pc_url`，但请统一传 `url`。
  快照条目一般没有链接，快照观测的 `url` 为 NULL。
- 同一条公告产生的事件共享 `access_event.group_key = 'ann:<source_id>:<source_event_id>:<asset_key>'`
  （例如无交易对下架作用到 KRW/BTC/USDT 三个事件），见 `STATE_MACHINE.md` §9.1。

公告标题没写市场时 **quote 留空，不要按默认 quote 展开**：LISTING 的空 quote 会在之后与具体市场合并；
DELISTING / SUSPEND / RESUME 的空 quote 是通配，作用于该币在该平台、该 access_kind 下所有已存在的 quote，
每个受影响的 quote 一个事件，已是目标状态的不报 rejected（`STATE_MACHINE.md` §6.1）。

辅助映射：`rc.map_upbit_market`、`rc.map_coinone_market`、`rc.map_korbit_pair`、`rc.map_ramp_asset`。
其余库函数：`upsert_asset`、`add_deployment`、`resolve_ref`、`apply_transition`、`process_due`、`recent_events`。

## 下一步

1. 韩国 4 家适配器（Upbit 市场列表 + 公告 WS、Bithumb 市场 + `/v1/notices` 2s、Coinone 市场、Korbit pairs/networks/notices），source_id 与 CATALOG 对齐。
2. NewListings 中继（stream + History 补数）、Circle、Onramper/Transak、Ondo/Superstate。
3. 对接 GMGN market.sqlite / UI。
