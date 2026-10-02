"""Label states. Disabled states are written as hit=0 reason=disabled."""

import argparse
import time

from forced_trade.pipeline import label_states, latest_closed_bar, load_settings, open_db


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
    written = label_states(conn, bar, cfg)
    print(f"label_states: bar={bar} rows={written}")


if __name__ == "__main__":
    main()
