"""Development stub for the ingestion service."""

from datetime import datetime


def trigger_ingest(source: str, date: str | None, stock_codes: list[str]) -> dict:
    return {
        "job_id": f"ingest_{(date or datetime.now().strftime('%Y%m%d'))}_stub",
        "status": "queued",
        "estimated_docs": 14,
    }


def get_job_status(job_id: str) -> dict:
    return {
        "job_id": job_id,
        "status": "completed",
        "docs_collected": 12,
        "docs_failed": 0,
        "started_at": "2026-04-08T08:30:00+08:00",
        "finished_at": "2026-04-08T08:31:42+08:00",
    }


def list_documents(
    date: str | None = None,
    source: str | None = None,
    stock_code: str | None = None,
    doc_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    stub_item = {
        "id": "doc_stub_001",
        "source": source or "sec_edgar",
        "doc_type": doc_type or "filing",
        "title": "[Stub] Apple files quarterly report",
        "url": "https://www.sec.gov/Archives/doc_stub_001.html",
        "company_code": stock_code or "AAPL",
        "published_at": "2026-04-08T07:45:00+08:00",
        "is_indexed": True,
    }
    return {"total": 1, "items": [stub_item]}
