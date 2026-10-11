# Crypto OS 数据采集工作区

三条独立采集链，各自单写 SQLite，互不干扰，十月只采数不出信号。

## 目录

```
rh_v2/                  # Robinhood 链新币扫描（每小时）
market_structure/       # Binance/Bybit 永续市场结构（常驻）
access_radar/           # Recent Access Radar：可买入口变化（新上币、法币通道、新链部署、代币化股票）
ops/nightly.py          # 统一夜间报告
reports/                # 每日输出
```

---

## 一、rh_v2（Robinhood 链新币扫描）

**目的**：每小时从 GeckoTerminal / DexScreener / Blockscout / Binance 拉数据，计算四列评分和状态机。

**库文件**：`rh_v2/rhv2.sqlite`

**运行方式（已挂 launchd，每小时第 3 分钟自动跑）**：

```bash
# 手动跑一轮
cd rh_v2 && /opt/homebrew/bin/python3 run.py once

# 强制刷新宇宙 + 交易所状态
cd rh_v2 && /opt/homebrew/bin/python3 run.py once --force

# 离线自测（不连网）
cd rh_v2 && /opt/homebrew/bin/python3 test_offline.py
```

**看运行状态**：

```bash
cd rh_v2 && /opt/homebrew/bin/python3 run.py status        # 上一轮 last_run
cat rh_v2/logs/collector.log                               # launchd 日志
sqlite3 rh_v2/rhv2.sqlite "SELECT ts, COUNT(*) FROM snapshots GROUP BY ts ORDER BY ts DESC LIMIT 5"
```

**停止定时任务**：

```bash
launchctl bootout gui/$(id -u)/com.rhv2.collector
rm ~/Library/LaunchAgents/com.rhv2.collector.plist
```

---

## 二、market_structure（Binance/Bybit 永续市场结构）

**目的**：15m K 线 + CVD、OI、资金费率、可见强平（WebSocket 实时收）。

**库文件**：`market_structure/data/market_structure.sqlite`

**运行方式（已挂 launchd，常驻）**：

```bash
# 查看健康（最近 24 小时）
cd market_structure && .venv/bin/python -m ms health

# 手动跑一轮 REST 回补
cd market_structure && .venv/bin/python -m ms once

# 币池同步（rh_v2 → config.toml）
cd market_structure && .venv/bin/python -m ms sync

# 查看日志
tail -f market_structure/logs/collector.log
```

**停止常驻进程**：

```bash
launchctl bootout gui/$(id -u)/com.cryptoos.market-structure
rm ~/Library/LaunchAgents/com.cryptoos.market-structure.plist
```

---

## 三、币池同步（两链唯一接口）

`market_structure/ms/sync_symbols.py` 每天随健康报告一起跑（约 23:30）：
- 从 `rh_v2/rhv2.sqlite` 读取 90 天内上永续的币
- 用 Binance fapi exchangeInfo 核对真实合约名（含 1000 前缀）
- 写入 `market_structure/config.toml` 的 `[[symbols]]`，自动条目标记 `auto = true`
- 手写条目保持不动；币池有变化时触发进程重启以加载新列表

最多 40 个自动条目，按上永续时间从新到旧取。

---

## 四、统一夜间报告

```bash
/opt/homebrew/bin/python3 ops/nightly.py           # 生成 reports/YYYY-MM-DD.txt
/opt/homebrew/bin/python3 ops/nightly.py 2026-10-01  # 指定日期
```

报告包含：rh_v2 当天轮数/失败/最长用时/状态分布/新 READY 币、market_structure 数据量、Access Radar 当天事件/来源健康/断线缺口/身份解析进度、币池同步状态。

---

## 五、Access Radar（可买入口变化）

**目的**：盯“能在哪里买到”这类结构性变化：交易所新上币/暂停/下架、法币通道开通、代币部署到新链、代币化股票和 RWA 上架。只记状态变化，不记价格。设计细节见 `access_radar/README.md` 和 `access_radar/STATE_MACHINE.md`。

**库文件**：`access_radar/access.sqlite`（可用环境变量 `ACCESS_DB` 改）。不碰 GMGN 的 `rh_v2/market.sqlite`，只读它做代币关联。

**数据源（适配器在 `access_radar/adapters/`）**：

| 来源 | 内容 | 需要 key |
|---|---|---|
| Upbit | 市场列表 + 公告 WebSocket | 公告要 JWT（`UPBIT_ACCESS_KEY` / `UPBIT_SECRET_KEY`，API key 不用勾任何权限） |
| Bithumb | 市场列表 + 公告（每 IP 每秒 1 次） | 否 |
| Coinone | KRW 市场列表 | 否 |
| Korbit | 交易对 + 各币充提网络 | 否 |
| xStocks | 代币化股票目录 + 各链部署 | 否 |
| Ramp | 各法币可买资产（固定带 `withDisabled`、`withHidden`） | 否 |
| Binance Alpha | 只用于代币身份解析（symbol → 合约） | 否 |

