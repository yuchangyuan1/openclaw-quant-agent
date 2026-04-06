from __future__ import annotations

from datetime import date
from dataclasses import dataclass

from services.common.stocks import extract_company_terms, load_target_stocks
from services.rag.service import build_index

from .collaboration import run_knowledge_agent, run_parallel_collaboration, run_quant_agent, run_risk_agent
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
    collaboration_agents: list[str]
    orchestration_mode: str


def classify_intent(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return "UNKNOWN"
    if "日报" in text:
        return "DAILY_REPORT"
    if "周报" in text:
        return "WEEKLY_REPORT"
    has_doc = any(keyword in text for keyword in ["公告", "新闻", "进展", "事件", "披露"])
    has_risk = any(keyword in text for keyword in ["回撤", "风险", "暴露", "压力测试", "持仓"])
    has_quant = any(keyword in text for keyword in ["量化", "均线", "涨跌幅", "成交量", "指标", "估值", "roe", "pe"])
    if sum([has_doc, has_quant, has_risk]) >= 2 or "综合" in text or "同时" in text:
        return "MIXED_QUERY"
    if has_risk:
        return "RISK_QUERY"
    if has_quant:
        return "QUANT_QUERY"
    return "DOC_QA"


def execute_message(message: str, refresh_index: bool = True) -> PlannerResponse:
    intent = classify_intent(message)
    if intent == "DOC_QA":
        return execute_doc_qa(message, refresh_index=refresh_index)
    if intent == "MIXED_QUERY":
        return execute_mixed_query(message, refresh_index=refresh_index)
    if intent == "QUANT_QUERY":
        return execute_quant_query(message)
    if intent == "RISK_QUERY":
        return execute_risk_query(message)
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
        collaboration_agents=["planner"],
        orchestration_mode="planner_only",
    )


def execute_doc_qa(message: str, refresh_index: bool = True) -> PlannerResponse:
    stock_codes = infer_stock_codes(message)
    company_terms = infer_company_terms(message)
    if refresh_index:
        build_index([], False)

    knowledge_result = run_knowledge_agent(
        question=message,
        stock_codes=stock_codes,
        company_terms=company_terms,
        doc_types=["news", "announcement"],
        days=7,
        top_k=5,
        min_score=0.25,
    )
    payload = knowledge_result.payload
    reply = format_doc_qa_reply(message, payload)
    sources = sorted({item["source"] for item in payload["evidence_pack"]})
    critic_status = "PASS_WITH_WARNINGS" if payload["coverage_warning"] else "PASS"
    matched_companies = payload.get("matched_companies", [])
    return PlannerResponse(
        intent="DOC_QA",
        reply_markdown=reply,
        latest_data_date=payload["latest_evidence_date"],
        sources=sources,
        critic_status=critic_status,
        evidence_count=len(payload["evidence_pack"]),
        matched_companies=matched_companies,
        matched_company_names=_company_names_from_codes(matched_companies),
        matched_themes=payload.get("matched_themes", []),
        company_terms=payload.get("company_terms", company_terms),
        collaboration_agents=["planner", knowledge_result.agent_id],
        orchestration_mode="delegated_single_agent",
    )


