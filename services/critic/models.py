from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CriticReviewRequest(BaseModel):
    report_payload: dict
    evidence_payload: dict = {}
    quant_payload: dict = {}
    risk_payload: dict = {}


class ApiResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    timestamp: datetime = datetime.now()
