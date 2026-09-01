const chatMessages = document.getElementById("chat-messages");
const emptyState = document.getElementById("empty-state");
const emptyStateText = document.getElementById("empty-state-text");
const examplePrompt = document.getElementById("example-prompt");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendButton = document.getElementById("send-button");

const STORAGE_KEY = "discovr_business_website";
const AUDIT_PROMPT = "Run my AI-visibility audit";
const FIX_EVERYTHING_PROMPT = "Fix my site";
const POLL_INTERVAL_MS = 1500;

// Every route we fetch() here is @login_required. If the session
// expired, Flask redirects to /login (HTML) instead of erroring — and
// fetch() follows that redirect silently, so response.ok is still
// true. Parsing that as JSON is where "Unexpected token '<'" comes
// from. Checking the content-type catches this (and any other
// non-JSON response) before we try to parse it.
async function parseJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Your session may have expired — refresh the page and log in again.");
  }
  return response.json();
}

const STAGE_LABELS = {
  scraping: "Scraping website",
  ingesting: "Indexing content",
  scoring: "Scoring categories",
  ranking: "Ranking findings",
  saving: "Saving report",
};
const STAGE_ORDER = Object.keys(STAGE_LABELS);

const CATEGORY_LABELS = {
  nap_consistency: "NAP Consistency",
  structured_data: "Structured Data",
  content_clarity: "Content Clarity",
  crawler_access: "Crawler Access",
  mentions: "Mentions",
};

// Categories with a stable, permanent-feeling reason for having no
// score — as opposed to content_clarity, where a null score means a
// one-off check failure and should show the real dynamic error instead
// (see report.skipped). Mentions technically doesn't need a connector
// (Reddit needs no API key), but Reddit blocks non-browser clients at
// the network level with no workaround from a server, so today it's
// effectively in the same "not wired up" state as NAP Consistency —
// see src/components/find_mentions.py for the full story.
const STATIC_SKIP_MESSAGES = {
  nap_consistency: "Not connected — needs the Google Places connector",
  mentions: "Not measured yet — needs a search connector",
};

const storedWebsite = localStorage.getItem(STORAGE_KEY);
if (storedWebsite) {
  emptyStateText.textContent = `Discovr checks how visible ${storedWebsite} is to AI assistants like ChatGPT and Perplexity, and tells you exactly what to fix.`;
}

examplePrompt.addEventListener("click", () => sendMessage(AUDIT_PROMPT));

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = "";
  sendMessage(text);
});

async function sendMessage(text) {
  hideEmptyState();
  addUserMessage(text);
  setBusy(true);

  const pending = addPendingMessage();

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text }),
    });
    const data = await parseJsonResponse(response);
    pending.remove();

    if (!response.ok) {
      addErrorMessage(data.error || "Something went wrong.", () => sendMessage(text));
      return;
    }

    if (data.type === "run_started") {
      const stepEl = addStepMessage();
      pollRun(data.run_id, stepEl);
      return;
    }

    if (data.type === "fix_run_started") {
      const runEl = addAgentRunMessage();
      pollAgentRun(data.run_id, runEl);
      return;
    }

    if (data.type === "fix") {
      addFixMessage(data.finding, data.fix);
      return;
    }

    if (data.type === "upgrade") {
      addUpgradeMessage(data.answer);
      return;
    }

    addAssistantMessage(data.answer);
  } catch (error) {
    pending.remove();
    addErrorMessage(String(error), () => sendMessage(text));
  } finally {
    setBusy(false);
  }
}

async function pollRun(runId, stepEl) {
  let response;
  try {
    response = await fetch(`/runs/${runId}`);
  } catch (error) {
    setTimeout(() => pollRun(runId, stepEl), POLL_INTERVAL_MS);
    return;
  }

  if (response.status === 404) {
    // The background thread hasn't written its first agent_runs row yet.
    setTimeout(() => pollRun(runId, stepEl), POLL_INTERVAL_MS);
    return;
  }

  let data;
  try {
    data = await parseJsonResponse(response);
  } catch (error) {
    stepEl.remove();
    addErrorMessage(error.message, () => retryAudit());
    return;
  }

  renderSteps(stepEl, data.steps || []);

  if (data.status === "running") {
    setTimeout(() => pollRun(runId, stepEl), POLL_INTERVAL_MS);
    return;
  }

  stepEl.remove();

  if (data.status === "error") {
    addErrorMessage(data.error || "The audit failed.", () => retryAudit());
    return;
  }

  addReportMessage(data.result);
}

