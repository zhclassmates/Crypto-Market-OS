"""Fill closed horizons for the decision-time universe only."""

import argparse
import time

from forced_trade.pipeline import fill_outcomes, latest_closed_bar, load_settings, open_db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--db", default=None)
    parser.add_argument("--floor", type=int, default=None,
                        help="latest bar_open whose close is known; default = latest kline in db")
    args = parser.parse_args()
    cfg = load_settings(args.config)
    conn = open_db(cfg, args.db)
    floor = args.floor
    if floor is None:
        floor = latest_closed_bar(int(time.time() * 1000), int(cfg.get("decision_delay_sec", 120)) * 1000)
    written = fill_outcomes(conn, cfg, now_close_floor=floor)
    print(f"fill_outcomes: floor={floor} rows={written}")


if __name__ == "__main__":
    main()
