"""The agent loop: a LangGraph state machine that decides for itself what
finding to work on, generates or plans a fix for it, checks its own
output, and decides whether to continue.

Everything it calls already exists — src.workflows.full_audit produced
the findings, src.checkers/src.clarity produced the categories,
src.components.fix_generator generates and verifies fixes. This module
only wires them into a loop and logs every decision to agent_runs so a
user watching the chat sees the agent's actual reasoning, not just a
progress bar.

SUGGEST -> PLAN -> EXECUTE -> MONITOR -> SUGGEST | END
PLAN routes straight back to SUGGEST for instruction-type findings
(nothing to verify automatically), skipping EXECUTE/MONITOR entirely.
"""

import copy
import json
import operator
import re
import sys
from typing import Annotated, Optional, TypedDict

from langgraph.graph import END, StateGraph

from src.agents import ask_structured, strip_code_fence
from src.checkers import LOCAL_BUSINESS_TYPES
from src.components.fix_generator import generate_fix, verify_fix
from src.store import (
    create_agent_run,
    create_fix,
    get_findings,
    get_latest_analysis,
    get_snapshot,
    update_finding_status,
)
from src.rag import retrieve
from src.scoring import run_all_checks

MAX_NODE_EXECUTIONS = 15
MAX_FIX_ATTEMPTS = 2
MAX_FINDINGS_HANDLED = 6

# category -> fix_type, the PLAN node's whole job. "mentions" has no fix
# generator (see fix_generator.generate_fix) so it's simply never chosen.
FIXABLE_CATEGORIES = {
    "structured_data": "generated",
    "content_clarity": "generated",
    "crawler_access": "instruction",
    "nap_consistency": "instruction",
}

CATEGORY_LABELS = {
    "nap_consistency": "NAP Consistency",
    "structured_data": "Structured Data",
    "content_clarity": "Content Clarity",
    "crawler_access": "Crawler Access",
    "mentions": "Mentions",
}

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


class AgentState(TypedDict):
    business_id: str
    run_id: str
    snapshot: dict
    findings: list
    current_finding: Optional[dict]
    attempts: int
    resolved: Annotated[list, operator.add]
    needs_human: Annotated[list, operator.add]
    failed: Annotated[list, operator.add]
    applied_fixes: Annotated[list, operator.add]
    step_log: Annotated[list, operator.add]
    step_number: int
    findings_handled: int
    last_fix: Optional[dict]
    last_verify_reason: Optional[str]
    done: bool
    done_reason: Optional[str]


class AgentLoopError(Exception):
    pass


def _load_initial_state(business_id, run_id):
    analysis = get_latest_analysis(business_id)
    if analysis is None:
        raise AgentLoopError("This business has no analysis yet — run an audit first.")

    findings = [dict(row) for row in get_findings(analysis["id"])]
    for finding in findings:
        finding["missing"] = json.loads(finding.get("missing_json") or "[]")
    snapshot_row = get_snapshot(analysis["snapshot_id"])
    snapshot = {
        "text": snapshot_row["website_text"] if snapshot_row else "",
        "schema": json.loads(snapshot_row["website_schema_json"] or "[]") if snapshot_row else [],
    }

    return AgentState(
        business_id=business_id,
        run_id=run_id,
        snapshot=snapshot,
        findings=findings,
        current_finding=None,
        attempts=0,
        resolved=[],
        needs_human=[],
        failed=[],
        applied_fixes=[],
        step_log=[],
        step_number=0,
        findings_handled=0,
        last_fix=None,
        last_verify_reason=None,
        done=False,
        done_reason=None,
    )


def _log(state, node, input_summary, decision, why=""):
    """Every node calls this before returning: step_number, node name,
    what it saw, what it decided, and why — persisted to agent_runs so
    the chat's live step view can show the agent's actual reasoning."""
    step_number = state["step_number"] + 1
    message = f"{decision} — {why}" if why else decision
    create_agent_run(
        state["run_id"], state["business_id"], node, "done",
        message=message, step_number=step_number, input_summary=input_summary,
    )
    entry = {
        "step_number": step_number,
        "node": node,
        "input": input_summary,
        "decision": decision,
        "why": why,
    }
    return step_number, entry


def _set_status(findings, finding_id, status):
    return [{**f, "status": status} if f["id"] == finding_id else f for f in findings]


