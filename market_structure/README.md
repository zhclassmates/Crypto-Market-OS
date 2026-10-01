# market_structure — crypto_os 市场结构采集器 v0.1

十月阶段只做一件事：**把数据攒齐**。它不出信号，不画图，不下单。
规则引擎、回测和一屏雷达留到十一月，等 30 天数据攒够再做。

## 采什么

| 数据 | 来源 | 方式 | 断线后能否补 |
|---|---|---|---|
| 永续 K 线 + Perp CVD | Binance USD-M `/fapi/v1/klines` | 每根 bar 收盘后 REST 拉取 | 能，自动补 |
| 现货 K 线 + Spot CVD | Binance Spot `/api/v3/klines` | 同上 | 能 |
| OI 历史（5m） | Binance `/futures/data/openInterestHist` | 同上 | 能，但只能补近 29 天 |
| OI 快照 + 预测资金费率 | Binance `openInterest` + `premiumIndex` | 每根 bar 采样一次 | 不能（这是时点采样） |
| 已结算资金费率 | Binance `/fapi/v1/fundingRate` | 同上 | 能 |
| **可见强平** | Binance `!forceOrder@arr`（全市场） | WebSocket 实时收 | **不能**，没有公开历史 |
| 交叉校验 | Bybit OI(15min)、ticker 费率、`allLiquidation` | REST + WS | OI 能补，强平不能 |

CVD 直接从 K 线里的"主动买成交额"字段计算：`cvd = 2 × taker_buy_quote − vol_quote`，按 bar 切片。
这个数和逐笔累加 aggTrade 的结果完全一致，但不需要处理逐笔成交，算力几乎为零，历史也能直接回补。

## 安装（Mac）

把整个 `market_structure/` 放进 crypto_os 仓库，然后执行：

```bash
cd crypto_os/market_structure
bash deploy/install_mac.sh          # 或者指定解释器：bash deploy/install_mac.sh /opt/homebrew/bin/python3.12
```

安装脚本依次完成：建 `.venv` → 生成 `config.toml` → 先跑一轮 30 天回补 → 注册 launchd 常驻（开机自启、崩溃自动拉起）。

**在国内网络下，务必先在 `config.toml` 里填 `proxy`**。launchd 常驻进程不读取终端里的代理环境变量。

改币池：编辑 `config.toml` 里的 `[[symbols]]`，然后重新执行一次 `bash deploy/install_mac.sh`。
卸载：`bash deploy/install_mac.sh --uninstall`，数据会保留。

## 每天看一眼

每晚 23:30 会自动生成 `reports/health-YYYY-MM-DD.txt`，也可以随时手动运行：

```bash
.venv/bin/python -m ms health            # 最近 24 小时
```

报告第一行是 `OK` 或 `WARN: ...`，其余各列含义如下：
- 强平WS覆盖率：只有某一分钟内 WS 全程在线，这一分钟才算覆盖。低于 95% 会报警告。
- perp / spot：已拉到的 bar 数。
- oi5m / byOI：OI 数据点数。
- fund：资金费率采样次数。
- liqB / liqY：Binance / Bybit 各自可见的强平笔数。

## 表结构（`data/market_structure.sqlite`，所有 ts 均为 UTC 毫秒）

`bars` · `oi` · `funding_live` · `funding_settled` · `liq_prints` · `ws_heartbeat` · `poll_log`，字段注释见 `ms/db.py`。
库文件开启了 WAL，采集进程运行时也可以同时读取。十一月做分析时，DuckDB 可以直接读这个文件：
`INSTALL sqlite; LOAD sqlite; ATTACH 'data/market_structure.sqlite' AS ms (TYPE sqlite);`

## 已知限制（写死在数据语义里，分析时不要忘）

1. **强平是抽样，不是全量。** Binance 每个品种每秒只推一笔快照，Bybit 按 500ms 一批推送。字段名是"可见强平"，不代表全市场真实爆仓额。
2. **强平方向已统一**为 `long_liq` / `short_liq`，原始方向保留在 `raw_side` 字段。
3. **Mac 睡眠期间强平会断档**，这段时间的覆盖率会显示在 `ws_heartbeat` 里。分析时应剔除覆盖率不足的 bar。
4. **防前视**：做信号时只能用 `ts <= bar 收盘时刻` 的 OI 和资金费率数据。
5. **Binance OI 历史只有约 30 天**，所以采集器必须从现在开始连续运行，数据才会越攒越长。

## 十一月接着做

规则 YAML（修正版合取条件，做多用 `funding < Q80`，做空用 `funding > Q20`）→ 单项条件前向收益 → 合取条件 → 夜间报告 → 证明有增量后再做 LWC 一屏雷达。

## 测试

```bash
python -m unittest discover tests        # 字段解析与方向语义
python tests/fake_exchange.py &          # 本地假交易所（含 429、断线、坏品种），配合测试配置做端到端验证
```
