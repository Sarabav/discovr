// Stores the business website client-side so the chat can reference it
// after signup. The backend signup route only persists email; wiring a
// real businesses table is a backend change (see README What's Next).
const signupForm = document.getElementById("signup-form");

signupForm.addEventListener("submit", () => {
  const website = document.getElementById("website").value.trim();
  if (website) {
    localStorage.setItem("discovr_business_website", website);
  }
});
