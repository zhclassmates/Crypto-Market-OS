"""Identity resolution tests: fixed Alpha fixture, in-memory SQLite, no network."""
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import radar_core as rc  # noqa: E402
import resolve as rs  # noqa: E402

T0 = 1_790_000_000_000
SOL_MINT = "So1AnaMintCaseSensitiveXyZ111111111111111111"


def alpha_payload(extra=()):
    rows = [
        {"alphaId": "ALPHA_1", "symbol": "rez", "name": "Renzo", "chainId": "56",
         "contractAddress": "0xAbCdEf0000000000000000000000000000000001", "decimals": "18"},
        {"alphaId": "ALPHA_2", "symbol": "DUP", "name": "Dup on BSC", "chainId": "56",
         "contractAddress": "0x00000000000000000000000000000000000000d1"},
        {"alphaId": "ALPHA_3", "symbol": "DUP", "name": "Dup on Base", "chainId": "8453",
         "contractAddress": "0x00000000000000000000000000000000000000d2", "offline": True},
        {"alphaId": "ALPHA_4", "symbol": "TWIN", "name": "Twin A", "chainId": "1",
         "contractAddress": "0x00000000000000000000000000000000000000e1"},
        {"alphaId": "ALPHA_5", "symbol": "TWIN", "name": "Twin B", "chainId": "CT_501",
         "contractAddress": SOL_MINT},
        {"alphaId": "ALPHA_6", "symbol": "NEWCHAIN", "chainId": "777777",
         "contractAddress": "0x00000000000000000000000000000000000000f1"},
        {"alphaId": "ALPHA_7", "symbol": "", "chainId": "56", "contractAddress": "0xdead"},   # unusable -> skipped
    ]
    return {"code": "000000", "data": rows + list(extra)}


def fake_fetch(payload):
    calls = []

    def fetch(url, headers=None):
        calls.append(url)
        if isinstance(payload, Exception):
            raise payload
        return payload
    fetch.calls = calls
    return fetch


