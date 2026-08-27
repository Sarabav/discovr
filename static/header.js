const avatarToggle = document.getElementById("avatar-toggle");
const avatarDropdown = document.getElementById("avatar-dropdown");

avatarToggle.addEventListener("click", (event) => {
  event.stopPropagation();
  avatarDropdown.classList.toggle("hidden");
});

document.addEventListener("click", (event) => {
  if (!avatarDropdown.contains(event.target) && event.target !== avatarToggle) {
    avatarDropdown.classList.add("hidden");
  }
});
