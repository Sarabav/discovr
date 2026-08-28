"""SQLite persistence for Discovr.

Kept separate from routes: app.py only calls the functions below and
never touches sqlite3 directly. Tables are created automatically on
startup via `init_db()`.

All SQL here is standard enough to move to PostgreSQL later by swapping
`get_connection()` for a driver like psycopg2 and adjusting the
placeholder style (`?` -> `%s`) — callers outside this module would not
need to change.
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"
DB_PATH = Path(os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  is_admin INTEGER NOT NULL DEFAULT 0,
  paid INTEGER NOT NULL DEFAULT 0,
  stripe_payment_intent_id TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS businesses (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  website_url TEXT,
  facebook_url TEXT,
  instagram_url TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS business_snapshots (
  id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(id),
  website_text TEXT,
  website_schema_json TEXT,
  facebook_data TEXT,
  instagram_data TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analyses (
  id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(id),
  snapshot_id TEXT NOT NULL REFERENCES business_snapshots(id),
  overall_score INTEGER,
  nap_consistency_score INTEGER,
  structured_data_score INTEGER,
  content_clarity_score INTEGER,
  crawler_access_score INTEGER,
  mentions_score INTEGER,
  skipped_json TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY,
  analysis_id TEXT NOT NULL REFERENCES analyses(id),
  category TEXT NOT NULL CHECK (category IN ('nap_consistency','structured_data','content_clarity','crawler_access','mentions')),
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  priority TEXT NOT NULL CHECK (priority IN ('High','Medium','Low')),
  fix_type TEXT NOT NULL CHECK (fix_type IN ('generated','instruction')),
  why_it_matters TEXT,
  worst_passage TEXT,
  missing_json TEXT,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','needs_human','failed')),
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fixes (
  id TEXT PRIMARY KEY,
  finding_id TEXT NOT NULL REFERENCES findings(id),
  fix_type TEXT NOT NULL CHECK (fix_type IN ('generated','instruction')),
  content TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  run_id TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  business_id TEXT NOT NULL REFERENCES businesses(id),
  stage TEXT NOT NULL CHECK (stage IN (
    'scraping','ingesting','scoring','ranking','saving',
    'suggest','plan','execute','monitor','done'
  )),
  status TEXT NOT NULL CHECK (status IN ('running','done','error')),
  message TEXT,
  analysis_id TEXT,
  step_number INTEGER,
  input_summary TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recommendations (
  id TEXT PRIMARY KEY,
  finding_id TEXT NOT NULL REFERENCES findings(id),
  priority TEXT NOT NULL CHECK (priority IN ('High','Medium','Low')),
  why TEXT NOT NULL,
  how TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started','fix_generated','applied')),
  created_at TEXT DEFAULT (datetime('now'))
);
"""


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def transaction():
    """Yield a connection, committing on success and rolling back on error."""
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with transaction() as connection:
        connection.executescript(SCHEMA)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        if "is_admin" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        if "password_hash" not in columns:
            # No DEFAULT possible for a NOT NULL text column on an
            # ALTER TABLE with existing rows, so this is added nullable;
            # src.auth treats a NULL hash as "no password set, can't log
            # in" (fail clearly) rather than a bypass.
            connection.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        if "paid" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN paid INTEGER NOT NULL DEFAULT 0")
        if "stripe_payment_intent_id" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN stripe_payment_intent_id TEXT")


def new_id():
    return str(uuid.uuid4())


def create_user(email, password_hash):
    user_id = new_id()
    with transaction() as connection:
        connection.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)", (user_id, email, password_hash)
        )
    return user_id


def get_user_by_email(email):
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()


def get_user_by_id(user_id):
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def get_all_users():
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM users ORDER BY created_at ASC"
        ).fetchall()


def set_admin(email, is_admin=True):
    with transaction() as connection:
        connection.execute(
            "UPDATE users SET is_admin = ? WHERE email = ?", (int(bool(is_admin)), email)
        )


def set_paid(user_id, paid, payment_intent_id=None):
    """payment_intent_id is only overwritten when a value is passed (a
    fresh successful checkout); marking unpaid on refund keeps the old
    id around as a record of what was refunded."""
    with transaction() as connection:
        if payment_intent_id is not None:
            connection.execute(
                "UPDATE users SET paid = ?, stripe_payment_intent_id = ? WHERE id = ?",
                (int(bool(paid)), payment_intent_id, user_id),
            )
        else:
            connection.execute(
                "UPDATE users SET paid = ? WHERE id = ?", (int(bool(paid)), user_id)
            )


def set_password(email, password_hash):
    with transaction() as connection:
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE email = ?", (password_hash, email)
        )


def update_user_email(user_id, email):
    with transaction() as connection:
        connection.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))


def get_business(business_id):
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM businesses WHERE id = ?", (business_id,)
        ).fetchone()


def get_business_for_user(user_id):
    """Most recently created business for this user, or None."""
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM businesses WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()


