from datetime import datetime

from fastapi import APIRouter

from .models import (
    ApiResponse,
    PlannerAlertSummaryRequest,
    PlannerClassifyRequest,
    PlannerDailyReportRequest,
    PlannerQueryRequest,
    PlannerReplayRunRequest,
    PlannerRunLogsRequest,
    PlannerWeeklyReportRequest,
)
from .pipeline import classify_intent, execute_message
from .report_pipeline import (
    execute_daily_report,
    execute_weekly_report,
    list_recent_runs,
    replay_run,
    summarize_alerts,
)

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "planner", "version": "0.2.0-mvp"}


@router.post("/api/v1/planner/classify")
def classify(req: PlannerClassifyRequest) -> ApiResponse:
    data = {"intent": classify_intent(req.message)}
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/planner/query")
def query(req: PlannerQueryRequest) -> ApiResponse:
    result = execute_message(req.message, refresh_index=req.refresh_index)
    data = {
        "intent": result.intent,
        "reply_markdown": result.reply_markdown,
        "latest_data_date": result.latest_data_date,
        "sources": result.sources,
        "critic_status": result.critic_status,
        "evidence_count": result.evidence_count,
        "company_terms": result.company_terms,
        "matched_companies": result.matched_companies,
        "matched_company_names": result.matched_company_names,
        "matched_themes": result.matched_themes,
        "collaboration_agents": result.collaboration_agents,
        "orchestration_mode": result.orchestration_mode,
        # Ethics fields
        "evidence_status": result.evidence_status,
        "data_freshness": result.data_freshness,
        "risk_status": result.risk_status,
        "conflict_detected": result.conflict_detected,
        "human_approval_required": result.human_approval_required,
        "action_boundary": result.action_boundary,
        "accountability_trail": result.accountability_trail,
    }
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


def _ethics_fields_from_report_result(result) -> dict:
    """Extract ethics metadata fields to include in report endpoint responses."""
    from services.common.ethics import (
        build_accountability_trail,
        classify_action_boundary,
        compute_data_freshness,
        compute_evidence_status,
    )
    critic_status = result.critic_payload.get("status", "UNKNOWN")
    risk_status = result.risk_payload.get("risk_level", "UNKNOWN")
    evidence_count = len(result.evidence_payload.get("evidence_pack", []))
    conflict_detected = bool(result.critic_payload.get("errors")) or bool(result.report_payload.get("has_conflicts"))
    evidence_status = compute_evidence_status(evidence_count, result.critic_payload.get("warnings") and "low" or None)
    data_freshness = compute_data_freshness(result.evidence_payload.get("latest_evidence_date"))
    critic_recommended = result.critic_payload.get("recommended_action_boundary")
    action_boundary = classify_action_boundary(
        intent="DAILY_REPORT", critic_status=critic_status, conflict_detected=conflict_detected,
        risk_status=risk_status, evidence_count=evidence_count, critic_recommended=critic_recommended,
    )
    human_approval_required = action_boundary == "requires_human_approval"
    trail = build_accountability_trail(
        participating_agents=["planner", "knowledge", "quant", "risk", "report", "critic"],
        evidence_count=evidence_count, evidence_status=evidence_status,
        risk_status=risk_status, critic_result=critic_status,
        conflict_detected=conflict_detected, action_boundary=action_boundary,
        human_approval_required=human_approval_required,
    )
    if human_approval_required and "feishu_summary" in result.report_payload:
        result.report_payload["feishu_summary"] = (
            "【⚠ 需要人工审批后方可执行任何操作】\n" + result.report_payload["feishu_summary"]
        )
    return {
        "evidence_status": evidence_status,
        "data_freshness": data_freshness,
        "risk_status": risk_status,
        "conflict_detected": conflict_detected,
        "human_approval_required": human_approval_required,
        "action_boundary": action_boundary,
        "accountability_trail": trail,
    }


@router.post("/api/v1/planner/daily-report")
def daily_report(req: PlannerDailyReportRequest) -> ApiResponse:
    result = execute_daily_report(report_date=req.report_date, stock_codes=req.stock_codes or None)
    ethics = _ethics_fields_from_report_result(result)
    data = {
        "report": result.report_payload,
        "critic": result.critic_payload,
        "evidence": {
            "count": len(result.evidence_payload.get("evidence_pack", [])),
            "latest_evidence_date": result.evidence_payload.get("latest_evidence_date"),
        },
        "quant": {"trade_date": result.quant_payload.get("trade_date")},
        "risk": {"risk_level": result.risk_payload.get("risk_level")},
        "run": {"run_log_id": result.run_log_id, "attempts": result.attempts},
        **ethics,
    }
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/planner/weekly-report")
def weekly_report(req: PlannerWeeklyReportRequest) -> ApiResponse:
    result = execute_weekly_report(report_date=req.report_date, stock_codes=req.stock_codes or None)
    ethics = _ethics_fields_from_report_result(result)
    data = {
        "report": result.report_payload,
        "critic": result.critic_payload,
        "evidence": {
            "count": len(result.evidence_payload.get("evidence_pack", [])),
            "latest_evidence_date": result.evidence_payload.get("latest_evidence_date"),
            "week_range": result.evidence_payload.get("week_range"),
            "daily_report_count": result.evidence_payload.get("daily_report_count", 0),
        },
        "quant": {"trade_date": result.quant_payload.get("trade_date")},
        "risk": {"risk_level": result.risk_payload.get("risk_level")},
        "run": {"run_log_id": result.run_log_id, "attempts": result.attempts},
        **ethics,
    }
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/planner/run-logs")
def run_logs(req: PlannerRunLogsRequest) -> ApiResponse:
    data = {"items": list_recent_runs(limit=req.limit, job_type=req.job_type, status=req.status)}
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/planner/run-logs/replay")
def replay(req: PlannerReplayRunRequest) -> ApiResponse:
    data = replay_run(req.run_id)
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/planner/alerts/summary")
def alert_summary(req: PlannerAlertSummaryRequest) -> ApiResponse:
    data = summarize_alerts(limit=req.limit)
    return ApiResponse(success=True, data=data, timestamp=datetime.now())
