# Robinhood 生态站：设计 · 规划 · 交接提示词

> 参考对象：<https://ru7.one/stocks/robinhood>（RU7 美股终端 →「🪶 Robinhood 生态」页）
> 本文给**接手开发的人 / AI 编码代理**用：第 1–6 节是设计和规划，第 7 节是可直接复制的提示词。
> 编写日期：2026-10-01

---

## 0. 一句话目标

做一个**中文优先、信息密集的 Robinhood 生态终端页**：

1. 链上「代币化美股」比真股票贵还是便宜，扣掉成本后有没有能做的价差；
2. Robinhood Chain 自己赚多少、有多热；
3. 链上原生币按多个口径排榜；
4. 一个币从「链上」走到「交易所」再走到「Robinhood App」的上币阶梯；
5. **我们自己的差异化**：rh_v2 的小时级评分 + 状态机（WATCH → ACCELERATING → RESEARCH → READY / OVERHEATED），以及 market_structure 对已上永续币的 OI / 资金费率 / CVD / 强平。

前 4 块对标 RU7（他们用公开 API 现算），第 5 块是 RU7 没有、而我们已经在采的数据。

---

## 1. 参考站拆解（RU7 实际做了什么）

> 下面来自对页面 HTML 和前端脚本的阅读，只用来理解产品思路。**不要复制他们的代码、文案和视觉**，自己实现。

### 1.1 页面骨架

- 顶栏：站名 + 「导览页」下拉（美股导览 / 个股 F9 / 大V 持仓蒸馏 / Robinhood 生态；站内其他：首页、Hyperliquid、预测市场、链上分析）、代码搜索框 + GO、市场开收盘状态、中/EN 切换、刷新、提问。
- Robinhood 生态页自上而下 7 块：

| # | 区块 | 副标题（大意） | 数据源 |
|---|---|---|---|
| 1 | 今日速读 | 把下面几块的结论压成 3–4 张卡片，点卡片跳到对应区块 | 汇总 |
| 2 | 代币化美股折溢价 | 链上股票代币比真股票贵还是便宜；按 24h 成交额排，点表头改排序 | CoinGecko + Yahoo |
| 3 | Robinhood Chain 收入与活跃度 | 链赚多少、发射台赚多少、链上多热 | DefiLlama + RPC 采样 |
| 4 | 链上可交易的币 | 只在本链发的原生币，多口径各排一张榜 + 综合评分 | GeckoTerminal + DexScreener + Robinscan |
| 5 | 上币阶梯 | 链上 → 交易所 / Robinhood App 两条并列路径，每级多少个币 | 各交易所公开上币列表 |
| 6 | HOOD 母公司 | Robinhood Markets 股价 | Yahoo |
| 7 | 口径说明 | 数据源与计算口径的完整文字说明 | — |

### 1.2 关键交互

- 每张表：**筛选胶囊**（如 有成交 / 全部 / 溢价>1% / 折价>1% / 私募无参照 / 24h成交Top）+ **点表头排序** + 「显示全部列」开关。
- 每个区块右上角：**数据源徽章** + **质量徽章**（如「覆盖 182/190」，绿/黄/红）+ 更新时间。
- 主表先出，慢字段（持有地址数）**异步补列**，挂了就显示「—」，不影响其他列。
- 美股休市时：折溢价表顶部横幅提示、整表调淡，按最新收盘价算。
- 榜单 Tab：综合 / 热门 / 成交额 / 市值 / 持币地址 / 换手 / 新币(72h)；类别筛选：全部 / 链上美股 / 与股票配对（如 RIM/TSLA）/ 纯 Meme / 生态币。
- 上币阶梯压成两行：
  - 交易所一路：`链上有量的币 → Aster · Hyperliquid → 币安 Alpha → 币安永续 → 币安现货 → 韩所`
  - App 一路：`Robinhood App 有报价 → Robinhood App 可买`
  - 下方「展开台阶明细表」：每个币在每一级的核实情况，默认只看池深 ≥ $100k。

