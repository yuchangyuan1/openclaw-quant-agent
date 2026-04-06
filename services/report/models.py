from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ReportBuildRequest(BaseModel):
    report_type: str = "daily"
    report_date: str
    evidence_payload: dict = {}
    quant_payload: dict = {}
    risk_payload: dict = {}
    critic_status: str = "PENDING"


class ApiResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    timestamp: datetime = datetime.now()
