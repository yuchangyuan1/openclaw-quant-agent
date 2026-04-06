from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from . import service
from .models import ApiResponse, IngestTriggerRequest, TargetPoolSyncRequest

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "ingestion", "version": "0.2.0-mvp"}


@router.post("/api/v1/ingest/trigger")
def trigger_ingest(req: IngestTriggerRequest) -> ApiResponse:
    data = service.trigger_ingest(
        req.source,
        req.date,
        req.stock_codes,
        target_pool=req.target_pool,
        incremental=req.incremental,
        lookback_days=req.lookback_days,
        per_stock_limit=req.per_stock_limit,
        task_name=req.task_name,
    )
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/ingest/target-pool/sync")
def trigger_target_pool_sync(req: TargetPoolSyncRequest) -> ApiResponse:
    data = service.trigger_target_pool_sync(
        source=req.source,
        date=req.date,
        lookback_days=req.lookback_days,
        per_stock_limit=req.per_stock_limit,
        task_name=req.task_name,
    )
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.get("/api/v1/ingest/status/{job_id}")
def get_status(job_id: str) -> ApiResponse:
    data = service.get_job_status(job_id)
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.get("/api/v1/documents")
def list_documents(
    date: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    stock_code: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ApiResponse:
    data = service.list_documents(date, source, stock_code, doc_type, limit, offset)
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.get("/api/v1/ingest/tasks")
def list_ingestion_tasks() -> ApiResponse:
    data = service.list_tasks()
    return ApiResponse(success=True, data=data, timestamp=datetime.now())
