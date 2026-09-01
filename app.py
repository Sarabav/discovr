"""Discovr proof-of-concept entry point."""

import json
import os
import sys
import threading
import time
import traceback

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

from src.agent.graph import BLOCKERS_MARKER, PROJECTION_MARKER, run_agent_loop
from src.agents import load_knowledge_base, load_prompt, save_knowledge_base, save_prompt
from src.auth import (
    admin_required,
    is_valid_email,
    login as authenticate,
    login_required,
    signup as signup_user,
)
from src.chatbot import (
    ChatIntentError,
    answer_question,
    classify_intent,
    describe_progress,
    resolve_finding_ref,
)
from src.billing import BillingError, confirm_checkout_session, create_checkout_session, refund_payment
from src.checkers import summarize_schema
from src.components.find_mentions import city_from_address, find_mentions
from src.components.fix_generator import generate_verified_fix
from src.components.scrape_website import check_crawler_access, scrape_website
from src.data_source import get_data_source, set_data_source
from src.db import init_db, new_id
from src.store import (
    create_business,
    create_snapshot,
    get_agent_runs,
    get_all_users,
    get_analyses_for_business,
    get_analysis,
    get_business,
    get_business_for_user,
    get_finding,
    get_findings,
    get_fixes_for_run,
    get_latest_analysis,
    get_user_by_email,
    get_user_by_id,
    set_paid,
    update_business_website,
    update_user_email,
)
from src.supabase_store import clone_local_to_supabase, ensure_schema
from src.rag import (
    DEFAULT_CHUNK_SIZE,
    get_indexed_chunks,
    get_status,
    start_background_build,
)
from src.ratings import get_ratings, get_rating_stats, save_rating
from src.scoring import rank_findings, run_all_checks, save_analysis
from src.workflows.full_audit import run_audit

CATEGORY_NAMES = (
    "nap_consistency",
    "structured_data",
    "content_clarity",
    "crawler_access",
    "mentions",
)

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
# Secure (HTTPS-only) cookies in production, off locally so plain HTTP
# dev keeps working -- same FLASK_DEBUG signal already used below to
# tell local dev from a real deploy.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_DEBUG", "true").lower() != "true",
)
init_db()

# If the (locally-persisted, gitignored) Data Source setting says
# Supabase, make sure those tables actually exist before serving --
# otherwise every query after login would fail. Falls back to local
# SQLite (always ready, via init_db() above) and logs why, rather than
# serving requests against a backend that was never actually set up.
if get_data_source() == "supabase":
    try:
        ensure_schema()
    except Exception as error:
        print(f"Supabase not ready at startup ({error}); falling back to local SQLite.", file=sys.stderr)
        set_data_source("local")


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Last-resort net: any exception a route didn't already catch (a
    bad config value, a library raising something unexpected, etc.)
    lands here instead of the bare default 500 page, so a real user
    always sees something plain and actionable while the real
    traceback still goes to the logs for whoever's watching them."""
    if isinstance(error, HTTPException):
        return error
    traceback.print_exc(file=sys.stderr)
    return render_template("error.html"), 500


# The knowledge-base RAG index is no longer built eagerly here at import
# time -- src.rag.retrieve() builds it synchronously on its own first
# call instead (see src.rag._ensure_ready), so gunicorn boot stays cheap
# (no chromadb/sentence-transformers/torch loaded) instead of spiking
# memory before the process has served a single request.


@app.route("/")
def landing_page():
    if session.get("user_id"):
        return redirect(url_for("dashboard_page"))
    return render_template("landing.html")


