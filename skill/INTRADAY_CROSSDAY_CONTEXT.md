# Intraday cross-day context contract

The GitHub Actions snapshot builder materializes **optional** historical references
directly into research/intraday_market_snapshot.json, the only live input used by
the ChatGPT intraday monitor aside from research/intraday_monitor_state.json.

- trends[*].history_context.seven_day: median current-constituent returns and
  positive-constituent ratio over **seven completed return intervals** through
  source_low_risk_trade_date (eight valid closing observations). Coverage and
  sample sizes must accompany any conclusion. These are not benchmark-relative
  returns. The snapshot does not publish board five_day or twenty_day metrics.
- low_risk_stocks[*].seven_day: individual seven-session return using the same
  eight-valid-close convention and prior close baseline as the board. An
  unavailable window is null, never a substituted legacy five-close figure.
  The materialized stock technical history is still used for structural context;
  legacy five-close research fields are retained upstream for compatibility but
  excluded from the intraday snapshot.
- trends[*].history_context.previous_trade_day: last successfully persisted
  intraday board scan from that **exact** preceding handoff trade date. It is
  **not** the official close, and same_industry_codes must be true before direct
  breadth comparisons. No previous day available means null, not a guess.
- low_risk_stocks[*].history_context: established multi-session stock K-line
  structure from validated, materialized low-risk parts, with the independently
  verified seven-session return replacing the legacy five-close figure.
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
