"""Tests for the deterministic checks in src/checkers.py.

No LLM calls (check_content_clarity lives separately in src/clarity.py)
and no network calls: every fixture is a plain snapshot dict shaped like
what src/components/scrape_website.py returns.
"""

import pytest

from src.checkers import (
    check_crawler_access,
    check_mentions,
    check_nap_consistency,
    check_structured_data,
)


@pytest.fixture
def snapshot_complete_schema():
    return {
        "schema": [
            {
                "@type": "Dentist",
                "name": "Bright Smile Dental Clinic",
                "address": "123 Main St, Riverside, CA 92501",
                "telephone": "+1-555-010-2222",
                "openingHours": "Mo-Fr 09:00-17:00",
                "areaServed": "Riverside, CA",
            }
        ],
    }


@pytest.fixture
def snapshot_no_schema():
    return {"schema": []}


@pytest.fixture
def snapshot_blocking_gptbot():
    return {
        "robots": {
            "robots_txt": "User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nDisallow:\n",
            "bots": {
                "GPTBot": True,
                "ClaudeBot": False,
                "PerplexityBot": False,
                "CCBot": False,
                "Google-Extended": False,
                "anthropic-ai": False,
            },
        },
        "unreachable_pages": [],
    }


@pytest.fixture
def snapshot_no_robots_txt():
    return {
        "robots": {"robots_txt": "", "bots": {"GPTBot": False, "ClaudeBot": False}},
        "unreachable_pages": [],
    }


@pytest.fixture
def snapshot_two_unreachable_pages():
    return {
        "robots": {"robots_txt": "User-agent: *\nDisallow:\n", "bots": {"GPTBot": False}},
        "unreachable_pages": [
            {"url": "https://example.com/contact", "status": 404},
            {"url": "https://example.com/about", "status": 500},
        ],
    }


class TestCheckStructuredData:
    def test_complete_schema_scores_100_with_no_findings(self, snapshot_complete_schema):
        result = check_structured_data(snapshot_complete_schema)
        assert result["score"] == 100
        assert result["findings"] == []

    def test_no_schema_scores_0_with_one_high_finding(self, snapshot_no_schema):
        result = check_structured_data(snapshot_no_schema)
        assert result["score"] == 0
        assert len(result["findings"]) == 1
        assert result["findings"][0]["priority"] == "High"
        assert result["findings"][0]["fix_type"] == "generated"

    def test_missing_fields_deduct_20_each(self):
        snapshot = {"schema": [{"@type": "LocalBusiness", "name": "X", "telephone": "555-1234"}]}
        result = check_structured_data(snapshot)
        # name, telephone present; address, openingHours, areaServed missing = -60
        assert result["score"] == 40
        assert len(result["findings"]) == 3

    def test_graph_array_is_expanded(self):
        snapshot = {"schema": [{"@graph": [{"@type": ["LocalBusiness"], "name": "X"}]}]}
        result = check_structured_data(snapshot)
        assert result["score"] == 20  # only name present, 4 fields missing


