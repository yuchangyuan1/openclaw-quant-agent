from services.common.graph import build_graph_context_payload, extract_document_graph
from services.rag import service as rag_service
from services.rag.knowledge_pipeline import build_evidence_pack


def test_extract_document_graph_builds_company_theme_and_industry_edges():
    document = {
        "id": "doc-1",
        "source": "sec_edgar",
        "doc_type": "filing",
        "title": "Apple files quarterly report",
        "url": "https://www.sec.gov/Archives/doc-1",
        "company_code": "AAPL",
        "published_at": "2026-04-06",
    }
    raw = {
        "content": "Apple discussed AI features, services growth, and hardware demand.",
        "metadata": {
            "primary_company_code": "AAPL",
            "matched_stocks": [{"code": "AAPL", "name": "Apple Inc."}],
            "matched_themes": ["Consumer Platforms"],
            "company_terms": ["Apple"],
        },
    }

    graph = extract_document_graph(document, raw)
    entity_keys = {(item["entity_type"], item["entity_key"]) for item in graph["entities"]}
    relation_keys = {
        (item["src_type"], item["relation_type"], item["dst_type"], item["dst_key"])
        for item in graph["relations"]
    }

    assert ("company", "AAPL") in entity_keys
    assert ("theme", "consumerplatforms") in entity_keys
    assert ("industry", "consumerelectronics") in entity_keys
    assert ("company", "mentioned_in", "filing", "doc-1") in relation_keys
    assert ("company", "belongs_to_industry", "industry", "consumerelectronics") in relation_keys
    assert ("company", "has_theme", "theme", "consumerplatforms") in relation_keys


def test_retrieve_returns_graph_context(monkeypatch):
    monkeypatch.setattr(
        rag_service,
        "_keyword_results",
        lambda *args, **kwargs: [
            {
                "doc_id": "doc-1",
                "title": "Apple 10-Q",
                "source": "sec_edgar",
                "url": "https://www.sec.gov/Archives/doc-1",
                "published_at": "2026-04-06",
                "company_code": "AAPL",
                "snippet": "Quarterly filing summary",
                "score": 0.88,
                "retrieval_method": "keyword",
                "matched_themes": ["Consumer Platforms"],
                "matched_stocks": ["AAPL"],
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
                "title": "Apple 10-Q",
                "source": "sec_edgar",
                "doc_type": "filing",
                "company_code": "AAPL",
                "published_at": "2026-04-06",
                "file_path": "",
            }
        ],
    )
    monkeypatch.setattr(
        rag_service._GRAPH_REPO,
        "get_graph_context",
        lambda **kwargs: {
            "companies": [{"type": "company", "key": "AAPL", "name": "Apple Inc.", "metadata": {}}],
            "themes": [{"type": "theme", "key": "Consumer Platforms", "name": "Consumer Platforms", "metadata": {}}],
            "industries": [{"type": "industry", "key": "Consumer Electronics", "name": "Consumer Electronics", "metadata": {}}],
            "relations": [{"src": "Apple Inc.", "relation_type": "has_theme", "dst": "Consumer Platforms"}],
            "doc_entity_counts": {"company": 1, "theme": 1},
        },
    )

    payload = rag_service.retrieve(
        query="Apple latest filing",
        stock_codes=["AAPL"],
        company_terms=["Apple"],
        doc_types=["filing"],
        date_range={"start": "2026-04-01", "end": "2026-04-06"},
        top_k=5,
        min_score=0.2,
    )

    assert payload["results"][0]["doc_id"] == "doc-1"
    assert payload["graph_context"]["companies"][0]["name"] == "Apple Inc."
    assert payload["graph_context"]["themes"][0]["name"] == "Consumer Platforms"


def test_build_evidence_pack_merges_graph_context(monkeypatch):
    monkeypatch.setattr(
        "services.rag.knowledge_pipeline.service.retrieve",
        lambda **kwargs: {
            "results": [
                {
                    "doc_id": "doc-1",
                    "title": "Apple 10-Q",
                    "source": "sec_edgar",
                    "url": "https://www.sec.gov/Archives/doc-1",
                    "published_at": "2026-04-06",
                    "company_code": "AAPL",
                    "snippet": "Quarterly filing summary",
                    "score": 0.91,
                    "matched_themes": ["Consumer Platforms"],
                    "matched_stocks": ["AAPL"],
                }
            ],
            "graph_context": build_graph_context_payload(
                [
                    {
                        "id": "company-1",
                        "entity_type": "company",
                        "entity_key": "AAPL",
                        "name": "Apple Inc.",
                        "metadata_json": {},
                    }
                ],
                [],
                [],
            ),
        },
    )

    payload = build_evidence_pack("Apple latest filing", stock_codes=["AAPL"], min_score=0.1)
    assert payload["graph_context"]["companies"][0]["name"] == "Apple Inc."
