"""Fix generator: given a finding, produces the actual fix.

Generated fixes (structured_data, content_clarity) are grounded in two
retrieved sources, never invented: the business's own scraped content
(src.rag.retrieve_business_context) and the playbook's "Tips for Fixing"
guidance (src.rag.retrieve) — so neither the facts nor the how-to advice
are hardcoded here.

CRITICAL: a structured_data field that isn't actually confirmed present
in the retrieved content is dropped and listed in needs_from_owner
instead of being invented — enforced in code (_value_confirmed), not
just by prompt instruction, since a plausible-looking wrong address is
worse than a missing one.

Instruction fixes (crawler_access, nap_consistency) are deterministic:
built from the finding's own data plus the same playbook guidance, no
LLM call, nothing to hallucinate.
"""

import json
import re
from urllib.parse import urlparse

from src.agents import ask_structured, strip_code_fence
from src.checkers import LOCAL_BUSINESS_TYPES, REQUIRED_FIELDS
from src.clarity import MISSING_ITEM_PHRASES, check_content_clarity
from src.store import create_fix, get_business
from src.rag import retrieve, retrieve_business_context

GROUNDING_QUERIES = {
    "structured_data": "business name address phone hours",
    "content_clarity": "what services does this business offer",
    "nap_consistency": "business name address phone",
    "crawler_access": "business name address phone",
}

MAX_CLARITY_ATTEMPTS = 2
CLARITY_MIN_IMPROVEMENT = 10
BUSINESS_TYPE_HINT = ", ".join(sorted(LOCAL_BUSINESS_TYPES - {"LocalBusiness"}))

BLOCKED_BOTS_TITLE = "AI crawlers blocked in robots.txt"
BLOCKED_BOTS_RE = re.compile(r"disallows (.+?), so")
URL_RE = re.compile(r"https?://\S+")
NAP_MISMATCH_RE = re.compile(r"Website (\w+) is '([^']*)', but the Google Business Profile lists '([^']*)'")

# Matches the "<Type> - name: X" lines src.rag._schema_to_text produces for
# business-identity schema nodes, and the "Page title: X" line
# src.rag._business_source_text always includes — both are reliable,
# deterministic sources for the business's own name without needing the
# model to get it right.
NAME_FROM_SCHEMA_RE = re.compile(r"name:\s*([^,\n]+)")
PAGE_TITLE_RE = re.compile(r"Page title:\s*([^\n]+)")


def _name_from_context(context_text):
    match = NAME_FROM_SCHEMA_RE.search(context_text) or PAGE_TITLE_RE.search(context_text)
    return match.group(1).strip() if match else None


def _tips_for_category(category):
    """The playbook's whole "Tips for Fixing" section, retrieved rather
    than paraphrased in Python. Fine as broad prompt context for an LLM
    call (structured_data, content_clarity) — never as returned fix
    content, since it covers every category, not just this finding's
    (see _relevant_tip_line for the instruction generators, which do
    return their content directly with no LLM call to filter it)."""
    label = category.replace("_", " ")
    sources = retrieve(f"Tips for fixing {label}", top_k=3)
    relevant = [s for s in sources if "tips for fixing" in s["heading"].lower()]
    chunks = relevant or sources
    return "\n\n".join(c["text"] for c in chunks)


def _relevant_tip_line(prefix):
    """Just the one line of the retrieved "Tips for Fixing" section that
    starts with `prefix`, so a deterministic instruction fix can ground
    its content in the playbook's own wording without leaking the other
    seven categories' unrelated advice into it."""
    for line in _tips_for_category("fixing").splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line
    return ""


def _grounded_chunks(finding, business_id):
    query = GROUNDING_QUERIES.get(finding.get("category"), finding.get("title", ""))
    return retrieve_business_context(business_id, query)


# ---------- structured_data ----------


def _confirmed_in_context(value, context_text):
    if not value:
        return False
    normalized_value = re.sub(r"\s+", " ", str(value)).strip().lower()
    normalized_context = re.sub(r"\s+", " ", context_text).lower()
    return normalized_value in normalized_context


def _value_confirmed(value, context_text):
    if isinstance(value, dict):
        return any(
            _confirmed_in_context(v, context_text) for v in value.values() if isinstance(v, (str, int, float))
        )
    if isinstance(value, list):
        return bool(value) and all(
            _confirmed_in_context(v, context_text) for v in value if isinstance(v, (str, int, float))
        )
    return _confirmed_in_context(value, context_text)


