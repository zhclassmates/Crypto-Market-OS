"""Unit tests for radar_core (stdlib unittest, simulated data, in-memory SQLite)."""
import contextlib
import io
import logging
import os
import sqlite3
import tempfile
import unittest

import radar_core as rc

H = 3600 * 1000
T0 = 1_790_000_000_000          # fixed simulated clock (UTC ms)
BASE = [f"C{i:02d}" for i in range(20)]   # 20 base markets


def upbit_items(syms, quote="KRW"):
    return [rc.map_upbit_market({"market": f"{quote}-{s}"}) for s in syms]


class RadarTestCase(unittest.TestCase):
    def setUp(self):
        logging.getLogger("access_radar").setLevel(logging.CRITICAL)
        self.conn = rc.init_db(":memory:")
        c = self.conn
        for pid, t in (("upbit", "CEX"), ("coinone", "CEX"), ("korbit", "CEX"), ("ramp", "ONRAMP"),
                       ("newlistings", "DATA_VENDOR")):
            rc.register_platform(c, pid, pid, t, at=T0)
        rc.register_source(c, "upbit_market", tier="OFFICIAL_STRUCTURED", origin_platform_id="upbit", at=T0)
        rc.register_source(c, "upbit_notice", kind="ANNOUNCEMENT", tier="OFFICIAL_ANNOUNCEMENT",
                           origin_platform_id="upbit", at=T0)
        rc.register_source(c, "newlistings", kind="ANNOUNCEMENT", tier="THIRD_PARTY", is_relay=True, at=T0)
        rc.register_source(c, "coinone_market", origin_platform_id="coinone", at=T0)
        rc.register_source(c, "korbit_pairs", origin_platform_id="korbit", at=T0)
        rc.register_source(c, "ramp_assets", origin_platform_id="ramp", at=T0)
        rc.register_source(c, "aggr_snap", tier="AGGREGATOR", origin_platform_id="upbit", at=T0)

    def tearDown(self):
        self.conn.close()

    # helpers
    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def events(self, **where):
        sql = "SELECT * FROM access_event"
        if where:
            sql += " WHERE " + " AND ".join(f"{k}=?" for k in where)
        return self.q(sql + " ORDER BY event_id", tuple(where.values()))

    def state(self, symbol, platform="upbit", kind="SPOT", quote="KRW", **extra):
        key = dict(asset_key=f"sym:{symbol}", platform_id=platform, access_kind=kind, quote=quote, **extra)
        rows = self.q("SELECT * FROM access_state WHERE " + " AND ".join(f"{k}=?" for k in key), tuple(key.values()))
        return rows[0] if rows else None

    def health(self, source, scope):
        return self.q("SELECT * FROM source_health WHERE source_id=? AND scope=?", (source, scope))[0]

    def baseline_upbit(self, syms=BASE, at=T0):
        r = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(syms), fetched_at=at)
        self.assertEqual(r["outcome"], "BASELINE")
        return r


class TestBaselineAndDiff(RadarTestCase):
    def test_first_snapshot_is_baseline_no_events(self):
        r = self.baseline_upbit()
        self.assertEqual(r["events"], [])
        self.assertEqual(self.events(), [])
        self.assertEqual(self.state("C00")["status"], "LIVE")
        self.assertEqual(self.state("C00")["created_via_baseline"], 1)
        h = self.health("upbit_market", "KRW")
        self.assertEqual((h["status"], h["baseline_done"], h["last_snapshot_size"]), ("HEALTHY", 1, 20))
        self.assertEqual(len(self.q("SELECT * FROM source_scope_baseline")), 1)
        self.assertEqual(self.q("SELECT COUNT(*) n FROM source_observation")[0]["n"], 0)

    def test_new_item_next_snapshot_emits_event(self):
        self.baseline_upbit()
        r = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE + ["NEW1"]), fetched_at=T0 + 60_000)
        self.assertEqual(r["outcome"], "DIFF")
        self.assertEqual(len(r["events"]), 1)
        ev = self.events()[0]
        self.assertEqual((ev["event_type"], ev["from_status"], ev["to_status"], ev["family"]),
                         ("SPOT_LISTED", "NONE", "LIVE", "ADD"))
        self.assertEqual(ev["asset_key"], "sym:NEW1")
        self.assertEqual(ev["quote"], "KRW")
        self.assertEqual(ev["poll_prev_at"], T0)            # uncertainty interval (T0, T0+60s]
        self.assertEqual(ev["live_observed_at"], T0 + 60_000)
        self.assertEqual(ev["independent_source_count"], 1)
        self.assertAlmostEqual(ev["confidence"], 0.95)
        self.assertEqual(ev["provisional"], 0)
        # unchanged next snapshot: no new events
        r = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE + ["NEW1"]), fetched_at=T0 + 120_000)
        self.assertEqual(r["events"], [])
        self.assertEqual(len(self.events()), 1)

    def test_new_scope_added_later_gets_own_baseline(self):
        self.baseline_upbit()
        r = rc.ingest_snapshot(self.conn, "upbit_market", "BTC", upbit_items(["X1", "X2", "X3", "X4"], "BTC"),
                               fetched_at=T0 + H)
        self.assertEqual(r["outcome"], "BASELINE")
        self.assertEqual(self.events(), [])
        self.assertEqual(len(self.q("SELECT * FROM source_scope_baseline WHERE source_id='upbit_market'")), 2)
        # the KRW scope is unaffected; a new BTC item afterwards is an event
        r = rc.ingest_snapshot(self.conn, "upbit_market", "BTC", upbit_items(["X1", "X2", "X3", "X4", "X5"], "BTC"),
                               fetched_at=T0 + 2 * H)
        self.assertEqual(len(r["events"]), 1)
        self.assertEqual(self.events()[0]["quote"], "BTC")


