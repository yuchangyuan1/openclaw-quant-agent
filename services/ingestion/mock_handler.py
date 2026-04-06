"""
Ingestion 服务 Stub 实现（阶段 0）
返回硬编码 fixture 数据，接口与 docs/mock-stubs.md 对齐。
阶段 1 实现真实采集逻辑后，替换此文件，router.py 不变。
"""

from datetime import datetime, timezone


def trigger_ingest(source: str, date: str | None, stock_codes: list[str]) -> dict:
    return {
        "job_id": f"ingest_{(date or datetime.now().strftime('%Y%m%d'))}_stub",
        "status": "queued",
        "estimated_docs": 120,
    }


def get_job_status(job_id: str) -> dict:
    return {
        "job_id": job_id,
        "status": "completed",
        "docs_collected": 118,
        "docs_failed": 2,
        "started_at": "2026-04-07T08:30:00+08:00",
        "finished_at": "2026-04-07T08:35:42+08:00",
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
        "source": source or "eastmoney",
        "doc_type": doc_type or "news",
        "title": "[测试] 贵州茅台发布2026年一季报，净利润同比增长12%",
        "url": "https://finance.eastmoney.com/stub/001.html",
        "company_code": stock_code or "600519",
        "published_at": "2026-04-07T07:45:00+08:00",
        "is_indexed": True,
    }
    return {"total": 1, "items": [stub_item]}