def execute_mixed_query(message: str, refresh_index: bool = True) -> PlannerResponse:
    stock_codes = infer_stock_codes(message)
    company_terms = infer_company_terms(message)
    if refresh_index:
        build_index([], False)

    tasks = {}
    if company_terms or stock_codes:
        tasks["knowledge"] = lambda: run_knowledge_agent(
            question=message,
            stock_codes=stock_codes,
            company_terms=company_terms,
            doc_types=["news", "announcement"],
            days=7,
            top_k=5,
            min_score=0.25,
        )
    if stock_codes:
        tasks["quant"] = lambda: run_quant_agent(stock_codes=stock_codes, report_date=date.today().isoformat(), indicators=[])
        equal_weight = round(1 / len(stock_codes), 4)
        portfolio = [{"code": code, "weight": equal_weight} for code in stock_codes]
        tasks["risk"] = lambda: run_risk_agent(portfolio=portfolio)

    results = run_parallel_collaboration(tasks)
    knowledge_payload = results["knowledge"].payload if "knowledge" in results else None
    quant_payload = results["quant"].payload if "quant" in results else None
    risk_payload = results["risk"].payload if "risk" in results else None

    sections = ["**综合研究结果**", "", f"查询：{message}", "协作路径：Planner -> sessions_spawn(Knowledge, Quant, Risk)", ""]
    sources: list[str] = []
    latest_data_date: str | None = None
    matched_themes: list[str] = []
    evidence_count = 0

    if knowledge_payload:
        sections.append("**Knowledge**")
        sections.append(knowledge_payload["synthesis"])
        sections.append(f"证据数量：{len(knowledge_payload['evidence_pack'])}")
        sections.append("")
        sources.extend(sorted({item["source"] for item in knowledge_payload["evidence_pack"]}))
        latest_data_date = knowledge_payload.get("latest_evidence_date")
        matched_themes = knowledge_payload.get("matched_themes", [])
        evidence_count = len(knowledge_payload["evidence_pack"])

    if quant_payload:
        sections.append("**Quant**")
        top_stock = (quant_payload.get("stocks") or [{}])[0]
        if top_stock:
            sections.append(
                f"{top_stock.get('name')}({top_stock.get('code')}): close={top_stock.get('close')}, "
                f"pe_ttm={top_stock.get('pe_ttm')}, roe={top_stock.get('roe')}, "
                f"signal={top_stock.get('composite_signal')}"
            )
        else:
            sections.append("暂无量化结果")
        sections.append("")
        if "quant_service" not in sources:
            sources.append("quant_service")

    critic_status = "PASS"
    if risk_payload:
        sections.append("**Risk**")
        sections.append(
            f"risk_level={risk_payload.get('risk_level')}, "
            f"alerts={'；'.join(risk_payload.get('alerts', [])) or '无'}"
        )
        if risk_payload.get("alerts"):
            critic_status = "PASS_WITH_WARNINGS"
        if "risk_service" not in sources:
            sources.append("risk_service")

    collaboration_agents = ["planner"] + [results[key].agent_id for key in results]
    return PlannerResponse(
        intent="MIXED_QUERY",
        reply_markdown="\n".join(sections),
        latest_data_date=latest_data_date,
        sources=sources,
        critic_status=critic_status,
        evidence_count=evidence_count,
        matched_companies=(knowledge_payload or {}).get("matched_companies", stock_codes) if knowledge_payload else stock_codes,
        matched_company_names=_company_names_from_codes((knowledge_payload or {}).get("matched_companies", stock_codes) if knowledge_payload else stock_codes),
        matched_themes=matched_themes,
        company_terms=company_terms,
        collaboration_agents=collaboration_agents,
        orchestration_mode="parallel_subagents",
    )


