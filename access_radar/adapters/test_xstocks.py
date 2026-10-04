"""xStocks adapter tests: fixed fixture pages, in-memory SQLite, no network."""
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from adapters import xstocks as xs  # noqa: E402
from adapters.chains import canonical_chain  # noqa: E402

H = 3600 * 1000
T0 = 1_790_000_000_000
SOL_ADDR = "XsbEhLAtcf6HdfpFZ5xEMdqW8nfAvcsP5bdudRLJzJp"   # base58: case must survive


def node(sym, chains=("Ethereum", "Solana"), halted=False):
    deps = []
    for c in chains:
        addr = SOL_ADDR + sym if c == "Solana" else "0xABCDEF" + sym.encode().hex().ljust(34, "0")
        deps.append({"network": c, "address": addr})
    return {"id": f"id-{sym}", "symbol": sym, "name": f"{sym} xStock", "isin": "CH0", "underlyingSymbol": sym[:-1],
            "isTradingHalted": halted, "trading": {"isTradingHalted": halted}, "deployments": deps}


def pager(nodes, per_page=7, dup_on_page=None, bad_page=None):
    pages = [nodes[i:i + per_page] for i in range(0, len(nodes), per_page)] or [[]]
    calls = []

    def fetch(url, headers=None):
        calls.append(url)
        p = int(url.rsplit("page=", 1)[1])
        if p == bad_page:
            return {"error": "rate limited"}
        body = list(pages[p])
        if p == dup_on_page:
            body[0] = pages[p - 1][-1]
        return {"nodes": body, "page": {"currentPage": p, "hasNextPage": p < len(pages) - 1}}
    fetch.calls = calls
    return fetch


BASE = [f"S{i:02d}x" for i in range(20)]


class XStocksTest(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        xs.register(self.conn, at=T0)

    def tearDown(self):
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def poll(self, nodes, at, **kw):
        return xs.run_once(self.conn, fetch=pager(nodes, **kw), fetched_at=at)

    def test_crawls_all_pages(self):
        f = pager([node(s) for s in BASE], per_page=7)
        self.assertEqual(len(xs.fetch_all(f)), 20)
        self.assertEqual(len(f.calls), 3)
        self.assertEqual(f.calls[0], f"{xs.BASE_URL}?pageSize={xs.PAGE_SIZE}&page=0")

    def test_baseline_emits_nothing(self):
        r = self.poll([node(s) for s in BASE], T0)
        self.assertEqual(r["catalog"]["outcome"], "BASELINE")
        self.assertEqual(r["deployments"]["outcome"], "BASELINE")
        self.assertEqual(r["catalog"]["valid"], 20)
        self.assertEqual(r["deployments"]["valid"], 40)
        self.assertEqual(self.q("SELECT * FROM access_event"), [])

    def test_new_asset_and_new_chain(self):
        self.poll([node(s) for s in BASE], T0)
        nodes = [node(s) for s in BASE] + [node("NEWx", chains=("Ethereum",))]
        nodes[0] = node(BASE[0], chains=("Ethereum", "Solana", "BinanceSmartChain"))
        r = self.poll(nodes, T0 + H)
        self.assertEqual(r["catalog"]["outcome"], "DIFF")
        ev = {(e["asset_key"], e["event_type"]) for e in self.q("SELECT * FROM access_event")}
        self.assertIn(("xstocks:NEWx", "CATALOG_ADDED"), ev)
        self.assertIn(("xstocks:NEWx", "CHAIN_DEPLOYED"), ev)
        self.assertIn((f"xstocks:{BASE[0]}", "CHAIN_DEPLOYED"), ev)
        bsc = self.q("SELECT * FROM access_state WHERE asset_key=? AND network='bsc'", (f"xstocks:{BASE[0]}",))
        self.assertEqual(bsc[0]["status"], "LIVE")
        self.assertEqual(len(ev), 3)

    def test_halt_is_suspend_not_remove(self):
        self.poll([node(s) for s in BASE], T0)
        nodes = [node(s, halted=(s == BASE[3])) for s in BASE]
        self.poll(nodes, T0 + H)
        st = self.q("SELECT status FROM access_state WHERE asset_key=? AND access_kind='CATALOG'", (f"xstocks:{BASE[3]}",))
        self.assertEqual(st[0]["status"], "SUSPENDED")
        types = {e["event_type"] for e in self.q("SELECT * FROM access_event WHERE asset_key=?", (f"xstocks:{BASE[3]}",))}
        self.assertIn("CATALOG_SUSPENDED", types)
        self.assertFalse(any(t.endswith("REMOVED") for t in types))

    def test_duplicate_across_pages_is_fetch_error(self):
        self.poll([node(s) for s in BASE], T0)
        r = self.poll([node(s) for s in BASE], T0 + H, dup_on_page=1)
        self.assertIn("pagination shifted", r["error"])
        self.assertEqual(self.q("SELECT * FROM access_event"), [])
        self.assertEqual(len(self.q("SELECT * FROM source_snapshot")), 2)   # only the two baseline snapshots
        self.assertIn("pagination", self.q("SELECT last_error FROM source_health WHERE scope='catalog'")[0]["last_error"])

    def test_bad_page_is_fetch_error_and_nothing_removed(self):
        self.poll([node(s) for s in BASE], T0)
        for i in range(4):
            r = self.poll([node(s) for s in BASE], T0 + (i + 1) * H, bad_page=2)
            self.assertIn("error", r)
        self.assertEqual(self.q("SELECT * FROM access_event"), [])
        self.assertEqual({r["status"] for r in self.q("SELECT status FROM access_state")}, {"LIVE"})

    def test_assets_and_deployments_registered_for_resolution(self):
        self.poll([node(s) for s in BASE], T0)
        a = self.q("SELECT * FROM asset WHERE asset_key=?", (f"xstocks:{BASE[1]}",))[0]
        self.assertEqual((a["asset_type"], a["issuer"], a["underlying"]), ("TOKENIZED_STOCK", "backed", BASE[1][:-1]))
        deps = {(d["chain"], d["contract"]) for d in self.q("SELECT * FROM asset_deployment WHERE asset_id=?", (a["asset_id"],))}
        self.assertIn(("solana", SOL_ADDR + BASE[1]), deps)                 # base58 case preserved
        self.assertTrue(all(c == c.lower() for ch, c in deps if ch == "ethereum"))   # EVM lowercased
        refs = self.q("SELECT resolution_status FROM source_asset_ref WHERE platform_symbol=?", (BASE[1].upper(),))
        self.assertTrue(refs and all(r["resolution_status"] == "CONFIRMED" for r in refs))

    def test_chain_names(self):
        self.assertEqual(canonical_chain("BinanceSmartChain"), "bsc")
        self.assertEqual(canonical_chain("Ethereum"), "ethereum")
        self.assertEqual(canonical_chain("HyperEVM"), "hyperevm")
        self.assertEqual(canonical_chain("MATIC"), "polygon")
        self.assertEqual(canonical_chain("Some_New-Chain"), "somenewchain")


if __name__ == "__main__":
    unittest.main()
