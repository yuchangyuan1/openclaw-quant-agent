from datetime import datetime

from fastapi import APIRouter

from .models import ApiResponse, CriticReviewRequest
from .service import review_report

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "critic", "version": "0.1.0-mvp"}


@router.post("/api/v1/critic/review")
def review(req: CriticReviewRequest) -> ApiResponse:
    data = review_report(
        report_payload=req.report_payload,
        evidence_payload=req.evidence_payload,
        quant_payload=req.quant_payload,
        risk_payload=req.risk_payload,
    )
    return ApiResponse(success=True, data=data, timestamp=datetime.now())
