"""Backfill is capped by Binance retention. OI ~1 month, taker ~30 days.

Do not invent earlier history. Start collecting; the 30-day question starts
when 30 complete days exist in this database.
"""

import sys


def main() -> None:
    print("v1.1 backfill cap: oi=30d taker=30d basis=endpoint retention funding=pageable")
    print("refusing unbounded backfill")
    sys.exit(0)


if __name__ == "__main__":
    main()
