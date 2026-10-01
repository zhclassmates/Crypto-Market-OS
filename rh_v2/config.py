"""RH V2 配置。所有阈值集中在这里，改规则只改这个文件。"""
import os

DB_PATH = os.environ.get("RHV2_DB", os.path.join(os.path.dirname(__file__), "rhv2.sqlite"))
OUT_DIR = os.environ.get("RHV2_OUT", os.path.join(os.path.dirname(__file__), "out"))
LOCK_PATH = os.path.join(os.path.dirname(__file__), "collector.lock")

# ---- 单轮运行控制 ----
BUDGET_SECS = 570              # 单轮总预算（<10 分钟）；超时后跳过剩余非关键步骤
LISTINGS_BUDGET_SECS = 240     # 交易所状态刷新（每日一次）最多占用的时间
CIRCUIT_FAILS = 3              # 同一数据源连续失败多少次后本轮熔断，不再请求
HTTP_TIMEOUT = 12             # 单次请求超时秒数
HTTP_TRIES = 3                # 单次请求最大尝试次数（4xx 除 429 外不重试）

# ---- 链 ----
CHAIN_DS = "robinhood"          # DexScreener chainId
CHAIN_GT = "robinhood"          # GeckoTerminal network id
CHAIN_ID = "4663"               # EVM chain id（币安 Alpha 列表里的 chainId）
BLOCKSCOUT = "https://robinhoodchain.blockscout.com/api/v2"
BLOCKSCOUT_KEY = os.environ.get("BLOCKSCOUT_API_KEY", "")   # 可选；dev.blockscout.com 免费申请

# ---- 限速（每秒请求数，保守取值）----
RPS = {
    "dexscreener": 4.0,     # 官方 300/min
    "geckoterminal": 0.15,  # 公开层 10~30/min 且不稳，按 10/min 设计
    "blockscout": 3.0,
    "binance": 2.0,
    "aster": 2.0,
    "hyperliquid": 1.0,
}

# ---- 宇宙 ----
UNIVERSE_REFRESH_HOURS = 6       # 每 6 小时从 GT 拉一次按 24h 成交排序的池子
GT_UNIVERSE_PAGES = 10           # 每页 20 个池子 → 最多 200 个；外加 new_pools 1 页
EXTRA_TOKENS_FILE = os.environ.get("RHV2_EXTRA", os.path.join(os.path.dirname(__file__), "extra_tokens.txt"))

# ---- 观察池（只有这些进入深挖 + 状态机）----
OBS_MIN_LIQ = 25_000
OBS_MIN_VOL24 = 20_000
INVALID_LIQ = 10_000

# ---- 状态机 ----
READY_MIN_SNAPSHOTS = 6          # 自有快照少于 6 小时的币不准进 READY
DOWNGRADE_CONFIRM_HOURS = 2      # 降级需连续 2 小时确认，避免来回跳
OVERHEAT_PC24 = 300              # 24h 涨幅 %
OVERHEAT_VOL_LIQ = 10            # Vol24/池深
OVERHEAT_PC24_HARD = 500

# ---- ListingP ----
LISTING_MIN_N = 20               # 格子样本 < 20 → 输出「不确定」
REGIME_CUTOFF_MS = 1788825600000 # 2026-09-08 00:00 UTC：币安 Alpha 2.0 接入 RH 链，之后算新政体

# ---- 告警（可选）----
TG_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TG_CHAT_ID", "")
