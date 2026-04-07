"""Shared ethics helper functions used by planner and report services."""

from __future__ import annotations

from datetime import UTC, datetime


def compute_evidence_status(evidence_count: int, coverage_warning: str | None) -> str:
    """Return evidence sufficiency status."""
    if evidence_count == 0:
        return "NONE"
    if coverage_warning:
        return "PARTIAL" if evidence_count >= 2 else "INSUFFICIENT"
    return "SUFFICIENT"


def compute_data_freshness(latest_data_date: str | None) -> str:
    """Return data freshness label based on days since latest evidence date."""
    if not latest_data_date:
        return "UNKNOWN"
    try:
        delta_days = (datetime.now(UTC).date() - datetime.fromisoformat(latest_data_date).date()).days
    except ValueError:
        return "UNKNOWN"
    if delta_days <= 3:
        return "FRESH"
    if delta_days <= 7:
        return "ACCEPTABLE"
    return "STALE"


_BOUNDARY_ORDER = {"informational_only": 0, "analysis_only": 1, "requires_human_approval": 2}


def _more_restrictive(a: str, b: str) -> str:
    """Return the more restrictive of two action_boundary values."""
    return a if _BOUNDARY_ORDER.get(a, 0) <= _BOUNDARY_ORDER.get(b, 0) else b


def classify_action_boundary(
    intent: str,
    critic_status: str,
    conflict_detected: bool,
    risk_status: str,
    evidence_count: int,
    critic_recommended: str | None = None,
) -> str:
    """
    Determine action_boundary using precedence rules:
    1. critic_status FAIL → informational_only
    2. conflict_detected → requires_human_approval
    3. risk_status HIGH/CRITICAL → requires_human_approval
    4. intent DAILY_REPORT/WEEKLY_REPORT → requires_human_approval
    5. intent MIXED_QUERY with evidence → analysis_only
    6. default → informational_only
    """
    if critic_status == "FAIL":
        planner_boundary = "informational_only"
    elif conflict_detected:
        planner_boundary = "requires_human_approval"
    elif risk_status in {"HIGH", "CRITICAL"}:
        planner_boundary = "requires_human_approval"
    elif intent in {"DAILY_REPORT", "WEEKLY_REPORT"}:
        planner_boundary = "requires_human_approval"
    elif intent == "MIXED_QUERY" and evidence_count >= 3:
        planner_boundary = "analysis_only"
    else:
        planner_boundary = "informational_only"

    if critic_recommended:
        return _more_restrictive(planner_boundary, critic_recommended)
    return planner_boundary


def build_accountability_trail(
    participating_agents: list[str],
    evidence_count: int,
    evidence_status: str,
    risk_status: str,
    critic_result: str,
    conflict_detected: bool,
    action_boundary: str,
    human_approval_required: bool,
) -> dict:
    """Build structured accountability trail for final output."""
    return {
        "participating_agents": participating_agents,
        "evidence_count": evidence_count,
        "evidence_status": evidence_status,
        "risk_gate_result": risk_status,
        "critic_result": critic_result,
        "conflict_detected": conflict_detected,
        "action_boundary": action_boundary,
        "human_approval_required": human_approval_required,
        "checked_at": datetime.now(UTC).isoformat(),
    }
