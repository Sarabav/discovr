"""Deterministic scoring checks: no LLM calls, no network calls — each
function takes the scraper's snapshot dict and returns a plain,
reproducible result. (The one LLM-based check, Content Clarity, lives
separately in src/clarity.py.)

Each check returns {"score": 0-100 or None, "findings": [...]}; a score
of None means the check was skipped (its data source isn't wired up
yet) and the dict also carries a "skipped" reason. Each finding is
shaped {category, title, description, priority, fix_type}, where
priority is "High"/"Medium"/"Low" and fix_type is "generated" (Discovr
can write the fix) or "instruction" (the owner has to act on it).

Only the website connector (src/components/scrape_website.py) exists so
far. check_nap_consistency and check_mentions need Google Places and
Brave Search respectively, so they return a skipped result for now; the
real comparison logic is already written behind an `if ...data:` branch
so each activates automatically once its connector exists.
"""

import re

# Field -> priority. A module-level config dict, not buried in logic, so
# which fields matter (and how much) can be edited without touching
# check_structured_data itself.
REQUIRED_FIELDS = {
    "name": "High",
    "address": "High",
    "telephone": "High",
    "openingHours": "Medium",
    "areaServed": "Medium",
}

# schema.org @type values that count as "this is the business's own
# LocalBusiness listing". LocalBusiness itself plus common subtypes.
LOCAL_BUSINESS_TYPES = {
    "LocalBusiness",
    "Dentist",
    "Physician",
    "MedicalBusiness",
    "Plumber",
    "Electrician",
    "HVACBusiness",
    "HomeAndConstructionBusiness",
    "Restaurant",
    "CafeOrCoffeeShop",
    "BarOrPub",
    "HairSalon",
    "BeautySalon",
    "DaySpa",
    "AutoRepair",
    "AutomotiveBusiness",
    "Attorney",
    "LegalService",
    "AccountingService",
    "RealEstateAgent",
    "Store",
    "ProfessionalService",
}

STRUCTURED_DATA_SCORE_STEP = 20
CRAWLER_BOT_PENALTY = 20
UNREACHABLE_PAGE_PENALTY = 15
NAP_MISMATCH_PENALTY = 25

# St -> Street, Ave -> Avenue, etc., applied after punctuation is
# stripped, so "St." and "St" both normalize the same way.
STREET_ABBREVIATIONS = {
    "st": "street",
    "ave": "avenue",
    "rd": "road",
    "blvd": "boulevard",
    "dr": "drive",
    "ln": "lane",
    "ct": "court",
}


def _iter_schema_items(schema):
    """Flatten schema entries, expanding any @graph arrays (some sites
    wrap multiple entities in one {"@graph": [...]} block per script tag)."""
    for item in schema or []:
        if not isinstance(item, dict):
            continue
        graph = item.get("@graph")
        if isinstance(graph, list):
            for sub in graph:
                if isinstance(sub, dict):
                    yield sub
        else:
            yield item


def _matches_local_business_type(item):
    item_type = item.get("@type")
    types = item_type if isinstance(item_type, list) else [item_type]
    return any(t in LOCAL_BUSINESS_TYPES for t in types if t)


def _unique_types(candidates):
    """@type values across all schema blocks, in order, deduplicated."""
    types = []
    for item in candidates:
        item_type = item.get("@type")
        for t in item_type if isinstance(item_type, list) else [item_type]:
            if t and t not in types:
                types.append(t)
    return types


# Preference order for "what does this site call itself" -- Organization
# and WebSite are reliable identity sources; other page-level types (e.g.
# CollectionPage) just describe whatever page they're attached to.
SITE_IDENTITY_TYPES = ("Organization", "WebSite")


def _site_name_from_schema(candidates):
    for preferred_type in SITE_IDENTITY_TYPES:
        for item in candidates:
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if preferred_type in types and item.get("name"):
                return item["name"]
    return next((item["name"] for item in candidates if item.get("name")), None)


def summarize_schema(schema):
    """Block count and @type names for whatever schema exists on a page,
    independent of whether any of it is a business node. Used by the
    Business Website component page so "3 schema blocks found" and "no
    business schema" can be shown as two separate, non-contradictory
    facts (see check_structured_data for the scoring version)."""
    candidates = list(_iter_schema_items(schema))
    return {
        "block_count": len(candidates),
        "types": _unique_types(candidates),
        "has_business_node": any(_matches_local_business_type(item) for item in candidates),
    }


