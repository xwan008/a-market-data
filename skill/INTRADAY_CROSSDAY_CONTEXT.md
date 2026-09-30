# Intraday cross-day context contract

The GitHub Actions snapshot builder materializes **optional** historical references
directly into research/intraday_market_snapshot.json, the only live input used by
the ChatGPT intraday monitor aside from research/intraday_monitor_state.json.

- trends[*].history_context.five_day: median current-constituent returns and
  positive-constituent ratio using **five completed sessions** through
  source_low_risk_trade_date (six valid closing observations). Coverage and
  sample sizes must accompany any conclusion. These are *not* benchmark-relative
  returns. No board twenty_day metric is produced; longer stock K-line history
  remains available for separate stock analysis.
- trends[*].history_context.previous_trade_day: last successfully persisted
  intraday board scan from that **exact** preceding handoff trade date. It is
  **not** the official close, and same_industry_codes must be true before direct
  breadth comparisons. No previous day available means null, not a guess.
- low_risk_stocks[*].history_context: established multi-session stock K-line
  evidence from validated, materialized low-risk parts.
- low_risk_stocks[*].previous_trade_day_monitor: separate prior-day observed
  stock execution state when the same code was monitored that day.
- research/intraday_crossday_archive.json: bounded 30-date rolling archive of
  the last persisted intraday scans. On a new day, snapshot generation archives
  the outgoing dated monitor state before today's monitor resets it.

**Never** populate previous_state, previous_structure_momentum,
previous_entry_action, previous_holding_action, or any stock previous_* from
cross-day context. They remain **same-day**, earlier and already persisted only.
Don't call the previous last scan an official closing observation; don't
classify a same-day deterioration solely from prior-day history. Cross-day
history is corroborating context, not a substitute for the live snapshot or
freshness/coverage gates.

History failure is optional enrichment: expose errors and coverage in snapshot
validation, but don't fabricate past states or suppress otherwise valid live
market data.
