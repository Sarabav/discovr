"""Aggregates the five category checks into one report, ranks findings
by real-world impact, and persists the result.

Calls src/checkers.py (deterministic) and src/clarity.py (the one
LLM-based check), then src/db.py to persist.
"""

import json
import sys

from src.agents import ask_structured, strip_code_fence
from src.checkers import (
    check_crawler_access,
    check_mentions,
    check_nap_consistency,
    check_structured_data,
)
from src.clarity import check_content_clarity
from src.store import create_analysis, create_finding

CHECKS = {
    "nap_consistency": check_nap_consistency,
    "structured_data": check_structured_data,
    "content_clarity": check_content_clarity,
    "crawler_access": check_crawler_access,
    "mentions": check_mentions,
}

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def run_all_checks(snapshot):
    """Run all five category checks against `snapshot` (the scraper's
    result dict, plus a "robots" key from scrape_website.check_crawler_access
    — see app.py's /components/scoring/run route for how it's built).

    Skipped checks (score None) don't count toward the overall average,
    so a business missing a Places/Brave connection isn't penalized for
    it; they're surfaced separately in "skipped" instead."""
    categories = {}
    skipped = {}
    findings = []

    for name, check in CHECKS.items():
        result = check(snapshot)
        categories[name] = result.get("score")
        if result.get("score") is None and result.get("skipped"):
            skipped[name] = result["skipped"]
        findings.extend(result.get("findings") or [])

    scored = [score for score in categories.values() if score is not None]
    overall_score = round(sum(scored) / len(scored)) if scored else None

    return {
        "overall_score": overall_score,
        "categories": categories,
        "skipped": skipped,
        "findings": findings,
    }


def _rank_findings_by_priority(findings):
    return sorted(findings, key=lambda f: PRIORITY_ORDER.get(f.get("priority"), 3))


def _build_ranking_prompt(findings, snapshot):
    numbered = "\n".join(
        f"{i}. [{f['category']}] {f['title']} (priority: {f['priority']}): {f['description']}"
        for i, f in enumerate(findings)
    )
    business = snapshot.get("final_url") or snapshot.get("url") or "the business"
    system = (
        f"You rank AI-visibility findings for {business} by their real impact on "
        "whether an AI assistant can find, read, and correctly recommend the "
        "business. Findings in the crawler_access category should generally rank "
        "above everything else, since a fix to schema markup or website copy does "
        "nothing on a page an AI crawler cannot even fetch.\n\n"
        "Respond with ONLY a JSON array, no other text or markdown formatting, of "
        'objects shaped exactly like {"index": <int, the original list index above>, '
        '"why_it_matters": "<one sentence>"}, ordered from most to least impactful. '
        "Include every index exactly once."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Findings:\n{numbered}"},
    ]


def rank_findings(findings, snapshot):
    """Reorder findings by real impact on AI visibility (one LLM call),
    adding a one-sentence why_it_matters to each. Falls back to sorting
    by the checkers' own priority if the call fails."""
    if not findings:
        return []

    try:
        result = ask_structured(_build_ranking_prompt(findings, snapshot), temperature=0)
        ranking = json.loads(strip_code_fence(result["content"]))

        ranked, seen = [], set()
        for entry in ranking:
            index = entry.get("index")
            if index is None or index in seen or not (0 <= index < len(findings)):
                continue
            seen.add(index)
            finding = dict(findings[index])
            finding["why_it_matters"] = entry.get("why_it_matters", "")
            ranked.append(finding)

        # Anything the model dropped is appended at the end rather than lost.
        for index, finding in enumerate(findings):
            if index not in seen:
                ranked.append(dict(finding))

        return ranked
    except Exception as error:
        print(f"rank_findings LLM call failed, falling back to priority sort: {error}", file=sys.stderr)
        return _rank_findings_by_priority(findings)


def save_analysis(business_id, snapshot_id, results):
    """Write the analyses row and all findings rows via src/db.py.
    Returns the new analysis id."""
    analysis_id = create_analysis(
        business_id, snapshot_id, results["overall_score"], results["categories"], results.get("skipped")
    )
    for finding in results["findings"]:
        create_finding(analysis_id, finding)
    return analysis_id
