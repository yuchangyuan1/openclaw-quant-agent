from datetime import datetime

from pydantic import BaseModel, Field


class PlannerQueryRequest(BaseModel):
    message: str
    refresh_index: bool = True


class PlannerClassifyRequest(BaseModel):
    message: str


class PlannerDailyReportRequest(BaseModel):
    report_date: str | None = None
    stock_codes: list[str] = Field(default_factory=list)


class PlannerWeeklyReportRequest(BaseModel):
    report_date: str | None = None
    stock_codes: list[str] = Field(default_factory=list)


class PlannerRunLogsRequest(BaseModel):
    limit: int = 20
    job_type: str | None = None
    status: str | None = None


class PlannerReplayRunRequest(BaseModel):
    run_id: str


class PlannerAlertSummaryRequest(BaseModel):
    limit: int = 50


class ApiResponse(BaseModel):
    success: bool
    data: dict | None = None
    error: str | None = None
    timestamp: datetime = datetime.now()
