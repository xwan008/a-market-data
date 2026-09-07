from __future__ import annotations

import time
from datetime import datetime

import fetch_market as base


def normalize_easyquotation_timestamp(item: dict) -> tuple[object, object]:
    """Normalize provider timestamps without weakening date verification.

    Sina exposes separate ``date`` / ``time`` fields, while easyquotation 0.7.7's
    Tencent adapter exposes a Python ``datetime`` object. Preserve the native
    fields when present and use ``datetime`` only as a fallback.
    """
    quote_date = item.get("date")
    quote_time = item.get("time")
    raw_datetime = item.get("datetime")

    if raw_datetime is None or (quote_date and quote_time):
        return quote_date, quote_time

    parsed: datetime | None = None
    if isinstance(raw_datetime, datetime):
        parsed = raw_datetime
    else:
        text = str(raw_datetime).strip()
        for fmt in (None, "%Y%m%d%H%M%S", "%Y/%m/%d %H:%M:%S"):
            try:
                parsed = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
                break
            except ValueError:
                continue

    if parsed is not None:
        quote_date = quote_date or parsed.date().isoformat()
        quote_time = quote_time or parsed.time().replace(microsecond=0).isoformat()

    return quote_date, quote_time


def fetch_easyquotation_snapshot(provider: str, *, attempts: int = 3) -> dict[str, dict]:
    """Fetch one quote source with bounded retries and normalized timestamps."""
    import easyquotation

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            q = easyquotation.use(provider)
            raw = q.market_snapshot(prefix=True)
            out: dict[str, dict] = {}
            for symbol, item in raw.items():
                if not base.is_main_board_symbol(symbol):
                    continue
                code = base.normalize_code(symbol)
                quote_date, quote_time = normalize_easyquotation_timestamp(item)
                out[code] = {
                    "name": item.get("name"),
                    "price": item.get("now"),
                    "prev_close": item.get("close"),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "volume": item.get("turnover"),
                    "date": quote_date,
                    "time": quote_time,
                }
            return out
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt * 2)

    assert last_error is not None
    raise last_error


def retry_safe_fetch(
    fn,
    label: str,
    *,
    attempts: int = 2,
    delay_seconds: int = 2,
) -> tuple[dict[str, dict], str | None]:
    """Retry transient provider failures while preserving the original fail-closed result."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn(), None
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(delay_seconds * attempt)

    assert last_error is not None
    return {}, f"{label}:{type(last_error).__name__}:{last_error}"


def install_resilient_adapters() -> None:
    base.fetch_easyquotation_snapshot = fetch_easyquotation_snapshot
    base.fetch_sina_snapshot = lambda: fetch_easyquotation_snapshot("sina", attempts=3)
    base.fetch_tencent_snapshot = lambda: fetch_easyquotation_snapshot("tencent", attempts=3)
    base.safe_fetch = retry_safe_fetch


def main() -> int:
    install_resilient_adapters()
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
