"""Development stub for the retrieval service."""


def retrieve(
    query: str,
    stock_codes: list[str],
    doc_types: list[str],
    date_range: dict | None,
    top_k: int,
    min_score: float,
) -> dict:
    return {
        "query": query,
        "results": [
            {
                "doc_id": "doc_stub_001",
                "title": "[Stub] Apple files quarterly report",
                "source": "sec_edgar",
                "url": "https://www.sec.gov/Archives/doc_stub_001.html",
                "published_at": "2026-04-08T07:45:00+08:00",
                "company_code": stock_codes[0] if stock_codes else "AAPL",
                "snippet": "Apple discussed services growth, hardware demand, and capital returns in the filing summary.",
                "score": 0.92,
                "retrieval_method": "stub",
            }
        ],
        "total_retrieved": 1,
    }


def build_index(doc_ids: list[str], force_rebuild: bool) -> dict:
    return {
        "job_id": "index_stub_001",
        "status": "queued",
        "doc_count": len(doc_ids) if doc_ids else "all",
    }
