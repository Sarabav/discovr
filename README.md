# Discovr

**See your business the way an AI assistant does.**

## What It Does

When someone asks ChatGPT, Google's AI Overview, or a voice assistant
"who's a good dentist near me," the answer comes from how *legible* that
business's website and social profiles are to AI systems — not just from
traditional SEO. Most small business owners have no way to check that.

Discovr is a proof-of-concept web app, built chat-first: a business owner
signs up, lands directly in a single chat thread, and asking to "run my
AI-visibility audit" kicks off a real pipeline (see [Full Audit
Pipeline](#full-audit-pipeline)) that scrapes their website, scores it
against five categories, ranks the findings by impact, and returns a
scored report right inside the conversation, with live progress shown
while it runs. Every message after that is a follow-up question about
the results, answered in the same thread.

Two of the five categories aren't scored yet: NAP consistency needs a
Google Places connector that doesn't exist, and Mentions
(`src/components/find_mentions.py`, Reddit's public search) is correct
code that Reddit currently blocks at the network for any non-browser
client — both report "not measured" rather than a fake score. See
[What's Next](#whats-next) for the plan to unblock both.

## Screenshots

_(placeholder — add a screenshot of the chat here)_

## Features Implemented So Far

- **Authentication** — sign up and log in with just an email address (no
  password) via Flask-session-backed login state. Chat, settings, chunks,
  results, and components all require login (see
  [Authentication](#authentication)).
- **Chat-first UI** — no separate dashboard: the whole app is one
  scrolling message thread with a composer pinned to the bottom.
  Asking to run an audit kicks off the real pipeline in the background
  with live step-by-step progress; every message after that is a
  follow-up question about the results (see [Chat UI](#chat-ui)).
- **Real audit pipeline, in-thread** — scrapes the business's website,
  runs all five category checks, ranks the findings by impact, and
  persists the result, all triggered from a single chat message and
  rendered as part of the chat itself (see [Full Audit
  Pipeline](#full-audit-pipeline)).
- **Findings, ranked by impact** — a High/Medium/Low list of concrete,
  AI-ranked next steps, shown with the report.
- **Real, intent-routed chat** — every message is classified (question,
  run the audit, fix everything, fix one finding, check progress) and
  routed accordingly; general questions are answered from the knowledge
  base grounded in your real scores and findings when you have them
  (see [Chat Intent Routing](#chat-intent-routing)).
- **Knowledge base RAG** — `data/knowledge_base.md` is chunked and
  embedded (OpenRouter's embeddings API + ChromaDB) rather than loaded
  whole, and used to ground the content-clarity rubric, fix generation,
  and the agent loop's ranking (see [RAG Pipeline](#rag-pipeline)).
- **Settings page** — edit `data/knowledge_base.md` and the chatbot's
  system prompt directly from the app, behind login.
- **Chunks page** — inspect every chunk the knowledge base was split
  into, and re-run chunking with a different chunk size, behind login.
- **Response ratings** — thumbs up/down persistence and a Results page
  showing global stats and every rated response (see [Response
  Ratings](#response-ratings)); currently unused now that the widget
  that generated ratings has been removed (see [What's
  Next](#whats-next)).
- **Business Website component** — a real, working data-gathering
  component (not a mock): fetches a business's website plus a few likely
  internal pages and extracts visible text, JSON-LD schema, a best-effort
  NAP, and which AI crawlers its robots.txt allows. No API key needed
  (see [Business Website Component](#business-website-component)).
- **Scoring component** — a real scoring layer (not a mock): runs five
  category checks against a scraped website snapshot and persists the
  result. Three checks (structured data, crawler access, content
  clarity) are fully implemented today; NAP consistency and mentions
  return a skipped score until the Google Places and Brave Search
  connectors exist (see [Scoring Component](#scoring-component)).
- **Fix generator** — a "Generate fix" button on findings in the chat
  report produces a real fix (JSON-LD, rewritten copy, or numbered
  instructions), grounded in the business's own scraped content and the
  playbook's fixing guidance, with facts it can't confirm listed
  explicitly rather than invented, plus an objective pass/fail
  verification pass (see [Fix Generator](#fix-generator)).
- **Agent loop** — saying "fix my site" hands the whole findings list to
  a LangGraph agent that decides what to work on next, generates or
  plans a fix, checks its own output, and keeps going until everything's
  handled, with its reasoning streamed live into the chat (see [Agent
  Loop](#agent-loop)).
- **Workflows dashboard** — `/workflows` lists the app's end-to-end
  workflows as cards (components used, what it does, a Run button), with
  the same live step trail the chat shows, run from a dedicated page
  instead of by typing a chat message (see [Workflows
  Dashboard](#workflows-dashboard)).

## Technologies Used

- **Python 3** / **Flask** — web framework and routing
- **SQLite** (`sqlite3`, standard library) — persistence for users,
  businesses, analyses, findings, and recommendations
- **python-dotenv** — loads local config from `.env`
- **OpenRouter** — model-agnostic LLM API used by content clarity, fix generation, and the agent loop; also embeds knowledge base chunks and questions for retrieval (`src.agents.embed`, `openai/text-embedding-3-small` by default) — no local embedding model, see [Deploying to Render](#deploying-to-render)
- **LangGraph** — the agent loop's state machine (`src/agent/graph.py`)
- **ChromaDB** — stores chunk embeddings and serves similarity search
- **requests** / **beautifulsoup4** — HTTP fetching and HTML parsing for the Business Website component; **Playwright** is an optional headless-browser fallback for JS-heavy sites, not installed by default on Render (see [Deploying to Render](#deploying-to-render))
- **pytest** — unit tests for the deterministic scoring checks
- **Vanilla HTML/CSS/JS** — no frontend framework or build step

## Project Structure

```
discovr/
├── app.py                 # Flask entry point and routes
├── data/
│   ├── knowledge_base.md  # Chatbot facts, editable from the Settings page
│   ├── app.db              # SQLite database (created automatically, gitignored)
│   ├── chroma/              # ChromaDB vector store (created automatically, gitignored)
│   └── results.json         # Rated chatbot responses (created automatically, gitignored)
├── src/
│   ├── checkers.py        # Deterministic (no-LLM) rule checks: structured data, crawler access, NAP, mentions
│   ├── clarity.py         # The one LLM-based check: content clarity, rubric pulled from the playbook via RAG
│   ├── scoring.py         # run_all_checks, rank_findings, save_analysis
│   ├── chatbot.py         # classify_intent, answer_question, resolve_finding_ref, describe_progress
│   ├── agents.py          # OpenRouter model access
│   ├── rag.py              # Chunking, embedding, ChromaDB storage/retrieval for both the knowledge base and per-business collections
│   ├── ratings.py           # Thumbs up/down persistence and stats (data/results.json)
│   ├── components/
│   │   ├── __init__.py
│   │   ├── scrape_website.py  # Business Website component: scrape_website(), check_crawler_access()
│   │   └── fix_generator.py   # generate_fix/verify_fix/generate_verified_fix: RAG-grounded fixes
│   ├── workflows/
│   │   ├── __init__.py
│   │   └── full_audit.py  # run_audit(): the real chat-triggered pipeline (scrape -> ingest -> score -> rank -> save)
│   ├── agent/
│   │   ├── __init__.py
│   │   └── graph.py       # run_agent_loop(): LangGraph SUGGEST -> PLAN -> EXECUTE -> MONITOR loop
│   ├── prompts/
│   │   └── website_chatbot.txt  # System prompt for src.chatbot.answer_question
│   ├── auth.py            # Email-only signup/login validation, login_required, admin_required
│   ├── db.py              # SQLite schema and persistence (users, businesses, analyses, findings, fixes, agent_runs, ...)
│   ├── store.py           # Persistence dispatcher: src.db or src.supabase_store, based on src.data_source
│   ├── data_source.py     # Tracks the admin page's local/supabase selection (data/data_source.txt)
│   ├── supabase_client.py # Cached Supabase client (service-role key)
│   └── supabase_store.py  # Supabase-backed mirror of db.py's API, plus clone_local_to_supabase()
├── templates/
│   ├── landing.html       # Public marketing page at /
│   ├── login.html
│   ├── signup.html        # Email + business website
│   ├── dashboard.html     # The chat (requires login) — the whole app, at /dashboard
│   ├── settings.html      # Edit knowledge base / prompt (requires login)
│   ├── admin.html         # Admin hub: links to Components/Workflows/Chunks/Results, Data Source dropdown, clone button (admin only)
│   ├── admin_bar.html     # Muted "Admin — internal tools" bar, included by every admin page
│   ├── chunks.html        # Inspect and re-run chunking (admin only)
│   ├── results.html       # Rating stats and rated responses (admin only)
│   ├── components.html    # Architecture overview (admin only)
│   ├── component_website.html  # Business Website component page, at /components/website (admin only)
│   ├── component_scoring.html  # Scoring component page, at /components/scoring (admin only)
│   ├── workflows.html     # Workflows dashboard, at /workflows (admin only)
│   └── header.html        # Shared sticky header, included by every logged-in page
├── static/
│   ├── style.css          # Shared tokens (palette, type, radii, shadows), card/field/button primitives
│   ├── landing.css
│   ├── auth.css           # Centered-card-on-dark-hero layout for login/signup
│   ├── header.css
│   ├── header.js          # Avatar dropdown toggle
│   ├── admin_bar.css      # Muted admin-area header bar + sub-nav
│   ├── admin.css          # Data Source dropdown / clone summary styling
│   ├── admin.js           # Data Source dropdown + "Clone Local Data to Supabase" button
│   ├── chat.css           # Chat layout: message list, bubbles, composer; step-trail classes reused by workflows.js
│   ├── chat.js
│   ├── signup.js          # Saves business website to localStorage on submit
│   ├── component_website.css
│   ├── component_website.js
│   ├── component_scoring.css
│   ├── component_scoring.js
│   ├── settings.css
│   ├── settings.js
│   ├── chunks.css
│   ├── chunks.js
│   ├── results.css
│   ├── results.js
│   ├── components.css
│   ├── workflows.css      # Workflow card / pill / run-button styling, extends components.css
│   └── workflows.js       # Run button handlers + step-trail polling for the workflows dashboard
├── tests/
│   ├── test_agents.py     # Smoke test: calls src.agents.ask and prints the reply
│   └── test_checkers.py   # Fixture-based unit tests for src/checkers.py
├── .env.example            # Template for local environment variables
├── .python-version          # Pins the Python version Render's build uses
├── render.yaml               # Render Blueprint: web service, build/start commands, env vars
└── requirements.txt
```

## Installation & Local Setup

Requires Python 3.9+.

1. **Clone the repository**

   ```bash
   git clone <YOUR_GITHUB_REPO_URL>
   cd discovr
   ```

2. **Create and activate a virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

   Optional: for the Business Website component's JS-render fallback
   (see [Business Website Component](#business-website-component)),
   also install Playwright and its browser binary. It's not in
   `requirements.txt` (too heavy for Render's free tier — see
   [Deploying to Render](#deploying-to-render)); the app runs fine
   without it, it just won't render JS-heavy sites.

   ```bash
   pip install "playwright>=1.62,<2.0"
   playwright install chromium
   ```

4. **Set up environment variables**

   ```bash
   cp .env.example .env
   ```

   Then open `.env` and set:
   - `SECRET_KEY` to a real random value:
     ```bash
     python -c "import secrets; print(secrets.token_hex(32))"
     ```
   - `OPENROUTER_API_KEY` to a key from [openrouter.ai/keys](https://openrouter.ai/keys)
     (needed for content clarity, fix generation, and the agent loop)

5. **Run the app**

   ```bash
   python app.py
   ```

## Deploying to Render

`render.yaml` is a Render [Blueprint](https://render.com/docs/blueprint-spec)
— push it to your repo, then in the Render dashboard **New +** → **Blueprint**
and point it at the repo. It provisions one web service:

- **Runtime**: Python, pinned via `.python-version` (3.12 — chosen for
  broad prebuilt-wheel availability; Render's own default at one point
  landed on 3.14, which several of this app's heavier dependencies
  didn't have wheels for yet).
- **Build**: `pip install -r requirements.txt`. **Playwright is
  deliberately not installed** — its browser binary + OS libraries don't
  fit the free tier's 512MB. The Business Website component's JS-render
  fallback (see [Business Website
  Component](#business-website-component)) degrades automatically when
  Playwright isn't importable — every call site in
  `src/components/scrape_website.py` already catches that as just
  another exception and falls back to the plain `requests` fetch, so
  the app runs fine, it just won't render JS-heavy sites. To get that
  back on a bigger instance: add `playwright>=1.62,<2.0` back to
  `requirements.txt` and change the build command to
  `pip install -r requirements.txt && playwright install --with-deps chromium`.
- **Start**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4
  --timeout 120`. **1 worker**, several threads — no reason for more on
  an app that's I/O-bound (LLM/HTTP calls), not CPU-bound, and it avoids
  needless duplicate process overhead on a memory-constrained host. No
  `--preload` — that flag defaults off in gunicorn already (it's a bare
  flag, not `--preload on/off`), and its memory benefit (workers sharing
  one pre-loaded copy via copy-on-write after fork) only applies with
  multiple workers anyway. `--timeout 120` gives synchronous LLM calls
  (chat, fix generation, scoring) room — the audit and agent-loop routes
  return immediately and do their real work in a background thread
  either way.
- **Startup memory**: two changes together got this app to boot in
  ~30MB instead of OOM-killing on Render's 512MB free tier (measured
  locally under gunicorn):
  1. **No local embedding model.** RAG embeddings go through
     `src.agents.embed()` (OpenRouter's `/embeddings` endpoint) instead
     of a locally-run sentence-transformers model — which pulled in
     `torch`, by far the single heaviest thing this app ever loaded.
     There's no in-process model to load at all now, at boot or ever —
     see [RAG Pipeline](#rag-pipeline).
  2. **Lazy imports for what's left.** `chromadb` and `langgraph` are
     still real dependencies, but are imported inside the functions
     that actually use them (`src/rag.py`'s `_get_client()`,
     `src/agent/graph.py`'s `build_graph()`) rather than at module top
     level, and `app.py` no longer kicks off the RAG index build at
     import time — `src.rag.retrieve()` builds it synchronously on its
     own first call instead (`src.rag._ensure_ready`). Together this
     means gunicorn boot, and Render's health check, only pay for
     `chromadb`/`langgraph` the first time a request actually needs
     them, never before.
- **Env vars**: `SECRET_KEY` is auto-generated by Render. `FLASK_DEBUG` is
  set to `false` for production behavior (secure cookies; see
  `app.config.update(...)` near the top of `app.py`).
  `OPENROUTER_API_KEY` and the `SUPABASE_*` vars are marked `sync: false`
  — Render prompts for these in the dashboard rather than committing
  them; fill in `OPENROUTER_API_KEY` at minimum, and the Supabase ones
  only if you plan to use [Supabase
  mode](#data-source-local-sqlite-or-supabase).

**Storage is ephemeral by default.** Render's free-tier disk resets on
every deploy and restart, so `data/app.db` and `data/chroma/` don't
survive between deploys unless you attach a persistent disk (commented
out in `render.yaml` — needs a paid instance type, disks aren't
available on the free plan). The alternative that needs no disk at
all: switch `/admin`'s Data Source dropdown to Supabase after deploying,
so persistence goes through Postgres instead of the container's local
filesystem.

**No Blueprint?** You can also create the web service by hand in the
Render dashboard: set the build/start commands above directly in the
service's Settings, and add the same env vars.

   The database tables are created automatically on first run. Visit
   [http://localhost:8014](http://localhost:8014), sign up with your
   business's website, and you'll land straight in the chat.

## Environment Variables

See `.env.example` for the full list with descriptions. Summary:

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs Flask session cookies | _none — must be set_ |
| `DATABASE_PATH` | Path to the SQLite database file | `data/app.db` |
| `PORT` | Local dev server port | `8014` |
| `FLASK_DEBUG` | Enables Flask debug mode | `true` |
| `OPENROUTER_API_KEY` | Auth for OpenRouter model calls | _none — must be set_ |
| `OPENROUTER_MODEL` | Default OpenRouter model id | `nvidia/nemotron-3-super-120b-a12b:free` |
| `OPENROUTER_EMBEDDING_MODEL` | OpenRouter embedding model id, used by RAG (`src.agents.embed`) | `openai/text-embedding-3-small` |
| `SUPABASE_URL` | Supabase project URL | _optional — only used in Supabase mode, see [Data Source](#data-source-local-sqlite-or-supabase)_ |
| `SUPABASE_API_KEY` | Supabase **service-role** key (not the anon key — the app needs to bypass RLS) | _optional — only used in Supabase mode_ |
| `SUPABASE_DB_URL` | Direct Postgres connection string (session pooler) | _optional — only used by the "Clone Local Data to Supabase" button, to create tables_ |

`.env` is gitignored and never committed; `.env.example` documents the
required variables with placeholder values only.

## Chat Intent Routing

Nothing in the main chat is a canned response anymore. Every message
goes through `src.chatbot.classify_intent` — one structured LLM call
that returns `{"intent": ..., "finding_ref": ...}` — before `POST /chat`
decides what to do:

- **`run_audit`** — starts the [audit pipeline](#full-audit-pipeline),
  asking for the website URL first if it's missing.
- **`fix_all`** — starts the [agent loop](#agent-loop) over every open
  finding.
- **`generate_fix`** — fixes the one finding the message named or
  described. `finding_ref` (a short phrase like "schema" or "crawler
  access") is matched against the business's open findings' titles and
  categories by `src.chatbot.resolve_finding_ref`; no match or more
  than one match asks the user to be more specific instead of guessing.
  Calls the same `generate_verified_fix` the manual "Generate fix"
  button uses, and the chat renders the same fix card inline.
- **`check_progress`** — `src.chatbot.describe_progress` compares the
  two most recent persisted analyses (via
  `src.db.get_analyses_for_business`) and reports the overall and
  per-category deltas. Pure arithmetic on real numbers, not an LLM
  call — nothing to phrase, just report.
- **`question`** — `src.chatbot.answer_question` retrieves from the
  knowledge base exactly as before, but if the user has a current
  analysis, their real overall score, per-category scores, and open
  findings are folded into the system prompt too, so "how am I scored"
  gets answered with their actual numbers instead of a generic
  explanation of how scoring works.

Classification failure isn't swallowed: `ChatIntentError` propagates
out of `classify_intent` and `POST /chat` returns a real error (502),
shown in the thread with a Retry button — no silent fallback to a stub
response.

## Landing Page

`/` is a public marketing page (`templates/landing.html`,
`static/landing.css`) — a dark full-bleed hero with a coral radial glow
behind the headline, a browser-frame mockup of a real audit exchange, a
3-up "how it works" row, a sample score-ring section, and a closing CTA
band. It's the only page that doesn't require login; visiting it while
already logged in redirects straight to `/dashboard`.

## Chat UI

The dashboard is a single chat thread at `/dashboard`
(`templates/dashboard.html`, `static/chat.css`, `static/chat.js`). There
is no separate report page or history list; the whole app is one
scrolling `#chat-messages` column (max-width 760px) with a composer
pinned to the bottom via flexbox.

- **Empty state**: before the first message, a one-line explanation and a
  clickable example prompt ("Run my AI-visibility audit") are shown.
- **Every message goes to `POST /chat`**, which classifies intent and
  routes accordingly (see [Chat Intent Routing](#chat-intent-routing)):
  start a background audit run, ask for a missing website URL, work
  through findings, generate one fix, report progress, or answer a
  question grounded in the user's real results.
- **Live progress while the audit runs**: `chat.js` polls
  `GET /runs/<run_id>` every 1.5s and updates a step list in place
  (Scraping → Indexing → Scoring → Ranking → Saving) until the run finishes, then
  replaces it with the score card.
- **Errors are shown for real, with a Retry button**: if a stage fails
  (unreachable site, DB error), the actual error message is shown in
  the thread with a Retry button that resends the audit trigger — no
  silent fallback to fake data.
- **"Fix all findings" button**: the score card's findings section leads
  with this button rather than requiring the user to type "fix my site"
  — clicking it sends that exact phrase, classified as the `fix_all`
  intent (see [Agent Loop](#agent-loop)) under the hood, so typing it
  still works too, it's just no longer the primary way in.

## Full Audit Pipeline

`POST /chat` (`app.py`) is where an audit actually starts. Before intent
classification even runs, one thing is checked first: **the previous
turn asked for a website URL** (`session["awaiting_website_for"]` holds
the pending business id) — this message is treated as the answer, saved
via `update_business_website`, and the audit starts immediately.

Otherwise, once `classify_intent` returns `run_audit` (see [Chat Intent
Routing](#chat-intent-routing)): the logged-in user's most recent
business (`get_business_for_user`) is looked up. If it has no
`website_url` yet, a business row is created if needed,
`awaiting_website_for` is set, and the assistant asks for the URL in
the chat instead of guessing or falling back to a default. Once a URL
exists, the audit starts right away.

Starting an audit spawns a daemon thread running
`src.workflows.full_audit.run_audit(business_id, run_id)` and returns
`{"type": "run_started", "run_id": ...}` immediately, so the chat
request itself never blocks on scraping or LLM calls. `run_audit`:

1. Reads the business's `website_url` and calls `scrape_website()` +
   `check_crawler_access()` (see [Business Website
   Component](#business-website-component)), saving the result to
   `business_snapshots`.
2. Calls `ingest_business(business_id, snapshot)` to (re-)index the
   business's own content into its RAG collection (see [Per-Business
   RAG Ingestion](#per-business-rag-ingestion)), before scoring runs.
3. Calls `run_all_checks(snapshot)` then `rank_findings()` (see
   [Scoring Component](#scoring-component)).
4. Calls `save_analysis()` to write the `analyses` and `findings` rows.

At the start and end of every stage (`scraping`, `ingesting`,
`scoring`, `ranking`, `saving`), it writes a row to `agent_runs` with a
`status` (`running`/`done`/`error`) and, on failure, the real error
message — one row per transition rather than a single mutable row, so
`GET /runs/<run_id>` can replay the whole run's history. The
`ingesting` stage's `done` row carries the chunk count in its `message`
(e.g. "Indexed 6 chunks"). If a stage raises, the thread stops there;
nothing downstream silently continues on bad data.

`GET /runs/<run_id>` reads every `agent_runs` row for that run and
derives:

- `status` — `"error"` if any row errored, `"done"` once the `saving`
  stage's `done` row exists, otherwise `"running"`.
- `result` — once done, the analysis's `overall_score` and per-category
  scores (`None` for `nap_consistency`/`mentions` until their
  connectors exist) plus the findings, in ranked order, read straight
  from `analyses`/`findings` rather than kept in memory, so a page
  refresh mid-poll doesn't lose anything.

### Shared header

`/dashboard`, `/settings`, `/admin`, `/workflows`, `/chunks`,
`/results`, and `/components` all include the same
`templates/header.html` partial (a sticky 64px bar with a backdrop
blur) instead of duplicating header markup. Each page sets
`{% set active_page = '...' %}` before the include so the matching nav
link gets a coral underline. The top-level nav is Dashboard / Settings
only — normal users never see Workflows, Components, Chunks, or
Results. Log out lives under the circular avatar dropdown (initial
derived from the user's email), toggled by `static/header.js`; an
Admin link appears there too, but only when the logged-in user's
`is_admin` flag is set.

### Admin area

Workflows, Components, Chunks, and Results are developer/admin views,
not part of the normal user flow. `/admin` (`templates/admin.html`)
hubs them as cards; the pages themselves are unchanged, just no longer
reachable from the main nav. Every admin page includes
`templates/admin_bar.html`, a muted "Admin — internal tools" bar with
its own sub-nav, so it's visually obvious which side of the app you're
on. Access control happens server-side, not just in the nav: `/admin`,
`/components*`, `/workflows*`, `/chunks*`, and `/results*` (including
their run/data endpoints) are wrapped in `@admin_required`
(`src/auth.py`), which returns a real 403 for any logged-in non-admin
rather than just hiding the link. `users.is_admin` (default 0) drives
this and is mirrored into `session["is_admin"]` at login.

### Visual design

The whole app shares one token system defined in `static/style.css`:
`--ink`/`--ink-2` (near-black, used for dark sections like the hero and
CTA band), `--paper`/`--card` (warm off-white page background / white
raised surfaces), `--accent` (coral, buttons/links/active states) with
`--accent-2` (amber, used in the score ring), `--good`/`--warn`/`--bad`
status colors, `--text`/`--muted`, `--line` (1px borders), plus
`--radius-card` (12px) / `--radius-control` (8px) and two soft shadow
tokens (`--shadow-low`, `--shadow-high`) — never a harsh shadow. Every
page's CSS (`landing.css`, `auth.css`, `header.css`, `chat.css`,
`settings.css`, `chunks.css`, `results.css`,
`components.css`) consumes these same custom properties, so changing the
palette in one place (`:root` in `style.css`) re-skins the whole app.
Light/dark is automatic via `prefers-color-scheme` (swapping `--paper`
and `--card` to dark tones while keeping the coral accent), with
`color-scheme: light dark` set so native form controls follow along too.

Type is Fraunces (display serif, headlines and score numbers) paired
with Inter (everything else), both loaded via a Google Fonts `@import`
at the top of `style.css`.

## RAG Pipeline

`src/rag.py` holds two kinds of Chroma collections in the same
persistent client, kept separate from `src/agents.py` (which only knows
how to call OpenRouter) and from routes in `app.py`:

1. The **knowledge base** collection (`knowledge_base`) — rules,
   category definitions, examples — grounds content clarity's rubric,
   fix generation, and the agent loop's ranking.
2. One **per-business** collection (`business_<id>`) per audited
   business, holding that business's own scraped website content, so
   generated fixes can be grounded in its real details instead of
   invented ones (see [Per-Business RAG
   Ingestion](#per-business-rag-ingestion)).

Both reuse the same chunker.

- **Chunking**: `chunk_text()` splits the knowledge base generically on
  `##`/`###` headers into sections (no section names are hardcoded, so
  this keeps working whichever headings the file has), then packs each
  section's paragraphs into chunks of about 500 tokens by default (a
  word-count approximation, configurable), never splitting a sentence
  and never combining paragraphs from different sections. A paragraph
  larger than the chunk size falls back to sentence-level packing. Each
  chunk's text starts with its section heading. When a section needs
  more than one chunk, consecutive chunks overlap by about 50 tokens (the
  trailing content of one reappears at the start of the next) so context
  right at the cut point isn't lost to either chunk.
- **Embedding**: each chunk's text is embedded via `src.agents.embed()`
  — OpenRouter's `/embeddings` endpoint (`openai/text-embedding-3-small`
  by default, `OPENROUTER_EMBEDDING_MODEL` to change it), the same
  provider and API key already used for chat calls — and stored in a
  persistent ChromaDB collection at `data/chroma/`, along with its
  section heading and token count. No local embedding model runs in
  this process; earlier this used sentence-transformers (`all-MiniLM-
  L6-v2`), which pulls in torch and was the single biggest thing this
  app loaded into memory, more than Render's 512MB free tier could
  handle at boot — see [Deploying to Render](#deploying-to-render).
- **Retrieval**: `retrieve(question, top_k=3)` embeds the question and
  returns the 3 most similar chunks by cosine similarity, each with its
  similarity score.
- **Lazy indexing**: nothing builds the index at import time anymore.
  The first call to `retrieve()` after boot builds it synchronously if
  it isn't ready yet (`src.rag._ensure_ready`); `GET /rag/status`
  exposes progress either way (`ready`, `building`, `chunk_count`,
  `chunk_size`, `error`).
- **Chunks page** (`/chunks`, requires login): lists every currently
  indexed chunk (id, section heading, token count, full text), and lets
  you pick a different chunk size and re-run chunking and embedding via
  `POST /rag/rebuild`, with the same progress spinner pattern.

Editing the knowledge base from the [Settings page](#settings) does not
automatically re-index it; re-run chunking from the Chunks page after
making edits you want reflected in retrieval.

### Per-Business RAG Ingestion

`ingest_business(business_id, snapshot)` builds a collection named
`business_<id>` from that business's own scraped content: the page
title, meta description, every schema.org node rendered as readable
`Type - field: value` lines (so structured facts like address and phone
end up embedded too, not just page copy), and the full crawled page
text (`snapshot["text"]`). It's chunked with the same `chunk_text()`
used for the knowledge base, then embeds and stores it exactly like
`build_index()` does — deleting and recreating the collection first, so
re-running an audit replaces the old content rather than piling chunks
on top of it. Each chunk's metadata carries `business_id`,
`source_url`, and `page_title`. Returns the chunk count.

`retrieve_business_context(business_id, query, k=5)` queries that one
business's collection and returns a plain list of chunk texts (not the
dict-with-similarity shape `retrieve()` returns, since callers here
just want grounding text for a prompt). Returns `[]` instead of raising
if the business hasn't been ingested yet.

Called from [the audit pipeline](#full-audit-pipeline) right after the
snapshot is saved and before scoring, so a business's real content is
already indexed and ready to ground generated fixes by the time
scoring finishes. Run `python -m src.rag` to ingest the most recent
snapshot in the database standalone and print what two test queries
("what services does this business offer", "where is this business
located") retrieve — useful for checking retrieval quality without
running a full audit.

## Response Ratings

**Currently unused**: the floating "Ask Discovr" widget was the only
UI that posted 👍/👎 ratings (`POST /rate`), and it's been removed (see
[What's Next](#whats-next)). `POST /rate`, `src/ratings.py`, and the
Results page (`/results`) still exist and still work if called, but
nothing in the app calls them anymore.

- `src/ratings.py` holds all read/write logic against
  `data/results.json` (a flat JSON array, one object per rated
  response), including `save_rating()` and `get_rating_stats()`.
  A `threading.Lock` serializes writes since the file has no built-in
  transaction support.
- Each entry stores the question, the answer, the rating (`up`/`down`),
  the model used, the response time in seconds, input/output token
  counts, and a UTC timestamp.
- The Results page (`/results`, requires login) shows global stats
  (thumbs up, thumbs down, percent positive, total rated) at the top,
  then every rated response as a row (icon, model badge, question,
  answer); clicking a row expands it in place to show every stored field.

## Business Website Component

Unlike `src/analysis.py` (still hardcoded sample data), the Business
Website component actually fetches a real site. It's the first of the
"Data Connectors" named on the `/components` overview page to be
implemented; the same `src/components/` pattern is meant to be reused
for the others (Google Business Profile, Brave Web Search).

**What it extracts** (`src/components/scrape_website.py`):

- `scrape_website(url)` fetches the page (real User-Agent, 10s timeout),
  strips `<script>`/`<style>`/`<nav>`/`<footer>`, and returns the visible
  text, page title, meta description, every `<script type="application/ld+json">`
  block (malformed JSON-LD is skipped, not fatal), and a best-effort NAP.
  It also follows up to 3 internal links matching `/about`, `/services`,
  `/contact`, or `/faq` and folds their text and schema in, recording
  every URL actually fetched.
- **JS-rendered sites**: a plain GET is tried first. If the result looks
  like an empty shell (page text under 500 characters, fewer than 3
  links found, or no JSON-LD at all — the signature of a client-rendered
  single-page app), that URL is re-fetched with headless Chromium via
  Playwright (`goto(url, wait_until="networkidle", timeout=20000)`), and
  the resulting HTML is parsed with the exact same BeautifulSoup logic.
  Once the main page needs this fallback, the rest of the crawl (its
  internal links) is rendered with that *same* browser instance rather
  than re-trying `requests` per page — internal links are re-extracted
  from the rendered page, not the original empty HTML, since a
  JS-rendered site's internal pages are JS-rendered too. Which method
  actually produced the main page's result is reported as
  `render_method` (`"requests"` or `"playwright"`).
- **Unreachable internal pages** are reported, not silently dropped: if
  a linked internal page 404s (or otherwise fails) on direct navigation,
  which is common for single-page apps whose hosting has no catch-all
  rewrite to `index.html` (a client-side-only route like `/contact` 404s
  even though a human can click to it from the rendered site), it's
  added to `unreachable_pages` as `{"url", "status"}` instead of just
  being skipped. A page an AI crawler can't directly navigate to is
  invisible to it in exactly the same way, which is itself a finding
  worth surfacing.
- **NAP extraction** checks several sources in priority order and merges
  whichever is found first per field, checking the footer specifically
  before the rest of the page (small business sites usually put contact
  details there): schema.org data first; then `<address>` tags and
  `itemprop="address"` elements; then `tel:` links for phone; then regex
  over the footer text; then regex over the full page text as a last
  resort. The phone regex covers North American formats (`+1`, parens,
  dots, dashes, spaces). The address regex requires a street number,
  street name, and street-type word, with an optional trailing
  city/region/postal segment (accepting both US ZIP and Canadian postal
  code shapes). Name is `og:site_name`, then the page `<title>` with any
  `| Tagline` / `- Tagline` suffix trimmed, then a logo `<img>`'s `alt`
  text.
- `check_crawler_access(url)` fetches `/robots.txt` and reports whether
  each of GPTBot, ClaudeBot, PerplexityBot, Google-Extended, and CCBot is
  disallowed, plus the raw robots.txt text.
- Neither function ever raises: network failures, timeouts, and bad
  responses are all caught and reported through the dict's `error` field
  instead, so the route and the CLI both stay simple. If the Playwright
  fallback itself fails (most likely because `playwright install
  chromium` was never run), that's logged to stderr and the original
  `requests` result is kept rather than the whole scrape failing.

**No API key needed** — both functions only make HTTP requests (plain or
via a local headless browser) to the target site itself.

**Running it standalone**, without the Flask app:

```bash
python -m src.components.scrape_website https://example.com
```

prints the `scrape_website()` result followed by the
`check_crawler_access()` result, both as formatted JSON.

**In the app**: `/components/website` (requires login) is the component
page — URL field pre-filled with `https://www.wafflehouse.com` (a real
business site, plain HTML, demonstrates the fast `requests` path), plus
a "Try a JS-heavy example (fresh2home.ca)" button that fills in and runs
a single-page-app site to demonstrate the Playwright fallback. Results
are broken into labelled sections (title/meta, schema markup, crawler
access per bot, NAP, page text with a 1000-character preview and a
total character count, pages crawled, and any unreachable pages), plus
a render-method badge ("Fetched with requests" / "Rendered with
headless browser"), the elapsed time, and the full raw JSON in a
collapsed `<details>`.
`POST /components/website/run` calls both functions and returns their
combined result; errors from either surface as a banner rather than a
blank page. The "Business Website" card on `/components` links here.

**Setup note**: Playwright isn't in `requirements.txt` by default (see
[Installation & Local Setup](#installation--local-setup) and
[Deploying to Render](#deploying-to-render)) — install it plus its
browser binary once to enable the JS-render fallback locally:

```bash
pip install "playwright>=1.62,<2.0"
playwright install chromium
```

Without this, the JS-rendered-site fallback silently fails (falling back
to the plain-`requests` result) rather than breaking the component.

## Scoring Component

The scoring layer turns a scraped snapshot (from the Business Website
component) into a scored, ranked report. It's split into two kinds of
checks, on purpose:

- **`src/checkers.py`** — deterministic, no LLM calls. Each function
  takes a `snapshot` dict and returns `{"score": 0-100 or None,
  "findings": [...]}`:
  - `check_structured_data` — looks for a `LocalBusiness` (or a
    recognized subtype like `Dentist`, `Plumber`, `Restaurant`,
    `HairSalon` — editable via the `LOCAL_BUSINESS_TYPES` set) schema.org
    block, including `@graph`-wrapped schema, and checks it has every
    field in `REQUIRED_FIELDS`. Score 0 if no schema at all; otherwise
    100 minus 20 per missing field.
  - `check_crawler_access` — reads the robots.txt result from the
    Business Website component and deducts 20 points per AI crawler bot
    that's disallowed, plus 15 per unreachable internal page.
  - `check_nap_consistency` — returns `score: None` with a `"skipped"`
    reason today, since it needs a Google Places connector that doesn't
    exist yet. The real comparison logic (NAP field matching with
    street-abbreviation normalization) is already written behind an
    `if places_data:` branch, so it activates automatically the moment
    that connector is added, no changes needed here.
  - `check_mentions` — the tiered scoring (0 → 20/High, 1-2 → 60/Medium,
    3+ → 90/Low, with the finding listing the actual threads found and
    their links) is real and complete, backed by
    `src/components/find_mentions.py` searching Reddit's public
    `/search.json` for posts that actually contain the business name.
    It's unused today: Reddit returns 403 for any non-browser client,
    confirmed at the network level (real browser UA and headers still
    blocked), not something a header change can fix. Missing data and a
    search failure both return `score: None` with `"Not measured yet —
    needs a search connector"` — same treatment as NAP consistency, and
    never a fake 0. The scoring activates automatically the moment
    `find_mentions()` can actually reach Reddit — no changes needed here.
- **`src/clarity.py`** — the one LLM-based check, `check_content_clarity`.
  It retrieves the "Content Clarity" section (with its good/bad examples)
  from the playbook's RAG index at request time rather than hardcoding a
  rubric in the prompt, sends the first ~1500 characters of the page
  text, and asks for structured JSON (`score`, `missing`, `worst_passage`,
  `reason`) at `temperature=0`, requesting the provider's native JSON
  mode (`ask_structured(..., json_mode=True)`) so the model is
  constrained from returning prose around the object in the first place.
  Parsing itself goes through `src.agents.extract_json_object`, which
  strips a markdown code fence and any prose before/after the object —
  belt-and-braces for models that ignore JSON mode. If the response
  still isn't parseable, the call is retried once (logging the raw
  response both times) before giving up; a parse failure that survives
  the retry returns `score: None` with a skipped reason distinct from a
  general API failure, so `_verify_content_clarity_fix` in
  `src/components/fix_generator.py` reports it as "unavailable" (check
  couldn't run), not "failed" (fix was checked and fell short) — see
  [Agent Loop](#agent-loop). A sanity check clamps the score to 60 if
  it's 70+ while 2 or more items are missing, since that combination
  means the model contradicted itself. On any other API failure it
  returns `score: None` with a skipped reason rather than raising.

`src/scoring.py` orchestrates both:

- `run_all_checks(snapshot)` runs all five checks and returns
  `overall_score` (the mean of whichever category scores aren't `None`,
  rounded), `categories` (score or `None` per category), `skipped`
  (reason per skipped category), and the combined `findings` list.
- `rank_findings(findings, snapshot)` makes one LLM call to reorder
  findings by real AI-visibility impact and add a one-sentence
  `why_it_matters` to each (Crawler Access findings generally rank
  first, since a blocked bot can't see anything else on the site). If
  the call fails, it falls back to sorting by each finding's own
  `priority` (High/Medium/Low) instead of raising.
- `save_analysis(business_id, snapshot_id, results)` writes one
  `analyses` row and one `findings` row per finding, returning the new
  `analysis_id`.

**In the app**: `/components/scoring` (requires login) pastes a URL,
scrapes it, scores it, and shows the overall score, each category
(with "Skipped — reason" where applicable), and the ranked findings
list, plus the full raw JSON in a collapsed `<details>` for debugging.
`POST /components/scoring/run` runs the whole pipeline (scrape →
checks → rank → persist) and returns the combined result. The "Runs
the Rule Checks" card on `/components` links here.

**Tests**: `tests/test_checkers.py` covers `check_structured_data` and
`check_crawler_access` with fixtures for a site with complete schema, a
site with none, a site blocking GPTBot, a site with no robots.txt, and
a site with two unreachable pages; `check_mentions`'s 0/1-2/3+ scoring
tiers and its skip-on-real-failure behavior; and NAP consistency's
activate-behind-a-branch behavior once Places data exists. Run with:

```bash
pytest tests/test_checkers.py -v
```

## Fix Generator

`src/components/fix_generator.py` turns a finding into the actual fix,
grounded in two retrieved sources rather than invented: the business's
own scraped content (`retrieve_business_context`, see [Per-Business RAG
Ingestion](#per-business-rag-ingestion)) and the playbook's "Tips for
Fixing" guidance (`retrieve`) — so neither the facts nor the how-to
advice are hardcoded in Python.

- **`structured_data`** — `generate_fix` asks the model for a complete
  JSON-LD block, picking the most specific `@type` the retrieved
  content supports (falling back to `LocalBusiness`). **The "never
  invent a fact" rule is enforced in code, not just by prompt
  instruction**: after the model responds, every `REQUIRED_FIELDS`
  value is checked against the retrieved content (`_value_confirmed`)
  and dropped — moved to `needs_from_owner` instead — if it doesn't
  actually appear there, regardless of what the model claimed. A
  business with no address or phone anywhere on its site (e.g. a
  1,900-location chain like Waffle House) gets a schema with only
  `@context`/`@type` and `needs_from_owner: ["name", "address",
  "telephone", "openingHours", "areaServed"]` — never a plausible-looking
  invented address.
- **`content_clarity`** — rewrites `finding["worst_passage"]` (now
  attached to every content-clarity finding by `src/clarity.py`) into a
  2-3 sentence replacement using only retrieved facts, returning both
  `before` and `after` so the UI can show a diff.
- **`crawler_access`** and **`nap_consistency`** — `fix_type:
  "instruction"`, built deterministically (no LLM call, nothing to
  hallucinate) from the finding's own data plus the same playbook
  guidance: exact robots.txt lines to remove for a blocked bot, or the
  catch-all rewrite for a host (Netlify/Vercel/Apache) for an
  unreachable page; for NAP mismatches, which value to treat as
  canonical (the Google Business Profile one) and exactly which field
  to change where.

`verify_fix(finding, fix)` is an objective pass/fail, not another LLM
opinion:

- `structured_data` — the content parses as JSON, has `@context` and
  `@type`, and every `REQUIRED_FIELDS` entry is either present and
  non-empty or listed in `needs_from_owner`.
- `content_clarity` — re-runs `check_content_clarity()` on the
  rewritten text and passes only if the score improved by 10 or more.
- `crawler_access`/`nap_consistency` — always `verified: False, reason:
  "needs_human"`, since there's nothing to check automatically.

`generate_verified_fix(finding, business_id)` ties it together: for
`content_clarity`, if the first attempt doesn't verify, it regenerates
once more (2 attempts max) before accepting whatever it produced with
`verified: False`; it then writes one row to the `fixes` table
(`finding_id`, `fix_type`, `content`, `verified`, `attempts`) via
`src.db.create_fix`. This is what `POST /findings/<finding_id>/fix`
calls.

**In the app**: every fixable finding card in the chat report (all
categories except `mentions`, which has no fix generator) has a
"Generate fix" button. Clicking it renders a fix card in place:
a syntax-styled code block with a Copy button for generated JSON-LD, a
before/after diff for rewritten copy, or numbered steps for
instructions — plus a "You'll need to add: ..." note when
`needs_from_owner` is non-empty, and a verified/unverified badge.

## Agent Loop

Generating one fix at a time is `POST /findings/<id>/fix`. Working
through *all* of a business's open findings on its own — deciding what
to fix next, acting, checking its own output, and deciding whether to
continue — is `src/agent/graph.py`, a [LangGraph](https://langchain-ai.github.io/langgraph/)
state machine. It calls nothing new: the audit workflow, the checkers,
and `src/components/fix_generator.py` already exist — this module only
wires them into a loop and logs every decision.

```
SUGGEST -> PLAN -> EXECUTE -> MONITOR -> SUGGEST | END
             \_______________________________/
              (instruction findings skip straight
               back to SUGGEST — nothing to verify)
```

- **SUGGEST** looks at every `open` finding in a category
  `fix_generator` actually knows how to fix (everything except
  `mentions`), retrieves the playbook's "Tips for Fixing" guidance, and
  makes one LLM call to rank them by real impact and choose one, with a
  one-sentence reason. **Crawler Access always wins**, enforced in code
  (not just prompted for) after the LLM call returns: if any open
  finding is `crawler_access` and the model picked something else, the
  choice is overridden and the override is logged — a fix to schema or
  copy does nothing on a page a crawler can't fetch. No open findings
  left (or the max-findings-handled limit is reached) sets `done=True`.
- **PLAN** is not an LLM call — a plain mapping from
  `finding.category` to `fix_type`. `structured_data`/`content_clarity`
  route to EXECUTE. `crawler_access`/`nap_consistency` are generated
  once right here (deterministic, nothing to verify) and marked
  `needs_human`, skipping EXECUTE/MONITOR entirely.
- **EXECUTE** calls `generate_fix(finding, business_id, retry_reason=...)`
  and saves the attempt to `fixes`. On a retry, the previous verification
  failure's reason is threaded into the prompt so the model doesn't
  repeat the same mistake.
- **MONITOR** calls `verify_fix`, which returns one of three statuses —
  conflating them was a real bug, since retrying on a check that
  couldn't run risks discarding a perfectly good fix and burns another
  API call for nothing:
  - **`passed`** — the finding is marked `resolved`, returns to SUGGEST.
  - **`failed`** — the check ran and the fix didn't meet the bar. Fewer
    than 2 attempts made goes back to EXECUTE with the failure reason
    threaded into the retry prompt; at 2 attempts the finding is marked
    `failed` and returns to SUGGEST. Never loops forever on one finding.
  - **`unavailable`** — the check itself couldn't run (API error, rate
    limit, or an unparseable model response — `_verify_content_clarity_fix`'s
    `check_content_clarity` calls are the only place this can happen; the
    deterministic structured-data check never can). No retry: the finding
    is marked `needs_human` with reason `"couldn't verify — <error>"` and
    the loop returns to SUGGEST.

  The chat's fix cards read this distinction back from the finding's
  persisted `status`, not a plain verified/unverified bool, so a broken
  checker never shows the same badge as a bad fix: `resolved` -> green
  "Verified", `needs_human` -> amber "Couldn't verify automatically —
  &lt;reason&gt;", `failed` -> red "Verification failed — &lt;reason&gt;".
  The reason text itself isn't a separate column — `app.py`'s
  `_verification_reason` recovers it from the finding's last MONITOR
  step message, the same "read it back out of the log" approach
  `_needs_from_owner_from_content` uses for FILL IN fields.

**Measuring its own effect, not just that the output parsed**: once the
loop ends, `run_agent_loop` re-runs `run_all_checks` against a *copy*
of the original snapshot with every resolved fix's actual effect
substituted in — the generated JSON-LD block replacing whatever
business schema node was there, the rewritten passage replacing
`worst_passage` in the page text — and logs two MONITOR steps.

The first is a two-part projection, not one: scoring only what the
agent generated makes the ceiling look artificially low, since
instruction-type findings (blocked crawlers, hosting config, Google
listing changes) never appear in it. So it shows current score, score
with the agent's own generated fixes applied, and — assuming every
open instruction-type finding also gets done — the real ceiling:
`"58 today · 73 with the fixes below applied · 87 if you also
complete the 1 manual step"`. Only categories a resolved fix actually
touched get re-scored from the modified snapshot for the middle
number; `crawler_access`/`nap_consistency` keep their current
persisted score there (re-deriving them needs data that isn't
persisted, like robots.txt), but are assumed to reach 100 for the
third number once their open instruction finding is resolved.

The second MONITOR step is "what's still holding the score back" —
so there's always a next step, not a dead end: `FILL IN: ...` fields a
resolved generated fix still needs the owner to supply (see the fix
generator's placeholder markers above), plus any category that's
never been measured at all (`skipped_json` — e.g. Mentions with no
search connector). Both projections are surfaced in the chat's final
summary alongside resolved/needs-owner/failed counts, the second as a
bulleted list under "Still holding the score back."

**Hard limits**, checked at the top of every node so the graph always
stops cleanly with `done_reason` set: 15 node executions total, 2 fix
attempts per finding, 6 findings handled in one run.

**Logging is how the loop is demonstrated.** Every node writes a row to
`agent_runs` before returning — `step_number`, the node name (as
`stage`), what it saw (`input_summary`), and what it decided and why
(`message`) — the same table the audit workflow uses, with `suggest`/
`plan`/`execute`/`monitor`/`done` added to its `stage` values. A run
looks like:

```
1  SUGGEST  choosing 'GPTBot is blocked in robots.txt' — overridden:
            Crawler Access outranks everything else
2  PLAN     fix_type=instruction (category=crawler_access) — generated
            steps once, marked needs_human
3  SUGGEST  choosing 'Missing: specific services' — LLM ranking
            unavailable, falling back to priority order
4  PLAN     fix_type=generated (category=content_clarity) — routing to
            EXECUTE
5  EXECUTE  generated content_clarity fix
6  MONITOR  passed — resolved
7  SUGGEST  stopping — all findings handled
```

**In the app**: `POST /chat` classifies phrases like "fix my site",
"fix everything", or "work through my findings" as the `fix_all` intent
(see [Chat Intent Routing](#chat-intent-routing)); if the business
hasn't been audited yet, it says so instead of guessing. It starts
`run_agent_loop(business_id, run_id)` in a background thread
and returns immediately, same pattern as the audit. `chat.js` polls
`GET /agent-runs/<run_id>` and renders each new `agent_runs` row as a
monospace reasoning line in place, streams a fix card for every
finding the loop resolves or marks `needs_human` as it completes (not
just at the end), and closes with a summary: how many resolved, how
many need the owner, how many failed.

**Test that matters**: run against two differently-shaped businesses
and the paths differ. Against Waffle House (blocked crawlers, no
business schema), every SUGGEST call is overridden to a `crawler_access`
finding and PLAN handles it inline — 13 steps, SUGGEST/PLAN alternating,
EXECUTE/MONITOR never called, stopping at the 6-findings-handled limit
with `needs_human: 6`. Against a business with clean schema but vague
copy, SUGGEST picks the one `content_clarity` finding and the graph
runs the full EXECUTE → MONITOR retry loop — a structurally different
step sequence, not just different numbers, which is what confirms
SUGGEST is actually deciding something rather than just walking a fixed
pipeline.

## Workflows Dashboard

`/workflows` (requires login) lists the app's end-to-end workflows as
cards — what each one uses (as small pills) and a numbered description
of what it does — matching the visual style of `/components`
(`components.css`, reused rather than duplicated).

- **AI Visibility Audit** and **Fix My Site** are real: their Run
  buttons call `POST /workflows/audit/run` and `POST /workflows/fix/run`,
  which reuse the exact same `_start_audit`/`_start_agent_loop` helpers
  the chat's "run my audit" / "fix my site" intents call — same
  background thread, same `agent_runs` logging. The card polls
  `GET /runs/<run_id>` or `GET /agent-runs/<run_id>` (the same routes
  the chat already polls) and renders the live step trail inline on the
  card, via `static/workflows.js` — a small, self-contained script that
  reuses `chat.css`'s `.step-row`/`.agent-step-row` classes rather than
  duplicating chat.js's DOM-specific rendering.
- **Weekly Re-Check** isn't implemented — no cron scheduling or
  previous-audit diffing exists yet — so its Run button is rendered
  `disabled` with "Not implemented yet," and has no click handler at
  all (`workflows.js` only wires up cards with a `data-workflow`
  attribute).
- Both real workflows fail clearly if their prerequisite is missing: no
  business website on file yet, or (for Fix My Site) no analysis yet —
  a 400 with a real error message, shown on the card, not a silent
  no-op.

## Settings

The Settings page (`/settings`, requires login) has two editable text
panes: one for `data/knowledge_base.md`, one for
`src/prompts/website_chatbot.txt`. Each has its own Save button and shows
a confirmation or error message; saving writes straight back to the file
on disk. `src/agents.py` provides the matching `load_prompt`/`save_prompt`
and `load_knowledge_base`/`save_knowledge_base` functions.

## Authentication

Discovr identifies accounts by **email + password**:

- **Sign up** (`/signup`) creates a `users` row for an email not seen
  before, hashing the password with `werkzeug.security.generate_password_hash`
  (PBKDF2) before it's ever persisted — `password_hash` is the only
  form of the password that reaches the database. A password under 8
  characters, or an email that's already registered, shows an error
  instead of creating an account.
- **Log in** (`/login`) looks up the `users` row for the submitted
  email and verifies the password against its hash with
  `check_password_hash`. A wrong email and a wrong password return the
  identical "Invalid email or password" error, so a failed attempt
  doesn't reveal which emails have accounts.
- **Log out** (`/logout`) clears the session.
- The chat (`/`), `/chat`, `/runs/<run_id>`, `/settings`, `/chunks`,
  `/results`, and `/components` are all wrapped with the
  `login_required` decorator (`src/auth.py`), which redirects anonymous
  visitors to `/login`; `/admin` and every developer view under it
  additionally require `admin_required` (`session["is_admin"]`, set at
  login from the `users.is_admin` column) — see [Admin
  Area](#admin-area).

Accounts created before password auth existed (or provisioned directly,
e.g. via a script) have a `NULL` `password_hash` and can't log in until
one is set (`src.db.set_password`/`src.store.set_password`) — `src.auth.login`
treats a missing hash as a failed login, never a free pass. There is
still no password-reset flow or email verification; consider those
(plus rate-limiting `/login`) before this holds real user data at
scale.

## Database

Discovr persists data in SQLite (path configurable via `DATABASE_PATH`),
using Python's built-in `sqlite3` module. All database access is
isolated in `src/db.py` — routes in `app.py` never run SQL directly.
`init_db()` creates every table below (if it doesn't already exist) once,
when the app starts, and writes go through `src.db.transaction()`, a
context manager that wraps each write in a transaction (commit on
success, rollback on error) and uses parameterized queries throughout to
avoid SQL injection.

The `businesses`/`business_snapshots`/`analyses`/`findings`/`agent_runs`
tables back the real chat audit — see [Full Audit
Pipeline](#full-audit-pipeline).

- **`users`** — `id` (UUID text), `email` (unique), `password_hash`
  (PBKDF2 via `werkzeug.security`, never the plain password — see
  [Authentication](#authentication)), `is_admin` (0/1, default 0 —
  gates the [admin area](#admin-area)), `created_at`.
- **`businesses`** — a business belonging to a user: `name`,
  `website_url`.
- **`business_snapshots`** — the raw material an analysis is based on
  for a business at a point in time: `website_text`,
  `website_schema_json`.
- **`analyses`** — one scored run against a specific snapshot:
  `overall_score` plus a nullable score per category
  (`nap_consistency_score`, `structured_data_score`,
  `content_clarity_score`, `crawler_access_score`, `mentions_score`) —
  nullable since NAP consistency and mentions are skipped until their
  connectors exist.
- **`findings`** — individual findings for an analysis: `category`
  (constrained to the five scoring categories), `title`, `description`,
  `priority` (High/Medium/Low), `fix_type` (`generated` for LLM-derived
  findings like content clarity, `instruction` for deterministic ones
  like a blocked crawler), `why_it_matters` (filled in by
  `rank_findings`), `worst_passage` (content-clarity findings only — the
  passage `src/components/fix_generator.py` rewrites), and `status`
  (`open`/`resolved`/`needs_human`/`failed`, defaulting to `open`,
  updated by the [agent loop](#agent-loop) as it works through them).
- **`fixes`** — one row per fix attempt: `finding_id`, `fix_type`,
  `content` (the JSON-LD, rewritten copy, or instruction steps),
  `verified`, `attempts`, and `run_id` (nullable — set when the fix came
  from an [agent loop](#agent-loop) run rather than a single manual
  "Generate fix" click, so `GET /agent-runs/<run_id>` can find them).
- **`recommendations`** — recommendations tied to a finding, each with a
  `priority` (High/Medium/Low), `why`/`how` text, and a `status`
  (`not_started`/`fix_generated`/`applied`) for tracking whether a fix
  has been generated or applied yet. Not yet written to by the scoring
  pipeline.
- **`agent_runs`** — progress log shared by both the audit workflow and
  the agent loop: one row per `(run_id, stage, status)` transition.
  `stage` is `scraping`/`ingesting`/`scoring`/`ranking`/`saving` for an
  audit, or `suggest`/`plan`/`execute`/`monitor`/`done` for an agent
  loop run; `status` is `running`/`done`/`error`. `message` carries the
  audit's real error text on failure, or the agent loop's decision +
  reason for each step; `step_number`/`input_summary` are populated only
  by the agent loop. `GET /runs/<run_id>` (audit) and
  `GET /agent-runs/<run_id>` (agent loop) each read the full set for
  their own run_id to answer "what's happening right now."

All primary keys are UUID strings (`src.db.new_id()`), generated in
Python rather than relying on SQLite autoincrement, since IDs need to be
assignable before a row is inserted (e.g. an `analyses` row referencing a
`snapshot_id` created in the same transaction).

The SQL is written in a driver-agnostic style so migrating to PostgreSQL
later mainly means swapping `get_connection()` for a different driver —
see [What's Next](#whats-next).

## Data Source (Local SQLite or Supabase)

Every route and background job reads/writes through `src/store.py`
rather than `src/db.py` directly. `store.py` re-exports the same
function names as `db.py` (`create_business`, `get_findings`, etc.),
but each one dispatches at call time to either `src.db` (local SQLite)
or `src.supabase_store` (Supabase), based on `src.data_source`. This
means switching backends never needs a restart — the next request just
resolves differently.

- **The switch** lives on `/admin` as a "Data Source" dropdown (Local /
  Supabase). Selecting one calls `POST /admin/data-source`, which
  writes the choice to `data/data_source.txt` (gitignored, generated —
  absent means `local`). `src.data_source.get_data_source()` reads that
  file fresh on every call, so there's no in-memory state to fall out
  of sync across the Flask reloader's worker/watcher processes.
- **`src/supabase_store.py`** mirrors `src/db.py`'s public API 1:1
  (same function names, same argument shapes, same return shapes —
  plain dicts instead of `sqlite3.Row`, which behave the same for every
  caller in this codebase) using the official `supabase-py` client with
  the **service-role** key (`SUPABASE_API_KEY`), so the app's own
  reads/writes are never blocked by row-level security.
- **`POST /admin/clone-to-supabase`** ("Clone Local Data to Supabase" on
  the admin page) first calls `ensure_schema()`, then copies every row
  from the local SQLite database into Supabase, table by table in
  foreign-key order (`users` → `businesses` → `business_snapshots` →
  `analyses` → `findings` → `fixes`/`recommendations` → `agent_runs`).
  It's idempotent: each table is upserted with `on_conflict="id",
  ignore_duplicates=True`, so a row already in Supabase is silently
  skipped rather than duplicated on a repeat run — only the rows
  PostgREST actually inserts come back in the response, so `copied` is
  a real count, not the batch size. Every insert's response is checked;
  a table that fails (schema not ready, a rejected row) gets the real
  error message in its own summary entry, never a silent `0 copied`
  that reads as success.
- **Table creation needs a direct Postgres connection, not the REST
  API.** The REST API a Supabase URL + API key authenticate (PostgREST)
  can only read/write rows in tables that already exist — it has no DDL
  support, so `SUPABASE_URL`/`SUPABASE_API_KEY` alone can't create
  anything. `ensure_schema()` in `src/supabase_store.py` instead opens
  a `psycopg2` connection using `SUPABASE_DB_URL` (the project's session
  pooler connection string) and runs `SCHEMA_SQL` directly — a Postgres
  translation of `src.db.SCHEMA`, all `CREATE TABLE IF NOT EXISTS`, so
  safe to run on every clone. It then runs `ALTER TABLE ... DISABLE ROW
  LEVEL SECURITY` on each table, since PostgREST enforces RLS and a
  freshly created table has none defined — with no policy, that means
  every request gets rejected, including the app's own. **This is
  acceptable for a single-tenant demo where the service-role key is the
  only caller, but must be revisited (real RLS policies, or keeping all
  access on the service role and never exposing the anon key) before
  this holds real multi-user data.**
- **Local SQLite stays the default and the fallback** — nothing about
  it changed; Supabase mode is purely additive and opt-in per the
  dropdown.

## What's Next

Planned directions for evolving this proof of concept:

- **Response Ratings has no caller** — the floating "Ask Discovr" widget
  (`templates/widget.html`, `static/widget.css`/`widget.js`,
  `POST /widget-chat`, `src/agents.ask_website_chatbot`) was removed in
  favor of the main composer being the only chat input; it was the only
  thing that ever posted to `POST /rate`. Either wire ratings into the
  main chat's follow-up responses, or remove `src/ratings.py`/`/results`
  if they're not worth keeping around unused.
- **Supabase RLS is disabled, not policy-scoped** — see [Data
  Source](#data-source-local-sqlite-or-supabase). Fine while the
  service-role key is the only caller; needs real per-table RLS
  policies before Supabase mode could sit behind anything else (a
  browser client using the anon key, for instance).
- **Google Places connector** — `check_nap_consistency` in
  `src/checkers.py` is fully written but returns `score: None` until
  this exists; adding it activates the check with no changes to the
  scoring logic itself.
- **Unblock Mentions** — `src/components/find_mentions.py` and
  `check_mentions`'s tiered scoring are complete and correct, but
  Reddit blocks `/search.json` for any non-browser client at the
  network level (confirmed: real UA and headers don't help). Needs
  either a proxy/residential egress, Reddit's official API (requires
  registering an app), or a different mentions source entirely — any
  of which just needs to populate `snapshot["mentions"]` the same way,
  no changes to the scoring itself. Once real, more sources (review
  sites, news, forums) can merge into the same shape.
- **Real authentication credential** — replace email-only login with a
  password, magic link, or OAuth, since the current `users` table and
  `src/auth.py` intentionally have no credential to verify (see
  [Authentication](#authentication)).
- **Mentions in the agent loop** — `src/agent/graph.py`'s SUGGEST node
  only ever picks findings in categories `fix_generator` can act on;
  once `mentions` has a real fix path (see the Google/Brave connector
  item above), it can join the loop with no change to SUGGEST/PLAN's
  routing logic, just an addition to `FIXABLE_CATEGORIES`.
- **Apply fixes automatically** — the agent loop and fix generator
  produce real fixes but never write them back to the business's site;
  that would need a way to actually publish (a CMS API, a PR against
  the site's repo, etc.) that doesn't exist yet.
- **Weekly Re-Check workflow** — listed on `/workflows` but not
  implemented: needs a cron scheduler, storing/diffing against the
  previous analysis (the `analyses` table already keeps history, so
  this is mostly a comparison + alerting layer, not new scraping or
  scoring logic), and an actual alert channel (email, in-app) for when
  the score moves.
