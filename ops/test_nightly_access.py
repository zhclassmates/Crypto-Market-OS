"""ops/nightly.py access_section tests: temp access.sqlite built with radar_core, no network."""
import logging
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "access_radar"))
import nightly  # noqa: E402
import radar_core as rc  # noqa: E402

DAY = "2026-10-03"
T0 = int(datetime(2026, 10, 3, 2, 0, tzinfo=timezone.utc).timestamp() * 1000)   # 10:00 UTC+8
H = 3600 * 1000


class AccessSection(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "access.sqlite"
        c = rc.init_db(str(self.db))
        rc.register_platform(c, "upbit", "Upbit", "CEX", "KR", at=T0)
        rc.register_source(c, "upbit_market", kind="SNAPSHOT", tier="OFFICIAL_STRUCTURED",
                           origin_platform_id="upbit", at=T0)
        rc.register_source(c, "upbit_notice", kind="ANNOUNCEMENT", tier="OFFICIAL_ANNOUNCEMENT",
                           origin_platform_id="upbit", at=T0)
        mk = lambda syms: [{"symbol": s, "quote": "KRW", "access_kind": "SPOT"} for s in syms]  # noqa: E731
        base = ["BTC", "ETH", "XRP", "SOL", "ADA"]
        rc.ingest_snapshot(c, "upbit_market", "KRW", mk(base), fetched_at=T0 - 2 * H)          # baseline (no events)
        rc.ingest_snapshot(c, "upbit_market", "KRW", mk(base + ["REZ"]), fetched_at=T0)       # REZ listed
        rc.report_fetch_error(c, "upbit_market", "BTC", "HTTP 429", at=T0 + H)
        rc.mark_disconnected(c, "upbit_notice", at=T0 + 2 * H, reason="ws closed")
        rc.ingest_snapshot(c, "upbit_market", "KRW", mk(base + ["REZ"]), fetched_at=T0 + 26 * H)  # next day: nothing
        c.close()

    def tearDown(self):
        self.tmp.cleanup()
        logging.disable(logging.NOTSET)

    def test_missing_db(self):
        self.assertEqual(nightly.access_section(DAY, Path(self.tmp.name) / "nope.sqlite"), "[access_radar] 库文件不存在")

    def test_uninitialised_db(self):
        p = Path(self.tmp.name) / "empty.sqlite"
        sqlite3.connect(p).close()
        self.assertIn("库未初始化", nightly.access_section(DAY, p))

    def test_day_report(self):
        out = nightly.access_section(DAY, self.db)
        self.assertIn("[access_radar] 2026-10-03", out)
        self.assertIn("新事件: SPOT_LISTED=1", out)
        self.assertIn("sym:REZ/KRW", out)
        self.assertIn("10-03 10:00", out)                      # anchor shown in UTC+8
        self.assertIn("upbit_notice 10-03 12:00→仍断开", out)
        self.assertIn("UNRESOLVED=6", out)
        self.assertIn("upbit_market/BTC=DOWN (HTTP 429)", out)
        self.assertIn("（无 source_run 表）", out)
        self.assertIn("（无 maintenance_run 表）", out)

    def test_runner_tables(self):
        c = sqlite3.connect(self.db)
        c.executescript("""
            CREATE TABLE source_run (source_id TEXT PRIMARY KEY, consecutive_errors INTEGER NOT NULL DEFAULT 0,
                                     last_error TEXT NOT NULL DEFAULT '');
            INSERT INTO source_run VALUES ('bithumb_notice', 4, 'HTTP 429'), ('upbit_market', 0, '');
            CREATE TABLE maintenance_run (job_id TEXT PRIMARY KEY, job_state TEXT, last_success INTEGER,
                                          consecutive_errors INTEGER NOT NULL DEFAULT 0);
        """)
        c.execute("INSERT INTO maintenance_run VALUES ('resolve', 'error', ?, 2)", (T0,))
        c.commit()
        c.close()
        out = nightly.access_section(DAY, self.db)
        self.assertIn("采集进程: bithumb_notice 连续失败 4", out)
        self.assertNotIn("upbit_market 连续失败", out)
        self.assertIn("维护任务: resolve=error 上次成功 10-03 10:00 连续失败 2", out)

    def test_other_day_has_no_events(self):
        out = nightly.access_section("2026-10-05", self.db)
        self.assertIn("新事件: 无", out)
        self.assertNotIn("事件明细", out)

    def test_quote_less_delisting_counts_once(self):
        """同一公告同一币在 KRW、BTC 两个市场各出一条事件：按 group_key 只算一条，明细合并成一行。"""
        c = rc.init_db(str(self.db))
        rc.ingest_snapshot(c, "upbit_market", "BTC", [{"symbol": "ADA", "quote": "BTC", "access_kind": "SPOT"}],
                           fetched_at=T0 - H)                                    # BTC 报价基线（无事件）
        r = rc.ingest_announcement(c, "upbit_notice", {
            "action": "DELISTING", "platform_id": "upbit", "symbol": "ADA", "quote": "",
            "source_event_id": "n1", "title": "ADA 거래지원 종료", "observed_at": T0 + 3 * H})
        c.close()
        self.assertEqual((len(r["events"]), r["rejected"]), (2, 0))
        out = nightly.access_section(DAY, self.db)
        self.assertIn("SPOT_DELISTED=1（2 个市场）", out)
        self.assertIn("sym:ADA/BTC+KRW", out)
        self.assertEqual(out.count("sym:ADA"), 1)

    def test_read_only(self):
        before = self.db.stat().st_mtime_ns
        nightly.access_section(DAY, self.db)
        self.assertEqual(self.db.stat().st_mtime_ns, before)

    def test_broken_db_isolated_by_safe(self):
        """库损坏时 access_section 会抛异常；main 用 _safe 包住，只影响 access_radar 这一段。"""
        p = Path(self.tmp.name) / "corrupt.sqlite"
        p.write_bytes(b"not a sqlite database" * 100)
        out = nightly._safe("access_radar", nightly.access_section, DAY, p)
        self.assertTrue(out.startswith("[access_radar] 生成失败: DatabaseError"), out)


if __name__ == "__main__":
    unittest.main()