def update_business_website(business_id, website_url):
    with transaction() as connection:
        connection.execute(
            "UPDATE businesses SET website_url = ? WHERE id = ?", (website_url, business_id)
        )


def create_business(user_id, name, website_url):
    business_id = new_id()
    with transaction() as connection:
        connection.execute(
            "INSERT INTO businesses (id, user_id, name, website_url) VALUES (?, ?, ?, ?)",
            (business_id, user_id, name, website_url),
        )
    return business_id


def create_snapshot(business_id, website_text, website_schema_json):
    snapshot_id = new_id()
    with transaction() as connection:
        connection.execute(
            "INSERT INTO business_snapshots (id, business_id, website_text, website_schema_json) "
            "VALUES (?, ?, ?, ?)",
            (snapshot_id, business_id, website_text, website_schema_json),
        )
    return snapshot_id


def create_analysis(business_id, snapshot_id, overall_score, category_scores, skipped=None):
    """category_scores: dict with keys nap_consistency, structured_data,
    content_clarity, crawler_access, mentions, each a score or None.
    skipped: dict of category -> the real reason it's None (e.g. "Google
    Places connector not connected" or "Content Clarity check failed:
    ..."), persisted so it survives past the request that computed it —
    without this, /runs/<run_id> can only ever show a generic message
    for every null category, connector-gated or not."""
    analysis_id = new_id()
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO analyses (
                id, business_id, snapshot_id, overall_score,
                nap_consistency_score, structured_data_score,
                content_clarity_score, crawler_access_score, mentions_score,
                skipped_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                business_id,
                snapshot_id,
                overall_score,
                category_scores.get("nap_consistency"),
                category_scores.get("structured_data"),
                category_scores.get("content_clarity"),
                category_scores.get("crawler_access"),
                category_scores.get("mentions"),
                json.dumps(skipped or {}),
            ),
        )
    return analysis_id


def create_finding(analysis_id, finding):
    finding_id = new_id()
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO findings (
                id, analysis_id, category, title, description, priority, fix_type,
                why_it_matters, worst_passage, missing_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                analysis_id,
                finding["category"],
                finding["title"],
                finding["description"],
                finding["priority"],
                finding["fix_type"],
                finding.get("why_it_matters"),
                finding.get("worst_passage"),
                json.dumps(finding["missing"]) if finding.get("missing") else None,
            ),
        )
    return finding_id


def update_finding_status(finding_id, status):
    with transaction() as connection:
        connection.execute(
            "UPDATE findings SET status = ? WHERE id = ?", (status, finding_id)
        )


def get_finding(finding_id):
    """The finding row plus the business_id it belongs to (joined through
    analyses), since fix generation needs both."""
    with transaction() as connection:
        return connection.execute(
            """
            SELECT findings.*, analyses.business_id AS business_id
            FROM findings
            JOIN analyses ON analyses.id = findings.analysis_id
            WHERE findings.id = ?
            """,
            (finding_id,),
        ).fetchone()


def get_analysis(analysis_id):
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()


def get_findings(analysis_id):
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM findings WHERE analysis_id = ? ORDER BY rowid ASC", (analysis_id,)
        ).fetchall()


def create_agent_run(
    run_id, business_id, stage, status, message=None, analysis_id=None,
    step_number=None, input_summary=None,
):
    """One row per stage/step transition, so GET /runs/<run_id> (audit
    workflow) and GET /agent-runs/<run_id> (agent loop) can show live
    progress by reading the full history rather than a single mutable
    row. step_number/input_summary are only used by the agent loop."""
    row_id = new_id()
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO agent_runs (
                id, run_id, business_id, stage, status, message, analysis_id,
                step_number, input_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (row_id, run_id, business_id, stage, status, message, analysis_id, step_number, input_summary),
        )
    return row_id


def get_agent_runs(run_id):
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM agent_runs WHERE run_id = ? ORDER BY rowid ASC", (run_id,)
        ).fetchall()


def create_fix(finding_id, fix_type, content, verified, attempts, run_id=None):
    fix_id = new_id()
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO fixes (id, finding_id, fix_type, content, verified, attempts, run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (fix_id, finding_id, fix_type, content, int(bool(verified)), attempts, run_id),
        )
    return fix_id


def get_fixes_for_run(run_id):
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM fixes WHERE run_id = ? ORDER BY rowid ASC", (run_id,)
        ).fetchall()


def get_latest_analysis(business_id):
    """Most recent analysis for a business, or None if it's never been
    audited. The agent loop works over this analysis's findings."""
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM analyses WHERE business_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (business_id,),
        ).fetchone()


def get_analyses_for_business(business_id):
    """Every analysis for a business, oldest first, for trend queries
    (see src.chatbot.describe_progress)."""
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM analyses WHERE business_id = ? ORDER BY created_at ASC, rowid ASC",
            (business_id,),
        ).fetchall()


def get_snapshot(snapshot_id):
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM business_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
