# BSC 第五条链接入与验收

验收日期：2026-10-04  
结论：**PASS**

## 范围

本轮在现有 `sol`、`robinhood`、`base`、`eth` 基础上新增 `bsc`，并将市场链清单收口到共享配置。没有新增其它链，没有修改每日涨跌、FINALIZED、K 线、streak、token identity 或 stale 逻辑。

当前支持链：

```text
sol
robinhood
base
eth
bsc
```

内部 chain id 统一为 `bsc`，UI 显示为 `BSC`。

## GMGN BSC 真实能力验证

验证以 GMGN CLI 的真实 `--raw` 返回为准，覆盖 trending、hot-searches、trenches、token info、security、daily Kline 和 signal。

| Field | BSC raw field | Available | Notes |
| --- | --- | --- | --- |
| token / contract | `chain`, `address`, `symbol`, `name` | YES | chain 返回 `bsc` |
| price | `price`, `price.price` | YES | trending/trenches 与 token info 均可用 |
| market_cap / fdv | `market_cap`; `price.price × circulating_supply` | YES | 榜单直接返回 market cap；token info 可按现有口径派生 |
| created_at | `creation_timestamp`, `created_timestamp` | YES | endpoint 字段名不同，均为真实时间戳 |
| 24h volume | `volume`, `volume_24h` | YES | 可用 |
| buy/sell volume | `buy_volume_24h`, `sell_volume_24h` | YES | token info 可用 |
| buys/sells/swaps | `buys`, `sells`, `swaps`; `*_24h` | YES | 可用 |
| liquidity | `liquidity` | YES | 可用 |
| holders | `holder_count` | YES | 可用 |
| daily OHLCV | Kline `time`, `open`, `close`, `high`, `low`, `volume`, `amount` | YES | 真实 1D candles 可返回 |

GMGN BSC 支持结论：**PASS**。

## 实现

- 根目录 `market-chains.json` 是五链共享配置，包含顺序、UI 名称、DexScreener chain id 和 signal 能力。
- Python collector、health 和 lane 路由从共享配置读取链清单。
- TypeScript market status、市场页和发现页从同一配置读取链清单与显示名称。
- 数据库沿用现有通用 `chain + contract_address` 数据模型；没有修改 schema。
- BSC 复用现有 GMGN → collector → DB → API → UI 数据链路，以及现有 finalized 日期收益与日期方向 AND 筛选逻辑。

生产链结论：

```text
GMGN → collector → DB → API → UI
PASS
```

## 真实页面验收（当前 8080）

- BSC 第五条链接入：PASS
- BSC 切换：PASS
- BSC 数据展示：100 行
- finalized 日期收益：700 个
- `2026-09-30 ↑ AND 2026-10-03 ↑`：PASS
- AND 筛选结果：28 行，28 行均同时满足两个日期收益大于 0
- 第二个日期从 UP 循环到 DOWN、NONE 时，第一个日期条件保持不变：PASS
- 五链 UI 回归：PASS
  - Solana：77 行
  - Robinhood：100 行
  - Base：100 行
  - Ethereum：100 行
  - BSC：100 行

## 自动化验证

- Python collector / health / storage 回归：71 tests PASS
- TypeScript chain config + daily filter：24 tests PASS
- 完整前端测试：195 script tests + 161 TypeScript tests PASS
- `npm run typecheck`：PASS
- `npm run build`：PASS

## 数据与算法边界

- SQLite schema：未修改
- 现有四链历史数据：未修改
- 每日涨跌数据与算法：未修改
- FINALIZED 判定：未修改
- K 线逻辑：未修改
- 日期方向 AND 筛选逻辑：未修改，仅验证其天然适用于 BSC
- commit：未执行

## 8081 环境限制

8081 production preview 未启动，归类为：

```text
ENVIRONMENT_LIMITATION
reason: nice(5) failed: operation not permitted
```

这是当前 macOS 执行环境的后台进程权限限制，不是 BSC 业务功能失败，不影响已经在当前正常运行的 8080 页面完成的真实功能验收。按要求未继续尝试启动、重启或修复 preview，也未修改 preview 脚本。

## 本轮 BSC 相关文件

- `market-chains.json`
- `rh_v2/market_chains.py`
- `rh_v2/market_collect.py`
- `rh_v2/market_health.py`
- `rh_v2/market_lanes.py`
- `rh_v2/test_market_chains.py`
- `src/lib/rh/market-chains.ts`
- `src/lib/rh/market-chains.test.ts`
- `src/lib/rh/market-status.ts`
- `src/components/market-view.tsx`
- `src/components/discovery-view.tsx`
- `package.json`
- `tsconfig.json`
- `startup.sh`（仅保证 8080 dev server 在 macOS 后台启动时保持运行；未修改 preview）
- `docs/bsc-chain-acceptance.md`
