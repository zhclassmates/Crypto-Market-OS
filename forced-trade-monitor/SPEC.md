# forced-trade-monitor v1.1 冻结规格（方案 B）

状态：可开工。研究路径不接 EXEC，不接 veto。S4 关闭。

成功标准：上线满 30 个完整日之后，在决策当时的 universe 快照上，控制 BTC 收益与成交额分位，回答 S1–S3 的前向收益分布是否不同于仅用 `ret_4h_vs_btc` 筛出的对照组。

## 事实合同

- `sumOpenInterest` 入库为 `oi_qty`，`sumOpenInterestValue` 入库为 `oi_value_usdt`。方向与状态只用 `oi_qty`。
- OI `timestamp` 是周期结束。`bar_open_ts = api_ts - period_ms`。
- basis / taker / kline open time 是周期开始。`bar_open_ts = api_ts`。
- basis 请求用 `pair` + `contractType=PERPETUAL`，不是 `symbol`。
- funding 历史没有 `fundingIntervalHours`。周期来自 `fundingInfo` 快照；该接口可能只含被调整过的合约。缺失默认 8，`interval_source=default`。
- 事件只连接 `funding_time` 之前最近一次快照。禁止用今天的周期回写历史。
- `rateType=Special` 不进分位，不进状态。
- OI 历史约 1 个月，taker 约 30 天。不计划用这两条接口回补更早数据。
- ADL 可入库作上下文，不参与打分。

## 对齐

主键是 `bar_open_ts`（UTC 整点毫秒）。未对齐的时间戳入库但 `data_quality_flag` 含 `ts_unaligned`，不参与状态。

决策可见性：该小时收盘及之前的数据。funding 事件 `funding_time <= bar_open_ts + 1h` 才可见。

## 幂等

raw 主键冲突时：

- payload hash 相同：no-op
- hash 不同：旧行写入 `raw_revisions`，再更新当前行

禁止无条件覆盖。

## 两条路径

```
features → states → alerts
features → outcomes
```

outcomes 只对 `universe_snapshot` 里该小时在榜的币计算。价格定义是该小时 K 线 `close`。未闭合期限禁止写入。`vs_btc` 用同一 `bar_open_ts` 的 BTCUSDT。

## 状态

S1 / S2 / S3 / S5 开启。S4 `enabled: false`，标签器直接跳过。阈值为假设，不是优化参数。官方 taker 缺失时不得用 K 线 taker 静默顶替。

## 不在本版

5m watchlist、Claude veto、EXEC、ADL 打分、全市场多空比。