function retryAudit() {
  sendMessage(AUDIT_PROMPT);
}

function addAgentRunMessage() {
  const div = document.createElement("div");
  div.className = "message assistant";
  div.innerHTML = `
    <div class="agent-plain-list"></div>
    <details class="agent-technical-details">
      <summary>Show technical steps</summary>
      <div class="agent-step-list"></div>
    </details>
    <div class="agent-fix-list"></div>
    <p class="agent-summary hidden"></p>
  `;
  chatMessages.appendChild(div);
  scrollToBottom();
  return div;
}

async function pollAgentRun(runId, runEl) {
  let response;
  try {
    response = await fetch(`/agent-runs/${runId}`);
  } catch (error) {
    setTimeout(() => pollAgentRun(runId, runEl), POLL_INTERVAL_MS);
    return;
  }

  if (response.status === 404) {
    // The background thread hasn't written its first agent_runs row yet
    // (a real race, not an error) — keep polling instead of treating
    // "not found yet" as "already finished."
    setTimeout(() => pollAgentRun(runId, runEl), POLL_INTERVAL_MS);
    return;
  }

  if (!response.ok) {
    addErrorMessage("Something went wrong while working through the findings.", () =>
      sendMessage(FIX_EVERYTHING_PROMPT)
    );
    return;
  }

  let data;
  try {
    data = await parseJsonResponse(response);
  } catch (error) {
    addErrorMessage(error.message, () => sendMessage(FIX_EVERYTHING_PROMPT));
    return;
  }

  renderPlainSteps(runEl, data.steps || []);
  renderAgentSteps(runEl, data.steps || []);
  renderStreamedFixes(runEl, data.fixes || []);

  if (data.status !== "done") {
    setTimeout(() => pollAgentRun(runId, runEl), POLL_INTERVAL_MS);
    return;
  }

  addAgentSummary(runEl, data.summary);
}

const CATEGORY_ACTION_PHRASES = {
  structured_data: "Writing your business schema",
  content_clarity: "Rewriting your homepage",
  crawler_access: "Fixing blocked AI crawlers",
  nap_consistency: "Fixing inconsistent business details",
};

function renderPlainSteps(runEl, steps) {
  const list = runEl.querySelector(".agent-plain-list");
  list.innerHTML = "";
  buildPlainLines(steps).forEach((line) => {
    const p = document.createElement("p");
    p.className = "agent-plain-line";
    p.textContent = line;
    list.appendChild(p);
  });
  scrollToBottom();
}

