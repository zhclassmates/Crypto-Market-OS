"""Universe snapshot at decision time. Later rank changes do not rewrite it."""

from __future__ import annotations

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS


def listing_days(onboard_ms: int, asof_ms: int) -> float:
    return (asof_ms - onboard_ms) / DAY_MS


def select_universe(
    rows: list[dict],
    asof_ms: int,
    top_n: int = 80,
    min_listing_days: float = 14,
    quote_asset: str = "USDT",
    contract_type: str = "PERPETUAL",
) -> list[dict]:
    kept = []
    for row in rows:
        if row.get("contractType") != contract_type:
            continue
        if row.get("status") != "TRADING":
            continue
        if row.get("quoteAsset") != quote_asset:
            continue
        onboard = row.get("onboardDate")
        if onboard is None:
            continue
        days = listing_days(int(onboard), asof_ms)
        if days < min_listing_days:
            continue
        vol = row.get("quoteVolume")
        if vol is None:
            continue
        kept.append({**row, "listing_days": days, "quote_volume": float(vol)})
    kept.sort(key=lambda r: r["quote_volume"], reverse=True)
    out = []
    for rank, row in enumerate(kept[:top_n], start=1):
        out.append(
            {
                "ts": asof_ms,
                "symbol": row["symbol"],
                "rank": rank,
                "quote_volume": row["quote_volume"],
                "listing_days": row["listing_days"],
                "contract_type": row["contractType"],
                "status": row["status"],
                "quote_asset": row["quoteAsset"],
            }
        )
    return out