### 1.3 值得学的口径（这些是真坑，直接沿用思路）

| 坑 | 处理 |
|---|---|
| 没成交的代币，链上价是几天前最后一笔 → 算出大量「假折价」 | 折溢价统计只算 24h 成交 ≥ $10k 的；「今日速读」只看 ≥ $100k |
| 个别陈旧报价把均值拉飞 | 汇总用**中位数**不用均值 |
| 有价差 ≠ 能赚钱 | 扣掉链上滑点 + 兑换费后仍为正才算「能做」（按一个可调的下单金额，如 $1 万） |
| LINK / WETH 等跨链币在 CoinGecko 上是全网数字 | 跨链资产用 GeckoTerminal 池子口径；只存在于本链的币才用 CoinGecko |
| 链上市值很小的合约（桥过来的零星余额）换手率爆表 | 链上市值 < $50 万不算换手 |
| 同名币（符号撞名） | 每一级都用「链上价 vs 场所报价」比对，偏离 ≤ 8% 才算同一个币；币安用官方充提合约地址核 |
| 韩所报韩元 | 用 BTC 两边价格折算汇率再比 |
| Blockscout 经常 503/403 | 持币数单独接口、缓存 30 分钟、失败显示「—」 |
| 成交额高但是刷量 | 硬性排除：换手（成交÷池深）> 20 倍、池深 < $5 万、开池 < 3 天 |

---

## 2. 我们的版本：信息架构

路由：`/rh`（主页面，单页长滚动 + 顶部锚点导航）、`/rh/token/:address`（单币详情，第二期）。

```
/rh
├─ 顶栏：站名 · 锚点导航 · 美股开/收盘状态 · 全站数据新鲜度 · 中/EN · 明暗
├─ ① 今日速读（3–4 卡）
├─ ② 代币化美股折溢价
├─ ③ 链上收入与活跃度
├─ ④ 链上原生币榜单（多口径）
├─ ⑤ 我们的雷达：rh_v2 状态机       ← 差异化
├─ ⑥ 上币阶梯 + 明细
├─ ⑦ 已上永续币的市场结构           ← 差异化（market_structure）
├─ ⑧ HOOD 母公司
└─ ⑨ 口径说明（可折叠）
```

### 2.1 各区块规格

**① 今日速读**
- 卡片：`扣成本后还能做的价差 N 只` / `链上 24h 成交 & 较昨日` / `新进 READY 的币` / `近 30 天新上场所的币`。
- 每卡：一句结论（大字）+ 一句依据（小字）+ 点击滚动到对应区块。语气 warn/ok/neutral 三色。

**② 代币化美股折溢价**
- 顶部 KPI 行：代币化标的数 · 24h 链上成交（附整体换手）· 折溢价中位数 · 溢价>1% / 折价>1% 家数 · 扣成本后可做数。
- 表格列（默认）：代码 · 名称 · 链上价 · 美股价 · **折溢价%** · 24h 成交 · 链上市值 · 换手% · 扣成本净价差%。
- 「显示全部列」追加：持有地址 · 池深 · 1h/24h 涨跌 · 数据源。
- 筛选：有成交(默认，≥$10k) / 全部 / 溢价>1% / 折价>1% / 无参照 / 成交 Top30。
- 下单金额切换：$1k / $1 万 / $10 万（影响「净价差」列）。
- 休市横幅 + 表格 opacity 0.7。

**③ 链上收入与活跃度**
- KPI：链日收入 · 30 日收入 · 链上 tx/日（RPC 采样折算）· 活跃地址（如可得）。
- 近 N 日收入折线（SVG sparkline 即可）。
- 发射台收入 Top 表（按 30 日收入）。

