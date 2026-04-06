from __future__ import annotations

from datetime import UTC, datetime


def review_report(
    report_payload: dict,
    evidence_payload: dict,
    quant_payload: dict,
    risk_payload: dict,
) -> dict:
    content = report_payload.get("full_content", "")
    warnings: list[str] = []
    errors: list[str] = []

    has_date_marker = "数据日期" in content or "数据区间" in content
    if "数据来源" not in content or not has_date_marker:
        errors.append("报告缺少数据来源或数据日期/数据区间字段。")

    coverage = _evidence_coverage(content, evidence_payload)
    if coverage < 0.5 and evidence_payload.get("evidence_pack"):
        warnings.append("报告对 Evidence Pack 的引用覆盖率偏低。")

    timeliness = _timeliness_check(evidence_payload)
    if timeliness != "PASS":
        warnings.append("核心证据时效性不足。")

    consistency = _consistency_check(content, quant_payload, risk_payload)
    if consistency != "PASS":
        errors.append("风险提示或量化结论与报告正文存在不一致。")

    if errors:
        status = "FAIL"
    elif warnings:
        status = "PASS_WITH_WARNINGS"
    else:
        status = "PASS"

    return {
        "status": status,
        "warnings": warnings,
        "errors": errors,
        "evidence_coverage": round(coverage, 4),
        "timeliness_check": timeliness,
        "consistency_check": consistency,
        "summary": _summary(status, warnings, errors),
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
        delta_days = (datetime.now().date() - datetime.fromisoformat(latest).date()).days
    except ValueError:
        return "FAIL"
    if delta_days <= 7:
        return "PASS"
    return "PASS_WITH_WARNINGS"


def _consistency_check(content: str, quant_payload: dict, risk_payload: dict) -> str:
    alerts = risk_payload.get("alerts", [])
    if any(alert not in content for alert in alerts[:2]):
        return "FAIL"

    bearish_count = sum(1 for item in quant_payload.get("stocks", []) if item.get("ma_signal") == "bearish")
    bullish_count = sum(1 for item in quant_payload.get("stocks", []) if item.get("ma_signal") == "bullish")
    if bearish_count > bullish_count and "偏强" in content:
        return "FAIL"
    return "PASS"


def _summary(status: str, warnings: list[str], errors: list[str]) -> str:
    if status == "FAIL":
        return "报告存在关键校验失败项，需要修正后再使用。"
    if warnings:
        return "报告通过校验，但存在需要注意的覆盖率或时效性提示。"
    return "报告通过校验，主要结论与输入证据保持一致。"
