# CLAUDE.md

## 🎨 Style
- ✂️ concise, no filler
- 🧼 clean, readable
- 🧾 minimal comments and docs

## ⚙️ Rules
- ⚡ minimal code and libraries
- 🧱 modular, reusable, no repetition
- 🏷️ no hardcoding, use variables
- 🧩 use HTML templates with base
- 🚫 no fallback errors, fail clearly
- 🚷 no em-dashes at all costs
- 📄 update `requirements.txt` if needed
- 📝 update `CLAUDE.md` on structure changes
- 📘 update the `README.md` whenever a new feature is added
- Do not do browser testing (like playwright) unless i explicitly tell you to.

## 🧰 Stack
- 🐍 Flask, SQLite, Supabase, GitHub OAuth
- 🤖 OpenRouter (model-agnostic LLM calls)
- 🕸️ LangGraph (the agent loop's state machine — `src/agent/graph.py`)
- 🔎 sentence-transformers + ChromaDB (RAG: chunking, embedding, retrieval)
- 🌐 requests + BeautifulSoup + Playwright (Business Website component; Playwright is a headless-render fallback for JS-heavy sites, needs `playwright install chromium` once)
- 🚀 gunicorn on Render (`render.yaml`) — 1 worker/4 threads deliberately (see the file's comments): the RAG embedding model loads once per worker process, so extra workers just multiply memory

## 🗂️ Code Structure
- 🚪 **`app.py`** - Flask App entry point
- ☁️ **`render.yaml`** - Render Blueprint: build/start commands, env vars, for `gunicorn app:app` deploys
- 🖼️ **`templates/`** - front end. `landing.html` is the public page at `/`; `dashboard.html` (chat-first, at `/dashboard`) is the whole logged-in app; `header.html` is a shared partial included by every logged-in page (normal users see Dashboard/Settings only, plus an Admin link in the avatar dropdown if `is_admin`); `admin.html` (`/admin`, admin-only) hubs the developer views — Components, Workflows, Chunks, Results — each still its own page/route, just gated and reachable only from here, plus the Data Source dropdown (local/Supabase) and "Clone Local Data to Supabase" button; `admin_bar.html` is the muted "Admin — internal tools" partial included on all admin pages; `workflows.html` (`/workflows`) lists the app's end-to-end workflows as run-able cards
- 🎨 **`static/style.css`** - shared design tokens (palette, type, radii, shadows; light/dark), consumed by every page's CSS
- 🗄️ **`data/`** - all app data
- 💾 **`data/app.db`** - local SQLite database (generated, gitignored) - the default data source
- 🔀 **`data/data_source.txt`** - which backend is active, `local` or `supabase` (generated, gitignored; defaults to `local` when absent)
- 📚 **`data/knowledge_base.md`** - chatbot facts, chunked and embedded for RAG
- 🧬 **`data/chroma/`** - ChromaDB vector store (generated, gitignored)
- 👍 **`data/results.json`** - rated chatbot responses (generated, gitignored)
- ⚙️ **`src/`** - backend logic
- 🔀 **`src/store.py`** - persistence dispatcher every route/module imports instead of `src.db` directly; forwards each call to `src.db` (local SQLite) or `src.supabase_store` (Supabase) based on `src.data_source`, so the admin page's Data Source dropdown swaps backends without a restart
- 🗄️ **`src/db.py`** - the local SQLite backend: schema (`init_db`), connections, and every table's CRUD
- ☁️ **`src/supabase_store.py`** - the Supabase backend, same function signatures as `src/db.py`; `ensure_schema()` creates tables via a direct Postgres connection (`SUPABASE_DB_URL`, since the REST API can't run DDL) and disables RLS on each; `clone_local_to_supabase()` runs that then does an idempotent row copy from local SQLite, used by the admin page's clone button
- 🔑 **`src/supabase_client.py`** - cached Supabase client (service-role key, bypasses RLS) for row reads/writes; schema creation goes through `psycopg2` + `SUPABASE_DB_URL` instead, see above
- 🤖 **`src/agents.py`** - OpenRouter model access
- 💬 **`src/chatbot.py`** - `classify_intent`/`answer_question`/`resolve_finding_ref`/`describe_progress`: routes every chat message by real LLM-classified intent, answers grounded in the user's real scores when they have any, never a canned response
- 🔎 **`src/rag.py`** - chunking, embedding, ChromaDB storage and retrieval; two collection kinds — one shared `knowledge_base`, one `business_<id>` per audited business (`ingest_business`/`retrieve_business_context`)
- 👍 **`src/ratings.py`** - thumbs up/down persistence and stats
- 🌐 **`src/components/`** - real (non-mocked) data-gathering components, one module per component (e.g. `scrape_website.py`); each has a matching page at `/components/<name>`
- 🛠️ **`src/components/fix_generator.py`** - `generate_fix`/`verify_fix`/`generate_verified_fix`: turns a finding into a real fix, grounded in per-business RAG + the playbook's fixing tips, never invented; `POST /findings/<id>/fix` triggers it from the chat findings card
- 📣 **`src/components/find_mentions.py`** - `find_mentions(business_name, city)`: real Reddit public-search mentions, no API key; feeds `check_mentions`
- ✅ **`src/checkers.py`** - deterministic (no-LLM) rule checks: structured data, crawler access, NAP consistency, mentions
- 🧠 **`src/clarity.py`** - the one LLM-based check (content clarity), rubric pulled from the playbook via RAG, never hardcoded
- 🧮 **`src/scoring.py`** - runs all five checks, ranks findings by impact, persists analyses/findings; matching page at `/components/scoring`
- 🧵 **`src/workflows/full_audit.py`** - `run_audit(business_id, run_id)`: the real pipeline (scrape → ingest → score → rank → save) run in a background thread by the chat route, logging progress to `agent_runs` at each stage for `GET /runs/<run_id>` polling
- 🧠 **`src/agent/graph.py`** - the agent loop: a LangGraph SUGGEST → PLAN → EXECUTE → MONITOR state machine that picks a finding, fixes it, verifies its own output, and decides whether to continue; `run_agent_loop(business_id, run_id)` run in a background thread by the chat route ("fix my site"), logging every decision to `agent_runs` for `GET /agent-runs/<run_id>` polling
- 📝 **`src/prompts/`** - system prompts as text files, one per agent
- 🧪 **`scripts/`** - quick scripting
- ✅ **`tests/`** - unit tests

## ✅ Final
- 📋 end with the header Summary and a 1-3 concise bullet points of what has been done under it. Each bullet point needs a bold prefix with a colon
- 🎯 end with **"🎯 All Done Amigo"**
