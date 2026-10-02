#!/usr/bin/env python3
"""创建时间三个字段不能混写。不打外部接口。"""
import tempfile
import unittest

import market_db as db


class RankTimesTest(unittest.TestCase):
    def test_zero_and_milliseconds(self):
        self.assertIsNone(db.unix_ts(0))
        self.assertIsNone(db.unix_ts("0"))
        self.assertEqual(db.unix_ts(1_790_810_211_000), 1_790_810_211)

    def test_open_timestamp_is_not_token_or_pair_time(self):
        token_created, pair_created = db.rank_times({
            "creation_timestamp": 0,
            "open_timestamp": 1_700_000_000,
            "pool": {"creation_timestamp": 1_700_000_100},
        })
        self.assertIsNone(token_created)
        self.assertEqual(pair_created, 1_700_000_100)

    def test_token_time_stays_out_of_pair_column(self):
        token_created, pair_created = db.rank_times({
            "creation_timestamp": 1_781_535_194,
        })
        self.assertEqual(token_created, 1_781_535_194)
        self.assertIsNone(pair_created)


class UpsertTokenTest(unittest.TestCase):
    def test_three_clocks_stay_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            con = db.connect(tmp + "/t.sqlite")
            now = 1_700_000_000
            db.upsert_token(con, "sol", "MintA", "MICRO", "one", None, 100, 200, now)
            db.upsert_token(con, "sol", "MintB", "MICRO", "two", None, 300, None, now + 5)
            db.upsert_token(con, "sol", "MintA", "MICRO", "one", "logo", None, None, now + 50)
            con.commit()
            rows = {
                r["address"]: r
                for r in con.execute("SELECT * FROM tokens ORDER BY address")
            }
            self.assertEqual(rows["MintA"]["token_created_at"], 100)
            self.assertEqual(rows["MintA"]["pair_created_at"], 200)
            self.assertEqual(rows["MintA"]["creation_ts"], 100)
            self.assertEqual(rows["MintA"]["first_seen_at"], now)
            self.assertEqual(rows["MintB"]["token_created_at"], 300)
            self.assertIsNone(rows["MintB"]["pair_created_at"])
            self.assertEqual(rows["MintB"]["first_seen_at"], now + 5)
            self.assertNotEqual(rows["MintA"]["address"], rows["MintB"]["address"])
            con.close()

    def test_backfill_does_not_copy_creation_into_pair_or_first_seen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + "/t.sqlite"
            con = db.connect(path)
            con.execute(
                "INSERT INTO tokens(chain,address,symbol,creation_ts) VALUES('sol','MintC','OTC',1787923990)"
            )
            con.commit()
            con.close()
            con = db.connect(path)
            row = con.execute("SELECT * FROM tokens WHERE address='MintC'").fetchone()
            self.assertEqual(row["token_created_at"], 1787923990)
            self.assertIsNone(row["pair_created_at"])
            self.assertIsNone(row["first_seen_at"])
            con.close()


if __name__ == "__main__":
    unittest.main()
