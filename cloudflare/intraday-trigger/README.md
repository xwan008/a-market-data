# A-share intraday snapshot trigger

This Cloudflare Worker invokes the existing `Update Intraday Market Snapshot`
workflow in `xwan008/a-market-data` at 09:37, 10:37, 13:37, and 14:37
Asia/Shanghai, Monday to Friday. The Cron expression is in UTC. It only has a
scheduled handler and does not publish a public HTTP endpoint.

## Deploy in the browser (no local Git or CLI)

1. In Cloudflare, go to **Workers & Pages > Create application > Import a
   repository**. Connect GitHub and select `xwan008/a-market-data`.
2. Name the Worker `a-market-intraday-trigger`, set the production branch to
   `main` and the root directory to `cloudflare/intraday-trigger`, then select
   **Save and Deploy**. This directory contains the Wrangler configuration and
   source code. The first deployment can succeed without a token, but the
   scheduled handler will fail until the secret is added.
3. Create a fine-grained GitHub personal access token limited to
   `xwan008/a-market-data` with **Actions: Read and write**. Keep it private.
   In the Cloudflare Worker, select **Settings > Variables and Secrets > Add**,
   choose **Secret**, name it `GITHUB_TOKEN`, paste the token and **Deploy**.
4. Confirm the Worker has Cron trigger `37 1,2,5,6 * * MON-FRI`. Trigger
   propagation can take up to 15 minutes. Restrict Workers Builds watch paths
   to `cloudflare/intraday-trigger/**` so market-data commits do not redeploy
   the Worker.
5. At the next trading-day slot, verify the Worker invocation succeeded, the
   GitHub run has event `workflow_dispatch` and conclusion `success`, and
   `research/intraday_market_snapshot.json` has a fresh `captured_at` with
   passed validation. Only then remove the old intraday file-write branch from
   the ChatGPT scheduler. Keep its 17:00 daily and Sunday weekly branches.

The Worker skips invocations delivered 4 minutes or more after their planned
time to leave room before the downstream `:45` intraday analysis. GitHub API
errors fail the invocation and appear in Cloudflare logs. The Worker never
writes the repository's file trigger or its market data directly.
