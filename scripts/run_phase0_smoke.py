#!/usr/bin/env python3
"""
End-to-end smoke checks for the current US-market MVP.
This script intentionally validates only public API contracts and lightweight happy paths.
"""

from fastapi.testclient import TestClient

from services.critic.main import app as critic_app
from services.ingestion.main import app as ingestion_app
from services.planner.main import app as planner_app
from services.quant.main import app as quant_app
from services.rag.main import app as rag_app
from services.report.main import app as report_app
from services.risk.main import app as risk_app


def assert_ok(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_ingestion() -> None:
    client = TestClient(ingestion_app)
    health = client.get("/health")
    assert_ok(health.status_code == 200, "ingestion /health failed")

    trigger = client.post(
        "/api/v1/ingest/trigger",
        json={"source": "all", "date": "2026-04-07", "stock_codes": ["AAPL"]},
    )
    payload = trigger.json()
    assert_ok(trigger.status_code == 200, "ingestion trigger failed")
    assert_ok(payload["success"] is True, "ingestion trigger success=false")
    assert_ok(payload["data"]["status"] == "queued", "ingestion trigger status mismatch")


def check_rag() -> None:
    client = TestClient(rag_app)
    retrieve = client.post(
        "/api/v1/retrieve",
        json={
            "query": "Apple latest filing",
            "stock_codes": ["AAPL"],
            "doc_types": ["filing"],
            "date_range": {"start": "2026-04-01", "end": "2026-04-07"},
            "top_k": 5,
            "min_score": 0.7,
        },
    )
    payload = retrieve.json()
    assert_ok(retrieve.status_code == 200, "rag retrieve failed")
    assert_ok(payload["success"] is True, "rag retrieve success=false")
    assert_ok("results" in payload["data"], "rag results missing")


def check_quant() -> None:
    client = TestClient(quant_app)
    daily = client.post(
        "/api/v1/quant/daily",
        json={"stock_codes": ["AAPL", "MSFT"], "date": "2026-04-07", "indicators": []},
    )
    payload = daily.json()
    assert_ok(daily.status_code == 200, "quant daily failed")
    assert_ok(payload["success"] is True, "quant daily success=false")
    assert_ok(payload["data"]["trade_date"] <= "2026-04-07", "quant trade date mismatch")


def check_risk() -> None:
    client = TestClient(risk_app)
    risk = client.post(
        "/api/v1/risk/check",
        json={
            "portfolio": [
                {"code": "AAPL", "weight": 0.05},
                {"code": "MSFT", "weight": 0.08},
            ],
            "benchmark": "SPY",
            "lookback_days": 90,
            "run_scenarios": True,
        },
    )
    payload = risk.json()
    assert_ok(risk.status_code == 200, "risk check failed")
    assert_ok(payload["success"] is True, "risk check success=false")
    assert_ok(payload["data"]["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}, "risk level mismatch")
    assert_ok("alerts" in payload["data"], "risk alerts missing")


def check_planner() -> None:
    client = TestClient(planner_app)
    query = client.post(
        "/api/v1/planner/query",
        json={"message": "Apple latest filing", "refresh_index": False},
    )
    payload = query.json()
    assert_ok(query.status_code == 200, "planner query failed")
    assert_ok(payload["success"] is True, "planner query success=false")
    assert_ok(payload["data"]["intent"] == "DOC_QA", "planner intent mismatch")
    assert_ok("reply_markdown" in payload["data"], "planner reply missing")

    routed_daily = client.post(
        "/api/v1/planner/query",
        json={"message": "Please generate today's daily report", "refresh_index": False},
    )
    routed_daily_payload = routed_daily.json()
    assert_ok(routed_daily.status_code == 200, "planner routed daily-report failed")
    assert_ok(routed_daily_payload["success"] is True, "planner routed daily-report success=false")
    assert_ok(routed_daily_payload["data"]["intent"] == "DAILY_REPORT", "planner routed daily-report intent mismatch")

    routed_weekly = client.post(
        "/api/v1/planner/query",
        json={"message": "Please generate this week's weekly report", "refresh_index": False},
    )
    routed_weekly_payload = routed_weekly.json()
    assert_ok(routed_weekly.status_code == 200, "planner routed weekly-report failed")
    assert_ok(routed_weekly_payload["success"] is True, "planner routed weekly-report success=false")
    assert_ok(routed_weekly_payload["data"]["intent"] == "WEEKLY_REPORT", "planner routed weekly-report intent mismatch")

    run_logs = client.post("/api/v1/planner/run-logs", json={"limit": 5})
    run_logs_payload = run_logs.json()
    assert_ok(run_logs.status_code == 200, "planner run-logs failed")
    assert_ok(run_logs_payload["success"] is True, "planner run-logs success=false")
    assert_ok(isinstance(run_logs_payload["data"]["items"], list), "planner run-logs items invalid")

    alert_summary = client.post("/api/v1/planner/alerts/summary", json={"limit": 5})
    alert_summary_payload = alert_summary.json()
    assert_ok(alert_summary.status_code == 200, "planner alerts summary failed")
    assert_ok(alert_summary_payload["success"] is True, "planner alerts summary success=false")
    assert_ok("needs_attention" in alert_summary_payload["data"], "planner alerts summary missing needs_attention")

    daily_report = client.post(
        "/api/v1/planner/daily-report",
        json={"report_date": "2026-04-05", "stock_codes": ["AAPL", "MSFT"]},
    )
    daily_payload = daily_report.json()
    assert_ok(daily_report.status_code == 200, "planner daily-report failed")
    assert_ok(daily_payload["success"] is True, "planner daily-report success=false")
    assert_ok(daily_payload["data"]["report"]["report_type"] == "daily", "planner daily-report type mismatch")

    weekly_report = client.post(
        "/api/v1/planner/weekly-report",
        json={"report_date": "2026-04-05", "stock_codes": ["AAPL", "MSFT"]},
    )
    weekly_payload = weekly_report.json()
    assert_ok(weekly_report.status_code == 200, "planner weekly-report failed")
    assert_ok(weekly_payload["success"] is True, "planner weekly-report success=false")
    assert_ok(weekly_payload["data"]["report"]["report_type"] == "weekly", "planner weekly-report type mismatch")


def check_report() -> None:
    client = TestClient(report_app)
    report = client.post(
        "/api/v1/report/build",
        json={
            "report_type": "daily",
            "report_date": "2026-04-05",
            "evidence_payload": {
                "evidence_pack": [],
                "synthesis": "No major filing found.",
                "matched_companies": [],
                "matched_themes": [],
            },
            "quant_payload": {"trade_date": "2026-04-03", "market_summary": {}, "stocks": []},
            "risk_payload": {"risk_level": "MEDIUM", "alerts": [], "industry_breakdown": []},
            "critic_status": "PENDING",
        },
    )
    payload = report.json()
    assert_ok(report.status_code == 200, "report build failed")
    assert_ok(payload["success"] is True, "report build success=false")
    assert_ok(payload["data"]["report_type"] == "daily", "report type mismatch")


def check_critic() -> None:
    client = TestClient(critic_app)
    critic = client.post(
        "/api/v1/critic/review",
        json={
            "report_payload": {"full_content": "Data sources: sec_edgar\nData dates: 2026-04-05\nCritic status: PENDING"},
            "evidence_payload": {"evidence_pack": [], "latest_evidence_date": "2026-04-05"},
            "quant_payload": {"stocks": []},
            "risk_payload": {"alerts": []},
        },
    )
    payload = critic.json()
    assert_ok(critic.status_code == 200, "critic review failed")
    assert_ok(payload["success"] is True, "critic review success=false")
    assert_ok(payload["data"]["status"] in {"PASS", "PASS_WITH_WARNINGS", "FAIL"}, "critic status invalid")


def main() -> None:
    checks = [
        ("ingestion", check_ingestion),
        ("rag", check_rag),
        ("quant", check_quant),
        ("risk", check_risk),
        ("planner", check_planner),
        ("report", check_report),
        ("critic", check_critic),
    ]

    print("=" * 55)
    print("  US Market MVP Smoke Test")
    print("=" * 55)

    for name, check in checks:
        check()
        print(f"  [PASS] {name}")

    print()
    print(f"Result: all {len(checks)} checks passed")


if __name__ == "__main__":
    main()