**④ 链上原生币榜单**
- Tab：综合 / 热门 / 成交额 / 市值 / 持币地址 / 换手 / 新币(72h)。
- 类别：全部 / 链上美股 / 与股票配对 / 纯 Meme / 生态币。
- 列：# · 币 · 价格 · 24h% · 24h 成交 · 市值 · 池深 · 持币 · 换手 · 开池时长 ·（综合 Tab 加：综合分 + 分项迷你条）。
- 综合分 8 个分项：池深、成交额、换手、真实买盘、多周期动能、起量、持币地址、真实度。**我们直接用 rh_v2 的 Heat / Quality / Entry 替代**，见 ⑤。

**⑤ 我们的雷达（rh_v2）**
- 状态分布条：INVALID / WATCH / ACCELERATING / RESEARCH / READY / OVERHEATED 各多少个，点击筛选。
- 表：币 · 状态（徽章 + 进入时长）· Heat · Quality · Entry · ListingP · 池深 · 24h 成交 · 持币 · Top10% · 原因（hover 展开 `reasons`）。
- 「最近状态变化」时间线（最近 24h 升/降级）。
- 顶部固定免责：**「观察中，非交易信号」**（十月阶段只采数，见第 6 节）。

**⑥ 上币阶梯**
- 两行漏斗（同参考站）。每格：数字 + 标签；某个数据源挂了显示「—」。
- 明细表：币 × 各级（✓ 已核实 / ? 仅符号匹配 / — 未上），附上架日期。默认池深 ≥ $100k。
- 侧卡：「近 30 天新上场所」feed、「同名币警告」、「成交额高但硬性条件不过」。
- 数据直接来自 rh_v2 的 `listings` + `binance_events` 表（我们已经有了）。

**⑦ 已上永续币的市场结构（market_structure）**
- 只列从 rh_v2 同步过去、已上币安永续的币（`config.toml` 里 `auto = true` 那批）。
- 列：合约 · 上永续天数 · 价格 · 24h% · OI & 24h 变化 · 资金费率（当前/预测）· 24h Perp CVD · 24h 可见强平（多/空）。
- 每行可展开：15m 价格 + OI 双轴小图。

**⑧ HOOD 母公司**：价格、涨跌、市值、52 周区间、迷你 K 线（1D/5D/1M/6M/1Y）。

**⑨ 口径说明**：每个区块一段，写清数据源、过滤阈值、刷新频率、已知缺陷。

---

## 3. 技术架构

### 3.1 关键约束

- 网站部署在 **Vercel**（本仓库已是 TanStack Start + React 19 + Tailwind v4 脚手架，见 `AGENTS.md`）。
- rh_v2 和 market_structure 跑在 **本地 Mac**，各自写 SQLite。**Vercel 读不到本机 SQLite。**
- 公开 API（CoinGecko、GeckoTerminal、DexScreener、DefiLlama、Yahoo、币安等）有限速，前端不能直连（CORS + 限速 + 暴露 key）。

### 3.2 数据流（推荐方案：两条腿）

```
┌──────────── 本地 Mac ────────────┐         ┌──────── Vercel ────────┐
│ rh_v2 (每小时)                    │         │                        │
│ market_structure (常驻)           │         │  /api/rh/*  服务端路由 │
│        │                          │  HTTPS  │   ├─ 读快照（我们的数据）│
│ ops/publish.py（新增, 每小时+5分）├────────►│   └─ 现算（公开 API）   │
│   只读两库 → 导出 JSON → 上传      │  对象存储│        │ s-maxage 缓存 │
└──────────────────────────────────┘         │        ▼               │
                                             │   /rh 页面（客户端轮询）│
                                             └────────────────────────┘
```

- **腿 A：我们的数据（⑤⑥⑦ 和 ④ 的部分字段）** —— Mac 上新增 `ops/publish.py`，只读打开两个 SQLite，导出几份 JSON 快照，上传到对象存储（默认 **Vercel Blob**；备选 Cloudflare R2 / 一个私有 GitHub 仓库的 raw）。网站服务端读这些 JSON。写入 token 只放在 Mac 本地，不进仓库。
- **腿 B：公开 API 现算（②③⑧ 和 ④ 的行情字段）** —— 网站服务端路由去拉，带内存缓存 + `Cache-Control: s-maxage`，前端按区块轮询。
- **不上数据库**：两条腿都是只读快照，不需要 Neon / 登录。

