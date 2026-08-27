function wireSave(buttonId, textareaId, statusId, url) {
  const button = document.getElementById(buttonId);
  const textarea = document.getElementById(textareaId);
  const status = document.getElementById(statusId);

  button.addEventListener("click", async () => {
    status.textContent = "";
    status.className = "save-status";

    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: textarea.value }),
    });

    if (!response.ok) {
      const text = await response.text();
      status.textContent = `Save failed (${response.status}): ${text}`;
      status.className = "save-status error";
      return;
    }

    status.textContent = "Saved.";
    status.className = "save-status success";
  });
}

wireSave("save-knowledge-base", "knowledge-base-input", "knowledge-base-status", "/settings/knowledge-base");
wireSave("save-prompt", "prompt-input", "prompt-status", "/settings/prompt");
