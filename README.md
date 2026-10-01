# Crypto OS 数据采集工作区

两条独立采集链，各自单写 SQLite，互不干扰，十月只采数不出信号。

## 目录

```
rh_v2/                  # Robinhood 链新币扫描（每小时）
market_structure/       # Binance/Bybit 永续市场结构（常驻）
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

报告包含：rh_v2 当天轮数/失败/最长用时/状态分布/新 READY 币、market_structure 数据量、币池同步状态。

---

## 五、故障排查速查

| 症状 | 检查 |
|------|------|
| rh_v2 一小时没跑 | `launchctl print gui/$(id -u)/com.rhv2.collector \| grep state`；`tail rh_v2/logs/collector.log` |
| rh_v2 某轮很慢 | `run.py status` 看 `steps` 字段定位慢步骤；`sources` 看哪个源在重试/熔断 |
| market_structure 没数据 | `tail market_structure/logs/collector.log`；确认 `config.toml` 里 `proxy` 已填 |
| 强平覆盖 0% | WS 是否在线看日志里 `binance WS 已连接` / `bybit WS 已连接` |
| 币池没更新 | 手动跑 `cd market_structure && .venv/bin/python -m ms sync` |

---

## 六、环境备注

- Python 3.14.2（`/opt/homebrew/bin/python3`）
- 代理：`http://127.0.0.1:1082`（已写入 market_structure/config.toml）
- 两个 launchd 服务都加了 `caffeinate -i`，运行期间阻止 Mac 空闲睡眠
- 所有 SQLite 均开 WAL，采集进程运行时可被只读查询