def _finalize_finding(findings, finding_id, status):
    update_finding_status(finding_id, status)
    return _set_status(findings, finding_id, status)


def _check_node_limit(state):
    if state["step_number"] >= MAX_NODE_EXECUTIONS:
        return f"max node executions ({MAX_NODE_EXECUTIONS}) reached"
    return None


# ---------- SUGGEST ----------


def _rank_and_choose(open_findings, tips_text):
    numbered = "\n".join(
        f"{i}. [{f['category']}] {f['title']} (priority: {f['priority']}): {f['description']}"
        for i, f in enumerate(open_findings)
    )
    system = (
        "You choose which AI-visibility finding to fix next for this business, "
        "ranked by real impact. Crawler Access findings always outrank everything "
        "else, since a fix to schema or copy does nothing on a page a crawler "
        "can't fetch.\n\n"
        f"Guidance from the AI-visibility playbook:\n{tips_text}\n\n"
        "Respond with ONLY a single JSON object, no markdown fence, shaped exactly:\n"
        '{"chosen_index": <int, the index above of the single finding to work on '
        'next>, "reason": "<one sentence explaining the choice>"}'
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Open findings:\n{numbered}"},
    ]
    try:
        result = ask_structured(messages, temperature=0)
        parsed = json.loads(strip_code_fence(result["content"]))
        index = parsed.get("chosen_index")
        reason = parsed.get("reason") or ""
        if isinstance(index, int) and 0 <= index < len(open_findings):
            return index, reason
        failure = f"model returned an out-of-range or non-integer chosen_index: {parsed!r}"
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"

    print(f"SUGGEST ranking LLM call failed, falling back to priority order: {failure}", file=sys.stderr)
    # Never raise: fall back to priority order, matching the rest of the
    # codebase's "never raise" contract (see src.scoring.rank_findings).
    fallback_index = min(
        range(len(open_findings)), key=lambda i: PRIORITY_ORDER.get(open_findings[i]["priority"], 3)
    )
    return fallback_index, f"LLM ranking unavailable ({failure}), falling back to priority order"


def suggest_node(state):
    node_limit = _check_node_limit(state)
    if node_limit:
        step_number, entry = _log(state, "suggest", "-", "stopping", node_limit)
        return {"done": True, "done_reason": node_limit, "step_number": step_number, "step_log": [entry]}

    open_findings = [
        f for f in state["findings"] if f["status"] == "open" and f["category"] in FIXABLE_CATEGORIES
    ]

    if not open_findings:
        step_number, entry = _log(state, "suggest", "0 fixable findings open", "stopping", "all findings handled")
        return {"done": True, "done_reason": "all findings handled", "step_number": step_number, "step_log": [entry]}

    if state["findings_handled"] >= MAX_FINDINGS_HANDLED:
        reason = f"max findings handled ({MAX_FINDINGS_HANDLED}) reached"
        step_number, entry = _log(state, "suggest", f"{len(open_findings)} findings open", "stopping", reason)
        return {"done": True, "done_reason": reason, "step_number": step_number, "step_log": [entry]}

    tips = retrieve("Tips for Fixing Common AI Visibility Issues", top_k=3)
    tips_text = "\n\n".join(s["text"] for s in tips)
    chosen_index, reason = _rank_and_choose(open_findings, tips_text)
    chosen = open_findings[chosen_index]

    # Hard rule, enforced in code rather than trusted to the model alone
    # (same "never trust the model alone" pattern as fix_generator's
    # structured-data safety net): Crawler Access outranks everything.
    crawler_findings = [f for f in open_findings if f["category"] == "crawler_access"]
    if crawler_findings and chosen["category"] != "crawler_access":
        chosen = crawler_findings[0]
        reason = (
            "overridden: Crawler Access outranks everything else — a fix to schema "
            "or copy does nothing on a page a crawler can't fetch"
        )

    input_summary = f"{len(open_findings)} findings open"
    decision = f"choosing '{chosen['title']}'"
    step_number, entry = _log(state, "suggest", input_summary, decision, reason)

    return {
        "current_finding": chosen,
        "attempts": 0,
        "last_verify_reason": None,
        "last_fix": None,
        "step_number": step_number,
        "step_log": [entry],
    }


# ---------- PLAN ----------


