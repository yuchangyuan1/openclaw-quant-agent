"""Ethics contract tests — Phase 5 of the ethics transformation plan."""

from __future__ import annotations

from services.common.ethics import (
    classify_action_boundary,
    compute_data_freshness,
    compute_evidence_status,
)
from services.planner.pipeline import PlannerResponse


# ── Evidence status ──────────────────────────────────────────────────────────

def test_compute_evidence_status_none():
    assert compute_evidence_status(0, None) == "NONE"


def test_compute_evidence_status_insufficient():
    assert compute_evidence_status(1, "low coverage") == "INSUFFICIENT"


def test_compute_evidence_status_partial():
    assert compute_evidence_status(3, "low coverage") == "PARTIAL"


def test_compute_evidence_status_sufficient():
    assert compute_evidence_status(5, None) == "SUFFICIENT"


# ── Data freshness ────────────────────────────────────────────────────────────

def test_compute_data_freshness_unknown_when_none():
    assert compute_data_freshness(None) == "UNKNOWN"


def test_compute_data_freshness_unknown_bad_format():
    assert compute_data_freshness("not-a-date") == "UNKNOWN"


def test_compute_data_freshness_fresh(monkeypatch):
    import datetime
    from unittest.mock import patch
    fixed_today = datetime.date(2026, 4, 8)

    class FakeDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2026, 4, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    with patch("services.common.ethics.datetime", FakeDatetime):
        assert compute_data_freshness("2026-04-07") == "FRESH"
        assert compute_data_freshness("2026-04-06") == "FRESH"
        assert compute_data_freshness("2026-04-05") == "FRESH"
        assert compute_data_freshness("2026-04-02") == "ACCEPTABLE"
        assert compute_data_freshness("2026-03-31") == "STALE"


# ── Action boundary ───────────────────────────────────────────────────────────

def test_classify_action_boundary_fail_critic_overrides():
    result = classify_action_boundary(
        intent="DOC_QA", critic_status="FAIL", conflict_detected=False,
        risk_status="LOW", evidence_count=5,
    )
    assert result == "informational_only"


def test_classify_action_boundary_conflict_detected():
    result = classify_action_boundary(
        intent="DOC_QA", critic_status="PASS", conflict_detected=True,
        risk_status="LOW", evidence_count=3,
    )
    assert result == "requires_human_approval"


def test_classify_action_boundary_high_risk():
    result = classify_action_boundary(
        intent="QUANT_QUERY", critic_status="PASS", conflict_detected=False,
        risk_status="HIGH", evidence_count=3,
    )
    assert result == "requires_human_approval"


def test_classify_action_boundary_report_always_approval():
    for intent in ("DAILY_REPORT", "WEEKLY_REPORT"):
        result = classify_action_boundary(
            intent=intent, critic_status="PASS", conflict_detected=False,
            risk_status="LOW", evidence_count=5,
        )
        assert result == "requires_human_approval", f"{intent} should require approval"


def test_classify_action_boundary_mixed_query_with_evidence():
    result = classify_action_boundary(
        intent="MIXED_QUERY", critic_status="PASS", conflict_detected=False,
        risk_status="LOW", evidence_count=3,
    )
    assert result == "analysis_only"


def test_classify_action_boundary_default_informational():
    result = classify_action_boundary(
        intent="DOC_QA", critic_status="PASS", conflict_detected=False,
        risk_status="LOW", evidence_count=1,
    )
    assert result == "informational_only"


def test_classify_action_boundary_critic_downgrade():
    """Critic recommended boundary more restrictive than planner's → critic wins."""
    result = classify_action_boundary(
        intent="MIXED_QUERY", critic_status="PASS", conflict_detected=False,
        risk_status="LOW", evidence_count=5,
        critic_recommended="informational_only",
    )
    assert result == "informational_only"


def test_classify_action_boundary_critic_upgrade_ignored():
    """Critic can only downgrade, not upgrade beyond planner's FAIL override."""
    result = classify_action_boundary(
        intent="DAILY_REPORT", critic_status="FAIL", conflict_detected=False,
        risk_status="LOW", evidence_count=5,
        critic_recommended="analysis_only",
    )
    assert result == "informational_only"


# ── PlannerResponse ethics fields ─────────────────────────────────────────────

def test_planner_response_dataclass_has_ethics_fields():
    r = PlannerResponse(
        intent="DOC_QA",
        reply_markdown="test",
        latest_data_date=None,
        sources=[],
        critic_status="PASS",
        evidence_count=0,
        matched_companies=[],
        matched_company_names=[],
        matched_themes=[],
        company_terms=[],
        collaboration_agents=["planner"],
        orchestration_mode="planner_only",
    )
    assert hasattr(r, "evidence_status")
    assert hasattr(r, "data_freshness")
    assert hasattr(r, "risk_status")
    assert hasattr(r, "conflict_detected")
    assert hasattr(r, "human_approval_required")
    assert hasattr(r, "action_boundary")
    assert hasattr(r, "accountability_trail")
    # Defaults
    assert r.evidence_status == "NONE"
    assert r.data_freshness == "UNKNOWN"
    assert r.risk_status == "UNKNOWN"
    assert r.conflict_detected is False
    assert r.human_approval_required is False
    assert r.action_boundary == "informational_only"
    assert isinstance(r.accountability_trail, dict)
