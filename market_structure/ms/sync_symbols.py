"""币池同步：从 rh_v2 读取近期上永续的币，核对 Binance 真实合约名后写入 config.toml。
只修改 config.toml 里的 [[symbols]] 块，保留 [general]/[binance]/[bybit] 和注释不变。
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

import aiohttp

from .config import Config

log = logging.getLogger("ms.sync")
MAX_AUTO = 40
DAY_MS = 86_400_000


async def _fetch_binance_perp_symbols(proxy: str | None) -> set[str]:
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, proxy=proxy, timeout=aiohttp.ClientTimeout(total=15)) as r:
            data = await r.json(content_type=None)
    return {sym["symbol"] for sym in data.get("symbols", [])
            if sym.get("contractType") == "PERPETUAL"}


def _read_rh_v2(rhv2_path: str, days: int = 90) -> list[tuple[str, int]]:
    """返回 [(base_symbol_upper, perp_ms), ...]，按 perp_ms 从新到旧排序。"""
    con = sqlite3.connect(f"file:{rhv2_path}?mode=ro", uri=True)
    cutoff = int(time.time() * 1000) - days * DAY_MS
    rows = con.execute(
        "SELECT symbol, perp_ms FROM binance_events "
        "WHERE perp_ms IS NOT NULL AND perp_ms > 0 AND perp_ms >= ? ORDER BY perp_ms DESC",
        (cutoff,),
    ).fetchall()
    con.close()
    return [(r[0].strip().upper(), int(r[1])) for r in rows]


def _resolve_contract(base: str, binance_set: set[str]) -> str | None:
    direct = f"{base}USDT"
    if direct in binance_set:
        return direct
    for pre in ("1000000", "10000", "1000"):
        alt = f"{pre}{base}USDT"
        if alt in binance_set:
            return alt
    return None


def _rewrite_config(path: Path, manual: list[dict], auto: list[dict[str, Any]]) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # 截断到第一个 [[symbols]] 之前，保留所有配置和注释
    first = None
    for i, line in enumerate(lines):
        if line.strip() == "[[symbols]]":
            first = i
            break
    header = lines[:first] if first is not None else lines
    while header and header[-1].strip() == "":
        header.pop()

    out = list(header)
    out.append("")
    for s in manual:
        out.append("[[symbols]]")
        out.append(f'symbol = "{s["symbol"]}"')
        out.append(f'spot = {str(s.get("spot", True)).lower()}')
        out.append("")
    for s in auto:
        out.append("[[symbols]]")
        out.append(f'symbol = "{s["symbol"]}"')
        out.append(f'spot = {str(s.get("spot", True)).lower()}')
        out.append("auto = true")
        out.append("")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _read_symbols(path: Path) -> tuple[list[dict], list[dict]]:
    """解析现有 config.toml，分离 manual 和 auto symbols。"""
    try:
        import tomllib
    except ModuleNotFoundError:  # noqa: UP040
        import tomli as tomllib  # type: ignore[no-redef]
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    manual, auto = [], []
    for s in raw.get("symbols", []):
        d = {"symbol": s["symbol"].upper(), "spot": bool(s.get("spot", True))}
        if s.get("auto"):
            auto.append(d)
        else:
            manual.append(d)
    return manual, auto


async def run(cfg: Config) -> tuple[bool, list[str]]:
    """返回 (是否有变化, 新增/变更的合约名列表)。"""
    rhv2 = Path(cfg.base_dir).parent / "rh_v2" / "rhv2.sqlite"
    if not rhv2.exists():
        log.warning("rh_v2 库不存在: %s", rhv2)
        return False, []

    binance_set = await _fetch_binance_perp_symbols(cfg.proxy)
    rh_rows = _read_rh_v2(str(rhv2))

    auto = []
    mismatched = []
    for base, _ in rh_rows:
        contract = _resolve_contract(base, binance_set)
        if contract:
            auto.append({"symbol": contract, "spot": True})
        else:
            mismatched.append(base)

    if mismatched:
        log.info("核对不上的币（已跳过）: %s", ", ".join(mismatched))

    auto = auto[:MAX_AUTO]
    manual, old_auto = _read_symbols(cfg.config_path)

    # 比较新旧 auto 列表
    old_set = {s["symbol"] for s in old_auto}
    new_set = {s["symbol"] for s in auto}
    if old_set == new_set and len(old_auto) == len(auto):
        log.info("币池无变化 (%d auto symbols)", len(auto))
        return False, []

    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)
    log.info("币池变化: 新增 %s, 移除 %s", added, removed)

    _rewrite_config(cfg.config_path, manual, auto)
    return True, added + removed
