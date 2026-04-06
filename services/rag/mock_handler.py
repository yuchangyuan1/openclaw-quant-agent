"""
RAG 服务 Stub 实现（阶段 0）
阶段 1 替换为真实的混合检索（Dense + BM25 + rerank-2.5）。
"""


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
                "title": "[测试] 贵州茅台发布2026年一季报，净利润同比增长12%",
                "source": "eastmoney",
                "url": "https://finance.eastmoney.com/stub/001.html",
                "published_at": "2026-04-07T07:45:00+08:00",
                "company_code": stock_codes[0] if stock_codes else "600519",
                "snippet": "贵州茅台今日发布2026年一季报，实现营业收入XXX亿元，净利润XXX亿元，同比增长12%……（stub 数据）",
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
