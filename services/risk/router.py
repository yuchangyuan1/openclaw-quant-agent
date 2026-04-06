from datetime import datetime

from fastapi import APIRouter

from . import service
from .models import ApiResponse, DrawdownRequest, RiskCheckRequest

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "risk", "version": "0.2.0-mvp"}


@router.post("/api/v1/risk/check")
def risk_check(req: RiskCheckRequest) -> ApiResponse:
    portfolio = [h.model_dump() for h in req.portfolio]
    data = service.risk_check(portfolio, req.benchmark, req.lookback_days, req.run_scenarios)
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/risk/drawdown")
def drawdown(req: DrawdownRequest) -> ApiResponse:
    data = service.drawdown_analysis(req.stock_codes, req.lookback_days)
    return ApiResponse(success=True, data=data, timestamp=datetime.now())
