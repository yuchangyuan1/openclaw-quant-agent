import time

from services.planner.models import ApiResponse
from services.planner.pipeline import (
    classify_intent,
    execute_daily_report_request,
    execute_doc_qa,
    execute_message,
    execute_quant_query,
    execute_risk_query,
    execute_weekly_report_request,
    format_doc_qa_reply,
)


def test_classify_intent_defaults_to_doc_qa():
    assert classify_intent("Apple latest filing") == "DOC_QA"


def test_classify_intent_risk_query():
    assert classify_intent("What is the portfolio drawdown risk?") == "RISK_QUERY"


def test_classify_intent_daily_and_weekly_report():
    assert classify_intent("Please generate today's daily report") == "DAILY_REPORT"
    assert classify_intent("Please generate this week's weekly report") == "WEEKLY_REPORT"


def test_format_doc_qa_reply_contains_required_fields():
    reply = format_doc_qa_reply(
        "Apple latest filing",
        {
            "synthesis": "Current evidence indicates services growth remained resilient [E001].",
            "coverage_warning": None,
            "latest_evidence_date": "2026-04-05",
            "company_terms": ["Apple"],
            "matched_companies": ["AAPL"],
            "matched_themes": ["Consumer Platforms"],
            "evidence_pack": [{"source": "sec_edgar"}],
            "graph_context": {
                "companies": [{"name": "Apple Inc."}],
                "themes": [{"name": "Consumer Platforms"}],
                "industries": [{"name": "Consumer Electronics"}],
                "relations": [{"src": "Apple Inc.", "relation_type": "has_theme", "dst": "Consumer Platforms"}],
            },
        },
    )
    assert "**Query company terms**" in reply
    assert "**Matched companies**" in reply
    assert "Apple (AAPL)" in reply
    assert "**Matched themes**" in reply
    assert "**Graph-related companies**" in reply
    assert "**Graph-related industries**" in reply
    assert "**Evidence count**" in reply
    assert "**Data sources**" in reply
    assert "**Critic status**" in reply
    assert "**Collaboration path**: Planner -> Knowledge" in reply


def test_execute_doc_qa_returns_planner_response(monkeypatch):
    monkeypatch.setattr("services.planner.pipeline.build_index", lambda *_args, **_kwargs: {"status": "completed"})
    captured = {}

    def fake_run_knowledge_agent(**kwargs):
        captured.update(kwargs)
        return type(
            "KnowledgeResult",
            (),
            {
                "agent_id": "knowledge",
                "payload": {
                    "evidence_pack": [
                        {
                            "source": "sec_edgar",
                            "title": "Apple 10-Q",
                            "published_at": "2026-04-05",
                            "company_code": "AAPL",
                            "matched_themes": ["Consumer Platforms"],
                        }
                    ],
                    "synthesis": "Current evidence [E001] points to steady demand and resilient services growth.",
                    "latest_evidence_date": "2026-04-05",
                    "company_terms": kwargs["company_terms"],
                    "matched_companies": ["AAPL"],
                    "matched_themes": ["Consumer Platforms"],
                    "graph_context": {
                        "companies": [{"name": "Apple Inc."}],
                        "themes": [{"name": "Consumer Platforms"}],
                        "industries": [{"name": "Consumer Electronics"}],
                        "relations": [{"src": "Apple Inc.", "relation_type": "belongs_to_industry", "dst": "Consumer Electronics"}],
                    },
                    "coverage_warning": None,
                },
            },
        )()

    monkeypatch.setattr("services.planner.pipeline.run_knowledge_agent", fake_run_knowledge_agent)

    result = execute_doc_qa("Apple latest filing")
    assert result.intent == "DOC_QA"
    assert result.reply_markdown
    assert "Graph-related companies" in result.reply_markdown
    assert captured["company_terms"] == ["Apple"]
    assert result.company_terms == ["Apple"]
    assert result.matched_companies == ["AAPL"]
    assert result.matched_company_names == ["Apple"]
    assert result.matched_themes == ["Consumer Platforms"]
    assert result.collaboration_agents == ["planner", "knowledge"]


def test_execute_doc_qa_extracts_non_pool_company_terms(monkeypatch):
    monkeypatch.setattr("services.planner.pipeline.build_index", lambda *_args, **_kwargs: {"status": "completed"})
    captured = {}

    def fake_run_knowledge_agent(**kwargs):
        captured.update(kwargs)
        return type(
            "KnowledgeResult",
            (),
            {
                "agent_id": "knowledge",
                "payload": {
                    "evidence_pack": [],
                    "synthesis": "No directly relevant evidence was found.",
                    "latest_evidence_date": None,
                    "company_terms": kwargs["company_terms"],
                    "matched_companies": [],
                    "matched_themes": [],
                    "graph_context": {"companies": [], "themes": [], "industries": [], "relations": []},
                    "coverage_warning": "No relevant filing was found.",
                },
            },
        )()

    monkeypatch.setattr("services.planner.pipeline.run_knowledge_agent", fake_run_knowledge_agent)

    result = execute_doc_qa("Palantir earnings update")
    assert result.company_terms == ["Palantir"]
    assert captured["stock_codes"] == []


