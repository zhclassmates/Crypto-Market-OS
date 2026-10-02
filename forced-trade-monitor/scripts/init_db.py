"""Initialize sqlite from sql/schema.sql."""

import argparse
from pathlib import Path

from forced_trade.db import init_db

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "forced_trade.sqlite"))
    args = parser.parse_args()
    init_db(args.db)
    print(args.db)


if __name__ == "__main__":
    main()
