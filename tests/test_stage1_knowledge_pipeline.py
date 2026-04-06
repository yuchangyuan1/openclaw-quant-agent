from services.rag.knowledge_pipeline import (
    build_evidence_pack,
    build_query_variants,
    synthesize_answer,
)


def test_build_query_variants_keeps_base_query():
    variants = build_query_variants("贵州茅台近期新闻", ["600519"])
    assert variants[0] == "贵州茅台近期新闻"
    assert any("600519" in item for item in variants)


def test_synthesize_answer_uses_evidence_ids():
    text = synthesize_answer(
        "测试问题",
        [
            {"evidence_id": "E001", "snippet": "证据片段一"},
            {"evidence_id": "E002", "snippet": "证据片段二"},
        ],
    )
    assert "[E001]" in text
    assert "证据片段二" in text


def test_build_evidence_pack_promotes_matched_stocks_to_companies(monkeypatch):
    captured = []

    def fake_retrieve(**kwargs):
        captured.append(kwargs)
        return {
            "results": [
                {
                    "doc_id": "doc-1",
                    "title": "贵州茅台渠道跟踪",
                    "source": "eastmoney",
                    "url": "https://example.com/doc-1",
                    "published_at": "2026-04-05",
                    "company_code": None,
                    "snippet": "渠道反馈显示动销稳定。",
                    "score": 0.92,
                    "matched_themes": ["消费复苏"],
                    "matched_stocks": ["600519"],
                }
            ]
        }

    monkeypatch.setattr(
        "services.rag.knowledge_pipeline.service.retrieve",
        fake_retrieve,
    )

    payload = build_evidence_pack("贵州茅台近期公告", stock_codes=["600519"], min_score=0.1)
    assert captured[0]["company_terms"] == ["贵州茅台"]
    assert payload["company_terms"] == ["贵州茅台"]
    assert payload["matched_companies"] == ["600519"]
    assert payload["matched_themes"] == ["消费复苏"]
    assert payload["evidence_pack"][0]["matched_stocks"] == ["600519"]
