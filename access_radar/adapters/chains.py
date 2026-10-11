"""Canonical chain names shared by adapters (schema.sql: lowercase canonical, e.g. 'ethereum', 'solana', 'bsc').

Every source spells chains differently (Ramp 'ETH'/'MATIC', xStocks 'Ethereum'/'BinanceSmartChain',
Korbit network codes ...). Map them here so asset_deployment (chain, contract) matches across sources.
Unknown names fall back to a lowercased, separator-free form.
"""
import re

_ALIASES = {
    "ethereum": ("eth", "ethereum", "erc20", "mainnet"),
    "solana": ("sol", "solana", "spl"),
    "bsc": ("bsc", "bnb", "bep20", "binancesmartchain", "bnbsmartchain", "bnbchain"),
    "base": ("base",),
    "arbitrum": ("arbitrum", "arb", "arbitrumone"),
    "optimism": ("optimism", "op", "opmainnet"),
    "polygon": ("polygon", "matic", "pol"),
    "polygon_zkevm": ("polygonzkevm",),
    "avalanche": ("avax", "avalanche", "avaxc", "avalanchec", "avalanchecchain"),
    "tron": ("tron", "trx", "trc20"),
    "sui": ("sui",),
    "sonic": ("sonic",),
    "ton": ("ton",),
    "mantle": ("mantle", "mnt"),
    "monad": ("monad",),
    "xlayer": ("xlayer", "okxlayer"),
    "hyperevm": ("hyperevm", "hyperliquidevm"),
    "ink": ("ink",),
    "linea": ("linea",),
    "zksync": ("zksync", "zksyncera"),
    "starknet": ("starknet",),
    "gnosis": ("gnosis", "xdai"),
    "near": ("near",),
    "stellar": ("xlm", "stellar"),
    "ripple": ("xrp", "ripple", "xrpl"),
    "bitcoin": ("btc", "bitcoin"),
    "robinhood": ("robinhood", "robinhoodchain"),
    # non-EVM L1s seen as Korbit / Ramp network codes. Ramp's separate DOT vs POLKADOT routes collapse here;
    # ramp.py keeps the LIVE one when two routes merge.
    "polkadot": ("dot", "polkadot"),
    "cardano": ("ada", "cardano"),
    "dogecoin": ("doge", "dogecoin"),
    "aptos": ("apt", "aptos"),
    "cosmos": ("atom", "cosmos", "cosmoshub"),
    "kaia": ("kaia", "klay", "klaytn"),
    "litecoin": ("ltc", "litecoin"),
    "bitcoin_cash": ("bch", "bitcoincash"),
    "ethereum_classic": ("etc", "ethereumclassic"),
    "algorand": ("algo", "algorand"),
    "hedera": ("hbar", "hedera", "hederahashgraph"),
    "tezos": ("xtz", "tezos"),
    "celestia": ("tia", "celestia"),
}
_LOOKUP = {alias: canon for canon, aliases in _ALIASES.items() for alias in aliases}


def canonical_chain(name):
    key = re.sub(r"[\s_\-.]", "", (name or "").strip().lower())
    if not key:
        return ""
    return _LOOKUP.get(key, key)
