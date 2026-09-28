// Cloudflare Worker: intraday snapshot dispatch ONLY.
// This Worker NEVER dispatches daily or weekly workflows.
// Set GH_TOKEN as a Cloudflare Secret. No public trigger endpoints.
//
// Existing Cron from earlier instructions is compatible:
//   * 1,2,5,6,9 * * *
// Only four exact Beijing-time slots below can dispatch, so UTC hour 9
// (Beijing 17:00) and all other minutes are ALWAYS ignored.
// If configuring Cron afresh, use: * 1,2,5,6 * * 1-5

const API = "https://api.github.com/repos/xwan008/a-market-data";
const WORKFLOW = "update-intraday-snapshot.yml";
const SLOTS = new Set(["09:37", "10:37", "13:17", "14:27"]);
const HOLIDAYS_2026_REMAINDER = new Set([
  "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
  "2026-10-05", "2026-10-06", "2026-10-07"
]);

function beijingTime(utc) {
  const d = new Date(utc.getTime() + 8 * 60 * 60 * 1000);
  const pad = n => String(n).padStart(2, "0");
  return {
    date: d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()),
    year: d.getUTCFullYear(),
    weekday: d.getUTCDay(),
    time: pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes())
  };
}

function githubHeaders(env) {
  return {
    Authorization: "Bearer " + env.GH_TOKEN,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
    "User-Agent": "a-share-scheduler"
  };
}

export default {
  // Public endpoint is read-only and cannot start GitHub Actions.
  async fetch() {
    return Response.json({ service: "a-share-scheduler", scope: "intraday-only" });
  },

  async scheduled(controller, env) {
    const planned = new Date(controller.scheduledTime);
    const cn = beijingTime(planned);

    // A scheduled execution must start close to its planned slot.
    if (Math.abs(Date.now() - planned.getTime()) > 90_000) {
      console.warn("Skip delayed Cron execution", cn);
      return;
    }

    // Fail closed if future exchange calendar has not been approved.
    if (cn.year !== 2026) {
      console.warn("Trading calendar not configured for year", cn.year);
      return;
    }
    if (cn.weekday < 1 || cn.weekday > 5 ||
        HOLIDAYS_2026_REMAINDER.has(cn.date) ||
        !SLOTS.has(cn.time)) {
      return;
    }

    if (!env.GH_TOKEN) throw new Error("GH_TOKEN Secret is missing");
    const headers = githubHeaders(env);
    const workflowPath = "/actions/workflows/" + WORKFLOW;

    // If old ChatGPT scheduling already started this snapshot,
    // do not create another run. This is best-effort deduplication.
    const runsResponse = await fetch(
      API + workflowPath + "/runs?per_page=15",
      { headers }
    );
    if (!runsResponse.ok) {
      throw new Error("Cannot check existing runs: HTTP " + runsResponse.status);
    }
    const runs = await runsResponse.json();
    const existing = (runs.workflow_runs || []).find(run => {
      const created = Date.parse(run.created_at);
      return Number.isFinite(created) &&
        created >= planned.getTime() - 120_000 &&
        created <= Date.now() + 30_000;
    });
    if (existing) {
      console.log("Existing intraday snapshot run: " + existing.id);
      return;
    }

    // ONLY the intraday snapshot workflow may be dispatched.
    const response = await fetch(API + workflowPath + "/dispatches", {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main", return_run_details: true })
    });
    if (response.status !== 200) {
      throw new Error("Intraday dispatch failed: HTTP " + response.status);
    }
    const result = await response.json();
    if (!result.workflow_run_id) {
      throw new Error("Intraday dispatch returned no workflow_run_id");
    }
    console.log("Dispatched intraday run", result.workflow_run_id, result.html_url);
  }
};
