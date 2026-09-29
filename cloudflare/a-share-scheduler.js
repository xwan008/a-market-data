// A-share unified GitHub Actions scheduler: intraday + daily + weekly.
// GitHub Actions remains the data producer. This Worker only DISPATCHES.
// Keep GH_TOKEN in Cloudflare Secrets; public HTTP requests NEVER trigger jobs.
//
// Cloudflare Cron Triggers use UTC; configure FOUR rules total:
//   37 1,2 * * MON-FRI  => Beijing 09:37, 10:37 (intraday)
//   17 5 * * MON-FRI    => Beijing 13:17 (intraday)
//   27 6 * * MON-FRI    => Beijing 14:27 (intraday)
//   0,5,10 9 * * *      => Beijing 17:00, 17:05, 17:10
// At 17:00/05/10: trading weekdays = daily; Sunday = weekly; Saturday = NO-OP.
// 17:05 and 17:10 are recovery checks, NOT unconditional extra workflow runs.
// No built-in scheduled() request is allowed outside the clock windows below.

const API = "https://api.github.com/repos/xwan008/a-market-data";
const WORKFLOWS = Object.freeze({
  intraday: "update-intraday-snapshot.yml",
  daily: "update-data.yml",
  weekly: "update-weekly-research.yml"
});
const INTRADAY_SLOTS = new Set(["09:37", "10:37", "13:17", "14:27"]);
const FALLBACK_17 = new Set(["17:00", "17:05", "17:10"]);

// Official SSE 2026 holiday list for dates remaining after 2026-09-29.
// Review official SSE/SZSE calendars and update before 2027.
const CLOSED_2026 = new Set([
  "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
  "2026-10-05", "2026-10-06", "2026-10-07"
]);

function beijingTime(date) {
  const d = new Date(date.getTime() + 8 * 60 * 60 * 1000);
  const pad = n => String(n).padStart(2, "0");
  return {
    date: d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()),
    year: d.getUTCFullYear(),
    weekday: d.getUTCDay(), // JS getUTCDay: 0=Sunday, 1=Monday, ... 6=Saturday
    time: pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes())
  };
}

function headers(env) {
  return {
    Authorization: "Bearer " + env.GH_TOKEN,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
    "User-Agent": "a-share-scheduler"
  };
}

async function recentWorkflowRuns(env, workflow, count = 20) {
  const url = API + "/actions/workflows/" + workflow + "/runs?per_page=" + count;
  const response = await fetch(url, { headers: headers(env) });
  if (!response.ok) {
    throw new Error("RUN_LOOKUP_FAILED " + workflow + " HTTP " + response.status);
  }
  const result = await response.json();
  return result.workflow_runs || [];
}

