from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DateRange(BaseModel):
    start: str    # YYYY-MM-DD
    end: str      # YYYY-MM-DD


class RetrieveRequest(BaseModel):
    query: str
    stock_codes: list[str] = []
    company_terms: list[str] = []
    doc_types: list[str] = []              # news | announcement | research_report
    date_range: Optional[DateRange] = None
    top_k: int = 5
    min_score: float = 0.7


class RetrieveResult(BaseModel):
    doc_id: str
    title: str
    source: str
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    company_code: Optional[str] = None
    snippet: str
    score: float
    retrieval_method: str = "dense+bm25+rerank"


class IndexBuildRequest(BaseModel):
    doc_ids: list[str] = []
    force_rebuild: bool = False


class ApiResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    timestamp: datetime = datetime.now()