def check_structured_data(snapshot):
    """No business (LocalBusiness or subtype) schema block -> score 0.
    Two distinct reasons look the same to the score but not to the
    finding text: no schema at all, vs. schema that exists but describes
    something else (e.g. Yoast's default WebPage/WebSite/Organization
    output) with no business node among it. Otherwise, -20 per required
    field that's missing or empty from the business block."""
    candidates = list(_iter_schema_items(snapshot.get("schema")))
    business_block = next((item for item in candidates if _matches_local_business_type(item)), None)

    if business_block is None and not candidates:
        return {
            "score": 0,
            "findings": [
                {
                    "category": "structured_data",
                    "title": "No schema markup found",
                    "description": (
                        "The website has no schema.org markup at all, so AI systems have no "
                        "machine-readable source for the business's name, address, phone, "
                        "hours, or service area."
                    ),
                    "priority": "High",
                    "fix_type": "generated",
                }
            ],
        }

    if business_block is None:
        types_found = _unique_types(candidates)
        site_name = _site_name_from_schema(candidates)
        identity_clause = f"AI systems can see your site is called {site_name}" if site_name else "AI systems can see the site's general pages"
        description = (
            f"Your site has schema markup ({', '.join(types_found)}), but none of it "
            f"describes the business itself. {identity_clause}, but can't find an address, "
            "phone number, or opening hours."
        )
        if "Organization" in types_found:
            description += (
                " An Organization block already exists; the fix is to add a LocalBusiness "
                "node alongside it, not replace what's there."
            )
        return {
            "score": 0,
            "findings": [
                {
                    "category": "structured_data",
                    "title": "Schema markup exists, but no business (LocalBusiness) node found",
                    "description": description,
                    "priority": "High",
                    "fix_type": "generated",
                }
            ],
        }

    score = 100
    findings = []
    for field, priority in REQUIRED_FIELDS.items():
        if business_block.get(field):
            continue
        score -= STRUCTURED_DATA_SCORE_STEP
        findings.append(
            {
                "category": "structured_data",
                "title": f"Missing '{field}' in LocalBusiness schema",
                "description": (
                    f"The site's LocalBusiness schema block does not include a '{field}' "
                    "field, or it is empty."
                ),
                "priority": priority,
                "fix_type": "generated",
            }
        )

    return {"score": max(score, 0), "findings": findings}


def check_crawler_access(snapshot):
    """Reads the robots data the scraper already fetched
    (snapshot["robots"], from scrape_website.check_crawler_access) and
    snapshot["unreachable_pages"]. No robots.txt means every crawler is
    allowed by default, which is correct and not penalized."""
    robots = snapshot.get("robots") or {}
    bots = robots.get("bots") or {}
    findings = []
    score = 100

    if not robots.get("robots_txt"):
        findings.append(
            {
                "category": "crawler_access",
                "title": "No robots.txt found",
                "description": (
                    "The site has no robots.txt, so every crawler is allowed by default. "
                    "This is the correct, unrestricted default, not a problem."
                ),
                "priority": "Low",
                "fix_type": "instruction",
            }
        )
    else:
        blocked_bots = [bot for bot, disallowed in bots.items() if disallowed]
        if blocked_bots:
            # One finding for every blocked bot, not one per bot: they
            # share a single fix (edit robots.txt once), and one-per-bot
            # was drowning out other categories in anything that budgets
            # a limited number of findings to act on (see the agent loop).
            score -= CRAWLER_BOT_PENALTY * len(blocked_bots)
            bot_list = ", ".join(blocked_bots)
            pronoun = "it" if len(blocked_bots) == 1 else "they"
            findings.append(
                {
                    "category": "crawler_access",
                    "title": "AI crawlers blocked in robots.txt",
                    "description": (
                        f"robots.txt disallows {bot_list}, so {pronoun} cannot read any page on the site."
                    ),
                    "priority": "High",
                    "fix_type": "instruction",
                }
            )

    for page in snapshot.get("unreachable_pages") or []:
        score -= UNREACHABLE_PAGE_PENALTY
        status = page.get("status")
        status_text = f"HTTP {status}" if status else "a failed request"
        findings.append(
            {
                "category": "crawler_access",
                "title": "Page unreachable on direct navigation",
                "description": (
                    f"{page.get('url')} loads correctly when a visitor clicks through the "
                    f"site, but returns {status_text} when requested directly by URL, which "
                    "is how AI crawlers fetch pages."
                ),
                "priority": "High",
                "fix_type": "instruction",
            }
        )

    return {"score": max(score, 0), "findings": findings}


