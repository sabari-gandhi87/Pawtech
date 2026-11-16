// Your deployed Streamlit app, e.g. "https://pawtech-support.streamlit.app/?embed=true".
// Leave it empty until you have deployed. NEVER leave a placeholder like "YOUR-APP.streamlit.app":
// anyone can register that name on Streamlit Cloud and their app would then appear in your chat panel.
const SUPPORT_URL = "";
// Used automatically when the site itself is opened from this computer (local testing).
const LOCAL_SUPPORT_URL = "http://localhost:8501/?embed=true";

const isLocal = ["localhost", "127.0.0.1"].includes(location.hostname);
const chatUrl = isLocal ? LOCAL_SUPPORT_URL : SUPPORT_URL;

const fab = document.getElementById("chat-fab");
const panel = document.getElementById("chat-panel");
let loaded = false;

function loadChat() {
  if (!chatUrl) {
    // Not configured: show a note instead of loading some unknown page.
    panel.innerHTML = '<p class="chat-note">Chat isn\'t set up yet. Set <code>SUPPORT_URL</code> in <code>site/chat.js</code>.</p>';
    return;
  }
  panel.querySelector("iframe").src = chatUrl;
}

fab.addEventListener("click", () => {
  const open = panel.style.display === "block";
  panel.style.display = open ? "none" : "block";
  if (!open && !loaded) { loadChat(); loaded = true; } // lazy-load: wakes sleeping app only when needed
  fab.textContent = open ? "💬 Chat with support" : "✕ Close";
});
