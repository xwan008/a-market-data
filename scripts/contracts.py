"""Shared deterministic data-contract constants.

Keep only cross-stage representation constants and non-gating diagnostic
references here. Research admission must not use the legacy PE/price levels as
hard eligibility ceilings.
"""

YOY_UNIT = "percentage_points"

# Legacy low-risk reference levels retained for diagnostics only. They are not
# eligibility vetoes; Stage A / Stage B / final entry evaluation decide whether
# valuation and price are acceptable.
LEGACY_REFERENCE_MAX_PRICE = 120.0
LEGACY_REFERENCE_MAX_PE = 30.0