class TestCheckCrawlerAccess:
    def test_gptbot_blocked_deducts_and_flags_high(self, snapshot_blocking_gptbot):
        result = check_crawler_access(snapshot_blocking_gptbot)
        assert result["score"] == 80
        assert len(result["findings"]) == 1
        assert "GPTBot" in result["findings"][0]["description"]
        assert result["findings"][0]["priority"] == "High"
        assert result["findings"][0]["fix_type"] == "instruction"

    def test_multiple_blocked_bots_collapse_into_one_finding(self):
        bots = {"GPTBot": True, "ClaudeBot": True, "PerplexityBot": False, "CCBot": False, "Google-Extended": False, "anthropic-ai": False}
        snapshot = {"robots": {"robots_txt": "x", "bots": bots}, "unreachable_pages": []}
        result = check_crawler_access(snapshot)
        assert result["score"] == 60  # -20 per blocked bot, 2 blocked
        assert len(result["findings"]) == 1
        assert result["findings"][0]["title"] == "AI crawlers blocked in robots.txt"
        assert "GPTBot" in result["findings"][0]["description"]
        assert "ClaudeBot" in result["findings"][0]["description"]

    def test_no_robots_txt_is_low_priority_informational_no_penalty(self, snapshot_no_robots_txt):
        result = check_crawler_access(snapshot_no_robots_txt)
        assert result["score"] == 100
        assert len(result["findings"]) == 1
        assert result["findings"][0]["priority"] == "Low"

    def test_two_unreachable_pages_deduct_15_each(self, snapshot_two_unreachable_pages):
        result = check_crawler_access(snapshot_two_unreachable_pages)
        assert result["score"] == 70
        unreachable_findings = [f for f in result["findings"] if "unreachable" in f["title"].lower()]
        assert len(unreachable_findings) == 2
        assert all(f["priority"] == "High" for f in unreachable_findings)

    def test_score_never_goes_below_zero(self):
        all_bots_blocked = {bot: True for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "CCBot", "Google-Extended", "anthropic-ai")}
        snapshot = {
            "robots": {"robots_txt": "x", "bots": all_bots_blocked},
            "unreachable_pages": [{"url": f"https://x.com/{i}", "status": 404} for i in range(10)],
        }
        result = check_crawler_access(snapshot)
        assert result["score"] == 0


class TestSkippedChecksActivateAutomatically:
    def test_nap_consistency_skipped_without_places_data(self):
        result = check_nap_consistency({"nap": {"name": "X"}})
        assert result["score"] is None
        assert result["skipped"] == "Google Places connector not connected"
        assert result["findings"] == []

    def test_nap_consistency_activates_once_places_data_exists(self):
        snapshot = {
            "nap": {"name": "Bright Smile", "address": "123 Main St", "phone": "555-1234"},
            "places": {"name": "Bright Smile Dental", "address": "123 Main Street", "phone": "555-1234"},
        }
        result = check_nap_consistency(snapshot)
        assert result["score"] == 75  # only name mismatches; "St"/"Street" normalize the same
        assert len(result["findings"]) == 1
        assert "Name" in result["findings"][0]["title"]


class TestCheckMentions:
    """Reddit blocks find_mentions.py's requests at the network level
    (see src/components/find_mentions.py), so in practice this always
    skips today — but the tiered scoring is real and activates
    automatically the moment a search actually succeeds. Missing
    mentions data and a genuine search failure both mean "we don't
    know," not a confirmed zero — only real results ever score."""

    def test_no_mentions_data_is_skipped_not_scored_zero(self):
        result = check_mentions({})
        assert result["score"] is None
        assert result["skipped"] == "Not measured yet — needs a search connector"
        assert result["findings"] == []

    def test_search_failure_is_skipped_with_static_message(self):
        result = check_mentions({"mentions": {"reddit": [], "count": 0, "error": "Could not search Reddit: 403 blocked"}})
        assert result["score"] is None
        assert result["skipped"] == "Not measured yet — needs a search connector"
        assert result["findings"] == []

    def test_zero_mentions_scores_20(self):
        result = check_mentions({"mentions": {"reddit": [], "count": 0, "error": None}})
        assert result["score"] == 20
        assert result["findings"][0]["priority"] == "High"

    def test_few_mentions_scores_60_and_lists_threads(self):
        reddit = [
            {"title": "Anyone tried Bright Smile Dental?", "subreddit": "dentistry", "permalink": "https://reddit.com/r/dentistry/1"},
        ]
        result = check_mentions({"mentions": {"reddit": reddit, "count": 1, "error": None}})
        assert result["score"] == 60
        assert result["findings"][0]["priority"] == "Medium"
        assert "Bright Smile Dental" in result["findings"][0]["description"]
        assert "reddit.com/r/dentistry/1" in result["findings"][0]["description"]

    def test_three_or_more_mentions_scores_90(self):
        reddit = [{"title": f"post {i}", "subreddit": "x", "permalink": f"https://reddit.com/{i}"} for i in range(3)]
        result = check_mentions({"mentions": {"reddit": reddit, "count": 3, "error": None}})
        assert result["score"] == 90
        assert result["findings"][0]["priority"] == "Low"
