from services.rag.knowledge_pipeline import (
    build_evidence_pack,
    build_query_variants,
    synthesize_answer,
)


def test_build_query_variants_keeps_base_query():
    variants = build_query_variants("Apple latest filing", ["AAPL"])
    assert variants[0] == "Apple latest filing"
    assert any("AAPL" in item for item in variants)
    assert any("10-K" in item or "10-Q" in item or "8-K" in item for item in variants)


def test_synthesize_answer_uses_evidence_ids():
    text = synthesize_answer(
        "Apple latest filing",
        [
            {"evidence_id": "E001", "snippet": "Apple reported stronger services growth."},
            {"evidence_id": "E002", "snippet": "Management reaffirmed margin discipline."},
        ],
    )
    assert "[E001]" in text
    assert "margin discipline" in text


def test_build_evidence_pack_promotes_matched_stocks_to_companies(monkeypatch):
    captured = []

    def fake_retrieve(**kwargs):
        captured.append(kwargs)
        return {
            "results": [
                {
                    "doc_id": "doc-1",
                    "title": "Apple files Form 10-Q",
                    "source": "sec_edgar",
                    "url": "https://www.sec.gov/Archives/doc-1",
                    "published_at": "2026-04-05",
                    "company_code": None,
                    "snippet": "Apple discussed iPhone demand and services revenue.",
                    "score": 0.92,
                    "matched_themes": ["Consumer Platforms"],
                    "matched_stocks": ["AAPL"],
                }
            ]
        }

    monkeypatch.setattr("services.rag.knowledge_pipeline.service.retrieve", fake_retrieve)

    payload = build_evidence_pack("Apple latest filing", stock_codes=["AAPL"], min_score=0.1)
    assert captured[0]["company_terms"] == ["Apple"]
    assert payload["company_terms"] == ["Apple"]
    assert payload["matched_companies"] == ["AAPL"]
    assert payload["matched_themes"] == ["Consumer Platforms"]
    assert payload["evidence_pack"][0]["matched_stocks"] == ["AAPL"]