def _normalize_nap_value(value):
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r"[^\w\s]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    words = [STREET_ABBREVIATIONS.get(word, word) for word in value.split(" ")]
    return " ".join(words)


def check_nap_consistency(snapshot):
    """Google Places isn't wired up yet, so this is always skipped for
    now. The comparison logic below is complete and activates on its own
    once snapshot["places"] is populated by a real connector."""
    places_data = snapshot.get("places")

    if not places_data:
        return {
            "score": None,
            "findings": [],
            "skipped": "Google Places connector not connected",
        }

    website_nap = snapshot.get("nap") or {}
    score = 100
    findings = []

    for field, priority in (("name", "High"), ("address", "High"), ("phone", "Medium")):
        website_value = website_nap.get(field)
        places_value = places_data.get(field)
        if not website_value or not places_value:
            continue  # ignore fields missing from a source, not a mismatch

        if _normalize_nap_value(website_value) != _normalize_nap_value(places_value):
            score -= NAP_MISMATCH_PENALTY
            findings.append(
                {
                    "category": "nap_consistency",
                    "title": f"{field.title()} does not match Google Business Profile",
                    "description": (
                        f"Website {field} is '{website_value}', but the Google Business "
                        f"Profile lists '{places_value}'."
                    ),
                    "priority": priority,
                    "fix_type": "instruction",
                }
            )

    return {"score": max(score, 0), "findings": findings}


def _mention_thread_list(mentions):
    return "; ".join(
        f"\"{m.get('title')}\" (r/{m.get('subreddit')}) — {m.get('permalink')}" for m in mentions
    )


def check_mentions(snapshot):
    """Reddit's public search (src.components.find_mentions) is correct
    code — but Reddit returns 403 for any non-browser client, so it
    can't actually reach Reddit from a server context today (confirmed:
    a real browser User-Agent, real headers, still 403s at the network
    level). Until that's resolved (a proxy, an official API key, or
    some other search source), this always reports "not measured"
    rather than the raw network error, since from the user's point of
    view Mentions just isn't wired up yet, not intermittently flaky.
    The tiered scoring below is untouched and activates automatically
    the moment find_mentions() can actually return results."""
    mentions_data = snapshot.get("mentions")

    # No mentions data at all (never searched) is "we don't know," not a
    # confirmed zero — same distinction check_nap_consistency makes for
    # a missing places_data. Only real, successful search results ever
    # produce an actual 0-mentions score.
    if not mentions_data or mentions_data.get("error"):
        return {"score": None, "findings": [], "skipped": "Not measured yet — needs a search connector"}

    reddit_mentions = mentions_data.get("reddit") or []
    mention_count = mentions_data.get("count", len(reddit_mentions))

    if mention_count == 0:
        return {
            "score": 20,
            "findings": [
                {
                    "category": "mentions",
                    "title": "No independent mentions found",
                    "description": (
                        "No mentions of the business were found on Reddit, the only "
                        "independent source checked so far."
                    ),
                    "priority": "High",
                    "fix_type": "instruction",
                }
            ],
        }

    thread_list = _mention_thread_list(reddit_mentions)

    if mention_count <= 2:
        return {
            "score": 60,
            "findings": [
                {
                    "category": "mentions",
                    "title": "Few independent mentions found",
                    "description": f"Only {mention_count} independent mention(s) found on Reddit: {thread_list}.",
                    "priority": "Medium",
                    "fix_type": "instruction",
                }
            ],
        }

    return {
        "score": 90,
        "findings": [
            {
                "category": "mentions",
                "title": "Independent mentions found",
                "description": f"{mention_count} independent mention(s) found on Reddit: {thread_list}.",
                "priority": "Low",
                "fix_type": "instruction",
            }
        ],
    }
