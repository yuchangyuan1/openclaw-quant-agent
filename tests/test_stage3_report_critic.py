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


def test_critic_returns_ethics_checklist():
    result = review_report(
        report_payload={
            "full_content": "数据来源：eastmoney\n数据日期：2026-04-05\n行动边界：informational_only\n人工审批：不需要"
        },
        evidence_payload={
            "evidence_pack": [{"evidence_id": "E001", "title": "测试标题"}],
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
            "full_content": "推荐买入贵州茅台，数据来源：eastmoney，数据日期：2026-04-05，行动边界：requires_human_approval"
        },
        evidence_payload={
            "evidence_pack": [{"evidence_id": "E001", "title": "测试标题"}],
            "latest_evidence_date": "2026-04-05",
        },
        quant_payload={"stocks": []},
        risk_payload={"alerts": []},
    )
    assert result["overstatement_detected"] is True
    assert result["status"] == "FAIL"
    assert result["recommended_action_boundary"] == "informational_only"


def test_consistency_check_covers_all_alerts():
    """Regression: critic must check all alerts, not just the first 2."""
    result = review_report(
        report_payload={"full_content": "数据来源：eastmoney\n数据日期：2026-04-05\n告警1\n告警2"},
        evidence_payload={"evidence_pack": [], "latest_evidence_date": "2026-04-05"},
        quant_payload={"stocks": []},
        risk_payload={"alerts": ["告警1", "告警2", "告警3"]},
    )
    assert result["consistency_check"] == "FAIL"


def test_report_template_renders_ethics_section(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    payload = build_report(
        report_type="daily",
        report_date="2026-04-05",
        evidence_payload={
            "evidence_pack": [{"evidence_id": "E001", "title": "测试公告", "source": "eastmoney", "published_at": "2026-04-05"}],
            "synthesis": "测试综合",
            "matched_companies": ["600519"],
            "matched_themes": [],
            "latest_evidence_date": "2026-04-05",
        },
        quant_payload={"trade_date": "2026-04-05", "market_summary": {}, "stocks": []},
        risk_payload={"risk_level": "LOW", "alerts": [], "industry_breakdown": []},
        critic_status="PENDING",
    )
    content = payload["full_content"]
    assert "审查与合规" in content
    assert "行动边界" in content
    assert "人工审批要求" in content
    assert "证据状态" in content


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
