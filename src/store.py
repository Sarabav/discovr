"""Dispatches every persistence call to either src.db (local SQLite,
default) or src.supabase_store (Supabase), based on the admin page's
data-source dropdown (src.data_source). Callers import from here
instead of src.db directly, so switching the dropdown changes where
reads and writes go without restarting the app.

init_db and new_id stay imported from src.db directly wherever they're
used: local SQLite setup is unconditional (the fallback always has to
exist), and id generation is backend-agnostic.
"""

from src import db as _local
from src import supabase_store as _supabase
from src.data_source import get_data_source


def _backend():
    return _supabase if get_data_source() == "supabase" else _local


def create_user(email, password_hash):
    return _backend().create_user(email, password_hash)


def get_user_by_email(email):
    return _backend().get_user_by_email(email)


def set_admin(email, is_admin=True):
    return _backend().set_admin(email, is_admin)


def set_password(email, password_hash):
    return _backend().set_password(email, password_hash)


def get_business(business_id):
    return _backend().get_business(business_id)


def get_business_for_user(user_id):
    return _backend().get_business_for_user(user_id)


def update_business_website(business_id, website_url):
    return _backend().update_business_website(business_id, website_url)


def create_business(user_id, name, website_url):
    return _backend().create_business(user_id, name, website_url)


def create_snapshot(business_id, website_text, website_schema_json):
    return _backend().create_snapshot(business_id, website_text, website_schema_json)


def get_snapshot(snapshot_id):
    return _backend().get_snapshot(snapshot_id)


def create_analysis(business_id, snapshot_id, overall_score, category_scores, skipped=None):
    return _backend().create_analysis(business_id, snapshot_id, overall_score, category_scores, skipped)


def get_analysis(analysis_id):
    return _backend().get_analysis(analysis_id)


def get_latest_analysis(business_id):
    return _backend().get_latest_analysis(business_id)


def get_analyses_for_business(business_id):
    return _backend().get_analyses_for_business(business_id)


def create_finding(analysis_id, finding):
    return _backend().create_finding(analysis_id, finding)


def update_finding_status(finding_id, status):
    return _backend().update_finding_status(finding_id, status)


def get_finding(finding_id):
    return _backend().get_finding(finding_id)


def get_findings(analysis_id):
    return _backend().get_findings(analysis_id)


def create_fix(finding_id, fix_type, content, verified, attempts, run_id=None):
    return _backend().create_fix(finding_id, fix_type, content, verified, attempts, run_id)


def get_fixes_for_run(run_id):
    return _backend().get_fixes_for_run(run_id)


def create_agent_run(
    run_id, business_id, stage, status, message=None, analysis_id=None, step_number=None, input_summary=None
):
    return _backend().create_agent_run(
        run_id, business_id, stage, status, message, analysis_id, step_number, input_summary
    )


def get_agent_runs(run_id):
    return _backend().get_agent_runs(run_id)
