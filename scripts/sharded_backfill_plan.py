from __future__ import annotations

"""Shared deterministic partitioning helpers for full-market history backfills.

Partitioning is performed by the physical history-shard key (code[:4]) rather
than by individual stock code. That guarantees two matrix jobs never own the
same data/history_shards/<key>.json file.
"""

from collections import defaultdict


def partition_shard_keys(codes: list[str], partition_count: int) -> list[list[str]]:
    if partition_count <= 0:
        raise ValueError("partition_count must be positive")
    keys = sorted({str(code).zfill(6)[:4] for code in codes})
    parts: list[list[str]] = [[] for _ in range(partition_count)]
    for idx, key in enumerate(keys):
        parts[idx % partition_count].append(key)
    return parts


def codes_for_partition(codes: list[str], partition_index: int, partition_count: int) -> tuple[list[str], list[str]]:
    if partition_index < 0 or partition_index >= partition_count:
        raise ValueError("partition_index out of range")
    parts = partition_shard_keys(codes, partition_count)
    owned_keys = parts[partition_index]
    owned = set(owned_keys)
    selected = sorted(str(code).zfill(6) for code in codes if str(code).zfill(6)[:4] in owned)
    return selected, owned_keys


def partition_sizes(codes: list[str], partition_count: int) -> dict[int, int]:
    groups: dict[int, int] = defaultdict(int)
    for idx in range(partition_count):
        selected, _ = codes_for_partition(codes, idx, partition_count)
        groups[idx] = len(selected)
    return dict(groups)
