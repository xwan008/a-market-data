from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", nargs="?", default="data/snapshot.json")
    parser.add_argument("--market-state", default="data/market_state.json")
    args = parser.parse_args()

    snapshot_path = Path(args.snapshot)
    market_path = Path(args.market_state)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    market = json.loads(market_path.read_text(encoding="utf-8"))

    if snapshot.get("trade_date") != market.get("trade_date"):
        raise RuntimeError(
            f"snapshot/market_state trade_date mismatch: {snapshot.get('trade_date')} vs {market.get('trade_date')}"
        )

    snapshot["market_state"] = market
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(
        f"market state attached: {market.get('trade_date')} "
        f"risk={market.get('risk_level')} trend={market.get('trend')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
