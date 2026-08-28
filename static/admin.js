const dataSourceSelect = document.getElementById("data-source-select");
const dataSourceStatus = document.getElementById("data-source-status");
const cloneButton = document.getElementById("clone-button");
const cloneSummary = document.getElementById("clone-summary");

dataSourceSelect.addEventListener("change", async () => {
  const source = dataSourceSelect.value;
  dataSourceStatus.textContent = "Saving…";

  const response = await fetch("/admin/data-source", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    dataSourceStatus.textContent = `Couldn't switch: ${data.error || response.status}`;
    return;
  }

  dataSourceStatus.textContent = `Now using ${source === "supabase" ? "Supabase" : "Local (SQLite)"}.`;
});

cloneButton.addEventListener("click", async () => {
  cloneButton.disabled = true;
  cloneButton.textContent = "Cloning…";
  cloneSummary.classList.add("hidden");

  const response = await fetch("/admin/clone-to-supabase", { method: "POST" });
  const data = await response.json().catch(() => ({}));

  cloneButton.disabled = false;
  cloneButton.textContent = "Clone Local Data to Supabase";

  renderCloneSummary(data, response.ok);
});

function renderCloneSummary(data, ok) {
  cloneSummary.innerHTML = "";
  cloneSummary.classList.remove("hidden");

  if (!ok) {
    const p = document.createElement("p");
    p.className = "clone-error";
    p.textContent = data.error || "Clone failed.";
    cloneSummary.appendChild(p);
    return;
  }

  const list = document.createElement("ul");
  list.className = "clone-table-list";
  Object.entries(data.tables || {}).forEach(([table, result]) => {
    const item = document.createElement("li");
    item.textContent = result.error
      ? `${table}: ${result.error}`
      : `${table}: ${result.copied} copied, ${result.skipped} already there (${result.total} total)`;
    if (result.error) item.className = "clone-row-error";
    list.appendChild(item);
  });
  cloneSummary.appendChild(list);

  if (data.schema_error) {
    const note = document.createElement("p");
    note.className = "clone-error";
    note.textContent = `Couldn't create tables in Supabase: ${data.schema_error}`;
    cloneSummary.appendChild(note);
  }
}

document.querySelectorAll(".refund-user-button").forEach((button) => {
  button.addEventListener("click", async () => {
    const row = button.closest("tr");
    const userId = row.dataset.userId;
    button.disabled = true;
    button.textContent = "Refunding…";

    const response = await fetch(`/admin/users/${userId}/refund`, { method: "POST" });
    const data = await response.json().catch(() => ({}));

    if (data.ok) {
      const status = row.querySelector(".users-status");
      status.textContent = "Unpaid";
      status.classList.remove("paid");
      status.classList.add("unpaid");
      button.remove();
    } else {
      alert(data.message || "Refund failed.");
      button.disabled = false;
      button.textContent = "Refund";
    }
  });
});