class Base(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.conn = rc.init_db(rc.connect(":memory:"))
        rc.register_platform(self.conn, "upbit", "Upbit", "CEX", "KR", at=T0)
        rc.register_platform(self.conn, "ramp", "Ramp", "ONRAMP", "", at=T0)
        rc.register_source(self.conn, "upbit_market", kind="SNAPSHOT", tier="OFFICIAL_STRUCTURED",
                           origin_platform_id="upbit", at=T0)
        rc.register_source(self.conn, "ramp_assets", kind="SNAPSHOT", tier="OFFICIAL_STRUCTURED",
                           origin_platform_id="ramp", at=T0)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def upbit(self, syms, extra=(), at=T0):
        items = [{"symbol": s, "quote": "KRW", "access_kind": "SPOT"} for s in syms] + list(extra)
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", items, fetched_at=at)

    def ref(self, sym, platform="upbit"):
        return rc._one(self.conn, "SELECT * FROM source_asset_ref WHERE platform_id=? AND platform_symbol=?",
                       (platform, sym))

    def asset_of(self, chain, contract):
        return self.conn.execute("SELECT asset_id FROM asset_deployment WHERE chain=? AND contract=?",
                                 (chain, contract)).fetchone()[0]


class ParseAlpha(unittest.TestCase):
    def test_parse_normalises_and_skips_unusable(self):
        toks = rs.parse_alpha(alpha_payload())
        self.assertEqual(len(toks), 6)
        rez = toks[0]
        self.assertEqual((rez["symbol"], rez["chain"], rez["decimals"]), ("REZ", "bsc", 18))
        self.assertEqual(rez["contract"], "0xabcdef0000000000000000000000000000000001")   # EVM lowercased
        twin_sol = [t for t in toks if t["chain"] == "solana"][0]
        self.assertEqual(twin_sol["contract"], SOL_MINT)                                  # base58 case kept
        self.assertFalse([t for t in toks if t["symbol"] == "DUP" and t["chain"] == "base"][0]["live"])
        self.assertEqual([t for t in toks if t["symbol"] == "NEWCHAIN"][0]["chain"], "chainid:777777")

    def test_bad_shape_raises(self):
        for bad in (None, [], {"data": None}, {"code": "x"}):
            with self.assertRaises(rs.AlphaListError):
                rs.parse_alpha(bad)
        with self.assertRaises(rs.AlphaListError):
            rs.parse_alpha({"data": [{"symbol": "", "chainId": "", "contractAddress": ""}]})

    def test_empty_list_is_valid(self):
        self.assertEqual(rs.parse_alpha({"data": []}), [])


class Register(Base):
    def test_register_is_idempotent_and_does_not_clobber(self):
        xs = rc.upsert_asset(self.conn, "xstocks:AAPLx", "TOKENIZED_STOCK", "AAPLX", name="Apple xStock",
                             issuer="backed", at=T0)
        rc.add_deployment(self.conn, xs, "bsc", "0x00000000000000000000000000000000000000d1", at=T0)
        toks = rs.parse_alpha(alpha_payload())
        first = rs.register_alpha(self.conn, toks, at=T0)
        self.assertEqual(first["new_assets"], 5)        # DUP@bsc contract already owned by the xStocks asset
        again = rs.register_alpha(self.conn, toks, at=T0)
        self.assertEqual((again["new_assets"], again["new_deployments"]), (0, 0))
        a = rc._one(self.conn, "SELECT * FROM asset WHERE asset_id=?", (xs,))
        self.assertEqual((a["name"], a["issuer"]), ("Apple xStock", "backed"))
        key = rc._one(self.conn, "SELECT asset_key, asset_type FROM asset WHERE symbol='REZ'")
        self.assertEqual(key, {"asset_key": "crypto:bsc:0xabcdef0000000000000000000000000000000001",
                               "asset_type": "CRYPTO"})


class Resolve(Base):
    def test_unique_symbol_suggested_not_confirmed(self):
        self.upbit(["REZ", "BTC"])
        res = rs.run(self.conn, fetch=fake_fetch(alpha_payload()), at=T0 + 1)
        r = self.ref("REZ")
        self.assertEqual(r["resolution_status"], "SUGGESTED")
        self.assertEqual(r["resolution_source"], "symbol")
        self.assertIsNone(r["asset_id"])
        self.assertEqual(r["suggested_asset_id"], self.asset_of("bsc", "0xabcdef0000000000000000000000000000000001"))
        self.assertEqual(self.ref("BTC")["resolution_status"], "UNRESOLVED")
        self.assertEqual((res["suggested"], res["unmatched"]), (1, 1))
        # SUGGESTED must not leak into access_state.asset_id (only CONFIRMED does)
        self.assertIsNone(self.conn.execute(
            "SELECT asset_id FROM access_state WHERE asset_key='sym:REZ'").fetchone()[0])

    def test_ambiguous_prefers_single_live_alpha(self):
        self.upbit(["DUP", "TWIN"])
        res = rs.run(self.conn, fetch=fake_fetch(alpha_payload()), at=T0 + 1)
        dup = self.ref("DUP")
        self.assertEqual((dup["resolution_status"], dup["resolution_source"]), ("SUGGESTED", "symbol_alpha_live"))
        self.assertEqual(dup["suggested_asset_id"], self.asset_of("bsc", "0x00000000000000000000000000000000000000d1"))
        self.assertEqual(self.ref("TWIN")["resolution_status"], "UNRESOLVED")   # both live -> never guess
        self.assertEqual(res["ambiguous_symbols"], {"TWIN": 2})

    def test_offline_ambiguity_without_alpha_stays_unresolved(self):
        rs.register_alpha(self.conn, rs.parse_alpha(alpha_payload()), at=T0)
        self.upbit(["DUP"])
        res = rs.run(self.conn, offline=True, at=T0 + 1)
        self.assertEqual(self.ref("DUP")["resolution_status"], "UNRESOLVED")
        self.assertEqual(res["ambiguous"], 1)

    def test_ca_key_confirms_after_deployment_registered_later(self):
        # adapter knew the contract but the deployment wasn't in the registry yet at ingest time
        self.upbit([], extra=[{"symbol": "TWIN", "asset_key": f"ca:Solana:{SOL_MINT}", "quote": "KRW",
                               "access_kind": "SPOT"}])
        self.assertEqual(self.ref("TWIN")["resolution_status"], "UNRESOLVED")
        res = rs.run(self.conn, fetch=fake_fetch(alpha_payload()), at=T0 + 1)
        r = self.ref("TWIN")
        aid = self.asset_of("solana", SOL_MINT)
        self.assertEqual((r["resolution_status"], r["resolution_source"], r["asset_id"]), ("CONFIRMED", "contract", aid))
        self.assertEqual(res["confirmed_contract"], 1)
        self.assertEqual(self.conn.execute(
            "SELECT asset_id FROM access_state WHERE asset_key=?", (f"ca:Solana:{SOL_MINT}",)).fetchone()[0], aid)

    def test_confirmed_is_never_touched(self):
        self.upbit(["REZ"])
        other = rc.upsert_asset(self.conn, "manual:rez", "CRYPTO", "REZ", at=T0)
        rc.resolve_ref(self.conn, self.ref("REZ")["ref_id"], other, status="CONFIRMED", at=T0)
        res = rs.run(self.conn, fetch=fake_fetch(alpha_payload()), at=T0 + 1)
        r = self.ref("REZ")
        self.assertEqual((r["resolution_status"], r["asset_id"], r["resolution_source"]), ("CONFIRMED", other, "manual"))
        self.assertEqual(res["checked"], 0)

    def test_non_cex_platform_skips_symbol_match(self):
        rc.ingest_snapshot(self.conn, "ramp_assets", "USD",
                           [{"symbol": "REZ", "access_kind": "FIAT_ROUTE", "fiat": "USD"}], fetched_at=T0)
        res = rs.run(self.conn, fetch=fake_fetch(alpha_payload()), at=T0 + 1)
        self.assertEqual(self.ref("REZ", "ramp")["resolution_status"], "UNRESOLVED")
        self.assertEqual(res["skipped_platform"], 1)

    def test_rerun_is_idempotent(self):
        self.upbit(["REZ"])
        rs.run(self.conn, fetch=fake_fetch(alpha_payload()), at=T0 + 1)
        res = rs.run(self.conn, fetch=fake_fetch(alpha_payload()), at=T0 + 2)
        self.assertEqual((res["suggested"], res["already_suggested"]), (0, 1))
        self.assertEqual(self.ref("REZ")["resolved_at"], T0 + 1)

    def test_alpha_fetch_failure_still_resolves_from_registry(self):
        rs.register_alpha(self.conn, rs.parse_alpha(alpha_payload()), at=T0)
        self.upbit(["REZ"])
        res = rs.run(self.conn, fetch=fake_fetch(RuntimeError("HTTP 403")), at=T0 + 1)
        self.assertIn("HTTP 403", res["alpha_error"])
        self.assertEqual(self.ref("REZ")["resolution_status"], "SUGGESTED")

    def test_accepts_shared_http_client(self):
        class Client:
            def __init__(self):
                self.urls = []

            def get_json(self, url, params=None, headers=None):
                self.urls.append(url)
                return alpha_payload()
        cl = Client()
        self.upbit(["REZ"])
        res = rs.run(self.conn, fetch=cl, at=T0 + 1)
        self.assertEqual((cl.urls, res["suggested"]), ([rs.ALPHA_URL], 1))

    def test_summary_counts(self):
        self.upbit(["REZ", "BTC", "TWIN"])
        rs.run(self.conn, fetch=fake_fetch(alpha_payload()), at=T0 + 1)
        self.assertEqual(rs.resolution_summary(self.conn), {"SUGGESTED": 1, "UNRESOLVED": 2})


class CaKey(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(rs._ca_key("ca:BSC:0xABC"), ("bsc", "0xabc"))
        self.assertEqual(rs._ca_key(f"ca:sol:{SOL_MINT}"), ("solana", SOL_MINT))
        for k in ("sym:REZ", "ca:", "ca:bsc", "ca::0xabc", "xstocks:AAPLx"):
            self.assertIsNone(rs._ca_key(k))


class AlphaChains(unittest.TestCase):
    def test_mac_confirmed_ids_case_insensitive(self):
        for cid, chain in (("CT_784", "sui"), ("ct_784", "sui"), ("CT_195", "tron"), ("ct_195", "tron"),
                           ("146", "sonic"), ("CT_501", "solana"), ("ct_501", "solana"), (4663, "robinhood")):
            self.assertEqual(rs.alpha_chain(cid), chain, cid)
        self.assertEqual(rs.alpha_chain("CT_9999"), "chainid:ct_9999")

    def test_parse_sui_tron_contracts(self):
        tron = "TXL6rJbvmjD46zeN1JssfgxvSo99qC8MRT"
        rows = rs.parse_alpha({"data": [
            {"symbol": "wal", "chainId": "CT_784", "contractAddress": "0x356A26EB9E012A68958082340D4C4116E7F55615CF27AFFCFF209CF0AE544F59::wal::WAL"},
            {"symbol": "sun", "chainId": "CT_195", "contractAddress": tron}]})
        self.assertEqual([(r["symbol"], r["chain"]) for r in rows], [("WAL", "sui"), ("SUN", "tron")])
        self.assertTrue(rows[0]["contract"].startswith("0x356a26eb"))          # 0x 开头统一小写
        self.assertEqual(rows[1]["contract"], tron)                             # Tron base58 区分大小写，原样保留


if __name__ == "__main__":
    unittest.main()