function buildPlainLines(steps) {
  // Everything except the one-off score-projection/blockers rows, which
  // are logged as "monitor" steps but aren't part of any finding's story.
  const findingSteps = steps.filter((s) => !(s.stage === "monitor" && /^\d+ generated fix|^what's still holding/.test(s.input_summary || "")));

  const lines = [];
  const introStep = findingSteps.find((s) => s.stage === "suggest");
  if (introStep && introStep.input_summary) {
    const match = introStep.input_summary.match(/(\d+) findings? open/);
    if (match) lines.push(`Looking at ${match[1]} problem${match[1] === "1" ? "" : "s"}…`);
  }

  const groups = [];
  let current = null;
  findingSteps.forEach((step) => {
    const chosen = step.stage === "suggest" && step.message.match(/^choosing '(.+?)' — (.*)$/);
    if (chosen) {
      current = { title: chosen[1], reason: chosen[2], steps: [] };
      groups.push(current);
      return;
    }
    if (current) current.steps.push(step);
  });

  groups.forEach((group) => lines.push(buildFindingLine(group)));
  return lines;
}

function buildFindingLine(group) {
  const planStep = group.steps.find((s) => s.stage === "plan");
  const categoryMatch = planStep && planStep.message.match(/category=(\w+)/);
  const category = categoryMatch ? categoryMatch[1] : null;
  const actionPhrase = CATEGORY_ACTION_PHRASES[category] || `Working on "${group.title}"`;

  if (category === "crawler_access" && /outranks everything/.test(group.reason)) {
    return "Starting with blocked AI crawlers — nothing else matters until crawlers can read your site. This one needs you.";
  }

  const isInstruction = planStep && planStep.message.startsWith("fix_type=instruction");
  if (isInstruction) {
    return `${actionPhrase}… This one needs you.`;
  }

  let outcome = "";
  group.steps
    .filter((s) => s.stage === "monitor")
    .forEach((step, index) => {
      if (step.message.startsWith("passed")) {
        outcome += index === 0 ? "checked it, all good." : "better. Done.";
      } else if (step.message.startsWith("failed, retrying")) {
        outcome += "first attempt wasn't clear enough, trying again… ";
      } else if (step.message.startsWith("failed after max attempts")) {
        outcome += "still not quite right after a couple tries. Flagged for you to review.";
      } else if (step.message.startsWith("couldn't verify")) {
        outcome += "couldn't check this one automatically. Flagged for you to review.";
      }
    });

  if (!outcome) outcome = "stopped partway through — you can run it again to pick up where it left off.";
  return `${actionPhrase}… ${outcome}`.trim();
}

function renderAgentSteps(runEl, steps) {
  const list = runEl.querySelector(".agent-step-list");
  const alreadyShown = list.children.length;
  steps.slice(alreadyShown).forEach((step) => {
    if (step.stage === "done") return; // summary is rendered separately, in place
    const row = document.createElement("div");
    row.className = "agent-step-row";
    row.innerHTML = `<span class="agent-step-node">${step.stage.toUpperCase()}</span><span class="agent-step-sep">·</span><span class="agent-step-text"></span>`;
    row.querySelector(".agent-step-text").textContent = step.message || "";
    list.appendChild(row);
  });
  scrollToBottom();
}

function renderStreamedFixes(runEl, fixes) {
  const list = runEl.querySelector(".agent-fix-list");
  const shownIds = new Set(Array.from(list.children).map((el) => el.dataset.findingId));

  fixes.forEach((fix) => {
    if (shownIds.has(fix.finding_id)) return;
    const wrapper = document.createElement("div");
    wrapper.className = "finding-item";
    wrapper.dataset.findingId = fix.finding_id;
    wrapper.innerHTML = `<p class="finding-item-text">${CATEGORY_LABELS[fix.category] || fix.category} — ${fix.title}</p>`;
    wrapper.appendChild(buildFixCard(fix));
    list.appendChild(wrapper);
  });
  scrollToBottom();
}

function buildFinishedLine(summary) {
  const parts = [];
  if (summary.resolved) parts.push(`${summary.resolved} fix${summary.resolved === 1 ? "" : "es"} ready to paste`);
  if (summary.needs_human) parts.push(`${summary.needs_human} need${summary.needs_human === 1 ? "s" : ""} you`);
  if (summary.failed) parts.push(`${summary.failed} couldn't be fixed automatically`);
  return `Finished: ${parts.join(", ") || "nothing to do"}.`;
}

function addAgentSummary(runEl, summary) {
  // Appended inside the same trail block (not a new message) so the
  // reasoning stays visible under its own summary line rather than
  // collapsing away — the trail is the point of this feature.
  const p = runEl.querySelector(".agent-summary");
  p.textContent = summary ? buildFinishedLine(summary) : "Finished.";
  p.classList.remove("hidden");

  if (summary && summary.projection) {
    const projection = document.createElement("p");
    projection.className = "agent-summary agent-projection";
    projection.textContent = summary.projection;
    runEl.appendChild(projection);
  }

  if (summary && summary.blockers && summary.blockers.length) {
    const label = document.createElement("p");
    label.className = "agent-summary agent-blockers-label";
    label.textContent = "Still holding the score back:";
    runEl.appendChild(label);

    const list = document.createElement("ul");
    list.className = "agent-blockers-list";
    summary.blockers.forEach((blocker) => {
      const item = document.createElement("li");
      item.textContent = blocker;
      list.appendChild(item);
    });
    runEl.appendChild(list);
  }

  scrollToBottom();
}

function hideEmptyState() {
  emptyState.classList.add("hidden");
}

function addUserMessage(text) {
  const div = document.createElement("div");
  div.className = "message user";
  div.textContent = text;
  chatMessages.appendChild(div);
  scrollToBottom();
}

function addAssistantMessage(text) {
  const div = document.createElement("div");
  div.className = "message assistant";
  div.textContent = text;
  chatMessages.appendChild(div);
  scrollToBottom();
}

function addUpgradeMessage(text) {
  const div = document.createElement("div");
  div.className = "message assistant";

  const p = document.createElement("p");
  p.textContent = text;
  div.appendChild(p);

  const link = document.createElement("a");
  link.href = "/checkout";
  link.className = "button-ghost upgrade-link";
  link.textContent = "Upgrade — $5";
  div.appendChild(link);

  chatMessages.appendChild(div);
  scrollToBottom();
}

function addFixMessage(finding, fix) {
  const wrapper = document.createElement("div");
  wrapper.className = "message assistant";

  const intro = document.createElement("p");
  intro.textContent = `Here's a fix for "${finding.title}":`;
  wrapper.appendChild(intro);
  wrapper.appendChild(buildFixCard(fix));

  chatMessages.appendChild(wrapper);
  scrollToBottom();
}

function addPendingMessage() {
  const div = document.createElement("div");
  div.className = "message assistant pending";
  div.textContent = "Thinking...";
  chatMessages.appendChild(div);
  scrollToBottom();
  return div;
}

function addStepMessage() {
  const div = document.createElement("div");
  div.className = "message assistant";
  div.innerHTML = '<div class="step-list"></div>';
  chatMessages.appendChild(div);
  scrollToBottom();
  return div;
}

function renderSteps(stepEl, steps) {
  const list = stepEl.querySelector(".step-list");
  list.innerHTML = "";
  STAGE_ORDER.forEach((stage) => {
    const stageSteps = steps.filter((step) => step.stage === stage);
    const latest = stageSteps[stageSteps.length - 1];

    let stateClass = "step-pending";
    let icon = "&#9675;";
    if (latest) {
      if (latest.status === "running") {
        stateClass = "step-running";
        icon = "&#9678;";
      } else if (latest.status === "done") {
        stateClass = "step-done";
        icon = "&#10003;";
      } else if (latest.status === "error") {
        stateClass = "step-error";
        icon = "&#10005;";
      }
    }

    const row = document.createElement("div");
    row.className = `step-row ${stateClass}`;
    row.innerHTML = `<span class="step-icon">${icon}</span><span class="step-label">${STAGE_LABELS[stage]}</span>`;
    list.appendChild(row);
  });
  scrollToBottom();
}

function addErrorMessage(message, onRetry) {
  const div = document.createElement("div");
  div.className = "message assistant error-message-block";

  const p = document.createElement("p");
  p.textContent = message;
  div.appendChild(p);

  const button = document.createElement("button");
  button.type = "button";
  button.className = "retry-button";
  button.textContent = "Retry";
  button.addEventListener("click", () => {
    div.remove();
    onRetry();
  });
  div.appendChild(button);

  chatMessages.appendChild(div);
  scrollToBottom();
}

function gradeFor(score) {
  if (score === null || score === undefined) return "";
  if (score >= 80) return "Strong";
  if (score >= 60) return "Needs Improvement";
  return "Weak";
}

function addReportMessage(report) {
  const wrapper = document.createElement("div");
  wrapper.className = "message assistant";

  const intro = document.createElement("p");
  intro.textContent = `Here's the AI-visibility audit for ${report.business_name}.`;
  wrapper.appendChild(intro);

  const box = document.createElement("div");
  box.className = "report";

  const scoreRow = document.createElement("div");
  scoreRow.className = "report-score-row";
  const scoreText = report.overall_score === null ? "—" : `${report.overall_score}/100`;
  scoreRow.innerHTML =
    `<span class="report-score">${scoreText}</span>` +
    `<span class="report-grade">${gradeFor(report.overall_score)}</span>`;
  box.appendChild(scoreRow);

  const categories = document.createElement("div");
  categories.className = "report-categories";
  Object.entries(report.categories).forEach(([key, score]) => {
    const row = document.createElement("div");
    row.className = "report-category-row";
    const label = CATEGORY_LABELS[key] || key;
    if (score === null) {
      // A static, permanent-feeling reason (no connector wired up) reads
      // differently from a check that actually tried and failed this
      // specific run — that real, dynamic reason comes from
      // report.skipped, persisted alongside the score so it survives
      // past the request that computed it. Never a number either way:
      // a skipped category has nothing to show but 0/100 would lie.
      const message = STATIC_SKIP_MESSAGES[key] || `Couldn't score — ${(report.skipped && report.skipped[key]) || "unknown reason"}`;
      row.innerHTML =
        `<span class="report-category-name">${label}</span>` +
        `<span class="report-category-skipped">${message}</span>`;
    } else {
      row.innerHTML =
        `<span class="report-category-name">${label}</span>` +
        `<span class="report-category-score">${score}/100</span>`;
    }
    categories.appendChild(row);
  });
  box.appendChild(categories);

  const findingsBox = document.createElement("div");
  findingsBox.className = "report-recommendations";
  findingsBox.innerHTML = "<h4>Findings, Ranked by Impact</h4>";

  if (!report.paid) {
    const upgradeBar = document.createElement("div");
    upgradeBar.className = "upgrade-bar";
    const upgradeText = document.createElement("span");
    upgradeText.textContent = "You're on the free plan — audits and findings are free, generated fixes are paid.";
    upgradeBar.appendChild(upgradeText);
    const upgradeLink = document.createElement("a");
    upgradeLink.href = "/checkout";
    upgradeLink.className = "upgrade-bar-link";
    upgradeLink.textContent = "Upgrade";
    upgradeBar.appendChild(upgradeLink);
    findingsBox.appendChild(upgradeBar);
  }

  if (report.findings.length) {
    const fixAllWrapper = document.createElement("div");
    fixAllWrapper.className = "fix-all-wrapper";

    const fixAllButton = document.createElement("button");
    fixAllButton.type = "button";
    fixAllButton.className = "fix-all-button";
    fixAllButton.textContent = "Fix all findings";
    fixAllButton.addEventListener("click", () => {
      fixAllWrapper.remove();
      sendMessage(FIX_EVERYTHING_PROMPT);
    });
    fixAllWrapper.appendChild(fixAllButton);

    const fixAllNote = document.createElement("p");
    fixAllNote.className = "fix-all-note";
    fixAllNote.textContent =
      "Works through every problem in priority order, checks each fix is valid before showing it to you, " +
      "and keeps your wording consistent across all of them. Or fix them one at a time below.";
    fixAllWrapper.appendChild(fixAllNote);

    findingsBox.appendChild(fixAllWrapper);
  }

  const list = document.createElement("div");
  list.className = "finding-list";
  report.findings.forEach((finding) => list.appendChild(buildFindingCard(finding)));
  findingsBox.appendChild(list);
  box.appendChild(findingsBox);

  wrapper.appendChild(box);

  const outro = document.createElement("p");
  outro.textContent = "Ask me anything about these results.";
  wrapper.appendChild(outro);

  chatMessages.appendChild(wrapper);
  scrollToBottom();
}

const FIXABLE_CATEGORIES = new Set(["structured_data", "content_clarity", "crawler_access", "nap_consistency"]);

function buildFindingCard(finding) {
  const card = document.createElement("div");
  card.className = "finding-item";
  card.innerHTML = `
    <p class="finding-item-text">
      <span class="report-priority">${finding.priority}</span>${finding.title} — ${finding.description}
    </p>
  `;

  if (finding.why_it_matters) {
    const why = document.createElement("p");
    why.className = "finding-why-matters";
    why.textContent = `Why it matters: ${finding.why_it_matters}`;
    card.appendChild(why);
  }

  if (FIXABLE_CATEGORIES.has(finding.category) && finding.id) {
    if (finding.locked) {
      const lockedNote = document.createElement("a");
      lockedNote.href = "/checkout";
      lockedNote.className = "finding-locked-note";
      lockedNote.innerHTML = `<span class="lock-icon" aria-hidden="true">&#128274;</span> Upgrade to generate this fix`;
      card.appendChild(lockedNote);
    } else {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button-ghost generate-fix-button";
      button.textContent = "Generate this fix";
      button.addEventListener("click", () => generateFix(finding.id, button, card));
      card.appendChild(button);
    }
  }

  return card;
}

async function generateFix(findingId, button, card) {
  button.disabled = true;
  button.textContent = "Generating...";

  try {
    const response = await fetch(`/findings/${findingId}/fix`, { method: "POST" });
    const data = await parseJsonResponse(response);

    if (!response.ok) {
      button.remove();
      const error = document.createElement("p");
      error.className = "fix-error";
      error.textContent = data.error || "Could not generate a fix.";
      card.appendChild(error);
      return;
    }

    // The server is the real gate (see /findings/<id>/fix) -- the
    // locked/unlocked buttons are just a head start, so this still has
    // to handle being told "actually, upgrade" even though the button
    // shouldn't normally be clickable in that state.
    if (data.type === "upgrade") {
      button.remove();
      const lockedNote = document.createElement("a");
      lockedNote.href = "/checkout";
      lockedNote.className = "finding-locked-note";
      lockedNote.innerHTML = `<span class="lock-icon" aria-hidden="true">&#128274;</span> ${data.answer}`;
      card.appendChild(lockedNote);
      return;
    }

    button.remove();
    card.appendChild(buildFixCard(data));
  } catch (error) {
    button.disabled = false;
    button.textContent = "Generate this fix";
    const errorEl = document.createElement("p");
    errorEl.className = "fix-error";
    errorEl.textContent = error.message;
    card.appendChild(errorEl);
  }
}

function buildFixCard(fix) {
  const card = document.createElement("div");
  card.className = "fix-card";

  if (fix.fix_type === "generated" && fix.before === null) {
    // structured_data: a JSON-LD block with a Copy button.
    const pre = document.createElement("pre");
    pre.className = "fix-code";
    pre.textContent = fix.content;
    card.appendChild(pre);

    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "button-ghost copy-button";
    copyButton.textContent = "Copy";
    copyButton.addEventListener("click", () => {
      navigator.clipboard.writeText(fix.content);
      copyButton.textContent = "Copied!";
      setTimeout(() => (copyButton.textContent = "Copy"), 1500);
    });
    card.appendChild(copyButton);
  } else if (fix.fix_type === "generated") {
    // content_clarity: before/after diff.
    const diff = document.createElement("div");
    diff.className = "fix-diff";
    diff.innerHTML = `
      <div class="fix-diff-before"><span class="fix-diff-label">Before</span><p></p></div>
      <div class="fix-diff-after"><span class="fix-diff-label">After</span><p></p></div>
    `;
    diff.querySelector(".fix-diff-before p").textContent = fix.before || "(no passage identified)";
    diff.querySelector(".fix-diff-after p").textContent = fix.content || "(no rewrite generated)";
    card.appendChild(diff);
  } else {
    // instruction: numbered steps as plain preformatted text.
    const pre = document.createElement("pre");
    pre.className = "fix-instructions";
    pre.textContent = fix.content;
    card.appendChild(pre);
  }

  if (fix.needs_from_owner && fix.needs_from_owner.length) {
    const note = document.createElement("p");
    note.className = "fix-needs-owner";
    note.textContent =
      `Marked "FILL IN" in the block above — you'll need to add: ${fix.needs_from_owner.join(", ")}. ` +
      "Nothing was guessed for these; only confirmed facts were filled in automatically.";
    card.appendChild(note);
  }

  if (fix.where_to_apply) {
    const where = document.createElement("p");
    where.className = "fix-where";
    where.textContent = `Where to apply: ${fix.where_to_apply}`;
    card.appendChild(where);
  }

  const verifiedBadge = document.createElement("span");

  if (fix.fix_type === "instruction") {
    // "Not verified" implies failure; an instruction fix was never
    // attempted automatically in the first place, so it gets its own
    // honest label instead.
    verifiedBadge.className = "fix-verified-badge manual";
    verifiedBadge.textContent = "Needs you";
    card.appendChild(verifiedBadge);

    const manualNote = document.createElement("p");
    manualNote.className = "fix-manual-note";
    manualNote.textContent = "This step can't be applied automatically — it needs a person to make the change.";
    card.appendChild(manualNote);
  } else if (fix.status === "resolved") {
    verifiedBadge.className = "fix-verified-badge verified";
    verifiedBadge.textContent = "Verified";
    card.appendChild(verifiedBadge);
  } else if (fix.status === "needs_human") {
    // The check itself couldn't run (e.g. a parse error), not a verdict
    // on the fix — a distinct badge from "failed" so a broken checker
    // never reads the same as a bad fix.
    verifiedBadge.className = "fix-verified-badge unavailable";
    verifiedBadge.textContent = `Couldn't verify automatically${fix.reason ? ` — ${fix.reason}` : ""}`;
    card.appendChild(verifiedBadge);
  } else if (fix.status === "failed") {
    verifiedBadge.className = "fix-verified-badge unverified";
    verifiedBadge.textContent = `Verification failed${fix.reason ? ` — ${fix.reason}` : ""}`;
    card.appendChild(verifiedBadge);
  } else {
    // status === "open": the run stopped (node limit) before this fix
    // was ever checked — not a verdict either way.
    verifiedBadge.className = "fix-verified-badge unavailable";
    verifiedBadge.textContent = "Not yet verified";
    card.appendChild(verifiedBadge);
  }

  return card;
}

function setBusy(busy) {
  chatInput.disabled = busy;
  sendButton.disabled = busy;
}

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}
