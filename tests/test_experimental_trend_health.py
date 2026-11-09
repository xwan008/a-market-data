"""Regression tests: experimental health must never become a formal gate."""
import importlib.util
from pathlib import Path
import unittest

S = Path(__file__).resolve().parents[1] / "scripts" / "experimental_trend_health.py"
spec = importlib.util.spec_from_file_location("experimental_trend_health", S)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def metric(day, rel, momentum, b3=.9, b5=.9, b1=.9):
    return {"trade_date": day, "market_return_median_pct": 0.0,
            "industries": {"S720401": {"r": rel, "p": 1.0, "m3": momentum,
                                        "m5": 4.0, "b3": b3, "b5": b5,
                                        "b1": b1, "n": 14}}}


def theme(basis="A_SHARE"):
    return {"episode_id": "游戏#2026-11-02", "trend_name": "游戏", "market_state": "趋势确认",
            "trend_basis": basis, "industry_codes": ["S720401"],
            "confirmation_audit": {"core_industry_codes": ["S720401"]},
            "industry_assessments": [{"industry_code": "S720401", "market_state": "趋势确认"}]}


class HealthTest(unittest.TestCase):
    def test_game_day_5_decay_even_before_loss_of_breadth(self):
        days = [metric("2026-11-02", 7.458, .81), metric("2026-11-03", 2.939, 5.185),
                metric("2026-11-04", .213, 12.77), metric("2026-11-05", .165, 5.945)]
        result = mod.health_one(theme(), days)
        self.assertEqual(result["health"], "衰减")
        self.assertEqual(result["signal_count"], 2)
        self.assertEqual(result["protection_status"], "防御")
        self.assertEqual(result["protection_color"], "ORANGE")
        self.assertFalse(result["market_invalidation"])

    def test_game_day_6_high_risk_not_invalidated(self):
        days = [metric("2026-11-03", 2.939, 5.185),
                metric("2026-11-04", .213, 12.77),
                metric("2026-11-05", .165, 5.945),
                metric("2026-11-06", -.719, .495, b3=.5, b5=1.0, b1=0)]
        result = mod.health_one(theme(), days)
        self.assertEqual(result["health"], "高风险")
        self.assertEqual(result["protection_status"], "防御")
        self.assertFalse(result["protection_is_trade_instruction"])
        self.assertFalse(result["market_invalidation"])

    def test_exit_requires_multiday_structural_evidence(self):
        days = [metric("2026-11-03", 2, 4),
                metric("2026-11-04", 1, 3),
                metric("2026-11-05", -0.6, 1),
                metric("2026-11-06", -1, -2, b3=.2, b5=.2, b1=.05)]
        days[-1]["industries"]["S720401"]["m5"] = -3
        result = mod.health_one(theme(), days)
        self.assertEqual(result["protection_status"], "退出")
        self.assertEqual(result["protection_color"], "RED")
        self.assertFalse(result["market_invalidation"])
        self.assertFalse(result["protection_is_trade_instruction"])

    def test_one_warning_is_not_exit(self):
        days = [metric("2026-11-03", 0.4, 2),
                metric("2026-11-04", 0.4, 2),
                metric("2026-11-05", 0.4, 2),
                metric("2026-11-06", 0.4, 2, b3=.5, b5=.9, b1=.9)]
        result = mod.health_one(theme(), days)
        self.assertEqual(result["protection_status"], "警戒")
        self.assertEqual(result["protection_color"], "YELLOW")

    def test_missing_history_and_commodity(self):
        self.assertEqual(mod.health_one(theme(), [metric("2026-11-06", 1, 3)])["health"], "待积累")
        self.assertEqual(mod.health_one(theme(), [metric("2026-11-06", 1, 3)])["protection_status"], "待评估")
        self.assertEqual(mod.health_one(theme("COMMODITY"), [])["status"], "COMMODITY_FIRST_ANCHOR")

    def test_dates_idempotence_and_formal_unchanged(self):
        registry = {"trade_date": "2026-11-06", "status": "COMPLETE", "trends": [theme()]}
        sector = {"trade_date": "2026-11-06", "market_median_return_1d_pct": -1,
                  "sectors": [{"kind": "industry", "sample_quality": "OK", "id": "industry:S720401",
                               "usable_count": 14, "relative_1d_vs_market_median_pct": -.719,
                               "median_1d_pct": -2.157, "median_3d_pct": .495, "median_5d_pct": 13.015,
                               "breadth_3d": .5, "breadth_5d": 1, "advance_ratio": 0}]}
        import copy
        original = copy.deepcopy(registry)
        first = mod.build(registry, sector)
        second = mod.build(registry, sector, first)
        self.assertEqual(registry, original)
        self.assertEqual(len(second["sector_history"]), 1)
        self.assertEqual(len(second["daily_observations"]), 1)
        self.assertEqual(second["latest"][0]["health"], "待积累")
        self.assertEqual(second["latest"][0]["protection_status"], "待评估")
        sector["trade_date"] = "2026-11-05"
        with self.assertRaisesRegex(ValueError, "ASOF_DATE_MISMATCH"):
            mod.build(registry, sector, first)


if __name__ == "__main__":
    unittest.main()
