# Discovr

**See your business the way an AI assistant does.**

## What It Does

When someone asks ChatGPT, Google's AI Overview, or a voice assistant
"who's a good dentist near me," the answer comes from how *legible* that
business's website and social profiles are to AI systems — not just from
traditional SEO. Most small business owners have no way to check that.

Discovr is a proof-of-concept web app that lets a business owner enter
their website and social handles, run an "AI-visibility" analysis, and get
back a scored report broken down by category, with prioritized
recommendations and a chatbot to ask follow-up questions about the
results.

This POC does not scrape real websites yet — it runs the full flow
(signup → login → analyze → report → chat) against one hardcoded sample
business (a fictional local dental clinic) so the end-to-end experience
can be evaluated and demoed without external dependencies. See
[What's Next](#whats-next) for the plan to make it real.

## Screenshots

_(placeholder — add screenshots of the login page, dashboard, and report
view here)_

| Login | Dashboard | Report |
|---|---|---|
| _screenshot_ | _screenshot_ | _screenshot_ |

## Features Implemented So Far

- **Authentication** — sign up, log in, and log out with hashed passwords
  (Werkzeug `generate_password_hash`/`check_password_hash`) and
  Flask-session-backed login state. The dashboard, analysis, and chat
  routes all require login and only ever show the logged-in user's own
  data.
- **Analysis flow** — enter a website URL and Facebook/Instagram handles
  and run an analysis (currently backed by hardcoded sample data).
- **Scored report** — an overall AI-visibility score and grade, broken
  down into four categories: consistency, structured data, content
  clarity, and social presence, each with a score and specific findings.
- **Prioritized recommendations** — a High/Medium/Low list of concrete
  next steps.
- **Analysis history** — every run is saved to SQLite and shown on the
  dashboard, scoped to the logged-in user.
- **Chatbot panel** — ask follow-up questions about your report. Currently
  answered by a placeholder function with a stable interface, ready to be
  swapped for a real AI backend (see [AI Placeholder](#ai-placeholder)).

## Technologies Used

- **Python 3** / **Flask** — web framework and routing
- **SQLite** (`sqlite3`, standard library) — persistence for users and
  analysis history
- **Werkzeug** — password hashing (ships with Flask)
- **python-dotenv** — loads local config from `.env`
- **Vanilla HTML/CSS/JS** — no frontend framework or build step

## Project Structure

```
discovr/
├── app.py                 # Flask entry point and routes
├── data/
│   ├── sample_data.py     # Hardcoded business profile, findings, recommendations
│   └── app.db             # SQLite database (created automatically, gitignored)
├── src/
│   ├── analysis.py        # Builds the report from sample data (swap-in point for real analysis)
│   ├── scoring.py         # Overall score / grade calculation
│   ├── chatbot.py         # Placeholder chatbot response logic
│   ├── auth.py            # Signup/login validation, password hashing, login_required
│   └── db.py              # SQLite persistence for users and progress
├── templates/
│   ├── index.html         # Dashboard (requires login)
│   ├── login.html
│   └── signup.html
├── static/
│   ├── style.css
│   └── script.js
├── .env.example            # Template for local environment variables
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

4. **Set up environment variables**

   ```bash
   cp .env.example .env
   ```

   Then open `.env` and set `SECRET_KEY` to a real random value, e.g.:

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

5. **Run the app**

   ```bash
   python app.py
   ```

   The database tables are created automatically on first run. Visit
   [http://localhost:8014](http://localhost:8014), sign up for an
   account, and log in to reach the dashboard.

## Environment Variables

See `.env.example` for the full list with descriptions. Summary:

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs Flask session cookies | _none — must be set_ |
| `DATABASE_PATH` | Path to the SQLite database file | `data/app.db` |
| `PORT` | Local dev server port | `8014` |
| `FLASK_DEBUG` | Enables Flask debug mode | `true` |

`.env` is gitignored and never committed; `.env.example` documents the
required variables with placeholder values only.

## AI Placeholder

The chatbot currently returns a generic canned response for any question,
via `src/chatbot.get_response(question, report)`. This keeps the function
signature stable so it can later be swapped for a real LLM call (e.g.
sending the question plus the report as context to an AI API) without
changing any calling code in `app.py`.

Similarly, `src/analysis.run_analysis` is the single place where real
website/social-media scraping and scoring would replace the hardcoded
sample data, without requiring changes to routes or templates.

## Database

Discovr stores users and their analysis progress in a SQLite database
(path configurable via `DATABASE_PATH`), using Python's built-in
`sqlite3` module. All database access is isolated in `src/db.py` —
routes in `app.py` never run SQL directly.

- `init_db()` creates the `users` and `progress` tables (if they don't
  already exist) once, when the app starts.
- Each analysis run is recorded as a `progress` row (website analyzed and
  overall score) linked to the logged-in user's `user_id`.
- Writes go through `src.db.transaction()`, a context manager that wraps
  each write in a transaction (commit on success, rollback on error) and
  uses parameterized queries throughout to avoid SQL injection.
- The SQL is written in a driver-agnostic style so migrating to
  PostgreSQL later mainly means swapping `get_connection()` for a
  different driver — see [What's Next](#whats-next).

## What's Next

Planned directions for evolving this proof of concept:

- **Database migration to PostgreSQL** — replace the SQLite connection in
  `src/db.py` with a PostgreSQL driver (e.g. `psycopg`) behind the same
  function interface, and move the connection string into `DATABASE_URL`.
- **Agentic AI analysis** — replace the hardcoded sample data in
  `src/analysis.py` with an agent that actually fetches and evaluates a
  business's website and social profiles.
- **RAG-backed chatbot** — replace the placeholder in `src/chatbot.py`
  with a real LLM call that retrieves relevant context (the business's
  own report, findings, and recommendations) to ground its answers.
