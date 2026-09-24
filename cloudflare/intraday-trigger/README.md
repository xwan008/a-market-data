# A-share intraday snapshot trigger

This Cloudflare Worker invokes the existing `Update Intraday Market Snapshot`
workflow in `xwan008/a-market-data` at 09:37, 10:37, 13:37, and 14:37
Asia/Shanghai, Monday to Friday. The Cron expression is in UTC. It only has a
scheduled handler and does not publish a public HTTP endpoint.

## Deploy

1. Sign in to Cloudflare and GitHub as `xwan008`.
2. In GitHub, create a fine-grained personal access token with repository
   access limited to `xwan008/a-market-data` and **Actions: Read and write**.
   Set an expiration date and retain the token privately.
3. From this directory, run `npx wrangler login`, then
   `npx wrangler secret put GITHUB_TOKEN`. Paste the token at Wrangler's secret
   prompt; never commit it or paste it into chat.
4. Run `npx wrangler deploy`. Check that the Cron trigger is
   `37 1,2,5,6 * * MON-FRI`. Trigger propagation can take up to 15 minutes.
5. At the next trading-day slot, verify the Worker invocation succeeded, the
   GitHub run has event `workflow_dispatch` and conclusion `success`, and
   `research/intraday_market_snapshot.json` has a fresh `captured_at` with
   passed validation. Only then remove the old intraday file-write branch from
   the ChatGPT scheduler. Keep its 17:00 daily and Sunday weekly branches.

The Worker skips invocations delivered 4 minutes or more after their planned
time to leave room before the downstream `:45` intraday analysis. GitHub API
errors fail the invocation and appear in Cloudflare logs. The Worker never
writes the repository's file trigger or its market data directly.
