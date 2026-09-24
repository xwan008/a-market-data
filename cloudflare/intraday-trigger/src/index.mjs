const DISPATCH_URL =
  "https://api.github.com/repos/xwan008/a-market-data/actions/workflows/update-intraday-snapshot.yml/dispatches";

// Beijing is UTC+08:00 throughout the year. These are its 09:37, 10:37,
// 13:37, and 14:37 weekday slots, expressed in UTC.
const UTC_HOURS = new Set([1, 2, 5, 6]);
const MAX_DELAY_MS = 4 * 60 * 1000;

export default {
  async scheduled(controller, env) {
    const scheduledAt = new Date(controller.scheduledTime);
    const now = Date.now();
    const weekday = scheduledAt.getUTCDay();

    if (
      controller.cron !== "37 1,2,5,6 * * MON-FRI" ||
      weekday < 1 ||
      weekday > 5 ||
      scheduledAt.getUTCMinutes() !== 37 ||
      !UTC_HOURS.has(scheduledAt.getUTCHours()) ||
      now < controller.scheduledTime ||
      now - controller.scheduledTime >= MAX_DELAY_MS
    ) {
      console.log("Skipping an unexpected or late intraday slot", {
        scheduledAt: scheduledAt.toISOString(),
        cron: controller.cron,
      });
      return;
    }

    if (!env.GITHUB_TOKEN) {
      throw new Error("GITHUB_TOKEN secret is missing");
    }

    const response = await fetch(DISPATCH_URL, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "a-market-intraday-trigger",
      },
      body: JSON.stringify({ ref: "main" }),
      signal: AbortSignal.timeout(10_000),
    });

    // GitHub's current API documents 200 with run details; older versions
    // returned 204 without a body. Both mean the dispatch was accepted.
    if (response.status !== 200 && response.status !== 204) {
      throw new Error(`GitHub workflow_dispatch failed: HTTP ${response.status}`);
    }

    console.log("Intraday workflow dispatch accepted", {
      scheduledAt: scheduledAt.toISOString(),
      status: response.status,
    });
  },
};
