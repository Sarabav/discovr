"""Scoring helpers for turning category findings into an overall score."""


def calculate_overall_score(category_findings):
    """Average the per-category scores into a single 0-100 score."""
    scores = [category["score"] for category in category_findings.values()]
    return round(sum(scores) / len(scores)) if scores else 0


def grade_for_score(score):
    """Map a numeric score to a short human-readable grade."""
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Needs Improvement"
    return "Weak"
