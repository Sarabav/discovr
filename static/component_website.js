const urlInput = document.getElementById("website-url");
const runButton = document.getElementById("run-button");
const runStatus = document.getElementById("run-status");
const renderMethodBadge = document.getElementById("render-method");
const elapsedTime = document.getElementById("elapsed-time");
const errorBanner = document.getElementById("error-banner");
const resultsEl = document.getElementById("results");
const exampleJsHeavyButton = document.getElementById("example-js-heavy");

const TEXT_PREVIEW_LENGTH = 1000;
const JS_HEAVY_EXAMPLE_URL = "https://fresh2home.ca";
let fullText = "";
let textExpanded = false;

runButton.addEventListener("click", runComponent);

exampleJsHeavyButton.addEventListener("click", () => {
  urlInput.value = JS_HEAVY_EXAMPLE_URL;
  runComponent();
});

async function runComponent() {
  const url = urlInput.value.trim();
  if (!url) return;

  runButton.disabled = true;
  runStatus.textContent = "Running...";
  elapsedTime.textContent = "";
  renderMethodBadge.classList.add("hidden");
  hideError();
  resultsEl.classList.add("hidden");

  const response = await fetch("/components/website/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

  runButton.disabled = false;

  if (!response.ok) {
    const text = await response.text();
    runStatus.textContent = "";
    showError(`Request failed (${response.status}): ${text}`);
    return;
  }

  const data = await response.json();
  runStatus.textContent = "";
  elapsedTime.textContent = `${data.elapsed_seconds}s`;

  if (data.scrape.render_method) {
    renderMethodBadge.textContent =
      data.scrape.render_method === "playwright" ? "Rendered with headless browser" : "Fetched with requests";
    renderMethodBadge.className =
      "render-method-badge " + (data.scrape.render_method === "playwright" ? "playwright" : "requests");
  }

  if (data.scrape.error) {
    showError(data.scrape.error);
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

function renderResults(data) {
  const scrape = data.scrape;
  const crawlerAccess = data.crawler_access;

  document.getElementById("result-title").textContent = scrape.title || "(none found)";
  document.getElementById("result-meta").textContent = scrape.meta_description || "(none found)";

  const schemaEl = document.getElementById("result-schema");
  if (scrape.schema && scrape.schema.length) {
    schemaEl.textContent = JSON.stringify(scrape.schema, null, 2);
    schemaEl.classList.remove("none-found");
  } else {
    schemaEl.textContent = "None found";
    schemaEl.classList.add("none-found");
  }

  const schemaSummary = data.schema_summary || { block_count: 0, types: [], has_business_node: false };
  const blocksEl = document.getElementById("result-schema-blocks");
  const businessEl = document.getElementById("result-schema-business");
  blocksEl.textContent = schemaSummary.block_count
    ? `${schemaSummary.block_count} (${schemaSummary.types.join(", ")})`
    : "0";
  businessEl.textContent = schemaSummary.has_business_node ? "found" : "none found";
  businessEl.classList.toggle("none-found", !schemaSummary.has_business_node);

  const crawlersEl = document.getElementById("result-crawlers");
  crawlersEl.innerHTML = "";
  if (crawlerAccess.error) {
    const p = document.createElement("p");
    p.className = "none-found";
    p.textContent = crawlerAccess.error;
    crawlersEl.appendChild(p);
  } else {
    Object.entries(crawlerAccess.bots).forEach(([bot, disallowed]) => {
      const row = document.createElement("div");
      row.className = "crawler-row";
      row.innerHTML =
        `<span class="crawler-name">${bot}</span>` +
        `<span class="crawler-status ${disallowed ? "blocked" : "allowed"}">${disallowed ? "Blocked" : "Allowed"}</span>`;
      crawlersEl.appendChild(row);
    });
  }

  const nap = scrape.nap || {};
  document.getElementById("result-nap-name").textContent = nap.name || "not found";
  document.getElementById("result-nap-phone").textContent = nap.phone || "not found";
  document.getElementById("result-nap-address").textContent = nap.address || "not found";

  fullText = scrape.text || "";
  textExpanded = false;
  document.getElementById("result-text-count").textContent = fullText.length;
  renderTextPreview();

  const pagesEl = document.getElementById("result-pages");
  pagesEl.innerHTML = "";
  (scrape.pages_crawled || []).forEach((page) => {
    const li = document.createElement("li");
    li.textContent = page;
    pagesEl.appendChild(li);
  });

  const unreachableSection = document.getElementById("unreachable-section");
  const unreachableEl = document.getElementById("result-unreachable");
  unreachableEl.innerHTML = "";
  const unreachablePages = scrape.unreachable_pages || [];
  if (unreachablePages.length) {
    unreachablePages.forEach((page) => {
      const li = document.createElement("li");
      li.textContent = `${page.url} (${page.status ? `HTTP ${page.status}` : "failed to load"})`;
      unreachableEl.appendChild(li);
    });
    unreachableSection.classList.remove("hidden");
  } else {
    unreachableSection.classList.add("hidden");
  }

  document.getElementById("result-raw").textContent = JSON.stringify(data, null, 2);

  resultsEl.classList.remove("hidden");
}

function renderTextPreview() {
  const textEl = document.getElementById("result-text");
  const toggleButton = document.getElementById("toggle-text");

  if (textExpanded) {
    textEl.textContent = fullText;
    toggleButton.textContent = "Show less";
  } else {
    textEl.textContent = fullText.slice(0, TEXT_PREVIEW_LENGTH);
    toggleButton.textContent = "Show full text";
  }

  toggleButton.classList.toggle("hidden", fullText.length <= TEXT_PREVIEW_LENGTH);
}

document.getElementById("toggle-text").addEventListener("click", () => {
  textExpanded = !textExpanded;
  renderTextPreview();
});
