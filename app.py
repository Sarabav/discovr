"""Discovr proof-of-concept entry point."""

import os

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from src.analysis import run_analysis
from src.auth import login as authenticate, login_required, signup as signup_user
from src.chatbot import get_response
from src.db import get_user_progress, init_db, record_progress

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
init_db()


@app.route("/signup", methods=["GET", "POST"])
def signup_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user_id, error = signup_user(name, email, password)
        if error:
            return render_template("signup.html", error=error, name=name, email=email)

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
        session["user_name"] = user["name"]
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/")
@login_required
def index():
    history = get_user_progress(session["user_id"])
    return render_template("index.html", user_name=session["user_name"], history=history)


@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    data = request.get_json(silent=True) or {}
    report = run_analysis(
        website_url=data.get("website", "").strip(),
        facebook_handle=data.get("facebook", "").strip(),
        instagram_handle=data.get("instagram", "").strip(),
    )

    record_progress(session["user_id"], report["input"]["website"], report["overall_score"])
    report["history"] = get_user_progress(session["user_id"])

    return jsonify(report)


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()
    report = data.get("report")
    answer = get_response(question, report)
    return jsonify({"answer": answer})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8014))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(port=port, debug=debug)
