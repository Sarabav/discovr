"""Supabase-backed persistence, mirroring src/db.py's public API so
src/store.py can dispatch to either backend transparently. Tables must
exist in Supabase first -- see ensure_schema(), which creates them via
a direct Postgres connection (the REST API these keys otherwise talk
through has no DDL support), and clone_local_to_supabase(), which then
copies every row across from the local SQLite database.
"""

import json
import os

from src.db import new_id
from src.supabase_client import get_client

# Dependency order (matches src.db.SCHEMA) -- every foreign key points
# to a table earlier in this tuple, so cloning in this order never hits
# a missing-reference error.
TABLES = (
    "users",
    "businesses",
    "business_snapshots",
    "analyses",
    "findings",
    "fixes",
    "recommendations",
    "agent_runs",
)

# Postgres translation of src.db.SCHEMA: same tables, columns, and CHECK
# constraints, TEXT ids kept as-is, datetime('now') -> now().
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT,
  is_admin INTEGER NOT NULL DEFAULT 0,
  paid INTEGER NOT NULL DEFAULT 0,
  stripe_payment_intent_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS businesses (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  website_url TEXT,
  facebook_url TEXT,
  instagram_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS business_snapshots (
  id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(id),
  website_text TEXT,
  website_schema_json TEXT,
  facebook_data TEXT,
  instagram_data TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fixes (
  id TEXT PRIMARY KEY,
  finding_id TEXT NOT NULL REFERENCES findings(id),
  fix_type TEXT NOT NULL CHECK (fix_type IN ('generated','instruction')),
  content TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  run_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendations (
  id TEXT PRIMARY KEY,
  finding_id TEXT NOT NULL REFERENCES findings(id),
  priority TEXT NOT NULL CHECK (priority IN ('High','Medium','Low')),
  why TEXT NOT NULL,
  how TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started','fix_generated','applied')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _table(name):
    return get_client().table(name)


def _one(result):
    return result.data[0] if result.data else None


# ---------- users ----------


def create_user(email, password_hash):
    user_id = new_id()
    _table("users").insert(
        {"id": user_id, "email": email, "password_hash": password_hash, "is_admin": 0}
    ).execute()
    return user_id


def get_user_by_email(email):
    return _one(_table("users").select("*").eq("email", email).execute())


def get_user_by_id(user_id):
    return _one(_table("users").select("*").eq("id", user_id).execute())


def get_all_users():
    result = _table("users").select("*").order("created_at").execute()
    return result.data


def set_admin(email, is_admin=True):
    _table("users").update({"is_admin": int(bool(is_admin))}).eq("email", email).execute()


def set_password(email, password_hash):
    _table("users").update({"password_hash": password_hash}).eq("email", email).execute()


def update_user_email(user_id, email):
    _table("users").update({"email": email}).eq("id", user_id).execute()


def set_paid(user_id, paid, payment_intent_id=None):
    update = {"paid": int(bool(paid))}
    if payment_intent_id is not None:
        update["stripe_payment_intent_id"] = payment_intent_id
    _table("users").update(update).eq("id", user_id).execute()


# ---------- businesses ----------


def get_business(business_id):
    return _one(_table("businesses").select("*").eq("id", business_id).execute())


def get_business_for_user(user_id):
    result = (
        _table("businesses").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
    )
    return _one(result)


def update_business_website(business_id, website_url):
    _table("businesses").update({"website_url": website_url}).eq("id", business_id).execute()


def create_business(user_id, name, website_url):
    business_id = new_id()
    _table("businesses").insert(
        {"id": business_id, "user_id": user_id, "name": name, "website_url": website_url}
    ).execute()
    return business_id


# ---------- business_snapshots ----------


def create_snapshot(business_id, website_text, website_schema_json):
    snapshot_id = new_id()
    _table("business_snapshots").insert(
        {
            "id": snapshot_id,
            "business_id": business_id,
            "website_text": website_text,
            "website_schema_json": website_schema_json,
        }
    ).execute()
    return snapshot_id


def get_snapshot(snapshot_id):
    return _one(_table("business_snapshots").select("*").eq("id", snapshot_id).execute())


# ---------- analyses ----------


def create_analysis(business_id, snapshot_id, overall_score, category_scores, skipped=None):
    analysis_id = new_id()
    _table("analyses").insert(
        {
            "id": analysis_id,
            "business_id": business_id,
            "snapshot_id": snapshot_id,
            "overall_score": overall_score,
            "nap_consistency_score": category_scores.get("nap_consistency"),
            "structured_data_score": category_scores.get("structured_data"),
            "content_clarity_score": category_scores.get("content_clarity"),
            "crawler_access_score": category_scores.get("crawler_access"),
            "mentions_score": category_scores.get("mentions"),
            "skipped_json": json.dumps(skipped or {}),
        }
    ).execute()
    return analysis_id


def get_analysis(analysis_id):
    return _one(_table("analyses").select("*").eq("id", analysis_id).execute())


def get_latest_analysis(business_id):
    result = (
        _table("analyses").select("*").eq("business_id", business_id).order("created_at", desc=True).limit(1).execute()
    )
    return _one(result)


def get_analyses_for_business(business_id):
    result = _table("analyses").select("*").eq("business_id", business_id).order("created_at").execute()
    return result.data


# ---------- findings ----------


def create_finding(analysis_id, finding):
    finding_id = new_id()
    _table("findings").insert(
        {
            "id": finding_id,
            "analysis_id": analysis_id,
            "category": finding["category"],
            "title": finding["title"],
            "description": finding["description"],
            "priority": finding["priority"],
            "fix_type": finding["fix_type"],
            "why_it_matters": finding.get("why_it_matters"),
            "worst_passage": finding.get("worst_passage"),
            "missing_json": json.dumps(finding["missing"]) if finding.get("missing") else None,
        }
    ).execute()
    return finding_id


def update_finding_status(finding_id, status):
    _table("findings").update({"status": status}).eq("id", finding_id).execute()


def get_finding(finding_id):
    """The finding row plus the business_id it belongs to (joined
    through analyses), same shape as src.db.get_finding -- PostgREST
    has no cross-table join here, so it's two lookups instead of one."""
    finding = _one(_table("findings").select("*").eq("id", finding_id).execute())
    if finding is None:
        return None
    analysis = get_analysis(finding["analysis_id"])
    return {**finding, "business_id": analysis["business_id"] if analysis else None}


def get_findings(analysis_id):
    result = _table("findings").select("*").eq("analysis_id", analysis_id).order("created_at").execute()
    return result.data


# ---------- fixes ----------


def create_fix(finding_id, fix_type, content, verified, attempts, run_id=None):
    fix_id = new_id()
    _table("fixes").insert(
        {
            "id": fix_id,
            "finding_id": finding_id,
            "fix_type": fix_type,
            "content": content,
            "verified": int(bool(verified)),
            "attempts": attempts,
            "run_id": run_id,
        }
    ).execute()
    return fix_id


def get_fixes_for_run(run_id):
    result = _table("fixes").select("*").eq("run_id", run_id).order("created_at").execute()
    return result.data


# ---------- agent_runs ----------


def create_agent_run(
    run_id, business_id, stage, status, message=None, analysis_id=None, step_number=None, input_summary=None
):
    row_id = new_id()
    _table("agent_runs").insert(
        {
            "id": row_id,
            "run_id": run_id,
            "business_id": business_id,
            "stage": stage,
            "status": status,
            "message": message,
            "analysis_id": analysis_id,
            "step_number": step_number,
            "input_summary": input_summary,
        }
    ).execute()
    return row_id


def get_agent_runs(run_id):
    result = _table("agent_runs").select("*").eq("run_id", run_id).order("created_at").execute()
    return result.data


# ---------- clone from local SQLite ----------


def ensure_schema():
    """Creates every table via a direct Postgres connection
    (SUPABASE_DB_URL) and disables row-level security on each -- the
    REST API's keys (SUPABASE_URL/SUPABASE_API_KEY) can only read/write
    existing tables, never run DDL, so PostgREST alone can't do this.

    SCHEMA_SQL is all CREATE TABLE IF NOT EXISTS, so this is safe to
    call on every clone, not just the first.

    RLS is disabled outright rather than given policies: this is a
    single-tenant demo where the app's own service-role key is the only
    caller, so there's no other principal to write a policy for yet.
    Revisit before this ever holds real multi-user data -- add real RLS
    policies (or route all access through the service role only, never
    the anon key, which is already the case) rather than leaving tables
    wide open.
    """
    import psycopg2

    db_url = os.environ["SUPABASE_DB_URL"]
    connection = psycopg2.connect(db_url, connect_timeout=10)
    try:
        with connection.cursor() as cursor:
            cursor.execute(SCHEMA_SQL)
            # CREATE TABLE IF NOT EXISTS is a no-op against a table that
            # already existed before a column was added to SCHEMA_SQL
            # (e.g. password_hash) -- add it here too, the same gap
            # src.db.init_db() handles for SQLite.
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS paid INTEGER NOT NULL DEFAULT 0")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_payment_intent_id TEXT")
            for table in TABLES:
                cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        connection.commit()
    finally:
        connection.close()


def clone_local_to_supabase():
    """Creates every table (ensure_schema) then copies each row from the
    local SQLite database into Supabase, table by table in FK order.
    Uses upsert with ignore_duplicates on the primary key, so re-running
    never duplicates a row already copied over -- only the rows
    PostgREST actually inserts come back in the response, so that count
    is the real "copied" number, not the batch size.

    Every insert's response is checked: a table whose schema creation or
    row copy fails gets a real error message in the summary, not a
    silent "0 copied" that looks like success.

    Returns {"tables": {name: {"total", "copied", "skipped"} or
    {"error"}}, "schema_error": str | None}.
    """
    from src.db import get_connection

    schema_error = None
    try:
        ensure_schema()
    except Exception as error:
        schema_error = f"{type(error).__name__}: {error}"

    connection = get_connection()
    summary = {}
    try:
        for table in TABLES:
            if schema_error:
                summary[table] = {"error": f"Schema setup failed: {schema_error}"}
                continue

            try:
                rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table}").fetchall()]
                if not rows:
                    summary[table] = {"total": 0, "copied": 0, "skipped": 0}
                    continue

                copied = 0
                batch_size = 500
                for start in range(0, len(rows), batch_size):
                    batch = rows[start : start + batch_size]
                    result = _table(table).upsert(batch, on_conflict="id", ignore_duplicates=True).execute()
                    copied += len(result.data)

                summary[table] = {"total": len(rows), "copied": copied, "skipped": len(rows) - copied}
            except Exception as error:
                summary[table] = {"error": f"{type(error).__name__}: {error}"}
    finally:
        connection.close()

    return {"tables": summary, "schema_error": schema_error}
