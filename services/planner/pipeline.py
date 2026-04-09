from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from services.common.ethics import (
    build_accountability_trail,
    classify_action_boundary,
    compute_data_freshness,
    compute_evidence_status,
)
from services.common.stocks import extract_company_terms, load_target_stocks
from services.rag.service import build_index

from .collaboration import (
    run_knowledge_agent,
    run_parallel_collaboration,
    run_quant_agent,
    run_risk_agent,
)
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
    evidence_status: str = "NONE"
    data_freshness: str = "UNKNOWN"
    risk_status: str = "UNKNOWN"
    conflict_detected: bool = False
    human_approval_required: bool = False
    action_boundary: str = "informational_only"
    accountability_trail: dict = field(default_factory=dict)


def classify_intent(message: str) -> str:
    text = (message or "").strip()
    lowered = text.lower()
    if not text:
        return "UNKNOWN"
    if any(keyword in lowered for keyword in ["daily report", "today's report", "generate daily report", "日报"]):
        return "DAILY_REPORT"
    if any(keyword in lowered for keyword in ["weekly report", "this week's report", "generate weekly report", "周报"]):
        return "WEEKLY_REPORT"

    has_doc = any(keyword in lowered for keyword in ["filing", "sec", "edgar", "8-k", "10-q", "10-k", "news", "update", "公告", "新闻"])
    has_risk = any(keyword in lowered for keyword in ["drawdown", "risk", "exposure", "stress test", "portfolio", "回撤", "风险"])
    has_quant = any(keyword in lowered for keyword in ["valuation", "momentum", "roe", "pe", "pb", "margin", "factor", "quant", "估值", "量化"])
    if sum([has_doc, has_quant, has_risk]) >= 2 or any(keyword in lowered for keyword in ["combined", "together", "综合", "同时"]):
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
        reply_markdown=(
            "Supported planner intents are DOC_QA, QUANT_QUERY, RISK_QUERY, MIXED_QUERY, "
            "DAILY_REPORT, and WEEKLY_REPORT."
        ),
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
        evidence_status="NONE",
        data_freshness="UNKNOWN",
        risk_status="UNKNOWN",
        conflict_detected=False,
        human_approval_required=False,
        action_boundary="informational_only",
        accountability_trail=build_accountability_trail(
            participating_agents=["planner"],
            evidence_count=0,
            evidence_status="NONE",
            risk_status="UNKNOWN",
            critic_result="NOT_IMPLEMENTED",
            conflict_detected=False,
            action_boundary="informational_only",
            human_approval_required=False,
        ),
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
        doc_types=["filing"],
        days=30,
        top_k=5,
        min_score=0.25,
    )
    payload = knowledge_result.payload
    evidence_count = len(payload["evidence_pack"])
    critic_status = "PASS_WITH_WARNINGS" if payload["coverage_warning"] else "PASS"
    evidence_status = compute_evidence_status(evidence_count, payload["coverage_warning"])
    data_freshness = compute_data_freshness(payload["latest_evidence_date"])
    action_boundary = classify_action_boundary(
        intent="DOC_QA",
        critic_status=critic_status,
        conflict_detected=False,
        risk_status="UNKNOWN",
        evidence_count=evidence_count,
    )
    collaboration_agents = ["planner", knowledge_result.agent_id]
    trail = build_accountability_trail(
        participating_agents=collaboration_agents,
        evidence_count=evidence_count,
        evidence_status=evidence_status,
        risk_status="UNKNOWN",
        critic_result=critic_status,
        conflict_detected=False,
        action_boundary=action_boundary,
        human_approval_required=(action_boundary == "requires_human_approval"),
    )
    matched_companies = payload.get("matched_companies", [])
    reply = format_doc_qa_reply(
        message,
        payload,
        action_boundary=action_boundary,
        human_approval_required=trail["human_approval_required"],
    )
    sources = sorted({item["source"] for item in payload["evidence_pack"]})
    return PlannerResponse(
        intent="DOC_QA",
        reply_markdown=reply,
        latest_data_date=payload["latest_evidence_date"],
        sources=sources,
        critic_status=critic_status,
        evidence_count=evidence_count,
        matched_companies=matched_companies,
        matched_company_names=_company_names_from_codes(matched_companies),
        matched_themes=payload.get("matched_themes", []),
        company_terms=payload.get("company_terms", company_terms),
        collaboration_agents=collaboration_agents,
        orchestration_mode="delegated_single_agent",
        evidence_status=evidence_status,
        data_freshness=data_freshness,
        risk_status="UNKNOWN",
        conflict_detected=False,
        human_approval_required=trail["human_approval_required"],
        action_boundary=action_boundary,
        accountability_trail=trail,
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
            doc_types=["filing"],
            days=30,
            top_k=5,
            min_score=0.25,
        )
    if stock_codes:
        tasks["quant"] = lambda: run_quant_agent(stock_codes=stock_codes, report_date=date.today().isoformat(), indicators=[])
        equal_weight = round(1 / len(stock_codes), 4)
        portfolio = [{"code": code, "weight": equal_weight} for code in stock_codes]
        tasks["risk"] = lambda: run_risk_agent(portfolio=portfolio, benchmark="SPY")

    results = run_parallel_collaboration(tasks)
    knowledge_payload = results["knowledge"].payload if "knowledge" in results else None
    quant_payload = results["quant"].payload if "quant" in results else None
    risk_payload = results["risk"].payload if "risk" in results else None

    sections = [
        "**Combined Research Result**",
        "",
        f"Query: {message}",
        "Collaboration path: Planner -> sessions_spawn(Knowledge, Quant, Risk)",
        "",
    ]
    sources: list[str] = []
    latest_data_date: str | None = None
    matched_themes: list[str] = []
    evidence_count = 0

    if knowledge_payload:
        sections.extend(
            [
                "**Knowledge**",
                knowledge_payload["synthesis"],
                f"Evidence count: {len(knowledge_payload['evidence_pack'])}",
                "",
            ]
        )
        sources.extend(sorted({item["source"] for item in knowledge_payload["evidence_pack"]}))
        latest_data_date = knowledge_payload.get("latest_evidence_date")
        matched_themes = knowledge_payload.get("matched_themes", [])
        evidence_count = len(knowledge_payload["evidence_pack"])

    if quant_payload:
        top_stock = (quant_payload.get("stocks") or [{}])[0]
        sections.append("**Quant**")
        if top_stock:
            sections.append(
                f"{top_stock.get('name')} ({top_stock.get('code')}): close={top_stock.get('close')}, "
                f"pe_ttm={top_stock.get('pe_ttm')}, roe={top_stock.get('roe')}, "
                f"signal={top_stock.get('composite_signal')}"
            )
        else:
            sections.append("No structured-analysis output was produced.")
        sections.append("")
        if "quant_service" not in sources:
            sources.append("quant_service")

    critic_status = "PASS"
    if risk_payload:
        sections.append("**Risk**")
        sections.append(
            f"risk_level={risk_payload.get('risk_level')}, "
            f"alerts={'; '.join(risk_payload.get('alerts', [])) or 'none'}"
        )
        if risk_payload.get("alerts"):
            critic_status = "PASS_WITH_WARNINGS"
        if "risk_service" not in sources:
            sources.append("risk_service")

    risk_status = risk_payload.get("risk_level", "UNKNOWN") if risk_payload else "UNKNOWN"
    conflict_detected = bool(risk_payload and risk_payload.get("alerts"))
    collaboration_agents = ["planner"] + [results[key].agent_id for key in results]
    evidence_status = compute_evidence_status(evidence_count, None if evidence_count >= 3 else "low")
    data_freshness = compute_data_freshness(latest_data_date)
    action_boundary = classify_action_boundary(
        intent="MIXED_QUERY",
        critic_status=critic_status,
        conflict_detected=conflict_detected,
        risk_status=risk_status,
        evidence_count=evidence_count,
    )
    trail = build_accountability_trail(
        participating_agents=collaboration_agents,
        evidence_count=evidence_count,
        evidence_status=evidence_status,
        risk_status=risk_status,
        critic_result=critic_status,
        conflict_detected=conflict_detected,
        action_boundary=action_boundary,
        human_approval_required=(action_boundary == "requires_human_approval"),
    )
    matched_companies = (knowledge_payload or {}).get("matched_companies", stock_codes) if knowledge_payload else stock_codes
    return PlannerResponse(
        intent="MIXED_QUERY",
        reply_markdown="\n".join(sections),
        latest_data_date=latest_data_date,
        sources=sources,
        critic_status=critic_status,
        evidence_count=evidence_count,
        matched_companies=matched_companies,
        matched_company_names=_company_names_from_codes(matched_companies),
        matched_themes=matched_themes,
        company_terms=company_terms,
        collaboration_agents=collaboration_agents,
        orchestration_mode="parallel_subagents",
        evidence_status=evidence_status,
        data_freshness=data_freshness,
        risk_status=risk_status,
        conflict_detected=conflict_detected,
        human_approval_required=trail["human_approval_required"],
        action_boundary=action_boundary,
        accountability_trail=trail,
    )


