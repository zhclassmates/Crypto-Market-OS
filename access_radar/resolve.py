"""CEX token identity resolution: attach source_asset_ref rows to global assets.

Exchange notices and market lists (Upbit, Bithumb, Coinone, Korbit, NewListings ...) usually carry only a
symbol. radar_core stores those refs UNRESOLVED and never drops the event; this module fills them in later.

Order of evidence (strongest first):
  1. Exact contract. A ref whose access_state key is 'ca:<chain>:<contract>' and that (chain, contract) is a
     known asset_deployment -> CONFIRMED, resolution_source 'contract'. (Refs whose adapter passed chain/contract
     are already confirmed by radar_core at ingest; this pass catches deployments registered afterwards.)
  2. Symbol. The ref's platform_symbol equals the symbol of exactly ONE crypto asset in the registry
     -> SUGGESTED (待确认), resolution_source 'symbol'. When several assets share the symbol, but exactly one of
     them is currently live on Binance Alpha -> SUGGESTED, resolution_source 'symbol_alpha_live'.
     Anything still ambiguous stays UNRESOLVED and is counted, never guessed.
  Symbol matching is only applied to refs on CEX platforms by default: issuer / on-ramp refs (xStocks, Ramp ...)
  carry their own contracts or are not tokens at all.

The registry is filled from the Binance Alpha token list (public, no key): every Alpha token becomes asset
'crypto:<chain>:<contract>' (CRYPTO) with one asset_deployment. Existing assets are never overwritten.

Never touches CONFIRMED refs and never downgrades. Pure stdlib; tests inject `fetch` and never hit the network.

CLI:
  python3 resolve.py --db access.sqlite              # fetch Alpha list, register, resolve, print summary
  python3 resolve.py --db access.sqlite --offline    # only resolve against what is already in the registry
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import radar_core as rc  # noqa: E402

from adapters._fetch import default_fetch  # noqa: E402
from adapters.chains import canonical_chain  # noqa: E402

ALPHA_URL = ("https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list")

# Binance Alpha chainId -> canonical chain (adapters/chains.py names). Unknown ids become 'chainid:<id>' so they
# can never collide with a real chain name; add them here once confirmed.
ALPHA_CHAINS = {
    "1": "ethereum", "56": "bsc", "8453": "base", "CT_501": "solana", "42161": "arbitrum", "10": "optimism",
    "137": "polygon", "43114": "avalanche", "196": "xlayer", "4663": "robinhood", "59144": "linea",
    "324": "zksync", "5000": "mantle", "143": "monad", "999": "hyperevm",
    "CT_784": "sui", "CT_195": "tron", "146": "sonic",       # Mac 实测 2026-10-04 确认
}
_ALPHA_CHAINS_CI = {k.upper(): v for k, v in ALPHA_CHAINS.items()}
CRYPTO_TYPES = ("CRYPTO", "STABLECOIN")


class AlphaListError(Exception):
    pass


def alpha_chain(chain_id):
    cid = str(chain_id or "").strip()
    if not cid:
        return ""
    return _ALPHA_CHAINS_CI.get(cid.upper()) or f"chainid:{cid.lower()}"     # 大小写不敏感（CT_784 / ct_784）


def parse_alpha(payload):
    """Binance Alpha list JSON -> [{symbol, name, chain, contract, decimals, live, alpha_id}]. Raises on bad shape."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise AlphaListError("unexpected Alpha list shape")
    out = []
    for t in payload["data"]:
        if not isinstance(t, dict):
            continue
        sym = (t.get("symbol") or "").strip().upper()
        chain = alpha_chain(t.get("chainId"))
        chain, contract = rc._norm_contract(chain, t.get("contractAddress"))
        if not (sym and chain and contract):
            continue
        dec = t.get("decimals")
        try:
            dec = int(dec) if dec not in (None, "") else None
        except (TypeError, ValueError):
            dec = None
        out.append({"symbol": sym, "name": (t.get("name") or "").strip(), "chain": chain, "contract": contract,
                    "decimals": dec, "live": not bool(t.get("offline") or t.get("offsell")),
                    "alpha_id": str(t.get("alphaId") or "")})
    if payload["data"] and not out:
        raise AlphaListError("Alpha list had rows but none were usable")
    return out


def fetch_alpha(fetch=None):
    """`fetch` is either the runner's shared access_http.HttpClient (has .get_json) or a fetch(url, headers) callable."""
    if fetch is not None and hasattr(fetch, "get_json"):
        return parse_alpha(fetch.get_json(ALPHA_URL))
    return parse_alpha((fetch or default_fetch)(ALPHA_URL))


def asset_key_for(chain, contract):
    return f"crypto:{chain}:{contract}"


def register_alpha(conn, tokens, at=None):
    """Upsert Alpha tokens into the asset registry without clobbering existing assets. Returns counts."""
    at = at or rc.now_ms()
    new_assets = new_deps = 0
    with rc._tx(conn):
        for t in tokens:
            dep = conn.execute("SELECT asset_id FROM asset_deployment WHERE chain=? AND contract=?",
                               (t["chain"], t["contract"])).fetchone()
            if dep:
                continue          # contract already belongs to some asset (maybe richer, e.g. xStocks) -> keep it
            key = asset_key_for(t["chain"], t["contract"])
            row = conn.execute("SELECT asset_id FROM asset WHERE asset_key=?", (key,)).fetchone()
            if row:
                asset_id = row[0]
            else:
                asset_id = rc.upsert_asset(conn, key, "CRYPTO", t["symbol"], name=t["name"], at=at)
                new_assets += 1
            rc.add_deployment(conn, asset_id, t["chain"], t["contract"], decimals=t["decimals"], at=at)
            new_deps += 1
    return {"alpha_tokens": len(tokens), "new_assets": new_assets, "new_deployments": new_deps}


