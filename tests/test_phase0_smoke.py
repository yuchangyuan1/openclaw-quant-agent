from fastapi.testclient import TestClient

from services.critic.main import app as critic_app
from services.ingestion.main import app as ingestion_app
from services.planner.main import app as planner_app
from services.quant import market_data as quant_market_data
from services.quant.fundamentals import FundamentalSnapshot
from services.quant.main import app as quant_app
from services.rag.main import app as rag_app
from services.report.main import app as report_app
from services.risk.main import app as risk_app


def _patch_quant_fundamentals(monkeypatch):
    def fake_load_fundamental_snapshot(code: str, **_kwargs):
        return FundamentalSnapshot(
            code=code,
            name="测试股票",
            industry="测试行业",
            report_period="2025-12-31",
            data_date="2025-12-31",
            fetched_at="2026-04-06T10:00:00",
            close_price=100.0,
            market_cap=100_000_000_000.0,
            float_market_cap=80_000_000_000.0,
            pe_ttm=20.0,
            pb=3.0,
            eps_ttm=5.0,
            eps_latest=5.0,
            book_value_per_share=33.3,
            operating_cashflow_per_share=4.0,
            roe=18.0,
            gross_margin=30.0,
            net_margin=15.0,
            revenue_growth=12.0,
            net_profit_growth=10.0,
            debt_to_asset=40.0,
            current_ratio=1.8,
            quick_ratio=1.2,
            source="test",
            valuation_method="test",
        )

    def fake_build_industry_comparison(code: str, snapshot, **_kwargs):
        return {
            "industry": snapshot.industry,
            "peer_count": 3,
            "coverage_count": 3,
            "metrics": {
                "pe_ttm": {
                    "stock_value": snapshot.pe_ttm,
                    "industry_avg": snapshot.pe_ttm + 2,
                    "industry_median": snapshot.pe_ttm + 1,
                    "percentile": 0.4,
                    "relative": "better_than_industry",
                }
            },
        }

    monkeypatch.setattr(quant_market_data, "load_fundamental_snapshot", fake_load_fundamental_snapshot)
    monkeypatch.setattr(quant_market_data, "build_industry_comparison", fake_build_industry_comparison)


def test_ingestion_health():
    client = TestClient(ingestion_app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "ingestion"


def test_ingestion_trigger_stub_contract():
    client = TestClient(ingestion_app)
    response = client.post(
        "/api/v1/ingest/trigger",
        json={"source": "all", "date": "2026-04-07", "stock_codes": ["600519"]},
    )
    data = response.json()
    assert response.status_code == 200
    assert data["success"] is True
    assert data["data"]["status"] == "queued"


def test_rag_retrieve_stub_contract():
    client = TestClient(rag_app)
    response = client.post(
        "/api/v1/retrieve",
        json={
            "query": "贵州茅台一季报净利润",
            "stock_codes": ["600519"],
            "doc_types": ["news"],
            "date_range": {"start": "2026-04-01", "end": "2026-04-07"},
            "top_k": 5,
            "min_score": 0.7,
        },
    )
    data = response.json()
    assert response.status_code == 200
    assert data["success"] is True
    assert "results" in data["data"]
    assert isinstance(data["data"]["results"], list)


def test_quant_daily_stub_contract(monkeypatch):
    _patch_quant_fundamentals(monkeypatch)
    client = TestClient(quant_app)
    response = client.post(
        "/api/v1/quant/daily",
        json={"stock_codes": ["600519", "300750"], "date": "2026-04-07", "indicators": []},
    )
    data = response.json()
    assert response.status_code == 200
    assert data["success"] is True
    assert data["data"]["trade_date"] <= "2026-04-07"
    assert len(data["data"]["stocks"]) == 2
    assert data["data"]["stocks"][0]["close"] > 0


def test_risk_check_stub_contract():
    client = TestClient(risk_app)
    response = client.post(
        "/api/v1/risk/check",
        json={
            "portfolio": [
                {"code": "600519", "weight": 0.05},
                {"code": "300750", "weight": 0.08},
            ],
            "benchmark": "000300",
            "lookback_days": 90,
            "run_scenarios": True,
        },
    )
    data = response.json()
    assert response.status_code == 200
    assert data["success"] is True
    assert data["data"]["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert "alerts" in data["data"]


def test_planner_query_contract():
    client = TestClient(planner_app)
    response = client.post(
        "/api/v1/planner/query",
        json={"message": "贵州茅台近期公告", "refresh_index": False},
    )
    data = response.json()
    assert response.status_code == 200
    assert data["success"] is True
    assert data["data"]["intent"] == "DOC_QA"
    assert "reply_markdown" in data["data"]


def test_planner_query_report_routing_contract():
    client = TestClient(planner_app)
    daily_response = client.post(
        "/api/v1/planner/query",
        json={"message": "请生成今日日报", "refresh_index": False},
    )
    weekly_response = client.post(
        "/api/v1/planner/query",
        json={"message": "请生成本周周报", "refresh_index": False},
    )
    daily = daily_response.json()
    weekly = weekly_response.json()
    assert daily_response.status_code == 200
    assert weekly_response.status_code == 200
    assert daily["success"] is True
    assert weekly["success"] is True
    assert daily["data"]["intent"] == "DAILY_REPORT"
    assert weekly["data"]["intent"] == "WEEKLY_REPORT"
    assert "已生成" in daily["data"]["reply_markdown"]
    assert "已生成" in weekly["data"]["reply_markdown"]


def test_planner_run_logs_contract():
    client = TestClient(planner_app)
    response = client.post("/api/v1/planner/run-logs", json={"limit": 5})
    data = response.json()
    assert response.status_code == 200
    assert data["success"] is True
    assert "items" in data["data"]
    assert isinstance(data["data"]["items"], list)


def test_planner_alert_summary_contract():
    client = TestClient(planner_app)
    response = client.post("/api/v1/planner/alerts/summary", json={"limit": 5})
    data = response.json()
    assert response.status_code == 200
    assert data["success"] is True
    assert "needs_attention" in data["data"]
    assert "failed_runs" in data["data"]


def test_report_build_contract():
    client = TestClient(report_app)
    response = client.post(
        "/api/v1/report/build",
        json={
            "report_type": "daily",
            "report_date": "2026-04-05",
            "evidence_payload": {"evidence_pack": [], "synthesis": "暂无", "matched_companies": [], "matched_themes": []},
            "quant_payload": {"trade_date": "2026-04-03", "market_summary": {}, "stocks": []},
            "risk_payload": {"risk_level": "MEDIUM", "alerts": [], "industry_breakdown": []},
            "critic_status": "PENDING",
        },
    )
    data = response.json()
    assert response.status_code == 200
    assert data["success"] is True
    assert data["data"]["report_type"] == "daily"
    assert "full_content" in data["data"]


def test_critic_review_contract():
    client = TestClient(critic_app)
    response = client.post(
        "/api/v1/critic/review",
        json={
            "report_payload": {"full_content": "数据来源：eastmoney\n数据日期：2026-04-05\nCritic 校验：PENDING\n风险提示：无"},
            "evidence_payload": {"evidence_pack": [], "latest_evidence_date": "2026-04-05"},
            "quant_payload": {"stocks": []},
            "risk_payload": {"alerts": []},
        },
    )
    data = response.json()
    assert response.status_code == 200
    assert data["success"] is True
    assert data["data"]["status"] in {"PASS", "PASS_WITH_WARNINGS", "FAIL"}
