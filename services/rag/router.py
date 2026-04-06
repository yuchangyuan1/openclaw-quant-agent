from datetime import datetime

from fastapi import APIRouter

from . import service
from .models import ApiResponse, IndexBuildRequest, RetrieveRequest

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "rag", "version": "0.2.0-mvp"}


@router.post("/api/v1/retrieve")
def retrieve(req: RetrieveRequest) -> ApiResponse:
    date_range = req.date_range.model_dump() if req.date_range else None
    data = service.retrieve(
        req.query,
        req.stock_codes,
        req.company_terms,
        req.doc_types,
        date_range,
        req.top_k,
        req.min_score,
    )
    return ApiResponse(success=True, data=data, timestamp=datetime.now())


@router.post("/api/v1/index/build")
def build_index(req: IndexBuildRequest) -> ApiResponse:
    data = service.build_index(req.doc_ids, req.force_rebuild)
    return ApiResponse(success=True, data=data, timestamp=datetime.now())