def plan_node(state):
    finding = state["current_finding"]
    node_limit = _check_node_limit(state)
    if node_limit:
        step_number, entry = _log(state, "plan", finding["title"], "stopping", node_limit)
        return {"done": True, "done_reason": node_limit, "step_number": step_number, "step_log": [entry]}

    fix_type = FIXABLE_CATEGORIES[finding["category"]]

    if fix_type == "generated":
        step_number, entry = _log(
            state, "plan", finding["title"],
            f"fix_type=generated (category={finding['category']})", "routing to EXECUTE",
        )
        return {"step_number": step_number, "step_log": [entry]}

    # instruction: deterministic, nothing to verify automatically —
    # generate once here and skip EXECUTE/MONITOR entirely.
    fix = generate_fix(finding, state["business_id"])
    create_fix(finding["id"], fix["fix_type"], fix["content"], False, 1, state["run_id"])
    updated_findings = _finalize_finding(state["findings"], finding["id"], "needs_human")

    step_number, entry = _log(
        state, "plan", finding["title"],
        f"fix_type=instruction (category={finding['category']})",
        "generated steps once, marked needs_human",
    )
    return {
        "findings": updated_findings,
        "needs_human": [finding["id"]],
        "findings_handled": state["findings_handled"] + 1,
        "current_finding": None,
        "last_fix": fix,
        "step_number": step_number,
        "step_log": [entry],
    }


# ---------- EXECUTE ----------


def execute_node(state):
    finding = state["current_finding"]
    node_limit = _check_node_limit(state)
    if node_limit:
        step_number, entry = _log(state, "execute", finding["title"], "stopping", node_limit)
        return {"done": True, "done_reason": node_limit, "step_number": step_number, "step_log": [entry]}

    attempt_number = state["attempts"] + 1
    fix = generate_fix(finding, state["business_id"], retry_reason=state.get("last_verify_reason"))
    create_fix(finding["id"], fix["fix_type"], fix["content"], False, attempt_number, state["run_id"])

    owner_note = f", {len(fix['needs_from_owner'])} field(s) need the owner" if fix.get("needs_from_owner") else ""
    input_summary = f"finding '{finding['title']}', attempt {attempt_number}"
    decision = f"generated {finding['category']} fix{owner_note}"
    step_number, entry = _log(state, "execute", input_summary, decision)

    return {
        "attempts": attempt_number,
        "last_fix": fix,
        "step_number": step_number,
        "step_log": [entry],
    }


# ---------- MONITOR ----------


def monitor_node(state):
    finding = state["current_finding"]
    node_limit = _check_node_limit(state)
    if node_limit:
        step_number, entry = _log(state, "monitor", finding["title"], "stopping", node_limit)
        return {"done": True, "done_reason": node_limit, "step_number": step_number, "step_log": [entry]}

    fix = state["last_fix"]
    verification = verify_fix(finding, fix)
    status = verification["status"]
    input_summary = f"finding '{finding['title']}', attempt {state['attempts']}"

    if status == "passed":
        updated_findings = _finalize_finding(state["findings"], finding["id"], "resolved")
        step_number, entry = _log(state, "monitor", input_summary, "passed", "resolved")
        return {
            "findings": updated_findings,
            "resolved": [finding["id"]],
            "applied_fixes": [{"finding": finding, "fix": fix}],
            "findings_handled": state["findings_handled"] + 1,
            "current_finding": None,
            "attempts": 0,
            "last_fix": None,
            "last_verify_reason": None,
            "step_number": step_number,
            "step_log": [entry],
        }

    if status == "unavailable":
        # The check itself couldn't run (API error, rate limit) — not a
        # verdict on the fix. Retrying would risk discarding a perfectly
        # good fix and burns another API call for nothing, so this goes
        # to a human instead of back through EXECUTE, unlike a real failure.
        updated_findings = _finalize_finding(state["findings"], finding["id"], "needs_human")
        step_number, entry = _log(
            state, "monitor", input_summary,
            f"couldn't verify — {verification['reason']}", "marking needs_human, not retrying",
        )
        return {
            "findings": updated_findings,
            "needs_human": [finding["id"]],
            "findings_handled": state["findings_handled"] + 1,
            "current_finding": None,
            "attempts": 0,
            "last_fix": None,
            "last_verify_reason": None,
            "step_number": step_number,
            "step_log": [entry],
        }

    # status == "failed": the check ran and the fix didn't meet the bar.
    if state["attempts"] < MAX_FIX_ATTEMPTS:
        step_number, entry = _log(state, "monitor", input_summary, "failed, retrying", verification["reason"])
        return {"last_verify_reason": verification["reason"], "step_number": step_number, "step_log": [entry]}

    updated_findings = _finalize_finding(state["findings"], finding["id"], "failed")
    step_number, entry = _log(
        state, "monitor", input_summary, "failed after max attempts",
        f"marking failed — {verification['reason']}",
    )
    return {
        "findings": updated_findings,
        "failed": [finding["id"]],
        "findings_handled": state["findings_handled"] + 1,
        "current_finding": None,
        "attempts": 0,
        "last_fix": None,
        "last_verify_reason": None,
        "step_number": step_number,
        "step_log": [entry],
    }


