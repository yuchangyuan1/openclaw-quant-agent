from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class IngestTriggerRequest(BaseModel):
    source: str = "all"
    date: Optional[str] = None
    stock_codes: list[str] = Field(default_factory=list)
    target_pool: bool = False
    incremental: bool = False
    lookback_days: int = Field(default=3, ge=1, le=30)
    per_stock_limit: int = Field(default=3, ge=1, le=20)
    task_name: Optional[str] = None


class TargetPoolSyncRequest(BaseModel):
    source: str = "all"
    lookback_days: int = Field(default=2, ge=1, le=30)
    per_stock_limit: int = Field(default=4, ge=1, le=20)
    date: Optional[str] = None
    task_name: str = "target_pool_incremental_sync"


class IngestJobStatus(BaseModel):
    job_id: str
    status: str
    docs_collected: int = 0
    docs_failed: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class DocumentItem(BaseModel):
    id: str
    source: str
    doc_type: str
    title: str
    url: Optional[str] = None
    company_code: Optional[str] = None
    published_at: Optional[datetime] = None
    is_indexed: bool = False


class ApiResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