def _structured_data_prompt(finding, context, tips, retry_reason=None):
    system = (
        "You write schema.org JSON-LD for a local business's AI visibility. "
        "Use ONLY facts present in the retrieved website content below. Never "
        "invent an address, phone number, opening hours, or any other detail "
        "that isn't there — a missing field is far better than a wrong one.\n\n"
        f"Pick the most specific @type the content supports (e.g. {BUSINESS_TYPE_HINT}), "
        "falling back to LocalBusiness if nothing more specific is supported.\n\n"
        f"Guidance from the AI-visibility playbook:\n{tips}\n\n"
        f"Retrieved content from the business's own website:\n{context}\n\n"
        "Respond with ONLY a single JSON object, no markdown fence, shaped exactly:\n"
        '{"schema": {<the LocalBusiness JSON-LD block, including "@context": '
        '"https://schema.org" and "@type">}, '
        f'"needs_from_owner": [<subset of {list(REQUIRED_FIELDS)} that could not be confirmed>]}}'
    )
    if retry_reason:
        system += f"\n\nA previous attempt failed verification for this reason: {retry_reason}\nDo not repeat that mistake."
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Finding: {finding.get('title', '')} — {finding.get('description', '')}"},
    ]


FILL_IN_VALUES = {
    "name": "FILL IN: your business name",
    "telephone": "FILL IN: your public phone number",
    "openingHours": "FILL IN: e.g. Mo-Su 08:00-20:00",
    "areaServed": "FILL IN: city, region, or service area",
}


def _fill_in_address():
    return {
        "@type": "PostalAddress",
        "streetAddress": "FILL IN: your street address",
        "addressLocality": "FILL IN: city",
        "addressRegion": "FILL IN: state/province",
        "postalCode": "FILL IN: postal code",
    }


def _generate_structured_data_fix(finding, business_id, retry_reason=None):
    chunks = _grounded_chunks(finding, business_id)
    context = "\n\n".join(chunks) or "(no content retrieved from the business's website)"
    context_text = "\n".join(chunks)
    tips = _tips_for_category("structured_data")

    try:
        result = ask_structured(_structured_data_prompt(finding, context, tips, retry_reason), temperature=0)
        parsed = json.loads(strip_code_fence(result["content"]))
        schema = parsed.get("schema") or {}
        needs_from_owner = [f for f in (parsed.get("needs_from_owner") or []) if f in REQUIRED_FIELDS]
    except Exception:
        schema = {}
        needs_from_owner = list(REQUIRED_FIELDS)

    schema["@context"] = "https://schema.org"
    type_value = schema.get("@type")
    types = type_value if isinstance(type_value, list) else [type_value]
    if not any(t in LOCAL_BUSINESS_TYPES for t in types if t):
        schema["@type"] = "LocalBusiness"

    # The business's own site URL is deterministic ground truth — it's
    # exactly what was scraped, nothing to "confirm" from retrieved text.
    business = get_business(business_id)
    if business and business["website_url"] and not schema.get("url"):
        schema["url"] = business["website_url"]

    # Hard safety net + backfill: drop any field whose value doesn't
    # actually appear in the grounded content, regardless of what the
    # model claimed (never trust the model alone on "did I invent
    # this"), but also recover the business name ourselves from the
    # grounded text if the model skipped a field we can clearly confirm
    # — omitting a plainly-present fact is over-correction, not safety.
    for field in REQUIRED_FIELDS:
        value = schema.get(field)
        confirmed = value and _value_confirmed(value, context_text)

        if not confirmed and field == "name":
            fallback_name = _name_from_context(context_text)
            if fallback_name:
                schema["name"] = fallback_name
                confirmed = True

        if confirmed:
            needs_from_owner = [f for f in needs_from_owner if f != field]
        else:
            schema.pop(field, None)
            if field not in needs_from_owner:
                needs_from_owner.append(field)

    # Required fields that couldn't be confirmed get an unmistakable
    # placeholder instead of being silently dropped, so the block is a
    # fillable template rather than missing pieces with no indication of
    # what belongs where. Still listed in needs_from_owner either way.
    for field in needs_from_owner:
        if field == "address":
            schema["address"] = _fill_in_address()
        elif field in FILL_IN_VALUES:
            schema[field] = FILL_IN_VALUES[field]

    where_to_apply = 'Paste as a <script type="application/ld+json"> block in the <head> of every page.'
    if "address" in needs_from_owner or "telephone" in needs_from_owner:
        where_to_apply += (
            " If this business has multiple locations, each location needs its own "
            "LocalBusiness block with that location's own address and phone on that "
            "location's own page — not a single block on the homepage."
        )

    return {
        "fix_type": "generated",
        "content": json.dumps(schema, indent=2),
        "before": None,
        "needs_from_owner": needs_from_owner,
        "grounded_on": chunks,
        "where_to_apply": where_to_apply,
    }


