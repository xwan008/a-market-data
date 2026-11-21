#!/usr/bin/env python3
"""Retrospective point-in-time quarter-acceleration shadow replay.

No production output, no model invocation, no trading, and no use of
future quotes in selection. Replays the currently frozen Python prescreen
on immutable November 2026 Git checkpoints, with the *same* historical
weekly core finance snapshot in both variants. Eastmoney F10 report
fields are added only when the announced/updated report was available at
that session.

Caveats: Current code retrospectively applied to old inputs is not the
original contemporary strategy. F10 point-in-time flags are necessary but
do not certify that later vendor revisions have been fully recovered.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import refresh_core_financial_only as finance_source
import prepare_trend_buy_candidates as admission
import build_trend_buy_manual_research as scanner
import build_full_market_price_structure as price_structure

# Each SHA is the original, independently time-stamped canonical candidate
# freeze from that market session. Do not replace with later branches.
CHECKPOINTS = [
    # All dates have original end-of-day confirmed SW3 handoffs and frozen
    # per-industry company/price data. Dates before 11/16 have no archived
    # canonical Top5 freeze, so we reconstruct candidates and label accordingly.
    ("2026-10-14", "13ef60313270cb5623fb900d2b489acac199804d"),
    ("2026-10-15", "63aff9b27d673b9538b7a8a0f55715aaee439978"),
    ("2026-10-16", "1a71d4aeed63c35d70905f8869578e893dd1b6bc"),
    ("2026-10-19", "e745298a2702e4f74d5e7b920626b329fcee5d24"),
    ("2026-10-20", "34613814cb6cdeeb631eaeeceb2d62befb17d918"),
    ("2026-10-21", "d91cb7c2ce1208554915eb628214be6fef195a25"),
    ("2026-10-22", "77b43e1ec5c432e8ab4b46b447bff343e559a484"),
    ("2026-10-23", "ef17f409853125431fb757d99ad4e12a5e2e796e"),
    ("2026-10-26", "34bda5a29493c14cea98155613443611e241bab1"),
    ("2026-11-03", "02a152cfefe88c9d00b764ed9a84dd044ab36f09"),
    ("2026-11-04", "130ab3e2521e624d8d8479a757c2df4875e65d98"),
    ("2026-11-05", "d93dc6dc2b4f3b9efb8c5ef2143f4204f2c8d8e1"),
    ("2026-11-16", "09decc254498c8c53d9d1f5ef2562a68c316f461"),
    ("2026-11-17", "a65d6852e2115ecf186865cc41ed90e890e08093"),
    ("2026-11-18", "8a03bba7bf8a7482f0262eccbdf0c257cec4f6bc"),
    ("2026-11-19", "19c1303a24168d59a9aad893bc0bcd78fe3b0e1c"),
    ("2026-11-20", "b8501ab00eefb96b5c4b9f794fa884a09fe5acad"),
]
HORIZONS = (1, 3, 5)
SOURCE = finance_source.SOURCE
BASELINE_VERSION = "ENTRY_FIRST_NO_QUOTAS"


def git(*args, cwd=ROOT, capture=True):
    p = subprocess.run(["git", *args], cwd=str(cwd), check=True,
                       text=True, capture_output=capture)
    return p.stdout.strip() if capture else ""


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def raw_financial_history(codes, batch_size=40, workers=4):
    """A single read-only F10 fetch reused across all historical sessions."""
    batches = [codes[i:i + batch_size] for i in range(0, len(codes), batch_size)]
    by_code = defaultdict(list)
    errors = []
    def query(group):
        return finance_source.query_batch(group, attempts=2)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(query, group): tuple(group) for group in batches}
        for task in as_completed(futures):
            group = futures[task]
            try:
                rows = task.result()
                for item in rows:
                    code = str(item.get("SECURITY_CODE") or "")
                    if code in group:
                        by_code[code].append(item)
            except Exception as exc:
                errors.append({"codes": list(group),
                               "error": type(exc).__name__ + ":" + str(exc)[:180]})
    return by_code, {
        "requested_companies": len(codes),
        "source_batches": len(batches),
        "source_failed_batches": len(errors),
        "source_failures": errors[:5],
    }


def attach_asof_acceleration(workspace, date, raw_financial):
    """Use contemporaneous finance snapshot if archived, otherwise clearly
    label a reconstructed F10 baseline; never imply it was a published Top5.
    """
    p=workspace/"data/research/core_profit_refresh_latest.json"
    reconstructed=not p.exists()
    if reconstructed:
        latest=read(workspace/"data/latest.json")
        stocks=latest.get("stocks") or {}
        original_records={}
        for code in stocks:
            item=finance_source.find_asof_row(raw_financial.get(code,[]),code,date)
            if item:
                original_records[code]=item
        old={"source":SOURCE,"asof_trade_date":date,"records":original_records}
        write(p,old)
    else:
        old=read(p)
        if old.get("source")!=SOURCE:
            raise ValueError("HISTORICAL_CORE_SOURCE_MISMATCH")
    kept=0
    verified=0
    unknown=0
    reasons=defaultdict(int)
    for code,historic in old.get("records",{}).items():
        computed=finance_source.find_asof_row(raw_financial.get(code,[]),code,date)
        if not computed or computed["report_date"]!=historic.get("report_date"):
            reasons["SOURCE_ASOF_OR_REPORT_DATE_MISMATCH"]+=1
            continue
        historic["quarterly_history"]=computed["quarterly_history"]
        historic["quarterly_acceleration"]=computed["quarterly_acceleration"]
        kept+=1
        if computed["quarterly_acceleration"]["status"]=="VERIFIED":
            verified+=1
        else:
            unknown+=1
            reasons[computed["quarterly_acceleration"].get("reason","UNKNOWN")]+=1
    write(p,old)
    return {
        "finance_baseline_mode":("RETROSPECTIVELY_RECONSTRUCTED_F10"
                                 if reconstructed else "CONTEMPORARY_ARCHIVED_F10"),
        "historical_core_records":len(old["records"]),
        "matched_point_in_time_reports":kept,
        "quarterly_acceleration_verified":verified,
        "quarterly_acceleration_unknown":unknown,
        "reasons":dict(reasons),
    }


def reconstruct_research_only(root, asof):
    """Replay all confirmed industry groups without weakening formal gates.

    Old checkpoints have no canonical original TOP5. An industry unable to
    supply at least one ranked company remains explicitly BLOCKED; it is not
    turned into a synthetic stock selection or silently omitted.
    """
    from copy import deepcopy
    with tempfile.TemporaryDirectory(prefix="retrospective-audit-") as tmp:
        empty=Path(tmp)/"empty_company_reviews.json"
        write(empty, {"schema_version":"trend_buy_company_reviews_v2",
                      "as_of_date":asof,"reviews":[]})
        lightweight=scanner.build(empty,audit_only=True)
    scan=deepcopy(lightweight)
    shadow_scan=deepcopy(lightweight)
    audited=scan["screen_audit"]["lightweight_scanned"]
    scan_by_code={row["code"]:row for row in audited}
    shadow_by_code={row["code"]:row for row in
                    shadow_scan["screen_audit"]["lightweight_scanned"]}
    if len(audited)!=len(scan_by_code):
        raise ValueError("RETROSPECTIVE_DUPLICATE_HARD_ELIGIBLE_COMPANY")
    per_industry=defaultdict(list)
    for row in audited:
        per_industry[row["industry_code"]].append(row["code"])
    index=read(root/"data/low_risk/index.json")
    evidence=read(root/"data/research/core_profit_refresh_latest.json")
    overlay={}
    evaluations={}
    for industry,codes in per_industry.items():
        frozen=admission.prescreen.frozen_industry_rows(root,index,industry,asof)
        peers=[row for row in frozen if row["code"] in set(codes)]
        if len(peers)!=len(codes):
            raise ValueError("RETROSPECTIVE_HARD_ELIGIBLE_FROZEN_SCOPE_MISMATCH")
        prepared=[]
        for row in peers:
            patch,why=admission.validated_core_patch(
                row,evidence["records"].get(row["code"]),asof)
            if why in ("VALIDATED","NO_NEW_FIELDS"):
                patch={**patch,"financial_publication_date_verified":True}
            if patch:
                overlay[row["code"]]=patch
            prepared.append({**row,**patch})
        baseline_scores=scanner.scores(prepared,financial_mode="CORE_FIRST")
        shadow_scores,quality=admission.quarterly_acceleration_shadow_scores(
            prepared,baseline_scores)
        for row,base,experimental in zip(peers,baseline_scores,shadow_scores):
            for target,metric in ((scan_by_code[row["code"]],base),
                                  (shadow_by_code[row["code"]],experimental)):
                target["fundamental_score"]=metric[0]
                target["growth"]=metric[1]
                target["quality"]=metric[2]
                target["valuation_match"]=metric[3]
                target["growth_risk"]=metric[5]
        evaluations[industry]=quality
    base=admission.prescreen.run(root,scan,industry_index=index,
                               financial_overlay=overlay)
    alt=admission.prescreen.run(root,shadow_scan,industry_index=index,
                              financial_overlay=overlay)
    shadow_by_sector={g["industry_code"]:g
                      for g in alt["industry_groups"]}
    groups=[]
    audits=[]
    for group in base["industry_groups"]:
        sector=group["industry_code"]
        experimental=shadow_by_sector[sector]
        baseline=group["research_codes"]
        variant=experimental["research_codes"]
        quality=evaluations[sector]
        quality.update({
            "industry_code":sector,
            "baseline_selected_codes":baseline,
            "acceleration_shadow_selected_codes":variant,
            "changed_out_codes":[x for x in baseline if x not in variant],
            "changed_in_codes":[x for x in variant if x not in baseline],
            "selection_changed":baseline!=variant,
            "reconstruction_eligible":bool(baseline and variant),
            "baseline_eligibility_count":group["eligible_with_new_technical_evidence"],
            "baseline_history_exclusions":group["history_exclusions"][:6],
        })
        groups.append({
            "industry_code":sector,
            "selected_codes":baseline,
            "selection_evidence":group["selection_evidence"],
        })
        audits.append(quality)
    return {
        "industries":groups,
        "quarterly_financial_acceleration_shadow":{"industries":audits},
    }


def replay_snapshot(workspace, day, raw_financial):
    # Redirect only the Python readers to immutable historical snapshots.
    # Nothing under the real project working tree changes.
    scanner.ROOT = workspace
    scanner.INDEX = workspace / "data/low_risk/index.json"
    scanner.TREND = workspace / "research/trend_handoff.json"
    price_structure.ROOT = workspace
    price_structure.HISTORY_DIR = workspace / "data/history_shards"
    price_structure.load_prefix_history.cache_clear()

    old_cwd = Path.cwd()
    try:
        os.chdir(workspace)
        archived_candidate=workspace/"research/trend_buy_candidates/latest.json"
        original=(read(archived_candidate) if archived_candidate.exists()
                  else None)
        if original and original["trade_date"]!=day:
            raise ValueError("ARCHIVE_DATE_MISMATCH")
        historical_handoff=read(workspace/"research/trend_handoff.json")
        if historical_handoff["trade_date"]!=day or not historical_handoff.get("signals"):
            raise ValueError("HISTORICAL_CONFIRMED_HANDOFF_INVALID")
        coverage=attach_asof_acceleration(workspace,day,raw_financial)
        if original:
            compared=admission.prepare(workspace)
            admission.validate_admission(workspace,compared)
        else:
            compared=reconstruct_research_only(workspace,day)

        baseline_groups = {x["industry_code"]: x["selected_codes"]
                           for x in compared["industries"]}
        frozen_groups = ({x["industry_code"]:x["selected_codes"]
                          for x in original["industries"]} if original else {})
        sector_names={}
        for signal in historical_handoff["signals"]:
            for code in signal.get("industry_codes") or []:
                sector_names[code]=signal.get("trend_name")
        audit_groups = compared["quarterly_financial_acceleration_shadow"]["industries"]
        groups = []
        for group in audit_groups:
            code = group["industry_code"]
            baseline = group["baseline_selected_codes"]
            variant = group["acceleration_shadow_selected_codes"]
            if baseline != baseline_groups[code]:
                raise ValueError("BASELINE_SHADOW_CONTRACT_MISMATCH")
            frozen = frozen_groups.get(code)
            groups.append({
                "industry_code": code,
                "confirmed_trend_name":sector_names.get(code),
                "frozen_formal_codes": frozen,
                "replayed_baseline_codes": baseline,
                "shadow_codes": variant,
                "replay_matches_original_freeze": (baseline==frozen
                                                    if original else None),
                "baseline_traceability":("ORIGINAL_TOP5_REPRODUCED"
                                         if original else "RETROSPECTIVE_RECONSTRUCTION"),
                "selection_changed":group["selection_changed"],
                "reconstruction_eligible":bool(baseline and variant),
                "baseline_history_eligible_count":group.get("baseline_eligibility_count"),
                "new_codes": group["changed_in_codes"],
                "removed_codes": group["changed_out_codes"],
                "quarterly_evidence_coverage_ratio": group["coverage_ratio"],
                "quarterly_rule_active": group["activated"],
                "eligible_count": group["eligible_count"],
                "available_count": group["available_count"],
                "rule_reason": group["reason"],
            })
        return {
            "date": day,
            "source_candidate_checkpoint": git("rev-parse", "HEAD", cwd=workspace),
            "historical_issuer_finance": coverage,
            "original_candidate_date":original["trade_date"] if original else None,
            "original_finance_snapshot_asof":(original["source"]["finance_report_asof_date"]
                                                if original else None),
            "baseline_traceability":("ARCHIVED_CANONICAL_CANDIDATE_TOP5"
                                     if original else "NO_ORIGINAL_TOP5_RECONSTRUCTED"),
            "confirmed_trend_names":sorted(set(sector_names.values())),
            "blocked_reconstruction_industry_count":sum(
                not group["reconstruction_eligible"] for group in groups),
            "groups": groups,
        }
    finally:
        os.chdir(old_cwd)
        price_structure.load_prefix_history.cache_clear()


def daily_price_panel(last_shards):
    by_code = {}
    days = []
    for path in sorted(last_shards.glob("*.json")):
        raw = read(path)
        for code, payload in (raw.get("stocks") or {}).items():
            rows = (payload or {}).get("history") or []
            close = {}
            for row in rows:
                date = str(row.get("date") or "")
                value = row.get("close")
                if date and isinstance(value, (float, int)) and math.isfinite(value) and value > 0:
                    close[date] = float(value)
            by_code[code] = close
            if code == "601288":
                days = sorted(close)
    if not days:
        raise ValueError("MARKET_TRADING_CALENDAR_REFERENCE_MISSING")
    return by_code, days


def returns(codes, dates, prices, decision, horizon):
    try:
        position = dates.index(decision)
    except ValueError:
        return {"status": "CENSORED", "reason": "NO_MARKET_CALENDAR_DATE"}
    if position + horizon >= len(dates):
        return {"status": "CENSORED", "reason": "FUTURE_SESSION_NOT_YET_OBSERVED"}
    future = dates[position + horizon]
    values = []
    missing = []
    for code in codes:
        quote = prices.get(code, {})
        initial, terminal = quote.get(decision), quote.get(future)
        if initial is None or terminal is None:
            missing.append(code)
        else:
            values.append((terminal / initial - 1) * 100)
    if not codes or missing:
        return {"status": "CENSORED", "reason": "MISSING_COMPANY_QUOTE",
                "missing_codes": missing}
    return {"status": "OBSERVED", "future_date": future,
            "company_count": len(values),
            "equal_weight_return_pct": round(statistics.mean(values), 5),
            "median_company_return_pct": round(statistics.median(values), 5),
            "losing_company_count": sum(x < 0 for x in values)}


def evaluate(history, prices, dates):
    matched = []
    all_groups = []
    for item in history:
        day = item["date"]
        for group in item["groups"]:
            base = group["replayed_baseline_codes"]
            shadow = group["shadow_codes"]
            outcomes = {}
            for horizon in HORIZONS:
                original = returns(base, dates, prices, day, horizon)
                alternate = returns(shadow, dates, prices, day, horizon)
                pair = {"baseline": original, "shadow": alternate}
                if original["status"] == alternate["status"] == "OBSERVED":
                    delta = (alternate["equal_weight_return_pct"]
                             - original["equal_weight_return_pct"])
                    pair["shadow_minus_baseline_pp"] = round(delta, 5)
                    matched.append({
                        "date": day, "industry_code": group["industry_code"],
                        "horizon": horizon, "baseline_return_pct": original["equal_weight_return_pct"],
                        "shadow_return_pct": alternate["equal_weight_return_pct"],
                        "difference_pp": round(delta, 5),
                    })
                outcomes[str(horizon)] = pair
            all_groups.append({**group, "date": day, "outcomes": outcomes})
    summary = {}
    for horizon in HORIZONS:
        candidates = [x for x in matched if x["horizon"] == horizon]
        summary[str(horizon)] = {
            "matched_industry_date_cohorts": len(candidates),
            "mean_baseline_return_pct": round(statistics.mean(
                x["baseline_return_pct"] for x in candidates), 5) if candidates else None,
            "mean_shadow_return_pct": round(statistics.mean(
                x["shadow_return_pct"] for x in candidates), 5) if candidates else None,
            "mean_shadow_minus_baseline_pp": round(statistics.mean(
                x["difference_pp"] for x in candidates), 5) if candidates else None,
            "shadow_improved_count": sum(x["difference_pp"] > 0 for x in candidates),
            "shadow_worsened_count": sum(x["difference_pp"] < 0 for x in candidates),
            "unchanged_count": sum(x["difference_pp"] == 0 for x in candidates),
        }
    return all_groups, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=Path("/tmp/quarterly_acceleration_backtest.json"))
    args = parser.parse_args()
    codes = sorted(read(ROOT / "data/latest.json")["stocks"])
    raw_financial, fetch_diagnostics = raw_financial_history(codes)
    if fetch_diagnostics["source_failed_batches"]:
        raise RuntimeError("BACKTEST_FINANCIAL_SOURCE_INCOMPLETE")
    prices, market_days = daily_price_panel(ROOT / "data/history_shards")
    replayed = []
    with tempfile.TemporaryDirectory(prefix="quarterly-finance-asof-") as tmp:
        workspace = Path(tmp) / "archived"
        for day, sha in CHECKPOINTS:
            git("fetch", "--depth=1", "origin", sha, capture=False)
            git("worktree", "add", "--detach", str(workspace), sha, capture=False)
            try:
                snapshot = replay_snapshot(workspace, day, raw_financial)
                replayed.append(snapshot)
                print("QUARTERLY_ASOF_REPLAY", json.dumps({
                    "day": day,
                    "baseline_traceability":snapshot["baseline_traceability"],
                    "groups": len(snapshot["groups"]),
                    "blocked_groups":snapshot["blocked_reconstruction_industry_count"],
                    "original_replay_matches":sum(x["replay_matches_original_freeze"] is True
                                                   for x in snapshot["groups"]),
                    "shadow_changes": sum(x["selection_changed"] for x in snapshot["groups"]),
                    "finance": snapshot["historical_issuer_finance"],
                }, ensure_ascii=False), flush=True)
            finally:
                git("worktree", "remove", "--force", str(workspace), capture=False)
    groups, summary = evaluate(replayed, prices, market_days)
    report = {
        "schema_version": 1,
        "kind": "quarterly_financial_acceleration_backtest",
        "mode": "RETROSPECTIVE_SHADOW_ONLY",
        "run_at": datetime.utcnow().isoformat() + "Z",
        "baseline": BASELINE_VERSION,
        "finance_source": SOURCE,
        "source_retrieval": fetch_diagnostics,
        "decision_dates": [x[0] for x in CHECKPOINTS],
        "asof_finance_cutoff": "REPORT_DATE_NOTICE_DATE_UPDATE_DATE",
        "group_count": len(groups),
        "selection_change_group_count":sum(x["selection_changed"] for x in groups),
        "reconstruction_blocked_group_count":sum(
            not x["reconstruction_eligible"] for x in groups),
        "original_freeze_replay_match_count":sum(
            x["replay_matches_original_freeze"] is True for x in groups),
        "original_freeze_replay_mismatch_count":sum(
            x["replay_matches_original_freeze"] is False for x in groups),
        "historically_reconstructed_group_count":sum(
            x["replay_matches_original_freeze"] is None for x in groups),
        "return_horizons_trading_days": list(HORIZONS),
        "forward_return_summary": summary,
        "sessions": replayed,
        "industry_sessions": groups,
        "limitations": [
            "Non-consecutive 2026-10-14 through 2026-11-20 confirmed sector checkpoints; no handoff-less dates are added.",
            "Dates before 2026-11-16 have no archived canonical Top5 freezes; the current Python prescreen is retrospectively applied to frozen contemporary market data.",
            "Dates before the first archived core-financial refresh have reconstructed F10 financial baselines, not contemporaneously versioned original finance archives.",
            "The current candidate algorithm is applied retrospectively to historical frozen datasets, not to contemporaneous executable trades.",
            "Vendor F10 revisions are screened by published and updated dates but original pre-revision versions are not independently archived.",
            "One-day, three-day, and five-day observed returns are close-to-close proxies, not READY entries, stop losses, trading costs or PnL.",
            "Unobserved future sessions and incomplete company prices are CENSORED, never filled.",
            "Shadow weights were selected before evaluating this sample, but this small, correlated sample cannot establish generalization.",
            "Market/industry macro conditions and fundamental changes can confound these comparisons.",
        ],
        "no_formal_publication": True,
    }
    write(args.output, report)
    print("QUARTERLY_ACCELERATION_BACKTEST_SUMMARY", json.dumps({
        "decision_dates":report["decision_dates"],
        "group_count":report["group_count"],
        "selection_change_group_count":report["selection_change_group_count"],
        "original_freeze_replay_match_count":report["original_freeze_replay_match_count"],
        "original_freeze_replay_mismatch_count":report["original_freeze_replay_mismatch_count"],
        "historically_reconstructed_group_count":report["historically_reconstructed_group_count"],
        "reconstruction_blocked_group_count":report["reconstruction_blocked_group_count"],
        "forward_return_summary":summary,
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
