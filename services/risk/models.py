from datetime import datetime

from pydantic import BaseModel


class PortfolioHolding(BaseModel):
    code: str
    weight: float                          # 0.0 ~ 1.0


class RiskCheckRequest(BaseModel):
    portfolio: list[PortfolioHolding]
    benchmark: str = "000300"              # 沪深 300
    lookback_days: int = 90
    run_scenarios: bool = True


class DrawdownRequest(BaseModel):
    stock_codes: list[str]
    lookback_days: int = 90


class IndustryExposure(BaseModel):
    industry: str
    weight: float


class ScenarioLoss(BaseModel):
    scenario: str
    estimated_loss: float


class RiskOutput(BaseModel):
    risk_level: str                        # LOW | MEDIUM | HIGH | CRITICAL
    max_drawdown_90d: float
    volatility_annual: float
    beta: float | None = None
    top_industry_exposure: IndustryExposure | None = None
    industry_breakdown: list[IndustryExposure] = []
    alerts: list[str] = []
    scenario_loss_estimate: dict[str, float] = {}
    generated_at: datetime


class ApiResponse(BaseModel):
    success: bool
    data: dict | None = None
    error: str | None = None
    timestamp: datetime = datetime.now()
