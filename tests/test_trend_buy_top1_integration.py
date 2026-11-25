"""Current mainline: frozen admission, funding and TOP1-only execution."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import prepare_trend_buy_candidates as intake
import build_trend_buy_manual_research as builder
import trend_buy_engine as engine


class CurrentTop1IntegrationTests(unittest.TestCase):
    def require_current_paired_working_set(self):
        # Data pipeline may update quotes before the next confirmed sector
        # handoff. That is an expected closed gate, not a screening failure.
        handoff=json.loads((ROOT/"research/trend_handoff.json").read_text())
        idx=json.loads((ROOT/"data/low_risk/index.json").read_text())
        if handoff.get("trade_date")!=idx.get("trade_date"):
            self.skipTest("confirmed_sector_and_market_working_set_dates_not_paired")
        if not handoff.get("signals"):
            self.skipTest("no_current_confirmed_sw3_to_run_positive_admission_cases")
        return handoff["trade_date"]

    def test_frozen_candidates_and_funds_reach_only_top1_risk_engine(self):
        self.require_current_paired_working_set()
        # Tests contract wiring only, NOT real issuer evidence or an executable
        # financial recommendation. All synthetic inputs live in /tmp.
        self.check_current_top1_path(intake.prepare(ROOT))

    def check_current_top1_path(self, a):
        # Current official adapter, not the retired all-candidate risk engine.
        # Synthetic model decisions are contract fixtures, never issuer research.
        import freeze_trend_buy_fund_flow as funds
        import run_model_top1_formal as formal
        import research_model_top1 as model
        import trend_buy_handoff as handoff
        import trend_buy_prescreen_core as pre
        d=a["trade_date"]
        stamp=d+"T19:00:00+08:00"
        cache={}
        groups=[]
        reviews=[]
        picks=[]
        for g in a["industries"]:
            sector=g["industry_code"]
            codes=g["selected_codes"]
            stocks={}
            for code in codes:
                hist=pre.history_for(ROOT,code,cache)["history"]
                dates=sorted({r["date"] for r in hist if r["date"]<=d})[-20:]
                rows=[{"date":x,"main_net_cny":1,"amount_cny":100} for x in dates]
                stocks[code]={"code":code,"provider":"tencent","trade_date":d,
                              "queried_at":stamp,"sources":["https://example.org/synthetic"],
                              "daily":rows,"windows":funds.metrics(rows)}
                reviews.append({"code":code,"transmission":"SUPPORTED","review_evidence_date":d,
                                "review_basis":"SYNTHETIC_UNIT_TEST_ONLY",
                                "source_review":"SYNTHETIC TEST ONLY; not issuer evidence.",
                                "source_materials":[{"asof":d,"published_at":d,
                                    "url":"https://example.org/synthetic"}],
                                "research_falsifier":"synthetic","early_evidence_risk_review_passed":True,
                                "evidence_gap":False})
            groups.append({"industry_code":sector,"candidate_codes":codes,"status":"VERIFIED",
                           "provider":"tencent","definition":funds.DEFINITIONS["tencent"],
                           "stocks":stocks,"attempts":[{"provider":"tencent","queried_at":stamp,"errors":{}}]})
            matrix={code:{k:{"status":"VERIFIED_FACT","sources":["https://example.org/synthetic"]}
                           for k in "ABCDE"} for code in codes}
            for code in codes:
                matrix[code]["A"]["frozen_fund_ref"]="fund_flow.groups/"+sector+"/stocks/"+code
            chosen=codes[-1]
            picks.append({"industry_code":sector,"candidate_codes":codes,"status":"COMPLETE",
                          "top1_code":chosen,"reason":"synthetic selection",
                          "completion_gate":dict.fromkeys(model.GATES,True),
                          "research_matrix":matrix,
                          "dynamic_comparison":{code:dict.fromkeys(model.DIMENSIONS,"synthetic") for code in codes},
                          "comparison_reasons":{code:"synthetic" for code in codes if code!=chosen},
                          "strongest_counter":"synthetic","falsifier":"synthetic"})
        a["fund_flow"]={"trade_date":d,"collected_at":stamp,"groups":groups}
        intake.validate_admission(ROOT,a)
        raw=json.dumps(a,ensure_ascii=False).encode()
        ev={"as_of_date":d,"reviews":reviews,"explicit_no_prior_formal_or_archive_input":True,
            "top1_selection":{"trade_date":d,"source_blob":model.git_blob_sha(raw),
                              "prompt_version":model.VERSION,"items":picks}}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            admission=root/"admission.json"
            evidence=root/"synthetic_only.json"
            structures=root/"technical.json"
            admission.write_bytes(raw)
            evidence.write_text(json.dumps(ev,ensure_ascii=False))
            research=builder.build(evidence,structure_output_path=structures,
                                   admission_path=admission,model_top1_research=True)
            self.assertEqual(research["mode"],"MODEL_TOP1_RESEARCH")
            technical=json.loads(structures.read_text())
            with patch.object(formal.engine,"evaluate_candidate",wraps=formal.engine.evaluate_candidate) as evaluate:
                output=formal.generate(raw,research,technical,ev,"synthetic-only")
            self.assertEqual(evaluate.call_count,len(picks))
            self.assertEqual([p["top1_code"] for p in output["top1_decisions"]],[p["top1_code"] for p in picks])
            self.assertEqual(output["python_top5_by_industry"],a["industries"])
            self.assertEqual([x["code"] for x in handoff.project(output,"synthetic-sha")["items"]],
                             [p["top1_code"] for p in output["top1_decisions"] if p["risk_status"] in ("READY","WAIT")])
            with self.assertRaisesRegex(ValueError,"LEGACY_TOP5_FORMAL_DISABLED"):
                engine.generate({**research,"mode":"FORMAL"},technical)


if __name__=="__main__":
    unittest.main()