Onramper、Transak、Ondo 需要先申请 key，拿到后再接。

**运行方式（launchd `com.access.collector`，常驻）**：

```bash
# 手动跑一轮（所有到期的源各抓一次）
/opt/homebrew/bin/python3 access_radar/access_run.py once

# 常驻循环（launchd 跑的就是这个）
/opt/homebrew/bin/python3 access_radar/access_run.py loop

# 看各来源状态：上次成功时间、连续失败、事件数
/opt/homebrew/bin/python3 access_radar/access_run.py status

# 最近事件（时间显示 UTC+8）
/opt/homebrew/bin/python3 access_radar/access_run.py feed --window 24h

# CEX 代币身份解析（采集循环里每小时自动跑一次）：拉币安 Alpha 列表，按合约精确匹配，否则按 symbol 标成待确认（SUGGESTED）
# 手动跑一次；采集循环在跑时会拒绝执行，结果看 status 里的 maintenance 一栏
/opt/homebrew/bin/python3 access_radar/access_run.py maintenance resolve

# 离线自测（不连网）
cd access_radar && /opt/homebrew/bin/python3 -m unittest discover -p "test_*.py"
cd access_radar && /opt/homebrew/bin/python3 -m unittest discover -s adapters -t . -p "test_*.py"
/opt/homebrew/bin/python3 -m unittest discover -s ops -p "test_*.py"
```

**几条规则**：
- 下架不会因为一次少返回就判定：要连续多次成功拉取都没有，且总条数没有异常骤降；骤降时整个来源标成 DEGRADED，暂停对比。
- 同一次上币被多个来源报到只算一个事件；置信度只数独立来源（NewListings 转述 Upbit 不算两家）。
- 身份解析只有合约精确匹配才算 CONFIRMED；按 symbol 匹配到的一律是 SUGGESTED，多个候选时不猜，留 UNRESOLVED 等人工确认。
- 所有真实接口的连通测试都在这台 Mac 上跑：交易所和法币通道可能拦机房 IP，云端和共用电脑测出来不准。

**停止常驻进程**：

```bash
launchctl bootout gui/$(id -u)/com.access.collector
rm ~/Library/LaunchAgents/com.access.collector.plist
```

---

## 六、故障排查速查

| 症状 | 检查 |
|------|------|
| rh_v2 一小时没跑 | `launchctl print gui/$(id -u)/com.rhv2.collector \| grep state`；`tail rh_v2/logs/collector.log` |
| rh_v2 某轮很慢 | `run.py status` 看 `steps` 字段定位慢步骤；`sources` 看哪个源在重试/熔断 |
| market_structure 没数据 | `tail market_structure/logs/collector.log`；确认 `config.toml` 里 `proxy` 已填 |
| 强平覆盖 0% | WS 是否在线看日志里 `binance WS 已连接` / `bybit WS 已连接` |
| 币池没更新 | 手动跑 `cd market_structure && .venv/bin/python -m ms sync` |
| Access Radar 没有新事件 | `access_run.py status` 看哪个源连续失败；夜间报告的“来源健康”和“断线缺口”两行 |
| 某个源一直 DEGRADED | 多半是返回条数骤降或字段变了，看 `source_health.last_error`；确认正常后连续几轮条数稳定会自动恢复 |
| 待确认代币越来越多 | `access_run.py status` 看 maintenance 一栏 resolve 是否连续失败；仍是 UNRESOLVED 的多半是同名币，需要人工确认 |

---

## 七、环境备注

- Python 3.14.2（`/opt/homebrew/bin/python3`）
- 代理：`http://127.0.0.1:1082`（已写入 market_structure/config.toml）
- 三个 launchd 服务都加了 `caffeinate -i`，运行期间阻止 Mac 空闲睡眠
- 所有 SQLite 均开 WAL，采集进程运行时可被只读查询


### 2026-10-11 中断恢复验收

统一市场已应用已有核心代码的 V1.7：当前报价资格与七日历史完整度分开，BTC/ETH/SOL 保留真实历史缺口并可进入当前报价 VALID 列表。原始采集表和既有资产身份保留，未重新采集或调用行情 API。测试、构建及开发/生产浏览器验收和恢复检查点详见 [恢复交付记录](integration/unified-market/DELIVERY-RESUME.md)。
