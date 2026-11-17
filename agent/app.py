import hmac
import json
import os
import re
import uuid
from datetime import datetime, timedelta

# Turn off mem0's anonymous usage tracking (PostHog). mem0 reads this environment variable once,
# when it is imported, so it must be set before the "from mem0 import Memory" line below.
os.environ["MEM0_TELEMETRY"] = "False"

import streamlit as st
from mem0 import Memory
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

from kb import KB

st.set_page_config(page_title="PawTech Support", page_icon="🐾")
st.title("PawTech Support 🐾")
st.caption("Chat with our AI assistant. It remembers you and your dog between visits.")

# ---- Config: everything comes from Streamlit secrets (never from a text box on a public site) ----
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
QDRANT_URL = st.secrets["QDRANT_URL"]
QDRANT_API_KEY = st.secrets["QDRANT_API_KEY"]
# gemini-2.5-flash is closed to new API keys; check Google AI Studio if this one is retired too.
CHAT_MODEL = st.secrets.get("CHAT_MODEL", "gemini-3.5-flash-lite")
# Used automatically when CHAT_MODEL is overloaded (503), rate-limited (429) or times out.
FALLBACK_MODEL = st.secrets.get("FALLBACK_MODEL", "gemini-3.1-flash-lite")
# Verify the embedding model name in Google AI Studio; change it here if it has been retired.
EMBED_MODEL = st.secrets.get("EMBED_MODEL", "models/gemini-embedding-001")
EMBED_DIMS = 768  # must match the Qdrant collection; delete the collection if you change it

KB_USER = "pawtech-kb"
SYSTEM_PROMPT = """You are the customer support assistant for PawTech, a (fictional) company selling AI products
for dog owners: WoofLingo Buds, StrollBot and PupSitter.
Answer using the 'Product knowledge' and 'Customer memory' provided. If the answer is not there, say you are not
sure and offer to pass the customer to a human. Never invent prices, policies or specs. Be warm, brief, and use
the dog's name when you know it."""

# Catalogue prices (must match kb.py) so generated demo orders don't invent prices or currencies.
PRICES = {
    "WoofLingo Buds": "199 EUR",
    "StrollBot": "1,499 EUR (or 59 EUR/month subscription)",
    "PupSitter": "349 EUR",
    "StrollBot bag cartridges (60 bags)": "12 EUR",
}


@st.cache_resource(show_spinner="Starting up...")
def get_clients():
    config = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "url": QDRANT_URL,
                "api_key": QDRANT_API_KEY,
                "collection_name": "pawtech_memory",
                "embedding_model_dims": EMBED_DIMS,
            },
        },
        "llm": {"provider": "gemini", "config": {"model": CHAT_MODEL, "api_key": GEMINI_API_KEY}},
        "embedder": {
            "provider": "gemini",
            "config": {"model": EMBED_MODEL, "embedding_dims": EMBED_DIMS, "api_key": GEMINI_API_KEY},
        },
        "version": "v1.1",
    }
    memory = Memory.from_config(config)
    # Gemini exposes an OpenAI-compatible endpoint, so the original OpenAI client code still works.
    llm = OpenAI(
        api_key=GEMINI_API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout=30,  # fail fast instead of hanging if Gemini is overloaded; chat() then tries the fallback
        max_retries=1,
    )
    return memory, llm


# Errors that mean "this model is busy right now", worth retrying on another model.
_BUSY_ERRORS = (InternalServerError, RateLimitError, APITimeoutError, APIConnectionError)


def chat(llm: OpenAI, **kwargs):
    """chat.completions.create with CHAT_MODEL, switching to FALLBACK_MODEL if it is busy."""
    models = [CHAT_MODEL] + ([FALLBACK_MODEL] if FALLBACK_MODEL and FALLBACK_MODEL != CHAT_MODEL else [])
    for i, model in enumerate(models):
        try:
            return llm.chat.completions.create(model=model, **kwargs)
        except _BUSY_ERRORS:
            if i == len(models) - 1:
                raise


def seed_kb(memory: Memory):
    """Store product knowledge verbatim (infer=False skips LLM fact extraction).
    Idempotent: entries already present are skipped, so repeated clicks don't create duplicates.
    Returns the number of entries added."""
    existing = set(_texts(memory.get_all(filters={"user_id": KB_USER}, top_k=100)))
    added = 0
    for doc in KB:
        if doc not in existing:
            memory.add(doc, user_id=KB_USER, infer=False, metadata={"role": "kb"})
            added += 1
    return added


