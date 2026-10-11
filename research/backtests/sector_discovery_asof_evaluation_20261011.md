# Sector discovery: strict as-of replay (2026-10-11 validation)

**Scope:** 14 completed market sessions from 2026-09-14 through 2026-10-09, each read from the corresponding immutable daily-data Git commit in `sector_discovery_asof_manifest_20260917_20261009.json`. Candidates use only quotes and the 申万三级 industry membership stored in or before each day's commit. **No later snapshot is supplied to the discovery algorithm**. Historical `full_market_price_structure.json` was stale with reference_trade_date=2026-09-16 even at 2026-10-08; the replay instead reconstructs 3d/5d/available volume evidence from day-by-day committed quote snapshots. Unavailable volume history remains null.

## 2026-10-08/09 agriculture (industry-level, not a cross-industry concept)

| Date | Industry | Median daily return | Advance breadth | Result |
|---|---|---:|---:|---|
| 10-08 | 种子 S110101 | -0.455% | 33.33% | NO_COHERENT_TRIGGER |
| 10-08 | 粮食种植 S110102 | -0.128% | 50.00% | LOW_SAMPLE_OBSERVE (2 stocks) |
| 10-08 | 粮油加工 S110502 | +0.136% | 50.00% | NO_COHERENT_TRIGGER |
| 10-09 | 种子 S110101 | +6.624% | 100.00% | MODEL_REVIEW |
| 10-09 | 粮食种植 S110102 | +4.518% | 100.00% | LOW_SAMPLE_OBSERVE (2 stocks) |
| 10-09 | 粮油加工 S110502 | +2.471% | 66.67% | CAPACITY_DEFERRED |

- Oct 8: 53 industry discovery candidates, 20 selected for research, 33 deferred.
- Oct 9: 78 candidates, 20 selected, 58 deferred.
- **Interpretation:** The current industry-level breadth threshold cannot retrospectively be said to have detected a broad grain trend on Oct 8. Individual named stocks reacting earlier do not establish industry breadth. Do not tune the thresholds just to turn Oct 8 into a pass.

## Forward weakness proxy (NOT a speculative-trading false-positive rate)

An industry-date candidate is classified as weak follow-through when the median next-session or next-two-session stock return is <= 0 **and** its relative performance versus the all-stock median is <= 0. Fixed membership is from the original signal day. Later snapshot data is used solely for objective evaluation, never during detection.

| Population | Horizon | Evaluable signal observations | Weak follow-through | Rate |
|---|---|---:|---:|---:|
| Top20 model-review candidates | +1 full session | 216 | 108 | 50.00% |
| Top20 model-review candidates | +2 full sessions | 196 | 86 | 43.88% |
| All eligible industry candidates | +1 full session | 488 | 220 | 45.08% |
| All eligible industry candidates | +2 full sessions | 435 | 175 | 40.23% |

Right-censored and coverage-insufficient observations are excluded from rates, not silently marked as positive or negative. These are correlated *industry-date* observations, not independent trades or calibrated win rates. Results do not demonstrate that the program's Top20 ranking improves forward persistence over the full candidate pool; model-side evidence verification and existing entry gates remain essential.

**Limitations:** Shares in this repository are not the full A-share universe; concept membership is not tested; as-of historical daily-data commit timestamps sometimes occur after the scheduled 18:40 trend research time; early days have incomplete 20-day volume context; corporate actions and special cases need separate price-return diligence; only the 1–2 subsequent recorded trading sessions are evaluated. Do not interpret the proxy as a causal estimate of speculative sentiment, future profit, or trades taken.

Source: [strict replay GitHub Actions run](https://github.com/xwan008/a-market-data/actions/runs/38101121814) (success) and its `sector-asof-backtest-report` artifact. Current validation code: `scripts/backtest_sector_discovery_asof.py`.