async function dispatch(env, workflow, extraInputs) {
  const body = { ref: "main", return_run_details: true };
  if (extraInputs) body.inputs = extraInputs;

  const response = await fetch(
    API + "/actions/workflows/" + workflow + "/dispatches",
    {
      method: "POST",
      headers: { ...headers(env), "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }
  );
  if (response.status !== 200) {
    // 204 without an ID may have dispatched. Do NOT retry in this invocation.
    throw new Error("DISPATCH_UNCONFIRMED " + workflow + " HTTP " + response.status);
  }
  const result = await response.json();
  if (!result.workflow_run_id) {
    throw new Error("DISPATCH_UNCONFIRMED " + workflow + " missing run ID");
  }
  console.log(JSON.stringify({
    event: "DISPATCHED", workflow,
    run_id: result.workflow_run_id, run_url: result.html_url
  }));
}

async function runIntraday(env, planned) {
  const workflow = WORKFLOWS.intraday;
  const runs = await recentWorkflowRuns(env, workflow, 15);
  // Preserve the existing snapshot dedupe window (2 minutes before planned).
  const existing = runs.find(run => {
    const created = Date.parse(run.created_at);
    return Number.isFinite(created) &&
      created >= planned.getTime() - 120_000 &&
      created <= Date.now() + 30_000;
  });
  if (existing) {
    console.log(JSON.stringify({
      event: "SKIP_EXISTING", workflow, run_id: existing.id
    }));
    return;
  }
  await dispatch(env, workflow);
}

function in17Window(planned) {
  const expected = beijingTime(planned);
  const actual = beijingTime(new Date());
  // Delayed scheduling is accepted ONLY within the original 17:00 tolerance.
  return actual.date === expected.date &&
    actual.time >= "16:50" && actual.time <= "17:10";
}

async function run17(env, cn) {
  const weekly = cn.weekday === 0;
  const workflow = weekly ? WORKFLOWS.weekly : WORKFLOWS.daily;
  const anchor = new Date(cn.date + "T17:00:00+08:00");
  const runs = await recentWorkflowRuns(env, workflow, 30);

  // A weekly refresh successfully completed after Friday's close is
  // already current for this Sunday's run. Keep the full-data job untouched.
  if (weekly) {
    const friClose = anchor.getTime() - 50 * 60 * 60 * 1000;
    const alreadyCurrent = runs.some(run =>
      run.conclusion === "success" &&
      Date.parse(run.created_at) >= friClose &&
      Date.parse(run.created_at) <= Date.now() + 30_000
    );
    if (alreadyCurrent) {
      console.log(JSON.stringify({ event: "SKIP_WEEKLY_ALREADY_DONE", workflow }));
      return;
    }
  }

  // All recovery checks refer to the SAME 17:00 slot: no duplicate
  // workflow runs after a queued/in-progress/successful attempt.
  const start = new Date(cn.date + "T16:50:00+08:00").getTime();
  const attempts = runs.filter(run => {
    const created = Date.parse(run.created_at);
    return Number.isFinite(created) &&
      created >= start && created <= Date.now() + 30_000;
  });

  if (attempts.some(run => run.conclusion === "success")) {
    console.log(JSON.stringify({ event: "SKIP_SUCCESSFUL", workflow }));
    return;
  }
  if (attempts.some(run =>
    run.status === "queued" || run.status === "in_progress" ||
    run.status === "waiting" || run.status === "requested" ||
    run.status === "pending"
  )) {
    console.log(JSON.stringify({ event: "SKIP_ALREADY_RUNNING", workflow }));
    return;
  }
  if (attempts.length >= 2) {
    console.error(JSON.stringify({
      event: "TWO_ATTEMPTS_EXHAUSTED", workflow,
      run_ids: attempts.map(run => run.id)
    }));
    return;
  }

  // Existing daily job implements full data/low-risk validation and skips
  // an already-fresh dataset only when Cloudflare passes skip_if_fresh.
  // Manual and push workflow behavior remains unchanged.
  const inputs = weekly ? undefined : { skip_if_fresh: "true" };
  await dispatch(env, workflow, inputs);
}

export default {
  // No public dispatch endpoint: only Cloudflare Cron may call scheduled().
  async fetch() {
    return Response.json({
      service: "a-share-scheduler",
      mode: "scheduled-only",
      scope: ["intraday", "daily", "weekly"],
      release: "2026-09-29-unified"
    }, { headers: { "Cache-Control": "no-store" } });
  },

  async scheduled(controller, env) {
    const planned = new Date(controller.scheduledTime);
    const cn = beijingTime(planned);

    // Weekly refresh must run on Sundays even on an exchange holiday.
    if (cn.weekday === 0 && FALLBACK_17.has(cn.time)) {
      if (!in17Window(planned)) return;
      if (!env.GH_TOKEN) throw new Error("GH_TOKEN Secret is missing");
      await run17(env, cn);
      return;
    }

    // Saturday and all unapproved future trading calendars fail closed.
    if (cn.weekday < 1 || cn.weekday > 5) return;
    if (cn.year !== 2026) {
      console.error("Trading calendar not approved for " + cn.year);
      return;
    }
    if (CLOSED_2026.has(cn.date)) return;

    if (INTRADAY_SLOTS.has(cn.time)) {
      if (Math.abs(Date.now() - planned.getTime()) > 90_000) {
        console.warn("Skip late intraday Cron", cn);
        return;
      }
      if (!env.GH_TOKEN) throw new Error("GH_TOKEN Secret is missing");
      await runIntraday(env, planned);
    } else if (FALLBACK_17.has(cn.time)) {
      if (!in17Window(planned)) return;
      if (!env.GH_TOKEN) throw new Error("GH_TOKEN Secret is missing");
      await run17(env, cn);
    }
  }
};
