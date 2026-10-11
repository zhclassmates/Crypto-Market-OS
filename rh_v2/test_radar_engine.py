#!/usr/bin/env python3
"""Radar engine 单测（Spec §1–39）。不联网；集成部分用临时 market / radar 库。"""
import json
import os
import sqlite3
import tempfile
import unittest

import radar_config as C
import radar_db
import radar_engine as E

DAY = C.DAY_SEC
NOW = 1791191191                      # 2026-10-05 07:06:31 UTC
D = E.latest_finalized_day(NOW)       # 2026-10-04 00:00 UTC


def snap(**kw):
    base = {
        "price": "1.0", "price_updated_at": NOW - 60,
        "liquidity": 80_000.0, "liquidity_updated_at": NOW - 60, "liquidity_source": "trending",
        "security_is_honeypot": 0, "security_updated_at": NOW - 600, "halt": None,
    }
    base.update(kw)
    return base


def bar(ts, vol=100.0, high=1.0, close=1.0, fetched=None, finalized=None):
    return {"ts": ts, "high": str(high), "close": str(close), "volume": None if vol is None else str(vol),
            "fetched_at": fetched if fetched is not None else ts + DAY + 60, "finalized_at": finalized}


def series(days, vol=100.0, high=1.0, latest_vol=None, latest_high=None):
    """D-(days-1) .. D，每根都已被观测定稿。"""
    rows = [bar(D - i * DAY, vol=vol, high=high) for i in range(days - 1, 0, -1)]
    rows.append(bar(D, vol=latest_vol if latest_vol is not None else vol,
                    high=latest_high if latest_high is not None else high))
    return rows


def sig(**kw):
    base = {"volume_ratio": None, "buy_share": None, "holder_growth": None, "liquidity_growth": None,
            "cross_list_count_60m": None, "breakout_10d": None, "near_breakout_10d": None}
    base.update(kw)
    return base


# ------------------------------------------------------------------ 时间基准
class FinalizedTests(unittest.TestCase):
    def test_latest_finalized_day_is_utc_yesterday(self):
        self.assertEqual(E.day_key(D), "2026-10-04")

    def test_open_day_never_enters_history(self):
        today = D + DAY
        bars = E.finalized_bars([bar(today, fetched=NOW)], NOW, None)
        self.assertEqual(bars, {})

    def test_unproven_or_future_observation_is_not_finalized(self):
        rows = [bar(D, fetched=D + 100), bar(D - DAY, fetched=NOW + 999)]
        self.assertEqual(E.finalized_bars(rows, NOW, None), {})

    def test_finalized_at_alone_proves_close(self):
        rows = [dict(bar(D), fetched_at=None, finalized_at=D + DAY + 5)]
        self.assertIn(D, E.finalized_bars(rows, NOW, None))


# ------------------------------------------------------------------ FAST GATE
class GateTests(unittest.TestCase):
    def test_pass_normal(self):
        g, low, _ = E.fast_gate(snap(), NOW)
        self.assertEqual((g, low), ("PASS", False))

    def test_pass_low_liquidity(self):
        g, low, reasons = E.fast_gate(snap(liquidity=20_000.0), NOW)
        self.assertEqual((g, low), ("PASS", True))
        self.assertIn("low_liquidity", [r["code"] for r in reasons])

    def test_boundaries(self):
        self.assertEqual(E.fast_gate(snap(liquidity=10_000.0), NOW)[:2], ("PASS", True))
        self.assertEqual(E.fast_gate(snap(liquidity=50_000.0), NOW)[:2], ("PASS", False))
        self.assertEqual(E.fast_gate(snap(liquidity=9_999.0), NOW)[0], "REJECT")

    def test_reject_on_explicit_untradeable(self):
        self.assertEqual(E.fast_gate(snap(security_is_honeypot=1), NOW)[0], "REJECT")
        self.assertEqual(E.fast_gate(snap(halt=1), NOW)[0], "REJECT")

    def test_missing_data_is_unknown_not_reject(self):
        self.assertEqual(E.fast_gate(snap(liquidity=None), NOW)[0], "UNKNOWN")
        self.assertEqual(E.fast_gate(snap(price=None), NOW)[0], "UNKNOWN")
        old = NOW - C.GATE_MAX_INPUT_AGE_SEC - 1
        self.assertEqual(E.fast_gate(snap(liquidity=1.0, liquidity_updated_at=old), NOW)[0], "UNKNOWN")

    def test_missing_security_does_not_reject(self):
        g, _, reasons = E.fast_gate(snap(security_updated_at=None, security_is_honeypot=None), NOW)
        self.assertEqual(g, "PASS")
        self.assertIn("security_missing", [r["code"] for r in reasons])


