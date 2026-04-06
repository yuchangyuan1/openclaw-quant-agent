from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PlannerQueryRequest(BaseModel):
    message: str
    refresh_index: bool = True


class PlannerClassifyRequest(BaseModel):
    message: str


class PlannerDailyReportRequest(BaseModel):
    report_date: Optional[str] = None
    stock_codes: list[str] = Field(default_factory=list)


class PlannerWeeklyReportRequest(BaseModel):
    report_date: Optional[str] = None
    stock_codes: list[str] = Field(default_factory=list)


class PlannerRunLogsRequest(BaseModel):
    limit: int = 20
    job_type: Optional[str] = None
    status: Optional[str] = None


class PlannerReplayRunRequest(BaseModel):
    run_id: str


class PlannerAlertSummaryRequest(BaseModel):
    limit: int = 50


class ApiResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    timestamp: datetime = datetime.now()
