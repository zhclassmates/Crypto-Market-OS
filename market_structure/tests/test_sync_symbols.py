"""sync_symbols 单元测试：用临时 sqlite 造数据，不连真实 Binance API。"""
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from ms.sync_symbols import (_read_rh_v2, _read_symbols, _resolve_contract,
                             _rewrite_config, run)


class TestSyncSymbols(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.config_path = self.base / "config.toml"
        self.config_path.write_text(
            """[general]
proxy = ""
[binance]
fapi = "https://fapi.binance.com"

[[symbols]]
symbol = "BTCUSDT"
spot = true

[[symbols]]
symbol = "ETHUSDT"
spot = false
""",
            encoding="utf-8",
        )
        # rh_v2 测试库
        self.rhv2 = self.base.parent / "rh_v2" / "rhv2.sqlite"
        self.rhv2.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.rhv2)
        con.execute("DROP TABLE IF EXISTS binance_events")
        con.execute(
            "CREATE TABLE binance_events (symbol TEXT, chain_id TEXT, address TEXT, alpha_ms INTEGER, perp_ms INTEGER, spot_ms INTEGER)"
        )
        now = int(time.time() * 1000)
        # 90 天内的上永续
        con.execute("INSERT INTO binance_events VALUES ('NEWCOIN','4663','0xaaa',?, ?, NULL)",
                    (now - 10 * 86400_000, now - 5 * 86400_000))
        # 1000 前缀
        con.execute("INSERT INTO binance_events VALUES ('PEPE','4663','0xbbb',?, ?, NULL)",
                    (now - 20 * 86400_000, now - 15 * 86400_000))
        # 超过 90 天的
        con.execute("INSERT INTO binance_events VALUES ('OLDCOIN','1','0xccc',?, ?, NULL)",
                    (now - 100 * 86400_000, now - 95 * 86400_000))
        # perp_ms 为负（撞名）
        con.execute("INSERT INTO binance_events VALUES ('BAD','1','0xddd',?, ?, NULL)",
                    (now - 5 * 86400_000, -1))
        # perp_ms 为空
        con.execute("INSERT INTO binance_events VALUES ('NOPERP','1','0xeee',?, NULL, NULL)",
                    (now - 5 * 86400_000,))
        con.commit()
        con.close()

        # mock Config
        from ms.config import Config, SymbolCfg
        self.cfg = Config(
            db_path=self.base / "data" / "ms.sqlite",
            bar_interval="15m",
            lookback_days=30,
            poll_delay_sec=20,
            request_gap_sec=0.25,
            tz="Asia/Shanghai",
            health_at="23:30",
            proxy=None,
            symbols=[SymbolCfg("BTCUSDT", True), SymbolCfg("ETHUSDT", False)],
            fapi="https://fapi.binance.com",
            spot_api="https://api.binance.com",
            force_order_ws="wss://fstream.binance.com/ws/!forceOrder@arr",
            bybit_enabled=True,
            bybit_api="https://api.bybit.com",
            bybit_ws="wss://stream.bybit.com/v5/public/linear",
            base_dir=self.base,
            config_path=self.config_path,
        )

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_resolve_contract_direct_and_1000(self):
        s = {"NEWCOINUSDT", "1000PEPEUSDT", "BTCUSDT"}
        self.assertEqual(_resolve_contract("NEWCOIN", s), "NEWCOINUSDT")
        self.assertEqual(_resolve_contract("PEPE", s), "1000PEPEUSDT")
        self.assertIsNone(_resolve_contract("NOSYM", s))

    async def test_read_rh_v2_filters(self):
        rows = _read_rh_v2(str(self.rhv2))
        syms = [r[0] for r in rows]
        self.assertIn("NEWCOIN", syms)
        self.assertIn("PEPE", syms)
        self.assertNotIn("OLDCOIN", syms)   # >90 天
        self.assertNotIn("BAD", syms)       # perp_ms=-1
        self.assertNotIn("NOPERP", syms)    # perp_ms 为空

    async def test_rewrite_config_preserves_manual(self):
        manual, _ = _read_symbols(self.config_path)
        auto = [{"symbol": "NEWCOINUSDT", "spot": True},
                {"symbol": "1000PEPEUSDT", "spot": True}]
        _rewrite_config(self.config_path, manual, auto)
        text = self.config_path.read_text(encoding="utf-8")
        # 保留 manual
        self.assertIn('symbol = "BTCUSDT"', text)
        self.assertIn('symbol = "ETHUSDT"', text)
        self.assertIn("spot = false", text)
        # 新增 auto 标记
        self.assertIn('symbol = "NEWCOINUSDT"', text)
        self.assertIn("auto = true", text)
        # 顺序：manual 在前，auto 在后
        self.assertLess(text.index("BTCUSDT"), text.index("NEWCOINUSDT"))

    async def test_run_detects_no_change(self):
        """当新旧 auto 集合一致时，返回无变化。"""
        manual, _ = _read_symbols(self.config_path)
        _rewrite_config(self.config_path, manual, [
            {"symbol": "NEWCOINUSDT", "spot": True},
            {"symbol": "1000PEPEUSDT", "spot": True},
        ])

        class FakeResp:
            async def json(self, content_type=None):
                return {"symbols": [
                    {"symbol": "NEWCOINUSDT", "contractType": "PERPETUAL"},
                    {"symbol": "1000PEPEUSDT", "contractType": "PERPETUAL"},
                ]}
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass

        class FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            def get(self, url, **kw): return FakeResp()

        import ms.sync_symbols as M
        orig = M._fetch_binance_perp_symbols
        async def _mock(proxy): return {"NEWCOINUSDT", "1000PEPEUSDT"}
        M._fetch_binance_perp_symbols = _mock
        try:
            changed, _ = await run(self.cfg)
            self.assertFalse(changed)
        finally:
            M._fetch_binance_perp_symbols = orig


if __name__ == "__main__":
    unittest.main()
