from services.common.graph import build_graph_context_payload, extract_document_graph
from services.rag import service as rag_service
from services.rag.knowledge_pipeline import build_evidence_pack


def test_extract_document_graph_builds_company_theme_and_industry_edges():
    document = {
        "id": "doc-1",
        "source": "eastmoney",
        "doc_type": "announcement",
        "title": "贵州茅台关于年度分红的公告",
        "url": "https://example.com/doc-1",
        "company_code": "600519",
        "published_at": "2026-04-06",
    }
    raw = {
        "content": "贵州茅台公告提到白酒消费复苏。",
        "metadata": {
            "primary_company_code": "600519",
            "matched_stocks": [{"code": "600519", "name": "贵州茅台"}],
            "matched_themes": ["消费复苏"],
            "company_terms": ["贵州茅台"],
        },
    }

    graph = extract_document_graph(document, raw)
    entity_keys = {(item["entity_type"], item["entity_key"]) for item in graph["entities"]}
    relation_keys = {
        (item["src_type"], item["relation_type"], item["dst_type"], item["dst_key"])
        for item in graph["relations"]
    }

    assert ("company", "600519") in entity_keys
    assert ("theme", "消费复苏") in entity_keys
    assert ("industry", "食品饮料") in entity_keys
    assert ("company", "announced_in", "announcement", "doc-1") in relation_keys
    assert ("company", "belongs_to_industry", "industry", "食品饮料") in relation_keys
    assert ("company", "has_theme", "theme", "消费复苏") in relation_keys


def test_retrieve_returns_graph_context(monkeypatch):
    monkeypatch.setattr(
        rag_service,
        "_keyword_results",
        lambda *args, **kwargs: [
            {
                "doc_id": "doc-1",
                "title": "贵州茅台公告",
                "source": "eastmoney",
                "url": "https://example.com/doc-1",
                "published_at": "2026-04-06",
                "company_code": "600519",
                "snippet": "公告摘要",
                "score": 0.88,
                "retrieval_method": "keyword",
                "matched_themes": ["消费复苏"],
                "matched_stocks": ["600519"],
            }
        ],
    )
    monkeypatch.setattr(rag_service, "_dense_results", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        rag_service._REPO,
        "get_documents",
        lambda **kwargs: [
            {
                "id": "doc-1",
                "title": "贵州茅台公告",
                "source": "eastmoney",
                "doc_type": "announcement",
                "company_code": "600519",
                "published_at": "2026-04-06",
                "file_path": "",
            }
        ],
    )
    monkeypatch.setattr(
        rag_service._GRAPH_REPO,
        "get_graph_context",
        lambda **kwargs: {
            "companies": [{"type": "company", "key": "600519", "name": "贵州茅台", "metadata": {}}],
            "themes": [{"type": "theme", "key": "消费复苏", "name": "消费复苏", "metadata": {}}],
            "industries": [{"type": "industry", "key": "食品饮料", "name": "食品饮料", "metadata": {}}],
            "relations": [{"src": "贵州茅台", "relation_type": "has_theme", "dst": "消费复苏"}],
            "doc_entity_counts": {"company": 1, "theme": 1},
        },
    )

    payload = rag_service.retrieve(
        query="贵州茅台近期公告",
        stock_codes=["600519"],
        company_terms=["贵州茅台"],
        doc_types=["announcement"],
        date_range={"start": "2026-04-01", "end": "2026-04-06"},
        top_k=5,
        min_score=0.2,
    )

    assert payload["results"][0]["doc_id"] == "doc-1"
    assert payload["graph_context"]["companies"][0]["name"] == "贵州茅台"
    assert payload["graph_context"]["themes"][0]["name"] == "消费复苏"


def test_build_evidence_pack_merges_graph_context(monkeypatch):
    monkeypatch.setattr(
        "services.rag.knowledge_pipeline.service.retrieve",
        lambda **kwargs: {
            "results": [
                {
                    "doc_id": "doc-1",
                    "title": "贵州茅台公告",
                    "source": "eastmoney",
                    "url": "https://example.com/doc-1",
                    "published_at": "2026-04-06",
                    "company_code": "600519",
                    "snippet": "公告摘要",
                    "score": 0.91,
                    "matched_themes": ["消费复苏"],
                    "matched_stocks": ["600519"],
                }
            ],
            "graph_context": build_graph_context_payload(
                [
                    {
                        "id": "company-1",
                        "entity_type": "company",
                        "entity_key": "600519",
                        "name": "贵州茅台",
                        "metadata_json": {},
                    }
                ],
                [],
                [],
            ),
        },
    )

    payload = build_evidence_pack("贵州茅台近期公告", stock_codes=["600519"], min_score=0.1)
    assert payload["graph_context"]["companies"][0]["name"] == "贵州茅台"
