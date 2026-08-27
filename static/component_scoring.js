const urlInput = document.getElementById("scoring-url");
const runButton = document.getElementById("run-button");
const runStatus = document.getElementById("run-status");
const elapsedTime = document.getElementById("elapsed-time");
const errorBanner = document.getElementById("error-banner");
const resultsEl = document.getElementById("results");

const CATEGORY_LABELS = {
  nap_consistency: "NAP Consistency",
  structured_data: "Structured Data",
  content_clarity: "Content Clarity",
  crawler_access: "Crawler Access",
  mentions: "Mentions",
};

runButton.addEventListener("click", runComponent);

async function runComponent() {
  const url = urlInput.value.trim();
  if (!url) return;

  runButton.disabled = true;
  runStatus.textContent = "Scraping and scoring...";
  elapsedTime.textContent = "";
  hideError();
  resultsEl.classList.add("hidden");

  const response = await fetch("/components/scoring/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

  runButton.disabled = false;
  runStatus.textContent = "";

  if (!response.ok) {
    const text = await response.text();
    showError(`Request failed (${response.status}): ${text}`);
    return;
  }

  const data = await response.json();
  elapsedTime.textContent = `${data.elapsed_seconds}s`;

  if (data.scrape_error) {
    showError(`Scrape failed: ${data.scrape_error}`);
  }

  renderResults(data);
}

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.classList.remove("hidden");
}

function hideError() {
  errorBanner.classList.add("hidden");
  errorBanner.textContent = "";
}

function gradeFor(score) {
  if (score === null || score === undefined) return "";
  if (score >= 80) return "Strong";
  if (score >= 60) return "Needs Improvement";
  return "Weak";
}

function renderResults(data) {
  document.getElementById("overall-score-value").textContent =
    data.overall_score === null ? "—" : `${data.overall_score}/100`;
  document.getElementById("overall-score-grade").textContent = gradeFor(data.overall_score);

  const categoriesEl = document.getElementById("result-categories");
  categoriesEl.innerHTML = "";
  Object.entries(data.categories).forEach(([key, score]) => {
    const row = document.createElement("div");
    row.className = "category-row";
    const label = CATEGORY_LABELS[key] || key;

    if (score === null) {
      const reason = (data.skipped && data.skipped[key]) || "Skipped";
      row.innerHTML =
        `<span class="category-name">${label}</span>` +
        `<span class="category-skipped">Skipped — ${reason}</span>`;
    } else {
      row.innerHTML = `<span class="category-name">${label}</span><span class="category-score">${score}/100</span>`;
    }
    categoriesEl.appendChild(row);
  });

  const findingsEl = document.getElementById("result-findings");
  findingsEl.innerHTML = "";
  if (!data.findings.length) {
    const p = document.createElement("p");
    p.className = "settings-hint";
    p.textContent = "No findings.";
    findingsEl.appendChild(p);
  }
  data.findings.forEach((finding) => {
    const card = document.createElement("div");
    card.className = "finding-card";
    card.innerHTML = `
      <div class="finding-badges">
        <span class="badge priority-${finding.priority.toLowerCase()}">${finding.priority}</span>
        <span class="badge category-badge">${CATEGORY_LABELS[finding.category] || finding.category}</span>
        <span class="badge fix-type-${finding.fix_type}">${finding.fix_type === "generated" ? "Fix generated" : "Manual fix"}</span>
      </div>
      <h3 class="finding-title"></h3>
      <p class="finding-description"></p>
      ${finding.why_it_matters ? '<p class="finding-why"></p>' : ""}
    `;
    card.querySelector(".finding-title").textContent = finding.title;
    card.querySelector(".finding-description").textContent = finding.description;
    if (finding.why_it_matters) {
      card.querySelector(".finding-why").textContent = `Why it matters: ${finding.why_it_matters}`;
    }
    findingsEl.appendChild(card);
  });

  document.getElementById("result-raw").textContent = JSON.stringify(data, null, 2);

  resultsEl.classList.remove("hidden");
}
