const analyzeForm = document.getElementById("analyze-form");
const historyCard = document.getElementById("history-card");
const reportCard = document.getElementById("report-card");
const chatCard = document.getElementById("chat-card");
const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");

let currentReport = null;

analyzeForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const payload = {
    website: document.getElementById("website").value,
    facebook: document.getElementById("facebook").value,
    instagram: document.getElementById("instagram").value,
  };

  const response = await fetch("/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  currentReport = await response.json();
  renderReport(currentReport);
});

function renderReport(report) {
  document.getElementById("business-name").textContent = report.business_name;
  document.getElementById("overall-score-value").textContent = report.overall_score;

  const gradeEl = document.getElementById("overall-grade");
  gradeEl.textContent = report.overall_grade;
  gradeEl.className = "grade-badge grade-" + report.overall_grade.toLowerCase().replace(/\s+/g, "-");

  const categoriesEl = document.getElementById("categories");
  categoriesEl.innerHTML = "";
  Object.values(report.categories).forEach((category) => {
    const el = document.createElement("div");
    el.className = "category";
    el.innerHTML = `
      <div class="category-header">
        <span>${category.label}</span>
        <span>${category.score}/100</span>
      </div>
      <div class="score-bar"><div class="score-fill" style="width:${category.score}%"></div></div>
      <ul>${category.findings.map((f) => `<li>${f}</li>`).join("")}</ul>
    `;
    categoriesEl.appendChild(el);
  });

  const recsEl = document.getElementById("recommendations");
  recsEl.innerHTML = "";
  report.recommendations.forEach((rec) => {
    const li = document.createElement("li");
    li.className = "recommendation priority-" + rec.priority.toLowerCase();
    li.innerHTML = `<span class="priority-badge">${rec.priority}</span> ${rec.text}`;
    recsEl.appendChild(li);
  });

  const historyEl = document.getElementById("history");
  historyEl.innerHTML = "";
  report.history.forEach((entry) => {
    const li = document.createElement("li");
    li.textContent = `${entry.created_at} — ${entry.website} — ${entry.overall_score}/100`;
    historyEl.appendChild(li);
  });
  historyCard.classList.remove("hidden");

  reportCard.classList.remove("hidden");
  chatCard.classList.remove("hidden");
  chatMessages.innerHTML = "";
  addChatMessage(
    "assistant",
    `Your analysis is ready! Ask me anything about ${report.business_name}'s AI-visibility report.`
  );
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const input = document.getElementById("chat-input");
  const question = input.value.trim();
  if (!question) return;

  addChatMessage("user", question);
  input.value = "";

  const response = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, report: currentReport }),
  });

  const data = await response.json();
  addChatMessage("assistant", data.answer);
});

function addChatMessage(role, text) {
  const div = document.createElement("div");
  div.className = "chat-message " + role;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}
