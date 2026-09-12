#!/usr/bin/env python3
"""Validate changed saved runs against runtime files at their recorded commit."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from research_audit import SHA, read, require, validate, write


def git(*args):
    return subprocess.check_output(["git", *args])


def main():
    event = read(os.environ["GITHUB_EVENT_PATH"])
    requested = os.environ.get("AUDIT_RUN_DIR", "").strip()
    if requested:
        require(re.fullmatch(r"data/research_runs/[A-Za-z0-9][A-Za-z0-9_-]{0,95}", requested), "invalid requested run directory")
        run_dirs = {requested}
    else:
        before = event.get("before") or event.get("pull_request", {}).get("base", {}).get("sha")
        if before and SHA.fullmatch(before) and before != "0" * 40:
            changed = git("diff", "--name-only", before, "HEAD", "--", "data/research_runs/").decode().splitlines()
        else:
            changed = git("ls-files", "data/research_runs/").decode().splitlines()
        run_dirs = set()
        for path in changed:
            match = re.match(r"(data/research_runs/[A-Za-z0-9][A-Za-z0-9_-]{0,95})/", path)
            require(match is not None, f"unexpected audit path: {path}")
            run_dirs.add(match[1])

    errors = []
    for run_dir in sorted(run_dirs):
        report_dir = Path("audit-reports") / Path(run_dir).name
        try:
            run = read(Path(run_dir) / "run.json")
            require(run.get("run_id") == Path(run_dir).name, "run_id must match saved directory")
            sha = run.get("locked_sha", "")
            require(SHA.fullmatch(sha), "invalid locked SHA")
            # Never execute scripts from the recorded data commit; only extract JSON.
            subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], check=True)
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                meta_bytes = git("show", f"{sha}:data/runtime/meta.json")
                (root / "meta.json").write_bytes(meta_bytes)
                meta = json.loads(meta_bytes)
                for key in ("screening_file", "industry_state_file"):
                    path = meta[key]
                    require(re.fullmatch(r"data/runtime/[A-Za-z0-9_-]+\.json", path), "unexpected runtime path")
                    (root / Path(path).name).write_bytes(git("show", f"{sha}:{path}"))
                report, outcomes = validate(run_dir, root, sha)
            report["audit_commit"] = git("rev-parse", "HEAD").decode().strip()
            write(report_dir / "validation.json", report)
            write(report_dir / "company_outcomes.json", outcomes)
            print(json.dumps({"run": run_dir, "status": report["status"], "publishable": report["publishable"]}))
        except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as exc:
            errors.append({"run": run_dir, "error": str(exc)})
            write(report_dir / "validation.json", {"status": "failed", "publishable": False, "error": str(exc)})
            write(report_dir / "company_outcomes.json", {})
    if errors:
        raise SystemExit(json.dumps(errors, ensure_ascii=False))
    if not run_dirs:
        print("No saved research runs changed; code tests only. No research result was validated.")


if __name__ == "__main__":
    main()
