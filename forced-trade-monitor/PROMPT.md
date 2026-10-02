# 开工提示词：forced-trade-monitor v1.1 接上小时采集

把下面整段交给实现者。不要改冻结合同。

---

你在已有仓库 `forced-trade-monitor/` 上开工。先读 `SPEC.md`、`sql/schema.sql`、`config/states.yaml`、`src/forced_trade/`。现有 15 个测试必须继续通过。这是研究雷达，不是交易系统。

## 已经冻住，禁止重开

- 方案是 B。不要回到单表 raw，不要打开 S4，不要接 5m，不要接 Claude veto，不要接 EXEC，不要让 ADL 参与打分。
- 主键是 `bar_open_ts`（UTC 整点毫秒）。
- OI 的 `timestamp` 是周期结束：`bar_open_ts = api_ts - period_ms`。字段是 `oi_qty` / `oi_value_usdt`，状态只用 `oi_qty`。
- basis、taker、K 线 open time 是周期开始。basis 请求用 `pair` + `contractType=PERPETUAL`。
- funding 历史没有周期。周期只来自 `funding_info_snapshot`，事件只连接 `funding_time` 之前最近一次快照。没有快照默认 8，`interval_source=default`。`rateType=Special` 不进分位，不能触发拥挤状态。
- raw 冲突：hash 相同 no-op，hash 变化写 `raw_revisions` 再更新。禁止无条件覆盖。
- outcomes 只对决策当时 `universe_snapshot` 在榜的币计算。未闭合期限不写。价格是该小时 K 线 `close`。`vs_btc` 用同一 `bar_open_ts` 的 BTCUSDT。
- 官方 taker 缺失时，不得用 K 线 taker 顶替。K 线 taker 只进 `kline_taker_imbalance_1h`。
- 阈值是假设，不要搜索最优参数。

## 这次只做

把小时链路从占位接成可重复运行的采集。顺序固定：

1. `refresh universe`：`/fapi/v1/exchangeInfo` + `/fapi/v1/ticker/24hr`。筛 `PERPETUAL`、`TRADING`、`quoteAsset=USDT`、上市至少 14 天，按 `quoteVolume` 取 Top 80。写入 `universe_snapshot`，`ts` 用本小时 `bar_open_ts`。已有快照不改写。
2. `ingest hourly`：只拉在榜币加 BTCUSDT。K 线、OI、taker、basis、funding 事件、fundingInfo、premiumIndex。全部走现有 parser 和 `upsert_fact`。
3. 每个源写一行 `data_health`：`age_sec`、`http_status`、`latency_ms`、`rows_expected`、`rows_got`、`null_rate`、`ts_semantics`、`error`。失败不中断其他源。
4. `build features`：调用现有 `build_feature`。未对齐时间戳标 `ts_unaligned`，不参与状态。
5. `label states`：调用现有 `evaluate`。S4 必须仍是 `hit=0, reason=disabled`。命中写入 `alerts`，12 小时同币同状态冷却只标 `cooldown_suppressed`，不删 state。
6. `fill outcomes`：只补已经收盘的期限。

调度不要卡在 `HH:00:00`。小时 K 收盘后再跑，默认延迟 120 秒，可配置。抓取失败可重跑，不得制造第二行同一 `bar_open_ts`。

## 接口事实，不要猜

- `GET /futures/data/openInterestHist`：`sumOpenInterest`、`sumOpenInterestValue`，`timestamp` 为周期结束，约 1 个月。
- `GET /futures/data/basis`：`pair`、`contractType`，`timestamp` 为周期开始。
- `GET /futures/data/takerlongshortRatio`：`buyVol`、`sellVol`，`timestamp` 为周期开始，约 30 天。单位不要自行断言。
- `GET /fapi/v1/fundingRate`：事件，无 `fundingIntervalHours`。有 `rateType`。
- `GET /fapi/v1/fundingInfo`：当前 cap/floor/interval，可能只含被调整过的合约。两种返回都要接住。
- `GET /fapi/v1/klines?interval=1h`：open time 为开始。taker buy 在数组下标 9 和 10。
- `GET /fapi/v1/premiumIndex`：mark/index 即时快照，写入 `raw_mark`。
- ADL 端点本轮不调用。

限频：OI/taker 约 1000 次/5 分钟。80 币要串行或小并发，并记录 429。不要为了补历史打爆限频。`scripts/backfill.py` 维持拒绝无界回补。

## 明确不做

不调阈值。不新增特征。不实现 Telegram 真发送，只留格式化函数。不写交易建议。不把 basis 分歧当成方向状态；分歧只进 `data_quality_flag`。不把 research 查询改成收益最大化。

## 完成标准

- `PYTHONPATH=src pytest` 全绿，并新增测试：OI 结束时间对齐、funding 不用未来快照、重复 ingest 不增行、不在榜的币没有 outcomes、S4 仍关闭。
- 用录好的 HTTP fixture 跑通一整小时，不依赖外网测试。
- `healthcheck` 按源打印，不能只报一句 API 正常。
- 最后用 10 行说明改了哪些文件。不要改 `SPEC.md` 的合同句；若实现发现合同无法落地，停下来写差异，不要私下改语义。
