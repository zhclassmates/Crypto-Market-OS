"""Circle adapter tests: fixed doc-page fixtures, in-memory SQLite, no network."""
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar_core as rc  # noqa: E402

from adapters import circle  # noqa: E402

H = 3600 * 1000
T0 = 1_790_000_000_000

MD_USDC = """# USDC contract addresses

## Mainnet

<Warning>
  **Mainnet Tokens have Financial Value**
</Warning>

| Blockchain | USDC Mainnet Address |
| :- | :- |
| Ethereum | [`0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`](https://etherscan.io/token/0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48) |
| Avalanche C-Chain | [`0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E`](https://snowtrace.io/token/0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E) |
| Polygon PoS | [`0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359`](https://polygonscan.com/token/0x3c499c542cef5e3811e1192ce70d8cc03d5c3359) |
| Solana | [`EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`](https://solscan.io/token/EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v) |
| Hedera | `0.0.456858` |
| Sui | [`0xDBA34672E30CB065B1F93E3AB55318768FD6FEF66C15942C9F7CB846E2F900E7::usdc::USDC`](https://suiscan.xyz/mainnet/coin/x::usdc::USDC/txs) |
| World Chain | [`0x79A02482A880bCe3F13E09da970dC34dB4cD24D1`](https://worldscan.org/address/0x79A02482A880bCe3F13E09da970dC34dB4cD24D1) |

## Testnet

| Blockchain | USDC Testnet Address |
| :- | :- |
| Ethereum Sepolia | [`0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238`](https://sepolia.etherscan.io/) |
"""

MD_EURC = """# EURC contract addresses

## Mainnet

| Blockchain | EURC Mainnet Address |
| :- | :- |
| Ethereum | [`0x60a3E35Cc302bFA44Cb288Bc5a4F335F972c7De3`](https://etherscan.io/token/0x60a3e35cc302bfa44cb288bc5a4f335f972c7de3) |
| Base | [`0x60a3E35Cc302bFA44Cb288Bc5a4F335F972c7De3`](https://basescan.org/) |
| Avalanche C-Chain | [`0xB97Ef9Ef8734C71904D8002F8b6Bc66Dd9c48a6E`](https://snowtrace.io/) |
| Solana | [`AfBDp9myMKdGnEbiTamL3mvTbVABAFxcdGH9nfhJhcUi`](https://solscan.io/token/AfBDp9myMKdGnEbiTamL3mvTbVABAFxcdGH9nfhJhcUi) |
| World Chain | [`0x79A02482A880bCe3F13E09da970dC34dB4cD24D1`](https://worldscan.org/) |
"""

MONAD_ROW = "\n| Monad | [`0x754704Bc059F8C67012fEd69BC8A327a5aafb603`](https://monadvision.com/) |\n"


class FakeHttp:
    """pages keys are URL substrings ('usdc' / 'eurc' match the doc URLs)."""

    def __init__(self, pages):
        self.pages = pages

    def get_text(self, url, **kw):
        hits = [v for k, v in self.pages.items() if k in url]
        if not hits:
            raise KeyError(url)
        v = hits[0]
        if isinstance(v, Exception):
            raise v
        return v


class CircleTest(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        rc.register_platform(self.conn, "circle", "Circle", "ISSUER", "", at=T0)
        rc.register_source(self.conn, "circle_chains", name="Circle docs", kind="SNAPSHOT",
                           tier="OFFICIAL_STRUCTURED", origin_platform_id="circle", at=T0)

    def tearDown(self):
        self.conn.close()

    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def poll(self, pages, at):
        out = circle.fetch(FakeHttp(pages))
        r = rc.ingest_snapshot(self.conn, "circle_chains", "deployments", out["deployments"],
                               fetched_at=at)
        return out, r

    def test_pages_parse_to_chain_items(self):
        out, r = self.poll({"usdc": MD_USDC, "eurc": MD_EURC}, T0)
        self.assertEqual(len(out["deployments"]), 12)          # 7 USDC + 5 EURC
        self.assertEqual(r["outcome"], "BASELINE")
        nets = {(i["symbol"], i["network"]) for i in out["deployments"]}
        self.assertIn(("USDC", "polygon"), nets)               # 'Polygon PoS'
        self.assertIn(("USDC", "avalanche"), nets)             # 'Avalanche C-Chain'
        self.assertIn(("USDC", "worldchain"), nets)
        hed = [i for i in out["deployments"] if i["network"] == "hedera"]
        self.assertEqual(hed[0]["contract"], "0.0.456858")     # verbatim, no link form
        self.assertFalse(any("sepolia" in i["contract"].lower() for i in out["deployments"]))

    def test_testnet_section_excluded(self):
        out, _ = self.poll({"usdc": MD_USDC, "eurc": MD_EURC}, T0)
        self.assertFalse(any("sepolia" in i["network"] or i["contract"].startswith("0x1c7D4B")
                             for i in out["deployments"]))

    def test_new_chain_produces_deployed_event(self):
        self.poll({"usdc": MD_USDC, "eurc": MD_EURC}, T0)
        _, r = self.poll({"usdc": MD_USDC.replace("| Solana |", MONAD_ROW + "| Solana |"),
                          "eurc": MD_EURC}, T0 + H)
        self.assertEqual(r["outcome"], "DIFF")
        ev = self.q("SELECT e.asset_key, e.event_type, s.network FROM access_event e "
                    "JOIN access_state s ON s.access_id = e.access_id")
        self.assertEqual([(e["asset_key"], e["event_type"], e["network"]) for e in ev],
                         [("sym:USDC", "CHAIN_DEPLOYED", "monad")])

    def test_layout_change_is_refused(self):
        small = "## Mainnet\n\n| Blockchain | addr |\n| :- | :- |\n| Ethereum | `0xA0b8` |\n"
        with self.assertRaises(circle.BadResponse):
            circle.fetch(FakeHttp({"usdc": small, "eurc": MD_EURC}))
        self.assertEqual(self.q("SELECT * FROM access_state"), [])

    def test_missing_section_is_refused(self):
        with self.assertRaises(circle.BadResponse):
            circle.fetch(FakeHttp({"usdc": "# USDC\n\nno table here", "eurc": MD_EURC}))

    def test_page_failure_breaks_the_whole_scope(self):
        with self.assertRaises(Exception):
            circle.fetch(FakeHttp({"usdc": MD_USDC, "eurc": ConnectionError("boom")}))
        self.assertEqual(self.q("SELECT * FROM access_state"), [])


if __name__ == "__main__":
    unittest.main()
