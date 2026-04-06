from datetime import datetime

from fastapi import APIRouter

from . import service
from .models import ApiResponse, BatchHistRequest, DailyRequest, FactorRequest

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "quant", "version": "0.3.0-fundamental"}


@router.post("/api/v1/quant/daily")
def daily_summary(req: DailyRequest) -> ApiResponse:
    data = service.daily_summary(req.stock_codes, req.date, req.indicators)
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/quant/batch_hist")
def batch_hist(req: BatchHistRequest) -> ApiResponse:
    data = service.batch_hist(req.stock_codes, req.start_date, req.end_date, req.adjust)
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/quant/factor")
def factor_values(req: FactorRequest) -> ApiResponse:
    data = service.factor_values(req.stock_codes, req.factors, req.date)
    return ApiResponse(success=True, data=data, timestamp=datetime.now())
