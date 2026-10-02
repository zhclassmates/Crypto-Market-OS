import unittest

from forced_trade.states import evaluate, flow_aligned, load_states


def _row(**kwargs):
    base = {
        "funding_pct_30d": 0.5,
        "ret_4h_vs_btc": 0.01,
        "oi_qty_chg_4h": 0.01,
        "taker_imbalance_4h": 0.0,
        "abs_ret_1h_z": 0.2,
        "oi_chg_1h_z": 0.1,
        "flow_aligned_with_price": 0,
        "basis_z_7d": 0.1,
        "funding_rate_type": "Regular",
        "data_quality_flag": None,
    }
    base.update(kwargs)
    return base


class StateTest(unittest.TestCase):
    def test_s4_is_disabled(self):
        spec = load_states()
        self.assertFalse(spec["states"]["delever_done"]["enabled"])
        hits = {item["state"]: item for item in evaluate(_row(), spec)}
        self.assertEqual(hits["delever_done"]["hit"], 0)
        self.assertEqual(hits["delever_done"]["reason"], "disabled")

    def test_crowded_long(self):
        row = _row(
            funding_pct_30d=0.95,
            ret_4h_vs_btc=-0.01,
            oi_qty_chg_4h=0.02,
            taker_imbalance_4h=-0.2,
        )
        hits = {item["state"]: item for item in evaluate(row)}
        self.assertEqual(hits["crowded_long_under_pressure"]["hit"], 1)
        self.assertEqual(hits["crowded_short_under_pressure"]["hit"], 0)

    def test_special_funding_cannot_hit_crowding(self):
        row = _row(
            funding_pct_30d=0.99,
            ret_4h_vs_btc=-0.02,
            oi_qty_chg_4h=0.02,
            taker_imbalance_4h=-0.2,
            funding_rate_type="Special",
        )
        hits = {item["state"]: item for item in evaluate(row)}
        self.assertEqual(hits["crowded_long_under_pressure"]["hit"], 0)

    def test_delever_requires_flow_alignment(self):
        row = _row(abs_ret_1h_z=2.0, oi_chg_1h_z=-2.0, flow_aligned_with_price=0)
        hits = {item["state"]: item for item in evaluate(row)}
        self.assertEqual(hits["deleveraging_in_progress"]["hit"], 0)
        row["flow_aligned_with_price"] = 1
        hits = {item["state"]: item for item in evaluate(row)}
        self.assertEqual(hits["deleveraging_in_progress"]["hit"], 1)

    def test_basis_is_not_directional(self):
        spec = load_states()
        self.assertFalse(spec["states"]["basis_distortion"]["directional_signal"])
        self.assertEqual(flow_aligned(0.01, 0.2), 1)
        self.assertEqual(flow_aligned(0.01, -0.2), 0)
        self.assertEqual(flow_aligned(0.0, 0.2), 0)


if __name__ == "__main__":
    unittest.main()
