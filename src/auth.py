"""Authentication logic: email + password signup/login and session guard.

Kept separate from routes (app.py) and from raw SQL (src/db.py) so each
layer has one job.
"""

import re
from functools import wraps

from flask import abort, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from src.store import create_user, get_user_by_email

MIN_PASSWORD_LENGTH = 8

# The WHATWG HTML5 email input pattern -- not full RFC 5322, but a real
# shape check (local@label.label, domain requires a dot) rather than
# "contains @". Rejects things like "mum@123" that a bare `"@" in email`
# check let through, which broke Stripe checkout downstream.
EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


def is_valid_email(email):
    return bool(email) and bool(EMAIL_RE.match(email))


def signup(email, password):
    """Create a new account for an email not seen before. Returns (user, error)."""
    if not email:
        return None, "Email is required."
    if not is_valid_email(email):
        return None, "Enter a valid email address."
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return None, f"Password must be at least {MIN_PASSWORD_LENGTH} characters."

    if get_user_by_email(email) is not None:
        return None, "An account with that email already exists. Log in instead."

    create_user(email, generate_password_hash(password))
    return get_user_by_email(email), None


def login(email, password):
    """Look up an existing account by email and verify the password.
    Returns (user, error). One generic error message for both a wrong
    email and a wrong password, so a failed login doesn't reveal which
    accounts exist."""
    generic_error = "Invalid email or password."
    if not email or not password:
        return None, generic_error

    user = get_user_by_email(email)
    # A NULL password_hash means the account predates password auth (or
    # was provisioned directly) and has no credential set -- treat it
    # the same as a wrong password rather than raising, and never as a
    # free pass.
    if user is None or not user["password_hash"] or not check_password_hash(user["password_hash"], password):
        return None, generic_error

    return user, None


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    """Like login_required, but also demands is_admin — real access control,
    not just a hidden nav link. Returns 403 rather than a redirect so a
    logged-in non-admin gets a clear denial, not a silent bounce."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login_page"))
        if not session.get("is_admin"):
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view