class TestHealthGating(RadarTestCase):
    def test_zero_items_is_degraded_no_remove(self):
        self.baseline_upbit()
        for i in range(1, 6):   # API keeps returning nothing
            r = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", [], fetched_at=T0 + i * 60_000)
            self.assertEqual((r["outcome"], r["health"]), ("DEGRADED", "DEGRADED"))
        self.assertEqual(self.events(), [])
        self.assertEqual(self.state("C05")["status"], "LIVE")
        self.assertEqual(self.state("C05")["miss_count"], 0)
        self.assertEqual(self.q("SELECT COUNT(*) n FROM source_item_state WHERE miss_count>0")[0]["n"], 0)
        # recovery
        r = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE), fetched_at=T0 + 10 * 60_000)
        self.assertEqual((r["outcome"], r["health"]), ("DIFF", "HEALTHY"))
        self.assertEqual(self.events(), [])

    def test_shrink_over_20pct_is_degraded_no_remove(self):
        syms = [f"S{i:03d}" for i in range(100)]
        self.baseline_upbit(syms)
        for i in range(1, 3):
            r = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(syms[:70]), fetched_at=T0 + i * 60_000)
            self.assertEqual(r["outcome"], "DEGRADED")
            self.assertIn("outside", r["note"])
        self.assertEqual(self.events(family="REMOVE"), [])
        self.assertEqual(self.state("S099")["status"], "LIVE")
        # within tolerance (-10%) is a normal diff
        r = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(syms[:90]), fetched_at=T0 + 5 * 60_000)
        self.assertEqual(r["outcome"], "DIFF")
        self.assertEqual(self.events(), [])   # first miss only

    def test_persistent_consistent_new_size_is_accepted_after_3(self):
        syms = [f"S{i:03d}" for i in range(100)]
        self.baseline_upbit(syms)
        outs = [rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(syms[:70]),
                                   fetched_at=T0 + i * 60_000)["outcome"] for i in (1, 2, 3)]
        self.assertEqual(outs, ["DEGRADED", "DEGRADED", "SIZE_ACCEPTED"])
        self.assertEqual(self.events(), [])   # accepted snapshot only starts miss counting

    def test_schema_check_fails_on_many_invalid_items(self):
        self.baseline_upbit()
        bad = upbit_items(BASE) + [{"symbol": "X", "access_kind": "NOPE"}] * 5
        r = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", bad, fetched_at=T0 + 60_000)
        self.assertEqual(r["outcome"], "DEGRADED")
        self.assertEqual(self.health("upbit_market", "KRW")["schema_ok"], 0)
        self.assertEqual(self.events(), [])

    def test_fetch_error_sets_down_and_disconnect_intervals(self):
        rc.report_fetch_error(self.conn, "upbit_market", "KRW", "HTTP 503", at=T0)
        self.assertEqual(self.health("upbit_market", "KRW")["status"], "DOWN")
        rc.mark_disconnected(self.conn, "upbit_notice", "", at=T0, reason="ws closed")
        self.assertEqual(rc.mark_reconnected(self.conn, "upbit_notice", "", at=T0 + 5000), (T0, T0 + 5000))
        self.assertEqual(len(rc.open_gaps(self.conn, "upbit_notice")), 1)


class TestRemoval(RadarTestCase):
    def test_three_healthy_misses_then_removed(self):
        self.baseline_upbit()
        without = [s for s in BASE if s != "C07"]
        r1 = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(without), fetched_at=T0 + 60_000)
        # a degraded snapshot in between does not count as a miss
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", [], fetched_at=T0 + 90_000)
        r2 = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(without), fetched_at=T0 + 120_000)
        self.assertEqual(r1["events"] + r2["events"], [])
        self.assertEqual(self.state("C07")["status"], "LIVE")
        self.assertEqual(self.state("C07")["miss_count"], 2)
        r3 = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(without), fetched_at=T0 + 180_000)
        self.assertEqual(len(r3["events"]), 1)
        ev = self.events()[0]
        self.assertEqual((ev["event_type"], ev["from_status"], ev["to_status"]), ("SPOT_DELISTED", "LIVE", "REMOVED"))
        self.assertEqual(ev["poll_prev_at"], T0)              # last seen
        self.assertEqual(ev["live_observed_at"], T0 + 60_000)  # first miss
        self.assertEqual(self.state("C07")["status"], "REMOVED")
        # relisting later
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE), fetched_at=T0 + 10 * H)
        self.assertEqual(self.events()[-1]["event_type"], "SPOT_RELISTED")

    def test_reappearing_item_resets_miss_count(self):
        self.baseline_upbit()
        without = [s for s in BASE if s != "C07"]
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(without), fetched_at=T0 + 1)
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(without), fetched_at=T0 + 2)
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE), fetched_at=T0 + 3)
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(without), fetched_at=T0 + 4)
        self.assertEqual(self.state("C07")["status"], "LIVE")
        self.assertEqual(self.events(), [])

    def test_remove_min_elapsed_guard(self):
        rc.register_source(self.conn, "upbit_market", origin_platform_id="upbit", remove_min_elapsed_ms=10 * 60_000)
        self.baseline_upbit()
        without = [s for s in BASE if s != "C07"]
        for i in range(1, 5):   # 4 misses within 8 seconds: not enough elapsed time
            rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(without), fetched_at=T0 + i * 2000)
        self.assertEqual(self.state("C07")["status"], "LIVE")
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(without), fetched_at=T0 + 11 * 60_000)
        self.assertEqual(self.state("C07")["status"], "REMOVED")

    def test_official_delisting_scheduled_then_effective(self):
        self.baseline_upbit()
        eff = T0 + 5 * 24 * H
        r = rc.ingest_announcement(self.conn, "upbit_notice", {
            "action": "DELISTING", "symbol": "C03", "quote": "KRW", "announced_at": T0 + H, "observed_at": T0 + H + 500,
            "effective_at": eff, "source_event_id": "n-1"})
        ev = self.events()[0]
        self.assertEqual(ev["event_type"], "SPOT_DELISTED_SCHEDULED")
        self.assertEqual(self.state("C03")["status"], "LIVE")
        self.assertEqual(self.state("C03")["pending_removal_at"], eff)
        # after effective time, the first healthy miss removes it (1 official delisting is enough)
        without = [s for s in BASE if s != "C03"]
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(without), fetched_at=eff + 60_000)
        self.assertEqual(self.state("C03")["status"], "REMOVED")
        evs = self.events()
        self.assertEqual(len(evs), 1, "removal merges into the scheduled episode via effective_at window")
        self.assertEqual(evs[0]["event_type"], "SPOT_DELISTED")
        self.assertEqual(evs[0]["independent_source_count"], 2)
        self.assertEqual(r["events"], [evs[0]["event_id"]])

    def test_official_delisting_immediate_and_process_due(self):
        self.baseline_upbit()
        rc.ingest_announcement(self.conn, "upbit_notice", {"action": "DELISTING", "symbol": "C01", "quote": "KRW",
                                                           "observed_at": T0 + H, "source_event_id": "d1"})
        self.assertEqual(self.state("C01")["status"], "REMOVED")
        rc.ingest_announcement(self.conn, "upbit_notice", {"action": "DELISTING", "symbol": "C02", "quote": "KRW",
                                                           "observed_at": T0 + H, "effective_at": T0 + 2 * H,
                                                           "source_event_id": "d2"})
        self.assertEqual(rc.process_due(self.conn, at=T0 + H + 1), [])
        self.assertEqual(len(rc.process_due(self.conn, at=T0 + 2 * H + 1)), 1)
        self.assertEqual(self.state("C02")["status"], "REMOVED")

    def test_third_party_delisting_is_provisional_without_state_change(self):
        self.baseline_upbit()
        rc.ingest_announcement(self.conn, "newlistings", {"action": "DELISTING", "platform_id": "upbit", "symbol": "C04",
                                                          "quote": "KRW", "origin_group": "upbit_notice",
                                                          "observed_at": T0 + H, "source_event_id": "nl-d"})
        ev = self.events()[0]
        self.assertEqual((ev["family"], ev["provisional"]), ("REMOVE", 1))
        self.assertEqual(self.state("C04")["status"], "LIVE")


