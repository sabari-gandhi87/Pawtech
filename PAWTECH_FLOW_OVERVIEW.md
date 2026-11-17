# PawTech support agent: end-to-end flow

A plain-language description of what the code does, from a visitor opening the website to an answer appearing in
the chat. It's written as a script for an animated visualization. Anything inferred rather than read directly
from the code is marked **(unsure)**.

## Components

- **The website**: a static marketing page with three product cards, a short FAQ line and a chat button.
- **The chat widget**: a floating button plus a hidden panel. When opened, the panel shows the support app inside a frame.
- **The visitor ID**: a random, anonymous ID kept in the visitor's browser so the backend can recognise a returning visitor.
- **The backend (support app)**: a hosted web app that shows the chat screen, runs the support pipeline and holds the secret keys.
- **The memory layer**: a component in the backend that saves notes, turns them into searchable form and searches them by meaning.
- **The knowledge store**: a cloud vector database holding all saved notes, each labelled with an owner. Product knowledge has its own reserved owner label; each visitor's notes carry their visitor ID.
- **The embedding model**: turns text into a list of numbers that captures its meaning. It's used both when notes are saved and when a question is searched.
- **The language model**: writes the answers. It also extracts facts from conversations for the memory layer and creates demo customer profiles. It has a backup model in case the main one is busy.
- **The admin panel**: a hidden side panel, shown only with a special link and a password. It holds the one-off and testing tools.

> There is no separate "agent" that plans or uses tools. The "agent" is a fixed pipeline: it searches, builds a
> prompt, asks the language model, then saves memory. It is the same every time (see stage 7).

## 1. Website load

- The visitor sees the page: a headline, the three product cards (two with photos, one with an emoji), a FAQ line ("30-day returns · 2-year warranty · Free delivery over €100 … Ask our AI assistant, bottom right") and a "💬 Chat with support" button in the bottom-right corner.
- A small script loads with the page. It finds the chat button and the hidden chat panel and decides which backend to use: the live backend normally, or a local test copy if the page is opened on the developer's own computer.
- **The chat backend is not contacted yet.** The chat panel's frame is empty and hidden. Nothing is sent anywhere at this point.

## 2. Chat widget load

- **Visitor clicks "Chat with support".** The panel appears above the button and the button label changes to "✕ Close".
- **First open only:**
  - The script looks in the browser's storage for a saved visitor ID. If there isn't one, it creates a new random ID and saves it.
  - It then points the panel's frame at the backend, adding the visitor ID to the address.
- **Later clicks** only show or hide the panel. The frame isn't reloaded, so the conversation on screen stays.
- **Safety limits on the frame:** it can run scripts and forms, but it can't redirect the website or open pop-ups. The website's address isn't passed to it.
- **Backend side:**
  - If the backend has been asleep from inactivity, it wakes up first. The hosting platform puts it to sleep; this isn't in the code **(unsure about timing)**.
  - On first start, it connects to the knowledge store and the language model and shows "Starting up…" while doing so. Those connections are reused by later visitors.
- **Recognising the visitor:**
  - The backend reads the visitor ID from the address.
  - If it is a valid random ID, the backend uses it as this visitor's identity for the whole session.
  - If it is missing or malformed (for example, someone opens the backend directly), the backend makes up a new random ID for this session only. It won't be remembered.
- **Returning visitors:**
  - The same browser sends the same ID, so the backend can find what it learned about them before.
  - Their **previous chat transcript is not shown again**. Each new session starts with an empty chat. Only the facts saved in memory carry over.
  - If the browser blocks storage, a new ID is made on each page load, so the visitor isn't recognised.
- **Checking for a demo profile:** once per session, the backend asks the knowledge store for this visitor's notes. If they include a demo customer profile, a line appears under the description: "You're chatting as demo customer *name*, owner of *dog*. Latest order: *product* (*status*). Try asking: Where is my order?" This check doesn't use the language model.
- **What the visitor sees:** a title ("PawTech Support 🐾"), a one-line description, the "chatting as" line for returning visitors, and a message box ("How can I help with your PawTech gear?"). No side panel is shown to normal visitors.

## 3. Visitor sends a message

- The visitor types a question and presses Enter or the send button.
- The text goes from the frame to the backend over the app's live connection. This is how the hosting framework works, not something the code sets up itself **(unsure about the transport details)**.
- The backend runs the chat screen again from the top (this is how the framework works):
  - It redraws earlier messages from this session.
  - It shows the new question as a "user" bubble.
  - It shows a "Thinking…" spinner.
- **New visitor, first message:** if the visitor has no demo profile yet, the backend first creates one (see stage 4). The spinner reads "Setting up your demo customer account…". This happens at most once per session.
- The message isn't cleaned, filtered or classified on the way in. It is passed to the support pipeline exactly as typed, along with the visitor ID.

## 4. Memory

There are two kinds of memory.

**Short-term (this session only)**
- The backend keeps the list of messages for the current browser session.
- The last 6 messages (about 3 back-and-forth exchanges) go to the language model with every new question.
- This list is lost when the page or frame is reloaded.

