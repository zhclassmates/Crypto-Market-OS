"""State labels. Thresholds are hypotheses. S4 is off in v1.1."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_states(path: Path | None = None) -> dict:
    return yaml.safe_load((path or ROOT / "config" / "states.yaml").read_text())


def _num(row: dict, key: str):
    value = row.get(key)
    return value


def evaluate(row: dict, spec: dict | None = None) -> list[dict]:
    spec = spec or load_states()
    results = []
    for name, rule in spec["states"].items():
        if not rule.get("enabled", False):
            results.append({"state": name, "hit": 0, "reason": "disabled"})
            continue
        hit, reason = _one(name, row, rule)
        results.append({"state": name, "hit": int(hit), "reason": reason})
    return results


def _one(name: str, row: dict, rule: dict) -> tuple[bool, str]:
    if row.get("data_quality_flag") and "ts_unaligned" in str(row.get("data_quality_flag")):
        return False, "ts_unaligned"
    if name == "crowded_long_under_pressure":
        return _crowded_long(row, rule)
    if name == "crowded_short_under_pressure":
        return _crowded_short(row, rule)
    if name == "deleveraging_in_progress":
        return _delever(row, rule)
    if name == "basis_distortion":
        return _basis(row, rule)
    return False, "unhandled"


def _regular(row: dict) -> bool:
    return row.get("funding_rate_type") in (None, "Regular")


def _crowded_long(row: dict, rule: dict) -> tuple[bool, str]:
    need = ("funding_pct_30d", "ret_4h_vs_btc", "oi_qty_chg_4h", "taker_imbalance_4h")
    if any(row.get(k) is None for k in need) or not _regular(row):
        return False, "missing_or_special"
    ok = (
        row["funding_pct_30d"] >= rule["funding_percentile_min"]
        and row["ret_4h_vs_btc"] < rule["ret_4h_vs_btc_max"]
        and row["oi_qty_chg_4h"] >= rule["oi_change_4h_min"]
        and row["taker_imbalance_4h"] <= rule["taker_imbalance_4h_max"]
    )
    return ok, "pass" if ok else "threshold"


def _crowded_short(row: dict, rule: dict) -> tuple[bool, str]:
    need = ("funding_pct_30d", "ret_4h_vs_btc", "oi_qty_chg_4h", "taker_imbalance_4h")
    if any(row.get(k) is None for k in need) or not _regular(row):
        return False, "missing_or_special"
    ok = (
        row["funding_pct_30d"] <= rule["funding_percentile_max"]
        and row["ret_4h_vs_btc"] > rule["ret_4h_vs_btc_min"]
        and row["oi_qty_chg_4h"] >= rule["oi_change_4h_min"]
        and row["taker_imbalance_4h"] >= rule["taker_imbalance_4h_min"]
    )
    return ok, "pass" if ok else "threshold"


def _delever(row: dict, rule: dict) -> tuple[bool, str]:
    need = ("abs_ret_1h_z", "oi_chg_1h_z", "flow_aligned_with_price")
    if any(row.get(k) is None for k in need):
        return False, "missing"
    aligned = bool(row["flow_aligned_with_price"])
    if rule.get("require_flow_alignment") and not aligned:
        return False, "flow"
    ok = (
        row["abs_ret_1h_z"] >= rule["abs_return_z_min"]
        and row["oi_chg_1h_z"] <= rule["oi_change_z_max"]
        and aligned
    )
    return ok, "pass" if ok else "threshold"


def _basis(row: dict, rule: dict) -> tuple[bool, str]:
    z = row.get("basis_z_7d")
    if z is None:
        return False, "missing"
    ok = abs(z) >= rule["basis_z_abs_min"]
    return ok, "observe" if ok else "threshold"


def flow_aligned(ret_1h: float | None, taker_imbalance_1h: float | None) -> int | None:
    if ret_1h is None or taker_imbalance_1h is None:
        return None
    if ret_1h == 0 or taker_imbalance_1h == 0:
        return 0
    return int((ret_1h > 0) == (taker_imbalance_1h > 0))