### 3.3 刷新节奏

| 数据 | 服务端缓存 | 前端轮询 |
|---|---|---|
| 美股报价（折溢价分母） | 60s | 60s |
| 代币化股票链上价/成交 | 120s | 120s |
| 原生币榜单 | 5min | 5min |
| 持币地址 | 30min | 随榜单 |
| 链收入（DefiLlama） | 1h | 打开时 |
| rh_v2 快照 | 跟随上传（1h） | 5min |
| market_structure 快照 | 跟随上传（15min） | 5min |
| 上币阶梯 | 1h | 打开时 |

数据新鲜度：每个区块显示「更新于 xx 分钟前」；快照超过 2 个周期未更新 → 黄色，超过 6 个周期 → 红色 + 「本机采集可能已停」。

### 3.4 API 契约（前后端、本机导出共用）

所有接口统一外层：

```ts
type Envelope<T> = {
  ok: boolean;
  ts: number;              // 数据时间（unix 秒）
  stale: boolean;          // 超过预期周期
  sources: Record<string, "live" | "cache" | "down">;
  quality: { coverage?: { active: number; total: number }; partialReasons: string[] };
  data: T;
  error?: string;
};
```

| 路由 | data 形状（要点） | 腿 |
|---|---|---|
| `GET /api/rh/stocks` | `{ rows: { symbol, name, address, chainPrice, usPrice, premPct, vol24h, mcap, turnover, liq, edgePct, holders?, isPrivate }[], marketState: "pre"\|"open"\|"post"\|"closed" }` | B |
| `GET /api/rh/activity` | `{ revenue1d, revenue30d, txPerDay, series: [ts, usd][], launchpads: { name, fee30 }[] }` | B |
| `GET /api/rh/boards` | `{ tokens: Token[], boards: Record<"score"\|"hot"\|"vol"\|"mcap"\|"holders"\|"turnover"\|"fresh", string[] /*address*/> }` | A+B |
| `GET /api/rh/radar` | `{ counts: Record<State, number>, rows: { address, symbol, state, sinceTs, heat, quality, entry, listingP, liq, vol24h, holders, top10Pct, reasons: string[] }[], changes: { ts, address, symbol, from, to }[] }` | A |
| `GET /api/rh/ladder` | `{ rungs: { key, label, count }[], down: string[], detail: { address, symbol, kind, liq, steps: Record<string, { ok: boolean\|null, by: "address"\|"price"\|"symbol", at?: number }> }[], recent: {...}[], collisions: {...}[], ruledOut: {...}[] }` | A |
| `GET /api/rh/perps` | `{ rows: { symbol, onboardDays, price, pc24h, oi, oiChg24h, funding, fundingPred, cvd24h, liqLong24h, liqShort24h, spark: [ts, price, oi][] }[] }` | A |
| `GET /api/rh/hood` | `{ price, chgPct, mcap, hi52, lo52, candles: Record<"1d"\|"5d"\|"1m"\|"6m"\|"1y", [ts,o,h,l,c][]> }` | B |

阶梯 `key` 固定为：`onchain, aster, hl, bnAlpha, bnPerp, bnSpot, kr, rhQuoted, rhSpot`。

### 3.5 本机导出（`ops/publish.py`）映射

| 输出文件 | 来自 |
|---|---|
| `radar.json` | `rh_v2.scores`（最新 ts）+ `state` + `tokens` + 最新 `snapshots`；`changes` 从近 24h 的 `scores.state` 差分 |
| `ladder.json` | `rh_v2.listings` + `binance_events` + 最新 `snapshots.liq` |
| `boards-extra.json` | 最新 `snapshots`（holders、top10_pct、buyers/sellers）按 address |
| `perps.json` | `market_structure.sqlite` 近 24h K 线 / OI / 资金费率 / 强平聚合 |
| `meta.json` | 两边 last_run、本次导出时间、行数 |

