from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
from statistics import median

import fetch_market as market
import intraday_crossday_context as crossday
import trend_buy_handoff as trend_contract

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = ROOT / "research"
TREND_PATH = RESEARCH_DIR / "trend_handoff.json"
TREND_BUY_PATH = RESEARCH_DIR / "trend_buy_handoff.json"
TREND_BUY_FORMAL_PATH = RESEARCH_DIR / "trend_buy_formal_result.json"
SNAPSHOT_PATH = RESEARCH_DIR / "intraday_market_snapshot.json"
MANIFEST_ROOT = ROOT / "data" / "low_risk" / "by_industry"
HISTORY_CONTEXT_RUNTIME_FORMAT = "low_risk_industry_working_set_chunk"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def active_stock_handoff() -> tuple[dict, list[dict], str]:
    """One official handoff; validate exact SHA and dynamic Top5 membership."""
    handoff = read_json(TREND_BUY_PATH)
    if handoff.get("shadow") is not False or not handoff.get("source_formal_blob_sha") or not handoff.get("source_run_id"):
        raise ValueError("NO_VALID_TREND_BUY_HANDOFF")
    items = trend_contract.validate_items(handoff)
    formal_bytes = TREND_BUY_FORMAL_PATH.read_bytes()
    digest = hashlib.sha1(b"blob " + str(len(formal_bytes)).encode() + b"\0" + formal_bytes).hexdigest()
    formal = json.loads(formal_bytes)
    if (digest != handoff.get("source_formal_blob_sha")
        or formal.get("schema_version") != "trend_buy_result_v2"
        or formal.get("status") != "COMPLETE"
        or formal.get("production_eligible") is not True
        or formal.get("run_id") != handoff.get("source_run_id")
        or formal.get("trade_date") != handoff.get("trade_date")):
        raise ValueError("TREND_BUY_FORMAL_HANDOFF_MISMATCH")
    # The only production monitor universe is the *researched dynamic theme Top5*.
    # Never silently fall back to yesterday's unranked READY+WAIT population.
    if not isinstance(formal.get("top5_by_theme"), list):
        raise ValueError("TREND_BUY_FORMAL_DYNAMIC_TOP5_MISSING")
    projected = trend_contract.project(formal, digest, shadow=False)
    if items != projected["items"]:
        raise ValueError("TREND_BUY_FORMAL_HANDOFF_ITEM_MISMATCH")
    return handoff, items, "trend_buy_v2"


def round_or_none(value, digits: int = 4):
    if value is None:
        return None
    return round(float(value), digits)


def choose_quote(code: str, sina: dict[str, dict], tencent: dict[str, dict], trade_date: str | None) -> dict:
    s = sina.get(code) or {}
    t = tencent.get(code) or {}

    fresh_sources = []
    if market.source_is_fresh(s, trade_date):
        fresh_sources.append(("sina", s, t))
    if market.source_is_fresh(t, trade_date):
        fresh_sources.append(("tencent", t, s))

    if not fresh_sources:
        return {
            "name": s.get("name") or t.get("name"),
            "price": None,
            "prev_close": None,
            "change_pct": None,
            "quote_time": None,
            "primary_source": "none",
            "confidence": "invalid",
            "warnings": ["no_fresh_quote"],
        }

    source, base, other = fresh_sources[0]
    primary = market.positive_number(base.get("price"))
    secondary = market.positive_number(other.get("price")) if other else None
    validation = market.validate_price(
        primary_price=primary,
        secondary_price=secondary,
    )
    change_pct = market.calculate_change_pct(base.get("price"), base.get("prev_close"))
    warnings = list(validation.warnings)
    for name, item in (("sina", s), ("tencent", t)):
        if (
            item
            and market.positive_number(item.get("price")) is not None
            and not market.source_is_fresh(item, trade_date)
        ):
            warnings.append(f"{name}_date_unverified")
    warnings += market.validate_quote_fields(
        {
            "price": base.get("price"),
            "prev_close": base.get("prev_close"),
            "change_pct": change_pct,
        }
    )

    return {
        "name": base.get("name") or s.get("name") or t.get("name"),
        "price": round_or_none(base.get("price")),
        "prev_close": round_or_none(base.get("prev_close")),
        "change_pct": round_or_none(change_pct),
        "quote_time": market.parse_quote_time(base.get("date"), base.get("time")),
        "primary_source": source,
        "source_prices": {
            "sina": round_or_none(s.get("price")) if s else None,
            "tencent": round_or_none(t.get("price")) if t else None,
        },
        "confidence": validation.confidence,
        "warnings": sorted(set(warnings)),
    }


