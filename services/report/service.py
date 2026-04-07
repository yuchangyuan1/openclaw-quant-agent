from __future__ import annotations

from pathlib import Path

from services.common.ethics import (
    classify_action_boundary,
    compute_data_freshness,
    compute_evidence_status,
)
from services.common.paths import PROJECT_ROOT, reports_dir


def build_report(
    report_type: str,
    report_date: str,
    evidence_payload: dict,
    quant_payload: dict,
    risk_payload: dict,
    critic_status: str = "PENDING",
) -> dict:
    template = _load_template(report_type)
    content = _render_template(
        template,
        report_type=report_type,
        report_date=report_date,
        evidence_payload=evidence_payload,
        quant_payload=quant_payload,
        risk_payload=risk_payload,
        critic_status=critic_status,
    )
    file_path = _archive_report(report_type, report_date, content)
    summary = _build_summary(report_type, report_date, evidence_payload, quant_payload, risk_payload, file_path)
    return {
        "report_type": report_type,
        "report_date": report_date,
        "full_content": content,
        "feishu_summary": summary,
        "file_path": str(file_path),
        "has_conflicts": _detect_conflicts(evidence_payload, quant_payload),
        "conflict_notes": _conflict_notes(evidence_payload, quant_payload),
        "risk_level": risk_payload.get("risk_level", "UNKNOWN"),
    }


def finalize_report_with_critic(report_payload: dict, critic_payload: dict) -> dict:
    old_content = report_payload["full_content"]
    old_marker = f"Critic status: {_extract_existing_critic_status(old_content)}"
    new_marker = f"Critic status: {critic_payload['status']}"
    updated_content = old_content.replace(old_marker, new_marker)
    if updated_content == old_content:
        updated_content = f"{old_content}\n\n{new_marker}"

    ethics_checklist = critic_payload.get("ethics_checklist", {})
    if ethics_checklist:
        checklist_summary = _format_ethics_checklist_summary(ethics_checklist)
        updated_content = updated_content.replace("PENDING", checklist_summary, 1)

    path = Path(report_payload["file_path"])
    path.write_text(updated_content, encoding="utf-8")

    updated_payload = dict(report_payload)
    updated_payload["full_content"] = updated_content
    updated_payload["critic_status"] = critic_payload["status"]
    return updated_payload


def _load_template(report_type: str) -> str:
    template_name = "daily_report.md" if report_type == "daily" else "weekly_report.md"
    template_path = PROJECT_ROOT / "templates" / template_name
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return _fallback_template(report_type)


def _render_template(
    template: str,
    *,
    report_type: str,
    report_date: str,
    evidence_payload: dict,
    quant_payload: dict,
    risk_payload: dict,
    critic_status: str,
) -> str:
    evidence_items = evidence_payload.get("evidence_pack", [])
    evidence_highlights = _format_evidence(evidence_items)
    quant_signals = _format_quant_signals(quant_payload)
    market_summary = _format_market_summary(quant_payload)
    market_signals = _format_market_signals(quant_payload)
    risk_alerts = _format_risk_alerts(risk_payload)
    industry_exposure = _format_industry_exposure(risk_payload)
    conclusion = evidence_payload.get("synthesis") or "No additional conclusion was generated from the current evidence set."
    data_sources = _collect_data_sources(evidence_payload, quant_payload, risk_payload)
    data_dates = _collect_data_dates(evidence_payload, quant_payload, risk_payload)

    evidence_count = len(evidence_items)
    latest_date = evidence_payload.get("latest_evidence_date")
    risk_status = risk_payload.get("risk_level", "UNKNOWN")
    evidence_status = compute_evidence_status(evidence_count, None)
    data_freshness = compute_data_freshness(latest_date)
    conflict_detected = _detect_conflicts(evidence_payload, quant_payload)
    action_boundary = classify_action_boundary(
        intent="DAILY_REPORT",
        critic_status=critic_status,
        conflict_detected=conflict_detected,
        risk_status=risk_status,
        evidence_count=evidence_count,
    )
    human_approval_required = action_boundary == "requires_human_approval"

    payload = {
        "report_date": report_date,
        "report_week": evidence_payload.get("report_week", report_date),
        "week_range": evidence_payload.get("week_range", report_date),
        "trade_date": quant_payload.get("trade_date", "unknown"),
        "market_summary": market_summary,
        "market_signals": market_signals,
        "evidence_pack_highlights": evidence_highlights,
        "weekly_evidence_highlights": evidence_highlights,
        "quant_signals": quant_signals,
        "weekly_quant_summary": quant_signals,
        "risk_level": risk_status,
        "risk_alerts": risk_alerts,
        "industry_exposure": industry_exposure,
        "risk_breakdown": industry_exposure,
        "conclusion": conclusion,
        "watchlist": _format_watchlist(evidence_payload),
        "style_rotation": quant_payload.get("style_rotation")
        or quant_payload.get("market_summary", {}).get("data_source", "Not available"),
        "data_sources": data_sources,
        "data_dates": data_dates,
        "critic_status": critic_status,
        "evidence_status": evidence_status,
        "data_freshness": data_freshness,
        "conflict_detected": "Yes" if conflict_detected else "No",
        "human_approval_required": "Yes" if human_approval_required else "No",
        "action_boundary": action_boundary,
        "ethics_checklist_summary": "PENDING",
    }
    return template.format(**payload)