def _today_note():
    """The model doesn't know today's date; without it, it treats future delivery dates as past."""
    return (f"Today's date is {datetime.now():%A, %B %d, %Y}. Compare any dates in the customer memory with "
            "today: a delivery date after today means the order has NOT arrived yet (it is on its way).")


def _texts(res):
    return [m["memory"] for m in (res or {}).get("results", []) if "memory" in m]


_PROFILE_KEYS = ("name", "dog", "recent_order")


def _profile_summary(data):
    """The parts of a demo profile shown in the 'chatting as' line, or None if there is no profile."""
    profile = {k: data[k] for k in _PROFILE_KEYS if isinstance(data, dict) and data.get(k)}
    return profile or None


def _profile_from_memories(res):
    """Rebuild the demo profile summary from a customer's stored notes. Demo profiles are stored as
    'key: <json>' notes (see generate_synthetic_data); notes learned from chats are plain sentences."""
    data = {}
    for text in _texts(res):
        key, sep, value = text.partition(": ")
        if sep and key in _PROFILE_KEYS:
            try:
                data[key] = json.loads(value)
            except ValueError:
                pass
    return _profile_summary(data)


def _profile_line(profile):
    """e.g. 'You're chatting as demo customer **Aoife**, owner of **Biscuit**. Latest order: **StrollBot** (in transit).'"""
    name, dog, order = profile.get("name"), profile.get("dog"), profile.get("recent_order")
    line = f"🐶 You're chatting as demo customer **{name if isinstance(name, str) else 'Guest'}**"
    if isinstance(dog, dict) and dog.get("name"):
        line += f", owner of **{dog['name']}**"
    line += "."
    if isinstance(order, dict) and order.get("product"):
        line += f" Latest order: **{order['product']}**" + (f" ({order['status']})." if order.get("status") else ".")
    return line + " Try asking: *Where is my order?*"


