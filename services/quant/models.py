from datetime import datetime

from pydantic import BaseModel


class DailyRequest(BaseModel):
    stock_codes: list[str]
    date: str | None = None             # YYYY-MM-DD，默认最新交易日
    indicators: list[str] = []             # price | volume | ma | momentum，为空则全部


class BatchHistRequest(BaseModel):
    stock_codes: list[str]
    start_date: str                        # YYYY-MM-DD
    end_date: str | None = None
    adjust: str = "qfq"


class FactorRequest(BaseModel):
    stock_codes: list[str]
    factors: list[str]                     # momentum_1m | pe_ttm | pb | roe | revenue_growth | industry_pe_percentile | composite_score
    date: str | None = None


class StockMetric(BaseModel):
    code: str
    name: str
    close: float
    pct_change: float
    volume: int
    turnover_rate: float
    ma5: float | None = None
    ma20: float | None = None
    ma_signal: str | None = None        # bullish | bearish | neutral
    momentum_5d: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    roe: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    revenue_growth: float | None = None
    net_profit_growth: float | None = None
    technical_score: float | None = None
    fundamental_score: float | None = None
    valuation_score: float | None = None
    composite_score: float | None = None
    composite_signal: str | None = None
    data_date: str


class ApiResponse(BaseModel):
    success: bool
    data: dict | None = None
    error: str | None = None
    timestamp: datetime = datetime.now()
