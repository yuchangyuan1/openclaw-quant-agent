from pathlib import Path

from fastapi.testclient import TestClient

from services.critic.service import review_report
from services.planner.main import app as planner_app
from services.planner.report_pipeline import execute_weekly_report
from services.report.service import build_report


def test_report_service_archives_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    payload = build_report(
        report_type="daily",
        report_date="2026-04-05",
        evidence_payload={
            "evidence_pack": [{"evidence_id": "E001", "title": "Apple 10-Q", "source": "sec_edgar", "published_at": "2026-04-05"}],
            "synthesis": "The latest filing highlighted stable demand and disciplined capital returns.",
            "matched_companies": ["AAPL"],
            "matched_themes": ["Consumer Platforms"],
            "latest_evidence_date": "2026-04-05",
        },
        quant_payload={
            "trade_date": "2026-04-03",
            "market_summary": {"tracked_avg_pct_change": 0.5, "advancing_stocks": 2, "declining_stocks": 1},
            "stocks": [{"code": "AAPL", "name": "Apple Inc.", "close": 210.0, "pct_change": 0.01, "ma5": 209.0, "ma20": 205.0, "ma_signal": "bullish"}],
        },
        risk_payload={"risk_level": "MEDIUM", "alerts": ["Consumer electronics exposure is concentrated."], "industry_breakdown": [{"industry": "Consumer Electronics", "weight": 0.4}]},
        critic_status="PENDING",
    )
    path = Path(payload["file_path"])
    assert path.exists()
    assert "Critic status: PENDING" in path.read_text(encoding="utf-8")


def test_planner_daily_report_endpoint_returns_critic_result(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    client = TestClient(planner_app)
    response = client.post("/api/v1/planner/daily-report", json={"report_date": "2026-04-05", "stock_codes": ["AAPL", "NVDA"]})
    payload = response.json()["data"]
    assert response.status_code == 200
    assert payload["report"]["report_type"] == "daily"
    assert payload["critic"]["status"] in {"PASS", "PASS_WITH_WARNINGS", "FAIL"}
    assert Path(payload["report"]["file_path"]).exists()


def test_execute_weekly_report_aggregates_archived_dailies(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    build_report(
        report_type="daily",
        report_date="2026-03-31",
        evidence_payload={"evidence_pack": [], "synthesis": "day1", "matched_companies": ["AAPL"], "matched_themes": [], "latest_evidence_date": "2026-03-31"},
        quant_payload={"trade_date": "2026-03-31", "market_summary": {}, "stocks": []},
        risk_payload={"risk_level": "MEDIUM", "alerts": [], "industry_breakdown": []},
        critic_status="PENDING",
    )
    build_report(
        report_type="daily",
        report_date="2026-04-02",
        evidence_payload={"evidence_pack": [], "synthesis": "day2", "matched_companies": ["NVDA"], "matched_themes": [], "latest_evidence_date": "2026-04-02"},
        quant_payload={"trade_date": "2026-04-02", "market_summary": {}, "stocks": []},
        risk_payload={"risk_level": "LOW", "alerts": [], "industry_breakdown": []},
        critic_status="PENDING",
    )

    result = execute_weekly_report(report_date="2026-04-05", stock_codes=["AAPL", "NVDA"])
    assert result.report_payload["report_type"] == "weekly"
    assert result.evidence_payload["daily_report_count"] == 2
    assert result.evidence_payload["week_range"] == "2026-03-30 to 2026-04-05"
    assert Path(result.report_payload["file_path"]).exists()


def test_critic_returns_ethics_checklist():
    result = review_report(
        report_payload={
            "full_content": (
                "Data sources: sec_edgar\n"
                "Data dates: 2026-04-05\n"
                "Action boundary: informational_only\n"
                "Human approval required: no"
            )
        },
        evidence_payload={
            "evidence_pack": [{"evidence_id": "E001", "title": "Apple 10-Q"}],
            "latest_evidence_date": "2026-04-05",
        },
        quant_payload={"stocks": []},
        risk_payload={"alerts": []},
    )
    assert "ethics_checklist" in result
    checklist = result["ethics_checklist"]
    assert set(checklist.keys()) == {
        "claims_supported_by_evidence",
        "data_freshness_explicit",
        "no_analysis_risk_conflict",
        "no_overstatement",
        "action_boundary_appropriate",
    }
    assert all(isinstance(v, bool) for v in checklist.values())
    assert "overstatement_detected" in result
    assert "recommended_action_boundary" in result
    assert result["recommended_action_boundary"] in {"informational_only", "analysis_only"}


def test_critic_detects_overstatement():
    result = review_report(
        report_payload={
            "full_content": (
                "Strong buy Apple now. Data sources: sec_edgar. "
                "Data dates: 2026-04-05. Action boundary: requires_human_approval."
            )
        },
        evidence_payload={
            "evidence_pack": [{"evidence_id": "E001", "title": "Apple 10-Q"}],
            "latest_evidence_date": "2026-04-05",
        },
        quant_payload={"stocks": []},
        risk_payload={"alerts": []},
    )
    assert result["overstatement_detected"] is True
    assert result["status"] == "FAIL"
    assert result["recommended_action_boundary"] == "informational_only"


def test_consistency_check_covers_all_alerts():
    result = review_report(
        report_payload={"full_content": "Data sources: sec_edgar\nData dates: 2026-04-05\nAlert one\nAlert two"},
        evidence_payload={"evidence_pack": [], "latest_evidence_date": "2026-04-05"},
        quant_payload={"stocks": []},
        risk_payload={"alerts": ["Alert one", "Alert two", "Alert three"]},
    )
    assert result["consistency_check"] == "FAIL"


def test_report_template_renders_ethics_section(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    payload = build_report(
        report_type="daily",
        report_date="2026-04-05",
        evidence_payload={
            "evidence_pack": [{"evidence_id": "E001", "title": "Apple 10-Q", "source": "sec_edgar", "published_at": "2026-04-05"}],
            "synthesis": "Test synthesis",
            "matched_companies": ["AAPL"],
            "matched_themes": [],
            "latest_evidence_date": "2026-04-05",
        },
        quant_payload={"trade_date": "2026-04-05", "market_summary": {}, "stocks": []},
        risk_payload={"risk_level": "LOW", "alerts": [], "industry_breakdown": []},
        critic_status="PENDING",
    )
    content = payload["full_content"]
    assert "Review and Compliance" in content
    assert "Action boundary" in content
    assert "Human approval required" in content
    assert "Evidence status" in content


def test_planner_weekly_report_endpoint_returns_critic_result(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    client = TestClient(planner_app)
    client.post("/api/v1/planner/daily-report", json={"report_date": "2026-04-01", "stock_codes": ["AAPL", "NVDA"]})
    response = client.post("/api/v1/planner/weekly-report", json={"report_date": "2026-04-05", "stock_codes": ["AAPL", "NVDA"]})
    payload = response.json()["data"]
    assert response.status_code == 200
    assert payload["report"]["report_type"] == "weekly"
    assert payload["critic"]["status"] in {"PASS", "PASS_WITH_WARNINGS", "FAIL"}
    assert payload["evidence"]["week_range"] == "2026-03-30 to 2026-04-05"
    assert Path(payload["report"]["file_path"]).exists()