class SupportAgent:
    def __init__(self, memory, llm):
        self.memory, self.llm = memory, llm

    def handle_query(self, query, user_id):
        try:
            kb = _texts(self.memory.search(query, filters={"user_id": KB_USER}, top_k=4))
            mine = _texts(self.memory.search(query, filters={"user_id": user_id}, top_k=5))
            context = (
                "Product knowledge:\n" + "\n".join(f"- {t}" for t in kb)
                + "\n\nCustomer memory:\n" + ("\n".join(f"- {t}" for t in mine) or "- (nothing yet)")
            )
            history = st.session_state.messages[-6:]  # short-term context from this session
            resp = chat(
                self.llm,
                messages=[{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + _today_note() + "\n\n" + context}]
                + history
                + [{"role": "user", "content": query}],
            )
            answer = resp.choices[0].message.content
        except Exception as e:
            st.error(f"Error: {e}")
            return "Sorry, something went wrong. Please try again."
        if not answer:  # e.g. response blocked by a safety filter; never put None into chat history
            return "Sorry, I couldn't answer that. Could you rephrase, or ask to talk to a human?"
        try:
            # Store the exchange as one conversation so Mem0 extracts facts (dog name, owned products, issues)
            self.memory.add(
                [{"role": "user", "content": query}, {"role": "assistant", "content": answer}],
                user_id=user_id,
                metadata={"app_id": "pawtech-support"},
            )
        except Exception as e:  # don't throw away a good answer just because saving memory failed
            st.warning(f"Couldn't save this conversation to memory: {e}")
        return answer

    def get_memories(self, user_id):
        return self.memory.get_all(filters={"user_id": user_id}, top_k=100)

    def generate_synthetic_data(self, user_id, show_errors=True):
        today = datetime.now()
        order_date = (today - timedelta(days=10)).strftime("%B %d, %Y")
        delivery = (today + timedelta(days=2)).strftime("%B %d, %Y")
        price_list = "\n".join(f"- {p}: {price}" for p, price in PRICES.items())
        prompt = f"""Create a customer profile for PawTech customer {user_id}. Return a JSON object with keys:
name, dog (name, breed, age), recent_order (product from WoofLingo Buds / StrollBot / PupSitter, order_date
{order_date}, status "in transit", expected_delivery_date {delivery}, order_number, price),
previous_orders (2 items, each delivered before {order_date}), support_history (2 short past tickets),
preferences (list).
Use ONLY these catalogue prices, in EUR, exactly as written:
{price_list}
Valid JSON only."""
        try:
            resp = chat(
                self.llm,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            raw = re.sub(r"^```(?:json)?|```$", "", resp.choices[0].message.content.strip(), flags=re.M).strip()
            data = json.loads(raw)
            for key, value in data.items():
                items = value if isinstance(value, list) else [value]
                for item in items:
                    self.memory.add(f"{key}: {json.dumps(item)}", user_id=user_id, infer=False,
                                    metadata={"role": "system"})
            return data
        except Exception as e:
            if show_errors:  # visitors just carry on without a profile
                st.error(f"Failed to generate synthetic data: {e}")
            return None


memory, llm = get_clients()
agent = SupportAgent(memory, llm)

# ---- Who is chatting ----
# The website passes a random, anonymous visitor ID as ?cid=<uuid> (see site/chat.js). Anything that isn't a
# UUID is ignored (it can't be the reserved KB ID or contain spaces), and the session gets a fresh ID instead.
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
if "visitor_id" not in st.session_state:
    cid = (st.query_params.get("cid") or "").strip().lower()
    st.session_state.visitor_id = cid if _UUID_RE.match(cid) else str(uuid.uuid4())
customer_id = st.session_state.visitor_id

# ---- Admin (hidden): only with ?admin=1 AND the ADMIN_PASSWORD secret ----
# Visitors never see the sidebar: Streamlit doesn't draw it when nothing is written to it.
if st.query_params.get("admin") == "1" and not st.session_state.get("is_admin"):
    admin_password = st.secrets.get("ADMIN_PASSWORD", "")
    if not admin_password:
        st.sidebar.info("Admin is disabled: set ADMIN_PASSWORD in the app's secrets.")
    else:
        entered = st.sidebar.text_input("Admin password", type="password")
        if entered and hmac.compare_digest(entered.encode(), admin_password.encode()):
            st.session_state.is_admin = True
            st.rerun()
        elif entered:
            st.sidebar.error("Wrong password.")
is_admin = st.session_state.get("is_admin", False)

if is_admin:
    st.sidebar.caption(f"Your visitor ID: `{customer_id}`")
    override = st.sidebar.text_input("Customer ID (blank = your visitor ID)", placeholder="e.g. aoife-123").strip()
    if override.lower() == KB_USER:  # reserved: would read/write the shared product knowledge base
        st.sidebar.error("That ID is reserved. Please choose another.")
    elif any(c.isspace() for c in override):  # mem0 rejects IDs containing spaces
        st.sidebar.error("Customer IDs can't contain spaces. Try e.g. aoife-123.")
    elif override:
        customer_id = override

if customer_id != st.session_state.get("previous_customer_id"):
    st.session_state.messages = []
    st.session_state.customer_data = None
    st.session_state.previous_customer_id = customer_id
    # Look up this customer's demo profile once (no language model call, just the knowledge store).
    try:
        st.session_state.profile = _profile_from_memories(agent.get_memories(customer_id))
    except Exception:
        st.session_state.profile = None
    st.session_state.profile_attempted = False
st.session_state.setdefault("messages", [])
profile_slot = st.empty()  # filled at the end, so a profile created during this run shows straight away

if is_admin:
    if st.sidebar.button("Generate demo customer data"):
        with st.spinner("Generating..."):
            st.session_state.customer_data = agent.generate_synthetic_data(customer_id)
        st.session_state.profile = _profile_summary(st.session_state.customer_data) or st.session_state.profile
    if st.session_state.get("customer_data"):
        st.sidebar.json(st.session_state.customer_data)

    if st.sidebar.button("View memory"):
        for t in _texts(agent.get_memories(customer_id)) or ["No memory yet."]:
            st.sidebar.write(f"- {t}")

    with st.sidebar.expander("Admin"):
        if st.button("Seed product knowledge (run once)"):
            added = seed_kb(memory)
            st.success(f"Added {added} new entries ({len(KB) - added} already present).")

# ---- Chat ----
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

query = st.chat_input("How can I help with your PawTech gear?")
if query:
    st.chat_message("user").markdown(query)
    # Automatic demo profile: a visitor with no profile gets one on their first message, so questions like
    # "where is my order?" work. Only for the visitor's own ID (admins looking up other IDs use the sidebar),
    # and only one attempt per session so a failure doesn't add a slow call to every message.
    if (not st.session_state.profile and customer_id == st.session_state.visitor_id
            and not st.session_state.profile_attempted):
        st.session_state.profile_attempted = True
        with st.spinner("Looking up your details..."):
            st.session_state.profile = _profile_summary(agent.generate_synthetic_data(customer_id, show_errors=is_admin))
    with st.spinner("Thinking..."):
        answer = agent.handle_query(query, customer_id)
    st.session_state.messages += [{"role": "user", "content": query}, {"role": "assistant", "content": answer}]
    st.chat_message("assistant").markdown(answer)

if st.session_state.profile:
    profile_slot.caption(_profile_line(st.session_state.profile))
