"""Content Clarity check: the one LLM-based scoring check.

The rubric is not hardcoded here: the "Content Clarity" section of the
playbook (data/knowledge_base.md), including its good/bad examples, is
retrieved from the existing RAG index (src/rag.retrieve) and dropped
into the prompt as the standard to grade against, so editing the
playbook changes what "good" means without touching this code.

Never raises: an API failure or unparseable response returns a skipped
result instead, matching the pattern in src/checkers.py.
"""

import json
import sys

from src.agents import ask_structured, extract_json_object
from src.rag import retrieve

TEXT_PREVIEW_CHARS = 1500
MISSING_ITEMS = {"what_they_do", "who_they_serve", "service_area", "specific_services"}

# Natural-language clause for each missing item, used to build one
# combined description ("doesn't state what the business does, who it
# serves, ...") rather than a generic label.
MISSING_ITEM_PHRASES = {
    "what_they_do": "what the business does",
    "who_they_serve": "who it serves",
    "service_area": "its service area",
    "specific_services": "which specific services it offers",
}

# Content Clarity is one problem (vague copy), not one problem per
# missing element — this is purely descriptive (content_clarity's score
# comes straight from the model's own 0-100 rating, not a per-item
# deduction), so a missing item "costs" this many informational points
# on the finding, matching the deduction step other checks use.
POINTS_PER_MISSING_ITEM = 20

# Sanity check: a model that lists 2+ things missing shouldn't also be
# handing out a passing score. If it does, trust the missing list over
# the number and clamp down rather than silently keep a contradiction.
SANITY_MIN_MISSING = 2
SANITY_SCORE_THRESHOLD = 70
SANITY_CLAMP_SCORE = 60


def _join_missing_phrases(items):
    phrases = [MISSING_ITEM_PHRASES.get(item, item.replace("_", " ")) for item in items]
    if len(phrases) == 1:
        return phrases[0]
    if len(phrases) == 2:
        return f"{phrases[0]} or {phrases[1]}"
    return ", ".join(phrases[:-1]) + f", or {phrases[-1]}"


def _rubric_context():
    sources = retrieve("Content Clarity good example bad example", top_k=5)
    relevant = [s for s in sources if "content clarity" in s["heading"].lower() or "examples" in s["heading"].lower()]
    chunks = relevant or sources
    return "\n\n".join(f"[{c['heading']}]\n{c['text']}" for c in chunks)


def _build_prompt(page_text):
    system = (
        "You are grading a business website's Content Clarity for AI visibility, "
        "using the rubric below. Respond with ONLY a single JSON object, no other "
        "text or markdown formatting, matching exactly this shape:\n"
        '{"score": <integer 0-100>, '
        '"missing": [<zero or more of "what_they_do", "who_they_serve", "service_area", "specific_services">], '
        '"worst_passage": "<the single worst quoted passage from the page text, or empty string>", '
        '"reason": "<one or two sentence explanation>"}\n\n'
        "Rubric (Content Clarity section of the AI-visibility playbook):\n"
        f"{_rubric_context()}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Page text to grade:\n\n{page_text}"},
    ]


def _call_and_parse(prompt, model):
    """Raises ValueError (with the raw response text attached) if the
    model's response isn't parseable JSON with a numeric score, so the
    caller can log the actual response and retry."""
    result = ask_structured(prompt, model=model, temperature=0, json_mode=True)
    try:
        return _parse_response(result["content"])
    except ValueError as error:
        raise ValueError(f"{error} | raw response: {result['content']!r}") from error


def check_content_clarity(snapshot, model=None):
    page_text = (snapshot.get("text") or "").strip()[:TEXT_PREVIEW_CHARS]

    if not page_text:
        return {"score": None, "findings": [], "skipped": "No page text available to grade"}

    prompt = _build_prompt(page_text)
    parsed, parse_error = None, None
    for attempt in (1, 2):
        try:
            parsed = _call_and_parse(prompt, model)
            break
        except ValueError as error:
            # The check ran but the response wasn't parseable JSON — worth
            # one retry, since this is usually the model ignoring the
            # "raw JSON only" instruction on a single call, not a
            # persistent problem.
            parse_error = error
            print(f"check_content_clarity parse failure (attempt {attempt}/2): {error}", file=sys.stderr)
        except Exception as error:
            print(f"check_content_clarity failed: {type(error).__name__}: {error}", file=sys.stderr)
            return {"score": None, "findings": [], "skipped": f"Content Clarity check failed: {error}"}

    if parsed is None:
        # A parse failure is the check not running, not the fix being
        # bad — callers (e.g. fix_generator._verify_content_clarity_fix)
        # key off this "skipped" shape to mark the outcome "unavailable"
        # rather than "failed".
        return {
            "score": None,
            "findings": [],
            "skipped": f"Content Clarity check couldn't run — the model's response wasn't valid JSON: {parse_error}",
        }

    score = parsed["score"]

    missing = [item for item in (parsed.get("missing") or []) if item in MISSING_ITEMS]

    if score >= SANITY_SCORE_THRESHOLD and len(missing) >= SANITY_MIN_MISSING:
        print(
            f"Content Clarity sanity check: model scored {score} but listed "
            f"{len(missing)} missing items {missing}; clamping to {SANITY_CLAMP_SCORE}.",
            file=sys.stderr,
        )
        score = SANITY_CLAMP_SCORE

    reason = parsed.get("reason") or ""
    worst_passage = parsed.get("worst_passage") or ""

    findings = []
    if missing:
        clause = f"It doesn't state {_join_missing_phrases(missing)}."
        description = f"{reason} {clause}" if reason else clause
        findings.append(
            {
                "category": "content_clarity",
                "title": "Homepage copy is too vague for AI systems to summarise",
                "description": description,
                "priority": "Medium",
                "fix_type": "generated",
                "points_deducted": POINTS_PER_MISSING_ITEM * len(missing),
                # Kept so the fix generator addresses exactly what's
                # missing in one rewrite, rather than guessing at all
                # four every time regardless of what's actually wrong.
                "missing": missing,
                "worst_passage": worst_passage,
            }
        )

    return {"score": int(score), "findings": findings}


def _parse_response(content):
    parsed = json.loads(extract_json_object(content))
    if not isinstance(parsed, dict) or not isinstance(parsed.get("score"), (int, float)):
        raise ValueError(f"Model response had no numeric score: {parsed!r}")
    return parsed