def metrics_for_codes(codes: list[str], quotes: dict[str, dict]) -> dict:
    usable = [
        quotes[code]
        for code in codes
        if code in quotes
        and quotes[code].get("confidence") in {"high", "medium"}
        and quotes[code].get("change_pct") is not None
    ]
    changes = [float(item["change_pct"]) for item in usable]
    up = sum(1 for x in changes if x > 0)
    down = sum(1 for x in changes if x < 0)
    flat = sum(1 for x in changes if x == 0)
    total = len(codes)
    quoted = len(usable)
    coverage = quoted / total if total else 0.0

    return {
        "company_count": total,
        "quoted_count": quoted,
        "coverage_ratio": round(coverage, 4),
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "up_ratio": round(up / quoted, 4) if quoted else None,
        "median_change_pct": round(median(changes), 4) if changes else None,
        "max_change_pct": round(max(changes), 4) if changes else None,
        "min_change_pct": round(min(changes), 4) if changes else None,
        "data_quality": (
            "READY"
            if coverage >= 0.90
            else "DEGRADED"
            if coverage >= 0.80
            else "DATA_INSUFFICIENT"
        ),
    }


def project_history_context(company: dict, source_trade_date: str | None) -> dict:
    return {
        "source_trade_date": source_trade_date,
        "history_confidence": company.get("history_confidence"),
        "close_change_7d_pct": round_or_none(company.get("close_change_7d_pct")),
        "trend_state": company.get("trend_state"),
        "break_state": company.get("break_state"),
        "latest_high": company.get("latest_high"),
        "latest_low": company.get("latest_low"),
        "invalidation": company.get("invalidation"),
    }


def load_history_contexts(
    trend_buy_items: list[dict],
    manifests: dict[str, dict],
    expected_trade_date: str | None,
) -> tuple[dict[str, dict], list[str], int]:
    """Load only the small materialized parts that contain monitored READY/WAIT stocks.

    History context is optional enrichment. Any read/validation failure is reported
    but must never block the live intraday snapshot.
    """
    contexts: dict[str, dict] = {}
    errors: list[str] = []
    required_parts: dict[str, dict] = {}

    for item in trend_buy_items:
        code = str(item.get("code") or "").zfill(6)
        industry_code = str(item.get("industry_code") or "")
        manifest = manifests.get(industry_code)
        if not manifest:
            errors.append(f"{code}:history_context_manifest_unavailable:{industry_code}")
            continue

        matched_part = None
        for part in manifest.get("parts") or []:
            part_codes = {str(x).zfill(6) for x in part.get("company_codes") or []}
            if code in part_codes:
                matched_part = part
                break

        if not matched_part:
            errors.append(f"{code}:history_context_part_not_found:{industry_code}")
            continue

        part_file = str(matched_part.get("file") or "")
        if not part_file:
            errors.append(f"{code}:history_context_part_file_missing:{industry_code}")
            continue

        entry = required_parts.setdefault(
            part_file,
            {
                "industry_code": industry_code,
                "part_number": matched_part.get("part_number"),
                "codes": set(),
            },
        )
        entry["codes"].add(code)

    part_read_count = 0
    for part_file, request in required_parts.items():
        try:
            payload = read_json(ROOT / part_file)
            part_read_count += 1

            if payload.get("runtime_format") != HISTORY_CONTEXT_RUNTIME_FORMAT:
                raise ValueError("runtime_format_mismatch")
            if expected_trade_date and payload.get("trade_date") != expected_trade_date:
                raise ValueError(
                    f"trade_date_mismatch:{payload.get('trade_date')}!={expected_trade_date}"
                )
            if payload.get("industry_code") != request["industry_code"]:
                raise ValueError("industry_identity_mismatch")
            if payload.get("part_number") != request["part_number"]:
                raise ValueError("part_number_mismatch")

            companies = {
                str(company.get("code") or "").zfill(6): company
                for company in payload.get("companies") or []
                if company.get("code")
            }
            for code in request["codes"]:
                company = companies.get(code)
                if not company:
                    errors.append(f"{code}:history_context_company_missing:{part_file}")
                    continue
                contexts[code] = project_history_context(
                    company,
                    expected_trade_date,
                )
        except Exception as exc:
            for code in request["codes"]:
                errors.append(
                    f"{code}:history_context_read_failed:{part_file}:"
                    f"{type(exc).__name__}:{exc}"
                )

    return contexts, errors, part_read_count