def _archive_report(report_type: str, report_date: str, content: str) -> Path:
    target_dir = reports_dir() / report_type
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{report_date}.md"
    path.write_text(content, encoding="utf-8")
    return path


def _format_evidence(items: list[dict]) -> str:
    if not items:
        return "[No evidence pack provided]"
    lines = []
    for item in items[:5]:
        published = item.get("published_at", "unknown")
        lines.append(f"- {item['evidence_id']} | {item['title']} | {item['source']} | {published}")
    return "\n".join(lines)


def _format_quant_signals(quant_payload: dict) -> str:
    stocks = quant_payload.get("stocks", [])
    if not stocks:
        return "[No structured-analysis payload provided]"
    lines = []
    for item in stocks[:5]:
        lines.append(
            f"- {item['name']} ({item['code']}): close {item['close']}, change {item['pct_change']}%, "
            f"MA5/MA20 {item.get('ma5')}/{item.get('ma20')}, signal {item.get('ma_signal', 'N/A')}"
        )
    return "\n".join(lines)


def _format_market_summary(quant_payload: dict) -> str:
    summary = quant_payload.get("market_summary", {})
    if not summary:
        return "[No market summary available]"
    return (
        f"Average tracked move {summary.get('sh300_pct_change', 'N/A')}%, "
        f"tracked volume {summary.get('total_volume_billion', 'N/A')} bn, "
        f"advancers {summary.get('advancing_stocks', 'N/A')}, decliners {summary.get('declining_stocks', 'N/A')}"
    )


def _format_market_signals(quant_payload: dict) -> str:
    stocks = quant_payload.get("stocks", [])
    if not stocks:
        return "[No structured-analysis payload provided]"
    bullish = [item["name"] for item in stocks if item.get("ma_signal") == "bullish"]
    bearish = [item["name"] for item in stocks if item.get("ma_signal") == "bearish"]
    parts = []
    if bullish:
        parts.append(f"Bullish trend: {', '.join(bullish[:3])}")
    if bearish:
        parts.append(f"Bearish trend: {', '.join(bearish[:3])}")
    return "; ".join(parts) or "No strong trend divergence detected"


def _format_risk_alerts(risk_payload: dict) -> str:
    alerts = risk_payload.get("alerts", [])
    return "; ".join(alerts) if alerts else "No additional risk alerts"


def _format_industry_exposure(risk_payload: dict) -> str:
    breakdown = risk_payload.get("industry_breakdown", [])
    if not breakdown:
        return "[Risk check not available]"
    return "; ".join(f"{item['industry']} {item['weight']:.2%}" for item in breakdown[:3])


def _format_watchlist(evidence_payload: dict) -> str:
    companies = evidence_payload.get("matched_companies", [])
    themes = evidence_payload.get("matched_themes", [])
    lines = []
    if companies:
        lines.append(f"- Companies: {', '.join(companies[:5])}")
    if themes:
        lines.append(f"- Themes: {', '.join(themes[:5])}")
    return "\n".join(lines) if lines else "- No new watchlist items"


def _collect_data_sources(evidence_payload: dict, quant_payload: dict, risk_payload: dict) -> str:
    sources = {item.get("source") for item in evidence_payload.get("evidence_pack", []) if item.get("source")}
    if quant_payload:
        sources.add("quant_service")
    if risk_payload:
        sources.add("risk_service")
    return ", ".join(sorted(sources)) or "none"


