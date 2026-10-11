"""Circle adapter — USDC / EURC chain deployments from the public contract-address doc pages.

GET https://developers.circle.com/stablecoins/usdc-contract-addresses.md   (Mainnet table, ~37 chains)
GET https://developers.circle.com/stablecoins/eurc-contract-addresses.md   (Mainnet table, ~9 chains)

No key.  These are the pages Circle itself tells integrators to look addresses up from ("Never
hardcode — use .../usdc-contract-addresses.md"), so they double as the canonical deployment
registry.  Parsed as markdown: the '## Mainnet' section's table rows `| Chain | `address` |`
(address optionally wrapped in a [`addr`](explorer) link); the Testnet section is excluded.

Native adapter (KIND snapshot): the source is markdown text and conn-style fetch() is JSON-only
(RecordingFetch -> http.get_json), so fetch(http) uses http.get_text.

One scope "deployments": one CHAIN_DEPLOYMENT item per (asset, chain), asset_key sym:USDC /
sym:EURC, status LIVE.  Contracts stay verbatim per chain convention (Hedera '0.0.456858', Stellar
'CODE-ISSUER', Sui fully-qualified type, Algorand asset id, Noble denom; 0x forms are lowercased by
radar_core's _norm_contract).  Unlike xstocks this adapter does not upsert the global asset tables
(native adapters never touch the DB): sym:USDC / sym:EURC asset rows and cross-source resolution
come from the resolve maintenance job and other sources' own upserts.
"""
import re
import sys

if __package__ in (None, ""):                                    # direct script run: python3 adapters/circle.py
    sys.path.insert(0, __file__.rsplit("/", 2)[0])

try:
    from .chains import canonical_chain
except ImportError:                                              # direct script run
    from chains import canonical_chain  # noqa: E402

USD_URL = "https://developers.circle.com/stablecoins/usdc-contract-addresses.md"
EURC_URL = "https://developers.circle.com/stablecoins/eurc-contract-addresses.md"
PLATFORM_ID = "circle"
SOURCE_ID = "circle_chains"
SCOPE = "deployments"
MIN_ROWS = 5          # a parsed table much smaller than this means the docs layout changed

# Circle page labels that canonical_chain() alone would leave unnormalized
_CHAIN_FIXES = {"polygonpos": "polygon", "polkadotassethub": "polkadot"}

_ROW_RE = re.compile(r"\|\s*([^|`]+?)\s*\|\s*\[?`([^`]+)`")
_MAINNET_RE = re.compile(r"^##\s*Mainnet\s*$", re.M)
_SECTION_RE = re.compile(r"^##\s+", re.M)


class BadResponse(Exception):
    pass


def _chain(label):
    c = canonical_chain(label)
    return _CHAIN_FIXES.get(c, c)


def _mainnet_rows(text):
    """-> [(chain label, address), ...] of the '## Mainnet' section."""
    m = _MAINNET_RE.search(text or "")
    if not m:
        raise BadResponse("no '## Mainnet' section found")
    body = text[m.end():]
    nxt = _SECTION_RE.search(body)
    if nxt:
        body = body[:nxt.start()]
    rows = []
    for ln in body.splitlines():
        m = _ROW_RE.match(ln)
        if m:
            rows.append((m.group(1).strip(), m.group(2).strip()))
    return rows


def parse_page(text):
    """markdown text -> [(chain, address), ...]. Raises BadResponse."""
    return [(_chain(label), addr) for label, addr in _mainnet_rows(text) if _chain(label) and addr]


def fetch(http):
    """-> {"deployments": [item, ...]}. Raises BadResponse / transport on any page failure."""
    if not hasattr(http, "get_text"):
        raise BadResponse("circle adapter needs an http client with get_text (markdown source)")
    items = []
    for symbol, url in (("USDC", USD_URL), ("EURC", EURC_URL)):
        rows = parse_page(http.get_text(url))
        if len(rows) < MIN_ROWS:
            raise BadResponse(f"{symbol} page parsed to only {len(rows)} rows (docs layout changed?)")
        for chain, addr in rows:
            items.append({"platform_id": PLATFORM_ID, "asset_key": f"sym:{symbol}", "symbol": symbol,
                          "access_kind": "CHAIN_DEPLOYMENT", "status": "LIVE", "network": chain,
                          "chain": chain, "contract": addr, "native_id": f"{symbol}:{chain}",
                          "raw": {"chain": chain, "address": addr}})
    return {SCOPE: items}


KIND = "snapshot"
PLATFORMS = [{"platform_id": PLATFORM_ID, "name": "Circle", "platform_type": "ISSUER", "country": ""}]
SOURCE = {"name": "Circle USDC/EURC contract addresses (docs)", "kind": "SNAPSHOT",
          "tier": "OFFICIAL_STRUCTURED", "origin_platform_id": PLATFORM_ID}


if __name__ == "__main__":
    from access_http import default_client
    out = fetch(default_client())
    print(f"circle: {len(out[SCOPE])} deployments")
    for it in out[SCOPE][:8]:
        print(f"  {it['symbol']:<5} {it['chain']:<20} {it['contract']}")
