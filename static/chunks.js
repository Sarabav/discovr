const chunkSizeInput = document.getElementById("chunk-size-input");
const rebuildButton = document.getElementById("rebuild-button");
const rebuildStatus = document.getElementById("rebuild-status");
const rebuildProgress = document.getElementById("rebuild-progress");
const chunksList = document.getElementById("chunks-list");
const chunkCount = document.getElementById("chunk-count");

rebuildButton.addEventListener("click", async () => {
  rebuildStatus.textContent = "";
  rebuildStatus.className = "save-status";
  rebuildButton.disabled = true;

  const response = await fetch("/rag/rebuild", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chunk_size: Number(chunkSizeInput.value) }),
  });

  if (!response.ok) {
    const text = await response.text();
    rebuildStatus.textContent = `Rebuild failed (${response.status}): ${text}`;
    rebuildStatus.className = "save-status error";
    rebuildButton.disabled = false;
    return;
  }

  rebuildProgress.classList.remove("hidden");
  pollUntilReady();
});

async function pollUntilReady() {
  const response = await fetch("/rag/status");
  const status = await response.json();

  if (status.building) {
    setTimeout(pollUntilReady, 1000);
    return;
  }

  rebuildProgress.classList.add("hidden");
  rebuildButton.disabled = false;

  if (status.error) {
    rebuildStatus.textContent = `Rebuild failed: ${status.error}`;
    rebuildStatus.className = "save-status error";
    return;
  }

  rebuildStatus.textContent = `Rebuilt: ${status.chunk_count} chunks.`;
  rebuildStatus.className = "save-status success";
  refreshChunkList();
}

async function refreshChunkList() {
  const response = await fetch("/chunks/data");
  const data = await response.json();

  chunkCount.textContent = data.chunks.length;
  chunksList.innerHTML = "";

  data.chunks.forEach((chunk) => {
    const card = document.createElement("div");
    card.className = "chunk-card";
    card.innerHTML = `
      <div class="chunk-meta">
        <span class="chunk-id">${chunk.id}</span>
        <span class="chunk-heading"></span>
        <span class="chunk-tokens">${chunk.tokens} tokens</span>
      </div>
      <pre class="chunk-text"></pre>
    `;
    card.querySelector(".chunk-heading").textContent = chunk.heading;
    card.querySelector(".chunk-text").textContent = chunk.text;
    chunksList.appendChild(card);
  });
}
