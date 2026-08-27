"""Business Website component: fetches a business's website and extracts
what an AI system would actually see (visible text, JSON-LD structured
data, NAP details) plus which AI crawlers its robots.txt allows.

Most sites are plain HTML and a fast `requests` GET is enough. Some are
JavaScript-rendered single-page apps that return an near-empty shell to
a plain GET (no text, no links, no schema); those get a fallback fetch
through headless Chromium (Playwright), which actually runs the page's
JS before we read its HTML. Which path was used is reported back via
"render_method" ("requests" or "playwright").

Never raises: every failure is reported in the returned dict's "error"
field instead, so callers (the component page, the CLI) don't need to
wrap calls in try/except.
"""

import json
import re
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; DiscovrBot/1.0; +https://discovr.example.com/bot)"
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT_SECONDS = 10
PLAYWRIGHT_TIMEOUT_MS = 20000
MAX_INTERNAL_PAGES = 3
INTERNAL_LINK_PATHS = ("/about", "/services", "/contact", "/faq")
CRAWLER_BOTS = ["GPTBot", "ClaudeBot", "PerplexityBot", "CCBot", "Google-Extended", "anthropic-ai"]

EMPTY_TEXT_THRESHOLD = 500
EMPTY_LINK_THRESHOLD = 3

# Phone: optional +1, optional parens/dots/dashes/spaces around the groups.
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")

STREET_TYPES = r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Way|Dr|Drive|Ln|Lane|Ct|Court)"
# Street address, optionally followed by a city/province-or-state/postal tail
# (accepts both "City, ST 12345" and "City, PR A1A 1A1" shaped tails).
ADDRESS_FULL_RE = re.compile(
    rf"\d{{1,6}}\s+[A-Za-z0-9.\s]{{2,40}}\b{STREET_TYPES}\b\.?,?"
    r"\s+[A-Za-z][A-Za-z.\s]{1,30},?\s+[A-Za-z]{2,3}[,\s]+[A-Za-z0-9]{3}[\s-]?[A-Za-z0-9]{0,4}",
    re.IGNORECASE,
)
ADDRESS_STREET_RE = re.compile(
    rf"\d{{1,6}}\s+[A-Za-z0-9.\s]{{2,40}}\b{STREET_TYPES}\b\.?",
    re.IGNORECASE,
)


def _fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response


def _fetch_with_playwright(url):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT_MS)
            html = page.content()
            final_url = page.url
        finally:
            browser.close()
    return html, final_url


def _crawl_with_playwright(url):
    """Render `url` with headless Chromium, re-extract internal links from
    the *rendered* page (not the original empty HTML), then follow up to
    MAX_INTERNAL_PAGES of them with the same browser instance, since a
    JS-rendered site's internal pages are JS-rendered too.

    Returns (pages, unreachable_pages). `pages` is a list of
    (final_url, parsed) tuples, main page first. `unreachable_pages` is a
    list of {"url", "status"} for any internal link that itself failed
    (SPA routes are only virtual client-side unless the host has a
    catch-all rewrite to index.html) — a page unreachable by direct
    navigation is invisible to AI crawlers even if a human can click
    through to it, which is worth surfacing rather than hiding."""
    from playwright.sync_api import sync_playwright

    pages = []
    unreachable_pages = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)

            page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT_MS)
            main_html = page.content()
            main_final_url = page.url
            main_parsed = _parse_html(main_html, main_final_url)
            pages.append((main_final_url, main_parsed))

            for link in main_parsed["internal_links"]:
                try:
                    response = page.goto(link, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT_MS)
                except Exception as error:
                    print(f"Playwright navigation failed for {link}: {error}", file=sys.stderr)
                    unreachable_pages.append({"url": link, "status": None})
                    continue
                if response is None or response.status >= 400:
                    unreachable_pages.append(
                        {"url": link, "status": response.status if response else None}
                    )
                    continue
                pages.append((page.url, _parse_html(page.content(), page.url)))
        finally:
            browser.close()

    return pages, unreachable_pages


def _clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _extract_text(soup):
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    return _clean_text(soup.get_text(separator=" "))


def _extract_schema(soup):
    schema = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue  # malformed JSON-LD is skipped, not fatal
        if isinstance(data, list):
            schema.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            schema.append(data)
    return schema


def _all_links(soup, base_url):
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#")[0]
        if href not in links:
            links.append(href)
    return links


def _filter_internal_links(all_links, base_url):
    base_host = urlparse(base_url).netloc
    matches = []
    for href in all_links:
        parsed = urlparse(href)
        if parsed.netloc != base_host:
            continue
        path = parsed.path.lower().rstrip("/")
        if any(path == p or path.endswith(p) for p in INTERNAL_LINK_PATHS):
            matches.append(href)
        if len(matches) >= MAX_INTERNAL_PAGES:
            break
    return matches[:MAX_INTERNAL_PAGES]


