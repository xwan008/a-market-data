"""Research-only TOP1 risk routing. Never creates a production handoff.
Reads already evaluated historical risk decisions; does not calculate or relax them.
"""
from collections import Counter


def project_top1(admission, formal, selections):
    day = admission['trade_date']
    if formal.get('trade_date') != day or formal.get('status') != 'COMPLETE':
        raise ValueError('FORMAL_DATE_OR_STATUS_MISMATCH')
    if selections.get('trade_date') != day:
        raise ValueError('SELECTION_DATE_MISMATCH')
    groups = admission['industries']
    by_industry = {g['industry_code']: g['selected_codes'] for g in groups}
    if len(by_industry) != len(groups) or any(not 1 <= len(c) <= 5 or len(set(c)) != len(c) for c in by_industry.values()):
        raise ValueError('INVALID_FROZEN_CANDIDATES')
    expected = {c: i for i, codes in by_industry.items() for c in codes}
    if len(expected) != sum(map(len, by_industry.values())):
        raise ValueError('DUPLICATE_FROZEN_CODE')
    risk = {}
    for status in ('READY', 'WAIT', 'DROP', 'UNCERTAIN'):
        for row in formal.get(status.lower(), []):
            code = row['code']
            if code in risk or expected.get(code) != row.get('industry_code') or row.get('status') != status:
                raise ValueError('RISK_SCOPE_OR_STATUS_MISMATCH')
            if code not in expected:
                raise ValueError('UNRESEARCHED_CODE')
            risk[code] = row
    if set(risk) != set(expected):
        raise ValueError('INCOMPLETE_RISK_EVIDENCE')
    picks = selections['items']
    if Counter(x['industry_code'] for x in picks) != Counter(by_industry.keys()):
        raise ValueError('SELECTION_GROUP_MISMATCH')
    result = []
    for pick in picks:
        industry = pick['industry_code']
        codes = by_industry[industry]
        if sorted(pick['candidate_codes']) != sorted(codes):
            raise ValueError('SELECTION_ROSTER_MISMATCH')
        code = pick['top1_code']
        if code is None:
            if not pick.get('reason'):
                raise ValueError('MISSING_ABSTENTION_REASON')
            status, decision = 'NO_SELECTION', 'NO_MONITOR'
        else:
            if code not in codes:
                raise ValueError('TOP1_OUTSIDE_ROSTER')
            status = risk[code]['status']
            decision = {'READY': 'CONDITIONAL_MONITOR', 'WAIT': 'OBSERVE_ONLY',
                        'DROP': 'NO_MONITOR', 'UNCERTAIN': 'NO_MONITOR'}[status]
        result.append({'industry_code': industry, 'top1_code': code,
                       'historical_risk_status': status, 'research_route': decision,
                       'other_ready_count': sum(risk[c]['status'] == 'READY' for c in codes if c != code)})
    return {'research_only': True, 'production_eligible': False, 'trade_date': day,
            'items': result}