@app.route("/signup", methods=["GET", "POST"])
def signup_page():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user, error = signup_user(email, password)
        if error:
            return render_template("signup.html", error=error, email=email)

        flash("Account created! Please log in.")
        return redirect(url_for("login_page"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user, error = authenticate(email, password)
        if error:
            return render_template("login.html", error=error, email=email)

        session["user_id"] = user["id"]
        session["user_name"] = user["email"].split("@")[0]
        session["is_admin"] = bool(user["is_admin"])
        return redirect(url_for("dashboard_page"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/dashboard")
@login_required
def dashboard_page():
    user = get_user_by_id(session["user_id"])
    return render_template("dashboard.html", user_name=session["user_name"], paid=bool(user["paid"]))


@app.route("/checkout")
@login_required
def start_checkout():
    user = get_user_by_id(session["user_id"])
    if user["paid"]:
        return redirect(url_for("dashboard_page"))

    # Belt-and-braces: signup already rejects a malformed email, but an
    # account could predate that check (or have been provisioned
    # directly) -- catching it here means Stripe never sees a bad value
    # in the first place, rather than us finding out from its error.
    if not is_valid_email(user["email"]):
        return redirect(url_for("update_email_page"))

    try:
        checkout_url = create_checkout_session(
            user_id=user["id"],
            user_email=user["email"],
            success_url=url_for("checkout_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("dashboard_page", _external=True),
        )
    except BillingError as error:
        return render_template("error.html", message=str(error)), 502
    return redirect(checkout_url)


@app.route("/account/email", methods=["GET", "POST"])
@login_required
def update_email_page():
    user = get_user_by_id(session["user_id"])

    if request.method == "POST":
        new_email = request.form.get("email", "").strip().lower()
        if not is_valid_email(new_email):
            return render_template("update_email.html", current_email=user["email"], error="Enter a valid email address.")
        existing = get_user_by_email(new_email)
        if existing is not None and existing["id"] != user["id"]:
            return render_template("update_email.html", current_email=user["email"], error="That email is already in use.")

        update_user_email(user["id"], new_email)
        flash("Email updated.")
        return redirect(url_for("start_checkout"))

    return render_template("update_email.html", current_email=user["email"])


@app.route("/checkout/success")
@login_required
def checkout_success():
    session_id = request.args.get("session_id")
    try:
        payment_intent_id = confirm_checkout_session(session_id, session["user_id"]) if session_id else None
    except BillingError as error:
        return render_template("error.html", message=str(error)), 502

    if payment_intent_id:
        set_paid(session["user_id"], True, payment_intent_id)
        flash("Payment successful — welcome to Discovr!")
    else:
        flash("We couldn't confirm that payment. Please try again.")
    return redirect(url_for("dashboard_page"))


def _refund_user(user):
    """Shared by the self-serve and admin refund routes: refund
    user's payment through Stripe, then mark them unpaid so the
    paywall re-applies. Returns (ok, message)."""
    if not user["paid"] or not user["stripe_payment_intent_id"]:
        return False, "This user has no payment to refund."
    try:
        refund_payment(user["stripe_payment_intent_id"])
    except BillingError as error:
        return False, str(error)
    set_paid(user["id"], False)
    return True, "Refund issued."


@app.route("/billing/refund", methods=["POST"])
@login_required
def refund_own_payment():
    user = get_user_by_id(session["user_id"])
    ok, message = _refund_user(user)
    return jsonify({"ok": ok, "message": message}), (200 if ok else 400)


@app.route("/admin/users/<user_id>/refund", methods=["POST"])
@admin_required
def refund_user_payment(user_id):
    user = get_user_by_id(user_id)
    if user is None:
        return jsonify({"ok": False, "message": "User not found."}), 404
    ok, message = _refund_user(user)
    return jsonify({"ok": ok, "message": message}), (200 if ok else 400)


def _start_audit(business_id):
    run_id = new_id()
    thread = threading.Thread(target=_run_audit_safely, args=(business_id, run_id), daemon=True)
    thread.start()
    return {"type": "run_started", "run_id": run_id}


def _run_audit_safely(business_id, run_id):
    try:
        run_audit(business_id, run_id)
    except Exception as error:
        print(f"run_audit({business_id}, {run_id}) failed: {error}", file=sys.stderr)


def _start_agent_loop(business_id):
    run_id = new_id()
    thread = threading.Thread(target=_run_agent_loop_safely, args=(business_id, run_id), daemon=True)
    thread.start()
    return {"type": "fix_run_started", "run_id": run_id}


def _run_agent_loop_safely(business_id, run_id):
    try:
        run_agent_loop(business_id, run_id)
    except Exception as error:
        print(f"run_agent_loop({business_id}, {run_id}) failed: {error}", file=sys.stderr)


def _taster_finding_id(analysis_id):
    """The one finding a free user can generate a fix for without
    paying -- the highest-priority (first-ranked, see rank_findings)
    still-open finding, so they see the quality of what they'd be
    paying for. None if there are no open findings."""
    open_findings = [f for f in get_findings(analysis_id) if f["status"] == "open"]
    return open_findings[0]["id"] if open_findings else None


def _upgrade_response(message):
    # 200, not 402/403: this is an expected, clean UI state for a free
    # user, not an error -- the frontend renders it as an upgrade
    # prompt (with a link to /checkout) rather than an error banner.
    return jsonify({"type": "upgrade", "answer": message})


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "question is required."}), 400

    user_id = session["user_id"]

    # A previous turn asked for the website URL; this message is the answer.
    if session.get("awaiting_website_for"):
        business_id = session.pop("awaiting_website_for")
        update_business_website(business_id, question)
        return jsonify(_start_audit(business_id))

    business = get_business_for_user(user_id)
    analysis = get_latest_analysis(business["id"]) if business else None

    try:
        classification = classify_intent(question, analysis is not None)
    except ChatIntentError as error:
        return jsonify({"error": str(error)}), 502

    intent = classification["intent"]

    if intent == "run_audit":
        if business and business["website_url"]:
            # The diagnosis itself is free, but only once per business --
            # an analysis already existing means this is a re-run, not
            # the free first audit.
            if analysis is not None and not get_user_by_id(user_id)["paid"]:
                return _upgrade_response(
                    "Your first audit is free — re-running one is a paid feature. Upgrade to run it again."
                )
            return jsonify(_start_audit(business["id"]))
        business_id = business["id"] if business else create_business(user_id, session["user_name"], None)
        session["awaiting_website_for"] = business_id
        return jsonify(
            {
                "type": "ask",
                "answer": "What's your business's website URL? I'll run the audit as soon as I have it.",
            }
        )

    if intent == "fix_all":
        if business is None or not business["website_url"] or analysis is None:
            return jsonify(
                {"type": "answer", "answer": "Run an AI-visibility audit first, then I can work through the findings."}
            )
        if not get_user_by_id(user_id)["paid"]:
            return _upgrade_response("Fixing everything automatically is a paid feature. Upgrade to let the agent work through your findings.")
        return jsonify(_start_agent_loop(business["id"]))

    if intent == "generate_fix":
        if analysis is None:
            return jsonify({"type": "answer", "answer": "Run an AI-visibility audit first, then I can generate a fix."})

        open_findings = [dict(f) for f in get_findings(analysis["id"]) if f["status"] == "open"]
        for f in open_findings:
            f["missing"] = json.loads(f.get("missing_json") or "[]")
        finding = resolve_finding_ref(classification.get("finding_ref"), open_findings)

        if finding is None:
            if not open_findings:
                return jsonify({"type": "answer", "answer": "No open findings right now — nothing to fix."})
            titles = ", ".join(f["title"] for f in open_findings)
            return jsonify({"type": "answer", "answer": f"Which finding do you mean? Open ones: {titles}."})

        if not get_user_by_id(user_id)["paid"] and finding["id"] != _taster_finding_id(analysis["id"]):
            return _upgrade_response("Upgrade to generate this fix.")

        try:
            result = generate_verified_fix(finding, business["id"])
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(
            {
                "type": "fix",
                "finding": {"id": finding["id"], "category": finding["category"], "title": finding["title"]},
                "fix": result,
            }
        )

    if intent == "check_progress":
        if business is None:
            return jsonify(
                {"type": "answer", "answer": "Run an AI-visibility audit first, then I can show you your progress."}
            )
        if not get_user_by_id(user_id)["paid"]:
            return _upgrade_response("Tracking your score over time is a paid feature. Upgrade to see your progress.")
        return jsonify({"type": "answer", "answer": describe_progress(get_analyses_for_business(business["id"]))})

    # question
    open_findings = [dict(f) for f in get_findings(analysis["id"]) if f["status"] == "open"] if analysis else None
    return jsonify({"type": "answer", "answer": answer_question(question, business, analysis, open_findings)})


@app.route("/runs/<run_id>")
@login_required
def run_status(run_id):
    steps = [dict(row) for row in get_agent_runs(run_id)]
    if not steps:
        return jsonify({"error": "Run not found."}), 404

    error = next((step["message"] for step in steps if step["status"] == "error"), None)
    last = steps[-1]

    if error:
        status = "error"
    elif last["stage"] == "saving" and last["status"] == "done":
        status = "done"
    else:
        status = "running"

    result = None
    if status == "done":
        analysis_id = last["analysis_id"]
        analysis = get_analysis(analysis_id)
        business = get_business(analysis["business_id"])
        paid = bool(get_user_by_id(session["user_id"])["paid"])
        taster_id = _taster_finding_id(analysis_id)
        findings = [dict(finding) for finding in get_findings(analysis_id)]
        for finding in findings:
            # The real gate is server-side on the actual generate-fix
            # routes (this is display only) -- a free user can generate
            # exactly one fix (the taster, highest-priority open
            # finding) for free; everything else needs an upgrade.
            finding["locked"] = not paid and finding["status"] == "open" and finding["id"] != taster_id
        result = {
            "analysis_id": analysis_id,
            "business_name": business["name"],
            "overall_score": analysis["overall_score"],
            "categories": {name: analysis[f"{name}_score"] for name in CATEGORY_NAMES},
            "skipped": json.loads(analysis["skipped_json"] or "{}"),
            "findings": findings,
            "paid": paid,
        }

    return jsonify({"run_id": run_id, "status": status, "steps": steps, "error": error, "result": result})


def _latest_fixes_by_finding(fix_rows):
    """fix_rows is ordered by insertion (rowid ASC); keep only each
    finding's last attempt so a retried finding shows one card, not one
    per failed attempt."""
    latest = {}
    for row in fix_rows:
        finding_id = row["finding_id"]
        if finding_id not in latest or row["attempts"] >= latest[finding_id]["attempts"]:
            latest[finding_id] = row
    return list(latest.values())


def _needs_from_owner_from_content(fix_type, content):
    """The fixes table only stores the fix's plain content, not the full
    fix dict — recover needs_from_owner from the unmistakable "FILL IN"
    markers themselves (see src.components.fix_generator) rather than
    persisting a parallel field."""
    if fix_type != "generated":
        return []
    try:
        schema = json.loads(content)
    except (ValueError, TypeError):
        return []

    needs = []

    def _walk(value, key=None):
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                _walk(sub_value, sub_key)
        elif isinstance(value, str) and value.startswith("FILL IN") and key and key not in needs:
            needs.append(key)

    _walk(schema)
    return needs


def _verification_reason(steps, finding_title):
    """The human reason for a finding's final MONITOR outcome, recovered
    from the agent_runs message text — same "read it back out of the
    unmistakable log format" approach as _needs_from_owner_from_content,
    since there's no separate reason column. Only meaningful for
    "needs_human" (couldn't verify — check itself failed, e.g. a
    Content Clarity parse error) and "failed" (ran, fix fell short)."""
    monitor_steps = [
        s for s in steps
        if s["stage"] == "monitor" and (s["input_summary"] or "").startswith(f"finding '{finding_title}'")
    ]
    if not monitor_steps:
        return None
    message = monitor_steps[-1]["message"] or ""
    if message.startswith("couldn't verify — "):
        return message[len("couldn't verify — "):].rsplit(" — marking needs_human", 1)[0]
    if message.startswith("failed after max attempts — marking failed — "):
        return message[len("failed after max attempts — marking failed — "):]
    return None


@app.route("/agent-runs/<run_id>")
@login_required
def agent_run_status(run_id):
    steps = [dict(row) for row in get_agent_runs(run_id)]
    if not steps:
        return jsonify({"error": "Run not found."}), 404

    done_row = next((step for step in steps if step["stage"] == "done"), None)
    status = "done" if done_row else "running"

    fixes = []
    for fix_row in _latest_fixes_by_finding(get_fixes_for_run(run_id)):
        finding = get_finding(fix_row["finding_id"])
        if finding is None:
            continue
        fixes.append(
            {
                "finding_id": fix_row["finding_id"],
                "category": finding["category"],
                "title": finding["title"],
                "fix_type": fix_row["fix_type"],
                "content": fix_row["content"],
                "before": finding["worst_passage"] if fix_row["fix_type"] == "generated" and finding["category"] == "content_clarity" else None,
                # A finding's persisted status is the source of truth (fixes
                # rows are attempt logs written before the outcome is
                # known, not the row's own verified column) and, unlike a
                # plain verified bool, distinguishes "ran and fell short"
                # (failed) from "the check itself couldn't run" (needs_human)
                # so a broken parser doesn't read the same as a bad fix.
                "status": finding["status"],
                "reason": _verification_reason(steps, finding["title"]) if fix_row["fix_type"] == "generated" else None,
                "needs_from_owner": _needs_from_owner_from_content(fix_row["fix_type"], fix_row["content"]),
            }
        )

    summary = None
    if status == "done":
        business_id = steps[0]["business_id"]
        analysis = get_latest_analysis(business_id)
        counts = {"resolved": 0, "needs_human": 0, "failed": 0, "open": 0}
        if analysis:
            for finding in get_findings(analysis["id"]):
                counts[finding["status"]] = counts.get(finding["status"], 0) + 1
        projection_row = next(
            (s for s in reversed(steps) if s["stage"] == "monitor" and s["input_summary"] == PROJECTION_MARKER),
            None,
        )
        blockers_row = next(
            (s for s in reversed(steps) if s["stage"] == "monitor" and s["input_summary"] == BLOCKERS_MARKER),
            None,
        )
        summary = {
            "message": done_row["message"],
            "projection": projection_row["message"] if projection_row else None,
            "blockers": blockers_row["message"].split(" | ") if blockers_row else [],
            **counts,
        }

    return jsonify({"run_id": run_id, "status": status, "steps": steps, "fixes": fixes, "summary": summary})


@app.route("/findings/<finding_id>/fix", methods=["POST"])
@login_required
def generate_fix_route(finding_id):
    finding = get_finding(finding_id)
    if finding is None:
        return jsonify({"error": "Finding not found."}), 404

    user = get_user_by_id(session["user_id"])
    if not user["paid"] and finding["id"] != _taster_finding_id(finding["analysis_id"]):
        return _upgrade_response("Upgrade to generate this fix.")

    finding = dict(finding)
    finding["missing"] = json.loads(finding.get("missing_json") or "[]")
    try:
        result = generate_verified_fix(finding, finding["business_id"])
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    return jsonify(result)


@app.route("/rate", methods=["POST"])
@login_required
def rate():
    data = request.get_json(silent=True) or {}
    rating = data.get("rating")
    if rating not in ("up", "down"):
        return jsonify({"error": "rating must be 'up' or 'down'."}), 400

    question = data.get("question", "").strip()
    answer = data.get("answer", "").strip()
    if not question or not answer:
        return jsonify({"error": "question and answer are required."}), 400

    entry = save_rating(
        question=question,
        answer=answer,
        rating=rating,
        model=data.get("model", ""),
        response_time_seconds=data.get("response_time_seconds"),
        input_tokens=data.get("input_tokens"),
        output_tokens=data.get("output_tokens"),
    )
    return jsonify(entry)


@app.route("/admin")
@admin_required
def admin_page():
    return render_template(
        "admin.html",
        user_name=session["user_name"],
        data_source=get_data_source(),
        users=get_all_users(),
    )


@app.route("/admin/data-source", methods=["POST"])
@admin_required
def admin_set_data_source():
    data = request.get_json(silent=True) or {}
    source = data.get("source")
    try:
        set_data_source(source)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"data_source": source})


@app.route("/admin/clone-to-supabase", methods=["POST"])
@admin_required
def admin_clone_to_supabase():
    try:
        result = clone_local_to_supabase()
    except KeyError as error:
        return jsonify({"error": f"Missing Supabase config: {error}"}), 400
    except Exception as error:
        return jsonify({"error": str(error)}), 502
    return jsonify(result)


@app.route("/results")
@admin_required
def results_page():
    return render_template(
        "results.html",
        user_name=session["user_name"],
        ratings=get_ratings(),
        stats=get_rating_stats(),
    )


@app.route("/results/data")
@admin_required
def results_data():
    return jsonify({"ratings": get_ratings(), "stats": get_rating_stats()})


@app.route("/workflows")
@admin_required
def workflows_page():
    return render_template("workflows.html", user_name=session["user_name"])


@app.route("/workflows/audit/run", methods=["POST"])
@admin_required
def workflow_audit_run():
    business = get_business_for_user(session["user_id"])
    if business is None or not business["website_url"]:
        return jsonify({"error": "No business website on file yet — run an audit from the chat first."}), 400
    return jsonify(_start_audit(business["id"]))


@app.route("/workflows/fix/run", methods=["POST"])
@admin_required
def workflow_fix_run():
    business = get_business_for_user(session["user_id"])
    if business is None or not business["website_url"]:
        return jsonify({"error": "No business website on file yet — run an audit first."}), 400
    if get_latest_analysis(business["id"]) is None:
        return jsonify({"error": "This business has no analysis yet — run an audit first."}), 400
    return jsonify(_start_agent_loop(business["id"]))


@app.route("/components")
@admin_required
def components_page():
    return render_template("components.html", user_name=session["user_name"])


@app.route("/components/website")
@admin_required
def component_website_page():
    return render_template("component_website.html", user_name=session["user_name"])


@app.route("/components/website/run", methods=["POST"])
@admin_required
def component_website_run():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required."}), 400

    start = time.monotonic()
    scrape = scrape_website(url)
    crawler_access = check_crawler_access(url)
    schema_summary = summarize_schema(scrape.get("schema"))
    elapsed = round(time.monotonic() - start, 2)

    return jsonify(
        {
            "scrape": scrape,
            "crawler_access": crawler_access,
            "schema_summary": schema_summary,
            "elapsed_seconds": elapsed,
        }
    )


@app.route("/components/scoring")
@admin_required
def component_scoring_page():
    return render_template("component_scoring.html", user_name=session["user_name"])


@app.route("/components/scoring/run", methods=["POST"])
@admin_required
def component_scoring_run():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required."}), 400

    start = time.monotonic()

    scrape = scrape_website(url)
    robots = check_crawler_access(url)
    snapshot = {**scrape, "robots": robots}
    nap = snapshot.get("nap") or {}
    business_name = nap.get("name") or snapshot.get("title")
    snapshot["mentions"] = find_mentions(business_name, city_from_address(nap.get("address")))

    results = run_all_checks(snapshot)
    results["findings"] = rank_findings(results["findings"], snapshot)

    business_id = create_business(session["user_id"], scrape.get("title") or url, url)
    snapshot_id = create_snapshot(business_id, scrape.get("text", ""), json.dumps(scrape.get("schema", [])))
    analysis_id = save_analysis(business_id, snapshot_id, results)

    elapsed = round(time.monotonic() - start, 2)
    return jsonify(
        {
            **results,
            "analysis_id": analysis_id,
            "scrape_error": scrape.get("error"),
            "elapsed_seconds": elapsed,
        }
    )


@app.route("/rag/status")
@admin_required
def rag_status():
    return jsonify(get_status())


@app.route("/rag/rebuild", methods=["POST"])
@admin_required
def rag_rebuild():
    data = request.get_json(silent=True) or {}
    chunk_size = int(data.get("chunk_size") or DEFAULT_CHUNK_SIZE)
    start_background_build(chunk_size)
    return jsonify({"started": True})


@app.route("/chunks")
@admin_required
def chunks_page():
    return render_template(
        "chunks.html",
        user_name=session["user_name"],
        chunks=get_indexed_chunks(),
        status=get_status(),
        default_chunk_size=DEFAULT_CHUNK_SIZE,
    )


@app.route("/chunks/data")
@admin_required
def chunks_data():
    return jsonify({"chunks": get_indexed_chunks(), "status": get_status()})


@app.route("/settings")
@login_required
def settings_page():
    return render_template(
        "settings.html",
        user_name=session["user_name"],
        knowledge_base=load_knowledge_base(),
        prompt=load_prompt("website_chatbot.txt"),
    )


@app.route("/settings/knowledge-base", methods=["POST"])
@login_required
def save_knowledge_base_route():
    data = request.get_json(silent=True) or {}
    content = data.get("content", "")
    if not content.strip():
        return jsonify({"error": "Content cannot be empty."}), 400
    save_knowledge_base(content)
    return jsonify({"saved": True})


@app.route("/settings/prompt", methods=["POST"])
@login_required
def save_prompt_route():
    data = request.get_json(silent=True) or {}
    content = data.get("content", "")
    if not content.strip():
        return jsonify({"error": "Content cannot be empty."}), 400
    save_prompt("website_chatbot.txt", content)
    return jsonify({"saved": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8014))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(port=port, debug=debug, threaded=True)