def main() -> int:
    now = datetime.now(market.TZ)
    trend = read_json(TREND_PATH)
    try:
        trend_buy_handoff, trend_buy_items, stock_handoff_kind = active_stock_handoff()
    except ValueError as exc:
        print(json.dumps({"error": "invalid_trend_buy_handoff", "detail": str(exc)}, ensure_ascii=False))
        return 2
    source_trend_trade_date = trend.get("trade_date")
    source_trend_buy_trade_date = trend_buy_handoff.get("trade_date")
    source_handoff_trade_date_consistent = bool(
        source_trend_trade_date
        and source_trend_buy_trade_date
        and source_trend_trade_date == source_trend_buy_trade_date
    )

    industries: dict[str, dict] = {}
    trends: dict[str, dict] = {}
    target_codes: set[str] = set()
    manifest_errors: list[str] = []
    manifests: dict[str, dict] = {}

    for signal in trend.get("signals") or []:
        trend_name = str(signal.get("trend_name") or "")
        grouped_codes: list[str] = []

        for industry_code, expected_name in zip(
            signal.get("industry_codes") or [],
            signal.get("industry_names") or [],
        ):
            manifest_path = MANIFEST_ROOT / industry_code / "manifest.json"
            try:
                manifest = read_json(manifest_path)
            except Exception as exc:
                manifest_errors.append(
                    f"{industry_code}:manifest_read_failed:{type(exc).__name__}:{exc}"
                )
                continue

            if manifest.get("industry_code") != industry_code:
                manifest_errors.append(f"{industry_code}:manifest_identity_mismatch")
                continue
            if (
                source_trend_buy_trade_date
                and manifest.get("trade_date") != source_trend_buy_trade_date
            ):
                manifest_errors.append(
                    f"{industry_code}:manifest_trade_date_mismatch:"
                    f"{manifest.get('trade_date')}!={source_trend_buy_trade_date}"
                )
                continue

            manifests[industry_code] = manifest
            company_codes = [str(code).zfill(6) for code in manifest.get("universe_company_codes") or []]
            target_codes.update(company_codes)
            grouped_codes.extend(company_codes)

            industries[industry_code] = {
                "industry_code": industry_code,
                "industry_name": manifest.get("industry_name") or expected_name,
                "manifest_trade_date": manifest.get("trade_date"),
                "trend_rank": signal.get("rank"),
                "trend_name": trend_name,
                "trend_state": signal.get("trend_state"),
                "market_state": signal.get("market_state"),
                "source_scope": "trend",
                "company_codes": company_codes,
            }

        trends[trend_name] = {
            "rank": signal.get("rank"),
            "trend_name": trend_name,
            "trend_state": signal.get("trend_state"),
            "market_state": signal.get("market_state"),
            "industry_codes": list(signal.get("industry_codes") or []),
            "company_codes": sorted(set(grouped_codes)),
        }

    trend_buy_only_attempted: set[str] = set()
    for item in trend_buy_items:
        target_codes.add(str(item.get("code") or "").zfill(6))
        industry_code = str(item.get("industry_code") or "")
        if (
            not industry_code
            or industry_code in industries
            or industry_code in trend_buy_only_attempted
        ):
            continue

        trend_buy_only_attempted.add(industry_code)
        manifest_path = MANIFEST_ROOT / industry_code / "manifest.json"
        try:
            manifest = read_json(manifest_path)
        except Exception as exc:
            manifest_errors.append(
                f"{industry_code}:trend_buy_only_manifest_read_failed:"
                f"{type(exc).__name__}:{exc}"
            )
            continue

        if manifest.get("industry_code") != industry_code:
            manifest_errors.append(
                f"{industry_code}:trend_buy_only_manifest_identity_mismatch"
            )
            continue
        if (
            source_trend_buy_trade_date
            and manifest.get("trade_date") != source_trend_buy_trade_date
        ):
            manifest_errors.append(
                f"{industry_code}:trend_buy_only_manifest_trade_date_mismatch:"
                f"{manifest.get('trade_date')}!={source_trend_buy_trade_date}"
            )
            continue

        manifests[industry_code] = manifest
        company_codes = [
            str(code).zfill(6)
            for code in manifest.get("universe_company_codes") or []
        ]
        target_codes.update(company_codes)
        industries[industry_code] = {
            "industry_code": industry_code,
            "industry_name": manifest.get("industry_name")
            or item.get("industry_name"),
            "manifest_trade_date": manifest.get("trade_date"),
            "trend_rank": None,
            "trend_name": item.get("trend_name"),
            "trend_state": None,
            "market_state": None,
            "source_scope": "trend_buy_only",
            "company_codes": company_codes,
        }


    history_contexts, history_context_errors, history_context_part_read_count = load_history_contexts(
        trend_buy_items,
        manifests,
        source_trend_buy_trade_date,
    )

    sina, sina_error = market.safe_fetch(market.fetch_sina_snapshot, "sina")
    tencent, tencent_error = market.safe_fetch(market.fetch_tencent_snapshot, "tencent")
    if not sina and not tencent:
        print(
            json.dumps(
                {"error": "all_sources_failed", "details": [sina_error, tencent_error]},
                ensure_ascii=False,
            )
        )
        return 2

    trade_date = market.infer_trade_date([sina, tencent], now)
    quotes = {
        code: choose_quote(code, sina, tencent, trade_date)
        for code in sorted(target_codes)
    }

    formal_prev_close_comparable_count = 0
    formal_prev_close_matched_count = 0
    for item in trend_buy_items:
        code = str(item.get("code") or "").zfill(6)
        formal_close = market.positive_number(item.get("current_price"))
        live_prev_close = market.positive_number((quotes.get(code) or {}).get("prev_close"))
        if formal_close is None or live_prev_close is None:
            continue
        formal_prev_close_comparable_count += 1
        diff_ratio = abs(formal_close - live_prev_close) / live_prev_close
        if diff_ratio <= 0.005:
            formal_prev_close_matched_count += 1

    if trend_buy_items:
        required_comparable = max(1, (len(trend_buy_items) * 8 + 9) // 10)
        formal_prev_close_alignment_ratio = (
            formal_prev_close_matched_count / formal_prev_close_comparable_count
            if formal_prev_close_comparable_count
            else 0.0
        )
        formal_prev_close_alignment_passed = bool(
            formal_prev_close_comparable_count >= required_comparable
            and formal_prev_close_alignment_ratio >= 0.80
        )
    else:
        formal_prev_close_alignment_ratio = 1.0
        formal_prev_close_alignment_passed = True

    for industry_code, industry in industries.items():
        codes = industry["company_codes"]
        industry["metrics"] = metrics_for_codes(codes, quotes)
        industry["stocks"] = {code: quotes.get(code) for code in codes}

    for trend_name, trend_item in trends.items():
        trend_item["metrics"] = metrics_for_codes(trend_item["company_codes"], quotes)

    # Cross-day references are independent of same-day previous_* transitions.
    board_history_audit = {
        "board_history_target_count": 0,
        "board_history_7d_available_count": 0,
        "board_previous_day_available_count": 0,
        "board_history_shard_read_count": 0,
        "board_history_errors": [],
    }
    stock_seven_day_contexts: dict[str, dict] = {}
    stock_seven_day_audit = {
        "stock_history_7d_target_count": 0,
        "stock_history_7d_available_count": 0,
        "stock_history_7d_shard_read_count": 0,
        "stock_history_7d_errors": [],
    }
    crossday_errors: list[str] = []
    crossday_archive = None
    previous_day_stock_refs: dict[str, dict] = {}
    if source_handoff_trade_date_consistent and trade_date:
        archive_healthy = True
        try:
            old_archive = crossday.read_archive()
        except (ValueError, TypeError, OSError, json.JSONDecodeError) as exc:
            old_archive = {"schema_version": 1, "result_kind": "a_share_intraday_crossday_archive", "days": []}
            archive_healthy = False
            crossday_errors.append(f"archive_read_invalid_not_overwritten:{type(exc).__name__}")
        try:
            merged_archive = crossday.merge_archive(old_archive, crossday.MONITOR_PATH, trade_date)
            contexts, board_history_audit = crossday.build_board_context(
                trends, source_trend_buy_trade_date, merged_archive
            )
            stock_seven_day_contexts, stock_seven_day_audit = crossday.build_stock_seven_day_context(
                {str(item["code"]).zfill(6) for item in trend_buy_items},
                source_trend_buy_trade_date,
            )
            for name, context in contexts.items():
                trend_item = trends[name]
                trend_item["history_context"] = context
                seven_day_status = context["seven_day"]["status"]
                trend_item["history_context_status"] = (
                    "available" if seven_day_status == "available" or context["previous_trade_day"]
                    else "partial" if seven_day_status == "partial" else "unavailable"
                )
            previous_day = next(
                (d for d in merged_archive["days"] if d["trade_date"] == source_trend_buy_trade_date),
                None,
            )
            if previous_day:
                previous_day_stock_refs = previous_day.get("stocks") or {}
            if archive_healthy:
                crossday_archive = merged_archive
        except (ValueError, TypeError, OSError, KeyError) as exc:
            crossday_errors.append(f"board_history_unavailable:{type(exc).__name__}")
    for trend_item in trends.values():
        trend_item.setdefault("history_context", None)
        trend_item.setdefault("history_context_status", "unavailable")
    # Prefer the same eight validated completed-session closes used by boards.
    # Seven-session returns require eight verified closing observations.
    for code, context in history_contexts.items():
        stock_seven = stock_seven_day_contexts.get(code) or {}
        context["close_change_7d_pct"] = stock_seven.get("close_change_7d_pct")
        context["seven_day_status"] = stock_seven.get("status", "unavailable")
        context["seven_day_window_sessions"] = 7

    trend_buy_stocks: dict[str, dict] = {}
    for item in trend_buy_items:
        code = str(item.get("code") or "").zfill(6)
        quote = quotes.get(code) or {}
        industry = industries.get(str(item.get("industry_code") or "")) or {}
        industry_median = ((industry.get("metrics") or {}).get("median_change_pct"))
        stock_change = quote.get("change_pct")
        relative_to_industry = None
        if stock_change is not None and industry_median is not None:
            relative_to_industry = round(float(stock_change) - float(industry_median), 4)

        trend_buy_stocks[code] = {
            "rank": item.get("rank"),
            "code": code,
            "company_name": item.get("company_name"),
            "trend_name": item.get("trend_name"),
            "industry_code": item.get("industry_code"),
            "industry_name": item.get("industry_name"),
            "formal_status": item.get("status"),
            "wait_reason": item.get("wait_reason"),
            "formal_current_price": item.get("current_price"),
            "trend_entry_plan": {k: item.get(k) for k in
                ("setup_type", "entry_zone", "entry_trigger", "max_entry_price",
                 "invalidation_price", "invalidation_rule", "initial_risk_pct",
                 "upside_to_resistance_R", "exit_plan")},
            "stock_handoff_kind": stock_handoff_kind,
            "price": quote.get("price"),
            "prev_close": quote.get("prev_close"),
            "change_pct": quote.get("change_pct"),
            "quote_time": quote.get("quote_time"),
            "confidence": quote.get("confidence"),
            "warnings": quote.get("warnings") or [],
            "industry_median_change_pct": industry_median,
            "relative_to_industry_pct": relative_to_industry,
            "in_monitored_industry_universe": code in set(industry.get("company_codes") or []),
            "trend_in_current_handoff": str(item.get("trend_name") or "") in trends,
            "history_context_status": "available" if code in history_contexts else "unavailable",
            "history_context": history_contexts.get(code),
            "seven_day": stock_seven_day_contexts.get(code),
            "previous_trade_day_monitor": (
                {"trade_date": source_trend_buy_trade_date,
                 "basis": "last_persisted_intraday_scan_not_official_close",
                 **previous_day_stock_refs[code]}
                if code in previous_day_stock_refs else None
            ),
        }

    expected_trend_buy_codes = {str(item["code"]).zfill(6) for item in trend_buy_items}
    trend_buy_stock_coverage_passed = (
        len(trend_buy_stocks) == len(trend_buy_items)
        and set(trend_buy_stocks) == expected_trend_buy_codes
        and all(
            trend_buy_stocks[str(item["code"]).zfill(6)]["formal_status"] == item["status"]
            and trend_buy_stocks[str(item["code"]).zfill(6)]["wait_reason"] == item.get("wait_reason")
            for item in trend_buy_items
        )
    )

    usable_quotes = sum(
        1
        for quote in quotes.values()
        if quote.get("confidence") in {"high", "medium"}
        and quote.get("change_pct") is not None
    )
    total_quotes = len(quotes)
    quote_coverage = usable_quotes / total_quotes if total_quotes else 0.0

    payload = {
        "schema_version": 2,
        "result_kind": "a_share_intraday_market_snapshot",
        "trade_date": trade_date,
        "captured_at": now.isoformat(),
        "timezone": "Asia/Shanghai",
        "market_status": market.clock_market_status(now),
        "source_trend_trade_date": source_trend_trade_date,
        "source_trend_buy_trade_date": source_trend_buy_trade_date,
        "stock_handoff_kind": stock_handoff_kind,
        "source_stock_handoff_path": "research/trend_buy_handoff.json",
        "source_trend_buy_handoff_run_id": trend_buy_handoff.get("source_run_id"),
        "source_trend_buy_handoff_schema_version": trend_buy_handoff.get("schema_version"),
        "source_status": {
            "sina": "ok" if sina else "failed",
            "tencent": "ok" if tencent else "failed",
            "errors": [x for x in (sina_error, tencent_error) if x],
        },
        "validation": {
            "status": (
                "passed"
                if trade_date == now.date().isoformat()
                and source_handoff_trade_date_consistent
                and trend_buy_stock_coverage_passed
                and formal_prev_close_alignment_passed
                and quote_coverage >= 0.90
                and not manifest_errors
                else "degraded"
            ),
            "source_handoff_dates_present": bool(
                source_trend_trade_date and source_trend_buy_trade_date
            ),
            "source_handoff_trade_date_consistent": source_handoff_trade_date_consistent,
            "trend_buy_handoff_item_count": len(trend_buy_items),
            "trend_buy_stock_count": len(trend_buy_stocks),
            "trend_buy_stock_coverage_passed": trend_buy_stock_coverage_passed,
            "formal_prev_close_comparable_count": formal_prev_close_comparable_count,
            "formal_prev_close_matched_count": formal_prev_close_matched_count,
            "formal_prev_close_alignment_ratio": round(formal_prev_close_alignment_ratio, 4),
            "formal_prev_close_alignment_passed": formal_prev_close_alignment_passed,
            "target_company_count": total_quotes,
            "usable_quote_count": usable_quotes,
            "quote_coverage": round(quote_coverage, 4),
            "manifest_errors": manifest_errors,
            "history_context_target_count": len(trend_buy_items),
            "history_context_available_count": len(history_contexts),
            "history_context_unavailable_count": max(0, len(trend_buy_items) - len(history_contexts)),
            "history_context_part_read_count": history_context_part_read_count,
            "history_context_errors": history_context_errors,
            **board_history_audit,
            **stock_seven_day_audit,
            "crossday_archive_days": len(crossday_archive["days"]) if crossday_archive else 0,
            "crossday_history_errors": crossday_errors,
        },
        "trends": trends,
        "industries": industries,
        "trend_buy_stocks": trend_buy_stocks,
    }

    if crossday_archive is not None:
        crossday.ARCHIVE_PATH.write_text(
            json.dumps(crossday_archive, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    SNAPSHOT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "trade_date": trade_date,
                "captured_at": now.isoformat(),
                "target_company_count": total_quotes,
                "usable_quote_count": usable_quotes,
                "quote_coverage": round(quote_coverage, 4),
                "industry_count": len(industries),
                "trend_buy_stock_count": len(trend_buy_stocks),
                "history_context_available_count": len(history_contexts),
                "history_context_part_read_count": history_context_part_read_count,
                "validation_status": payload["validation"]["status"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