规则：**只读打开**（`file:...?mode=ro`），不改两边任何表、评分和阈值；导出失败只记日志，不影响采集。

---

## 4. 视觉设计

**基调**：交易终端，信息密度优先，不做营销页。参考站是浅色底 + 薄荷绿强调，我们做**自己的**配色，默认深色、支持浅色。

### 4.1 Token（起点，可调）

```css
:root {            /* 浅色 */
  --bg: #f7f8fa; --surface: #ffffff; --surface-2: #f1f3f6;
  --border: #e3e6eb; --text: #14171c; --text-2: #4d5562; --text-3: #949ba6;
  --accent: #6d5efc;          /* 主强调：紫，避开参考站的薄荷绿 */
  --up: #16a34a; --down: #dc2626; --warn: #d97706;
  --up-bg: rgb(22 163 74 / .10); --down-bg: rgb(220 38 38 / .10); --warn-bg: rgb(217 119 6 / .12);
  --r: 6px; --r-2: 10px;
}
[data-theme="dark"] {
  --bg: #0b0d12; --surface: #12151c; --surface-2: #181c25;
  --border: #242a35; --text: #e7eaf0; --text-2: #a3abb9; --text-3: #6b7383;
  --accent: #8b7dff; --up: #22c55e; --down: #f05252; --warn: #f59e0b;
}
```

- 字体：正文 `Inter` / 系统中文字体；**所有数字用等宽 tabular-nums**（`font-variant-numeric: tabular-nums`）。
- 涨跌色：默认 **绿涨红跌**，设置里可切「红涨绿跌」。
- 状态徽章色：INVALID 灰 · WATCH 蓝灰 · ACCELERATING 蓝 · RESEARCH 紫 · READY 绿 · OVERHEATED 橙。

### 4.2 组件清单

`SectionCard`（标题 + 副标题 + 源徽章 + 质量徽章 + 更新时间 + 折叠）· `KpiRow` · `FilterChips` · `SortableTable`（粘性表头、首列粘性、横向滚动、数字右对齐）· `StateBadge` · `ScoreBar`（0–100 小条）· `Sparkline`（纯 SVG）· `LadderFunnel` · `FreshnessDot` · `EmptyState` / `ErrorState`（写清哪个源挂了）· `Skeleton`。

### 4.3 响应式

- ≥1024px：KPI 一行 4–6 个；表格全宽。
- 390px：KPI 两列；表格只保留 4 列（币 / 核心数值 / 次要数值 / 变化），其余进行内展开；锚点导航变横向滚动条。不允许页面整体横向溢出。

### 4.4 文案

- 中文为主，EN 切换（i18n 字典，不要在组件里写死）。
- 结论句先行：「扣掉成本后一只都做不了」比「价差统计」好。
- 所有金额 `$1.23M / $456K` 缩写；百分比带符号 `+1.24%`。

---

## 5. 里程碑与验收

| 阶段 | 内容 | 验收 |
|---|---|---|
| **M0 骨架** | 路由 `/rh`、布局、Token、组件库、i18n、明暗切换、所有区块用**假数据**（`src/data/mock/*.json`，形状严格按 3.4） | 桌面 + 390px 截图无溢出；`npm run build`、`npm run typecheck` 通过 |
| **M1 公开数据（腿 B）** | `/api/rh/stocks`、`/activity`、`/hood`、`/boards` 行情部分；缓存 + 降级 | 任一上游断掉，该区块显示错误态、其他区块正常；折溢价口径符合 1.3 |
| **M2 本机导出（腿 A）** | `ops/publish.py` + 上传；`/api/rh/radar`、`/ladder`、`/perps`；新鲜度提示 | 本机停跑 3 小时后页面变黄/红；导出不影响采集（rh_v2 单轮耗时不变） |
| **M3 打磨** | 今日速读、口径说明、单币详情页、分享图、SEO | 首屏 LCP < 2.5s（4G）；控制台无报错 |
| **M4（11 月后）** | 状态变化推送、历史回看、ListingP 命中率回测 | 有 30 天以上快照后再做 |

