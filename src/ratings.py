"""Thumbs up/down ratings for chatbot responses, persisted to a JSON file.

Kept separate from routes (app.py) so file I/O and stats math live in one
place. A simple lock serializes writes since data/results.json is a
single shared file, not a database with its own transaction support.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from src.db import new_id

RESULTS_PATH = Path(__file__).resolve().parent.parent / "data" / "results.json"

_lock = threading.Lock()


def _read_all():
    if not RESULTS_PATH.exists():
        return []
    return json.loads(RESULTS_PATH.read_text())


def _write_all(ratings):
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(ratings, indent=2))


def save_rating(question, answer, rating, model, response_time_seconds, input_tokens, output_tokens):
    entry = {
        "id": new_id(),
        "question": question,
        "answer": answer,
        "rating": rating,
        "model": model,
        "response_time_seconds": response_time_seconds,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with _lock:
        ratings = _read_all()
        ratings.append(entry)
        _write_all(ratings)

    return entry


def get_ratings():
    with _lock:
        ratings = _read_all()
    return sorted(ratings, key=lambda r: r["timestamp"], reverse=True)


def get_rating_stats():
    ratings = get_ratings()
    up = sum(1 for r in ratings if r["rating"] == "up")
    down = sum(1 for r in ratings if r["rating"] == "down")
    total = up + down
    positive_percent = round((up / total) * 100, 1) if total else 0

    return {"up": up, "down": down, "total": total, "positive_percent": positive_percent}
