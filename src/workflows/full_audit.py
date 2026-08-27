"""The real AI-visibility audit pipeline: scrape -> score -> rank -> save.

Called from a background thread kicked off by the chat route (app.py).
Writes a row to agent_runs at the start and end of each stage so
GET /runs/<run_id> can show live progress. Never swallows a failure: a
stage that errors logs it to agent_runs and raises, so the run's final
status is "error" with the real message, not a silent fallback.
"""

import json

from src.components.find_mentions import city_from_address, find_mentions
from src.components.scrape_website import check_crawler_access, scrape_website
from src.store import create_agent_run, create_snapshot, get_business
from src.rag import ingest_business
from src.scoring import rank_findings, run_all_checks, save_analysis


class AuditError(Exception):
    pass


def _log(run_id, business_id, stage, status, message=None, analysis_id=None):
    create_agent_run(run_id, business_id, stage, status, message, analysis_id)


def run_audit(business_id, run_id):
    business = get_business(business_id)
    url = business["website_url"] if business else None
    if not url:
        raise AuditError("This business has no website URL yet.")

    _log(run_id, business_id, "scraping", "running")
    scrape = scrape_website(url)
    robots = check_crawler_access(url)
    if scrape.get("error"):
        _log(run_id, business_id, "scraping", "error", scrape["error"])
        raise AuditError(scrape["error"])
    snapshot = {**scrape, "robots": robots}
    nap = snapshot.get("nap") or {}
    business_name = nap.get("name") or snapshot.get("title")
    snapshot["mentions"] = find_mentions(business_name, city_from_address(nap.get("address")))
    snapshot_id = create_snapshot(
        business_id, snapshot.get("text", ""), json.dumps(snapshot.get("schema", []))
    )
    _log(run_id, business_id, "scraping", "done")

    _log(run_id, business_id, "ingesting", "running")
    chunk_count = ingest_business(business_id, snapshot)
    _log(run_id, business_id, "ingesting", "done", message=f"Indexed {chunk_count} chunks")

    _log(run_id, business_id, "scoring", "running")
    results = run_all_checks(snapshot)
    _log(run_id, business_id, "scoring", "done")

    _log(run_id, business_id, "ranking", "running")
    results["findings"] = rank_findings(results["findings"], snapshot)
    _log(run_id, business_id, "ranking", "done")

    _log(run_id, business_id, "saving", "running")
    analysis_id = save_analysis(business_id, snapshot_id, results)
    _log(run_id, business_id, "saving", "done", analysis_id=analysis_id)

    return {"analysis_id": analysis_id, **results}
