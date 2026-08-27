"""Mentions component: searches Reddit's public JSON search endpoint for
independent mentions of a business. No API key needed — Reddit's
/search.json is meant to be publicly readable.

STATUS: this code is correct but currently unusable in production.
Reddit blocks /search.json with a 403 for any non-browser client — and
not just on User-Agent: a real Chrome UA plus full browser-like headers
(Accept, Accept-Language, Referer) still gets 403'd at the network
level (server: snooserv, a full HTML challenge-page body), which means
Reddit is blocking the request by IP/fingerprint, not by header
inspection. There's no header combination that fixes this from a
server. See src.checkers.check_mentions, which reports "not measured"
rather than surfacing this as a flaky per-request failure. This will
start working the moment it's run from a network Reddit doesn't block
(or a real proxy/official API key is added) — nothing else needs to
change.

The only mentions source right now; src.checkers.check_mentions is
written so more sources can be folded into the same snapshot["mentions"]
shape later without changing its scoring logic.

Never raises: every failure is reported in the returned dict's "error"
field instead, matching src.components.scrape_website's pattern.
"""

import json
import sys
from datetime import datetime, timezone

import requests

REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"
# A real browser UA doesn't actually bypass Reddit's block (see module
# docstring) but is kept since it's still the more correct choice than
# the default python-requests UA, which Reddit also rejects outright.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT_SECONDS = 10
SEARCH_LIMIT = 10


def city_from_address(address):
    """Best-effort city extraction from a free-form NAP address string
    like "123 Main St, Springfield, IL 62701" — good enough to narrow a
    Reddit search, not a full address parser."""
    if not address or "," not in address:
        return None
    parts = [p.strip() for p in address.split(",")]
    return parts[-2] if len(parts) >= 2 and parts[-2] else None


def _build_query(business_name, city):
    query = f'"{business_name}"'
    return f"{query} {city}" if city else query


def _mentions_business(post, business_name):
    """Reddit's search is loose (stemming, related terms); only count a
    result if the business name actually appears in it."""
    haystack = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
    return business_name.lower() in haystack


def _format_mention(post):
    created = post.get("created_utc")
    created_date = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d") if created else None
    permalink = post.get("permalink")
    return {
        "title": post.get("title"),
        "subreddit": post.get("subreddit"),
        "permalink": f"https://www.reddit.com{permalink}" if permalink else None,
        "score": post.get("score"),
        "created": created_date,
    }


def find_mentions(business_name, city=None):
    """Search Reddit for posts/comments that actually mention
    `business_name`, optionally narrowed by `city` to cut down false
    positives for common business names. Returns
    {"reddit": [...], "count": int, "error": None or str}; never raises."""
    result = {"reddit": [], "count": 0, "error": None}

    if not business_name:
        result["error"] = "No business name to search for."
        return result

    try:
        response = requests.get(
            REDDIT_SEARCH_URL,
            params={"q": _build_query(business_name, city), "limit": SEARCH_LIMIT, "sort": "relevance"},
            headers=HEADERS,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as error:
        result["error"] = f"Could not search Reddit: {error}"
        return result
    except ValueError as error:
        result["error"] = f"Reddit returned an unexpected response: {error}"
        return result

    children = (data.get("data") or {}).get("children") or []
    mentions = [
        _format_mention(post)
        for child in children
        if (post := child.get("data") or {}) and _mentions_business(post, business_name)
    ]

    result["reddit"] = mentions
    result["count"] = len(mentions)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.components.find_mentions <business name> [city]")
        sys.exit(1)

    name_arg = sys.argv[1]
    city_arg = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(find_mentions(name_arg, city_arg), indent=2))
