// Your deployed Streamlit app (keep "?embed=true"). Set it to "" to turn the chat off. NEVER leave a placeholder like "YOUR-APP.streamlit.app":
// anyone can register that name on Streamlit Cloud and their app would then appear in your chat panel.
const SUPPORT_URL = "https://pawtech-support-sg-learning.streamlit.app/?embed=true";
// Used automatically when the site itself is opened from this computer (local testing).
const LOCAL_SUPPORT_URL = "http://localhost:8501/?embed=true";

const isLocal = ["localhost", "127.0.0.1"].includes(location.hostname);
const chatUrl = isLocal ? LOCAL_SUPPORT_URL : SUPPORT_URL;

// Anonymous visitor ID: random, created on first visit and kept in this browser, so the agent can
// remember the visitor between visits without asking them for an ID. It is sent to the agent as "cid".
function visitorId() {
  const KEY = "pawtech_visitor_id";
  let id = null;
  try { id = localStorage.getItem(KEY); } catch (e) { /* storage blocked: use a one-off ID */ }
  if (!id) {
    id = crypto.randomUUID();
    try { localStorage.setItem(KEY, id); } catch (e) { /* ignore */ }
  }
  return id;
}

function chatUrlWithVisitor() {
  const url = new URL(chatUrl);
  url.searchParams.set("cid", visitorId());
  return url.toString();
}

const fab = document.getElementById("chat-fab");
const panel = document.getElementById("chat-panel");
let loaded = false;

function loadChat() {
  if (!chatUrl) {
    // Not configured: show a note instead of loading some unknown page.
    panel.innerHTML = '<p class="chat-note">Chat isn\'t set up yet. Set <code>SUPPORT_URL</code> in <code>site/chat.js</code>.</p>';
    return;
  }
  panel.querySelector("iframe").src = chatUrlWithVisitor();
}

fab.addEventListener("click", () => {
  const open = panel.style.display === "block";
  panel.style.display = open ? "none" : "block";
  if (!open && !loaded) { loadChat(); loaded = true; } // lazy-load: wakes sleeping app only when needed
  fab.textContent = open ? "💬 Chat with support" : "✕ Close";
});
