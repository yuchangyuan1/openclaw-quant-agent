from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from services.critic.service import review_report
from services.quant.service import daily_summary
from services.rag.knowledge_pipeline import build_evidence_pack
from services.report.service import build_report, finalize_report_with_critic
from services.risk.service import risk_check


@dataclass
class AgentCollaborationResult:
    agent_id: str
    task_type: str
    payload: dict[str, Any]
    backend: str = "service"
    coordination_mode: str = "planner_delegated"


def run_parallel_collaboration(tasks: dict[str, Any]) -> dict[str, AgentCollaborationResult]:
    results: dict[str, AgentCollaborationResult] = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(task): name for name, task in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()
    return results


def run_knowledge_agent(
    *,
    question: str,
    stock_codes: list[str] | None = None,
    company_terms: list[str] | None = None,
    doc_types: list[str] | None = None,
    days: int = 7,
    top_k: int = 5,
    min_score: float = 0.25,
) -> AgentCollaborationResult:
    payload = build_evidence_pack(
        question=question,
        stock_codes=stock_codes,
        company_terms=company_terms,
        doc_types=doc_types,
        days=days,
        top_k=top_k,
        min_score=min_score,
    )
    return AgentCollaborationResult(agent_id="knowledge", task_type="evidence_pack", payload=payload)


def run_quant_agent(
    *,
    stock_codes: list[str],
    report_date: str,
    indicators: list[str] | None = None,
) -> AgentCollaborationResult:
    payload = daily_summary(stock_codes, report_date, indicators or [])
    return AgentCollaborationResult(agent_id="quant", task_type="daily_summary", payload=payload)


def run_risk_agent(
    *,
    portfolio: list[dict[str, Any]],
    benchmark: str = "000300",
    lookback_days: int = 90,
    run_scenarios: bool = True,
) -> AgentCollaborationResult:
    payload = risk_check(
        portfolio=portfolio,
        benchmark=benchmark,
        lookback_days=lookback_days,
        run_scenarios=run_scenarios,
    )
    return AgentCollaborationResult(agent_id="risk", task_type="risk_check", payload=payload)


def run_report_agent(
    *,
    report_type: str,
    report_date: str,
    evidence_payload: dict[str, Any],
    quant_payload: dict[str, Any],
    risk_payload: dict[str, Any],
    critic_status: str = "PENDING",
) -> AgentCollaborationResult:
    payload = build_report(
        report_type=report_type,
        report_date=report_date,
        evidence_payload=evidence_payload,
        quant_payload=quant_payload,
        risk_payload=risk_payload,
        critic_status=critic_status,
    )
    return AgentCollaborationResult(agent_id="report", task_type="report_build", payload=payload)


def run_critic_agent(
    *,
    report_payload: dict[str, Any],
    evidence_payload: dict[str, Any],
    quant_payload: dict[str, Any],
    risk_payload: dict[str, Any],
) -> AgentCollaborationResult:
    payload = review_report(
        report_payload=report_payload,
        evidence_payload=evidence_payload,
        quant_payload=quant_payload,
        risk_payload=risk_payload,
    )
    return AgentCollaborationResult(agent_id="critic", task_type="report_review", payload=payload)


def finalize_report_stage(
    *,
    report_payload: dict[str, Any],
    critic_payload: dict[str, Any],
) -> AgentCollaborationResult:
    payload = finalize_report_with_critic(report_payload, critic_payload)
    return AgentCollaborationResult(agent_id="planner", task_type="report_finalize", payload=payload, backend="planner")
