# RH V2 — 小时快照库 + 四列 + 状态机

两份方案的「B 档」（改展示 + 小时库 + 状态机）+「C 档」（ListingP 频率表）已经写成可跑的代码。
纯 Python 标准库，零依赖，SQLite 单文件，数据 API 全部免费层。

## 今天就开跑（约 15 分钟）

```bash
cd rh_v2
# 1) 可选：把你现有网站那 ~460 个币的合约地址放进 extra_tokens.txt（一行一个）
#    不放也行，会自动从 GeckoTerminal 按 24h 成交排序拉前 200 个池子 + 新池
python3 run.py once --force     # 第一轮：建宇宙、拉快照、拉交易所状态、出看板
open out/index.html             # 看板
python3 run.py backfill         # 一次性：给观察池补 7 天小时 K（GT 限速，约 10~20 分钟）
python3 run.py rates            # 看 Alpha→永续 频率表
```

然后挂成每小时自动跑（二选一）：

- **macOS launchd**：把 `com.rhv2.collector.plist` 里的 `__DIR__` 换成本文件夹绝对路径，
  `cp com.rhv2.collector.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.rhv2.collector.plist`
- **VPS / Linux cron**：`3 * * * * cd /path/rh_v2 && python3 run.py once >> collector.log 2>&1`

可选环境变量：`BLOCKSCOUT_API_KEY`（dev.blockscout.com 免费申请，限额更稳）、`TG_BOT_TOKEN` + `TG_CHAT_ID`（新进 READY/RESEARCH 时推送）。

自测（不连网）：`python3 test_offline.py`

## 每小时做什么

```
宇宙(每6h) GT 按24h量前200池 + 新池 + extra_tokens.txt
   ↓
全量快照  DexScreener /tokens/v1/robinhood/{≤30个地址}   ~20 次请求/小时
   ↓  池深≥$25k 且 24h量≥$20k
观察池深挖 Blockscout 持币数(每h)、Top10(每6h，剔除合约地址)、GT 独立买家/卖家数(每h)
   ↓
交易所状态(每天) 币安 Alpha 列表 / 币安永续 / 币安现货 / Aster / Hyperliquid
   ↓
四列评分 + 状态机 → out/index.html + dashboard.json + Telegram
```

死币（最新池深 < $5k）只在每天 00:00 UTC 那轮复查，不浪费请求。

## 四列怎么算（全部在 `scoring.py`，阈值在 `config.py`）

| 列 | 组成 | 说明 |
|---|---|---|
| Heat | 6h/18h 量比 35、6h/18h 笔数比 20、买家加速 15、6h 涨幅 15、持币 6h 增长 15 | 加速度用**非重叠窗**：`(v6/6) / ((v24−v6)/18)`，第一天就能算 |
| Quality | 池深 25、Vol/LP（**减分**）20、独立买家/买单笔数 20、持币数 15、Top10 集中度（减分）10、币龄 10 | 独立买家/笔数低 = 少数地址反复买，像刷 |
| Entry | 100 减：距 7 天低点倍数、24h 涨幅、Vol/LP、1h 卖压、72h 高点腰斩 | 防「更可能上所但已经涨完」 |
| ListingP | 频率表，不是回归；格子 n<20 输出「不确定」 | 见下 |

缺数据的分项自动跳过、权重重新归一，所以第一小时就有分，随着历史积累越来越准。

**状态机**：`INVALID → WATCH → ACCELERATING → RESEARCH → READY`，外加 `OVERHEATED`。
READY 要同时满足 7 条（Heat≥55、Quality≥60、Entry≥60、自有快照≥6h、连续 3h 热、持币不降、6h 买单占优）。
升级立即生效；降级要连续 2 小时确认；INVALID / OVERHEATED 立即生效。

## ListingP：比原方案省掉的最大一块活

原方案第 2 步说「脏活在公告对齐，5–10 人天」。实际不用对公告：

- 币安 Alpha 代币列表接口本身带 `listingTime`、`chainId`、合约地址；
- 币安永续 `exchangeInfo` 每个合约带 `onboardDate`；
- 现货没有日期字段 → 用第一根日 K 的时间当上线日。

所以「全链所有 Alpha 币 → 7/30/90 天内上没上永续」一次请求就能建表（`binance_events`）。
做了两个防坑：**删失**（上 Alpha 不满 30 天的币不进 30 天分母，不能当 0 算）；**撞名**（永续比 Alpha 早 1 天以上的视为撞名/早已上过，剔除）。

格子优先级：RH 链·9/8 后 → 全链·近 180 天 → 全链·全时段；都不够 20 个样本就写「不确定」。
纯链上币要等自有观察池样本（入池 30 天后才看得到结果），在此之前一律「不确定」。

## 已知限制（诚实版）

- 代码字段按各家官方文档写的，但我这边的沙盒连不上这些 API，**第一轮真跑可能要微调字段名**。`run.py once` 的输出里 `queried / got / obs` 三个数能立刻看出哪一步没拿到数据。
- Aster / Hyperliquid 只能按符号匹配，看板里带 `?`，市值 <$1M 的不认；不参与 ListingP。
- 洗量（手递手环）检测没做，这是 V2.1；Quality 里的「独立买家/笔数」和 Vol/LP 只能挡住一部分。
- EV 排序没做：需要 30–60 天自有快照后才有意义。