**Long-term (across visits, stored in the knowledge store under the visitor's ID)**
- **Looked up:** on every question, before the answer is written (see stage 6).
- **Saved:** after every successful answer (see stage 10).
- **Demo customer profile:** a made-up profile with a name, dog, a current order that is in transit, past orders, past support tickets and preferences. The language model invents it using the real catalogue prices, and each piece is saved word for word as a memory note under the visitor's ID.
  - **Automatic:** created when a visitor without a profile sends their first message, before that message is answered, so the answer can already use it. The same browser keeps the profile on later visits.
  - **Admin:** an admin can also create one by hand for any ID from the hidden panel.
  - **Typed IDs don't count:** a visitor typing a name or ID in the chat doesn't change whose memory is used.

## 5. Knowledge preparation (before any chat)

- **The source content** is a fixed list of 13 short, hand-written paragraphs:
  - product descriptions, accuracy notes, troubleshooting, safety, cleaning and limits for each product
  - returns, warranty, shipping and support hours
- **No automatic chunking:** each paragraph is already one small "chunk" and is stored whole.
- **Started by hand:** an admin opens the hidden admin panel and presses the "seed product knowledge" button. It's meant to be done once.
- **For each paragraph**, the memory layer:
  - checks whether the exact same text is already stored, and skips it if so (so pressing twice doesn't create duplicates)
  - otherwise asks the embedding model to turn it into a list of 768 numbers
  - saves the text, its numbers and the reserved "product knowledge" owner label in the knowledge store
- Product paragraphs are stored **word for word**. The language model doesn't rewrite them.
- The admin sees "Added N new entries (M already present)."

## 6. Retrieval at question time

- The question is turned into numbers by the same embedding model.
- **Two separate searches by meaning** are run in the knowledge store:
  - **Product knowledge:** the **4** closest paragraphs among notes labelled "product knowledge".
  - **This visitor's memory:** the **5** closest notes among notes labelled with this visitor's ID. No other visitor's notes can come back.
- **No minimum score:** the closest results are always kept, even if they aren't very relevant **(unsure: the memory layer may apply a default cut-off)**.
- Only the note text is kept; scores and labels are dropped.
- Search is by meaning only. The memory layer's optional keyword search is switched off because a required add-on isn't installed (seen in the server log).
- **Result:** two short bullet lists, "Product knowledge" and "Customer memory". If the visitor has no notes yet, the second list says "(nothing yet)".

## 7. Agent role

- **The code makes no decisions here.** It runs the same fixed steps for every message: search both stores → build the prompt → ask the language model → save to memory → show the answer. There's no loop and no tool use, and nothing chooses whether to search: the search always runs.
- **Any "decision" is made by the language model while writing its answer**, following its instructions:
  - **Answer from the provided product knowledge and customer memory.**
  - **Use the customer's details** (e.g. call the dog by name, refer to their order) when the memory has them.
  - **Compare dates with today:** a delivery date later than today means the order is still on its way.
  - **Admit it doesn't know:** if the answer isn't in the provided notes, say it isn't sure and **offer to pass the customer to a human**.
  - **Never invent** prices, policies or specs.
- **There's no real hand-off.** Offering a human is only words in the reply; nothing alerts a person, creates a ticket or changes the flow. The product knowledge mentions a "talk to a human" request, but no such feature exists in the code.
- **Clarifying questions:** nothing in the code asks for them. The language model may ask one on its own **(unsure)**.

## 8. Answer generation

- **The language model receives one request**, with:
  1. its role and rules: PawTech support assistant, use only the given knowledge, don't invent, be warm and brief, use the dog's name
  2. today's date, with a note about comparing delivery dates
  3. the "Product knowledge" list (up to 4 paragraphs)
  4. the "Customer memory" list (up to 5 notes, or "nothing yet")
  5. the last 6 messages from this session
  6. the visitor's new question
- **It returns:** a single plain-text reply, which may contain simple formatting.
- **Not streamed:** the whole answer is produced first, then shown all at once. The visitor sees "Thinking…" until then.
- **If the main model is busy** (overloaded, rate-limited, timed out or unreachable), the same request is sent once to the backup model. Each attempt gives up after 30 seconds and may retry once on its own **(unsure about the exact retry behaviour)**.

## 9. Reply to the visitor

- **Memory is saved before the reply appears.** The backend waits for the memory save in stage 10 to finish, then shows the answer. The visitor's wait includes that save.
- The question and answer are added to this session's message list.
- The "Thinking…" spinner disappears and the answer appears as an "assistant" bubble, in the chat frame inside the website's panel.
- The visitor can ask another question (back to stage 3) or close the panel. Closing only hides it; reopening shows the same conversation.

## 10. After the reply

- **Long-term memory update:**
  - The visitor's question and the answer are sent to the memory layer as one short conversation, labelled with the visitor's ID.
  - The memory layer asks the language model to pull out personal facts worth keeping (e.g. the dog's name, products owned, problems reported), turns them into numbers and saves them in the knowledge store.
  - General questions (e.g. "what is your return policy?") often produce no new facts, so nothing is saved.
  - The memory layer may also update or replace older facts when new ones conflict **(unsure: depends on the memory layer's built-in behaviour)**.
- **Session history:** the question and answer are added to this session's list (used as short-term context next time).
- **No logs, analytics or feedback:** there are no thumbs-up/down buttons, ratings or conversation logs. The memory layer's own usage tracking is switched off.

## 11. Edge cases

- **Nothing relevant found:**
  - Search still returns the closest notes, even if unrelated.
  - The language model is told to say it isn't sure and offer a human.
- **Product knowledge never loaded:** the product list is empty, and the model is told to admit it doesn't know.
- **New visitor:** a demo profile is created before their first answer, so the customer memory list usually has their profile notes. If creating it fails, the list says "(nothing yet)".
- **Demo profile creation fails:** no error is shown to visitors. The chat carries on without a profile, and it isn't retried until the next session.
- **Off-topic questions:** there is no filter or topic check. The question goes through the same pipeline, and the model's rules (only use the provided knowledge, don't invent) are the only guard.
- **Language model fails** (both main and backup busy, timeout, or any other error during search or generation):
  - The visitor sees a red error box with technical details.
  - The chat reply is "Sorry, something went wrong. Please try again."
- **Model returns an empty reply** (e.g. blocked by a safety filter): the visitor sees "Sorry, I couldn't answer that. Could you rephrase, or ask to talk to a human?"
- **Memory save fails:** the visitor sees a yellow warning that the conversation couldn't be saved, but still gets the answer.
- **Error replies are still recorded:** they are added to the session history like a normal answer.
- **Backend not configured on the website:** the panel shows "Chat isn't set up yet" instead of loading anything.
- **Invalid or missing visitor ID:** a temporary ID is used for the session (see stage 2).

## Decision points

1. **Which backend?** The page is opened on the developer's own computer → local test backend. Otherwise → live backend.
2. **Is a backend configured?** No → "Chat isn't set up yet" note. Yes → load the chat.
3. **Chat button click:**
   - Panel closed → open it.
   - Panel open → close it.
   - First open only → also create or read the visitor ID and load the backend in the frame.
4. **Visitor ID in the browser?** Found → reuse it (returning visitor). Not found → create and save a new one. Storage blocked → new one each page load.
5. **Visitor ID valid at the backend?** Valid random ID → use it. Missing or malformed → temporary ID for this session.
6. **Backend awake?** Asleep → wake up and connect first. Awake → continue. **(Platform behaviour, unsure.)**
7. **Admin link used?** No → no side panel at all. Yes → show the admin password box.
8. **Admin password:**
   - not configured on the backend → "admin is disabled" note
   - wrong → "Wrong password"
   - right → show admin tools for the rest of the session
9. **Admin customer ID override:** blank → admin chats as their own visitor ID. Reserved knowledge label or contains spaces → error, keep own ID. Otherwise → chat and look up as that ID.
10. **Identity changed?** The customer ID differs from the previous run → clear the on-screen conversation and demo profile.
11. **Message sent?** No → just show the chat. Yes → run the pipeline.
11a. **Demo profile needed?** The visitor is chatting as their own ID, has no profile and no attempt was made this session → create one first. Otherwise → go straight to the pipeline. **Profile exists?** Yes → show the "chatting as" line.
12. **Main model busy?** Yes → try the backup model once. Backup also busy → error path.
13. **Any error during search or answer?** Yes → error box plus "something went wrong" reply. No → continue.
14. **Empty answer?** Yes → "couldn't answer that" reply, and no memory is saved. No → save memory.
15. **Memory save failed?** Yes → warning, answer still shown. No → answer shown.
16. **Inside the language model (not code):** is the answer in the provided notes? Yes → answer, personalised if memory exists. No → say it isn't sure and offer a human.
17. **Inside the memory layer:** does the conversation contain new personal facts? Yes → save or update them. No → save nothing.
18. **Admin knowledge load:** is the paragraph already stored? Yes → skip it. No → turn it into numbers and store it.

## Parts I wasn't sure about

- **How the message travels from frame to backend:** handled by the hosting framework's live connection, not by this project's code.
- **How sleep and wake-up timing works:** handled by the hosting platform, outside the code.
- **Whether search drops weak matches:** the code sets no minimum relevance score, but the memory layer might apply a default.
- **How memory updates older facts:** how the memory layer decides to add, update or replace facts from a conversation is its own built-in behaviour, not visible in this code.
- **Exact timeouts and retries:** each model call gives up after 30 seconds and may retry once inside the client library before the backup model is tried.
- **Whether the question is embedded once or twice:** it's searched twice (product knowledge and customer memory); the memory layer may convert it to numbers separately for each search.
- **Clarifying questions:** the model could ask one, but nothing in the code asks for or handles that.
