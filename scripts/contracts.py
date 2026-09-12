"""Shared deterministic data-contract constants.

Keep only cross-stage representation / eligibility constants here. Structural
admission thresholds remain owned and calculated by split_snapshot.py so there
is exactly one structural-filter truth source.
"""

YOY_UNIT = "percentage_points"
ELIGIBILITY_MAX_PRICE = 120.0
ELIGIBILITY_MAX_PE = 30.0