def execute_quant_query(message: str) -> PlannerResponse:
    stock_codes = infer_stock_codes(message)
    company_terms = infer_company_terms(message)
    if not stock_codes:
        return _empty_response(
            intent="QUANT_QUERY",
            message="Quant queries require at least one supported ticker from the Mag 7 universe.",
            company_terms=company_terms,
            critic_status="PASS_WITH_WARNINGS",
        )

    quant_result = run_quant_agent(stock_codes=stock_codes, report_date=date.today().isoformat(), indicators=[])
    payload = quant_result.payload
    evidence_count = len(payload.get("stocks", []))
    data_freshness = compute_data_freshness(payload.get("trade_date"))
    action_boundary = classify_action_boundary(
        intent="QUANT_QUERY",
        critic_status="PASS",
        conflict_detected=False,
        risk_status="UNKNOWN",
        evidence_count=evidence_count,
    )
    collaboration_agents = ["planner", quant_result.agent_id]
    trail = build_accountability_trail(
        participating_agents=collaboration_agents,
        evidence_count=evidence_count,
        evidence_status=compute_evidence_status(evidence_count, None),
        risk_status="UNKNOWN",
        critic_result="PASS",
        conflict_detected=False,
        action_boundary=action_boundary,
        human_approval_required=(action_boundary == "requires_human_approval"),
    )
    reply_lines = [
        "**Quant Analysis**",
        "",
        f"Query: {message}",
        "Collaboration path: Planner -> Quant",
        f"Matched companies: {_format_company_labels(stock_codes)}",
        f"Data date: {payload.get('trade_date') or 'unknown'}",
        "",
    ]
    for item in payload.get("stocks", [])[:3]:
        reply_lines.append(
            f"- {item['name']} ({item['code']}): close={item['close']}, pct_change={item['pct_change']}, "
            f"pe_ttm={item.get('pe_ttm')}, roe={item.get('roe')}, composite_signal={item.get('composite_signal')}"
        )
    if not payload.get("stocks"):
        reply_lines.append("No quant output was produced.")

    return PlannerResponse(
        intent="QUANT_QUERY",
        reply_markdown="\n".join(reply_lines),
        latest_data_date=payload.get("trade_date"),
        sources=["quant_service"],
        critic_status="PASS",
        evidence_count=evidence_count,
        matched_companies=stock_codes,
        matched_company_names=_company_names_from_codes(stock_codes),
        matched_themes=[],
        company_terms=company_terms,
        collaboration_agents=collaboration_agents,
        orchestration_mode="delegated_single_agent",
        evidence_status=trail["evidence_status"],
        data_freshness=data_freshness,
        risk_status="UNKNOWN",
        conflict_detected=False,
        human_approval_required=trail["human_approval_required"],
        action_boundary=action_boundary,
        accountability_trail=trail,
    )


