from __future__ import annotations

from datetime import UTC, datetime

_OVERSTATEMENT_PHRASES = [
    "strong buy",
    "must buy",
    "guaranteed upside",
    "certain gain",
    "cannot miss",
]


def review_report(
    report_payload: dict,
    evidence_payload: dict,
    quant_payload: dict,
    risk_payload: dict,
) -> dict:
    content = report_payload.get("full_content", "")
    warnings: list[str] = []
    errors: list[str] = []

    has_date_marker = "Data dates" in content or "Week range" in content or "Trade date" in content
    if "Data sources" not in content or not has_date_marker:
        errors.append("Report is missing explicit data-source or data-date fields.")

    coverage = _evidence_coverage(content, evidence_payload)
    if coverage < 0.5 and evidence_payload.get("evidence_pack"):
        warnings.append("Evidence coverage is low relative to the evidence pack.")

    timeliness = _timeliness_check(evidence_payload)
    if timeliness != "PASS":
        warnings.append("Core evidence may be stale.")

    consistency = _consistency_check(content, quant_payload, risk_payload)
    if consistency != "PASS":
        errors.append("Risk review or structured-analysis content is inconsistent with the report body.")

    overstatement_detected = _overstatement_check(content)
    if overstatement_detected:
        errors.append("Report contains overstated or advisory language that exceeds the allowed action boundary.")

    if errors:
        status = "FAIL"
    elif warnings:
        status = "PASS_WITH_WARNINGS"
    else:
        status = "PASS"

    ethics_checklist = _ethics_checklist(content, evidence_payload, coverage, consistency)
    recommended_action_boundary = _recommend_action_boundary(status, overstatement_detected)

    return {
        "status": status,
        "warnings": warnings,
        "errors": errors,
        "evidence_coverage": round(coverage, 4),
        "timeliness_check": timeliness,
        "consistency_check": consistency,
        "overstatement_detected": overstatement_detected,
        "ethics_checklist": ethics_checklist,
        "recommended_action_boundary": recommended_action_boundary,
        "summary": _summary(status, warnings, errors, overstatement_detected),
        "checked_at": datetime.now(UTC).isoformat(),
    }


def _evidence_coverage(content: str, evidence_payload: dict) -> float:
    evidence_items = evidence_payload.get("evidence_pack", [])
    if not evidence_items:
        return 1.0
    referenced = 0
    for item in evidence_items:
        if item["evidence_id"] in content or item["title"] in content:
            referenced += 1
    return referenced / len(evidence_items)


def _timeliness_check(evidence_payload: dict) -> str:
    latest = evidence_payload.get("latest_evidence_date")
    if not latest:
        return "PASS_WITH_WARNINGS"
    try:
        delta_days = (datetime.now(UTC).date() - datetime.fromisoformat(latest).date()).days
    except ValueError:
        return "FAIL"
    if delta_days <= 7:
        return "PASS"
    return "PASS_WITH_WARNINGS"


def _consistency_check(content: str, quant_payload: dict, risk_payload: dict) -> str:
    alerts = risk_payload.get("alerts", [])
    if any(alert not in content for alert in alerts):
        return "FAIL"

    bearish_count = sum(1 for item in quant_payload.get("stocks", []) if item.get("ma_signal") == "bearish")
    bullish_count = sum(1 for item in quant_payload.get("stocks", []) if item.get("ma_signal") == "bullish")
    if bearish_count > bullish_count and "Bullish trend" in content:
        return "FAIL"
    return "PASS"


def _overstatement_check(content: str) -> bool:
    lowered = content.lower()
    return any(phrase in lowered for phrase in _OVERSTATEMENT_PHRASES)


def _ethics_checklist(content: str, evidence_payload: dict, coverage: float, consistency: str) -> dict:
    return {
        "claims_supported_by_evidence": coverage >= 0.5,
        "data_freshness_explicit": ("Data dates" in content or "Week range" in content or "Trade date" in content),
        "no_analysis_risk_conflict": consistency == "PASS",
        "no_overstatement": not _overstatement_check(content),
        "action_boundary_appropriate": ("Action boundary" in content or "Human approval required" in content),
    }


def _recommend_action_boundary(status: str, overstatement_detected: bool) -> str:
    if status == "FAIL" or overstatement_detected:
        return "informational_only"
    return "analysis_only"


def _summary(status: str, warnings: list[str], errors: list[str], overstatement_detected: bool = False) -> str:
    if status == "FAIL":
        if overstatement_detected:
            return "The report used overstated or advisory language and has been downgraded to informational use only."
        return "The report failed one or more critical review checks and must be corrected before reuse."
    if warnings:
        return "The report passed review with warnings about evidence coverage or timeliness."
    return "The report passed review and remains consistent with the supplied evidence and analysis."
