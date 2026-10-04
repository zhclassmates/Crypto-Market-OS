#!/usr/bin/env python3
"""Five-chain configuration and BSC collector/storage regression tests."""
import tempfile
import unittest

import market_collect as collect
import market_db as db
import market_health as health
import market_lanes as lanes
import market_research as research
from market_chains import (
    DEFAULT_MARKET_CHAINS,
    DEXSCREENER_CHAINS,
    MARKET_CHAINS,
    SIGNAL_CHAINS,
)


EXPECTED_CHAINS = ("sol", "robinhood", "base", "eth", "bsc")


class MarketChainConfigTest(unittest.TestCase):
    def test_five_supported_chains_share_one_configuration(self):
        self.assertEqual(DEFAULT_MARKET_CHAINS, EXPECTED_CHAINS)
        self.assertEqual(MARKET_CHAINS, EXPECTED_CHAINS)
        self.assertEqual(collect.CHAINS, EXPECTED_CHAINS)
        self.assertEqual(DEXSCREENER_CHAINS["bsc"], "bsc")
        self.assertIn("bsc", SIGNAL_CHAINS)

    def test_health_catalog_covers_all_five_chains(self):
        catalog = health.catalog()
        gmgn_chains = tuple(row[1] for row in catalog if row[0] == "gmgn")
        self.assertEqual(gmgn_chains, EXPECTED_CHAINS)
        for chain in EXPECTED_CHAINS:
            sources = {source for source, item_chain, _period in catalog if item_chain == chain}
            self.assertTrue({"gmgn", "gmgn_hot", "gmgn_new_pair", "gmgn_kline", "gmgn_security", "dexscreener"}.issubset(sources))

    def test_collector_builds_a_bsc_trending_request(self):
        calls = []
        original = collect.gmgn
        collect.gmgn = lambda args, timeout=60: calls.append((args, timeout)) or {"data": {"rank": []}}
        try:
            self.assertEqual(collect.fetch_trending("bsc", limit=7, attempts=1), [])
        finally:
            collect.gmgn = original
        self.assertEqual(
            calls[0][0],
            ["market", "trending", "--chain", "bsc", "--interval", "24h", "--limit", "7"],
        )


class BscStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = db.connect(self.tmp.name + "/market.sqlite")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    @staticmethod
    def _rank_row(address, symbol):
        return {
            "chain": "bsc",
            "address": address,
            "symbol": symbol,
            "name": symbol,
            "price": 0.125,
            "price_change_percent": 3.5,
            "price_change_percent1h": 1.25,
            "volume": 250000,
            "liquidity": 100000,
            "market_cap": 500000,
            "creation_timestamp": 1_700_000_000,
            "holder_count": 321,
            "swaps": 30,
            "buys": 18,
            "sells": 12,
        }

    def test_all_existing_chains_and_bsc_use_the_same_storage_path(self):
        for index, chain in enumerate(EXPECTED_CHAINS):
            row = self._rank_row(f"0x{index + 1:040x}", chain.upper())
            row["chain"] = chain
            lanes.write_gmgn_rows(self.con, chain, [row], 1_700_200_000 + index, source="trending")
        self.con.commit()
        stored = tuple(
            row[0]
            for row in self.con.execute(
                "SELECT chain FROM token_snapshot GROUP BY chain ORDER BY MIN(rowid)"
            )
        )
        self.assertEqual(stored, EXPECTED_CHAINS)

    def test_bsc_market_fields_and_daily_kline_land_without_schema_changes(self):
        address = "0x4902c5ebc598265ed2212b559b042de8a5eeec3f"
        day = 1_700_006_400 - (1_700_006_400 % research.DAY_SEC)
        now = day + 3 * research.DAY_SEC + 60
        row = self._rank_row(address, "BNCB")
        row["creation_timestamp"] = day
        lanes.write_gmgn_rows(self.con, "bsc", [row], now, source="trending")
        written = research.commit_kline_fetch(self.con, "bsc", address, [
            {"time": day, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "amount": 15},
            {"time": day + research.DAY_SEC, "open": 1.5, "high": 2, "low": 1, "close": 1.8, "volume": 12, "amount": 20},
        ], now, True)
        self.con.commit()

        snapshot = self.con.execute(
            "SELECT price, volume_24h, liquidity, market_cap, holders, buys_24h, sells_24h, swaps "
            "FROM token_snapshot WHERE chain='bsc' AND address=?",
            (address,),
        ).fetchone()
        self.assertEqual(snapshot["price"], "0.125")
        self.assertEqual(snapshot["volume_24h"], "250000")
        self.assertEqual(snapshot["liquidity"], "100000")
        self.assertEqual(snapshot["market_cap"], "500000")
        self.assertEqual((snapshot["holders"], snapshot["buys_24h"], snapshot["sells_24h"], snapshot["swaps"]), (321, 18, 12, 30))
        self.assertEqual(written, 2)
        self.assertEqual(
            self.con.execute(
                "SELECT COUNT(*) FROM daily_kline WHERE chain='bsc' AND address=?",
                (address,),
            ).fetchone()[0],
            2,
        )


if __name__ == "__main__":
    unittest.main()
