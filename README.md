# PawTech demo: site + support agent (all free tiers)

## 1. Accounts (no card needed)
- Qdrant Cloud free cluster -> copy cluster URL + API key
- Google AI Studio -> Gemini API key
- GitHub repo (push this folder)

## 2. Deploy the agent (Streamlit Community Cloud)
- New app -> repo, main file `agent/app.py`, requirements `agent/requirements.txt`
- Settings -> Secrets: paste `agent/secrets.toml.example` with real values
- Open the app, sidebar -> Admin -> "Seed product knowledge" ONCE
- Smoke test: customer ID `test1` -> "Generate demo customer data" -> ask about returns, then about "my order"

## 3. Deploy the site (Cloudflare Pages)
- Edit `SUPPORT_URL` in `site/chat.js` to your Streamlit URL (keep `?embed=true`).
  Until then the chat shows "not set up yet"; never leave a placeholder URL, since anyone can claim it.
  When the site is opened from localhost it uses the local agent at `http://localhost:8501` automatically.
- Pages -> connect repo, build command none, output directory `site`

## Local run
cd agent && pip install -r requirements.txt && mkdir -p .streamlit && cp secrets.toml.example .streamlit/secrets.toml && streamlit run app.py
