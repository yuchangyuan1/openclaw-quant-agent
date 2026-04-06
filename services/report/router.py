from datetime import datetime

from fastapi import APIRouter

from .models import ApiResponse, ReportBuildRequest
from .service import build_report

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "report", "version": "0.1.0-mvp"}


@router.post("/api/v1/report/build")
def build(req: ReportBuildRequest) -> ApiResponse:
    data = build_report(
        report_type=req.report_type,
        report_date=req.report_date,
        evidence_payload=req.evidence_payload,
        quant_payload=req.quant_payload,
        risk_payload=req.risk_payload,
        critic_status=req.critic_status,
    )
    return ApiResponse(success=True, data=data, timestamp=datetime.now())
