"""Shared market-chain configuration loaded from the workspace manifest."""
import json
import os


_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "market-chains.json")
with open(_CONFIG_PATH, encoding="utf-8") as _config_file:
    _CONFIG = json.load(_config_file)

_ROWS = tuple(_CONFIG["chains"])
DEFAULT_MARKET_CHAINS = tuple(row["id"] for row in _ROWS)


def configured_market_chains():
    raw = os.environ.get("MARKET_CHAINS")
    if raw is None:
        return DEFAULT_MARKET_CHAINS
    requested = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    if not requested:
        return DEFAULT_MARKET_CHAINS
    unknown = tuple(chain for chain in requested if chain not in DEFAULT_MARKET_CHAINS)
    if unknown:
        raise ValueError(f"unsupported MARKET_CHAINS: {','.join(unknown)}")
    return tuple(dict.fromkeys(requested))


MARKET_CHAINS = configured_market_chains()
DEXSCREENER_CHAINS = {row["id"]: row["dexscreener"] for row in _ROWS}
SIGNAL_CHAINS = frozenset(row["id"] for row in _ROWS if row.get("signal"))
