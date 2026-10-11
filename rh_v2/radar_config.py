"""Radar 阈值与口径。全部集中在这里，引擎里不得再写数字常量。

规格见用户提供的 Radar Backend Spec §1–39。带 [SPEC] 的值逐字来自规格，禁止改动；
带 [IMPL] 的值是规格没有给出、实现时必须选定的数据有效性参数，在 README / 报告里公开。
"""

DAY_SEC = 86400
# [PROJECT] 与 src/lib/rh/streak.ts KLINE_FETCH_WINDOW_SEC 一致：观测时间只能证明回看窗口内的 bar 定稿
KLINE_FETCH_WINDOW_SEC = 100 * DAY_SEC

# ---------------- FAST GATE ----------------
GATE_REJECT_LIQUIDITY_USD = 10_000          # [SPEC §7]  liquidity < 10k → REJECT
GATE_LOW_LIQUIDITY_USD = 50_000             # [SPEC §8/9] 10k ≤ liq < 50k → PASS + low_liquidity
# [IMPL] 关键 gate 数据（价格、流动性）超过这个年龄就不能"确认" → UNKNOWN（不是 REJECT）。
GATE_MAX_INPUT_AGE_SEC = 24 * 3600

# ---------------- Signals ----------------
VOLUME_BASELINE_DAYS = 7                    # [SPEC §12] preceding 7 completed-day median
BREAKOUT_WINDOW_DAYS = 10                   # [SPEC §22] previous 10 finalized candles
NEAR_BREAKOUT_MIN_DISTANCE = -0.10          # [SPEC §24] -10% ≤ distance ≤ 0
CROSS_LIST_WINDOW_SEC = 3600                # [SPEC §20] 60m
# 独立 discovery source（discovery_event.source）。seed 不是榜单，不计数。
CROSS_LIST_SOURCES = ("trending", "hot", "signal", "trenches")
# discovery_event.source → source_health.source（只用于展示健康）
CROSS_LIST_HEALTH_SOURCE = {
    "trending": "gmgn",
    "hot": "gmgn_hot",
    "signal": "gmgn_signal",
    "trenches": "gmgn_new_pair",
}
# [IMPL] holder / liquidity 历史 = discovery_event 里 GMGN 榜单每次看到该币时带的
# holder_count / liquidity。只往回看这么久找"最近两次快照"。
SNAPSHOT_HISTORY_LOOKBACK_SEC = 24 * 3600
# [PROJECT] 一个"快照" = 采集器 discovery_event 的 time_bucket（market_research.DISCOVERY_BUCKET_SEC = 300）。
# 同一桶内多个榜单几秒内的重复看到不算两次快照。
SNAPSHOT_BUCKET_SEC = 300
# [IMPL] 突破比较用的"当前有效价格"最大年龄。超过 → breakout_10d = null。
BREAKOUT_PRICE_MAX_AGE_SEC = 3600

# ---------------- Scoring [SPEC §13–28] ----------------
# 每档 (下限, 分)。从高往低匹配第一个 value >= 下限 的档；都不满足 → 0。
VOLUME_RATIO_TIERS = ((3.0, 25), (2.0, 20), (1.5, 10))
BUY_SHARE_TIERS = ((0.65, 15), (0.60, 10), (0.55, 5))
# holder / liquidity：<= 0 → 0；(0, t1) → 5；以下为 >= 下限的档
HOLDER_GROWTH_TIERS = ((0.10, 15), (0.05, 10))
HOLDER_GROWTH_POSITIVE = 5
LIQUIDITY_GROWTH_TIERS = ((0.25, 15), (0.10, 10))
LIQUIDITY_GROWTH_POSITIVE = 5
CROSS_LIST_TIERS = ((4, 20), (3, 15), (2, 10))
BREAKOUT_CONFIRMED_SCORE = 20
BREAKOUT_NEAR_SCORE = 5
SCORE_CAP = 100

SIGNAL_NAMES = (
    "volume_ratio",
    "buy_share",
    "holder_growth",
    "liquidity_growth",
    "cross_list_count_60m",
    "breakout_10d",
)

# ---------------- Stage [SPEC §29–36] ----------------
STAGES = ("NORMAL", "OBSERVE", "EARLY", "READY")
OBSERVE_MIN_SCORE = 40
EARLY_MIN_SCORE = 60
READY_MIN_SCORE = 75
READY_MIN_KNOWN_SIGNALS = 4
READY_MIN_VOLUME_RATIO = 2.0
READY_MIN_BUY_SHARE = 0.60
READY_MIN_CROSS_LIST = 2
# 降级：score < 阈值，且连续 N 次 valid observation
DOWNGRADE_BELOW = {"READY": 65, "EARLY": 50, "OBSERVE": 30}
DOWNGRADE_CONSECUTIVE = 2

# ---------------- REVIVAL [SPEC §37–38] ----------------
REVIVAL_MIN_AGE_DAYS = 7
REVIVAL_MIN_VOLUME_RATIO = 3.0
REVIVAL_MIN_SUPPORTING = 2
REVIVAL_MIN_BUY_SHARE = 0.60
REVIVAL_MIN_CROSS_LIST = 2
# [IMPL] "历史沉寂期"：最新定稿日之前的 7 个定稿日（与 volume baseline 同一窗口）必须齐全，
# 且其中每一天的成交额都 <= 最新一天成交额 × 该比例。窗口不全 → 无法证明 → null。
REVIVAL_DORMANT_WINDOW_DAYS = 7
REVIVAL_DORMANT_MAX_FRACTION_OF_LATEST = 1 / 3

# ---------------- Runner ----------------
RUN_INTERVAL_SEC = 300                      # [IMPL] 与最慢的 discovery 源（300s）对齐
# [IMPL] 非 transition 引用的 evaluation 保留天数（transition 引用的永久保留）
EVAL_RETENTION_DAYS = 30
# [IMPL] API 侧：radar 最后一轮超过这个年龄 → STALE
RUN_STALE_AFTER_SEC = 3 * RUN_INTERVAL_SEC
