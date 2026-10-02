#!/usr/bin/env python3
"""Phase 1 研究账本。不打 GMGN，不打开运行库。"""
import tempfile
import unittest
from datetime import datetime, timezone

import market_collect as collect
import market_db as db
import market_health as H
import market_lanes as lanes
import market_research as R
import market_sched as sched


def _reset_sched():
    sched._state = {"until": 0, "start": 0, "step": 0, "basis": "", "loaded": True}


class TimestampTest(unittest.TestCase):
    def test_contract(self):
        self.assertIsNone(db.unix_ts(None))
        self.assertIsNone(db.unix_ts(""))
        self.assertIsNone(db.unix_ts("   "))
        self.assertIsNone(db.unix_ts("not-a-time"))
        self.assertIsNone(db.unix_ts(0))
        self.assertIsNone(db.unix_ts(-5))
        self.assertIsNone(db.unix_ts("-3"))
        self.assertIsNone(db.unix_ts(True))
        self.assertIsNone(db.unix_ts(False))
        self.assertEqual(db.unix_ts(1_700_000_000), 1_700_000_000)
        self.assertEqual(db.unix_ts(1_700_000_000.9), 1_700_000_000)
        self.assertEqual(db.unix_ts("1700000000"), 1_700_000_000)
        self.assertEqual(db.unix_ts(1_790_810_211_000), 1_790_810_211)
        self.assertEqual(db.unix_ts(10**12), 10**9)
        self.assertEqual(db.unix_ts(10**12 - 1), 10**12 - 1)
        # 1e15 落在微秒桶，不能被收成 1。
        self.assertEqual(db.unix_ts(10**15), 10**9)
        self.assertEqual(db.unix_ts(1_700_000_000_000_000), 1_700_000_000)
        self.assertEqual(db.unix_ts(10**17), 10**8)
        ns = db.unix_ts(float("1e17"))
        self.assertIsNotNone(ns)
        self.assertGreater(ns, 10**7)
        self.assertNotEqual(ns, 1)
        expected = int(datetime(2026, 10, 2, tzinfo=timezone.utc).timestamp())
        self.assertEqual(db.unix_ts("2026-10-02T00:00:00Z"), expected)
        self.assertIsNone(db.unix_ts("2026-13-40T00:00:00Z"))


