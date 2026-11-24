import copy
import unittest
from top1_gate_research import project_top1


class GateTests(unittest.TestCase):
    def setUp(self):
        self.a = {'trade_date': '2026-11-24', 'industries': [{'industry_code': 'S1', 'selected_codes': ['A', 'B']}]}
        self.f = {'trade_date': '2026-11-24', 'status': 'COMPLETE', 'wait': [{'code': 'A', 'industry_code': 'S1', 'status': 'WAIT'}], 'ready': [{'code': 'B', 'industry_code': 'S1', 'status': 'READY'}]}
        self.s = {'trade_date': '2026-11-24', 'items': [{'industry_code': 'S1', 'candidate_codes': ['B', 'A'], 'top1_code': 'A'}]}

    def project(self):
        return project_top1(self.a, self.f, self.s)

    def test_wait_no_fallback(self):
        r = self.project()
        self.assertFalse(r['production_eligible'])
        self.assertEqual(r['items'], [{'industry_code': 'S1', 'top1_code': 'A', 'historical_risk_status': 'WAIT', 'research_route': 'OBSERVE_ONLY', 'other_ready_count': 1}])

    def test_ready(self):
        self.s['items'][0]['top1_code'] = 'B'
        self.assertEqual(self.project()['items'][0]['research_route'], 'CONDITIONAL_MONITOR')

    def test_drop_or_uncertain(self):
        for status in ('DROP', 'UNCERTAIN'):
            with self.subTest(status=status):
                self.f['wait'] = []
                self.f['drop'] = []
                self.f['uncertain'] = []
                self.f[status.lower()] = [{'code': 'A', 'industry_code': 'S1', 'status': status}]
                self.assertEqual(self.project()['items'][0]['research_route'], 'NO_MONITOR')

    def test_abstain(self):
        self.s['items'][0].update(top1_code=None, reason='missing evidence')
        self.assertEqual(self.project()['items'][0]['research_route'], 'NO_MONITOR')

    def test_invalid_inputs(self):
        for change in ('date', 'outsider', 'roster', 'duplicate', 'missing_risk', 'missing_reason'):
            with self.subTest(change=change):
                self.setUp()
                if change == 'date': self.s['trade_date'] = '2026-11-23'
                if change == 'outsider': self.s['items'][0]['top1_code'] = 'X'
                if change == 'roster': self.s['items'][0]['candidate_codes'] = ['A']
                if change == 'duplicate': self.s['items'].append(copy.deepcopy(self.s['items'][0]))
                if change == 'missing_risk': self.f['ready'] = []
                if change == 'missing_reason': self.s['items'][0]['top1_code'] = None
                with self.assertRaises(ValueError): self.project()


if __name__ == '__main__':
    unittest.main()
