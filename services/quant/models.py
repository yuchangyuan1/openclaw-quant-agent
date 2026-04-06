from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DailyRequest(BaseModel):
    stock_codes: list[str]
    date: Optional[str] = None             # YYYY-MM-DD，默认最新交易日
    indicators: list[str] = []             # price | volume | ma | momentum，为空则全部


class BatchHistRequest(BaseModel):
    stock_codes: list[str]
    start_date: str                        # YYYY-MM-DD
    end_date: Optional[str] = None
    adjust: str = "qfq"


class FactorRequest(BaseModel):
    stock_codes: list[str]
    factors: list[str]                     # momentum_1m | pe_ttm | pb | roe | revenue_growth | industry_pe_percentile | composite_score
    date: Optional[str] = None


class StockMetric(BaseModel):
    code: str
    name: str
    close: float
    pct_change: float
    volume: int
    turnover_rate: float
    ma5: Optional[float] = None
    ma20: Optional[float] = None
    ma_signal: Optional[str] = None        # bullish | bearish | neutral
    momentum_5d: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    gross_margin: Optional[float] = None
    net_margin: Optional[float] = None
    revenue_growth: Optional[float] = None
    net_profit_growth: Optional[float] = None
    technical_score: Optional[float] = None
    fundamental_score: Optional[float] = None
    valuation_score: Optional[float] = None
    composite_score: Optional[float] = None
    composite_signal: Optional[str] = None
    data_date: str


class ApiResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    timestamp: datetime = datetime.now()
