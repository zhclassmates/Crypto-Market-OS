"""chains.canonical_chain tests: aliases used by Korbit / Ramp / xStocks network names."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.chains import _ALIASES, canonical_chain  # noqa: E402


class CanonicalChain(unittest.TestCase):
    def test_new_aliases(self):
        cases = {
            "DOT": "polkadot", "Polkadot": "polkadot", "ADA": "cardano", "DOGE": "dogecoin", "APT": "aptos",
            "ATOM": "cosmos", "KAIA": "kaia", "KLAY": "kaia", "Klaytn": "kaia", "LTC": "litecoin",
            "BCH": "bitcoin_cash", "Bitcoin Cash": "bitcoin_cash", "ETC": "ethereum_classic",
            "Ethereum Classic": "ethereum_classic", "ALGO": "algorand", "HBAR": "hedera", "XTZ": "tezos",
            "TIA": "celestia", "Avalanche C-Chain": "avalanche", "OP Mainnet": "optimism",
        }
        for raw, want in cases.items():
            self.assertEqual(canonical_chain(raw), want, raw)

    def test_existing_unchanged(self):
        for raw, want in {"ETH": "ethereum", "BinanceSmartChain": "bsc", "SOL": "solana", "MATIC": "polygon",
                          "Polygon zkEVM": "polygon_zkevm", "": ""}.items():
            self.assertEqual(canonical_chain(raw), want, raw)

    def test_unknown_falls_back(self):
        self.assertEqual(canonical_chain("Some New-Chain"), "somenewchain")

    def test_no_alias_maps_to_two_chains(self):
        seen = {}
        for canon, aliases in _ALIASES.items():
            for a in aliases:
                self.assertNotIn(a, seen, f"{a} -> {seen.get(a)} and {canon}")
                seen[a] = canon


if __name__ == "__main__":
    unittest.main()
