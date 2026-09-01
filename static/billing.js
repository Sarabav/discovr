const billingToggle = document.getElementById("billing-settings-toggle");
const billingPanel = document.getElementById("billing-settings-panel");
const refundButton = document.getElementById("refund-button");
const refundMessage = document.getElementById("refund-message");

billingToggle.addEventListener("click", (event) => {
  event.stopPropagation();
  billingPanel.classList.toggle("hidden");
});

document.addEventListener("click", (event) => {
  if (!billingPanel.contains(event.target) && event.target !== billingToggle) {
    billingPanel.classList.add("hidden");
  }
});

// Only rendered for paid users -- a free user's panel shows an Upgrade
// link instead, with nothing to wire up here.
if (refundButton) {
  refundButton.addEventListener("click", async () => {
    refundButton.disabled = true;
    refundMessage.classList.add("hidden");

    const response = await fetch("/billing/refund", { method: "POST" });
    const data = await response.json().catch(() => ({}));

    refundMessage.textContent = data.message || "Something went wrong.";
    refundMessage.classList.remove("hidden");
    refundMessage.classList.toggle("billing-message-error", !data.ok);

    if (data.ok) {
      refundButton.textContent = "Refunded";
      // Paid status just flipped server-side -- reload to pick up the
      // free-plan view (locked fix cards, upgrade bar, etc.).
      setTimeout(() => {
        window.location.href = "/dashboard";
      }, 1500);
    } else {
      refundButton.disabled = false;
    }
  });
}