# ------------------------------------------------------------------ signals
class SignalTests(unittest.TestCase):
    def test_volume_ratio_median_of_seven(self):
        bars = E.finalized_bars(series(8, vol=100.0, latest_vol=350.0), NOW, None)
        v, ev = E.volume_ratio(bars, D)
        self.assertAlmostEqual(v, 3.5)
        self.assertEqual(ev["baseline_median"], 100.0)

    def test_volume_ratio_unknown_when_baseline_short(self):
        bars = E.finalized_bars(series(7), NOW, None)
        self.assertIsNone(E.volume_ratio(bars, D)[0])

    def test_volume_ratio_never_uses_token_own_last_candle(self):
        # 最后一根是 D-1，不是统一 D → null，而不是拿 D-1 当最新
        rows = [bar(D - i * DAY) for i in range(8, 0, -1)]
        self.assertIsNone(E.volume_ratio(E.finalized_bars(rows, NOW, None), D)[0])

    def test_buy_share(self):
        self.assertAlmostEqual(E.buy_share(65.0, 35.0)[0], 0.65)
        self.assertIsNone(E.buy_share(None, 10.0)[0])
        self.assertIsNone(E.buy_share(0.0, 0.0)[0])

    def test_growth_ignores_bucket_tag(self):
        self.assertAlmostEqual(E.growth([(200, 110.0, 2), (100, 100.0, 1)])[0], 0.10)

    def test_growth_last_two_snapshots(self):
        g, ev = E.growth([(200, 110.0), (100, 100.0)])
        self.assertAlmostEqual(g, 0.10)
        self.assertEqual(ev["span_sec"], 100)
        self.assertIsNone(E.growth([(200, 110.0)])[0])
        self.assertIsNone(E.growth([])[0])

    def test_cross_list_dedups_sources_and_unknown_when_unreliable(self):
        self.assertEqual(E.cross_list_count({"hot": 1, "trending": 2}, True, {})[0], 2)
        self.assertEqual(E.cross_list_count({}, True, {})[0], 0)
        self.assertIsNone(E.cross_list_count({"hot": 1}, False, {})[0])

    def test_breakout_confirmed_near_and_unknown(self):
        bars = E.finalized_bars(series(10, high=2.0), NOW, None)
        bk, near, dist, _ = E.breakout_10d(bars, D, "2.5", NOW - 10, NOW)
        self.assertEqual((bk, near), (True, False))
        bk, near, dist, _ = E.breakout_10d(bars, D, "1.9", NOW - 10, NOW)
        self.assertEqual((bk, near), (False, True))
        self.assertAlmostEqual(dist, -0.05)
        bk, near, _, _ = E.breakout_10d(bars, D, "1.0", NOW - 10, NOW)
        self.assertEqual((bk, near), (False, False))
        short = E.finalized_bars(series(9, high=2.0), NOW, None)
        self.assertIsNone(E.breakout_10d(short, D, "2.5", NOW - 10, NOW)[0])
        stale = NOW - C.BREAKOUT_PRICE_MAX_AGE_SEC - 1
        self.assertIsNone(E.breakout_10d(bars, D, "2.5", stale, NOW)[0])

    def test_breakout_window_excludes_open_day(self):
        rows = series(10, high=2.0) + [bar(D + DAY, high=99.0, fetched=NOW)]
        bars = E.finalized_bars(rows, NOW, None)
        self.assertEqual(E.breakout_10d(bars, D, "2.5", NOW - 10, NOW)[3]["prev_10d_high"], 2.0)