class TestSuspension(RadarTestCase):
    def ramp_items(self, disabled=(), hidden=()):
        return [rc.map_ramp_asset({"symbol": s, "chain": "ETHEREUM", "enabled": s not in disabled, "hidden": s in hidden},
                                  "EUR") for s in ("USDC", "USDT", "ETH", "LINK", "UNI", "AAVE")]

    def test_ramp_enabled_false_is_suspended_not_removed(self):
        rc.ingest_snapshot(self.conn, "ramp_assets", "EUR", self.ramp_items(), fetched_at=T0)
        for i in range(1, 6):
            rc.ingest_snapshot(self.conn, "ramp_assets", "EUR", self.ramp_items(disabled=("LINK",)), fetched_at=T0 + i * H)
        st = self.state("LINK", "ramp", "FIAT_ROUTE", "EUR", network="ethereum")
        self.assertEqual(st["status"], "SUSPENDED")
        evs = self.events()
        self.assertEqual(len(evs), 1)
        self.assertEqual((evs[0]["event_type"], evs[0]["to_status"]), ("FIAT_ROUTE_SUSPENDED", "SUSPENDED"))
        self.assertEqual(self.events(family="REMOVE"), [])
        # re-enabled -> RESUMED
        rc.ingest_snapshot(self.conn, "ramp_assets", "EUR", self.ramp_items(), fetched_at=T0 + 10 * H)
        self.assertEqual(self.events()[-1]["event_type"], "FIAT_ROUTE_RESUMED")

    def test_coinone_and_korbit_status_mapping(self):
        mk = lambda ts, ms=0: rc.map_coinone_market({"target_currency": "AAA", "quote_currency": "KRW",
                                                     "trade_status": ts, "maintenance_status": ms})
        self.assertEqual([mk(t)["status"] for t in (0, 1, 2, 3)], ["SUSPENDED", "LIVE", "SUSPENDED", "LIVE"])
        self.assertEqual(mk(1, 1)["status"], "SUSPENDED")
        self.assertEqual(rc.map_korbit_pair({"symbol": "btc_krw", "status": "stopped"})["status"], "SUSPENDED")
        self.assertEqual(rc.map_korbit_pair({"symbol": "btc_krw", "status": "launched"})["quote"], "KRW")
        pairs = lambda stop=(): [rc.map_korbit_pair({"symbol": f"{s.lower()}_krw",
                                                     "status": "stopped" if s in stop else "launched"}) for s in BASE]
        rc.ingest_snapshot(self.conn, "korbit_pairs", "KRW", pairs(), fetched_at=T0)
        rc.ingest_snapshot(self.conn, "korbit_pairs", "KRW", pairs(stop=("C09",)), fetched_at=T0 + H)
        self.assertEqual(self.events()[0]["event_type"], "SPOT_SUSPENDED")
        self.assertEqual(self.state("C09", "korbit")["status"], "SUSPENDED")


class TestCrossSourceMerge(RadarTestCase):
    def test_newlistings_upbit_notice_and_market_diff_merge_into_one_event(self):
        self.baseline_upbit()
        ta = T0 + 10 * H
        # 1) NewListings relays the Upbit notice (3s vendor delay): same independence group as upbit_notice
        r1 = rc.ingest_announcement(self.conn, "newlistings", {
            "action": "LISTING", "platform_id": "upbit", "symbol": "REZ", "quote": "KRW", "origin_group": "upbit_notice",
            "announced_at": ta, "source_detected_at": ta + 3000, "observed_at": ta + 3200,
            "source_event_id": "nl:upbit:REZ:LISTING:KRW"})
        ev = self.events()[0]
        self.assertEqual((ev["event_type"], ev["independent_source_count"], ev["provisional"]), ("SPOT_ANNOUNCED", 1, 1))
        self.assertEqual(self.state("REZ")["status"], "ANNOUNCED")
        # 2) the official Upbit notice: corroborates, still ONE independent group, provisional cleared
        r2 = rc.ingest_announcement(self.conn, "upbit_notice", {
            "action": "LISTING", "symbol": "REZ", "quote": "KRW", "announced_at": ta, "observed_at": ta + 800,
            "effective_at": ta + 2 * H, "source_event_id": "upbit:5101"})
        self.assertEqual(r2["events"], r1["events"])
        ev = self.events()[0]
        self.assertEqual((ev["independent_source_count"], ev["provisional"]), (1, 0))
        self.assertAlmostEqual(ev["confidence"], 0.85)
        self.assertEqual(ev["effective_at"], ta + 2 * H)
        # 3) the market appears in the structured market list: second independent group
        r3 = rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE + ["REZ"]), fetched_at=ta + 2 * H + 5000)
        self.assertEqual(r3["events"], r1["events"])
        evs = self.events()
        self.assertEqual(len(evs), 1)
        ev = evs[0]
        self.assertEqual((ev["event_type"], ev["from_status"], ev["to_status"]), ("SPOT_LISTED", "NONE", "LIVE"))
        self.assertEqual(ev["independent_source_count"], 2)
        self.assertAlmostEqual(ev["confidence"], 1 - 0.15 * 0.05, places=4)
        self.assertEqual(ev["announced_at"], ta)
        self.assertEqual(ev["source_detected_at"], ta + 3000)
        self.assertEqual(ev["live_observed_at"], ta + 2 * H + 5000)
        self.assertEqual(ev["anchor_at"], ta)
        roles = sorted(r["role"] for r in self.q("SELECT role FROM event_observation_link WHERE event_id=?", (ev["event_id"],)))
        self.assertEqual(roles, ["CORROBORATE", "ORIGIN", "PROGRESS"])
        self.assertEqual(self.state("REZ")["status"], "LIVE")

    def test_late_relay_after_live_corroborates_not_regresses(self):
        self.baseline_upbit()
        ta = T0 + 10 * H
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE + ["REZ"]), fetched_at=ta)
        rc.ingest_announcement(self.conn, "newlistings", {"action": "LISTING", "platform_id": "upbit", "symbol": "REZ",
                                                          "quote": "KRW", "origin_group": "upbit_notice",
                                                          "observed_at": ta + 60_000, "source_event_id": "nl-late"})
        evs = self.events()
        self.assertEqual(len(evs), 1)
        self.assertEqual((evs[0]["to_status"], evs[0]["independent_source_count"]), ("LIVE", 2))
        self.assertEqual(self.state("REZ")["status"], "LIVE")
        self.assertEqual(self.q("SELECT COUNT(*) n FROM rejected_transition")[0]["n"], 0)

    def test_wildcard_quote_announcement_binds_to_market(self):
        self.baseline_upbit()
        ta = T0 + 10 * H
        rc.ingest_announcement(self.conn, "upbit_notice", {"action": "LISTING", "symbol": "ZORA", "announced_at": ta,
                                                           "observed_at": ta + 500, "source_event_id": "u-z"})
        self.assertEqual(self.state("ZORA", quote="")["status"], "ANNOUNCED")
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE + ["ZORA"]), fetched_at=ta + H)
        evs = self.events()
        self.assertEqual(len(evs), 1)
        self.assertEqual((evs[0]["quote"], evs[0]["to_status"], evs[0]["independent_source_count"]), ("KRW", "LIVE", 2))
        self.assertEqual(self.state("ZORA", quote="")["status"], "LIVE")   # placeholder promoted

    def test_announcement_idempotent(self):
        self.baseline_upbit()
        a = {"action": "LISTING", "symbol": "DUP", "quote": "KRW", "observed_at": T0 + H, "source_event_id": "same"}
        rc.ingest_announcement(self.conn, "upbit_notice", a)
        r = rc.ingest_announcement(self.conn, "upbit_notice", dict(a, observed_at=T0 + 2 * H))
        self.assertTrue(r["duplicate"])
        self.assertEqual(len(self.q("SELECT * FROM source_observation")), 1)

    def test_outside_72h_window_is_a_new_episode(self):
        self.baseline_upbit()
        rc.ingest_announcement(self.conn, "upbit_notice", {"action": "LISTING", "symbol": "OLD", "quote": "KRW",
                                                           "observed_at": T0 + H, "source_event_id": "o1"})
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE + ["OLD"]), fetched_at=T0 + 100 * H)
        self.assertEqual(self.state("OLD")["status"], "LIVE")
        self.assertEqual(len(self.events()), 2)


