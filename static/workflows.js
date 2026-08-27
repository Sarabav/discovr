const POLL_INTERVAL_MS = 1500;

const AUDIT_STAGE_LABELS = {
  scraping: "Scraping website",
  ingesting: "Indexing content",
  scoring: "Scoring categories",
  ranking: "Ranking findings",
  saving: "Saving report",
};

const WORKFLOWS = {
  audit: { runUrl: "/workflows/audit/run", pollUrlFor: (id) => `/runs/${id}`, isDone: (data) => data.status !== "running" },
  fix: { runUrl: "/workflows/fix/run", pollUrlFor: (id) => `/agent-runs/${id}`, isDone: (data) => data.status === "done" },
};

// Every route here is @login_required. If the session expired, Flask
// redirects to /login (HTML) instead of erroring, and fetch() follows
// that redirect silently — so response.ok is still true. Checking the
// content-type catches this before .json() throws a cryptic parse error.
async function parseJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Your session may have expired — refresh the page and log in again.");
  }
  return response.json();
}

document.querySelectorAll(".workflow-card[data-workflow]").forEach((card) => {
  card.querySelector(".workflow-run-button").addEventListener("click", () => runWorkflow(card));
});

async function runWorkflow(card) {
  const kind = card.dataset.workflow;
  const workflow = WORKFLOWS[kind];
  const button = card.querySelector(".workflow-run-button");
  const errorEl = card.querySelector(".workflow-error");
  const stepsEl = card.querySelector(".workflow-steps");

  button.disabled = true;
  errorEl.classList.add("hidden");
  stepsEl.innerHTML = "";
  stepsEl.classList.remove("hidden");

  let data;
  try {
    const response = await fetch(workflow.runUrl, { method: "POST" });
    data = await parseJsonResponse(response);
    if (!response.ok) {
      button.disabled = false;
      errorEl.textContent = data.error || "Something went wrong.";
      errorEl.classList.remove("hidden");
      return;
    }
  } catch (error) {
    button.disabled = false;
    errorEl.textContent = error.message;
    errorEl.classList.remove("hidden");
    return;
  }

  pollWorkflow(kind, data.run_id, card);
}

async function pollWorkflow(kind, runId, card) {
  const workflow = WORKFLOWS[kind];
  const button = card.querySelector(".workflow-run-button");
  const stepsEl = card.querySelector(".workflow-steps");
  const errorEl = card.querySelector(".workflow-error");

  let response;
  try {
    response = await fetch(workflow.pollUrlFor(runId));
  } catch (error) {
    setTimeout(() => pollWorkflow(kind, runId, card), POLL_INTERVAL_MS);
    return;
  }

  if (response.status === 404) {
    setTimeout(() => pollWorkflow(kind, runId, card), POLL_INTERVAL_MS);
    return;
  }

  let data;
  try {
    data = await parseJsonResponse(response);
  } catch (error) {
    button.disabled = false;
    errorEl.textContent = error.message;
    errorEl.classList.remove("hidden");
    return;
  }

  if (kind === "audit") {
    renderAuditSteps(stepsEl, data.steps || []);
  } else {
    renderAgentSteps(stepsEl, data.steps || []);
  }

  if (!workflow.isDone(data)) {
    setTimeout(() => pollWorkflow(kind, runId, card), POLL_INTERVAL_MS);
    return;
  }

  button.disabled = false;
}

function renderAuditSteps(stepsEl, steps) {
  stepsEl.innerHTML = "";
  Object.keys(AUDIT_STAGE_LABELS).forEach((stage) => {
    const matches = steps.filter((step) => step.stage === stage);
    const latest = matches[matches.length - 1];
    const status = latest ? latest.status : "pending";
    const icon = { done: "&#10003;", running: "&#9678;", error: "&#10005;" }[status] || "&#9675;";

    const row = document.createElement("div");
    row.className = `step-row step-${status}`;
    row.innerHTML = `<span class="step-icon">${icon}</span><span class="step-label">${AUDIT_STAGE_LABELS[stage]}</span>`;
    stepsEl.appendChild(row);
  });
}

function renderAgentSteps(stepsEl, steps) {
  const alreadyShown = stepsEl.children.length;
  steps.slice(alreadyShown).forEach((step) => {
    if (step.stage === "done") return;
    const row = document.createElement("div");
    row.className = "agent-step-row";
    row.innerHTML = `<span class="agent-step-node">${step.stage.toUpperCase()}</span><span class="agent-step-sep">·</span><span class="agent-step-text"></span>`;
    row.querySelector(".agent-step-text").textContent = step.message || "";
    stepsEl.appendChild(row);
  });
}
