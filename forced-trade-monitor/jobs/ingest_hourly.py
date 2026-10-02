"""Live ingest for one closed bar. Parsers are the contract; upsert_fact keeps it idempotent."""

import argparse
import time

from forced_trade.http import BinanceClient
from forced_trade.pipeline import (
    ingest_hourly,
    latest_closed_bar,
    load_settings,
    open_db,
    refresh_universe,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--db", default=None)
    parser.add_argument("--bar-open-ts", type=int, default=None)
    args = parser.parse_args()
    cfg = load_settings(args.config)
    conn = open_db(cfg, args.db)
    client = BinanceClient(cfg["base_url"])
    bar = args.bar_open_ts
    now = int(time.time() * 1000)
    if bar is None:
        bar = latest_closed_bar(now, int(cfg.get("decision_delay_sec", 120)) * 1000)
    symbols = refresh_universe(conn, client, bar, cfg, now_ms=now)
    if not symbols:
        print(f"ingest_hourly: no universe for {bar}; aborting")
        return
    if cfg["btc_symbol"] not in symbols:
        symbols.append(cfg["btc_symbol"])
    ingest_hourly(conn, client, symbols, bar, cfg)
    print(f"ingest_hourly: bar={bar} symbols={len(symbols)}")


if __name__ == "__main__":
    main()
