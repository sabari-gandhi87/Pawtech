import json
import re
from datetime import datetime, timedelta

import streamlit as st
from mem0 import Memory
from openai import OpenAI

from kb import KB

st.set_page_config(page_title="PawTech Support", page_icon="🐾")
st.title("PawTech Support 🐾")
st.caption("Chat with our AI assistant. It remembers you and your dog between visits.")

# ---- Config: everything comes from Streamlit secrets (never from a text box on a public site) ----
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
QDRANT_URL = st.secrets["QDRANT_URL"]
QDRANT_API_KEY = st.secrets["QDRANT_API_KEY"]
CHAT_MODEL = st.secrets.get("CHAT_MODEL", "gemini-2.5-flash")
# Verify the embedding model name in Google AI Studio; change it here if it has been retired.
EMBED_MODEL = st.secrets.get("EMBED_MODEL", "models/gemini-embedding-001")
EMBED_DIMS = 768  # must match the Qdrant collection; delete the collection if you change it

KB_USER = "pawtech-kb"
SYSTEM_PROMPT = """You are the customer support assistant for PawTech, a (fictional) company selling AI products
for dog owners: WoofLingo Buds, StrollBot and PupSitter.
Answer using the 'Product knowledge' and 'Customer memory' provided. If the answer is not there, say you are not
sure and offer to pass the customer to a human. Never invent prices, policies or specs. Be warm, brief, and use
the dog's name when you know it."""


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
    )
    return memory, llm


def seed_kb(memory: Memory):
    """Store product knowledge verbatim (infer=False skips LLM fact extraction).
    Idempotent: entries already present are skipped, so repeated clicks don't create duplicates.
    Returns the number of entries added."""
    existing = set(_texts(memory.get_all(user_id=KB_USER)))
    added = 0
    for doc in KB:
        if doc not in existing:
            memory.add(doc, user_id=KB_USER, infer=False, metadata={"role": "kb"})
            added += 1
    return added


def _texts(res):
    return [m["memory"] for m in (res or {}).get("results", []) if "memory" in m]


class SupportAgent:
    def __init__(self, memory, llm):
        self.memory, self.llm = memory, llm

    def handle_query(self, query, user_id):
        try:
            kb = _texts(self.memory.search(query=query, user_id=KB_USER, limit=4))
            mine = _texts(self.memory.search(query=query, user_id=user_id, limit=5))
            context = (
                "Product knowledge:\n" + "\n".join(f"- {t}" for t in kb)
                + "\n\nCustomer memory:\n" + ("\n".join(f"- {t}" for t in mine) or "- (nothing yet)")
            )
            history = st.session_state.messages[-6:]  # short-term context from this session
            resp = self.llm.chat.completions.create(
                model=CHAT_MODEL,
                messages=[{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context}]
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
        return self.memory.get_all(user_id=user_id)

    def generate_synthetic_data(self, user_id):
        today = datetime.now()
        order_date = (today - timedelta(days=10)).strftime("%B %d, %Y")
        delivery = (today + timedelta(days=2)).strftime("%B %d, %Y")
        prompt = f"""Create a customer profile for PawTech customer {user_id}. Return a JSON object with keys:
name, dog (name, breed, age), recent_order (product from WoofLingo Buds / StrollBot / PupSitter, placed {order_date},
delivery by {delivery}, order number, price), previous_orders (2 items), support_history (2 short past tickets),
preferences (list). Valid JSON only."""
        try:
            resp = self.llm.chat.completions.create(
                model=CHAT_MODEL,
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
            st.error(f"Failed to generate synthetic data: {e}")
            return None


memory, llm = get_clients()
agent = SupportAgent(memory, llm)

# ---- Sidebar ----
customer_id = st.sidebar.text_input("Customer ID", placeholder="e.g. aoife-123").strip()
if customer_id.lower() == KB_USER:  # reserved: would read/write the shared product knowledge base
    st.sidebar.error("That ID is reserved. Please choose another.")
    customer_id = ""
if customer_id != st.session_state.get("previous_customer_id"):
    st.session_state.messages = []
    st.session_state.customer_data = None
    st.session_state.previous_customer_id = customer_id
st.session_state.setdefault("messages", [])

if st.sidebar.button("Generate demo customer data"):
    if customer_id:
        with st.spinner("Generating..."):
            st.session_state.customer_data = agent.generate_synthetic_data(customer_id)
    else:
        st.sidebar.error("Enter a customer ID first.")
if st.session_state.get("customer_data"):
    st.sidebar.json(st.session_state.customer_data)

if st.sidebar.button("View memory"):
    if customer_id:
        for t in _texts(agent.get_memories(customer_id)) or ["No memory yet."]:
            st.sidebar.write(f"- {t}")
    else:
        st.sidebar.error("Enter a customer ID first.")

with st.sidebar.expander("Admin"):
    if st.button("Seed product knowledge (run once)"):
        added = seed_kb(memory)
        st.success(f"Added {added} new entries ({len(KB) - added} already present).")

# ---- Chat ----
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

query = st.chat_input("How can I help with your PawTech gear?")
if query and not customer_id:
    st.error("Please enter a customer ID in the sidebar first.")
elif query:
    st.chat_message("user").markdown(query)
    with st.spinner("Thinking..."):
        answer = agent.handle_query(query, customer_id)
    st.session_state.messages += [{"role": "user", "content": query}, {"role": "assistant", "content": answer}]
    st.chat_message("assistant").markdown(answer)
