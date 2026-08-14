"""Authentication logic: signup/login validation, hashing, and session guard.

Kept separate from routes (app.py) and from raw SQL (src/db.py) so each
layer has one job. Passwords are never stored or logged in plain text —
only their Werkzeug hash is persisted.
"""

from functools import wraps

from flask import redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from src.db import create_user, get_user_by_email


def signup(name, email, password):
    """Create a new user account. Returns (user_id, error)."""
    if not name or not email or not password:
        return None, "Name, email, and password are all required."

    if get_user_by_email(email) is not None:
        return None, "An account with that email already exists."

    password_hash = generate_password_hash(password)
    user_id = create_user(name, email, password_hash)
    return user_id, None


def login(email, password):
    """Verify credentials. Returns (user, error)."""
    if not email or not password:
        return None, "Email and password are required."

    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return None, "Invalid email or password."

    return user, None


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)

    return wrapped_view