# ---------- content_clarity ----------


DEFAULT_CLARITY_TARGETS = "what the business does, who it serves, where it operates, and its specific services"


def _content_clarity_prompt(before, context, tips, missing=None, retry_reason=None):
    targets = (
        ", ".join(MISSING_ITEM_PHRASES.get(item, item.replace("_", " ")) for item in missing)
        if missing
        else DEFAULT_CLARITY_TARGETS
    )
    system = (
        f"You rewrite a local business's website copy so an AI system can clearly "
        f"understand {targets}. One rewrite must cover all of these — don't leave "
        "any of them out. Use ONLY facts present in the retrieved content below — "
        "do not invent services, locations, or details that aren't there. Write "
        "2-3 plain sentences, no marketing language.\n\n"
        f"Guidance from the AI-visibility playbook:\n{tips}\n\n"
        f"Retrieved content from the business's own website:\n{context}\n\n"
        "Respond with ONLY the replacement text: no quotes, no markdown, no preamble."
    )
    if retry_reason:
        system += f"\n\nA previous rewrite failed verification for this reason: {retry_reason}\nDo not repeat that mistake."
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Weakest passage to replace:\n{before}"},
    ]


def _generate_content_clarity_fix(finding, business_id, retry_reason=None):
    chunks = _grounded_chunks(finding, business_id)
    context = "\n\n".join(chunks) or "(no content retrieved from the business's website)"
    tips = _tips_for_category("content_clarity")
    before = finding.get("worst_passage") or ""
    missing = finding.get("missing") or []

    try:
        result = ask_structured(_content_clarity_prompt(before, context, tips, missing, retry_reason), temperature=0)
        after = strip_code_fence(result["content"]).strip()
    except Exception:
        after = ""

    return {
        "fix_type": "generated",
        "content": after,
        "before": before,
        "needs_from_owner": [],
        "grounded_on": chunks,
        "where_to_apply": "Replace the weakest passage on the page with the rewritten text.",
    }


# ---------- crawler_access (instruction) ----------


def _generate_crawler_access_fix(finding):
    title = finding.get("title", "")
    description = finding.get("description", "")

    if title == BLOCKED_BOTS_TITLE:
        bots_match = BLOCKED_BOTS_RE.search(description)
        bot_list = bots_match.group(1) if bots_match else "the blocked crawlers"
        tip = _relevant_tip_line("Unblocking AI crawlers:")
        content = (
            "1. Open robots.txt at the root of the site.\n"
            f"2. Find the block(s) disallowing {bot_list} and remove their "
            "\"Disallow: /\" line (or the whole block, if it has no other rules).\n"
            "3. Save and redeploy so the updated robots.txt is live."
        )
        if tip:
            content += f"\n\n{tip}"
        where = "robots.txt at the site root"
    else:
        url_match = URL_RE.search(description)
        page_url = url_match.group(0) if url_match else "the affected page"
        host = urlparse(page_url).netloc or "the site's host"
        tip = _relevant_tip_line("Fixing unreachable pages:")
        content = (
            f"1. {page_url} loads when clicked from the site but returns an error "
            "on direct navigation — a hosting routing issue, not a robots.txt issue.\n"
            f"2. Add a catch-all rewrite for {host} so every URL serves the app.\n"
            "3. Redeploy and re-check that the URL loads directly."
        )
        if tip:
            content += f"\n\n{tip}"
        content += (
            "\n\nThis is a hosting/deploy configuration change for whoever built or "
            "hosts the site, not something Discovr can apply directly."
        )
        where = f"hosting configuration for {host}"

    return {
        "fix_type": "instruction",
        "content": content,
        "before": None,
        "needs_from_owner": [],
        "grounded_on": [tip] if tip else [],
        "where_to_apply": where,
    }


# ---------- nap_consistency (instruction) ----------


def _generate_nap_consistency_fix(finding):
    description = finding.get("description", "")
    match = NAP_MISMATCH_RE.search(description)
    tip = _relevant_tip_line("Fixing inconsistent NAP details:")

    if match:
        field, website_value, places_value = match.groups()
        # Google Business Profile is treated as canonical: it's the value
        # location-aware AI answers pull from most directly, so the
        # website should be the one that changes to match it.
        content = (
            f"1. Canonical value: '{places_value}' (from the Google Business Profile).\n"
            f"2. Update the website's {field} to '{places_value}' everywhere it "
            f"currently reads '{website_value}' — footer, contact page, and any "
            "LocalBusiness schema block — so both sources match exactly."
        )
        where = f"the website's {field} (footer, contact page, schema)"
    else:
        content = description
        where = "the website's NAP details"

    if tip:
        content += f"\n\n{tip}"

    return {
        "fix_type": "instruction",
        "content": content,
        "before": None,
        "needs_from_owner": [],
        "grounded_on": [tip] if tip else [],
        "where_to_apply": where,
    }