---

## 6. 边界与风险

- **十月只采数**：之前定过「十月不新增信号、不改评分、不做 UI」。M0/M1（公开数据部分）可以先做；⑤ 雷达区块上线时必须挂「观察中，非交易信号」，或等 11 月再公开。
- **不改采集链**：网站侧任何需求都通过 `ops/publish.py` 读取，不改 rh_v2 / market_structure 的表结构、评分、阈值、状态机。
- **上游不稳定**：Blockscout、GeckoTerminal（约 0.5 rps 免费限速）、Yahoo（非官方接口，Vercel 出口 IP 可能被拒）都可能挂。每个源都要有超时（≤10s）、缓存、降级，Yahoo 备选 Finnhub 免费 quote。
- **待核实（实现前先确认，不要凭记忆写）**：CoinGecko 上 Robinhood 代币化股票的识别方式（名称后缀「• Robinhood Token」/ category / 平台 id）、DexScreener 与 GeckoTerminal 的链 id、DefiLlama 的链 slug、Robinhood App 可买币列表的获取方式、Robinhood Chain RPC 地址。
- **合规**：页面不给买卖建议；所有分数标注「非投资建议」；不抓取需要登录的数据。
- **不抄参考站**：不复制 RU7 的代码、文案、配色、图标。

---

## 7. 交接提示词（直接复制给开发者 / AI 编码代理）

> 用法：先把**总提示词**发出去，再按里程碑逐个发**阶段提示词**。每个阶段完成、验收通过后再发下一个。
> 每段提示词都假设对方能看到本仓库和本文件 `docs/robinhood-site-plan.md`。

### 7.0 总提示词（每次新会话都先贴这段）

```text
你在这个仓库里做一个「Robinhood 生态终端」网页，路由 /rh。完整设计在 docs/robinhood-site-plan.md，先通读一遍，以它为准。

技术栈：仓库现有的 TanStack Start + React 19 + Tailwind v4（读 package.json，不要另起脚手架），部署到 Vercel。
仓库里还有两条本地数据采集链：rh_v2/（Robinhood 链新币小时扫描，SQLite）和 market_structure/（币安/Bybit 永续结构，SQLite）。

硬性约束：
1. 不修改 rh_v2/ 和 market_structure/ 下的任何代码、表结构、评分和阈值。网站需要它们的数据，只能通过 ops/publish.py 只读导出。
2. 不加登录、不加数据库。所有数据是只读快照或服务端现算。
3. 前端不直连第三方 API；全部走 src/routes 下的服务端路由（/api/rh/*），带超时、缓存和降级。
4. 所有接口返回 docs/robinhood-site-plan.md 第 3.4 节的 Envelope 结构，字段名照抄。
5. 第三方接口的路径、链 id、字段名，先用真实请求核实再写代码，不要凭记忆。核实结果写进 docs/data-sources.md。
6. 不复制参考站 ru7.one 的代码、文案和配色。
7. 每个阶段结束：npm run build 和 npm run typecheck 通过；用浏览器在 1280px 和 390px 各截一张图检查；控制台无报错；git 提交一次。
8. 中文界面为主，文案进 i18n 字典；数字等宽；金额缩写 $1.2M。

现在先不要写代码，回复：你理解的 7 个区块各是什么、你准备怎么拆组件、有哪些第三方接口需要先核实。
```

### 7.1 M0 骨架（假数据）

