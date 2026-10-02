"""Hourly order: universe, ingest, features, states, outcomes. No veto."""

import argparse

from forced_trade.http import BinanceClient
from forced_trade.pipeline import load_settings, open_db, run_hourly


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--db", default=None)
    parser.add_argument("--bar-open-ts", type=int, default=None,
                        help="re-run one already-closed bar; default derives from now and decision_delay_sec")
    args = parser.parse_args()
    cfg = load_settings(args.config)
    conn = open_db(cfg, args.db)
    client = BinanceClient(cfg["base_url"])
    run_hourly(conn, client, cfg, bar_open_ts=args.bar_open_ts)


if __name__ == "__main__":
    main()