# ---------- routing ----------


def _route_after_suggest(state):
    return "end" if state["done"] else "plan"


def _route_after_plan(state):
    if state["done"]:
        return "end"
    return "execute" if state["current_finding"] is not None else "suggest"


def _route_after_execute(state):
    return "end" if state["done"] else "monitor"


def _route_after_monitor(state):
    if state["done"]:
        return "end"
    return "execute" if state["current_finding"] is not None else "suggest"


# ---------- score projection ----------

# input_summary markers for the two projection rows logged at the end of a
# run — used by app.py to find them among the ordinary per-finding steps.
PROJECTION_MARKER = "generated fix(es) applied to a snapshot copy"
BLOCKERS_MARKER = "what's still holding the score back"

FILL_IN_PATTERN = re.compile(r'FILL IN: ([^"\\\n]+)')


def _is_business_schema_node(item):
    if not isinstance(item, dict):
        return False
    item_type = item.get("@type")
    types = item_type if isinstance(item_type, list) else [item_type]
    return any(t in LOCAL_BUSINESS_TYPES for t in types if t)


def _apply_fixes_to_snapshot(snapshot, applied_fixes):
    """A copy of `snapshot` with each applied (generated + verified)
    fix's effect actually substituted in — the new schema block
    replacing whatever business node was there, the rewritten passage
    replacing the weak one — so re-running the checkers against it
    measures the real effect of the agent's own work, not just that its
    output parsed. Instruction-type fixes (crawler_access,
    nap_consistency) are never in applied_fixes — they need a human, so
    nothing was actually applied for them to credit."""
    projected = copy.deepcopy(snapshot)

    for entry in applied_fixes:
        finding, fix = entry["finding"], entry["fix"]
        if finding["category"] == "structured_data":
            try:
                new_block = json.loads(fix["content"])
            except (ValueError, TypeError):
                continue
            schema = [item for item in (projected.get("schema") or []) if not _is_business_schema_node(item)]
            schema.append(new_block)
            projected["schema"] = schema
        elif finding["category"] == "content_clarity":
            before = finding.get("worst_passage") or ""
            after = fix.get("content") or ""
            text = projected.get("text") or ""
            if before and before in text:
                projected["text"] = text.replace(before, after, 1)

    return projected


def _fill_in_fields(applied_fixes):
    """Fields the fix generator could not invent and stubbed with a
    literal "FILL IN: ..." marker (see src.components.fix_generator) —
    these stay in an already-"resolved" generated fix and are the
    owner's next real step, so surface them by description rather than
    letting a resolved status read as fully done."""
    fields = []
    for entry in applied_fixes:
        content = entry["fix"].get("content") or ""
        for match in FILL_IN_PATTERN.finditer(content):
            description = match.group(1).strip()
            if description not in fields:
                fields.append(description)
    return fields


def _open_instruction_findings(findings):
    """Instruction-type findings (crawler_access, nap_consistency) are
    never auto-fixed — PLAN marks them needs_human immediately. These
    are the "manual steps" a human still owes."""
    return [f for f in findings if f["fix_type"] == "instruction" and f["status"] != "resolved"]