# ---------- dispatch ----------


def generate_fix(finding, business_id, retry_reason=None):
    """retry_reason: verify_fix's reason from a prior failed attempt at
    this same finding, if any, folded into the prompt so a retry doesn't
    just repeat the same mistake (used by the agent loop's EXECUTE node;
    ignored by the deterministic instruction generators)."""
    category = finding.get("category")
    if category == "structured_data":
        return _generate_structured_data_fix(finding, business_id, retry_reason)
    if category == "content_clarity":
        return _generate_content_clarity_fix(finding, business_id, retry_reason)
    if category == "crawler_access":
        return _generate_crawler_access_fix(finding)
    if category == "nap_consistency":
        return _generate_nap_consistency_fix(finding)
    raise ValueError(f"No fix generator for category '{category}'")


def _verify_structured_data_fix(fix):
    """Purely deterministic (json.loads + dict checks), no external
    calls — so this can only ever pass or fail, never "unavailable"."""
    try:
        schema = json.loads(fix["content"])
    except (ValueError, TypeError) as error:
        return {"status": "failed", "reason": f"Generated content is not valid JSON: {error}", "attempts": 1}

    if "@context" not in schema or not schema.get("@type"):
        return {"status": "failed", "reason": "Missing @context or @type.", "attempts": 1}

    needs_from_owner = set(fix.get("needs_from_owner") or [])
    for field in REQUIRED_FIELDS:
        if not schema.get(field) and field not in needs_from_owner:
            return {
                "status": "failed",
                "reason": f"'{field}' is neither present nor listed in needs_from_owner.",
                "attempts": 1,
            }

    return {"status": "passed", "reason": "", "attempts": 1}


def _verify_content_clarity_fix(fix):
    before_result = check_content_clarity({"text": fix.get("before") or ""})
    after_result = check_content_clarity({"text": fix.get("content") or ""})
    before_score = before_result.get("score")
    after_score = after_result.get("score")

    if before_score is None or after_score is None:
        # check_content_clarity couldn't produce a score at all (API
        # error, rate limit, no text) — that's not a verdict on the fix,
        # so this is "unavailable", not "failed".
        reason = before_result.get("skipped") or after_result.get("skipped") or "Content Clarity check unavailable"
        return {"status": "unavailable", "reason": reason, "attempts": 1}

    if after_score - before_score >= CLARITY_MIN_IMPROVEMENT:
        return {"status": "passed", "reason": "", "attempts": 1}

    return {
        "status": "failed",
        "reason": f"Score only improved from {before_score} to {after_score} (need +{CLARITY_MIN_IMPROVEMENT}).",
        "attempts": 1,
    }


def verify_fix(finding, fix):
    """Returns {"status": "passed" | "failed" | "unavailable", "reason":
    str, "attempts": int}. "failed" means the check ran and the fix
    didn't meet the bar — worth retrying. "unavailable" means the check
    itself couldn't run — retrying would risk discarding a perfectly
    good fix and burns another API call for nothing, so callers should
    not retry on it."""
    category = finding.get("category")
    if category == "structured_data":
        return _verify_structured_data_fix(fix)
    if category == "content_clarity":
        return _verify_content_clarity_fix(fix)
    return {"status": "unavailable", "reason": "needs_human", "attempts": 0}


def generate_verified_fix(finding, business_id):
    """Generate a fix, verify it, and for content_clarity retry the
    generation once more if it genuinely failed (max 2 attempts total)
    — never retry on "unavailable", since that isn't a verdict on the
    fix — then persist both to the fixes table. This is what app.py's
    route calls."""
    fix = generate_fix(finding, business_id)
    verification = verify_fix(finding, fix)

    if finding.get("category") == "content_clarity":
        attempts = 1
        while verification["status"] == "failed" and attempts < MAX_CLARITY_ATTEMPTS:
            fix = generate_fix(finding, business_id, retry_reason=verification["reason"])
            verification = verify_fix(finding, fix)
            attempts += 1
        verification["attempts"] = attempts

    verified = verification["status"] == "passed"
    create_fix(finding["id"], fix["fix_type"], fix["content"], verified, verification["attempts"])
    return {**fix, **verification, "verified": verified}
