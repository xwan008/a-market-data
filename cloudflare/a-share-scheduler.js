// A-share scheduler: Cloudflare Cron -> existing GitHub Actions.
// No public endpoint can dispatch workflows. GH_TOKEN is a Cloudflare Secret.
// Cron to configure in Cloudflare dashboard (UTC): * 1,2,5,6,9 * * *

const OWNER = "xwan008";
const REPO = "a-market-data";
const API = "https://api.github.com/repos/" + OWNER + "/" + REPO;
const MAX_DELAY_MS = 90_000;

// Official SSE closures for the REMAINDER of 2026. Update before 2027.
// Saturdays and Sundays are handled separately.
const CLOSED_2026 = new Set([
  "2026-10-01", "2026-10-02", "2026-10-03",
  "2026-10-04", "2026-10-05", "2026-10-06",
  "2026-10-07"
]);

function chinaTime(utcDate) {
  const d = new Date(utcDate.getTime() + 8 * 60 * 60 * 1000);
  const pad = n => String(n).padStart(2, "0");
  return {
    date: d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()),
    weekday: d.getUTCDay(),
    hourMinute: pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()),
    year: d.getUTCFullYear()
  };
}

async function githubRequest(env, path, options = {}) {
  const response = await fetch(API + path, {
    ...options,
    headers: {
      Authorization: "Bearer " + env.GH_TOKEN,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2026-03-10",
      "User-Agent": "a-share-scheduler",
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    throw new Error("GitHub HTTP " + response.status + ": " + path);
  }
  return response;
}

async function dispatch(env, workflow, slotTime) {
  // Avoid a second run if either Cloudflare or the previous ChatGPT
  // scheduler already started THIS SAME workflow near this time.
  // This is best-effort deduplication, not a durable distributed lock.
  const path = "/actions/workflows/" + workflow;
  const listResponse = await githubRequest(env, path + "/runs?per_page=15");
  const list = await listResponse.json();
  const earlierRun = (list.workflow_runs || []).find(run => {
    const createdAt = Date.parse(run.created_at);
    return Number.isFinite(createdAt) &&
      createdAt >= slotTime.getTime() - 2 * 60_000 &&
      createdAt <= Date.now() + 30_000;
  });
  if (earlierRun) {
    console.log(JSON.stringify({
      status: "skipped_existing_run",
      workflow,
      run_id: earlierRun.id,
      run_url: earlierRun.html_url
    }));
    return;
  }

  const response = await githubRequest(env, path + "/dispatches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main", return_run_details: true })
  });
  if (response.status !== 200) {
    throw new Error("Dispatch returned unexpected status " + response.status);
  }
  const result = await response.json();
  if (!result.workflow_run_id) {
    throw new Error("Dispatch returned no workflow_run_id");
  }
  console.log(JSON.stringify({
    status: "dispatched",
    workflow,
    run_id: result.workflow_run_id,
    run_url: result.html_url
  }));
}

export default {
  // Public site exposes HEALTH ONLY. It never dispatches GitHub jobs.
  async fetch() {
    return Response.json({
      service: "a-share-scheduler",
      mode: "scheduled-only"
    });
  },

  async scheduled(controller, env) {
    const scheduledAt = new Date(controller.scheduledTime);
    const delayedBy = Date.now() - scheduledAt.getTime();
    if (delayedBy > MAX_DELAY_MS || delayedBy < -30_000) {
      console.warn("Skipping late/invalid cron invocation: " + delayedBy + " ms");
      return;
    }

    const cn = chinaTime(scheduledAt);
    const weekdays = cn.weekday >= 1 && cn.weekday <= 5;
    let workflow = null;

    // The weekly refresh is allowed on Sundays, independent of exchange holidays.
    if (cn.hourMinute === "17:00" && cn.weekday === 0) {
      workflow = "update-weekly-research.yml";
    } else if (weekdays) {
      // Fail closed when the next year's official exchange calendar is not set.
      if (cn.year !== 2026) {
        console.error("No approved A-share trading calendar for " + cn.year);
        return;
      }
      if (CLOSED_2026.has(cn.date)) {
        console.log("Exchange closed: " + cn.date);
        return;
      }
      const intraday = new Set(["09:37", "10:37", "13:17", "14:27"]);
      if (intraday.has(cn.hourMinute)) {
        workflow = "update-intraday-snapshot.yml";
      } else if (cn.hourMinute === "17:00") {
        workflow = "update-data.yml";
      }
    }

    if (!workflow) return;
    if (!env.GH_TOKEN) throw new Error("GH_TOKEN Cloudflare Secret is missing");
    await dispatch(env, workflow, scheduledAt);
  }
};
