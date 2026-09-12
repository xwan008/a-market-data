#!/usr/bin/env python3
"""Persisted research-accounting checks; these do not verify investment judgments."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DIMENSIONS = ("earnings_quality", "cashflow", "valuation")
SELECTED = {"winner", "differential_candidate", "research_uncertain"}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def evidence(value):
    return isinstance(value, list) and bool(value) and all(nonempty(v) for v in value)


def unique(items, key, label):
    require(isinstance(items, list), f"{label}: expected list")
    result = {}
    for item in items:
        require(isinstance(item, dict), f"{label}: expected object")
        code = item.get(key)
        require(nonempty(code), f"{label}: missing {key}")
        require(code not in result, f"{label}: duplicate {code}")
        result[code] = item
    return result


def table(path, columns, count, date):
    obj = read(path)
    require(obj.get("trade_date") == date, f"{path}: trade_date mismatch")
    require(obj.get("columns") == columns, f"{path}: columns mismatch")
    rows = obj.get("rows")
    require(isinstance(rows, list) and len(rows) == count, f"{path}: count mismatch")
    require(all(isinstance(row, list) and len(row) == len(columns) for row in rows),
            f"{path}: row length mismatch")
    return unique([dict(zip(columns, row)) for row in rows], "code", str(path))


def runtime(root):
    root = Path(root)
    meta = read(root / "meta.json")
    require(meta.get("runtime_kind") == "low_risk_research", "unexpected runtime kind")
    require(meta.get("runtime_validation", {}).get("status") == "passed", "runtime validation failed")
    date = meta["snapshot"]["trade_date"]
    require(meta["screening_count"] == meta["source_candidate_count"] == meta["snapshot"]["counts"]["candidates"],
            "runtime candidate counts differ")
    candidates = table(root / Path(meta["screening_file"]).name, meta["screening_columns"], meta["screening_count"], date)
    industries = table(root / Path(meta["industry_state_file"]).name, meta["industry_columns"], meta["industry_count"], date)
    require(all(c["industry_code"] in industries for c in candidates.values()), "runtime industry mapping missing")
    return meta, candidates, industries


def initialise(runtime_dir, output, run_id, locked_sha, notable_codes):
    require(IDENTIFIER.fullmatch(run_id), "invalid run_id")
    require(SHA.fullmatch(locked_sha), "locked_sha must be a full commit SHA")
    output = Path(output)
    require(not output.exists(), "output exists; refusing to overwrite an earlier run")
    meta, candidates, industries = runtime(runtime_dir)
    require(set(notable_codes) <= candidates.keys(), "notable code outside candidate pool")
    write(output / "run.json", {
        "run_id": run_id, "locked_sha": locked_sha,
        "trade_date": meta["snapshot"]["trade_date"], "stage": "collecting",
        "group_files": [], "notable_codes": sorted(set(notable_codes)),
    })
    # Pending is intentional: generating a template must never fabricate research.
    write(output / "industries.json", [{
        "industry_code": code, "decision": "pending", "reason": "", "source_refs": []
    } for code in sorted(industries)])


def validate(run_dir, runtime_dir, expected_sha):
    run_dir = Path(run_dir)
    run = read(run_dir / "run.json")
    require(IDENTIFIER.fullmatch(run.get("run_id", "")), "invalid run_id")
    require(SHA.fullmatch(expected_sha), "expected SHA must be a full commit SHA")
    require(run.get("locked_sha") == expected_sha, "run locked_sha differs from expected runtime SHA")
    stage = run.get("stage")
    require(stage in {"collecting", "allocation", "final"}, "invalid run stage")
    meta, candidates, source_industries = runtime(runtime_dir)
    require(run.get("trade_date") == meta["snapshot"]["trade_date"], "run trade_date mismatch")
    if stage == "collecting":
        return {"status": "incomplete", "publishable": False, "run_id": run["run_id"]}, {}

    industries = unique(read(run_dir / "industries.json"), "industry_code", "industries")
    require(industries.keys() == source_industries.keys(), "industry coverage is not exact")
    populated = {c["industry_code"] for c in candidates.values()}
    for code, item in industries.items():
        decision = item.get("decision")
        require(decision in {"research", "uncertain", "excluded", "no_candidates"}, f"industry {code}: unfinished decision")
        require(nonempty(item.get("reason")), f"industry {code}: missing reason")
        require(decision != "no_candidates" or code not in populated, f"industry {code}: candidates silently omitted")
        require(evidence(item.get("source_refs")), f"industry {code}: missing evidence")

    group_files = run.get("group_files")
    require(isinstance(group_files, list) and all(isinstance(p, str) for p in group_files), "group_files must be a list")
    require(len(group_files) == len(set(group_files)), "duplicate group file")
    require(all(re.fullmatch(r"groups/[A-Za-z0-9][A-Za-z0-9_-]{0,95}\.json", p) for p in group_files), "invalid group path")
    actual_files = {p.relative_to(run_dir).as_posix() for p in (run_dir / "groups").glob("*.json")}
    require(set(group_files) == actual_files, "group manifest does not match saved files")
    grouped, group_ids, selected, outcomes, used_files = {}, set(), set(), {}, ["run.json", "industries.json"]
    for filename in group_files:
        path = run_dir / filename
        require(not path.is_symlink(), "symlinks are not allowed")
        group = read(path)
        group_id = group.get("group_id")
        require(group_id == path.stem and group_id not in group_ids, "duplicate or mismatched group_id")
        group_ids.add(group_id)
        require(nonempty(group.get("business_basis")) and evidence(group.get("source_refs")), f"{group_id}: missing grouping evidence")
        members = unique(group.get("members"), "code", group_id)
        require(bool(members), f"{group_id}: empty group")
        winners = {code for code, member in members.items() if member.get("decision") in SELECTED}
        for code, member in members.items():
            require(code in candidates, f"{code}: outside candidate pool")
            require(code not in grouped, f"{code}: assigned to more than one primary group")
            require(industries[candidates[code]["industry_code"]]["decision"] in {"research", "uncertain"},
                    f"{code}: grouped despite excluded industry")
            decision = member.get("decision")
            require(decision in SELECTED | {"excluded"}, f"{code}: unfinished group decision")
            require(nonempty(member.get("reason")), f"{code}: missing group reason")
            comparisons = member.get("comparisons", {})
            for dimension in DIMENSIONS:
                assessment = comparisons.get(dimension, {})
                require(assessment.get("status") in {"assessed", "uncertain"}, f"{code}: missing {dimension} assessment")
                require(nonempty(assessment.get("finding")) and evidence(assessment.get("source_refs")),
                        f"{code}: missing {dimension} finding/evidence")
            if decision == "excluded":
                require(all(comparisons[d]["status"] == "assessed" for d in DIMENSIONS),
                        f"{code}: cannot exclude before earnings, cashflow AND valuation are assessed")
                alternatives = member.get("preferred_codes")
                require(isinstance(alternatives, list) and bool(alternatives) and set(alternatives) <= winners,
                        f"{code}: exclusion must name a retained competitor in the same group")
                require(nonempty(member.get("revisit_condition")), f"{code}: missing reconsideration condition")
            else:
                selected.add(code)
            grouped[code] = group_id
            outcomes[code] = {"name": candidates[code]["name"], "industry_code": candidates[code]["industry_code"],
                              "group_id": group_id, "allocation": decision, "reason": member["reason"], "record": filename}
            if decision in SELECTED and stage == "final":
                detail = member.get("detail_read", {})
                expected_path = meta["detail_file_template"].replace("{code}", code)
                require(detail.get("locked_sha") == expected_sha and detail.get("path") == expected_path
                        and detail.get("eof_confirmed") is True, f"{code}: missing pinned detail-read record")
                outcome = member.get("outcome", {})
                require(outcome.get("status") in {"recommended", "waiting", "excluded"}, f"{code}: missing final destination")
                require(outcome.get("stage") in {"company", "valuation", "entry", "asymmetry", "ranking"}, f"{code}: missing decision stage")
                require(nonempty(outcome.get("reason")) and evidence(outcome.get("source_refs")), f"{code}: missing final evidence")
                for flag in ("company_confirmed", "entry_admitted", "asymmetry_passed"):
                    require(type(outcome.get(flag)) is bool, f"{code}: missing {flag}")
                require(not outcome["entry_admitted"] or outcome["company_confirmed"], f"{code}: entry before company confirmation")
                require(not outcome["asymmetry_passed"] or outcome["entry_admitted"], f"{code}: asymmetry before entry")
                require(outcome["status"] != "recommended" or outcome["asymmetry_passed"], f"{code}: recommended before admission")
                outcomes[code]["outcome"] = outcome
        used_files.append(filename)

    expected_grouped = {code for code, c in candidates.items() if industries[c["industry_code"]]["decision"] in {"research", "uncertain"}}
    require(set(grouped) == expected_grouped, "candidate coverage incomplete: some eligible candidates have no group decision")
    for code in candidates.keys() - grouped.keys():
        industry = industries[candidates[code]["industry_code"]]
        outcomes[code] = {"name": candidates[code]["name"], "industry_code": candidates[code]["industry_code"],
                          "allocation": "excluded_industry", "reason": industry["reason"], "record": "industries.json"}
    notable = run.get("notable_codes")
    require(isinstance(notable, list) and all(isinstance(c, str) for c in notable), "notable_codes must be a list")
    require(len(notable) == len(set(notable)) and set(notable) <= candidates.keys(), "invalid notable_codes")
    final_outcomes = [v["outcome"] for v in outcomes.values() if "outcome" in v]
    counts = {
        "mechanical_candidate_count": len(candidates), "industry_coverage_count": len(industries),
        "eligible_industry_count": sum(i["decision"] in {"research", "uncertain"} for i in industries.values()),
        "comparison_group_count": len(group_ids), "deep_read_codes_count": len(selected),
        "company_confirmed_count": sum(o["company_confirmed"] for o in final_outcomes),
        "low_risk_entry_admission_count": sum(o["entry_admitted"] for o in final_outcomes),
        "asymmetry_passed_count": sum(o["asymmetry_passed"] for o in final_outcomes),
        "final_recommendation_count": sum(o["status"] == "recommended" for o in final_outcomes),
    }
    require(counts["final_recommendation_count"] <= 10, "more than 10 final recommendations")
    fingerprints = {p: hashlib.sha256((run_dir / p).read_bytes()).hexdigest() for p in sorted(used_files)}
    digest = hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest()
    return {"status": "passed", "publishable": stage == "final", "stage": stage,
            "run_id": run["run_id"], "locked_sha": expected_sha, "trade_date": run["trade_date"],
            "audit_sha256": digest, "file_sha256": fingerprints, "counts": counts,
            "deep_read_codes": sorted(selected), "notable_candidates": {c: outcomes[c] for c in notable},
            "limits": "Checks record completeness and consistency, not research truth or actual model reading."}, outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--runtime-dir", default="data/runtime")
    init.add_argument("--output", required=True)
    init.add_argument("--run-id", required=True)
    init.add_argument("--locked-sha", required=True)
    init.add_argument("--notable", nargs="*", default=[])
    check = commands.add_parser("validate")
    check.add_argument("run_dir")
    check.add_argument("--runtime-dir", default="data/runtime")
    check.add_argument("--expected-sha", required=True)
    check.add_argument("--report-dir", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialise(args.runtime_dir, args.output, args.run_id, args.locked_sha, args.notable)
            print(json.dumps({"status": "incomplete", "output": args.output}))
        else:
            report, outcomes = validate(args.run_dir, args.runtime_dir, args.expected_sha)
            write(Path(args.report_dir) / "validation.json", report)
            write(Path(args.report_dir) / "company_outcomes.json", outcomes)
            print(json.dumps(report, ensure_ascii=False))
            if not report["publishable"]:
                return 2
    except (ValueError, KeyError, TypeError, OSError) as exc:
        failure = {"status": "failed", "publishable": False, "error": str(exc)}
        if args.command == "validate":
            # Never leave an older successful report beside the failed current run.
            write(Path(args.report_dir) / "validation.json", failure)
            write(Path(args.report_dir) / "company_outcomes.json", {})
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