def _phone_from_tel_links(soup):
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("tel:"):
            number = href[4:].strip()
            if number:
                return number
    return None


def _phone_from_text(text):
    match = PHONE_RE.search(text or "")
    return match.group(0).strip() if match else None


def _address_from_tag(soup):
    address_tag = soup.find("address")
    if address_tag:
        text = _clean_text(address_tag.get_text(separator=" "))
        if text:
            return text

    itemprop_el = soup.find(attrs={"itemprop": re.compile(r"address", re.I)})
    if itemprop_el:
        text = _clean_text(itemprop_el.get_text(separator=" "))
        if text:
            return text

    return None


def _address_from_text(text):
    if not text:
        return None
    match = ADDRESS_FULL_RE.search(text) or ADDRESS_STREET_RE.search(text)
    return match.group(0).strip() if match else None


def _name_from_og(soup):
    meta = soup.find("meta", attrs={"property": "og:site_name"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    return None


def _name_from_title(title):
    if not title:
        return None
    for separator in (" | ", " – ", " — ", " - "):
        if separator in title:
            return title.split(separator)[0].strip()
    return title.strip()


def _name_from_logo(soup):
    logo = soup.find("img", alt=re.compile(r"logo", re.I))
    if logo and logo.get("alt"):
        alt = logo["alt"].strip()
        cleaned = re.sub(r"\blogo\b", "", alt, flags=re.I).strip(" -|")
        return cleaned or alt
    return None


def _extract_name(soup, title):
    return _name_from_og(soup) or _name_from_title(title) or _name_from_logo(soup)


def _nap_from_schema(schema):
    for item in schema:
        name = item.get("name")
        phone = item.get("telephone")
        address = item.get("address")
        if isinstance(address, dict):
            parts = [
                address.get("streetAddress"),
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("postalCode"),
            ]
            address = ", ".join(p for p in parts if p) or None
        elif not isinstance(address, str):
            address = None
        if name or phone or address:
            return {"name": name, "phone": phone, "address": address}
    return None


def _parse_html(html, base_url):
    """Parse raw HTML into a page dict. Runs the same way regardless of
    whether the HTML came from `requests` or Playwright."""
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else None
    meta = soup.find("meta", attrs={"name": "description"})
    meta_description = meta["content"].strip() if meta and meta.get("content") else None

    schema = _extract_schema(soup)
    all_links = _all_links(soup, base_url)
    internal_links = _filter_internal_links(all_links, base_url)

    footer_tag = soup.find("footer")
    footer_text = _clean_text(footer_tag.get_text(separator=" ")) if footer_tag else ""

    tel_phone = _phone_from_tel_links(soup)
    address_tag_text = _address_from_tag(soup)
    name_hint = _extract_name(soup, title)

    text = _extract_text(soup)  # mutates soup: decomposes script/style/nav/footer

    return {
        "title": title,
        "meta_description": meta_description,
        "schema": schema,
        "text": text,
        "footer_text": footer_text,
        "all_links": all_links,
        "internal_links": internal_links,
        "tel_phone": tel_phone,
        "address_tag_text": address_tag_text,
        "name_hint": name_hint,
    }


def _looks_empty(parsed):
    return (
        len(parsed["text"]) < EMPTY_TEXT_THRESHOLD
        or len(parsed["all_links"]) < EMPTY_LINK_THRESHOLD
        or not parsed["schema"]
    )


def _fetch_and_parse(url):
    """Fetch `url` with `requests`; if the result looks like a
    JS-rendered empty shell, re-fetch with headless Chromium instead.
    Returns (parsed_or_None, final_url_or_None, render_method, error_or_None, status_or_None).
    `status` is only set when `error` is a 4xx/5xx HTTP response."""
    try:
        response = _fetch(url)
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else None
        return None, None, "requests", f"Could not fetch {url}: {error}", status
    except requests.RequestException as error:
        return None, None, "requests", f"Could not fetch {url}: {error}", None

    parsed = _parse_html(response.text, response.url)

    if _looks_empty(parsed):
        try:
            html, final_url = _fetch_with_playwright(url)
        except Exception as error:
            print(f"Playwright fallback failed for {url}: {error}", file=sys.stderr)
            return parsed, response.url, "requests", None, None
        return _parse_html(html, final_url), final_url, "playwright", None, None

    return parsed, response.url, "requests", None, None


def _build_nap(pages, schema_all):
    schema_nap = _nap_from_schema(schema_all) or {}
    phone = schema_nap.get("phone")
    address = schema_nap.get("address")
    name = schema_nap.get("name")

    for page in pages:
        if not phone:
            phone = (
                page["tel_phone"]
                or _phone_from_text(page["footer_text"])
                or _phone_from_text(page["text"])
            )
        if not address:
            address = (
                page["address_tag_text"]
                or _address_from_text(page["footer_text"])
                or _address_from_text(page["text"])
            )
        if not name:
            name = page["name_hint"]
        if phone and address and name:
            break

    return {"name": name, "phone": phone, "address": address}


def scrape_website(url):
    """Fetch `url` (plus up to 3 likely internal pages) and extract what
    an AI system would see. Returns a dict; never raises."""
    result = {
        "url": url,
        "final_url": None,
        "title": None,
        "meta_description": None,
        "text": "",
        "schema": [],
        "pages_crawled": [],
        "unreachable_pages": [],
        "nap": {"name": None, "phone": None, "address": None},
        "render_method": None,
        "error": None,
    }

    try:
        response = _fetch(url)
    except requests.RequestException as error:
        result["error"] = f"Could not fetch {url}: {error}"
        return result

    main_parsed = _parse_html(response.text, response.url)
    unreachable_pages = []

    if _looks_empty(main_parsed):
        try:
            pages, unreachable_pages = _crawl_with_playwright(url)
            render_method = "playwright"
        except Exception as error:
            print(f"Playwright fallback failed for {url}: {error}", file=sys.stderr)
            pages = [(response.url, main_parsed)]
            render_method = "requests"
    else:
        pages = [(response.url, main_parsed)]
        render_method = "requests"
        for link in main_parsed["internal_links"]:
            sub_parsed, sub_final_url, _, sub_error, sub_status = _fetch_and_parse(link)
            if sub_error or sub_parsed is None:
                unreachable_pages.append({"url": link, "status": sub_status})
                continue
            pages.append((sub_final_url, sub_parsed))

    result["render_method"] = render_method
    result["unreachable_pages"] = unreachable_pages
    result["pages_crawled"] = [page_url for page_url, _ in pages]
    result["final_url"] = pages[0][0]
    result["title"] = pages[0][1]["title"]
    result["meta_description"] = pages[0][1]["meta_description"]

    parsed_pages = [parsed for _, parsed in pages]
    schema_all = [item for parsed in parsed_pages for item in parsed["schema"]]

    result["schema"] = schema_all
    # Each page's text is already whitespace-collapsed to one line (see
    # _extract_text); joining pages with a blank line (rather than a
    # single space) keeps them as separate paragraphs, so a downstream
    # chunker (src/rag.py) can split per-page instead of treating a
    # multi-page crawl as one giant atomic paragraph.
    result["text"] = "\n\n".join(parsed["text"] for parsed in parsed_pages if parsed["text"])
    result["nap"] = _build_nap(parsed_pages, schema_all)
    # Per-page breakdown of how much visible text each crawled page
    # contributed, since result["text"] merges them all into one blob —
    # useful for diagnosing why a particular page's content did or
    # didn't make it into the combined text.
    result["page_text_lengths"] = {
        page_url: len(parsed["text"]) for page_url, parsed in pages
    }

    return result


def _parse_robots_groups(robots_text):
    """Return [(set_of_lowercase_agents, [disallow_paths]), ...] groups,
    following robots.txt's rule that consecutive User-agent lines share a
    group, and the first non-user-agent directive closes it."""
    groups = []
    current_agents = []
    current_rules = []
    started_rules = False

    def flush():
        if current_agents:
            groups.append((set(current_agents), list(current_rules)))

    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()

        if field == "user-agent":
            if started_rules:
                flush()
                current_agents = []
                current_rules = []
                started_rules = False
            current_agents.append(value.lower())
        elif field == "disallow":
            current_rules.append(value)
            started_rules = True

    flush()
    return groups


def _is_bot_disallowed(groups, bot_name):
    bot_lower = bot_name.lower()

    for agents, rules in groups:
        if bot_lower in agents:
            return any(rule == "/" for rule in rules)

    for agents, rules in groups:
        if "*" in agents:
            return any(rule == "/" for rule in rules)

    return False  # no matching group in robots.txt => not disallowed


def check_crawler_access(url):
    """Fetch /robots.txt for `url`'s host and report which AI crawlers
    are disallowed. Returns a dict; never raises."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    result = {"url": url, "robots_url": robots_url, "bots": {}, "robots_txt": None, "error": None}

    try:
        response = requests.get(robots_url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as error:
        result["error"] = f"Could not fetch {robots_url}: {error}"
        result["bots"] = {bot: None for bot in CRAWLER_BOTS}
        return result

    if response.status_code >= 400:
        result["robots_txt"] = ""
        result["bots"] = {bot: False for bot in CRAWLER_BOTS}
        return result

    result["robots_txt"] = response.text
    groups = _parse_robots_groups(response.text)
    result["bots"] = {bot: _is_bot_disallowed(groups, bot) for bot in CRAWLER_BOTS}
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.components.scrape_website <url>")
        sys.exit(1)

    target_url = sys.argv[1]

    print(f"Scraping {target_url} ...\n")
    print(json.dumps(scrape_website(target_url), indent=2))

    print(f"\nChecking crawler access for {target_url} ...\n")
    print(json.dumps(check_crawler_access(target_url), indent=2))
