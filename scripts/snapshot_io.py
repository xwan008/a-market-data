from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO


_EXPANDED_DICT_PATHS = {
    ("industry_state", "level3"),
    ("candidates",),
}


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _write_value(handle: TextIO, value: Any, path: tuple[str, ...]) -> None:
    if isinstance(value, dict) and path in _EXPANDED_DICT_PATHS:
        handle.write("{")
        if value:
            handle.write("\n")
            items = list(value.items())
            for index, (key, item) in enumerate(items):
                handle.write(json.dumps(str(key), ensure_ascii=False))
                handle.write(":")
                handle.write(_compact(item))
                handle.write(",\n" if index < len(items) - 1 else "\n")
        handle.write("}")
        return

    if isinstance(value, dict) and path == ("industry_state",):
        handle.write("{")
        items = list(value.items())
        for index, (key, item) in enumerate(items):
            handle.write(json.dumps(str(key), ensure_ascii=False))
            handle.write(":")
            _write_value(handle, item, path + (str(key),))
            if index < len(items) - 1:
                handle.write(",")
        handle.write("}")
        return

    handle.write(_compact(value))


def write_snapshot(path: Path, payload: dict[str, Any]) -> None:
    """Write valid JSON with bounded logical lines while preserving payload semantics.

    The whole file stays compact enough for GitHub's Contents API, while the two
    largest mappings (industry_state.level3 and candidates) are emitted one entry
    per line so callers can safely retrieve deterministic line ranges.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    items = list(payload.items())
    with path.open("w", encoding="utf-8") as handle:
        handle.write("{\n")
        for index, (key, value) in enumerate(items):
            handle.write(json.dumps(str(key), ensure_ascii=False))
            handle.write(":")
            _write_value(handle, value, (str(key),))
            handle.write(",\n" if index < len(items) - 1 else "\n")
        handle.write("}\n")