def execute_quant_query(message: str) -> PlannerResponse:
    stock_codes = infer_stock_codes(message)
    company_terms = infer_company_terms(message)
    if not stock_codes:
        return PlannerResponse(
            intent="QUANT_QUERY",
            reply_markdown="当前量化问题需要至少包含一个目标股票或股票代码。",
            latest_data_date=None,
            sources=[],
            critic_status="PASS_WITH_WARNINGS",
            evidence_count=0,
            matched_companies=[],
            matched_company_names=[],
            matched_themes=[],
            company_terms=company_terms,
            collaboration_agents=["planner"],
            orchestration_mode="planner_only",
        )

    quant_result = run_quant_agent(stock_codes=stock_codes, report_date=date.today().isoformat(), indicators=[])
    payload = quant_result.payload
    reply_lines = [
        "**量化分析**",
        "",
        f"查询：{message}",
        "协作路径：Planner -> Quant",
        f"研究命中公司：{_format_company_labels(stock_codes)}",
        f"数据日期：{payload.get('trade_date') or '未知'}",
        "",
    ]
    for item in payload.get("stocks", [])[:3]:
        reply_lines.append(
            f"- {item['name']}({item['code']}): "
            f"close={item['close']}, pct_change={item['pct_change']}, "
            f"pe_ttm={item.get('pe_ttm')}, roe={item.get('roe')}, "
            f"composite_signal={item.get('composite_signal')}"
        )
    if not payload.get("stocks"):
        reply_lines.append("暂无可用量化结果")

    return PlannerResponse(
        intent="QUANT_QUERY",
        reply_markdown="\n".join(reply_lines),
        latest_data_date=payload.get("trade_date"),
        sources=["quant_service"],
        critic_status="PASS",
        evidence_count=len(payload.get("stocks", [])),
        matched_companies=stock_codes,
        matched_company_names=_company_names_from_codes(stock_codes),
        matched_themes=[],
        company_terms=company_terms,
        collaboration_agents=["planner", quant_result.agent_id],
        orchestration_mode="delegated_single_agent",
    )


def execute_risk_query(message: str) -> PlannerResponse:
    stock_codes = infer_stock_codes(message)
    company_terms = infer_company_terms(message)
    if not stock_codes:
        return PlannerResponse(
            intent="RISK_QUERY",
            reply_markdown="当前风险问题需要至少包含一个目标股票或持仓代码。",
            latest_data_date=None,
            sources=[],
            critic_status="PASS_WITH_WARNINGS",
            evidence_count=0,
            matched_companies=[],
            matched_company_names=[],
            matched_themes=[],
            company_terms=company_terms,
            collaboration_agents=["planner"],
            orchestration_mode="planner_only",
        )

    equal_weight = round(1 / len(stock_codes), 4)
    portfolio = [{"code": code, "weight": equal_weight} for code in stock_codes]
    risk_result = run_risk_agent(portfolio=portfolio)
    payload = risk_result.payload
    alerts = payload.get("alerts", [])
    reply = "\n".join(
        [
            "**风险分析**",
            "",
            f"查询：{message}",
            "协作路径：Planner -> Risk",
            f"研究命中公司：{_format_company_labels(stock_codes)}",
            f"风险等级：{payload.get('risk_level')}",
            f"告警条数：{len(alerts)}",
            f"告警内容：{'；'.join(alerts) if alerts else '无'}",
        ]
    )
    return PlannerResponse(
        intent="RISK_QUERY",
        reply_markdown=reply,
        latest_data_date=None,
        sources=["risk_service"],
        critic_status="PASS" if not alerts else "PASS_WITH_WARNINGS",
        evidence_count=len(alerts),
        matched_companies=stock_codes,
        matched_company_names=_company_names_from_codes(stock_codes),
        matched_themes=[],
        company_terms=company_terms,
        collaboration_agents=["planner", risk_result.agent_id],
        orchestration_mode="delegated_single_agent",
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
        f"**协作路径**：Planner -> Knowledge\n"
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
    for source in ["quant_service", "risk_service"]:
        if source not in sources:
            sources.append(source)
    report_type_label = "日报" if intent == "DAILY_REPORT" else "周报"
    latest_date = evidence_payload.get("latest_evidence_date") or report_payload.get("report_date")
    count = len(evidence_payload.get("evidence_pack", []))
    reply = (
        f"**{report_type_label}已生成**\n\n"
        f"请求：{message}\n"
        f"报告日期：{report_payload.get('report_date')}\n"
        f"报告路径：{report_payload.get('file_path')}\n"
        f"协作路径：Planner -> Knowledge + Quant + Risk -> Report -> Critic\n"
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
        collaboration_agents=["planner", "knowledge", "quant", "risk", "report", "critic"],
        orchestration_mode="parallel_subagents",
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
