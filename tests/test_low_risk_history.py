"""History registry contract and lifecycle regression tests."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from update_low_risk_history import blob_sha, build, update, validate  # noqa: E402


def pair(date="2026-09-30", run="r1", rows=None, trends=None):
    rows = rows if rows is not None else [
        {"rank": 1, "code": "002074", "company_name": "样本公司", "trend_name": "A",
         "industry_code": "X", "industry_name": "测试行业", "status": "WAIT",
         "wait_reason": "WAIT_PRICE", "current_price": 10,
         "reasonable_buy_range": [8, 9], "low_risk_buy_range": [7, 8],
         "wait_or_trigger_condition": "价格", "invalidation": "结构"}]
    formal_rows = [{**item, "reasonable_price_range": item["reasonable_buy_range"], "reentry_trigger": item["wait_or_trigger_condition"]} for item in rows]
    formal = {"result_kind": "a_share_low_risk_formal_result", "status": "COMPLETE",
              "trade_date": date, "run_id": run,
              "ready": [r for r in formal_rows if r["status"] == "READY"],
              "wait": [r for r in formal_rows if r["status"] == "WAIT"],
              "trend_handoff": {"signals": trends if trends is not None else
                                [{"trend_name": "A", "industry_codes": ["X"]}]},
              "pre_screened_out": [], "hard_filtered_out": [], "uncertain": [],
              "early_evidence": [], "drop": []}
    handoff = {"status": "COMPLETE", "source_run_id": run, "trade_date": date,
               "source_formal_blob_sha": "sha", "items": rows}
    return formal, handoff


class HistoryTest(unittest.TestCase):
    def test_bootstrap_and_continuation(self):
        old, snap = build(*pair(), "sha")
        self.assertEqual((old["status"], old["counts"]["ACTIVE"]), ("BOOTSTRAP_PARTIAL", 1))
        self.assertIsNone(snap["prior_registry"])
        new, later = build(*pair("2026-10-01", "r2"), "sha", old)
        self.assertEqual(new["status"], "COMPLETE")
        self.assertEqual(new["records"][0]["episode"], 1)
        self.assertEqual(later["events"][0]["action"], "CONTINUED")

    def test_board_exit_and_reentry_start_new_episode(self):
        old, _ = build(*pair(), "sha")
        f, h = pair("2026-10-01", "r2", rows=[],
                    trends=[{"trend_name": "B", "industry_codes": ["Y"]}])
        paused, snap = build(f, h, "sha", old)
        self.assertEqual(paused["records"][0]["lifecycle"], "PAUSED_OUT_OF_SCOPE")
        self.assertEqual(snap["events"][0]["reason"], "OUT_OF_CURRENT_TREND_HANDOFF")
        fresh, events = build(*pair("2026-10-02", "r3"), "sha", paused)
        self.assertEqual(fresh["counts"], {"ACTIVE": 1, "PAUSED_OUT_OF_SCOPE": 0, "CLOSED": 1})
        self.assertEqual(fresh["records"][1]["episode"], 2)
        self.assertIn("ROUTE_CHANGED", [e["action"] for e in events["events"]])

    def test_still_routed_but_not_selected_gets_factual_reason(self):
        old, _ = build(*pair(), "sha")
        f, h = pair("2026-10-01", "r2", rows=[])
        f["pre_screened_out"] = [{"code": "002074", "industry_code": "X", "trend_name": "A"}]
        closed, snap = build(f, h, "sha", old)
        self.assertEqual(closed["counts"]["CLOSED"], 1)
        self.assertEqual(snap["events"][0]["reason"], "PRE_SCREENED_OUT")

    def test_mismatched_handoff_blocks_all_writes(self):
        f, h = pair()
        h["items"][0]["low_risk_buy_range"] = [6, 7]
        with self.assertRaisesRegex(ValueError, "HANDOFF_PRICE_MISMATCH"):
            validate(f, h, "sha")
        f, h = pair()
        h["source_formal_blob_sha"] = "bad"
        with self.assertRaisesRegex(ValueError, "FORMAL_SHA_MISMATCH"):
            validate(f, h, "sha")

    def test_history_quote_missing_no_stale_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            d = Path(root)
            (d / "0020.json").write_text(json.dumps({"stocks": {"002074": {
                "history_basis": "tencent_qfq", "history": [
                    {"date": "2026-09-30", "close": 10, "confidence": "high"},
                    {"date": "2026-10-01", "close": 11, "confidence": "high"}]}}}), encoding="utf-8")
            old, _ = build(*pair(), "sha", history_dir=d)
            newer, _ = build(*pair("2026-10-01", "r2"), "sha", old, history_dir=d)
            self.assertEqual(newer["records"][0]["last_market_observation"]["qfq_return_since_first_seen_pct"], 10.0)
            final, _ = build(*pair("2026-10-02", "r3"), "sha", newer, history_dir=d)
            self.assertEqual(final["records"][0]["last_market_observation"]["status"], "UNAVAILABLE")

    def test_same_day_rerun_uses_original_prior_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "research"
            research.mkdir()
            def save(date, run, rows=None):
                f, h = pair(date, run, rows)
                raw = json.dumps(f, ensure_ascii=False).encode()
                (research / "latest_formal_result.json").write_bytes(raw)
                h["source_formal_blob_sha"] = blob_sha(raw)
                (research / "low_risk_handoff.json").write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
            save("2026-09-30", "r1")
            self.assertEqual(update(root), "UPDATED")
            self.assertEqual(update(root), "UNCHANGED")
            new_row = {**pair()[1]["items"][0], "code": "002460"}
            save("2026-09-30", "r2", [new_row])
            self.assertEqual(update(root), "UPDATED")
            reg = json.loads((research / "low_risk_signal_registry.json").read_text())
            self.assertEqual([r["code"] for r in reg["records"]], ["002460"])
            snap = json.loads((research / "low_risk_history/2026-09-30.json").read_text())
            self.assertIsNone(snap["prior_registry"])


if __name__ == "__main__":
    unittest.main()
