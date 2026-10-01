你在 ~/Desktop/ctiwvGy8hZk3VdCu-grok-workspace 工作。这一轮只做后端整合和运维，不碰网页。

## 背景
这个文件夹里有三样东西：
1. 网页（src/、server/、.vercel/，Grok App Builder 生成）。本轮不动。AGENTS.md 是写给 Grok 的，本轮忽略。
2. attachments/：rh_v2，Robinhood 链新币扫描（宇宙 → 小时快照 → 四列评分 → 状态机 → ListingP）。纯标准库，库文件是 attachments/rhv2.sqlite，设计为每小时跑一次。
3. market_structure/：Binance/Bybit 永续市场结构采集器（K 线 + CVD、OI、资金费率、可见强平）。依赖 aiohttp，常驻进程，库文件是 market_structure/data/market_structure.sqlite。

两者是两条独立的采集链，节奏不同（一个每小时一轮，一个按 15m bar 常驻），各自单写一个 SQLite。不要合并数据库，也不要合并进程。
十月只采数：不新增信号，不改评分规则，不做 UI。

## 任务（按顺序做，每步验证通过再做下一步，每步结束提交一次 git）
1. **整理目录。**
   - 如果还没有 git，先 `git init` 并把现状提交一次。
   - 用 `git mv attachments rh_v2` 改名，并修正所有引用这个路径的地方（plist、README）。
   - .gitignore 加入：`__pycache__/`、`*.sqlite*`、`out/`、`data/`、`logs/`、`reports/`、`.venv/`、`config.toml`。
   - test_api*.py 是调试脚本，删除前先问我。

2. **修好 rh_v2 的定时运行。**
   - 现状：库里只有 1 个小时快照（2026-09-30 14:00 UTC），meta 表里的 last_run 显示那一轮跑了 30311 秒，之后再没有整点运行。
   - 先查原因：在 run_once 里给每一步加计时日志，手动跑一轮 `python3 run.py once`，用数据说明慢在哪里（GeckoTerminal 的 0.15 rps 限速和 429 退避？Binance 请求超时？Mac 睡眠？），然后再动手改。
   - 目标是单轮少于 10 分钟。具体要求：
     - 加文件锁：上一轮没跑完，本轮就跳过并记日志。
     - 给 run_once 设总时间预算：超时就跳过剩余的非关键步骤，并把跳过的步骤记进 last_run。
   - 修 launchd 配置：
     - 把 /usr/bin/python3 换成 `which python3` 返回的绝对路径。
     - 把 `__DIR__` 换成真实路径。
     - 安装到 ~/Library/LaunchAgents，用 launchctl bootstrap 加载。
   - 验收：连续 2 个整点都写入了新快照。

3. **安装 market_structure。**
   - 按 market_structure/README.md 执行 `bash deploy/install_mac.sh`。
   - 如果访问 Binance 需要代理，先问我代理地址，写进 config.toml 的 proxy。
   - 真实 API 返回的字段和代码不一致时，以真实返回为准：修改 ms/normalize.py，并补上对应的测试。
   - 验收：`.venv/bin/python -m ms health --hours 1` 的第一行是 OK，或者只有能解释的 WARN。把输出贴给我。

4. **两个系统之间只有一个接口：币池同步。**
   - 新建 market_structure/ms/sync_symbols.py：
     - 以只读方式打开 rh_v2/rhv2.sqlite。
     - 取 binance_events 里 perp_ms 不为空、且上永续时间在最近 90 天内的币。
     - 转换成 Binance USD-M 合约名（{SYMBOL}USDT）。rh_v2 去掉了 1000 之类的前缀，所以要用 fapi exchangeInfo 核对真实合约名，核对不上的跳过并记日志。
   - 并入 config.toml 的币池：
     - 手写的条目保持原样。
     - 自动加入的条目标记 `auto = true`，不再满足条件时自动移除。
     - 自动条目最多 40 个，按上永续时间从新到旧取。
   - 每天跑一次（挂进 ms run 的夜间任务）。币池有变化时写日志，并重新加载币池，不需要手动重启。
   - 用临时库造数据写单元测试。

5. **统一夜间报告。**
   - 新建 ops/nightly.py，以只读方式读取两边的库，输出 reports/YYYY-MM-DD.txt，内容包括：
     - rh_v2 当天跑了几轮、失败几轮、单轮最长用时、各状态的币数、新进入 READY 的币。
     - market_structure 的 health 报告。
     - 币池同步的变化。
   - 只写文件，不推送。

6. **在根目录写 README。** 说明两条采集链怎么安装、怎么看运行状态、怎么停止。

## 约束
- 不改 rh_v2 的评分、阈值和状态机。
- market_structure 的表结构只能新增，不能修改已有的表。
- 不写任何下单或私钥相关的代码。
- 遇到不确定、而且做了难以撤回的事情（删除文件、改数据库里已有的数据），先问我。

## 完成后交给我
- 改动清单。
- 两条链当前的运行状态，附上 health 输出和 rh_v2 最近 3 轮的 last_run。
- 还没解决的问题。
