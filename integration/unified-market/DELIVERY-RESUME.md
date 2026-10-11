最新历史覆盖恢复见 [DELIVERY-HISTORY-COVERAGE.md](DELIVERY-HISTORY-COVERAGE.md)：100资产本地审计、16资产有界免费请求、12资产真实七日补齐及727测试已核验；共享限流后停止扩大，现有页面功能不变。检查点见 backups/history-coverage-20261011/STATE.md。以下历史记录保留。

最新后续交付见 [DELIVERY-ALL-MARKET.md](DELIVERY-ALL-MARKET.md)：已在本次 V1.7 恢复基础上完成全部代币默认展示和相关功能；以下历史记录保留。

# 2026-10-11 中断恢复交付：统一市场 V1.7

## 原任务与中断位置

Git 起点为 a512543，工作区已有大量未提交变更和新增模块，全部保留；未 reset、stash、清理或重建项目，也未替用户提交既有改动。
最新工作区记录是 V1.6 的 GMGN/原生资产接入，但对照核心项目发现 10 月 10 日 21:31 的 authoritative unified_market.py 已到 V1.7，数据库仍 V1.6。真实遗留步骤是应用“当前报价质量与历史完整度分开判断”的投影规则并验收。

| 阶段 | 中断时状态 | 恢复后状态 |
|---|---|---|
| 原三源 V1.5 接入和页面 | 已完成 | 保留 |
| GMGN 接入、原生身份映射、分页/筛选/排序 | 已完成或已实现待复验 | 复验通过 |
| V1.7 核心报价质量规则及测试 | 代码完成，数据库未应用 | 已同步并核验 |
| 验收脚本、七日参与数查询、文档 | 部分完成 | 已修复和更新 |
| 构建、测试、开发/生产验收、恢复检查点 | 缺最新证明 | 已保存完整证据 |

## 本次修改

- browser-smoke-verdict 默认截图路径从机器绝对路径改为当前项目目录，并修复过时测试断言。
- 七日参与数改为一次 GROUP BY 查询，保留全市场先筛选/排序再分页的口径；新增两项测试覆盖参与数、日期筛选及隐藏偏好。
- 浏览器 QA 使用当前 SQLite 查询核对结果，替换 V1.5 固定计数和 DEX 两条记录假设；增加 GMGN、原生币默认 VALID、日期排序/涨跌筛选核验；控制台/页面错误直接失败。
- 保留旧 V1.6 副本，将已有核心 V1.7 源码及测试同步到 integration；新增 resume_v17.py，仅运行现有本地同步逻辑，不重装、不采集、不调用 API。
- 页面明确当前报价资格和七日历史完整度独立；文档更新到 V1.7，V1.5 历史交付记录保留。

## 发布结果与数据安全

- 版本：unified-v1.7；UTC 发布：2026-10-11T00:10:31.698682+00:00。
- 唯一身份资产 212,184，链级代币 205,104，GMGN 190,071，多源匹配 144,476，身份待确认 7,077。
- VALID 7,795，PARTIAL 204,389。BTC/ETH/SOL 均 VALID，仍保留 price_history_7d、daily_return 等真实缺失项。
- 11 张原始采集/质量表哈希前后相同；旧 canonical 身份全部保留或经 redirects 保留；无删除原始记录。
- 源数据库通过 SQLite backup 保存。链上三张输入表通过只读事务冻结，原采集器持续运行；重复同步使用同一输入，资产和日期重算均为 0。同步结束恢复原 live 数据路径。
- 本次外部行情 API 调用 0。版本变化需要重新计算派生投影，未重新采集历史或重建应用。
- 完整七日资产 232，有真实日涨幅资产 2,856。缺失数据保持缺失，不构造历史。

## 验证

- npm test：脚本 195、TypeScript 286、链上 Python 43 项通过；核心 Python 155、运维 Python 8 项通过（共 687 项）。工作区整合副本另外 73 项通过，包含复用夹具的重复测试，不重复计入上数。
- npm run typecheck、npm run build、git diff --check 通过。
- 优化前后六类真实只读查询结果完全一致。一次同机测量 GMGN 查询约 3925ms → 887ms；测量受缓存和负载影响，不代表统一延迟保证。
- 开发和生产各 16 项功能验收通过：数据库分页、默认质量、GMGN/DEX 来源、合约搜索、原始详情、星标/隐藏、日期多优先级、负向过滤、BTC/ETH/SOL VALID、手机无横向溢出。
- 两端控制台/页面错误为空。开发交互日志另记录平台 extensions.js 一次 ERR_ABORTED，未修改平台脚本；生产交互请求无失败。
- agent-browser 在此本机未安装，复用现有 Playwright 验收脚本。桌面与手机截图均已人工查看。
- 最终 smoke 等行情、质量与健康三个区域完整加载后取样，开发/生产基线无偏差；结果见 screenshots/resume-v17-ready-*.json；本工具型数据面板使用平台默认分享卡，BRAND NOTE 为提示而非测试失败。

## 恢复检查点和证据

backups/resume-20261011/：初始代码与 Git 状态、stage2-tools.tar.gz、stage3-query.tar.gz、stage4-v17-code.tar.gz、before-v17-* 数据库/代码/输入快照、最终代码快照和 current-state.json。
恢复时先读 current-state.json / PROGRESS.md 和 v17-verification.json，已发布的 V1.7 无需再次安装。不要盲目恢复数据库：数据采集会继续推进，旧备份仅在确需回退时使用。

核心证据：v17-verification.json、v17-before.json、query-parity.json、preservation-audit.json；测试/构建日志在同目录；qa-v17-dev.json 与 qa-v17-built.json 在 integration/unified-market。

本次识别的遗留编程步骤均已处理；未来采集、历史补齐和来源身份确认仍随真实数据更新，不能以程序假造。开发预览保持运行。

上游运行限制：已有健康面板仍如实显示部分 GMGN 主源 STALE/failed；这与浏览器应用错误和 V1.7 投影验收不同。本次未更改采集器限速或凭据，未将延迟源伪标 LIVE。