class TestAnnouncementLifecycle(RadarTestCase):
    def test_announcement_only_then_live_on_market_diff(self):
        self.baseline_upbit()
        ta = T0 + 5 * H
        rc.ingest_announcement(self.conn, "upbit_notice", {"action": "LISTING", "symbol": "ANN", "quote": "KRW",
                                                           "announced_at": ta, "observed_at": ta + 700,
                                                           "effective_at": ta + 3 * H, "source_event_id": "a1"})
        self.assertEqual(self.state("ANN")["status"], "ANNOUNCED")
        self.assertEqual(self.events()[0]["event_type"], "SPOT_ANNOUNCED")
        # several snapshots without the market: still ANNOUNCED, no misses (never present in snapshot)
        for i in range(1, 4):
            rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE), fetched_at=ta + i * 600_000)
        self.assertEqual(self.state("ANN")["status"], "ANNOUNCED")
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE + ["ANN"]), fetched_at=ta + 3 * H + 2000)
        self.assertEqual(self.state("ANN")["status"], "LIVE")
        evs = self.events()
        self.assertEqual(len(evs), 1)
        self.assertEqual((evs[0]["event_type"], evs[0]["to_status"]), ("SPOT_LISTED", "LIVE"))
        trans = [(t["from_status"], t["to_status"]) for t in
                 self.q("SELECT * FROM access_transition WHERE access_id=? ORDER BY transition_id",
                        (self.state("ANN")["access_id"],))]
        self.assertEqual(trans, [("NONE", "ANNOUNCED"), ("ANNOUNCED", "LIVE")])

    def test_provisional_snapshot_source_confirm_and_retract(self):
        rc.ingest_snapshot(self.conn, "aggr_snap", "all", upbit_items(BASE), fetched_at=T0)
        rc.ingest_snapshot(self.conn, "aggr_snap", "all", upbit_items(BASE + ["P1", "P2"]), fetched_at=T0 + 60_000)
        self.assertEqual([e["provisional"] for e in self.events()], [1, 1])
        rc.ingest_snapshot(self.conn, "aggr_snap", "all", upbit_items(BASE + ["P1"]), fetched_at=T0 + 120_000)
        e1, e2 = self.events()
        self.assertEqual((e1["provisional"], e1["retracted"]), (0, 0))   # P1 confirmed on 2nd observation
        self.assertEqual(e2["retracted"], 1)                              # P2 vanished before confirmation
        self.assertEqual(self.state("P1")["status"], "LIVE")
        self.assertEqual(self.state("P2")["status"], "NONE")

    def test_fiat_tier_upgrade_event_and_silent_downgrade(self):
        item = lambda tier: [rc.map_ramp_asset({"symbol": s, "chain": "ETHEREUM"}, "EUR") for s in ("A", "B", "C", "D")] + \
            [dict(rc.map_ramp_asset({"symbol": "USDC", "chain": "SOLANA"}, "EUR"), fiat_tier=tier)]
        rc.ingest_snapshot(self.conn, "ramp_assets", "EUR", item("SUPPORTED"), fetched_at=T0)
        rc.ingest_snapshot(self.conn, "ramp_assets", "EUR", item("QUOTABLE"), fetched_at=T0 + H)
        evs = self.events()
        self.assertEqual((len(evs), evs[0]["family"], evs[0]["event_type"]), (1, "TIER", "FIAT_ROUTE_QUOTABLE"))
        rc.ingest_snapshot(self.conn, "ramp_assets", "EUR", item("SUPPORTED"), fetched_at=T0 + 2 * H)
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.state("USDC", "ramp", "FIAT_ROUTE", "EUR", network="solana")["fiat_tier"], "SUPPORTED")


