"""Print latest health row per source. Not a single API-ok flag."""

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "forced_trade.sqlite"))
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    rows = conn.execute(
        """
        SELECT source, age_sec, success, rows_got, ts_semantics, error
        FROM data_health
        WHERE id IN (SELECT MAX(id) FROM data_health GROUP BY source)
        ORDER BY source
        """
    ).fetchall()
    if not rows:
        print("no health rows")
        return
    for source, age, ok, got, semantics, error in rows:
        mark = "ok" if ok else "dead"
        print(f"{source:12} age={age} {mark} rows={got} ts={semantics} {error or ''}")


if __name__ == "__main__":
    main()