class SchemaTest(unittest.TestCase):
    def test_four_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            con = db.connect(tmp + "/t.sqlite")
            names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ("token_registry", "discovery_event", "token_candle", "daily_metrics"):
                self.assertIn(table, names)
            liq = {r[1]: r[2] for r in con.execute("PRAGMA table_info(discovery_event)")}
            self.assertEqual(liq["liquidity"], "REAL")
            candle = {r[1] for r in con.execute("PRAGMA table_info(token_candle)")}
            self.assertIn("candle_open_ts", candle)
            con.close()


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = db.connect(self.tmp.name + "/t.sqlite")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_first_repeat_multisource_and_permanence(self):
        # 去重：同一 (chain, address, source, variant, 300 秒桶) 只插一行 event。
        # 桶内重复仍更新 last_seen_at。下一个桶再写一行。这不是最后状态快照。
        a = lanes.write_gmgn_rows(self.con, "sol", [{
            "address": "MintA", "symbol": "A", "name": "Alpha", "liquidity": 1000, "price": 1,
        }], 1_000, source="trending", source_variant="24h")
        self.con.commit()
        self.assertEqual(a[3]["new_addresses"], 1)
        self.assertEqual(a[3]["events_written"], 1)
        again = lanes.write_gmgn_rows(self.con, "sol", [{
            "address": "MintA", "symbol": "A", "liquidity": 1100, "price": 1,
        }], 1_050, source="trending", source_variant="24h")
        self.con.commit()
        self.assertEqual(again[3]["events_written"], 0)
        self.assertEqual(again[3]["rows_written"], 1)
        later = R.ingest_discovery(self.con, "sol", "MintA", "trending", 1_400, source_variant="24h", liquidity=1200)
        self.assertEqual(later["event_inserted"], 1)
        lanes.apply_hot_items(self.con, "sol", [{
            "address": "MintA", "symbol": "A", "liquidity": 1300, "price": 1,
        }], 1_500)
        lanes.apply_trench_payload(self.con, "sol", {
            "new_creation": [],
            "pump": [{"address": "MintA", "symbol": "A", "liquidity": 1400, "price": 1}],
            "completed": [],
        }, 1_600)
        lanes.write_gmgn_rows(self.con, "sol", [{
            "address": "MintB", "symbol": "B", "liquidity": 10, "price": 1,
        }], 1_000, source="trending", source_variant="24h")
        self.con.commit()
        # 第二轮榜上只剩 B，A 不能被删。
        lanes.write_gmgn_rows(self.con, "sol", [{
            "address": "MintB", "symbol": "B", "liquidity": 12, "price": 1,
        }], 2_000, source="trending", source_variant="24h")
        self.con.commit()
        row = self.con.execute("SELECT * FROM token_registry WHERE address='MintA'").fetchone()
        self.assertEqual(row["first_source"], "trending")
        self.assertEqual(row["first_seen_at"], 1_000)
        self.assertEqual(row["last_seen_at"], 1_600)
        seen = R.parse_sources(row["sources_seen"])
        self.assertEqual(seen, ["trending", "hot", "trenches"])
        still = self.con.execute("SELECT address FROM token_registry WHERE address='MintA'").fetchone()
        self.assertIsNotNone(still)
        events = self.con.execute(
            "SELECT COUNT(*) FROM discovery_event WHERE address='MintA'"
        ).fetchone()[0]
        self.assertGreaterEqual(events, 3)

    def test_four_sources_accept_unknown_addresses(self):
        lanes.write_gmgn_rows(self.con, "sol", [{
            "address": "TrendNew", "symbol": "T", "liquidity": 10, "price": 1,
        }], 5_000, source="trending", source_variant="24h")
        lanes.apply_hot_items(self.con, "base", [{
            "address": "HotNew", "symbol": "H", "liquidity": 20, "price": 2,
        }], 5_000)
        lanes.apply_trench_payload(self.con, "eth", {
            "data": {
                "new_creation": [{"address": "TrenchNew", "symbol": "N", "liquidity": 30, "usd_market_cap": 40}],
                "near_completion": [{"address": "TrenchNearKey", "symbol": "K", "liquidity": 34}],
                "pump": [{"address": "TrenchNear", "symbol": "P", "liquidity": 35}],
                "completed": [{"address": "TrenchDone", "symbol": "D", "liquidity": 36}],
            },
        }, 5_000)
        lanes.apply_signal_items(self.con, "sol", {
            "data": [{
                "token_address": "SignalNew",
                "symbol": "S",
                "signal_type": 3,
                "cur_data": {"liquidity": 40, "price": 0.2},
            }],
        }, 5_000)
        self.con.commit()
        found = {
            r["address"]: r["first_source"]
            for r in self.con.execute("SELECT address, first_source FROM token_registry")
        }
        self.assertEqual(found["TrendNew"], "trending")
        self.assertEqual(found["HotNew"], "hot")
        self.assertEqual(found["TrenchNew"], "trenches")
        self.assertEqual(found["TrenchNear"], "trenches")
        self.assertEqual(found["TrenchNearKey"], "trenches")
        self.assertEqual(found["TrenchDone"], "trenches")
        self.assertEqual(found["SignalNew"], "signal")
        variants = {
            r["address"]: r["source_variant"]
            for r in self.con.execute("SELECT address, source_variant FROM discovery_event")
        }
        self.assertEqual(variants["TrenchNear"], "near_completion")
        self.assertEqual(variants["TrenchNearKey"], "near_completion")
        self.assertEqual(variants["TrenchNew"], "new_creation")
        self.assertEqual(variants["SignalNew"], "3")
        for address in ("TrendNew", "HotNew", "TrenchNew", "SignalNew"):
            self.assertIsNotNone(
                self.con.execute("SELECT 1 FROM token_snapshot WHERE address=?", (address,)).fetchone()
            )


class LiquidityObservationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = db.connect(self.tmp.name + "/t.sqlite")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def _row(self, address="Mint"):
        return self.con.execute(
            "SELECT * FROM token_registry WHERE address=?", (address,)
        ).fetchone()

    def test_below_then_below(self):
        R.ingest_discovery(self.con, "sol", "Mint", "trending", 100, liquidity=30_000)
        R.ingest_discovery(self.con, "sol", "Mint", "trending", 200, liquidity=40_000)
        row = self._row()
        self.assertIsNone(row["first_liquidity_50k_at"])
        self.assertIsNone(row["liquidity_50k_observation_type"])
        self.assertEqual(row["seen_liquidity_below_50k"], 1)

    def test_observed_crossing(self):
        R.ingest_discovery(self.con, "sol", "Mint", "trending", 100, liquidity=30_000)
        R.ingest_discovery(self.con, "sol", "Mint", "hot", 200, liquidity=60_000)
        row = self._row()
        self.assertEqual(row["first_liquidity_50k_at"], 200)
        self.assertEqual(row["liquidity_50k_observation_type"], "observed_crossing")
        self.assertEqual(row["source_at_50k"], "hot")

    def test_first_observed_above_is_not_a_crossing(self):
        R.ingest_discovery(self.con, "sol", "Mint", "trending", 100, liquidity=120_000)
        row = self._row()
        self.assertEqual(row["liquidity_50k_observation_type"], "first_observed_above")
        self.assertNotEqual(row["liquidity_50k_observation_type"], "observed_crossing")
        self.assertEqual(row["first_liquidity_50k_at"], 100)

    def test_revisit_does_not_move_the_first_stamp(self):
        R.ingest_discovery(self.con, "sol", "Mint", "trending", 100, liquidity=60_000)
        R.ingest_discovery(self.con, "sol", "Mint", "trending", 200, liquidity=20_000)
        R.ingest_discovery(self.con, "sol", "Mint", "hot", 300, liquidity=80_000)
        row = self._row()
        self.assertEqual(row["first_liquidity_50k_at"], 100)
        self.assertEqual(row["liquidity_50k_observation_type"], "first_observed_above")
        self.assertEqual(row["source_at_50k"], "trending")

    def test_two_sources_lock_once(self):
        lanes.write_gmgn_rows(self.con, "sol", [{
            "address": "Mint", "liquidity": 60_000, "price": 1, "symbol": "M",
        }], 100, source="trending", source_variant="24h")
        lanes.apply_hot_items(self.con, "sol", [{
            "address": "Mint", "liquidity": 60_000, "price": 1, "symbol": "M",
        }], 101)
        row = self._row()
        self.assertEqual(row["first_liquidity_50k_at"], 100)
        self.assertEqual(row["source_at_50k"], "trending")
        self.assertEqual(row["liquidity_50k_observation_type"], "first_observed_above")

    def test_legacy_snapshot_does_not_invent_a_crossing(self):
        self.con.execute("DELETE FROM token_registry")
        self.con.execute("DELETE FROM market_meta WHERE k IN ('phase1_migrated', 'phase1_legacy_note')")
        self.con.execute(
            "INSERT INTO tokens(chain,address,symbol,name,first_seen_at) VALUES('sol','Old','OLD','Old',100)"
        )
        self.con.execute(
            "INSERT INTO token_snapshot(chain,address,ts,price,liquidity) VALUES('sol','Old',200,'1','100000')"
        )
        self.con.execute(
            "INSERT INTO daily_kline(chain,address,ts,open,high,low,close,volume) "
            "VALUES('sol','Old',86400,'1','1','1','1','1')"
        )
        self.con.commit()
        R.migrate(self.con)
        row = self._row("Old")
        self.assertIsNone(row["first_liquidity_50k_at"])
        self.assertIsNone(row["liquidity_50k_observation_type"])
        self.assertIsNone(row["source_at_50k"])
        self.assertIsNone(row["kline_backfilled_at"])
        self.assertIsNone(row["qualified_at"])
        self.assertEqual(row["first_source"], "legacy_snapshot")
        note = db.meta_get(self.con, "phase1_legacy_note")
        self.assertIn("cannot be reconstructed reliably", note)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM token_candle").fetchone()[0], 1)


class KlineAndMetricsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = db.connect(self.tmp.name + "/t.sqlite")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_failure_does_not_stamp_backfill(self):
        R.ingest_discovery(self.con, "sol", "Mint", "trending", 1_000, liquidity=60_000)
        self.assertEqual(R.commit_kline_fetch(self.con, "sol", "Mint", [], 2_000, True), 0)
        self.assertEqual(R.commit_kline_fetch(self.con, "sol", "Mint", [{"time": "bad"}], 2_100, False), 0)
        self.assertEqual(R.commit_kline_fetch(self.con, "sol", "Mint", [{"time": 1_700_000_000}], 2_200, True), 0)
        row = self.con.execute("SELECT * FROM token_registry WHERE address='Mint'").fetchone()
        self.assertIsNone(row["kline_backfilled_at"])
        self.assertIsNotNone(row["kline_retry_after"])

    def test_success_stamps_only_after_a_candle_write(self):
        now = 1_700_086_400 + 3_600
        day = now - now % 86400
        R.ingest_discovery(self.con, "sol", "Mint", "trending", now - 100, liquidity=30_000)
        R.ingest_discovery(self.con, "sol", "Mint", "trending", now - 50, liquidity=60_000)
        R.upsert_snapshot_numbers(self.con, "sol", "Mint", now, 1, 1, 100_000, 1, 1)
        written = R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": day - 2 * 86400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": day - 86400, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1},
            {"time": day, "open": 2, "high": 3, "low": 2, "close": 3, "volume": 1},
        ], now, True)
        self.assertGreaterEqual(written, 2)
        row = self.con.execute("SELECT * FROM token_registry WHERE address='Mint'").fetchone()
        self.assertEqual(row["kline_backfilled_at"], now)
        self.assertIsNone(row["kline_retry_after"])
        self.assertEqual(row["liquidity_50k_observation_type"], "observed_crossing")
        closed = R.closed_candle_rows(self.con, "sol", "Mint", now)
        self.assertEqual(R.streak_from_closed(closed), 1)
        # 缺第三根相邻日 K 时 2d 可以有值；这里两根已收盘相邻，2d 窗口不够。
        r2, _r3, r5 = R.returns_from_closed(closed)
        self.assertIsNone(r2)
        self.assertIsNone(r5)
        self.assertNotEqual(r2, 0)
        metrics = self.con.execute("SELECT * FROM daily_metrics WHERE address='Mint'").fetchone()
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["eligible"], 1)
        self.assertEqual(metrics["qualified_at"], now)
        self.assertIsNone(metrics["return_2d"])
        # 再次达标不改第一次 qualified_at。跌破流动性也不清掉。
        R.refresh_metrics(self.con, "sol", "Mint", now + 30)
        R.upsert_snapshot_numbers(self.con, "sol", "Mint", now + 80, 1, 1, 1_000, 1, 1)
        R.refresh_metrics(self.con, "sol", "Mint", now + 80)
        locked = self.con.execute("SELECT qualified_at FROM token_registry WHERE address='Mint'").fetchone()
        self.assertEqual(locked["qualified_at"], now)
        later = self.con.execute(
            "SELECT qualified_at, eligible FROM daily_metrics WHERE address='Mint'"
        ).fetchone()
        self.assertEqual(later["qualified_at"], now)
        self.assertEqual(later["eligible"], 0)

    def test_consecutive_closed_candles_have_returns(self):
        closed = [(i * 86400, float(i + 1), float(i + 1)) for i in range(6)]
        r2, r3, r5 = R.returns_from_closed(closed)
        self.assertAlmostEqual(r2, 6 / 4 - 1)
        self.assertAlmostEqual(r3, 6 / 3 - 1)
        self.assertAlmostEqual(r5, 6 / 1 - 1)

    def test_gap_return_is_null_not_zero(self):
        closed = [(0, 10.0, 10.0), (86400, 12.0, 12.0), (86400 * 3, 20.0, 20.0)]
        self.assertEqual(R.streak_from_closed(closed), 0)
        self.assertIsNone(R.returns_from_closed(closed)[0])
        flat = [(0, 10.0, 10.0), (86400, 10.0, 11.0)]
        self.assertEqual(R.streak_from_closed(flat), 0)

    def test_freshness_cases(self):
        self.assertTrue(R.formal_eligible(100_000, 30))
        self.assertFalse(R.formal_eligible(100_000, 1000))
        self.assertFalse(R.formal_eligible(30_000, 20))
        self.assertFalse(R.formal_eligible(100_000, None))


