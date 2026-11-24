#!/usr/bin/env python3
"""Render the official trend tables from the validated registry/handoff.

This is a read-only projection. It cannot discover, confirm, rank or route
industries. The research model may append context outside these tables.
"""
import argparse
import json
from pathlib import Path

try:
    from scripts.industry_lifecycle import industry_review_phase, industry_tracking_active
    from scripts.validate_trend_publication_pair import validate
except ModuleNotFoundError:
    from industry_lifecycle import industry_review_phase, industry_tracking_active
    from validate_trend_publication_pair import validate


def _cell(value):
    return str(value or "—").replace("|", "｜").replace("\n", " ").replace("\r", " ")


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(_cell(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def _phase_label(row):
    stage, decision, day = industry_review_phase(row)
    life = row.get("industry_lifecycle") or {}
    base = life.get("cutover_baseline") or {}
    inherited = not life.get("episodes") and bool(base)
    if decision == "INHERITED_CONFIRMED":
        return f"{stage or '—'}历史确认（沿用原主题阶段）"
    if decision == "PENDING":
        return f"{stage}验证中" + ("（承接历史阶段）" if inherited else "")
    if decision in {"CONFIRMED", "NOT_CONFIRMED"}:
        label = "确认" if decision == "CONFIRMED" else "未确认"
        return f"{stage}{label}（{day}）"
    return "待核验"


def _change(row):
    life = row.get("industry_lifecycle") or {}
    latest = (life.get("episodes") or [life.get("cutover_baseline") or {}])[-1]
    history = latest.get("state_history") or []
    if not history:
        return "延续原有状态"
    event = history[-1]
    before, after = event.get("from"), event.get("to")
    if before is None:
        return "新增"
    return "维持" if before == after else f"{before} → {after}"


def render(registry, handoff):
    errors = validate(registry, handoff)
    if errors:
        raise ValueError("正式趋势账本与交接文件不一致：" + "; ".join(errors))
    active, expired = [], []
    for theme in registry["trends"]:
        name = theme["trend_name"]
        for row in theme.get("industry_assessments") or []:
            display = name + "－" + row["industry_name"]
            phase = _phase_label(row)
            evidence = row.get("market_reason") or row.get("benefit_reason")
            if not industry_tracking_active(row):
                expired.append((display, phase, evidence))
                continue
            active.append((display, row["market_state"], phase, evidence, _change(row)))
    order = {"趋势确认": 0, "候选趋势": 1, "观察": 2}
    active.sort(key=lambda row: order[row[1]])
    parts = [f"### 完整趋势池｜{registry['trade_date']}",
             _table(["主题－三级行业", "当前市场状态", "D阶段", "核心证据", "本轮变化"], active)]
    if expired:
        parts += ["### 验证期限退出", _table(["主题－三级行业", "D阶段结论", "依据"], expired)]
    priority = [(signal["rank"], name) for signal in handoff["signals"]
                for name in signal["industry_display_names"]]
    parts += ["### 新仓优先方向",
              _table(["排名", "主题－三级行业"], priority) if priority else "本轮无合格确认行业。"]
    return "\n\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--handoff", required=True, type=Path)
    args = parser.parse_args()
    print(render(json.loads(args.registry.read_text("utf-8")),
                 json.loads(args.handoff.read_text("utf-8"))))


if __name__ == "__main__":
    main()
