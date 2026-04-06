from pathlib import Path

from fastapi.testclient import TestClient

from services.planner.main import app as planner_app
from services.planner.report_pipeline import execute_weekly_report
from services.report.service import build_report


def test_report_service_archives_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    payload = build_report(
        report_type="daily",
        report_date="2026-04-05",
        evidence_payload={
            "evidence_pack": [{"evidence_id": "E001", "title": "测试公告", "source": "eastmoney", "published_at": "2026-04-05"}],
            "synthesis": "根据现有证据，[E001] 提供了直接说明。",
            "matched_companies": ["600519"],
            "matched_themes": ["消费复苏"],
            "latest_evidence_date": "2026-04-05",
        },
        quant_payload={
            "trade_date": "2026-04-03",
            "market_summary": {"sh300_pct_change": 0.5, "total_volume_billion": 12.3, "advancing_stocks": 2, "declining_stocks": 1},
            "stocks": [{"code": "600519", "name": "贵州茅台", "close": 1460.0, "pct_change": 0.01, "ma5": 1449.0, "ma20": 1430.0, "ma_signal": "bullish"}],
        },
        risk_payload={"risk_level": "MEDIUM", "alerts": ["行业集中度偏高"], "industry_breakdown": [{"industry": "食品饮料", "weight": 0.4}]},
        critic_status="PENDING",
    )
    path = Path(payload["file_path"])
    assert path.exists()
    assert "Critic 校验：PENDING" in path.read_text(encoding="utf-8")


def test_planner_daily_report_endpoint_returns_critic_result(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    client = TestClient(planner_app)
    response = client.post("/api/v1/planner/daily-report", json={"report_date": "2026-04-05", "stock_codes": ["600519", "300750"]})
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
        evidence_payload={"evidence_pack": [], "synthesis": "day1", "matched_companies": ["600519"], "matched_themes": [], "latest_evidence_date": "2026-03-31"},
        quant_payload={"trade_date": "2026-03-31", "market_summary": {}, "stocks": []},
        risk_payload={"risk_level": "MEDIUM", "alerts": [], "industry_breakdown": []},
        critic_status="PENDING",
    )
    build_report(
        report_type="daily",
        report_date="2026-04-02",
        evidence_payload={"evidence_pack": [], "synthesis": "day2", "matched_companies": ["300750"], "matched_themes": [], "latest_evidence_date": "2026-04-02"},
        quant_payload={"trade_date": "2026-04-02", "market_summary": {}, "stocks": []},
        risk_payload={"risk_level": "LOW", "alerts": [], "industry_breakdown": []},
        critic_status="PENDING",
    )

    result = execute_weekly_report(report_date="2026-04-05", stock_codes=["600519", "300750"])
    assert result.report_payload["report_type"] == "weekly"
    assert result.evidence_payload["daily_report_count"] == 2
    assert result.evidence_payload["week_range"] == "2026-03-30 to 2026-04-05"
    assert Path(result.report_payload["file_path"]).exists()


def test_planner_weekly_report_endpoint_returns_critic_result(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    client = TestClient(planner_app)
    client.post("/api/v1/planner/daily-report", json={"report_date": "2026-04-01", "stock_codes": ["600519", "300750"]})
    response = client.post("/api/v1/planner/weekly-report", json={"report_date": "2026-04-05", "stock_codes": ["600519", "300750"]})
    payload = response.json()["data"]
    assert response.status_code == 200
    assert payload["report"]["report_type"] == "weekly"
    assert payload["critic"]["status"] in {"PASS", "PASS_WITH_WARNINGS", "FAIL"}
    assert payload["evidence"]["week_range"] == "2026-03-30 to 2026-04-05"
    assert Path(payload["report"]["file_path"]).exists()
