"""The main chat's brain: classifies what a message wants, then either
answers from the knowledge base (grounded in the user's real scores and
findings when they have one) or signals which workflow app.py should
trigger.

Never falls back to a canned response: if intent classification fails,
the real error propagates (ChatIntentError) so app.py can show it in
the chat instead of a silent stub.
"""

import json

from src.agents import ask_structured, load_prompt, strip_code_fence
from src.rag import retrieve

VALID_INTENTS = {"question", "run_audit", "generate_fix", "fix_all", "check_progress"}

CATEGORY_LABELS = {
    "nap_consistency": "NAP Consistency",
    "structured_data": "Structured Data",
    "content_clarity": "Content Clarity",
    "crawler_access": "Crawler Access",
    "mentions": "Mentions",
}


class ChatIntentError(Exception):
    pass


def classify_intent(question, has_analysis):
    """One structured LLM call: what does this message want?"""
    system = (
        "Classify the user's message into exactly one intent for Discovr, an "
        "AI-visibility audit assistant. Respond with ONLY a single JSON object, "
        "no markdown fence, shaped exactly:\n"
        '{"intent": "question" | "run_audit" | "generate_fix" | "fix_all" | '
        '"check_progress", "finding_ref": "<short phrase identifying which '
        'finding, or null>"}\n\n'
        "Intents:\n"
        "- run_audit: start or re-run the full AI-visibility audit.\n"
        "- fix_all: work through every open finding automatically "
        '(e.g. "fix my site", "fix everything", "work through my findings").\n'
        "- generate_fix: fix ONE specific finding the user names or describes. "
        'Set finding_ref to a short phrase identifying it (e.g. "schema", '
        '"crawler access", "the address issue").\n'
        "- check_progress: asks how their score has changed over time, or "
        "whether they're improving.\n"
        "- question: anything else — general questions about Discovr, how "
        "scoring works, or questions about their own current score or "
        "findings.\n\n"
        f"The user {'has' if has_analysis else 'does not have'} a current "
        "analysis on file."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    try:
        result = ask_structured(messages, temperature=0)
        parsed = json.loads(strip_code_fence(result["content"]))
        intent = parsed.get("intent")
        if intent not in VALID_INTENTS:
            raise ValueError(f"model returned an unrecognized intent: {intent!r}")
        return {"intent": intent, "finding_ref": parsed.get("finding_ref")}
    except Exception as error:
        raise ChatIntentError(f"Could not classify your message: {error}") from error


def resolve_finding_ref(finding_ref, findings):
    """Match a free-text finding_ref against a list of findings by title
    or category. Returns the single match, or None if there are no
    findings, no match, or more than one match (ambiguous) — the caller
    should ask for clarification rather than guess."""
    if not findings:
        return None
    if len(findings) == 1 and not finding_ref:
        return findings[0]
    if not finding_ref:
        return None

    ref = finding_ref.lower()
    matches = [
        f for f in findings
        if ref in f["title"].lower()
        or ref in f["category"].lower()
        or ref in CATEGORY_LABELS.get(f["category"], "").lower()
    ]
    return matches[0] if len(matches) == 1 else None


def _score_context(business, analysis, findings):
    """The user's real current results, folded into the system prompt so
    "how am I scored" gets answered with their actual numbers rather
    than a generic explanation. Empty string (no context added) if they
    have no analysis yet."""
    if analysis is None:
        return ""

    category_lines = "\n".join(
        f"- {label}: {analysis[f'{name}_score']}"
        if analysis[f"{name}_score"] is not None
        else f"- {label}: not connected"
        for name, label in CATEGORY_LABELS.items()
    )
    findings_lines = "\n".join(
        f"- [{f['priority']}] {CATEGORY_LABELS.get(f['category'], f['category'])}: "
        f"{f['title']} — {f['description']}"
        for f in (findings or [])
    ) or "(none)"

    business_name = business["name"] if business else "their business"
    return (
        f"\n\nThis user's real, current AI-visibility results for {business_name}:\n"
        f"Overall score: {analysis['overall_score']}\n"
        f"Category scores:\n{category_lines}\n"
        f"Open findings:\n{findings_lines}\n\n"
        "When the question is about their own score, category, or findings, "
        "answer using these real numbers — never a generic explanation."
    )


def answer_question(question, business=None, analysis=None, findings=None):
    """Retrieve from the knowledge base and answer, grounded in the
    user's real results when they have any."""
    sources = retrieve(question, top_k=3)
    knowledge_base = "\n\n".join(f"[{s['heading']}]\n{s['text']}" for s in sources)
    system = load_prompt("website_chatbot.txt").replace("{knowledge_base}", knowledge_base)
    system += _score_context(business, analysis, findings)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    return ask_structured(messages)["content"]


def describe_progress(analyses):
    """Trend since the last audit, from real persisted analyses — no LLM
    call, since it's arithmetic on real numbers, not something needing
    judgment or phrasing."""
    if not analyses:
        return "No audits yet — run one first and I can track your progress."
    if len(analyses) == 1:
        return (
            f"Just one audit so far (overall score {analyses[0]['overall_score']}). "
            "Run another and I can show you the trend."
        )

    previous, latest = analyses[-2], analyses[-1]
    overall_delta = latest["overall_score"] - previous["overall_score"]
    trend = "up" if overall_delta > 0 else "down" if overall_delta < 0 else "unchanged"
    lines = [
        f"Overall score is {trend} {abs(overall_delta)} point(s) since your last "
        f"audit: {previous['overall_score']} → {latest['overall_score']} "
        f"(across {len(analyses)} audits total)."
    ]
    for category, label in CATEGORY_LABELS.items():
        before = previous[f"{category}_score"]
        after = latest[f"{category}_score"]
        if before is not None and after is not None and before != after:
            lines.append(f"{label}: {before} → {after}.")
    return " ".join(lines)