class TestWildcardQuote(RadarTestCase):
    """Quote-less DELISTING / SUSPEND / RESUME apply to every existing market of the asset on that platform."""
    def setUp(self):
        super().setUp()
        self.baseline_upbit()                                                            # KRW: C00..C19
        for quote, syms in (("BTC", BASE[:10]), ("USDT", BASE[:5])):                     # BTC: C00..C09, USDT: C00..C04
            r = rc.ingest_snapshot(self.conn, "upbit_market", quote, upbit_items(syms, quote), fetched_at=T0)
            self.assertEqual(r["outcome"], "BASELINE")

    def ann(self, source="upbit_notice", **kw):
        kw.setdefault("observed_at", T0 + H)
        kw.setdefault("platform_id", "upbit")
        return rc.ingest_announcement(self.conn, source, kw)

    def rows(self, sym):
        return {r["quote"]: r for r in self.q("SELECT * FROM access_state WHERE asset_key=?", (f"sym:{sym}",))}

    def rejected(self):
        return self.q("SELECT * FROM rejected_transition")

    def test_delisting_without_quote_removes_every_quote_one_event_each(self):
        r = self.ann(action="DELISTING", symbol="C01", source_event_id="d-all")
        rows = self.rows("C01")
        self.assertEqual(set(rows), {"KRW", "BTC", "USDT"})                              # no '' row, no NONE rows
        self.assertTrue(all(x["status"] == "REMOVED" for x in rows.values()))
        evs = self.events(family="REMOVE")
        self.assertEqual(sorted(e["quote"] for e in evs), ["BTC", "KRW", "USDT"])
        self.assertEqual({e["event_type"] for e in evs}, {"SPOT_DELISTED"})
        self.assertEqual(sorted(r["events"]), [e["event_id"] for e in evs])
        self.assertEqual(r["wildcard"], [{"asset_key": "sym:C01", "platform_id": "upbit", "access_kind": "SPOT",
                                          "quotes": ["BTC", "KRW", "USDT"]}])
        self.assertEqual(r["rejected"], 0)
        self.assertEqual(self.rejected(), [])
        obs = self.q("SELECT * FROM source_observation WHERE source_event_id='d-all'")
        self.assertEqual(len(obs), 1)                                                    # one per target, as reported
        self.assertEqual((obs[0]["quote"], obs[0]["access_id"]), ("", None))
        links = self.q("SELECT event_id, role FROM event_observation_link WHERE obs_id=?", (obs[0]["obs_id"],))
        self.assertEqual(sorted(l["event_id"] for l in links), [e["event_id"] for e in evs])
        self.assertEqual({l["role"] for l in links}, {"ORIGIN"})
        tr = self.q("SELECT access_id FROM access_transition WHERE obs_id=?", (obs[0]["obs_id"],))
        self.assertEqual(sorted(t["access_id"] for t in tr), sorted(x["access_id"] for x in rows.values()))
        # resolving the notice's ref propagates to every quote the wildcard covered
        ref = self.q("SELECT ref_id FROM source_asset_ref WHERE source_id='upbit_notice' AND platform_symbol='C01'")[0]
        aid = rc.upsert_asset(self.conn, "crypto:test:c01", "CRYPTO", "C01", at=T0)
        self.conn.execute("UPDATE access_state SET asset_id=NULL")
        rc.resolve_ref(self.conn, ref["ref_id"], aid, at=T0 + H)
        self.assertEqual({x["asset_id"] for x in self.rows("C01").values()}, {aid})
        self.assertIsNone(self.rows("C02")["KRW"]["asset_id"])
        # same notice relayed by a third party (another independence group), still quote-less: corroborates each
        r2 = self.ann(source="newlistings", action="DELISTING", symbol="C01", source_event_id="nl-d-all",
                      observed_at=T0 + H + 5000)
        self.assertEqual(r2["rejected"], 0)
        self.assertEqual(len(self.events(family="REMOVE")), 3)
        self.assertEqual({e["independent_source_count"] for e in self.events(family="REMOVE")}, {2})
        # a concrete-quote message merges only into that quote's episode
        r3 = self.ann(source="newlistings", action="DELISTING", symbol="C01", quote="BTC", source_event_id="nl-btc",
                      observed_at=T0 + H + 9000)
        btc = [e for e in self.events(family="REMOVE") if e["quote"] == "BTC"][0]
        self.assertEqual(r3["events"], [btc["event_id"]])
        self.assertEqual(self.rejected(), [])

    def test_only_legal_rows_change_and_no_rejection_noise(self):
        self.ann(action="SUSPEND", symbol="C07", quote="BTC", source_event_id="s-btc")       # BTC already suspended
        self.ann(action="DELISTING", symbol="C02", quote="BTC", source_event_id="d-btc")     # BTC already removed
        n_ev = len(self.events())
        r = self.ann(action="SUSPEND", symbol="C07", source_event_id="s-all", observed_at=T0 + 2 * H)
        rows = self.rows("C07")
        self.assertEqual(set(rows), {"KRW", "BTC"})                                       # no USDT row invented
        self.assertEqual((rows["KRW"]["status"], rows["BTC"]["status"]), ("SUSPENDED", "SUSPENDED"))
        self.assertEqual(len(self.events()), n_ev + 1)                                    # only KRW is new
        btc_ev = self.events(quote="BTC", family="SUSPEND")[0]
        self.assertIn(btc_ev["event_id"], r["events"])                                    # BTC: corroboration
        r = self.ann(action="SUSPEND", symbol="C02", source_event_id="s2-all", observed_at=T0 + 2 * H)
        rows = self.rows("C02")
        self.assertEqual((rows["KRW"]["status"], rows["BTC"]["status"], rows["USDT"]["status"]),
                         ("SUSPENDED", "REMOVED", "SUSPENDED"))
        self.assertEqual(r["rejected"], 0)
        r = self.ann(action="RESUME", symbol="C07", source_event_id="r-all", observed_at=T0 + 3 * H)
        self.assertEqual({x["status"] for x in self.rows("C07").values()}, {"LIVE"})
        self.assertEqual(sorted(e["quote"] for e in self.events(family="RESUME")), ["BTC", "KRW"])
        r = self.ann(action="RESUME", symbol="C08", source_event_id="r-noop", observed_at=T0 + 3 * H)
        self.assertEqual((r["events"], r["rejected"]), ([], 0))                           # already LIVE everywhere
        self.assertEqual(self.rejected(), [])
        reasons = {t["reason"] for t in self.q("SELECT reason FROM access_transition WHERE reason LIKE '%wildcard%'")}
        self.assertEqual(reasons, {"official suspension notice (quote wildcard)", "official resume notice (quote wildcard)"})

    def test_no_existing_state_behaves_as_single_quoteless_target(self):
        r = self.ann(action="DELISTING", symbol="GHOST", source_event_id="g1")
        self.assertEqual(r["rejected"], 1)                                                # NONE -> REMOVED, as before
        self.assertEqual(r["wildcard"], [])
        self.assertEqual(list(self.rows("GHOST")), [""])                                  # one row, not one per quote
        self.assertEqual(len(self.rejected()), 1)
        r = self.ann(action="SUSPEND", symbol="GHOST2", source_event_id="g2")
        self.assertEqual((r["events"], r["rejected"]), ([], 0))
        self.assertEqual(list(self.rows("GHOST2")), [""])
        # stale NONE rows (e.g. from old default-quote expansion) are not treated as markets
        self.ann(action="DELISTING", symbol="GHOST3", quote="KRW", source_event_id="g3-krw")
        self.assertEqual(self.rows("GHOST3")["KRW"]["status"], "NONE")
        r = self.ann(action="DELISTING", symbol="GHOST3", source_event_id="g3-all")
        self.assertEqual(r["wildcard"], [])
        self.assertEqual(set(self.rows("GHOST3")), {"KRW", ""})
        self.assertEqual(self.events(), [])

    def test_scheduled_wildcard_delisting_tick_and_snapshot(self):
        eff = T0 + 2 * 24 * H
        r = self.ann(action="DELISTING", symbol="C03", effective_at=eff, source_event_id="sched")
        evs = self.events(family="REMOVE")
        self.assertEqual(sorted(e["quote"] for e in evs), ["BTC", "KRW", "USDT"])
        self.assertEqual({e["event_type"] for e in evs}, {"SPOT_DELISTED_SCHEDULED"})
        rows = self.rows("C03")
        self.assertEqual({x["status"] for x in rows.values()}, {"LIVE"})
        self.assertEqual({x["pending_removal_at"] for x in rows.values()}, {eff})
        self.assertEqual(rc.process_due(self.conn, at=eff - 1), [])
        # after effective_at the KRW snapshot miss removes KRW and merges into the KRW episode ...
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items([s for s in BASE if s != "C03"]),
                           fetched_at=eff + 60_000)
        self.assertEqual(self.rows("C03")["KRW"]["status"], "REMOVED")
        # ... and tick removes the other quotes, still one episode per quote
        done = rc.process_due(self.conn, at=eff + 120_000)
        self.assertEqual(len(done), 2)
        self.assertEqual({x["status"] for x in self.rows("C03").values()}, {"REMOVED"})
        evs = self.events(family="REMOVE")
        self.assertEqual(len(evs), 3)
        self.assertEqual({e["event_type"] for e in evs}, {"SPOT_DELISTED"})
        self.assertEqual(sorted(done + [e["event_id"] for e in evs if e["quote"] == "KRW"]), sorted(r["events"]))
        self.assertEqual(self.rejected(), [])

    def test_quoteless_placeholder_is_included(self):
        ta = T0 + 10 * H
        self.ann(action="LISTING", symbol="ZORA", announced_at=ta, observed_at=ta, source_event_id="z-l")
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE + ["ZORA"]), fetched_at=ta + H)
        self.assertEqual({q: x["status"] for q, x in self.rows("ZORA").items()}, {"": "LIVE", "KRW": "LIVE"})
        r = self.ann(action="DELISTING", symbol="ZORA", observed_at=ta + 200 * H, source_event_id="z-d")
        self.assertEqual({q: x["status"] for q, x in self.rows("ZORA").items()}, {"": "REMOVED", "KRW": "REMOVED"})
        evs = self.events(family="REMOVE")
        self.assertEqual([e["quote"] for e in evs], ["KRW"])                              # placeholder follows KRW
        self.assertEqual(r["events"], [evs[0]["event_id"]])
        # announced but never traded, then delisted without quote -> announcement cancelled on the placeholder
        self.ann(action="LISTING", symbol="NOPE", observed_at=ta, source_event_id="n-l")
        self.ann(action="DELISTING", symbol="NOPE", observed_at=ta + H, source_event_id="n-d")
        ev = self.events(asset_key="sym:NOPE", family="REMOVE")[0]
        self.assertEqual((ev["quote"], ev["event_type"]), ("", "SPOT_ANNOUNCEMENT_CANCELLED"))
        self.assertEqual(self.rejected(), [])

    def test_third_party_wildcard_delisting_is_provisional_per_quote(self):
        self.ann(source="newlistings", action="DELISTING", symbol="C04", source_event_id="nl-c04")
        evs = self.events(family="REMOVE")
        self.assertEqual(sorted(e["quote"] for e in evs), ["BTC", "KRW", "USDT"])
        self.assertEqual({e["provisional"] for e in evs}, {1})
        rows = self.rows("C04")
        self.assertEqual({x["status"] for x in rows.values()}, {"LIVE"})
        self.assertEqual({x["pending_removal_at"] for x in rows.values()}, {None})


