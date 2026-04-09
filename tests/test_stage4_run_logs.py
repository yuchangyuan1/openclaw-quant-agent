import json
from pathlib import Path

from fastapi.testclient import TestClient

from services.common.retry import call_with_retry
from services.planner.main import app as planner_app
from services.planner.report_pipeline import execute_daily_report, summarize_alerts


def test_call_with_retry_retries_once_before_success():
    state = {"count": 0}

    def flaky():
        state["count"] += 1
        if state["count"] == 1:
            raise RuntimeError("boom")
        return "ok"

    result, attempts = call_with_retry(flaky, attempts=2)
    assert result == "ok"
    assert attempts == 2


def test_execute_daily_report_writes_run_log_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("RUN_LOG_MANIFEST_PATH", str(tmp_path / "run_logs.json"))
    captured = {}
    monkeypatch.setattr(
        "services.planner.report_pipeline.run_knowledge_agent",
        lambda **kwargs: captured.update(kwargs) or type(
            "KnowledgeResult",
            (),
            {
                "agent_id": "knowledge",
                "payload": {
                    "evidence_pack": [{"evidence_id": "E001", "title": "Apple 10-Q", "source": "sec_edgar", "published_at": "2026-04-05"}],
                    "synthesis": "Test conclusion",
                    "matched_companies": ["AAPL"],
                    "matched_themes": [],
                    "latest_evidence_date": "2026-04-05",
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "services.planner.report_pipeline.run_quant_agent",
        lambda **_kwargs: type(
            "QuantResult",
            (),
            {
                "agent_id": "quant",
                "payload": {
                    "trade_date": "2026-04-03",
                    "market_summary": {"tracked_avg_pct_change": 0.5, "advancing_stocks": 2, "declining_stocks": 1},
                    "stocks": [{"code": "AAPL", "name": "Apple Inc.", "close": 210.0, "pct_change": 0.01, "ma5": 209.0, "ma20": 205.0, "ma_signal": "bullish"}],
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "services.planner.report_pipeline.run_risk_agent",
        lambda **_kwargs: type(
            "RiskResult",
            (),
            {
                "agent_id": "risk",
                "payload": {"risk_level": "MEDIUM", "alerts": ["Consumer electronics exposure is concentrated."], "industry_breakdown": [{"industry": "Consumer Electronics", "weight": 0.4}]},
            },
        )(),
    )

    result = execute_daily_report(report_date="2026-04-05", stock_codes=["AAPL"])
    assert result.run_log_id
    assert result.attempts == {"knowledge": 1, "quant": 1, "risk": 1, "report": 1, "critic": 1, "finalize": 1}

    manifest = json.loads((tmp_path / "run_logs.json").read_text(encoding="utf-8"))
    assert manifest[0]["id"] == result.run_log_id
    assert manifest[0]["status"] == "success"
    assert manifest[0]["output_summary"]["report_type"] == "daily"
    assert manifest[0]["output_summary"]["collaboration_agents"] == ["planner", "knowledge", "quant", "risk", "report", "critic"]
    assert captured["question"] == "Latest SEC filings and public updates for Apple (AAPL)"


def test_planner_run_logs_endpoint_returns_recent_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_LOG_MANIFEST_PATH", str(tmp_path / "run_logs.json"))
    run_logs_path = Path(tmp_path / "run_logs.json")
    run_logs_path.write_text(
        json.dumps(
            [
                {
                    "id": "run-1",
                    "job_id": "daily_report:2026-04-05:1",
                    "job_type": "daily_report",
                    "status": "success",
                    "input_params": {"report_date": "2026-04-05"},
                    "output_summary": {"report_type": "daily"},
                    "error_message": None,
                    "started_at": "2026-04-05T08:00:00+00:00",
                    "finished_at": "2026-04-05T08:00:01+00:00",
                    "duration_seconds": 1,
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    client = TestClient(planner_app)
    response = client.post("/api/v1/planner/run-logs", json={"limit": 5, "job_type": "daily_report"})
    payload = response.json()["data"]
    assert response.status_code == 200
    assert payload["items"][0]["id"] == "run-1"
    assert payload["items"][0]["job_type"] == "daily_report"


def test_planner_replay_endpoint_replays_daily_run(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_LOG_MANIFEST_PATH", str(tmp_path / "run_logs.json"))
    Path(tmp_path / "run_logs.json").write_text(
        json.dumps(
            [
                {
                    "id": "failed-run-1",
                    "job_id": "daily_report:2026-04-05:1",
                    "job_type": "daily_report",
                    "status": "failed",
                    "input_params": {"report_date": "2026-04-05", "stock_codes": ["AAPL"]},
                    "output_summary": None,
                    "error_message": "boom",
                    "started_at": "2026-04-05T08:00:00+00:00",
                    "finished_at": "2026-04-05T08:00:01+00:00",
                    "duration_seconds": 1,
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "services.planner.report_pipeline.execute_daily_report",
        lambda report_date=None, stock_codes=None: type(
            "DailyResult",
            (),
            {
                "run_log_id": "new-run-1",
                "report_payload": {"report_type": "daily", "report_date": report_date, "file_path": "D:/tmp/daily.md"},
                "critic_payload": {"status": "PASS"},
            },
        )(),
    )

    client = TestClient(planner_app)
    response = client.post("/api/v1/planner/run-logs/replay", json={"run_id": "failed-run-1"})
    payload = response.json()["data"]
    assert response.status_code == 200
    assert payload["source_run_id"] == "failed-run-1"
    assert payload["new_run_log_id"] == "new-run-1"
    assert payload["replayed_job_type"] == "daily_report"


def test_summarize_alerts_counts_failures_and_warnings(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_LOG_MANIFEST_PATH", str(tmp_path / "run_logs.json"))
    Path(tmp_path / "run_logs.json").write_text(
        json.dumps(
            [
                {
                    "id": "run-fail",
                    "job_id": "daily_report:1",
                    "job_type": "daily_report",
                    "status": "failed",
                    "input_params": {},
                    "output_summary": None,
                    "error_message": "boom",
                    "started_at": "2026-04-05T08:00:00+00:00",
                    "finished_at": "2026-04-05T08:00:01+00:00",
                    "duration_seconds": 1,
                },
                {
                    "id": "run-warn",
                    "job_id": "weekly_report:1",
                    "job_type": "weekly_report",
                    "status": "success",
                    "input_params": {},
                    "output_summary": {"critic_status": "PASS_WITH_WARNINGS"},
                    "error_message": None,
                    "started_at": "2026-04-05T07:00:00+00:00",
                    "finished_at": "2026-04-05T07:00:01+00:00",
                    "duration_seconds": 1,
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary = summarize_alerts(limit=10)
    assert summary["failed_runs"] == 1
    assert summary["warning_runs"] == 1
    assert summary["needs_attention"] is True