def execute_risk_query(message: str) -> PlannerResponse:
    stock_codes = infer_stock_codes(message)
    company_terms = infer_company_terms(message)
    if not stock_codes:
        return _empty_response(
            intent="RISK_QUERY",
            message="Risk queries require at least one supported ticker from the Mag 7 universe.",
            company_terms=company_terms,
            critic_status="PASS_WITH_WARNINGS",
        )

    equal_weight = round(1 / len(stock_codes), 4)
    portfolio = [{"code": code, "weight": equal_weight} for code in stock_codes]
    risk_result = run_risk_agent(portfolio=portfolio, benchmark="SPY")
    payload = risk_result.payload
    alerts = payload.get("alerts", [])
    risk_status = payload.get("risk_level", "UNKNOWN")
    critic_status = "PASS" if not alerts else "PASS_WITH_WARNINGS"
    conflict_detected = bool(alerts)
    action_boundary = classify_action_boundary(
        intent="RISK_QUERY",
        critic_status=critic_status,
        conflict_detected=conflict_detected,
        risk_status=risk_status,
        evidence_count=len(alerts),
    )
    collaboration_agents = ["planner", risk_result.agent_id]
    trail = build_accountability_trail(
        participating_agents=collaboration_agents,
        evidence_count=len(alerts),
        evidence_status="NONE",
        risk_status=risk_status,
        critic_result=critic_status,
        conflict_detected=conflict_detected,
        action_boundary=action_boundary,
        human_approval_required=(action_boundary == "requires_human_approval"),
    )
    reply = "\n".join(
        [
            "**Risk Analysis**",
            "",
            f"Query: {message}",
            "Collaboration path: Planner -> Risk",
            f"Matched companies: {_format_company_labels(stock_codes)}",
            f"Risk level: {risk_status}",
            f"Alert count: {len(alerts)}",
            f"Alerts: {'; '.join(alerts) if alerts else 'none'}",
            f"**Action boundary**: {action_boundary}",
            f"**Human approval**: {'required' if trail['human_approval_required'] else 'not required'}",
        ]
    )
    return PlannerResponse(
        intent="RISK_QUERY",
        reply_markdown=reply,
        latest_data_date=None,
        sources=["risk_service"],
        critic_status=critic_status,
        evidence_count=len(alerts),
        matched_companies=stock_codes,
        matched_company_names=_company_names_from_codes(stock_codes),
        matched_themes=[],
        company_terms=company_terms,
        collaboration_agents=collaboration_agents,
        orchestration_mode="delegated_single_agent",
        evidence_status="NONE",
        data_freshness="UNKNOWN",
        risk_status=risk_status,
        conflict_detected=conflict_detected,
        human_approval_required=trail["human_approval_required"],
        action_boundary=action_boundary,
        accountability_trail=trail,
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
        if code in text.upper() or any(alias.lower() in text.lower() for alias in aliases):
            matched.append(code)
    return matched


def infer_company_terms(message: str) -> list[str]:
    return extract_company_terms(message)


def format_doc_qa_reply(
    message: str,
    payload: dict,
    *,
    action_boundary: str = "informational_only",
    human_approval_required: bool = False,
) -> str:
    synthesis = payload["synthesis"]
    sources = ", ".join(sorted({item["source"] for item in payload["evidence_pack"]})) or "none"
    latest_date = payload["latest_evidence_date"] or "unknown"
    critic_status = "PASS_WITH_WARNINGS" if payload["coverage_warning"] else "PASS"
    warning = f"\n\nCoverage note: {payload['coverage_warning']}" if payload["coverage_warning"] else ""
    matched_companies = _format_company_labels(payload.get("matched_companies", []))
    matched_themes = ", ".join(payload.get("matched_themes", [])) or "none"
    company_terms = ", ".join(payload.get("company_terms", [])) or "none"
    graph_summary = _format_graph_summary(payload.get("graph_context", {}))
    return (
        f"**{message}**\n\n"
        f"{synthesis}{warning}\n\n"
        f"**Query company terms**: {company_terms}\n"
        f"**Matched companies**: {matched_companies}\n"
        f"**Matched themes**: {matched_themes}\n"
        f"**Collaboration path**: Planner -> Knowledge\n"
        f"{graph_summary}\n\n"
        "---\n"
        f"**Data sources**: {sources}\n"
        f"**Data date**: {latest_date}\n"
        f"**Evidence count**: {len(payload['evidence_pack'])}\n"
        f"**Critic status**: {critic_status}\n"
        f"**Action boundary**: {action_boundary}\n"
        f"**Human approval**: {'required' if human_approval_required else 'not required'}"
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
    report_type_label = "daily report" if intent == "DAILY_REPORT" else "weekly report"
    latest_date = evidence_payload.get("latest_evidence_date") or report_payload.get("report_date")
    count = len(evidence_payload.get("evidence_pack", []))
    critic_status = critic_payload.get("status", "UNKNOWN")
    risk_status = report_payload.get("risk_level", "UNKNOWN")
    conflict_detected = bool(critic_payload.get("errors")) or bool(report_payload.get("has_conflicts"))
    evidence_status = compute_evidence_status(count, critic_payload.get("warnings") and "low" or None)
    data_freshness = compute_data_freshness(latest_date)
    critic_recommended = critic_payload.get("recommended_action_boundary")
    action_boundary = classify_action_boundary(
        intent=intent,
        critic_status=critic_status,
        conflict_detected=conflict_detected,
        risk_status=risk_status,
        evidence_count=count,
        critic_recommended=critic_recommended,
    )
    collaboration_agents = ["planner", "knowledge", "quant", "risk", "report", "critic"]
    trail = build_accountability_trail(
        participating_agents=collaboration_agents,
        evidence_count=count,
        evidence_status=evidence_status,
        risk_status=risk_status,
        critic_result=critic_status,
        conflict_detected=conflict_detected,
        action_boundary=action_boundary,
        human_approval_required=(action_boundary == "requires_human_approval"),
    )
    approval_notice = "Human approval is required before any action is taken.\n\n" if trail["human_approval_required"] else ""
    reply = (
        f"{approval_notice}**{report_type_label.title()} generated**\n\n"
        f"Request: {message}\n"
        f"Report date: {report_payload.get('report_date')}\n"
        f"Report path: {report_payload.get('file_path')}\n"
        f"Collaboration path: Planner -> Knowledge + Quant + Risk -> Report -> Critic\n"
        f"Critic: {critic_status}\n"
        f"Evidence count: {count}\n"
        f"Data date/range: {evidence_payload.get('data_dates_label') or latest_date}\n"
        f"**Action boundary**: {action_boundary}\n"
        f"**Human approval**: {'required' if trail['human_approval_required'] else 'not required'}\n"
        f"Summary: {report_payload.get('feishu_summary')}"
    )
    return PlannerResponse(
        intent=intent,
        reply_markdown=reply,
        latest_data_date=latest_date,
        sources=sources,
        critic_status=critic_status,
        evidence_count=count,
        matched_companies=matched_companies,
        matched_company_names=_company_names_from_codes(matched_companies),
        matched_themes=evidence_payload.get("matched_themes", []),
        company_terms=[],
        collaboration_agents=collaboration_agents,
        orchestration_mode="parallel_subagents",
        evidence_status=evidence_status,
        data_freshness=data_freshness,
        risk_status=risk_status,
        conflict_detected=conflict_detected,
        human_approval_required=trail["human_approval_required"],
        action_boundary=action_boundary,
        accountability_trail=trail,
    )


def _empty_response(intent: str, message: str, company_terms: list[str], critic_status: str) -> PlannerResponse:
    return PlannerResponse(
        intent=intent,
        reply_markdown=message,
        latest_data_date=None,
        sources=[],
        critic_status=critic_status,
        evidence_count=0,
        matched_companies=[],
        matched_company_names=[],
        matched_themes=[],
        company_terms=company_terms,
        collaboration_agents=["planner"],
        orchestration_mode="planner_only",
        evidence_status="NONE",
        data_freshness="UNKNOWN",
        risk_status="UNKNOWN",
        conflict_detected=False,
        human_approval_required=False,
        action_boundary="informational_only",
        accountability_trail=build_accountability_trail(
            participating_agents=["planner"],
            evidence_count=0,
            evidence_status="NONE",
            risk_status="UNKNOWN",
            critic_result=critic_status,
            conflict_detected=False,
            action_boundary="informational_only",
            human_approval_required=False,
        ),
    )


def _company_names_from_codes(codes: list[str]) -> list[str]:
    stocks = load_target_stocks()
    return [str(stocks[code]["name"]) for code in codes if code in stocks]


def _format_company_labels(codes: list[str]) -> str:
    stocks = load_target_stocks()
    labels = []
    for code in codes:
        item = stocks.get(code)
        if item:
            labels.append(f"{item['name']} ({code})")
        else:
            labels.append(code)
    return ", ".join(labels) or "none"


def _format_graph_summary(graph_context: dict) -> str:
    companies = ", ".join(item["name"] for item in graph_context.get("companies", [])[:5]) or "none"
    themes = ", ".join(item["name"] for item in graph_context.get("themes", [])[:5]) or "none"
    industries = ", ".join(item["name"] for item in graph_context.get("industries", [])[:5]) or "none"
    relation_labels = [
        f"{item['src']} -> {item['relation_type']} -> {item['dst']}"
        for item in graph_context.get("relations", [])[:3]
    ]
    relations = "; ".join(relation_labels) or "none"
    return (
        f"**Graph-related companies**: {companies}\n"
        f"**Graph-related themes**: {themes}\n"
        f"**Graph-related industries**: {industries}\n"
        f"**Graph relations**: {relations}"
    )

