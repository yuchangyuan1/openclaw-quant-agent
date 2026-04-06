from __future__ import annotations

from pathlib import Path

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
    }


def finalize_report_with_critic(report_payload: dict, critic_payload: dict) -> dict:
    old_content = report_payload["full_content"]
    old_marker = f"Critic 校验：{_extract_existing_critic_status(old_content)}"
    new_marker = f"Critic 校验：{critic_payload['status']}"
    updated_content = old_content.replace(old_marker, new_marker)
    if updated_content == old_content:
        updated_content = f"{old_content}\n\n{new_marker}"

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
    conclusion = evidence_payload.get("synthesis") or "根据现有证据，暂无进一步结论。"
    data_sources = _collect_data_sources(evidence_payload, quant_payload, risk_payload)
    data_dates = _collect_data_dates(evidence_payload, quant_payload, risk_payload)

    payload = {
        "report_date": report_date,
        "report_week": evidence_payload.get("report_week", report_date),
        "week_range": evidence_payload.get("week_range", report_date),
        "trade_date": quant_payload.get("trade_date", "未知"),
        "market_summary": market_summary,
        "market_signals": market_signals,
        "evidence_pack_highlights": evidence_highlights,
        "weekly_evidence_highlights": evidence_highlights,
        "quant_signals": quant_signals,
        "weekly_quant_summary": quant_signals,
        "risk_level": risk_payload.get("risk_level", "UNKNOWN"),
        "risk_alerts": risk_alerts,
        "industry_exposure": industry_exposure,
        "risk_breakdown": industry_exposure,
        "conclusion": conclusion,
        "watchlist": _format_watchlist(evidence_payload),
        "style_rotation": quant_payload.get("style_rotation")
        or quant_payload.get("market_summary", {}).get("data_source", "暂无"),
        "data_sources": data_sources,
        "data_dates": data_dates,
        "critic_status": critic_status,
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
        return "[证据包未提供]"
    lines = []
    for item in items[:5]:
        published = item.get("published_at", "未知")
        lines.append(f"- {item['evidence_id']} | {item['title']} | {item['source']} | {published}")
    return "\n".join(lines)


def _format_quant_signals(quant_payload: dict) -> str:
    stocks = quant_payload.get("stocks", [])
    if not stocks:
        return "[量化数据未提供]"
    lines = []
    for item in stocks[:5]:
        lines.append(
            f"- {item['name']}({item['code']}): 收盘 {item['close']}, 涨跌幅 {item['pct_change']}%, "
            f"MA5/MA20 {item.get('ma5')}/{item.get('ma20')}, 信号 {item.get('ma_signal', 'N/A')}"
        )
    return "\n".join(lines)


def _format_market_summary(quant_payload: dict) -> str:
    summary = quant_payload.get("market_summary", {})
    if not summary:
        return "[市场数据未提供]"
    return (
        f"沪深300变动 {summary.get('sh300_pct_change', 'N/A')}%，"
        f"样本成交额 {summary.get('total_volume_billion', 'N/A')} 亿，"
        f"上涨 {summary.get('advancing_stocks', 'N/A')}，下跌 {summary.get('declining_stocks', 'N/A')}"
    )


def _format_market_signals(quant_payload: dict) -> str:
    stocks = quant_payload.get("stocks", [])
    if not stocks:
        return "[量化数据未提供]"
    bullish = [item["name"] for item in stocks if item.get("ma_signal") == "bullish"]
    bearish = [item["name"] for item in stocks if item.get("ma_signal") == "bearish"]
    parts = []
    if bullish:
        parts.append(f"偏强: {'、'.join(bullish[:3])}")
    if bearish:
        parts.append(f"偏弱: {'、'.join(bearish[:3])}")
    return "；".join(parts) or "暂无明显趋势分化"


def _format_risk_alerts(risk_payload: dict) -> str:
    alerts = risk_payload.get("alerts", [])
    return "；".join(alerts) if alerts else "无显著额外风险提示"


def _format_industry_exposure(risk_payload: dict) -> str:
    breakdown = risk_payload.get("industry_breakdown", [])
    if not breakdown:
        return "[风险检查未完成]"
    return "；".join(f"{item['industry']} {item['weight']:.2%}" for item in breakdown[:3])


def _format_watchlist(evidence_payload: dict) -> str:
    companies = evidence_payload.get("matched_companies", [])
    themes = evidence_payload.get("matched_themes", [])
    lines = []
    if companies:
        lines.append(f"- 重点公司：{'、'.join(companies[:5])}")
    if themes:
        lines.append(f"- 重点主题：{'、'.join(themes[:5])}")
    return "\n".join(lines) if lines else "- 暂无新增观察名单"


def _collect_data_sources(evidence_payload: dict, quant_payload: dict, risk_payload: dict) -> str:
    sources = {item.get("source") for item in evidence_payload.get("evidence_pack", []) if item.get("source")}
    if quant_payload:
        sources.add("quant_service")
    if risk_payload:
        sources.add("risk_service")
    return "、".join(sorted(sources)) or "暂无"


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
    return "、".join(sorted(dates)) or "未知"


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
    highlights = "；".join(top_titles) if top_titles else "暂无重点事件"
    report_label = "周报" if report_type == "weekly" else "日报"
    return (
        f"投研{report_label} {report_date}\n"
        f"市场概况：沪深300样本变动 {summary.get('sh300_pct_change', 'N/A')}%，"
        f"上涨 {summary.get('advancing_stocks', 'N/A')}，下跌 {summary.get('declining_stocks', 'N/A')}。\n"
        f"重点事件：{highlights}\n"
        f"风险等级：{risk_payload.get('risk_level', 'UNKNOWN')}；主要风险：{alerts}\n"
        f"完整报告：{file_path}"
    )


def _detect_conflicts(evidence_payload: dict, quant_payload: dict) -> bool:
    synthesis = (evidence_payload.get("synthesis") or "").lower()
    bullish_count = sum(1 for item in quant_payload.get("stocks", []) if item.get("ma_signal") == "bullish")
    bearish_count = sum(1 for item in quant_payload.get("stocks", []) if item.get("ma_signal") == "bearish")
    return ("下行" in synthesis or "风险" in synthesis) and bullish_count > bearish_count


def _conflict_notes(evidence_payload: dict, quant_payload: dict) -> str | None:
    if not _detect_conflicts(evidence_payload, quant_payload):
        return None
    return "文本证据偏谨慎，但量化信号中偏强个股数量更多，请综合判断。"


def _extract_existing_critic_status(content: str) -> str:
    for line in reversed(content.splitlines()):
        if line.startswith("Critic 校验："):
            return line.split("：", 1)[1].strip()
    return "PENDING"


def _fallback_template(report_type: str) -> str:
    title = "每日投研日报" if report_type == "daily" else "每周投研周报"
    return (
        f"# {title} - {{report_date}}\n\n"
        "## 市场概览\n\n"
        "- 交易日期：{trade_date}\n"
        "- 市场摘要：{market_summary}\n\n"
        "## 重点事件\n\n"
        "{evidence_pack_highlights}\n\n"
        "## 量化信号\n\n"
        "{quant_signals}\n\n"
        "## 风险提示\n\n"
        "- 风险等级：{risk_level}\n"
        "- 风险提示：{risk_alerts}\n\n"
        "## 结论\n\n"
        "{conclusion}\n\n"
        "---\n\n"
        "数据来源：{data_sources}\n"
        "数据日期：{data_dates}\n"
        "Critic 校验：{critic_status}\n"
    )