```text
做 M0：页面骨架 + 假数据，不接任何真实接口。

1. 在 src/lib/rh/types.ts 定义 docs/robinhood-site-plan.md 第 3.4 节所有类型（Envelope 和 7 个接口的 data）。
2. 在 src/data/mock/ 下为 7 个接口各写一份假数据 JSON，形状严格符合类型。数据要像真的：
   - stocks 至少 25 行，含溢价、折价、无参照、零成交几种情况；
   - radar 覆盖 6 种状态；ladder 的 9 个 key 都有数字，其中一个放进 down 演示「—」。
3. 按第 4 节做设计 token（浅/深两套，默认深色）和组件：SectionCard、KpiRow、FilterChips、SortableTable、StateBadge、ScoreBar、Sparkline、LadderFunnel、FreshnessDot、EmptyState、ErrorState、Skeleton。
4. 搭 /rh 页面：顶栏（锚点导航、美股开收盘状态、中/EN、明暗切换）+ 第 2 节的 9 个区块，全部读假数据。
   - 折溢价表的筛选、排序、显示全部列、下单金额切换要真能用。
   - 榜单的 7 个 Tab 和 5 个类别筛选要真能用。
   - 雷达的状态分布条点击能筛选表格。
5. 390px 下：KPI 两列、表格只保留 4 列其余行内展开、页面不横向溢出。
6. 做一个开关可以让任意区块显示 loading / error / empty 三种状态，用来自测。

验收：两种宽度的截图，明暗各一套；build、typecheck 通过。
```

### 7.2 M1 公开数据（腿 B）

```text
做 M1：把 ② 折溢价、③ 链上活跃度、⑧ HOOD、④ 榜单的行情部分接到真实公开数据。

第一步，核实（不写业务代码）：用真实请求确认以下内容，写进 docs/data-sources.md（接口 URL、限速、关键字段、示例响应片段）：
- CoinGecko：怎么拿到 Robinhood Chain 上全部代币化股票（价格、24h 成交、市值、合约地址），以及怎么识别它是股票代币；
- 美股实时价：Yahoo 和 Finnhub 各试一次，记录在 Vercel 环境下哪个更稳；
- GeckoTerminal / DexScreener：Robinhood Chain 的 network id，池子列表、池深、开池时间、买卖笔数；
- DefiLlama：Robinhood Chain 的收入/手续费接口和发射台拆分；
- Robinhood Chain 公共 RPC：用最近 20 分钟区块数和交易数折算 tx/日。

第二步，实现 src/routes/api/rh/ 下的 stocks、activity、hood、boards：
- 每个上游 10 秒超时；进程内缓存 + Cache-Control: s-maxage（时长见设计文档 3.3）；
- 某个上游失败：sources 里标 down，partialReasons 写原因，其他字段照常返回；全部失败才 ok=false；
- 折溢价口径严格按设计文档 1.3：24h 成交 < $10k 不进统计；汇总用中位数；链上市值 < $50 万不算换手；
  净价差 = |折溢价| − 估算滑点 − 兑换费，滑点用池深和下单金额估（公式写进口径说明）；
- 美股休市按最新收盘价，接口返回 marketState。

第三步，前端把这四块从假数据切到真接口（保留 mock 作为开发开关），按 3.3 的频率轮询，显示更新时间和新鲜度。

验收：手动让某个上游超时（改成错误 URL），确认只有对应列/区块降级；截图；build、typecheck 通过。
```

### 7.3 M2 本机导出（腿 A）