def _log_score_projection(final_state, business_id):
    """Logs two things as MONITOR steps so the chat can show the agent
    measuring the effect of its own work, not just that its output
    parsed, and so there's always a next step instead of a dead end:

    1. Two projections, not one — the current score only ever showing
       the ceiling of what the agent generated makes the ceiling look
       artificially low, since instruction-type findings (crawler
       blocks, hosting config, Google listing changes) never appear in
       it. So: current -> with the agent's own generated fixes applied
       -> with the manual steps also done. The first jump is re-derived
       by re-running the checkers against a snapshot with those fixes
       actually substituted in (see _apply_fixes_to_snapshot); the
       second assumes every open instruction-type finding gets
       resolved, since there's no snapshot data to re-check crawler
       access or NAP against (robots.txt and Places data aren't
       persisted).
    2. What still holds the score back after both: FILL IN fields the
       owner has to supply even inside a "resolved" generated fix, and
       categories that were never measured at all (skipped_json)."""
    applied_fixes = final_state.get("applied_fixes") or []
    manual_findings = _open_instruction_findings(final_state["findings"])
    if not applied_fixes and not manual_findings:
        return

    analysis = get_latest_analysis(business_id)
    if analysis is None:
        return

    touched_categories = {entry["finding"]["category"] for entry in applied_fixes}
    projected_snapshot = _apply_fixes_to_snapshot(final_state["snapshot"], applied_fixes)
    checked = run_all_checks(projected_snapshot) if applied_fixes else {"categories": {}}

    manual_categories = {f["category"] for f in manual_findings}

    fixes_scores, full_scores = [], []
    deltas = []
    for category, label in CATEGORY_LABELS.items():
        current = analysis[f"{category}_score"]
        after_fixes = checked["categories"].get(category) if category in touched_categories else current
        after_manual = 100 if category in manual_categories and current is not None else after_fixes

        if after_fixes is not None:
            fixes_scores.append(after_fixes)
        if after_manual is not None:
            full_scores.append(after_manual)
        if current is not None and after_fixes is not None and current != after_fixes:
            deltas.append(f"{label}: {current} → {after_fixes}")

    current_overall = analysis["overall_score"]
    fixes_overall = round(sum(fixes_scores) / len(fixes_scores)) if fixes_scores else current_overall
    full_overall = round(sum(full_scores) / len(full_scores)) if full_scores else current_overall

    message = f"{current_overall} today"
    if applied_fixes:
        message += f" · {fixes_overall} with the fixes below applied"
    if manual_findings:
        step_word = "step" if len(manual_findings) == 1 else "steps"
        message += f" · {full_overall} if you also complete the {len(manual_findings)} manual {step_word}"

    why = " ".join(deltas) if deltas else "No generated-fix category scores changed."
    _log(final_state, "monitor", PROJECTION_MARKER, message, why)

    blockers = []
    for description in _fill_in_fields(applied_fixes):
        blockers.append(f"FILL IN: {description}")
    skipped = json.loads(analysis["skipped_json"] or "{}")
    for category, reason in skipped.items():
        label = CATEGORY_LABELS.get(category, category)
        blockers.append(f"{label}: {reason}")

    if blockers:
        _log(final_state, "monitor", BLOCKERS_MARKER, " | ".join(blockers))


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("suggest", suggest_node)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("monitor", monitor_node)
    graph.set_entry_point("suggest")

    graph.add_conditional_edges("suggest", _route_after_suggest, {"plan": "plan", "end": END})
    graph.add_conditional_edges("plan", _route_after_plan, {"execute": "execute", "suggest": "suggest", "end": END})
    graph.add_conditional_edges("execute", _route_after_execute, {"monitor": "monitor", "end": END})
    graph.add_conditional_edges(
        "monitor", _route_after_monitor, {"execute": "execute", "suggest": "suggest", "end": END}
    )
    return graph.compile()


_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_agent_loop(business_id, run_id):
    """Entry point: load the business's latest analysis, run the graph
    to completion, and log a final summary row so GET /agent-runs/<run_id>
    can tell it's done."""
    state = _load_initial_state(business_id, run_id)
    final_state = _get_graph().invoke(state, config={"recursion_limit": MAX_NODE_EXECUTIONS + 10})

    _log_score_projection(final_state, business_id)

    summary = (
        f"{final_state.get('done_reason', 'stopped')} — "
        f"resolved: {len(final_state['resolved'])}, "
        f"needs owner: {len(final_state['needs_human'])}, "
        f"failed: {len(final_state['failed'])}"
    )
    create_agent_run(run_id, business_id, "done", "done", message=summary)
    return final_state