def _ca_key(asset_key):
    """'ca:<chain>:<contract>' -> (chain, contract) normalised, else None. Contract may itself contain ':'."""
    if not asset_key.startswith("ca:"):
        return None
    parts = asset_key.split(":", 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        return None
    return rc._norm_contract(canonical_chain(parts[1]), parts[2])


def _symbol_candidates(conn):
    """symbol -> set(asset_id) over crypto assets that have at least one deployment."""
    rows = conn.execute(
        f"""SELECT DISTINCT a.symbol, a.asset_id FROM asset a JOIN asset_deployment d ON d.asset_id = a.asset_id
            WHERE a.asset_type IN ({",".join("?" * len(CRYPTO_TYPES))})""", CRYPTO_TYPES).fetchall()
    out = {}
    for sym, aid in rows:
        out.setdefault((sym or "").upper(), set()).add(aid)
    return out


def _live_alpha_assets(conn, tokens):
    if not tokens:
        return set()
    live = set()
    for t in tokens:
        if t["live"]:
            r = conn.execute("SELECT asset_id FROM asset_deployment WHERE chain=? AND contract=?",
                             (t["chain"], t["contract"])).fetchone()
            if r:
                live.add(r[0])
    return live


def resolve_pending(conn, alpha_tokens=None, symbol_platform_types=("CEX",), at=None):
    """One resolution pass over every non-CONFIRMED ref. Returns counts + the ambiguous symbols."""
    at = at or rc.now_ms()
    stats = {"checked": 0, "confirmed_contract": 0, "suggested": 0, "already_suggested": 0,
             "ambiguous": 0, "unmatched": 0, "skipped_platform": 0}
    ambiguous = {}
    cands = _symbol_candidates(conn)
    live = _live_alpha_assets(conn, alpha_tokens or [])
    refs = conn.execute(
        """SELECT r.ref_id, r.platform_symbol, r.resolution_status, r.suggested_asset_id, p.platform_type, r.platform_id
           FROM source_asset_ref r JOIN platform p ON p.platform_id = r.platform_id
           WHERE r.resolution_status <> 'CONFIRMED' ORDER BY r.ref_id""").fetchall()
    with rc._tx(conn):
        for ref_id, sym, status, sugg, ptype, platform_id in refs:
            stats["checked"] += 1
            # 1) exact contract via the platform-local key 'ca:<chain>:<contract>'
            hit = None
            for (key,) in conn.execute(
                    """SELECT DISTINCT asset_key FROM access_state WHERE ref_id=? UNION
                       SELECT DISTINCT asset_key FROM source_observation WHERE ref_id=?""", (ref_id, ref_id)):
                cc = _ca_key(key)
                if cc:
                    r = conn.execute("SELECT asset_id FROM asset_deployment WHERE chain=? AND contract=?", cc).fetchone()
                    if r:
                        hit = r[0]
                        break
            if hit is not None:
                rc.resolve_ref(conn, ref_id, hit, status="CONFIRMED", resolution_source="contract", at=at)
                stats["confirmed_contract"] += 1
                continue
            # 2) symbol -> SUGGESTED only
            if symbol_platform_types and ptype not in symbol_platform_types:
                stats["skipped_platform"] += 1
                continue
            ids = cands.get((sym or "").upper(), set())
            pick, how = None, ""
            if len(ids) == 1:
                pick, how = next(iter(ids)), "symbol"
            elif len(ids) > 1:
                lv = ids & live
                if len(lv) == 1:
                    pick, how = next(iter(lv)), "symbol_alpha_live"
            if pick is None:
                if ids:
                    stats["ambiguous"] += 1
                    ambiguous.setdefault(sym, len(ids))
                else:
                    stats["unmatched"] += 1
                continue
            if status == "SUGGESTED" and sugg == pick:
                stats["already_suggested"] += 1
                continue
            rc.resolve_ref(conn, ref_id, pick, status="SUGGESTED", resolution_source=how, at=at)
            stats["suggested"] += 1
    stats["ambiguous_symbols"] = dict(sorted(ambiguous.items()))
    return stats


def run(conn, fetch=None, offline=False, at=None):
    """Fetch Alpha (unless offline), register it, then resolve. Alpha fetch failure still runs the pass."""
    at = at or rc.now_ms()
    out = {"alpha_error": ""}
    tokens = []
    if not offline:
        try:
            tokens = fetch_alpha(fetch)
            out.update(register_alpha(conn, tokens, at=at))
        except Exception as e:  # noqa: BLE001 - resolution against the existing registry still runs
            out["alpha_error"] = f"{type(e).__name__}: {e}"
    out.update(resolve_pending(conn, alpha_tokens=tokens, at=at))
    return out


def resolution_summary(conn):
    """{status: count} over all refs — used by ops/nightly.py and access_run status."""
    return {s: c for s, c in conn.execute(
        "SELECT resolution_status, COUNT(*) FROM source_asset_ref GROUP BY resolution_status")}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Access Radar: resolve CEX symbols to global assets")
    ap.add_argument("--db", default=os.environ.get("ACCESS_DB") or os.environ.get("ACCESS_RADAR_DB")
                    or os.path.join(rc.HERE, "access.sqlite"))
    ap.add_argument("--offline", action="store_true", help="skip the Binance Alpha fetch")
    a = ap.parse_args(argv)
    conn = rc.init_db(a.db)
    res = run(conn, offline=a.offline)
    res["totals"] = resolution_summary(conn)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 1 if res["alpha_error"] and not a.offline else 0


if __name__ == "__main__":
    sys.exit(main())
