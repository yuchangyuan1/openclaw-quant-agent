from datetime import datetime

from pydantic import BaseModel


class CriticReviewRequest(BaseModel):
    report_payload: dict
    evidence_payload: dict = {}
    quant_payload: dict = {}
    risk_payload: dict = {}


class ApiResponse(BaseModel):
    success: bool
    data: dict | None = None
    error: str | None = None
    timestamp: datetime = datetime.now()