OLD_FEED_COLUMNS = ["event_id", "anchor_at", "event_type", "platform_id", "asset_key", "quote", "from_status",
                    "to_status", "fiat_tier", "confidence", "independent_source_count", "provisional", "retracted",
                    "announced_at", "source_detected_at", "observed_at", "effective_at", "live_observed_at",
                    "poll_prev_at", "asset_id", "asset_symbol", "asset_type", "obs_count"]
NEW_FEED_COLUMNS = ["access_id", "access_kind", "family", "group_key", "first_source_id", "updated_at", "network",
                    "country", "fiat", "payment_method", "current_status", "pending_removal_at", "g_asset_key",
                    "asset_name", "ref_id", "ref_source_id", "platform_symbol", "native_id", "resolution_status",
                    "resolution_source", "suggested_asset_id", "url"]
OLD_VIEW = """CREATE VIEW v_recent_feed AS
SELECT e.event_id, e.anchor_at, e.event_type, e.platform_id, e.asset_key, e.quote,
       e.from_status, e.to_status, e.fiat_tier, e.confidence, e.independent_source_count,
       e.provisional, e.retracted, e.announced_at, e.source_detected_at, e.observed_at,
       e.effective_at, e.live_observed_at, e.poll_prev_at, a.asset_id, a.symbol AS asset_symbol,
       a.asset_type, (SELECT COUNT(*) FROM event_observation_link l WHERE l.event_id = e.event_id) AS obs_count
FROM access_event e LEFT JOIN access_state s ON s.access_id = e.access_id LEFT JOIN asset a ON a.asset_id = s.asset_id"""


