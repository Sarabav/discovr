"""Analysis orchestration.

`run_analysis` currently builds its report from hardcoded sample data.
It is the single seam where real website/social scraping would plug in
later — callers (app.py) only depend on the returned report shape, not
on how it was produced.
"""

from data.sample_data import BUSINESS_PROFILE, CATEGORY_FINDINGS, RECOMMENDATIONS
from src.scoring import calculate_overall_score, grade_for_score


def run_analysis(website_url, facebook_handle, instagram_handle):
    overall_score = calculate_overall_score(CATEGORY_FINDINGS)

    return {
        "input": {
            "website": website_url or BUSINESS_PROFILE["website"],
            "facebook": facebook_handle or BUSINESS_PROFILE["facebook"],
            "instagram": instagram_handle or BUSINESS_PROFILE["instagram"],
        },
        "business_name": BUSINESS_PROFILE["name"],
        "overall_score": overall_score,
        "overall_grade": grade_for_score(overall_score),
        "categories": CATEGORY_FINDINGS,
        "recommendations": RECOMMENDATIONS,
    }