def _collect_data_dates(evidence_payload: dict, quant_payload: dict, risk_payload: dict) -> str:
    if evidence_payload.get("data_dates_label"):
        return evidence_payload["data_dates_label"]
    dates = set()
    if evidence_payload.get("latest_evidence_date"):
        dates.add(evidence_payload["latest_evidence_date"])
    if quant_payload.get("trade_date"):
        dates.add(quant_payload["trade_date"])
    if risk_payload.get("generated_at"):
        dates.add(str(risk_payload["generated_at"])[:10])
    return ", ".join(sorted(dates)) or "unknown"


def _build_summary(
    report_type: str,
    report_date: str,
    evidence_payload: dict,
    quant_payload: dict,
    risk_payload: dict,
    file_path: Path,
) -> str:
    summary = quant_payload.get("market_summary", {})
    alerts = _format_risk_alerts(risk_payload)
    top_titles = [item["title"] for item in evidence_payload.get("evidence_pack", [])[:2]]
    highlights = "; ".join(top_titles) if top_titles else "No highlighted filings"
    report_label = "weekly report" if report_type == "weekly" else "daily report"
    risk_status = risk_payload.get("risk_level", "UNKNOWN")
    action_boundary = classify_action_boundary(
        intent="DAILY_REPORT",
        critic_status="PENDING",
        conflict_detected=_detect_conflicts(evidence_payload, quant_payload),
        risk_status=risk_status,
        evidence_count=len(evidence_payload.get("evidence_pack", [])),
    )
    human_approval_required = action_boundary == "requires_human_approval"
    approval_line = "Human approval required. " if human_approval_required else ""
    return (
        f"{report_label.title()} for {report_date}\n"
        f"Tracked-market move: {summary.get('sh300_pct_change', 'N/A')}% | "
        f"Advancers: {summary.get('advancing_stocks', 'N/A')} | Decliners: {summary.get('declining_stocks', 'N/A')}\n"
        f"Highlights: {highlights}\n"
        f"Risk level: {risk_status}. Alerts: {alerts}\n"
        f"{approval_line}Action boundary: {action_boundary}\n"
        f"Full report: {file_path}"
    )


def _detect_conflicts(evidence_payload: dict, quant_payload: dict) -> bool:
    synthesis = (evidence_payload.get("synthesis") or "").lower()
    bullish_count = sum(1 for item in quant_payload.get("stocks", []) if item.get("ma_signal") == "bullish")
    bearish_count = sum(1 for item in quant_payload.get("stocks", []) if item.get("ma_signal") == "bearish")
    return ("risk" in synthesis or "pressure" in synthesis or "weakness" in synthesis) and bullish_count > bearish_count


def _conflict_notes(evidence_payload: dict, quant_payload: dict) -> str | None:
    if not _detect_conflicts(evidence_payload, quant_payload):
        return None
    return "Narrative evidence is cautious while the technical layer still shows stronger signals."


def _format_ethics_checklist_summary(checklist: dict) -> str:
    labels = {
        "claims_supported_by_evidence": "claims backed by evidence",
        "data_freshness_explicit": "data freshness stated",
        "no_analysis_risk_conflict": "no analysis-risk conflict",
        "no_overstatement": "no overstatement",
        "action_boundary_appropriate": "action boundary stated",
    }
    parts = []
    for key, label in labels.items():
        status = "PASS" if checklist.get(key) else "FAIL"
        parts.append(f"{status}: {label}")
    return " | ".join(parts)


def _extract_existing_critic_status(content: str) -> str:
    for line in reversed(content.splitlines()):
        if line.startswith("Critic status:"):
            return line.split(":", 1)[1].strip()
    return "PENDING"


def _fallback_template(report_type: str) -> str:
    title = "Daily Research Report" if report_type == "daily" else "Weekly Research Report"
    return (
        f"# {title} - {{report_date}}\n\n"
        "## Market Overview\n\n"
        "- Trade date: {trade_date}\n"
        "- Market summary: {market_summary}\n\n"
        "## Key Filings and Events\n\n"
        "{evidence_pack_highlights}\n\n"
        "## Structured Analysis\n\n"
        "{quant_signals}\n\n"
        "## Risk Review\n\n"
        "- Risk level: {risk_level}\n"
        "- Key alerts: {risk_alerts}\n\n"
        "## Conclusion\n\n"
        "{conclusion}\n\n"
        "---\n\n"
        "Data sources: {data_sources}\n"
        "Data dates: {data_dates}\n"
        "Critic status: {critic_status}\n"
    )