class SchedulerTest(unittest.TestCase):
    def tearDown(self):
        _reset_sched()

    def test_kline_is_not_starved_by_trending(self):
        now = 10_000
        periods = {}
        nxt = {}
        priority = ["gmgn_kline", "gmgn", "gmgn_hot", "gmgn_new_pair", "gmgn_signal", "gmgn_security"]
        for chain in ("sol", "base", "eth", "robinhood"):
            periods[("gmgn", chain)] = 300
            nxt[("gmgn", chain)] = now - 10_000
            periods[("gmgn_kline", chain)] = 60
            nxt[("gmgn_kline", chain)] = now
        picked = sched.pick_gmgn_job(nxt, now, periods, priority)
        self.assertEqual(picked[0], "gmgn_kline")
        # Trending 一直到点时，日 K 仍按自己的周期被选中。
        clock = 0
        due = {("gmgn", "sol"): 0, ("gmgn_kline", "sol"): 0}
        per = {("gmgn", "sol"): 300, ("gmgn_kline", "sol"): 60}
        kline_at = []
        for _ in range(400):
            choice = sched.pick_gmgn_job(due, clock, per, priority)
            if choice is None:
                clock += 1
                continue
            source, chain, period = choice
            if source == "gmgn_kline":
                kline_at.append(clock)
            due[(source, chain)] = clock + period
            clock += 2
        self.assertGreaterEqual(len(kline_at), 2)
        gaps = [b - a for a, b in zip(kline_at, kline_at[1:])]
        self.assertTrue(gaps)
        self.assertLessEqual(max(gaps), 62)

    def test_one_rate_limit_blocks_every_gmgn_call(self):
        _reset_sched()
        now = 1_700_000_000
        decision = sched.parse_rate_limit(
            "HTTP 429 code=429 error=RATE_LIMIT_BANNED reset_at=1700000300",
            now,
        )
        self.assertEqual(decision["basis"], "reset_at")
        self.assertEqual(decision["until"], 1_700_000_300)
        with tempfile.TemporaryDirectory() as tmp:
            con = db.connect(tmp + "/t.sqlite")
            wall = int(__import__("time").time())
            sched.arm_cooldown(wall, {"basis": "fallback", "until": None}, con=con)
            self.assertEqual(sched.cooldown_until(), wall + 5)
            self.assertTrue(sched.in_cooldown(wall + 1))
            sched.observe_error(
                "HTTP 429 code=429 error=RATE_LIMIT_EXCEEDED Retry-After: 90",
                now=wall + 1,
                con=con,
            )
            self.assertGreaterEqual(sched.cooldown_until(), wall + 90)
            calls = []

            def boom(*_a, **_k):
                calls.append("hit")
                raise AssertionError("GMGN request was not blocked")

            import subprocess
            old = subprocess.run
            subprocess.run = boom
            try:
                for args in (
                    ["market", "trending", "--chain", "sol"],
                    ["market", "hot-searches", "--chain", "base"],
                    ["market", "trenches", "--chain", "eth"],
                    ["market", "signal", "--chain", "robinhood"],
                    ["market", "kline", "--chain", "sol"],
                ):
                    with self.assertRaises(sched.RateLimited):
                        collect.gmgn(args)
            finally:
                subprocess.run = old
            self.assertEqual(calls, [])
            con.close()


class HealthWriteTest(unittest.TestCase):
    def test_request_success_is_not_discovery_success(self):
        self.assertEqual(sched.discovery_run_state(8, 8, 0, 0), "zero_write")
        self.assertEqual(sched.discovery_run_state(8, 8, 0, 1), "healthy")
        self.assertEqual(sched.discovery_run_state(0, 0, 0, 0, unsupported=True), "unsupported")
        self.assertEqual(sched.discovery_run_state(0, 0, 0, 0, cooldown=True), "cooldown")
        with tempfile.TemporaryDirectory() as tmp:
            con = db.connect(tmp + "/t.sqlite")
            H.ensure_catalog(con)
            H.record_result(
                con, "gmgn_new_pair", "sol", False, 10, 11,
                rows_received=8, rows_parsed=8, rows_written=0, events_written=0,
                run_state="zero_write", request_ok=1, wrote_db=False,
                error="discovery write failed / zero-write",
            )
            row = con.execute(
                "SELECT round_ok, run_state, request_ok, rows_written FROM source_health WHERE source='gmgn_new_pair' AND chain='sol'"
            ).fetchone()
            self.assertEqual(row["round_ok"], 0)
            self.assertEqual(row["run_state"], "zero_write")
            self.assertEqual(row["request_ok"], 1)
            self.assertEqual(row["rows_written"], 0)
            self.assertEqual(
                H.classify_status(11, 11, None, 0, 0, 300, 0, row["run_state"]),
                "zero_write",
            )
            con.close()


if __name__ == "__main__":
    unittest.main()