```text
做 M2：把我们自己的数据（rh_v2 雷达、上币阶梯、market_structure 永续结构）放上网站。

1. 新建 ops/publish.py（Python 标准库优先）：
   - 以只读方式打开 rh_v2/rhv2.sqlite 和 market_structure/data/market_structure.sqlite（sqlite3.connect("file:...?mode=ro", uri=True)）；
   - 先读两边的表结构（.schema），再按设计文档 3.5 导出 radar.json、ladder.json、boards-extra.json、perps.json、meta.json，形状符合 3.4 的 Envelope；
   - 上传到 Vercel Blob（token 从环境变量 BLOB_READ_WRITE_TOKEN 读，不写进仓库、不写进 .env）；上传失败只记日志；
   - 加 --dry-run（只写到 ops/out/ 不上传）；
   - 写 launchd plist 让它每小时第 8 分钟跑一次（rh_v2 在第 3 分钟跑），并在根 README 里补安装/停止方法；
   - 用临时库造数据写单元测试。
2. 绝对不要修改 rh_v2/ 和 market_structure/ 下的任何文件；不要在它们的进程里加钩子。
3. 网站侧新增 /api/rh/radar、/api/rh/ladder、/api/rh/perps：读 Blob 上的 JSON，缓存 5 分钟；
   /api/rh/boards 合并 boards-extra.json 里的持币、Top10 等字段。
4. 新鲜度：快照 ts 超过 2 个周期显示黄色，超过 6 个周期显示红色并提示「本机采集可能已停」。
5. ⑤ 雷达区块顶部固定显示「观察中，非交易信号」。

验收：
- python3 ops/publish.py --dry-run 输出的 JSON 能通过前端类型校验（写一个 zod schema 校验脚本）；
- 跑完 publish 后 rh_v2 下一轮的单轮耗时没有变化（贴 rh_v2 run.py status 前后对比）；
- 停掉 publish 模拟 3 小时无更新，页面变黄；截图；build、typecheck 通过。
```

### 7.4 M3 打磨

```text
做 M3：打磨上线。

1. ① 今日速读：按设计文档 2.1 做 4 张结论卡，结论句先行，点击平滑滚动到对应区块。
2. ⑨ 口径说明：每个区块一段，写清数据源、阈值、刷新频率、已知缺陷；内容从 docs/data-sources.md 和代码里的真实阈值生成，不要写和代码不一致的数。
3. /rh/token/:address 单币详情：价格走势、我们的 Heat/Quality/Entry 历史、状态变化时间线、上币阶梯进度、同名币警告。
4. 分享卡片和页面标题/描述（不要在 __root.tsx 里写 og:* 标签，按仓库约定处理）。
5. 性能：首屏只请求今日速读和折溢价，其余区块进入视口再加载；表格超过 200 行做虚拟滚动或分页。
6. 全站过一遍 EN 文案。

验收：Lighthouse 移动端性能 ≥ 80；控制台无报错；生产构建预览和开发环境渲染一致；截图。
```

### 7.5 单次修 bug / 加功能的模板

```text
背景：docs/robinhood-site-plan.md 是设计依据。
问题/需求：<一句话描述>
期望：<页面上应该看到什么>
范围：只改 <文件或区块>；不动 rh_v2/、market_structure/。
完成标准：<可验证的条件>；build、typecheck 通过；附 1280px 和 390px 截图。
```

---

## 附：数据源速查

| 用途 | 首选 | 备选 | 备注 |
|---|---|---|---|
| 代币化股票链上价/成交/市值 | CoinGecko | GeckoTerminal | 只存在于本链的币用 CG |
| 美股实时价 | Yahoo | Finnhub | Yahoo 非官方，注意 Vercel 出口被拒 |
| 原生币池子、池深、买卖笔数 | GeckoTerminal | DexScreener | GT 免费限速很低，必须缓存 |
| 持币地址 | Robinscan | Blockscout | 慢、常挂，异步补列、缓存 30min |
| 链收入、发射台收入 | DefiLlama | — | |
| 链上 tx/日 | Robinhood Chain RPC 采样 | 区块浏览器 | |
| 上币阶梯 | rh_v2 `listings` / `binance_events` | 各交易所公开接口 | 我们已采 |
| 雷达分数/状态 | rh_v2 `scores` / `state` | — | 我们独有 |
| 永续结构 | market_structure | — | 我们独有 |
| HOOD | Yahoo | Finnhub | |
