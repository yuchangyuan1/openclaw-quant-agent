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
    }
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/planner/daily-report")
def daily_report(req: PlannerDailyReportRequest) -> ApiResponse:
    result = execute_daily_report(report_date=req.report_date, stock_codes=req.stock_codes or None)
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
    }
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/planner/weekly-report")
def weekly_report(req: PlannerWeeklyReportRequest) -> ApiResponse:
    result = execute_weekly_report(report_date=req.report_date, stock_codes=req.stock_codes or None)
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
