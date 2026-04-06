from __future__ import annotations

from dataclasses import dataclass

from services.common.stocks import extract_company_terms, load_target_stocks
from services.rag.knowledge_pipeline import build_evidence_pack
from services.rag.service import build_index

from .report_pipeline import execute_daily_report, execute_weekly_report


@dataclass
class PlannerResponse:
    intent: str
    reply_markdown: str
    latest_data_date: str | None
    sources: list[str]
    critic_status: str
    evidence_count: int
    matched_companies: list[str]
    matched_company_names: list[str]
    matched_themes: list[str]
    company_terms: list[str]


def classify_intent(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return "UNKNOWN"
    if "日报" in text:
        return "DAILY_REPORT"
    if "周报" in text:
        return "WEEKLY_REPORT"
    if any(keyword in text for keyword in ["回撤", "风险", "暴露", "压力测试", "持仓"]):
        return "RISK_QUERY"
    if any(keyword in text for keyword in ["量化", "均线", "涨跌幅", "成交量", "指标"]):
        return "QUANT_QUERY"
    return "DOC_QA"


def execute_message(message: str, refresh_index: bool = True) -> PlannerResponse:
    intent = classify_intent(message)
    if intent == "DOC_QA":
        return execute_doc_qa(message, refresh_index=refresh_index)
    if intent == "DAILY_REPORT":
        return execute_daily_report_request(message)
    if intent == "WEEKLY_REPORT":
        return execute_weekly_report_request(message)
    return PlannerResponse(
        intent=intent,
        reply_markdown=f"当前仅已打通 DOC_QA、日报和周报流程，`{intent}` 仍未实现。",
        latest_data_date=None,
        sources=[],
        critic_status="NOT_IMPLEMENTED",
        evidence_count=0,
        matched_companies=[],
        matched_company_names=[],
        matched_themes=[],
        company_terms=infer_company_terms(message),
    )


def execute_doc_qa(message: str, refresh_index: bool = True) -> PlannerResponse:
    stock_codes = infer_stock_codes(message)
    company_terms = infer_company_terms(message)
    if refresh_index:
        build_index([], False)
    result = build_evidence_pack(
        question=message,
        stock_codes=stock_codes,
        company_terms=company_terms,
        doc_types=["news", "announcement"],
        days=7,
        top_k=5,
        min_score=0.25,
    )
    reply = format_doc_qa_reply(message, result)
    sources = sorted({item["source"] for item in result["evidence_pack"]})
    critic_status = "PASS_WITH_WARNINGS" if result["coverage_warning"] else "PASS"
    matched_companies = result.get("matched_companies", [])
    return PlannerResponse(
        intent="DOC_QA",
        reply_markdown=reply,
        latest_data_date=result["latest_evidence_date"],
        sources=sources,
        critic_status=critic_status,
        evidence_count=len(result["evidence_pack"]),
        matched_companies=matched_companies,
        matched_company_names=_company_names_from_codes(matched_companies),
        matched_themes=result.get("matched_themes", []),
        company_terms=result.get("company_terms", company_terms),
    )


def execute_daily_report_request(message: str) -> PlannerResponse:
    stock_codes = infer_stock_codes(message)
    result = execute_daily_report(stock_codes=stock_codes or None)
    return _report_result_to_planner_response(
        intent="DAILY_REPORT",
        message=message,
        report_payload=result.report_payload,
        critic_payload=result.critic_payload,
        evidence_payload=result.evidence_payload,
        stock_codes=stock_codes,
    )


def execute_weekly_report_request(message: str) -> PlannerResponse:
    stock_codes = infer_stock_codes(message)
    result = execute_weekly_report(stock_codes=stock_codes or None)
    return _report_result_to_planner_response(
        intent="WEEKLY_REPORT",
        message=message,
        report_payload=result.report_payload,
        critic_payload=result.critic_payload,
        evidence_payload=result.evidence_payload,
        stock_codes=stock_codes,
    )


def infer_stock_codes(message: str) -> list[str]:
    text = message or ""
    matched = []
    for code, item in load_target_stocks().items():
        aliases = item.get("aliases", [])
        if code in text or any(alias and alias in text for alias in aliases):
            matched.append(code)
    return matched


def infer_company_terms(message: str) -> list[str]:
    return extract_company_terms(message)


def format_doc_qa_reply(message: str, payload: dict) -> str:
    synthesis = payload["synthesis"]
    sources = "、".join(sorted({item["source"] for item in payload["evidence_pack"]})) or "暂无"
    latest_date = payload["latest_evidence_date"] or "未知"
    critic_status = "PASS_WITH_WARNINGS" if payload["coverage_warning"] else "PASS"
    warning = f"\n\n提示：{payload['coverage_warning']}" if payload["coverage_warning"] else ""
    matched_companies = _format_company_labels(payload.get("matched_companies", []))
    matched_themes = "、".join(payload.get("matched_themes", [])) or "暂无"
    company_terms = "、".join(payload.get("company_terms", [])) or "暂无"
    graph_summary = _format_graph_summary(payload.get("graph_context", {}))
    return (
        f"**{message}**\n\n"
        f"{synthesis}{warning}\n\n"
        f"**查询公司词项**：{company_terms}\n"
        f"**研究命中公司**：{matched_companies}\n"
        f"**研究命中主题**：{matched_themes}\n"
        f"{graph_summary}\n\n"
        "---\n"
        f"**数据来源**：{sources}\n"
        f"**数据日期**：{latest_date}\n"
        f"**证据数量**：{len(payload['evidence_pack'])}\n"
        f"**Critic 校验**：{critic_status}"
    )


def _report_result_to_planner_response(
    *,
    intent: str,
    message: str,
    report_payload: dict,
    critic_payload: dict,
    evidence_payload: dict,
    stock_codes: list[str],
) -> PlannerResponse:
    matched_companies = evidence_payload.get("matched_companies") or stock_codes
    sources = sorted({item.get("source") for item in evidence_payload.get("evidence_pack", []) if item.get("source")})
    sources.extend(source for source in ["quant_service", "risk_service"] if source not in sources)
    report_type_label = "日报" if intent == "DAILY_REPORT" else "周报"
    latest_date = evidence_payload.get("latest_evidence_date") or report_payload.get("report_date")
    count = len(evidence_payload.get("evidence_pack", []))
    reply = (
        f"**{report_type_label}已生成**\n\n"
        f"请求：{message}\n"
        f"报告日期：{report_payload.get('report_date')}\n"
        f"报告路径：{report_payload.get('file_path')}\n"
        f"Critic：{critic_payload.get('status')}\n"
        f"证据数量：{count}\n"
        f"数据日期/区间：{evidence_payload.get('data_dates_label') or latest_date}\n"
        f"完整摘要：{report_payload.get('feishu_summary')}"
    )
    return PlannerResponse(
        intent=intent,
        reply_markdown=reply,
        latest_data_date=latest_date,
        sources=sources,
        critic_status=critic_payload.get("status", "UNKNOWN"),
        evidence_count=count,
        matched_companies=matched_companies,
        matched_company_names=_company_names_from_codes(matched_companies),
        matched_themes=evidence_payload.get("matched_themes", []),
        company_terms=[],
    )


def _company_names_from_codes(codes: list[str]) -> list[str]:
    stocks = load_target_stocks()
    return [stocks[code]["name"] for code in codes if code in stocks]


def _format_company_labels(codes: list[str]) -> str:
    stocks = load_target_stocks()
    labels = []
    for code in codes:
        item = stocks.get(code)
        if item:
            labels.append(f"{item['name']}({code})")
        else:
            labels.append(code)
    return "、".join(labels) or "暂无"


def _format_graph_summary(graph_context: dict) -> str:
    companies = "、".join(item["name"] for item in graph_context.get("companies", [])[:5]) or "暂无"
    themes = "、".join(item["name"] for item in graph_context.get("themes", [])[:5]) or "暂无"
    industries = "、".join(item["name"] for item in graph_context.get("industries", [])[:5]) or "暂无"
    relation_labels = [
        f"{item['src']} -> {item['relation_type']} -> {item['dst']}"
        for item in graph_context.get("relations", [])[:3]
    ]
    relations = "；".join(relation_labels) or "暂无"
    return (
        f"**图谱关联公司**：{companies}\n"
        f"**图谱关联主题**：{themes}\n"
        f"**图谱关联行业**：{industries}\n"
        f"**图谱关联关系**：{relations}"
    )
