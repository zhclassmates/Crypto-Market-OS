# World Model OS 三源统一市场数据层 V1 交付核验

> 这是 2026-10-10 的 V1.5 历史验收记录；后续 GMGN/V1.7 恢复验收见 `DELIVERY-RESUME.md`。原始证据保留。

## 1. 修改文件和数据库对象

现有核心项目 `/Users/zhaomosheng/Desktop/world-model-os-v1`：
- 新增 `unified_market.py`、`tests/test_unified_market.py`、`UNIFIED_MARKET.md`。
- `market_ingest.py` 仅追加质量闸门完成后的本地统一同步调用；整合失败保留上一可信视图，采集逻辑和源质量规则不变。

现有前端工作区：
- 新增 `src/components/wm-unified-market.tsx`。
- 新增 `src/lib/rh/wm-unified-query.ts`、`wm-unified-query.test.ts`、`wm-unified-server.ts`、`wm-unified-display.ts`、`wm-unified-display.test.ts`。
- `src/components/market-view.tsx` 复用健康区域并挂载统一市场；原有链上列表及筛选折叠后按需加载。
- `src/lib/rh/market-server.ts`、`market-health-server.ts` 调整现有数据库路径在生产构建中的定位。
- `package.json` 接入新增测试；`market-table-ui.test.ts` 和 `scripts/browser-smoke-verdict.test.mjs` 修正已有常量/本地截图路径契约的过时断言。
- `startup.sh`、`scripts/preview.mjs` 保证本机持久开发服务、生产预览可验证；`scripts/browser-smoke.mjs` 支持等统一记录加载；新增 `scripts/wm-unified-qa.mjs`。
- `integration/unified-market/` 保存安装/更新/只读核验脚本、源文件副本、测试日志与验收证明。未新建应用，未更换数据库。

SQLite 新增十张派生/映射表：`wm_unified_assets`、`wm_unified_sources`、`wm_unified_chain_tokens`、`wm_unified_identity_links`、`wm_unified_redirects`、`wm_unified_raw_versions`、`wm_unified_current`、`wm_unified_daily`、`wm_unified_conflicts`、`wm_unified_meta`。
新增视图 `wm_unified_market_view`、`wm_unified_research_view`。后者仅暴露 VALID 且身份已确认的记录，当前因真实历史等缺失为 0 条；研究模块可直接查询统一契约，不新增推理/交易系统。

原始表不变。写入前 SQLite backup 位于核心项目 `data/unified-backup-20261010T112510Z`。当前版本 unified-v1.5。

## 2. 原始记录数

| 来源 | 最新 UTC 快照 | 日期口径 | 记录数 | 质量 |
|---|---|---|---:|---|
| CG | 2026-10-10 | intraday | 18,235 | TRUSTED / complete |
| CMC | 2026-10-09 | utc_finalized | 8,141 | TRUSTED / complete |
| DEX | 2026-10-10 | watchlist / intraday | 2 | TRUSTED / complete |

## 3. 去重结果

统一资产身份记录 23,044，链级代币 15,961。这是按现有可证身份进行保守去重的结果，包括尚未能确认跨源经济身份的独立记录，不能宣称全部是已确认的真实经济唯一资产。

## 4. 匹配、未解析和冲突

多来源匹配资产 3,334；UNRESOLVED 7,083；已有合约身份覆盖约 69.3%。实际经可信官方映射确认的跨链关联 0，现有缓存不足，未按 Symbol/Name 推测 BTC、ETH 等原生资产的跨源关联。测试覆盖可信跨链映射机制。

同步口径字段冲突 0，身份冲突 0；9,996 对 CG/CMC 字段因日期或统计窗口不一致为 NOT_COMPARABLE，保留双方值、时间与原因，差异比例为 NULL。冲突为 0 不表示两源所有值相同。

## 5. 七日历史

T-6..T0 = 2026-10-04..2026-10-10 UTC；有真实历史的资产 16,489，完整七天资产 0。
统一日快照 19,410：10 月 9 日 CMC 日终 8,141；10 月 10 日 CG 盘中 11,268、DEX 盘中 1。
源报价实际 UTC 日期不属于采集日的旧报价不填入采集日历史单元格，但原值可追溯。每日涨幅可用资产 0，因为没有相邻同源 UTC 日终价格；已有真实 24h 涨幅独立保留。缺失日期显示 —。

## 6. 额外外部行情 API

CG / CMC / DEX 整合 API 调用 0。只读本地 SQLite；测试封锁网络并断言零调用。页面原有链上观察与平台品牌静态资源不属于新增三源采集。

## 7. 测试与数据安全

- 全部 632 项自动化测试通过：脚本 195 + TypeScript 284 + 现有链上 Python 43 + 核心 Python 110。核心保留原有 82 项（包含用户此前 58 项采集/质量测试）并新增 28 项整合测试。
- npm run build、npm run typecheck 均通过。
- 真实数据库原始表哈希不变；只读备份核验、注入失败回滚通过。
- 二次执行 recomputed_assets=0、recomputed_dates=0；修正历史单日只重算该日及下一日。版本、身份和来源质量变化按需要修复，正常更新不全量重建。
- 本地输入版本指纹扫描仍遍历已存来源元数据，避免漏掉补录/回填；实际派生发布仅影响相关资产/日期。
- 开发和生产浏览器功能检查各 10 项通过，桌面/手机有真实内容、页面无横向溢出、无 pageErrors，生产与开发无基线偏差。
- 通用浏览器 smoke 仍退出 2：唯一控制台错误是平台保留的 `https://grok.com/grok-app-builder/extensions.js` 被浏览器以 ERR_BLOCKED_BY_RESPONSE.NotSameOrigin 拒绝。未移除/遮蔽品牌脚本，不能报告浏览器控制台完全无错误。

## 8. 实际页面

`http://localhost:8080/#sec-market` 已真实核验并保持运行。统一市场显示本地合并结果，数据库分页每页 50 条，搜索名称/Symbol/合约，按链/来源/质量筛选、市值/成交量/日期排序、Shift 多日期优先级、每日方向过滤、星标/隐藏及原始数值详情均可使用。DEX 池口径与资产总量明确分开，身份合并后旧星标/隐藏通过 redirects 保留。
生产构建 `127.0.0.1:8081` 同样验证通过上述功能。

证据：`final-db-verification.json`、`real-final-verification.json`、`final-readonly-audit.json`、`python-tests.log`、`app-tests.log`、`build.log`、`typecheck.log`、`qa-dev.json`、`qa-built.json`；截图与 smoke verdict 在现有 `screenshots/wm-unified-*`。
