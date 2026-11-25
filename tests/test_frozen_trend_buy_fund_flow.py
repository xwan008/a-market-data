import datetime as dt
import json
import sys
from pathlib import Path
from unittest import TestCase, mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import freeze_trend_buy_fund_flow as f

DAY="2026-11-25"
DATES=["2026-11-19","2026-11-20","2026-11-23","2026-11-24",DAY]
STAMP=DAY+"T19:00:00+08:00"
CODES=["601288","601328"]
IND="S480201"
A={"trade_date":DAY,"industries":[{"industry_code":IND,"selected_codes":CODES}]}


def stock(code,provider="tencent"):
    rows=[{"date":d,"main_net_cny":i-1,"amount_cny":10} for i,d in enumerate(DATES)]
    return {"code":code,"provider":provider,"trade_date":DAY,"queried_at":STAMP,
            "sources":["https://example.com/source"],"daily":rows,"windows":f.metrics(rows)}


def snap(provider="tencent",incomplete=False):
    attempts=[{"provider":"tencent","queried_at":STAMP,"errors":{}}]
    if provider=="eastmoney" or incomplete:
        attempts[0]["errors"]={CODES[0]:"source missing"}
        attempts.append({"provider":"eastmoney","queried_at":STAMP,"errors":{}})
    if incomplete:
        attempts[-1]["errors"]={CODES[1]:"source missing"}
    g={"industry_code":IND,"candidate_codes":CODES,"status":"INCOMPLETE" if incomplete else "VERIFIED",
       "provider":None if incomplete else provider,"stocks":{} if incomplete else {c:stock(c,provider) for c in CODES},
       "attempts":attempts}
    if not incomplete:g["definition"]=f.DEFINITIONS[provider]
    return {"trade_date":DAY,"collected_at":STAMP,"groups":[g]}


class FundFlowTest(TestCase):
    def test_windows_use_weighted_amount_and_no_missing_zero(self):
        rows=[{"date":d,"main_net_cny":i+1,"amount_cny":(i+1)*10} for i,d in enumerate(DATES)]
        m=f.metrics(rows)
        self.assertEqual(m["5"]["net_pct"],10)
        self.assertEqual(m["5"]["positive_days"],5)
        self.assertEqual(m["10"]["status"],"UNKNOWN")

    def test_valid_and_tamper(self):
        for p in f.PROVIDERS:self.assertEqual(f.validate(A,snap(p)),{IND:"VERIFIED"})
        s=snap()
        s["groups"][0]["stocks"][CODES[0]]["windows"]["5"]["net_cny"]=99
        with self.assertRaisesRegex(ValueError,"AGGREGATE"):f.validate(A,s)
        s=snap()
        s["groups"][0]["stocks"][CODES[1]]["provider"]="eastmoney"
        with self.assertRaisesRegex(ValueError,"IDENTITY"):f.validate(A,s)

    def test_selection_gate_and_abstention(self):
        p={"industry_code":IND,"status":"COMPLETE","candidate_codes":CODES,
           "research_matrix":{c:{"A":{"frozen_fund_ref":"fund_flow.groups/"+IND+"/stocks/"+c}} for c in CODES}}
        picks={"items":[p]}
        f.validate_selections({**A,"fund_flow":snap()},picks)
        with self.assertRaisesRegex(ValueError,"SNAPSHOT_REQUIRED"):f.validate_selections(A,picks)
        with self.assertRaisesRegex(ValueError,"GROUP_NOT_VERIFIED"):f.validate_selections({**A,"fund_flow":snap(incomplete=True)},picks)
        with self.assertRaisesRegex(ValueError,"GROUP_NOT_VERIFIED"):f.validate_selections({**A,"fund_flow":snap(incomplete=True)},{"items":[{**p,"status":"NO_SELECTION"}]})
        p["research_matrix"][CODES[0]]["A"]["frozen_fund_ref"]="incorrect"
        with self.assertRaisesRegex(ValueError,"REFERENCE"):f.validate_selections({**A,"fund_flow":snap()},picks)
        f.validate_selections(A,{"items":[{**p,"status":"INCOMPLETE"}]})

    def test_incomplete_is_not_fake_data(self):
        self.assertEqual(f.validate(A,snap(incomplete=True)),{IND:"INCOMPLETE"})

    def test_missing_session_is_not_zero(self):
        quotes={d:{"close":10,"amount":100} for d in DATES}
        mapping={d:{"date":d,"main_net_cny":5,"amount_cny":100} for d in DATES if d!=DATES[1]}
        with mock.patch.object(f,"tencent_rows",return_value=(mapping,["https://example.com"])):
            with self.assertRaisesRegex(ValueError,"CORE_FIVE"):f.collect_stock(CODES[0],DATES,10,"tencent",quotes)

    def test_tencent_dated_close_and_matching_summary(self):
        today={"stockCode":"sh601288","desc":"主力=超大单+大单，20万元或6万股","mainNetIn":"5","superFlow":"2","bigFlow":"3","mainIn":"52","mainOut":"47","normalFlow":"-2","smallFlow":"-3","retailIn":"48","retailOut":"53"}
        trend={"stockCode":"sh601288","minList":[{"time":"202611251500","Price":"10","MainNetInflow":"5"}]}
        hist={"oneDayKlineList":[{"date":d,"price":"10","mainNetIn":"1"} for d in DATES[:-1]]}
        q=[""]*36;q[2]=CODES[0];q[3]="10";q[30]="20261125161500";q[35]="10/10/100"
        quotes={d:{"close":10,"amount":100} for d in DATES}
        def dat(code,typ):return {"todayFundFlow":today,"todayFundTrend":trend,"historyFundFlow":hist}[typ],"https://example.com/"+typ
        with mock.patch.object(f,"qq_data",side_effect=dat),mock.patch.object(f,"get",return_value="~".join(q)):
            s=f.collect_stock(CODES[0],DATES,10,"tencent",quotes)
            self.assertEqual(s["windows"]["5"]["net_cny"],9)
            trend["minList"][0]["time"]="202611241500"
            with self.assertRaisesRegex(ValueError,"NOT_DATED_CLOSE"):f.collect_stock(CODES[0],DATES,10,"tencent",quotes)

    def test_whole_group_fallback(self):
        class Clock(dt.datetime):
            @classmethod
            def now(cls,tz=None):return cls(2026,11,25,19,0,tzinfo=tz)
        def collect(code,dates,frozen,provider,quotes):
            if provider=="tencent" and code==CODES[0]:raise ValueError("network")
            return stock(code,provider)
        with mock.patch.object(f.dt,"datetime",Clock),mock.patch.object(f,"read",return_value={"trade_date":DAY}),mock.patch.object(f.pre,"frozen_industry_rows",return_value=[{"code":c,"price":10} for c in CODES]),mock.patch.object(f.pre,"history_for",return_value={"history":[{"date":d} for d in DATES]}),mock.patch.object(f,"actual_quotes",return_value={}),mock.patch.object(f,"collect_stock",side_effect=collect):
            result=f.build(Path("."),A)
        g=result["groups"][0]
        self.assertEqual(g["provider"],"eastmoney")
        self.assertTrue(all(s["provider"]=="eastmoney" for s in g["stocks"].values()))
        self.assertEqual(g["attempts"][0]["errors"],{CODES[0]:"network"})