class TestGroupUrlFeedMigration(RadarTestCase):
    def setUp(self):
        super().setUp()
        self.baseline_upbit()
        rc.ingest_snapshot(self.conn, "upbit_market", "BTC", upbit_items(BASE[:10], "BTC"), fetched_at=T0)

    def ann(self, **kw):
        kw.setdefault("observed_at", T0 + H)
        kw.setdefault("platform_id", "upbit")
        return rc.ingest_announcement(self.conn, kw.pop("source", "upbit_notice"), kw)

    def feed(self):
        return {(r["asset_key"], r["quote"], r["family"]): r for r in self.q("SELECT * FROM v_recent_feed")}

    def test_feed_view_columns(self):
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(v_recent_feed)")]
        self.assertEqual(cols, OLD_FEED_COLUMNS + NEW_FEED_COLUMNS)                    # old columns first, unchanged
        self.assertTrue(self.q("SELECT name FROM sqlite_master WHERE name='ix_event_group'"))

    def test_group_key_semantics(self):
        r = self.ann(action="DELISTING", symbol="C01", source_event_id="d-all", url="https://upbit.com/n/1")
        r2 = self.ann(action="LISTING", source_event_id="l-2",
                      targets=[{"symbol": s, "quote": q} for s in ("NEWA", "NEWB") for q in ("KRW", "BTC")])
        f = self.feed()
        g = "ann:upbit_notice:d-all:sym:C01"
        self.assertEqual({f[("sym:C01", q, "REMOVE")]["group_key"] for q in ("KRW", "BTC")}, {g})
        self.assertEqual(len(r["events"]), 2)
        self.assertEqual({f[("sym:NEWA", q, "ADD")]["group_key"] for q in ("KRW", "BTC")},
                         {"ann:upbit_notice:l-2:sym:NEWA"})
        self.assertEqual(f[("sym:NEWB", "KRW", "ADD")]["group_key"], "ann:upbit_notice:l-2:sym:NEWB")   # per asset
        self.assertEqual(len(r2["events"]), 4)
        # snapshot-born event: its own id; a later corroborating announcement does not regroup it
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE + ["SNAP1"]), fetched_at=T0 + 2 * H)
        ev = self.feed()[("sym:SNAP1", "KRW", "ADD")]
        self.assertEqual(ev["group_key"], f"ev:{ev['event_id']}")
        self.ann(action="LISTING", symbol="SNAP1", quote="KRW", source_event_id="l-snap", observed_at=T0 + 2 * H + 1)
        self.assertEqual(self.feed()[("sym:SNAP1", "KRW", "ADD")]["group_key"], f"ev:{ev['event_id']}")
        self.assertEqual(self.q("SELECT COUNT(*) n FROM access_event WHERE group_key IS NULL")[0]["n"], 0)

    def test_url_on_observations_and_feed(self):
        self.ann(action="SUSPEND", symbol="C02", source_event_id="s1", url="https://upbit.com/service_center/notice?id=1")
        self.ann(action="DELISTING", source_event_id="d2", pc_url="https://pc/2",
                 targets=[{"symbol": "C03"}, {"symbol": "C04", "quote": "KRW", "url": "https://own/4"}])
        obs = {(o["asset_key"], o["source_event_id"]): o["url"] for o in self.q("SELECT * FROM source_observation")}
        self.assertEqual(obs[("sym:C02", "s1")], "https://upbit.com/service_center/notice?id=1")
        self.assertEqual(obs[("sym:C03", "d2")], "https://pc/2")                         # pc_url also accepted
        self.assertEqual(obs[("sym:C04", "d2")], "https://own/4")                        # per-target url wins
        f = self.feed()
        self.assertEqual({f[("sym:C02", q, "SUSPEND")]["url"] for q in ("KRW", "BTC")},
                         {"https://upbit.com/service_center/notice?id=1"})
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", upbit_items(BASE + ["U2"]), fetched_at=T0 + 3 * H)
        self.assertIsNone(self.feed()[("sym:U2", "KRW", "ADD")]["url"])                  # snapshot only -> NULL
        self.assertEqual(self.q("""SELECT COUNT(*) n FROM source_observation
                                   WHERE obs_kind<>'ANNOUNCEMENT' AND url IS NOT NULL""")[0]["n"], 0)
        # the announcement link becomes the event's url once the notice corroborates the snapshot event
        self.ann(action="LISTING", symbol="U2", quote="KRW", source_event_id="l-u2", observed_at=T0 + 3 * H + 1,
                 url="https://upbit.com/n/u2")
        self.assertEqual(self.feed()[("sym:U2", "KRW", "ADD")]["url"], "https://upbit.com/n/u2")

    def test_feed_ref_and_dimensions(self):
        self.ann(action="SUSPEND", symbol="C05", quote="KRW", source_event_id="s5")
        rc.register_source(self.conn, "upbit_wallet", origin_platform_id="upbit", at=T0)
        dep = {"symbol": "ETH", "access_kind": "DEPOSIT_NETWORK", "network": "ethereum"}
        rc.ingest_snapshot(self.conn, "upbit_wallet", "DEP", [dep], fetched_at=T0)
        rc.ingest_snapshot(self.conn, "upbit_wallet", "DEP", [dict(dep, status="SUSPENDED")], fetched_at=T0 + H)
        f = self.feed()
        e = f[("sym:C05", "KRW", "SUSPEND")]
        self.assertEqual((e["access_kind"], e["platform_symbol"], e["resolution_status"], e["current_status"]),
                         ("SPOT", "C05", "UNRESOLVED", "SUSPENDED"))
        d = f[("sym:ETH", "", "SUSPEND")]
        self.assertEqual((d["access_kind"], d["network"], d["event_type"]),
                         ("DEPOSIT_NETWORK", "ethereum", "DEPOSIT_SUSPENDED"))
        # resolution shows through the best ref (notice ref CONFIRMED) although the state's ref is the market's
        ref = self.q("SELECT ref_id FROM source_asset_ref WHERE source_id='upbit_notice' AND platform_symbol='C05'")[0]
        aid = rc.upsert_asset(self.conn, "crypto:test:c05", "CRYPTO", "C05", name="Five", at=T0)
        rc.resolve_ref(self.conn, ref["ref_id"], aid, at=T0 + 2 * H)
        e = self.feed()[("sym:C05", "KRW", "SUSPEND")]
        self.assertEqual((e["resolution_status"], e["ref_id"], e["asset_id"], e["asset_name"]),
                         ("CONFIRMED", ref["ref_id"], aid, "Five"))

    def test_migration_of_old_db(self):
        fd, path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        try:
            c = rc.init_db(path)
            rc.register_platform(c, "upbit", "upbit", "CEX", at=T0)
            rc.register_source(c, "upbit_market", origin_platform_id="upbit", at=T0)
            rc.register_source(c, "upbit_notice", kind="ANNOUNCEMENT", tier="OFFICIAL_ANNOUNCEMENT",
                               origin_platform_id="upbit", at=T0)
            rc.ingest_snapshot(c, "upbit_market", "KRW", upbit_items(BASE), fetched_at=T0)
            rc.ingest_snapshot(c, "upbit_market", "KRW", upbit_items(BASE + ["M1"]), fetched_at=T0 + H)
            rc.ingest_announcement(c, "upbit_notice", {"action": "DELISTING", "platform_id": "upbit", "symbol": "C01",
                                                       "observed_at": T0 + H, "source_event_id": "old-1"})
            # turn it into a v0.1 db: no group_key / url columns, old view, no index
            c.executescript("DROP VIEW v_recent_feed; DROP INDEX ix_event_group;"
                            "ALTER TABLE access_event DROP COLUMN group_key;"
                            "ALTER TABLE source_observation DROP COLUMN url;" + OLD_VIEW + ";")
            self.assertNotIn("group_key", {r[1] for r in c.execute("PRAGMA table_info(access_event)")})
            c.close()
            c = rc.init_db(path)                                                         # migrate
            self.assertIn("url", {r[1] for r in c.execute("PRAGMA table_info(source_observation)")})
            self.assertEqual([r[1] for r in c.execute("PRAGMA table_info(v_recent_feed)")],
                             OLD_FEED_COLUMNS + NEW_FEED_COLUMNS)
            self.assertTrue(c.execute("SELECT 1 FROM sqlite_master WHERE name='ix_event_group'").fetchone())
            rows = {r["asset_key"]: r for r in c.execute("SELECT * FROM v_recent_feed")}
            self.assertEqual(rows["sym:C01"]["group_key"], "ann:upbit_notice:old-1:sym:C01")   # backfilled
            self.assertEqual(rows["sym:M1"]["group_key"], f"ev:{rows['sym:M1']['event_id']}")
            self.assertIsNone(rows["sym:C01"]["url"])
            c.close()
            c = rc.init_db(path)                                                         # idempotent
            self.assertEqual(c.execute("SELECT COUNT(*) FROM access_event WHERE group_key IS NULL").fetchone()[0], 0)
            c.close()
        finally:
            for ext in ("", "-wal", "-shm"):
                if os.path.exists(path + ext):
                    os.remove(path + ext)

    def test_db_path_env(self):
        old = {k: os.environ.pop(k, None) for k in ("ACCESS_DB", "ACCESS_RADAR_DB")}
        cwd = os.getcwd()
        try:
            os.chdir(tempfile.gettempdir())
            here = os.path.dirname(os.path.abspath(rc.__file__))
            self.assertEqual(rc.default_db_path(), os.path.join(here, "access.sqlite"))   # not cwd-relative
            os.environ["ACCESS_RADAR_DB"] = "/x/legacy.sqlite"
            self.assertEqual(rc.default_db_path(), "/x/legacy.sqlite")                    # legacy fallback
            os.environ["ACCESS_DB"] = "/x/new.sqlite"
            self.assertEqual(rc.default_db_path(), "/x/new.sqlite")                       # ACCESS_DB wins
        finally:
            os.chdir(cwd)
            for k, v in old.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


