// Replace with your deployed Streamlit URL. "?embed=true" hides Streamlit's chrome.
const SUPPORT_URL = "https://YOUR-APP.streamlit.app/?embed=true";
const fab = document.getElementById("chat-fab");
const panel = document.getElementById("chat-panel");
let loaded = false;
fab.addEventListener("click", () => {
  const open = panel.style.display === "block";
  panel.style.display = open ? "none" : "block";
  if (!open && !loaded) { panel.querySelector("iframe").src = SUPPORT_URL; loaded = true; } // lazy-load: wakes sleeping app only when needed
  fab.textContent = open ? "💬 Chat with support" : "✕ Close";
});
