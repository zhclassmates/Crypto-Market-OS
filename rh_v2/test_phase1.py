#!/usr/bin/env python3
"""Phase 1 研究账本。不打 GMGN，不打开运行库。"""
import tempfile
import time
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


class Phase4SnapshotMergeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = db.connect(self.tmp.name + "/t.sqlite")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def _trench(self, address="Mint", **overrides):
        row = {
            "address": address, "symbol": "M", "price": 1.25,
            "volume_24h": 123.5, "swaps_24h": 7,
            "liquidity": 500, "market_cap": 900, "holder_count": 11,
        }
        row.update(overrides)
        return {"new_creation": [row], "near_completion": [], "completed": []}

    def _signal(self, address="Mint", **cur):
        current = {"liquidity": 600, "holder_count": 12, "top_10_holder_rate": 0.2}
        current.update(cur)
        return [{
            "token_address": address, "signal_type": 7, "market_cap": 950,
            "data": {"symbol": "M", "price": 999, "volume_24h": 0, "swaps_24h": 0},
            "cur_data": current,
        }]

    def test_trenches_then_signal_preserves_unavailable_fields(self):
        lanes.apply_trench_payload(self.con, "sol", self._trench(), 100)
        lanes.apply_signal_items(self.con, "sol", self._signal(), 101)
        row = self.con.execute("SELECT * FROM token_snapshot WHERE address='Mint'").fetchone()
        self.assertEqual(row["price"], "1.25")
        self.assertEqual(row["volume_24h"], "123.5")
        self.assertEqual(row["swaps"], 7)
        self.assertEqual(row["holders"], 12)
        self.assertEqual(row["volume_24h_source"], "trenches")
        self.assertEqual(row["holders_source"], "signal")

    def test_signal_then_trenches_preserves_signal_only_field(self):
        lanes.apply_signal_items(self.con, "sol", self._signal(), 100)
        lanes.apply_trench_payload(self.con, "sol", self._trench(), 101)
        row = self.con.execute("SELECT * FROM token_snapshot WHERE address='Mint'").fetchone()
        self.assertEqual(row["top10_holder_rate"], "0.2")
        self.assertEqual(row["price"], "1.25")
        self.assertEqual(row["volume_24h"], "123.5")
        self.assertEqual(row["swaps"], 7)

    def test_zero_is_saved_and_missing_is_not_zero(self):
        lanes.apply_trench_payload(
            self.con, "base", self._trench(volume_24h=0, swaps_24h=0, holder_count=0), 100,
        )
        row = self.con.execute("SELECT volume_24h, swaps, holders FROM token_snapshot").fetchone()
        self.assertEqual(row["volume_24h"], "0")
        self.assertEqual(row["swaps"], 0)
        self.assertEqual(row["holders"], 0)
        lanes.write_gmgn_rows(self.con, "base", [{"address": "Missing", "symbol": "X"}], 101, source="trenches")
        missing = self.con.execute(
            "SELECT volume_24h, swaps, holders FROM token_snapshot WHERE address='Missing'"
        ).fetchone()
        self.assertIsNone(missing["volume_24h"])
        self.assertIsNone(missing["swaps"])
        self.assertIsNone(missing["holders"])

    def test_explicit_null_clears_owned_field_but_absent_preserves(self):
        lanes.write_gmgn_rows(self.con, "sol", [{"address": "Mint", "price": 1}], 100, source="trending")
        lanes.write_gmgn_rows(self.con, "sol", [{"address": "Mint"}], 101, source="trending")
        self.assertEqual(self.con.execute("SELECT price FROM token_snapshot").fetchone()[0], "1")
        lanes.write_gmgn_rows(self.con, "sol", [{"address": "Mint", "price": None}], 102, source="trending")
        self.assertIsNone(self.con.execute("SELECT price FROM token_snapshot").fetchone()[0])

    def test_trench_schema_variants_use_only_direct_24h_fields(self):
        for i, chain in enumerate(("sol", "robinhood", "base", "eth")):
            for j, bucket in enumerate(("new_creation", "near_completion", "completed")):
                address = f"{chain}-{bucket}"
                payload = {"new_creation": [], "near_completion": [], "completed": []}
                payload[bucket] = [{
                    "address": address, "volume_24h": i * 10 + j,
                    "swaps_24h": i + j, "liquidity": 999999,
                    "fresh_wallet_rate": 0.99, "new_wallet_volume": 123,
                }]
                lanes.apply_trench_payload(self.con, chain, payload, 200 + i * 10 + j)
                row = self.con.execute(
                    "SELECT volume_24h, swaps FROM token_snapshot WHERE chain=? AND address=?",
                    (chain, address),
                ).fetchone()
                self.assertEqual(row["volume_24h"], str(i * 10 + j))
                self.assertEqual(row["swaps"], i + j)

    def test_security_nullable_fields_and_raw_semantics(self):
        lanes.write_gmgn_rows(self.con, "sol", [{"address": "Mint"}], 100, source="trending")
        lanes.write_security_snapshot(self.con, "sol", "Mint", {
            "is_honeypot": False,
            "is_blacklist": None,
            "honeypot": 0,
            "top_10_holder_rate": "0.088",
        }, 110)
        row = self.con.execute("SELECT * FROM token_snapshot WHERE address='Mint'").fetchone()
        self.assertEqual(row["security_is_honeypot"], 0)
        self.assertIsNone(row["security_is_blacklist"])
        self.assertEqual(row["security_top10_holder_rate"], "0.088")
        raw = __import__("json").loads(row["security_json"])
        self.assertIsNone(raw["is_blacklist"])
        self.assertEqual(raw["honeypot"], 0)


