"""SQLite persistence for Discovr.

Kept separate from routes: app.py only calls the functions below and
never touches sqlite3 directly. Tables are created automatically on
startup via `init_db()`.

All SQL here is standard enough to move to PostgreSQL later by swapping
`get_connection()` for a driver like psycopg2 and adjusting the
placeholder style (`?` -> `%s`) — callers outside this module would not
need to change.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"
DB_PATH = Path(os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    website TEXT NOT NULL,
    overall_score INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
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


def create_user(name, email, password_hash):
    with transaction() as connection:
        connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        row = connection.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        return row["id"]


def get_user_by_email(email):
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()


def record_progress(user_id, website, overall_score):
    with transaction() as connection:
        connection.execute(
            "INSERT INTO progress (user_id, website, overall_score) VALUES (?, ?, ?)",
            (user_id, website, overall_score),
        )


def get_user_progress(user_id):
    with transaction() as connection:
        rows = connection.execute(
            "SELECT website, overall_score, created_at FROM progress "
            "WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
