import tempfile
import unittest
from pathlib import Path

from forced_trade.binance import parse_oi
from forced_trade.db import init_db, upsert_fact


class IdempotencyTest(unittest.TestCase):
    def test_same_payload_is_noop_and_change_revises(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = init_db(Path(tmp) / "t.sqlite")
            payload = {
                "symbol": "BTCUSDT",
                "sumOpenInterest": "1",
                "sumOpenInterestValue": "2",
                "timestamp": 3_600_000,
            }
            row = parse_oi(payload)
            body = row.pop("_payload")
            first = upsert_fact(conn, "raw_oi_1h", ["symbol", "bar_open_ts"], row, body)
            second = upsert_fact(conn, "raw_oi_1h", ["symbol", "bar_open_ts"], row, body)
            changed = dict(payload)
            changed["sumOpenInterest"] = "9"
            row2 = parse_oi(changed)
            body2 = row2.pop("_payload")
            third = upsert_fact(conn, "raw_oi_1h", ["symbol", "bar_open_ts"], row2, body2)
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM raw_oi_1h").fetchone()[0]
            revisions = conn.execute("SELECT COUNT(*) FROM raw_revisions").fetchone()[0]
            qty = conn.execute("SELECT oi_qty FROM raw_oi_1h").fetchone()[0]
            self.assertEqual(first, "inserted")
            self.assertEqual(second, "noop")
            self.assertEqual(third, "revised")
            self.assertEqual(count, 1)
            self.assertEqual(revisions, 1)
            self.assertEqual(qty, 9)


if __name__ == "__main__":
    unittest.main()