class V1FieldIntegrationTest(unittest.TestCase):
    """V1 字段：0 是合法值，缺 key 不覆盖，endpoint 不提供的字段保持 NULL。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = db.connect(self.tmp.name + "/t.sqlite")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def _row(self, address="Mint"):
        return self.con.execute("SELECT * FROM token_snapshot WHERE address=?", (address,)).fetchone()

    def test_trending_activity_fields(self):
        lanes.write_gmgn_rows(self.con, "sol", [{
            "address": "Mint", "swaps": 10, "buys": 6, "sells": 4,
            "price_change_percent1h": -3.5, "is_wash_trading": False,
        }], 100, source="trending")
        row = self._row()
        self.assertEqual((row["swaps"], row["buys_24h"], row["sells_24h"]), (10, 6, 4))
        self.assertEqual(row["pc_1h"], "-3.5")
        self.assertEqual(row["is_wash_trading"], 0)
        self.assertEqual(row["buys_24h_source"], "trending")
        self.assertEqual(row["pc_1h_updated_at"], 100)

    def test_hot_zero_is_value_and_true_flag(self):
        lanes.apply_hot_items(self.con, "eth", [{
            "address": "Mint", "swaps": 0, "buys": 0, "sells": 0,
            "price_change_percent1h": 0, "is_wash_trading": True,
        }], 100)
        row = self._row()
        self.assertEqual((row["swaps"], row["buys_24h"], row["sells_24h"]), (0, 0, 0))
        self.assertEqual(row["pc_1h"], "0")
        self.assertEqual(row["is_wash_trading"], 1)

    def test_trench_suffix_fields_and_no_pc_1h(self):
        payload = {"new_creation": [{
            "address": "Mint", "swaps_24h": 5, "buys_24h": 3, "sells_24h": 2,
            "volume_24h": 7.5, "is_wash_trading": False,
        }], "near_completion": [], "completed": []}
        lanes.apply_trench_payload(self.con, "base", payload, 100)
        row = self._row()
        self.assertEqual((row["swaps"], row["buys_24h"], row["sells_24h"]), (5, 3, 2))
        self.assertEqual(row["volume_24h"], "7.5")
        self.assertIsNone(row["pc_1h"])  # Trenches 不提供 1h 涨跌
        self.assertIsNone(row["pc_1h_source"])

    def test_signal_does_not_touch_activity_and_keeps_trigger(self):
        lanes.write_gmgn_rows(self.con, "sol", [{
            "address": "Mint", "swaps": 9, "buys": 5, "sells": 4, "price_change_percent1h": 2,
        }], 100, source="trending")
        lanes.apply_signal_items(self.con, "sol", [{
            "token_address": "Mint", "signal_type": 7, "market_cap": 50,
            "trigger_at": 1790984873, "trigger_mc": 2575.5,
            "data": {"swaps_24h": 0, "buys_24h": 0, "sells_24h": 0, "volume_24h": 0},
            "cur_data": {"liquidity": 1, "holder_count": 2, "top_10_holder_rate": 0.1},
        }], 101)
        row = self._row()
        self.assertEqual((row["swaps"], row["buys_24h"], row["sells_24h"]), (9, 5, 4))
        self.assertEqual(row["pc_1h"], "2")
        meta = __import__("json").loads(self.con.execute(
            "SELECT metadata_json FROM discovery_event WHERE source='signal'"
        ).fetchone()[0])
        self.assertEqual(meta["trigger_at"], 1790984873)
        self.assertEqual(meta["trigger_mc"], 2575.5)
        self.assertEqual(meta["source_variant"], "7")

    def test_missing_keys_stay_unobserved(self):
        lanes.write_gmgn_rows(self.con, "sol", [{"address": "Mint"}], 100, source="trending")
        row = self._row()
        for col in ("swaps", "buys_24h", "sells_24h", "pc_1h", "is_wash_trading", "buys_24h_source"):
            self.assertIsNone(row[col], col)

    def test_non_boolean_wash_flag_is_unknown(self):
        lanes.write_gmgn_rows(self.con, "sol", [{"address": "Mint", "is_wash_trading": "yes"}], 100)
        self.assertIsNone(self._row()["is_wash_trading"])

    def test_event_metadata_keeps_activity_history(self):
        lanes.write_gmgn_rows(self.con, "sol", [{
            "address": "Mint", "rank": 3, "volume": 100, "swaps": 0, "buys": 0, "sells": 0,
            "price_change_percent1h": 1.5,
        }], 100, source="trending")
        e = self.con.execute("SELECT rank, metadata_json FROM discovery_event").fetchone()
        meta = __import__("json").loads(e["metadata_json"])
        self.assertEqual(e["rank"], 3)
        self.assertEqual((meta["volume"], meta["swaps"], meta["buys"], meta["sells"]), (100, 0, 0, 0))
        self.assertEqual(meta["price_change_percent1h"], 1.5)

    def test_security_v1_fields(self):
        lanes.write_gmgn_rows(self.con, "sol", [{"address": "Mint"}], 100)
        lanes.write_security_snapshot(self.con, "sol", "Mint", {
            "is_honeypot": None, "renounced_mint": True,
            "renounced_freeze_account": False, "sell_tax": "0",
        }, 110)
        row = self._row()
        self.assertIsNone(row["security_is_honeypot"])  # 明确 null = 未评估，不是安全
        self.assertEqual(row["security_renounced_mint"], 1)
        self.assertEqual(row["security_renounced_freeze_account"], 0)
        self.assertEqual(row["security_sell_tax"], "0")
        lanes.write_security_snapshot(self.con, "sol", "Mint", {"is_honeypot": False}, 120)
        row = self._row()
        self.assertEqual(row["security_is_honeypot"], 0)
        self.assertIsNone(row["security_sell_tax"])  # 本次响应没有该 key


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


class LiquidityTierTest(unittest.TestCase):
    """EARLY 只观察，不进日 K 队列；一旦观测到 >= 50k 自动成为 MAIN。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = db.connect(self.tmp.name + "/t.sqlite")
        self.day = 1_700_000_000 - (1_700_000_000 % 86400)
        self.now = self.day + 10 * 3600

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def _see(self, address, liquidity, at):
        lanes.write_gmgn_rows(self.con, "sol", [{
            "address": address, "liquidity": liquidity, "price": 1, "symbol": address,
        }], at, source="trending", source_variant="24h")

    def _tier(self, address):
        row = self.con.execute(
            f"""SELECT {R.TIER_SQL} FROM token_registry r
                LEFT JOIN token_snapshot s ON s.chain=r.chain AND s.address=r.address
                WHERE r.address=?""",
            (address,),
        ).fetchone()
        return row[0]

    def test_tier_bands(self):
        self._see("Ign", 5_000, self.now)
        self._see("Zero", 0, self.now)
        self._see("Early", 20_000, self.now)
        self._see("Near", 49_999, self.now)
        self._see("Main", 50_000, self.now)
        self.assertEqual(self._tier("Ign"), R.TIER_IGNORE)
        self.assertEqual(self._tier("Zero"), R.TIER_IGNORE)
        self.assertEqual(self._tier("Early"), R.TIER_EARLY)
        self.assertEqual(self._tier("Near"), R.TIER_EARLY)
        self.assertEqual(self._tier("Main"), R.TIER_MAIN)
        self.assertEqual(R.tier_counts(self.con), {"MAIN": 1, "EARLY": 2, "IGNORE": 2})
        self.assertEqual(R.liquidity_tier(None, 49_999), R.TIER_EARLY)
        self.assertEqual(R.liquidity_tier(None, None), R.TIER_IGNORE)

    def test_early_is_not_queued_for_kline(self):
        self._see("Early", 45_000, self.now)
        self.assertEqual(R.pick_kline_repair(self.con, "sol", self.now, 8), [])
        pending = self.con.execute(
            """SELECT COUNT(*) FROM token_registry
               WHERE first_liquidity_50k_at IS NOT NULL AND kline_backfilled_at IS NULL"""
        ).fetchone()[0]
        self.assertEqual(pending, 0)

    def test_early_upgrades_to_main_on_next_observation(self):
        self._see("Early", 45_000, self.now)
        self.assertEqual(self._tier("Early"), R.TIER_EARLY)
        self._see("Early", 52_000, self.now + 600)
        row = self.con.execute("SELECT * FROM token_registry WHERE address='Early'").fetchone()
        self.assertEqual(self._tier("Early"), R.TIER_MAIN)
        self.assertEqual(row["first_liquidity_50k_at"], self.now + 600)
        self.assertEqual(row["liquidity_50k_observation_type"], R.OBS_CROSSING)
        self.assertIn("Early", R.pick_kline_repair(self.con, "sol", self.now + 600, 8))
        # 同一实体：EARLY 期间的 event 保留，不生成第二个 token。
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM token_registry").fetchone()[0], 1)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM discovery_event WHERE address='Early'").fetchone()[0], 2,
        )

    def test_main_stays_main_after_liquidity_drops(self):
        self._see("Was", 80_000, self.now)
        self._see("Was", 30_000, self.now + 600)
        self.assertEqual(self._tier("Was"), R.TIER_MAIN)


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

    def test_daily_metrics_refreshes_at_utc_boundary_and_after_finalize(self):
        day = 1_700_006_400 - (1_700_006_400 % 86400)
        before_midnight = day + 4 * 86400 - 1
        midnight = day + 4 * 86400
        after_midnight = midnight + 60
        R.ingest_discovery(self.con, "sol", "UtcMint", "trending", day, liquidity=60_000)
        R.upsert_snapshot_numbers(self.con, "sol", "UtcMint", before_midnight, 1, 1, 60_000, 1, 1)
        R.write_daily_candles(self.con, "sol", "UtcMint", [
            {"time": day + i * 86400, "close": i + 1, "high": i + 1}
            for i in range(4)
        ], before_midnight)
        self.assertEqual(R.refresh_daily_metrics_for_utc_day(self.con, before_midnight), 1)
        at_2359 = self.con.execute(
            "SELECT * FROM daily_metrics WHERE address='UtcMint'"
        ).fetchone()
        self.assertTrue(R.daily_metrics_fresh(at_2359["calculated_at"], before_midnight))
        self.assertIsNotNone(at_2359["return_2d"])

        self.assertEqual(R.refresh_daily_metrics_for_utc_day(self.con, midnight), 1)
        at_0000 = self.con.execute(
            "SELECT * FROM daily_metrics WHERE address='UtcMint'"
        ).fetchone()
        self.assertTrue(R.daily_metrics_fresh(at_0000["calculated_at"], midnight))
        self.assertIsNone(at_0000["return_2d"])
        self.assertIsNone(at_0000["streak"])
        self.assertEqual(R.refresh_daily_metrics_for_utc_day(self.con, after_midnight), 0)

        R.write_daily_candles(self.con, "sol", "UtcMint", [
            {"time": day + 3 * 86400, "close": 4, "high": 4}
        ], after_midnight)
        R.refresh_metrics(self.con, "sol", "UtcMint", after_midnight)
        finalized = self.con.execute(
            "SELECT * FROM daily_metrics WHERE address='UtcMint'"
        ).fetchone()
        self.assertIsNotNone(finalized["return_2d"])
        self.assertEqual(finalized["streak"], 3)

        replay = R.refresh_metrics(self.con, "sol", "UtcMint", before_midnight)
        self.assertIsNotNone(replay["return_2d"])
        self.assertEqual(replay["streak"], 2)

    def test_gap_return_is_null_not_zero(self):
        closed = [(0, 10.0, 10.0), (86400, 12.0, 12.0), (86400 * 3, 20.0, 20.0)]
        # 最后一根前一天缺：没有证据，不是 0
        self.assertIsNone(R.streak_from_closed(closed))
        self.assertIsNone(R.returns_from_closed(closed)[0])
        flat = [(0, 10.0, 10.0), (86400, 10.0, 11.0)]
        self.assertEqual(R.streak_from_closed(flat), 0)

    def test_freshness_cases(self):
        self.assertTrue(R.formal_eligible(100_000, 30))
        self.assertFalse(R.formal_eligible(100_000, 1000))
        self.assertFalse(R.formal_eligible(30_000, 20))
        self.assertFalse(R.formal_eligible(100_000, None))

    def test_intraday_fetch_is_provisional_after_calendar_close(self):
        day = 1_700_000_000 - (1_700_000_000 % 86400)
        during = day + 12 * 3600
        after = day + 86400 + 120
        R.ingest_discovery(self.con, "sol", "Mint", "trending", during, liquidity=80_000)
        written = R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": day - 86400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": day, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1},
        ], during, True)
        self.assertGreaterEqual(written, 2)
        candle = self.con.execute(
            "SELECT fetched_at, finalized_at FROM token_candle WHERE address='Mint' AND candle_open_ts=?",
            (day,),
        ).fetchone()
        self.assertEqual(candle["fetched_at"], during)
        self.assertIsNone(candle["finalized_at"])
        self.assertEqual(R.bar_status(day, during, after), R.STATUS_PROVISIONAL)
        classified = R.classified_candle_rows(self.con, "sol", "Mint", after)
        self.assertEqual(classified[-1]["status"], R.STATUS_PROVISIONAL)
        self.assertFalse(R.official_tail_finalized(classified))
        self.assertEqual(len(R.closed_candle_rows(self.con, "sol", "Mint", after)), 1)
        dk = self.con.execute(
            "SELECT fetched_at, finalized_at FROM daily_kline WHERE address='Mint' AND ts=?",
            (day,),
        ).fetchone()
        self.assertEqual(dk["fetched_at"], during)
        self.assertIsNone(dk["finalized_at"])

    def test_post_close_refetch_finalizes_yesterday(self):
        day = 1_700_000_000 - (1_700_000_000 % 86400)
        during = day + 12 * 3600
        after = day + 86400 + 120
        R.ingest_discovery(self.con, "sol", "Mint", "trending", during, liquidity=80_000)
        R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": day - 86400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": day, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 1},
        ], during, True)
        R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": day - 86400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": day, "open": 1, "high": 2, "low": 1, "close": 1.4, "volume": 1},
        ], after, True)
        candle = self.con.execute(
            "SELECT close, fetched_at, finalized_at FROM token_candle WHERE address='Mint' AND candle_open_ts=?",
            (day,),
        ).fetchone()
        self.assertEqual(candle["fetched_at"], after)
        self.assertEqual(candle["finalized_at"], after)
        self.assertAlmostEqual(candle["close"], 1.4)
        self.assertEqual(R.bar_status(day, after, after, after), R.STATUS_FINALIZED)
        closed = R.closed_candle_rows(self.con, "sol", "Mint", after)
        self.assertEqual(len(closed), 2)
        self.assertEqual(R.streak_from_closed(closed), 1)
        self.assertFalse(R.needs_yesterday_finalize(self.con, "sol", "Mint", after))

    def test_created_at_drops_older_days(self):
        day = 1_700_086_400 - (1_700_086_400 % 86400)
        now = day + 86400 + 3600
        created = day + 100
        R.ingest_discovery(self.con, "sol", "Mint", "trending", now, liquidity=80_000)
        self.con.execute(
            "UPDATE tokens SET token_created_at=? WHERE chain='sol' AND address='Mint'",
            (created,),
        )
        R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": day - 86400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": day, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1},
        ], now, True)
        closed = R.closed_candle_rows(self.con, "sol", "Mint", now, created)
        self.assertEqual([row[0] for row in closed], [day])

    def test_repair_pick_prefers_unfinalized_yesterday(self):
        day = 1_700_000_000 - (1_700_000_000 % 86400)
        during = day + 10 * 3600
        after = day + 86400 + 180
        R.ingest_discovery(self.con, "sol", "Need", "trending", during, liquidity=80_000)
        R.ingest_discovery(self.con, "sol", "Done", "trending", during, liquidity=80_000)
        R.commit_kline_fetch(self.con, "sol", "Need", [
            {"time": day, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        ], during, True)
        R.commit_kline_fetch(self.con, "sol", "Done", [
            {"time": day, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        ], after, True)
        picked = R.pick_kline_repair(self.con, "sol", after, 8)
        self.assertIn("Need", picked)
        self.assertNotIn("Done", picked)


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


class FinalizedContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = db.connect(self.tmp.name + "/t.sqlite")
        self.day = 1_700_000_000 - (1_700_000_000 % 86400)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def _seed(self, address="Mint", liquidity=80_000, at=None):
        at = self.day if at is None else at
        R.ingest_discovery(self.con, "sol", address, "trending", at, liquidity=liquidity)
        R.upsert_snapshot_numbers(self.con, "sol", address, at, 1, 1, liquidity, 1, 1)

    def test_intraday_observed_at_not_finalized(self):
        during = self.day + 12 * 3600
        after = self.day + 86400 + 120
        self.assertFalse(R.observation_proves_final(self.day, during))
        self.assertEqual(R.bar_status(self.day, during, after), R.STATUS_PROVISIONAL)

    def test_intraday_stays_unfinalized_next_day_and_next_year(self):
        during = self.day + 12 * 3600
        self.assertEqual(R.bar_status(self.day, during, self.day + 2 * 86400), R.STATUS_PROVISIONAL)
        self.assertEqual(R.bar_status(self.day, during, self.day + 366 * 86400), R.STATUS_PROVISIONAL)

    def test_observed_at_after_bar_end_is_finalized(self):
        after = self.day + 86400 + 120
        self.assertTrue(R.observation_proves_final(self.day, after))
        self.assertEqual(R.bar_status(self.day, after, after, after), R.STATUS_FINALIZED)

    def test_observed_at_equal_bar_end_is_finalized(self):
        end = self.day + 86400
        self.assertTrue(R.observation_proves_final(self.day, end))
        self.assertEqual(R.bar_status(self.day, end, end + 1), R.STATUS_FINALIZED)

    def test_missing_observed_at_is_not_finalized(self):
        after = self.day + 86400 + 120
        self.assertFalse(R.observation_proves_final(self.day, None))
        self.assertEqual(R.bar_status(self.day, None, after), R.STATUS_PROVISIONAL)

    def test_copy_candles_ignores_migration_now(self):
        during = self.day + 10 * 3600
        self.con.execute(
            "INSERT INTO tokens(chain,address,symbol,kline_fetched_at) VALUES('sol','Old','OLD',?)",
            (during,),
        )
        self.con.execute(
            "INSERT INTO daily_kline(chain,address,ts,open,high,low,close,volume) "
            "VALUES('sol','Old',?,'1','1','1','2','1')",
            (self.day,),
        )
        R._copy_candles(self.con, self.day + 86400 + 3600)
        row = self.con.execute(
            "SELECT fetched_at, finalized_at, is_closed FROM token_candle WHERE address='Old'"
        ).fetchone()
        self.assertEqual(row["fetched_at"], during)
        self.assertIsNone(row["finalized_at"])
        self.assertEqual(row["is_closed"], 0)
        self.con.execute("DELETE FROM token_candle")
        R._copy_candles(self.con, self.day + 400 * 86400)
        later = self.con.execute(
            "SELECT fetched_at, finalized_at, is_closed FROM token_candle WHERE address='Old'"
        ).fetchone()
        self.assertEqual(tuple(later), tuple(row))

    def test_rebuild_syncs_newer_per_bar_observation_into_legacy_mirror(self):
        """CONDO regression: a non-NULL intraday mirror must not hide a later observation."""
        during = self.day + 12 * 3600
        after = self.day + 86400 + 120
        self._seed(at=after)
        R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": self.day - 86400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": self.day, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1},
        ], after, True)
        # Recreate the legacy split: token_candle has the real post-close fetch,
        # while daily_kline contains an older but non-NULL intraday timestamp.
        self.con.execute(
            "UPDATE daily_kline SET fetched_at=?, finalized_at=NULL WHERE address='Mint' AND ts=?",
            (during, self.day),
        )
        R._backfill_per_bar_fetched(self.con)
        R.rebuild_candle_finalized(self.con)
        mirror = self.con.execute(
            "SELECT fetched_at, finalized_at FROM daily_kline WHERE address='Mint' AND ts=?",
            (self.day,),
        ).fetchone()
        self.assertEqual(mirror["fetched_at"], after)
        self.assertEqual(mirror["finalized_at"], after)

    def test_refresh_as_of_is_latest_finalized_not_open_tail_or_run_day(self):
        day2 = self.day + 86400
        run_at = day2 + 12 * 3600
        self._seed(at=run_at)
        R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": self.day - 86400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": self.day, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1},
            {"time": day2, "open": 2, "high": 3, "low": 2, "close": 3, "volume": 1},
        ], run_at, True)
        metrics = self.con.execute(
            "SELECT as_of_date, streak FROM daily_metrics WHERE address='Mint'"
        ).fetchone()
        self.assertEqual(metrics["as_of_date"], time.strftime("%Y-%m-%d", time.gmtime(self.day)))
        self.assertEqual(metrics["streak"], 1)

    def test_refresh_clears_stale_positive_when_latest_bar_loses_finalized_proof(self):
        after = self.day + 86400 + 120
        during = self.day + 12 * 3600
        self._seed(at=after)
        R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": self.day - 86400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": self.day, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1},
        ], after, True)
        before = self.con.execute(
            "SELECT streak FROM daily_metrics WHERE address='Mint'"
        ).fetchone()
        self.assertEqual(before["streak"], 1)

        self.con.execute(
            "UPDATE token_candle SET fetched_at=?, finalized_at=NULL, is_closed=0 "
            "WHERE address='Mint' AND candle_open_ts=?",
            (during, self.day),
        )
        refreshed = R.refresh_metrics(self.con, "sol", "Mint", after)
        rows = self.con.execute(
            "SELECT as_of_date, streak, return_2d, return_3d, return_5d "
            "FROM daily_metrics WHERE address='Mint'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["streak"])
        self.assertIsNone(rows[0]["return_2d"])
        self.assertIsNone(rows[0]["return_3d"])
        self.assertIsNone(rows[0]["return_5d"])
        self.assertEqual(refreshed["streak_status"], R.STREAK_INSUFFICIENT)

    def test_nday_uses_finalized_only(self):
        now = self.day + 86400 + 3600
        self._seed(at=now)
        R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": self.day - 86400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": self.day, "open": 1, "high": 9, "low": 1, "close": 9, "volume": 1},
        ], self.day + 12 * 3600, True)
        metrics = R.refresh_metrics(self.con, "sol", "Mint", now)
        self.assertIsNone(metrics["streak"])
        self.assertIsNone(metrics["return_2d"])
        self.assertEqual(metrics["streak_status"], R.STREAK_INSUFFICIENT)

    def test_missing_previous_day_is_insufficient(self):
        closed = [(0, 10.0, 10.0), (86400 * 2, 20.0, 20.0)]
        self.assertIsNone(R.streak_from_closed(closed))
        self.assertEqual(R.streak_status(closed), R.STREAK_INSUFFICIENT)

    def test_valid_zero_when_last_day_did_not_rise(self):
        closed = [(0, 10.0, 10.0), (86400, 9.0, 11.0)]
        self.assertEqual(R.streak_from_closed(closed), 0)
        self.assertEqual(R.streak_status(closed), R.STREAK_ZERO)

    def test_pumpgu_intraday_must_not_mint_1975(self):
        true_close = 7.7301777e-05
        intraday = 0.00015835
        base = true_close / 10.130812
        closed = [(self.day + i * 86400, base, base) for i in range(5)]
        closed.append((self.day + 5 * 86400, true_close, true_close))
        r5 = R.returns_from_closed(closed)[2]
        self.assertIsNotNone(r5)
        self.assertLess(abs(r5 * 100 - 913.0812), 1)
        self.assertLess(r5 * 100, 1900)
        bogus = list(closed)
        bogus[-1] = (bogus[-1][0], intraday, intraday)
        bad = R.returns_from_closed(bogus)[2]
        self.assertGreater(bad * 100, 1900)

    def test_migrate_twice_is_idempotent(self):
        during = self.day + 10 * 3600
        after = self.day + 86400 + 180
        self._seed(at=during)
        R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": self.day - 86400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": self.day, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1},
        ], after, True)
        snap = lambda: [
            dict(r) for r in self.con.execute(
                "SELECT candle_open_ts, close, fetched_at, finalized_at, is_closed "
                "FROM token_candle WHERE address='Mint' ORDER BY candle_open_ts"
            )
        ]
        first = snap()
        R.migrate(self.con)
        R.migrate(self.con)
        self.assertEqual(snap(), first)

    def test_migration_now_does_not_change_historical_finalized(self):
        during = self.day + 8 * 3600
        self._seed(at=during)
        R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": self.day, "open": 1, "high": 1, "low": 1, "close": 1.2, "volume": 1},
        ], during, True)
        R.rebuild_candle_finalized(self.con)
        row = self.con.execute(
            "SELECT finalized_at, is_closed FROM token_candle WHERE candle_open_ts=?",
            (self.day,),
        ).fetchone()
        self.assertIsNone(row["finalized_at"])
        self.assertEqual(row["is_closed"], 0)
        self.assertEqual(R.bar_status(self.day, during, during + 400 * 86400), R.STATUS_PROVISIONAL)

    def test_qualified_at_rebuild_clears_intraday_qualification(self):
        during = self.day + 12 * 3600
        after = self.day + 86400 + 120
        self._seed(at=during)
        R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": self.day, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        ], during, True)
        self.con.execute(
            "UPDATE token_registry SET qualified_at=?, kline_backfilled_at=? WHERE address='Mint'",
            (during, during),
        )
        self.con.execute(
            "UPDATE token_candle SET is_closed=1, finalized_at=? WHERE address='Mint'",
            (after,),
        )
        R.rebuild_research_facts(self.con, after)
        row = self.con.execute("SELECT qualified_at FROM token_registry WHERE address='Mint'").fetchone()
        self.assertIsNone(row["qualified_at"])
        metrics = self.con.execute("SELECT streak, qualified_at FROM daily_metrics WHERE address='Mint'").fetchone()
        self.assertIsNone(metrics["qualified_at"])
        self.assertIsNone(metrics["streak"])

    def test_proven_historical_candle_is_not_demoted(self):
        after = self.day + 86400 + 180
        self._seed(at=after)
        R.commit_kline_fetch(self.con, "sol", "Mint", [
            {"time": self.day - 86400, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": self.day, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 1},
        ], after, True)
        before = self.con.execute(
            "SELECT finalized_at, fetched_at FROM token_candle WHERE candle_open_ts=?",
            (self.day,),
        ).fetchone()
        self.assertEqual(before["finalized_at"], after)
        R.rebuild_research_facts(self.con, after + 10)
        after_row = self.con.execute(
            "SELECT finalized_at, fetched_at, is_closed FROM token_candle WHERE candle_open_ts=?",
            (self.day,),
        ).fetchone()
        self.assertEqual(after_row["fetched_at"], after)
        self.assertEqual(after_row["finalized_at"], after)
        self.assertEqual(after_row["is_closed"], 1)


if __name__ == "__main__":
    unittest.main()
