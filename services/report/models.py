from datetime import datetime

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
    data: dict | None = None
    error: str | None = None
    timestamp: datetime = datetime.now()