def test_execute_quant_query_uses_quant_collaboration(monkeypatch):
    def fake_run_quant_agent(**kwargs):
        return type(
            "QuantResult",
            (),
            {
                "agent_id": "quant",
                "payload": {
                    "trade_date": "2026-04-03",
                    "stocks": [
                        {
                            "code": "AAPL",
                            "name": "Apple Inc.",
                            "close": 210.0,
                            "pct_change": 0.01,
                            "pe_ttm": 21.2,
                            "roe": 24.6,
                            "composite_signal": "POSITIVE",
                        }
                    ],
                },
            },
        )()

    monkeypatch.setattr("services.planner.pipeline.run_quant_agent", fake_run_quant_agent)
    result = execute_quant_query("Apple valuation and momentum")
    assert result.intent == "QUANT_QUERY"
    assert "Collaboration path: Planner -> Quant" in result.reply_markdown
    assert result.collaboration_agents == ["planner", "quant"]


def test_execute_risk_query_uses_risk_collaboration(monkeypatch):
    def fake_run_risk_agent(**kwargs):
        return type(
            "RiskResult",
            (),
            {
                "agent_id": "risk",
                "payload": {"risk_level": "MEDIUM", "alerts": ["Technology concentration is elevated."]},
            },
        )()

    monkeypatch.setattr("services.planner.pipeline.run_risk_agent", fake_run_risk_agent)
    result = execute_risk_query("Apple portfolio risk")
    assert result.intent == "RISK_QUERY"
    assert "Collaboration path: Planner -> Risk" in result.reply_markdown
    assert result.collaboration_agents == ["planner", "risk"]


def test_execute_message_routes_daily_report(monkeypatch):
    monkeypatch.setattr(
        "services.planner.pipeline.execute_daily_report",
        lambda stock_codes=None: type(
            "DailyResult",
            (),
            {
                "report_payload": {
                    "report_date": "2026-04-06",
                    "file_path": "D:/tmp/daily.md",
                    "feishu_summary": "daily summary",
                },
                "critic_payload": {"status": "PASS"},
                "evidence_payload": {
                    "evidence_pack": [{"source": "daily_report_archive"}],
                    "latest_evidence_date": "2026-04-06",
                    "matched_companies": ["AAPL"],
                    "matched_themes": [],
                },
            },
        )(),
    )
    result = execute_message("Please generate Apple's daily report", refresh_index=False)
    assert result.intent == "DAILY_REPORT"
    assert result.critic_status == "PASS"
    assert "daily report generated" in result.reply_markdown.lower()
    assert result.collaboration_agents == ["planner", "knowledge", "quant", "risk", "report", "critic"]


def test_classify_intent_roe_uppercase():
    assert classify_intent("Find companies with ROE above 20%") == "QUANT_QUERY"
    assert classify_intent("PE valuation looks compressed") == "QUANT_QUERY"


def test_api_response_timestamps_are_distinct():
    r1 = ApiResponse(success=True)
    time.sleep(0.01)
    r2 = ApiResponse(success=True)
    assert r1.timestamp != r2.timestamp


def test_execute_daily_and_weekly_report_request(monkeypatch):
    monkeypatch.setattr(
        "services.planner.pipeline.execute_daily_report",
        lambda stock_codes=None: type(
            "DailyResult",
            (),
            {
                "report_payload": {
                    "report_date": "2026-04-06",
                    "file_path": "D:/tmp/daily.md",
                    "feishu_summary": "daily summary",
                },
                "critic_payload": {"status": "PASS_WITH_WARNINGS"},
                "evidence_payload": {
                    "evidence_pack": [{"source": "sec_edgar"}],
                    "latest_evidence_date": "2026-04-06",
                    "matched_companies": ["AAPL"],
                    "matched_themes": [],
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "services.planner.pipeline.execute_weekly_report",
        lambda stock_codes=None: type(
            "WeeklyResult",
            (),
            {
                "report_payload": {
                    "report_date": "2026-04-06",
                    "file_path": "D:/tmp/weekly.md",
                    "feishu_summary": "weekly summary",
                },
                "critic_payload": {"status": "PASS"},
                "evidence_payload": {
                    "evidence_pack": [{"source": "daily_report_archive"}],
                    "latest_evidence_date": "2026-04-06",
                    "matched_companies": ["AAPL", "NVDA"],
                    "matched_themes": [],
                    "data_dates_label": "2026-03-30 to 2026-04-05",
                },
            },
        )(),
    )

    daily = execute_daily_report_request("Please generate Apple's daily report")
    weekly = execute_weekly_report_request("Please generate this week's weekly report")
    assert daily.intent == "DAILY_REPORT"
    assert weekly.intent == "WEEKLY_REPORT"
    assert "D:/tmp/daily.md" in daily.reply_markdown
    assert "D:/tmp/weekly.md" in weekly.reply_markdown
    assert daily.collaboration_agents == ["planner", "knowledge", "quant", "risk", "report", "critic"]
    assert weekly.collaboration_agents == ["planner", "knowledge", "quant", "risk", "report", "critic"]
