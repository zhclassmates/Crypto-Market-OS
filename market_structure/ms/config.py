"""配置加载与时间工具。"""
from __future__ import annotations

import time
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib
from dataclasses import dataclass, field
from pathlib import Path

INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000,
}
BYBIT_OI_INTERVAL = {"5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"}


def now_ms() -> int:
    return int(time.time() * 1000)


def floor_ts(ts: int, step: int) -> int:
    return ts - ts % step


@dataclass
class SymbolCfg:
    symbol: str
    spot: bool = True


@dataclass
class Config:
    db_path: Path
    bar_interval: str
    lookback_days: float
    poll_delay_sec: float
    request_gap_sec: float
    tz: str
    health_at: str
    proxy: str | None
    symbols: list[SymbolCfg]
    fapi: str
    spot_api: str
    force_order_ws: str
    bybit_enabled: bool
    bybit_api: str
    bybit_ws: str
    base_dir: Path = field(default_factory=Path.cwd)
    config_path: Path = field(default_factory=lambda: Path.cwd() / "config.toml")

    @property
    def interval_ms(self) -> int:
        return INTERVAL_MS[self.bar_interval]


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    g, b, y = raw.get("general", {}), raw.get("binance", {}), raw.get("bybit", {})
    interval = g.get("bar_interval", "15m")
    if interval not in INTERVAL_MS:
        raise ValueError(f"bar_interval 不支持: {interval}，可选 {list(INTERVAL_MS)}")
    syms = [SymbolCfg(s["symbol"].upper(), bool(s.get("spot", True))) for s in raw.get("symbols", [])]
    if not syms:
        raise ValueError("config 里至少要有一个 [[symbols]]")
    db_path = Path(g.get("db_path", "data/market_structure.sqlite"))
    if not db_path.is_absolute():
        db_path = path.parent / db_path
    return Config(
        db_path=db_path,
        bar_interval=interval,
        lookback_days=float(g.get("lookback_days", 30)),
        poll_delay_sec=float(g.get("poll_delay_sec", 20)),
        request_gap_sec=float(g.get("request_gap_sec", 0.25)),
        tz=g.get("tz", "Asia/Shanghai"),
        health_at=g.get("health_at", "23:30"),
        proxy=(g.get("proxy") or None),
        symbols=syms,
        fapi=b.get("fapi", "https://fapi.binance.com").rstrip("/"),
        spot_api=b.get("spot_api", "https://api.binance.com").rstrip("/"),
        force_order_ws=b.get("force_order_ws", "wss://fstream.binance.com/ws/!forceOrder@arr"),
        bybit_enabled=bool(y.get("enabled", True)),
        bybit_api=y.get("api", "https://api.bybit.com").rstrip("/"),
        bybit_ws=y.get("ws", "wss://stream.bybit.com/v5/public/linear"),
        base_dir=path.parent,
        config_path=path,
    )