# ------------------------------------------------------------------ scoring
class ScoreTests(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual([E.score_volume(v) for v in (None, 1.49, 1.5, 2, 2.99, 3)], [0, 0, 10, 20, 20, 25])
        self.assertEqual([E.score_buy(v) for v in (None, .549, .55, .60, .65)], [0, 0, 5, 10, 15])
        self.assertEqual([E.score_holder(v) for v in (None, -.1, 0, .01, .05, .10)], [0, 0, 0, 5, 10, 15])
        self.assertEqual([E.score_liquidity(v) for v in (None, 0, .05, .10, .25)], [0, 0, 5, 10, 15])
        self.assertEqual([E.score_cross(v) for v in (None, 0, 1, 2, 3, 4, 7)], [0, 0, 0, 10, 15, 20, 20])

    def test_breakout_not_stacked(self):
        self.assertEqual(E.score_breakout(True, False), 20)
        self.assertEqual(E.score_breakout(True, True), 20)
        self.assertEqual(E.score_breakout(False, True), 5)
        self.assertEqual(E.score_breakout(None, None), 0)

    def test_raw_capped_and_known_counts(self):
        s = E.score_signals(sig(volume_ratio=4, buy_share=.7, holder_growth=.2, liquidity_growth=.3,
                                cross_list_count_60m=4, breakout_10d=True, near_breakout_10d=False))
        self.assertEqual((s["raw_score"], s["score"], s["known"], s["unknown"]), (110, 100, 6, 0))

    def test_unknown_is_not_zero(self):
        s = E.score_signals(sig(cross_list_count_60m=0))
        self.assertEqual((s["score"], s["known"], s["unknown"]), (0, 1, 5))
        s = E.score_signals(sig())
        self.assertEqual((s["known"], s["unknown"]), (0, 6))


# ------------------------------------------------------------------ stage
def ready_sig(**kw):
    s = sig(volume_ratio=3, buy_share=.65, holder_growth=.1, liquidity_growth=.25,
            cross_list_count_60m=1, breakout_10d=True, near_breakout_10d=False)
    s.update(kw)
    return s


def classify(s):
    sc = E.score_signals(s)
    checks = E.ready_check(sc["score"], s, sc["known"])
    return sc["score"], E.entry_stage(sc["score"], checks), checks


class StageTests(unittest.TestCase):
    def test_entry_thresholds(self):
        self.assertEqual(classify(sig(cross_list_count_60m=4, liquidity_growth=.3))[1], "NORMAL")  # 35
        self.assertEqual(classify(sig(cross_list_count_60m=4, volume_ratio=2))[1], "OBSERVE")      # 40
        self.assertEqual(classify(sig(cross_list_count_60m=4, volume_ratio=3, liquidity_growth=.3))[1],
                         "EARLY")                                                                   # 60

    def test_ready_requires_all_hard_conditions(self):
        score, entry, _ = classify(ready_sig())
        self.assertEqual((score, entry), (90, "READY"))   # 25+15+15+15+0(cross 1)+20
        for override in ({"buy_share": None}, {"buy_share": .59}, {"volume_ratio": 1.9},
                         {"breakout_10d": False, "cross_list_count_60m": 1}):
            s = ready_sig(**override)
            score, entry, _ = classify(s)
            self.assertNotEqual(entry, "READY", override)
        # cross_list ≥ 2 可以替代 breakout
        self.assertEqual(classify(ready_sig(breakout_10d=False, cross_list_count_60m=2))[1], "READY")

    def test_ready_blocked_by_known_count(self):
        s = sig(volume_ratio=3, buy_share=.65, cross_list_count_60m=4, breakout_10d=True,
                near_breakout_10d=False)  # 25+15+20+20 = 80, known = 4 → READY
        self.assertEqual(classify(s)[1], "READY")
        s2 = dict(s, cross_list_count_60m=None)  # known 3, score 60
        self.assertNotEqual(classify(s2)[1], "READY")

    def test_upgrade_is_immediate_and_skips_levels(self):
        st = E.new_state(NOW)
        score, entry, checks = classify(ready_sig())
        st2, tr = E.step_state(st, score, entry, True, checks)
        self.assertEqual((st2["stage"], tr["from"], tr["to"]), ("READY", "NORMAL", "READY"))
        self.assertIn("UPGRADE", tr["reason"])

    def test_downgrade_requires_two_consecutive_valid(self):
        st = dict(E.new_state(NOW), stage="READY")
        st, tr = E.step_state(st, 64, "EARLY", True, [])
        self.assertEqual((st["stage"], tr), ("READY", None))
        st, tr = E.step_state(st, 64, "EARLY", True, [])
        self.assertEqual((st["stage"], tr["to"]), ("EARLY", "EARLY"))
        self.assertIn("2 consecutive", tr["reason"])

    def test_streak_resets_on_recovery(self):
        st = dict(E.new_state(NOW), stage="READY")
        st, _ = E.step_state(st, 60, "EARLY", True, [])
        st, _ = E.step_state(st, 70, "EARLY", True, [])     # ≥ 65 → 连击清零
        st, tr = E.step_state(st, 60, "EARLY", True, [])
        self.assertEqual((st["stage"], tr), ("READY", None))

    def test_unknown_observation_does_not_count(self):
        st = dict(E.new_state(NOW), stage="EARLY")
        st, _ = E.step_state(st, 10, "NORMAL", True, [])
        st, tr = E.step_state(st, 10, "NORMAL", False, [])  # UNKNOWN / 无新数据
        self.assertEqual((st["stage"], tr), ("EARLY", None))
        st, tr = E.step_state(st, 10, "NORMAL", True, [])
        self.assertEqual(tr["from"], "EARLY")

    def test_hysteresis_band_holds_stage(self):
        st = dict(E.new_state(NOW), stage="EARLY")
        for _ in range(5):
            st, tr = E.step_state(st, 55, "OBSERVE", True, [])  # < 60 但 ≥ 50
            self.assertIsNone(tr)
        self.assertEqual(st["stage"], "EARLY")

    def test_cascading_downgrade(self):
        st = dict(E.new_state(NOW), stage="READY")
        E.step_state(st, 20, "NORMAL", True, [])
        st, _ = E.step_state(st, 20, "NORMAL", True, [])
        st, tr = E.step_state(st, 20, "NORMAL", True, [])
        self.assertEqual((tr["from"], tr["to"]), ("READY", "NORMAL"))

    def test_step_is_pure(self):
        st = E.new_state(NOW)
        E.step_state(st, 99, "EARLY", True, [])
        self.assertEqual(st["stage"], "NORMAL")


# ------------------------------------------------------------------ REVIVAL
class RevivalTests(unittest.TestCase):
    def bars(self, quiet=10.0, latest=100.0):
        return E.finalized_bars(series(10, vol=quiet, latest_vol=latest), NOW, None)

    def test_true(self):
        s = sig(volume_ratio=10, holder_growth=.01, cross_list_count_60m=2)
        self.assertIs(E.revival(30, self.bars(), D, s)[0], True)

    def test_new_token_is_false(self):
        s = sig(volume_ratio=10, holder_growth=.01, cross_list_count_60m=2)
        self.assertIs(E.revival(3, self.bars(), D, s)[0], False)

    def test_not_dormant_is_false(self):
        s = sig(volume_ratio=10, holder_growth=.01, cross_list_count_60m=2)
        self.assertIs(E.revival(30, self.bars(quiet=50.0), D, s)[0], False)

    def test_insufficient_history_is_null(self):
        s = sig(volume_ratio=10, holder_growth=.01, cross_list_count_60m=2)
        short = E.finalized_bars(series(5, vol=10.0, latest_vol=100.0), NOW, None)
        self.assertIsNone(E.revival(30, short, D, s)[0])
        self.assertIsNone(E.revival(None, self.bars(), D, s)[0])

    def test_support_unknown_is_null_not_false(self):
        s = sig(volume_ratio=10, holder_growth=.01)  # 1 true + 3 unknown
        self.assertIsNone(E.revival(30, self.bars(), D, s)[0])
        s = sig(volume_ratio=10, holder_growth=-.01, liquidity_growth=-.01, cross_list_count_60m=0,
                breakout_10d=False)  # 0 true, 1 unknown → 不可能 ≥2
        self.assertIs(E.revival(30, self.bars(), D, s)[0], False)

    def test_volume_ratio_below_three_is_false(self):
        s = sig(volume_ratio=2.9, holder_growth=.01, cross_list_count_60m=2)
        self.assertIs(E.revival(30, self.bars(), D, s)[0], False)


# ------------------------------------------------------------------ 集成：run_once
MARKET_SCHEMA = """
CREATE TABLE tokens (chain TEXT, address TEXT, symbol TEXT, token_created_at INTEGER, pair_created_at INTEGER,
                     PRIMARY KEY (chain, address));
CREATE TABLE token_snapshot (chain TEXT, address TEXT, price TEXT, price_updated_at INTEGER, liquidity_num REAL,
    liquidity_updated_at INTEGER, liquidity_source TEXT, security_is_honeypot INTEGER, security_updated_at INTEGER,
    halt INTEGER, PRIMARY KEY (chain, address));
CREATE TABLE daily_kline (chain TEXT, address TEXT, ts INTEGER, open TEXT, high TEXT, low TEXT, close TEXT,
    volume TEXT, amount TEXT, fetched_at INTEGER, finalized_at INTEGER, PRIMARY KEY (chain, address, ts));
CREATE TABLE discovery_event (id INTEGER PRIMARY KEY, chain TEXT, address TEXT, source TEXT, source_variant TEXT,
    seen_at INTEGER, time_bucket INTEGER, liquidity REAL, price REAL, market_cap REAL, rank INTEGER,
    metadata_json TEXT);
"""


class RunOnceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mpath = os.path.join(self.tmp.name, "market.sqlite")
        self.rpath = os.path.join(self.tmp.name, "radar.sqlite")
        con = sqlite3.connect(self.mpath)
        con.executescript(MARKET_SCHEMA)
        A = "TokenA"
        con.execute("INSERT INTO tokens VALUES ('sol', ?, 'A', ?, NULL)", (A, NOW - 60 * DAY))
        con.execute("INSERT INTO token_snapshot VALUES ('sol', ?, '1.0', ?, 80000, ?, 'trending', 0, ?, NULL)",
                    (A, NOW - 30, NOW - 30, NOW - 300))
        for i in range(9, -1, -1):
            ts = D - i * DAY
            con.execute("INSERT INTO daily_kline VALUES ('sol', ?, ?, '1', '2', '1', '1', ?, '', ?, NULL)",
                        (A, ts, "400" if i == 0 else "100", ts + DAY + 60))
        # 覆盖：首个事件早于窗口；窗口内四个源都在（sol 支持 signal）
        con.execute("INSERT INTO discovery_event(chain,address,source,seen_at) VALUES ('sol','Other','trending',?)",
                    (NOW - 2 * DAY,))
        for k, src in enumerate(("trending", "hot", "signal", "trenches")):
            # 四个榜单在同一个 300s 桶里几秒内先后看到 → 只算一个快照
            con.execute("INSERT INTO discovery_event(chain,address,source,seen_at,liquidity,metadata_json) "
                        "VALUES ('sol',?,?,?,?,?)", (A, src, NOW - 10 - k, 80000, json.dumps({"holder_count": 1100})))
        con.execute("INSERT INTO discovery_event(chain,address,source,seen_at,liquidity,metadata_json) "
                    "VALUES ('sol',?,'trending',?,?,?)", (A, NOW - 1800, 60000, json.dumps({"holder_count": 1000})))
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def run_once(self, as_of=NOW):
        return E.run_once(market_path=self.mpath, radar_path=self.rpath, as_of=as_of, log=lambda *_: None)

    def test_first_run_transitions_and_repeat_is_quiet(self):
        t1 = self.run_once()
        self.assertEqual(t1["transitions"], 1)
        r = sqlite3.connect(self.rpath)
        row = r.execute("SELECT volume_ratio, holder_growth, liquidity_growth, cross_list_count, buy_share, "
                        "score, stage, gate FROM radar_eval WHERE address='TokenA'").fetchone()
        # vol 4x=25, holder +10%=15, liq ≥25%=15 (80000/60000), cross 4=20, breakout: price 1 < high 2 → 0
        self.assertEqual(row[:4], (4.0, 0.1, round(80000 / 60000 - 1, 10), 4))
        self.assertIsNone(row[4])                 # buy_share 不可得 → null，不是 0
        self.assertEqual(row[5:], (75, "EARLY", "PASS"))   # 75 但 buy_share 未知 → READY 被挡
        tr = r.execute("SELECT from_stage, to_stage, reason FROM radar_transition").fetchall()
        self.assertEqual(tr[0][:2], ("NORMAL", "EARLY"))
        self.assertIn("READY blocked", tr[0][2])
        n_eval = r.execute("SELECT COUNT(*) FROM radar_eval").fetchone()[0]
        r.close()

        t2 = self.run_once()                       # 同一时刻、同一数据：不是新 observation
        self.assertEqual((t2["transitions"], t2["new_observations"], t2["evals_written"]), (0, 0, 0))
        r = sqlite3.connect(self.rpath)
        self.assertEqual(r.execute("SELECT COUNT(*) FROM radar_eval").fetchone()[0], n_eval)
        self.assertEqual(r.execute("SELECT COUNT(*) FROM radar_transition").fetchone()[0], 1)
        summ = r.execute("SELECT scanned, gate_pass, stage_early, candidates FROM radar_run_summary "
                         "WHERE chain='all' ORDER BY run_id DESC").fetchone()
        self.assertEqual(summ, (1, 1, 1, 1))
        r.close()

    def test_market_db_untouched(self):
        before = os.path.getmtime(self.mpath), os.path.getsize(self.mpath)
        self.run_once()
        self.assertEqual((os.path.getmtime(self.mpath), os.path.getsize(self.mpath)), before)

    def test_verify_replays_stored_scores(self):
        self.run_once()
        self.assertEqual(E.verify(self.rpath)["mismatches"], 0)

    def test_no_future_data(self):
        # 在 D 当天结束前评估：D 的 K 线还没收盘，不能用
        t = self.run_once(as_of=D + DAY - 10)
        r = sqlite3.connect(self.rpath)
        fd = r.execute("SELECT finalized_date FROM radar_run WHERE run_id=?", (t["run_id"],)).fetchone()[0]
        self.assertEqual(fd, E.day_key(D - DAY))
        r.close()


if __name__ == "__main__":
    unittest.main()
