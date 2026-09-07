from __future__ import annotations

import argparse
import json
from pathlib import Path

VALUATION_FIELDS = ("valuation_date", "pe_dynamic", "pe_ttm", "pb", "market_cap")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def valuation_is_usable(item: dict) -> bool:
    return any(item.get(field) is not None for field in ("pe_dynamic", "pe_ttm", "pb", "market_cap"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", default="data/latest.json")
    parser.add_argument("--previous", default="data/latest.previous.json")
    args = parser.parse_args()

    current_path = Path(args.current)
    previous_path = Path(args.previous)
    if not current_path.exists() or not previous_path.exists():
        print("valuation fallback skipped: current or previous snapshot missing")
        return 0

    current = read_json(current_path)
    previous = read_json(previous_path)
    current_stocks = current.get("stocks") or {}
    previous_stocks = previous.get("stocks") or {}
    total = len(current_stocks)
    stats = current.setdefault("fundamental_stats", {})
    fresh_usable = int(stats.get("valuation_usable") or 0)

    # Only use fallback when the fresh cross-section is materially incomplete.
    # A healthy fresh valuation fetch always wins over cached values.
    if total and fresh_usable / total >= 0.95:
        stats["valuation_fresh_usable"] = fresh_usable
        stats["valuation_stale_fallback"] = 0
        print(f"valuation fallback not needed: fresh={fresh_usable}/{total}")
        write_json(current_path, current)
        return 0

    restored = 0
    for code, quote in current_stocks.items():
        fundamentals = quote.get("fundamentals") or {}
        if valuation_is_usable(fundamentals):
            continue

        old = ((previous_stocks.get(code) or {}).get("fundamentals") or {})
        if not valuation_is_usable(old):
            continue

        for field in VALUATION_FIELDS:
            fundamentals[field] = old.get(field)

        sources = fundamentals.setdefault("sources", {})
        sources["valuation"] = "previous_verified_snapshot"
        warnings = set(fundamentals.get("warnings") or [])
        warnings.discard("valuation_unavailable")
        warnings.add("valuation_stale_fallback")
        fundamentals["warnings"] = sorted(warnings)
        quote["fundamentals"] = fundamentals
        restored += 1

    effective = sum(
        1
        for quote in current_stocks.values()
        if valuation_is_usable(quote.get("fundamentals") or {})
    )
    stats["valuation_fresh_usable"] = fresh_usable
    stats["valuation_stale_fallback"] = restored
    stats["valuation_usable"] = effective
    stats["pe_dynamic_usable"] = sum(
        1 for q in current_stocks.values() if ((q.get("fundamentals") or {}).get("pe_dynamic") is not None)
    )
    stats["pe_ttm_usable"] = sum(
        1 for q in current_stocks.values() if ((q.get("fundamentals") or {}).get("pe_ttm") is not None)
    )
    stats["pb_usable"] = sum(
        1 for q in current_stocks.values() if ((q.get("fundamentals") or {}).get("pb") is not None)
    )

    write_json(current_path, current)
    print(
        json.dumps(
            {
                "valuation_fresh_usable": fresh_usable,
                "valuation_stale_fallback": restored,
                "valuation_effective_usable": effective,
                "stocks": total,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
