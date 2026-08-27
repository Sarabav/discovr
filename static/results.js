const resultsList = document.getElementById("results-list");

resultsList.addEventListener("click", (event) => {
  const row = event.target.closest(".result-row");
  if (!row) return;

  const detail = row.querySelector(".result-detail");
  detail.classList.toggle("hidden");
});