class TestStateMachine(RadarTestCase):
    def test_illegal_transitions_rejected_and_logged(self):
        self.baseline_upbit()
        acc = self.state("C00")
        rc.apply_transition(self.conn, acc["access_id"], "REMOVED", "upbit_market", at=T0 + H)
        with self.assertRaises(rc.IllegalTransition):
            rc.apply_transition(self.conn, acc["access_id"], "SUSPENDED", "upbit_market", at=T0 + 2 * H)
        self.assertEqual(self.state("C00")["status"], "REMOVED")
        rej = self.q("SELECT * FROM rejected_transition")
        self.assertEqual((rej[0]["from_status"], rej[0]["to_status"]), ("REMOVED", "SUSPENDED"))
        # LIVE -> ANNOUNCED (listing notice for a market listed long ago, no episode in window) is rejected
        r = rc.ingest_announcement(self.conn, "upbit_notice", {"action": "LISTING", "symbol": "C01", "quote": "KRW",
                                                               "observed_at": T0 + 200 * H, "source_event_id": "x"})
        self.assertEqual(r["rejected"], 1)
        self.assertEqual(self.state("C01")["status"], "LIVE")
        # DELISTING for something never seen: NONE -> REMOVED rejected
        r = rc.ingest_announcement(self.conn, "upbit_notice", {"action": "DELISTING", "symbol": "GHOST", "quote": "KRW",
                                                               "observed_at": T0 + 200 * H, "source_event_id": "y"})
        self.assertEqual(r["rejected"], 1)
        self.assertEqual(len(self.q("SELECT * FROM rejected_transition")), 3)

    def test_transition_table_and_event_type_derivation(self):
        allowed = rc.ALLOWED_TRANSITIONS
        self.assertNotIn(("LIVE", "ANNOUNCED"), allowed)
        self.assertNotIn(("NONE", "REMOVED"), allowed)
        self.assertIn(("SUSPENDED", "LIVE"), allowed)
        d = rc.derive_event_type
        self.assertEqual(d("SPOT", "NONE", "LIVE"), "SPOT_LISTED")
        self.assertEqual(d("PERP", "NONE", "ANNOUNCED"), "PERP_ANNOUNCED")
        self.assertEqual(d("CHAIN_DEPLOYMENT", "NONE", "LIVE"), "CHAIN_DEPLOYED")
        self.assertEqual(d("DEPOSIT_NETWORK", "LIVE", "SUSPENDED"), "DEPOSIT_SUSPENDED")
        self.assertEqual(d("WITHDRAW_NETWORK", "SUSPENDED", "LIVE"), "WITHDRAW_RESUMED")
        self.assertEqual(d("SPOT", "REMOVED", "LIVE"), "SPOT_RELISTED")
        self.assertEqual(d("SPOT", "ANNOUNCED", "REMOVED"), "SPOT_ANNOUNCEMENT_CANCELLED")
        self.assertEqual(d("CATALOG", "NONE", "LIVE"), "CATALOG_ADDED")
        self.assertEqual(d("FIAT_ROUTE", "NONE", "LIVE", "CONFIRMED"), "FIAT_ROUTE_CONFIRMED")
        self.assertEqual(d("SPOT", "NONE", "SUSPENDED"), "SPOT_LISTED_SUSPENDED")


class TestMisc(RadarTestCase):
    def test_resolution_by_contract_and_manual(self):
        aid = rc.upsert_asset(self.conn, "crypto:ethereum:0xabc", "CRYPTO", "ABC", issuer="")
        rc.add_deployment(self.conn, aid, "Ethereum", "0xABC")
        rc.register_source(self.conn, "upbit_market", origin_platform_id="upbit")
        items = upbit_items(BASE) + [dict(upbit_items(["ABC"])[0], chain="ethereum", contract="0xAbC")]
        rc.ingest_snapshot(self.conn, "upbit_market", "KRW", items, fetched_at=T0)
        self.assertEqual(self.state("ABC")["asset_id"], aid)
        ref = self.q("SELECT * FROM source_asset_ref WHERE platform_symbol='C01'")[0]
        self.assertEqual(ref["resolution_status"], "UNRESOLVED")
        aid2 = rc.upsert_asset(self.conn, "crypto:x:c01", "CRYPTO", "C01")
        rc.resolve_ref(self.conn, ref["ref_id"], aid2, resolution_source="manual")
        self.assertEqual(self.state("C01")["asset_id"], aid2)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO asset(asset_key, asset_type, symbol, created_at) VALUES ('k','BOND','K',1)")

    def test_parse_since_and_cli_feed(self):
        self.assertEqual(rc.parse_since("24h"), 24 * H)
        self.assertEqual(rc.parse_since("90m"), 90 * 60_000)
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "demo.sqlite")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rc.main(["--db", db, "init"]), 0)
            conn = rc.connect(db)
            rc.run_demo(conn)
            buf = io.StringIO()
            evs = rc.print_feed(conn, "24h", out=buf)
            self.assertIn("SPOT_LISTED", buf.getvalue())
            self.assertIn("UTC+8", buf.getvalue())
            self.assertTrue(any(e["event_type"] == "SPOT_LISTED" and e["independent_source_count"] == 2 for e in evs))
            self.assertFalse(any(e["family"] == "REMOVE" and e["event_type"] == "SPOT_DELISTED" for e in
                                 [dict(r) for r in conn.execute("SELECT * FROM access_event")]))
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
