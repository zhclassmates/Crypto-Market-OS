"""Feature build entry. Logic lives in forced_trade.features."""

import argparse
import time

from forced_trade.pipeline import build_features, latest_closed_bar, load_settings, open_db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--db", default=None)
    parser.add_argument("--bar-open-ts", type=int, default=None)
    args = parser.parse_args()
    cfg = load_settings(args.config)
    conn = open_db(cfg, args.db)
    bar = args.bar_open_ts
    if bar is None:
        bar = latest_closed_bar(int(time.time() * 1000), int(cfg.get("decision_delay_sec", 120)) * 1000)
    written = build_features(conn, bar, cfg)
    print(f"build_features: bar={bar} rows={written}")


if __name__ == "__main__":
    main()
