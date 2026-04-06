from fastapi.testclient import TestClient

from services.quant import market_data as quant_market_data
from services.quant import service as quant_service
from services.quant.fundamentals import FundamentalSnapshot
from services.quant.main import app as quant_app
from services.risk import service as risk_service
from services.risk.main import app as risk_app


def _patch_quant_fundamentals(monkeypatch):
    snapshots = {
        "600519": FundamentalSnapshot(
            code="600519",
            name="贵州茅台",
            industry="白酒Ⅱ",
            report_period="2025-12-31",
            data_date="2025-12-31",
            fetched_at="2026-04-06T10:00:00",
            close_price=1460.0,
            market_cap=1_828_314_513_900.0,
            float_market_cap=1_828_314_513_900.0,
            pe_ttm=22.3,
            pb=8.5,
            eps_ttm=65.4,
            eps_latest=65.4,
            book_value_per_share=171.8,
            operating_cashflow_per_share=42.2,
            roe=31.5,
            gross_margin=91.2,
            net_margin=52.4,
            revenue_growth=15.6,
            net_profit_growth=17.3,
            debt_to_asset=18.2,
            current_ratio=4.5,
            quick_ratio=3.8,
            source="test",
            valuation_method="test",
        ),
        "300750": FundamentalSnapshot(
            code="300750",
            name="宁德时代",
            industry="电池",
            report_period="2025-12-31",
            data_date="2025-12-31",
            fetched_at="2026-04-06T10:00:00",
            close_price=240.0,
            market_cap=1_056_000_000_000.0,
            float_market_cap=820_000_000_000.0,
            pe_ttm=24.6,
            pb=4.2,
            eps_ttm=9.75,
            eps_latest=9.75,
            book_value_per_share=57.1,
            operating_cashflow_per_share=16.2,
            roe=19.3,
            gross_margin=28.4,
            net_margin=18.6,
            revenue_growth=12.4,
            net_profit_growth=10.1,
            debt_to_asset=43.5,
            current_ratio=1.9,
            quick_ratio=1.5,
            source="test",
            valuation_method="test",
        ),
    }

    def fake_load_fundamental_snapshot(code: str, **_kwargs):
        return snapshots.get(code)

    def fake_build_industry_comparison(code: str, snapshot, **_kwargs):
        if snapshot is None:
            return None
        return {
            "industry": snapshot.industry,
            "peer_count": 3,
            "coverage_count": 3,
            "metrics": {
                "pe_ttm": {
                    "stock_value": snapshot.pe_ttm,
                    "industry_avg": snapshot.pe_ttm + 2,
                    "industry_median": snapshot.pe_ttm + 1,
                    "percentile": 0.35,
                    "relative": "better_than_industry",
                },
                "pb": {
                    "stock_value": snapshot.pb,
                    "industry_avg": snapshot.pb + 0.5,
                    "industry_median": snapshot.pb + 0.2,
                    "percentile": 0.4,
                    "relative": "better_than_industry",
                },
                "roe": {
                    "stock_value": snapshot.roe,
                    "industry_avg": snapshot.roe - 3,
                    "industry_median": snapshot.roe - 2,
                    "percentile": 0.8,
                    "relative": "better_than_industry",
                },
                "revenue_growth": {
                    "stock_value": snapshot.revenue_growth,
                    "industry_avg": snapshot.revenue_growth - 2,
                    "industry_median": snapshot.revenue_growth - 1,
                    "percentile": 0.75,
                    "relative": "better_than_industry",
                },
            },
        }

    monkeypatch.setattr(quant_market_data, "load_fundamental_snapshot", fake_load_fundamental_snapshot)
    monkeypatch.setattr(quant_market_data, "build_industry_comparison", fake_build_industry_comparison)


def test_quant_daily_uses_local_market_data(monkeypatch):
    _patch_quant_fundamentals(monkeypatch)
    client = TestClient(quant_app)
    response = client.post(
        "/api/v1/quant/daily",
        json={"stock_codes": ["600519", "300750"], "date": "2026-04-07", "indicators": []},
    )
    payload = response.json()["data"]
    assert response.status_code == 200
    assert payload["trade_date"] == "2026-04-03"
    assert len(payload["stocks"]) == 2
    assert {item["code"] for item in payload["stocks"]} == {"600519", "300750"}
    assert all(item["ma_signal"] in {"bullish", "bearish", "neutral"} for item in payload["stocks"])


def test_quant_factor_endpoint_returns_real_fields(monkeypatch):
    _patch_quant_fundamentals(monkeypatch)
    client = TestClient(quant_app)
    response = client.post(
        "/api/v1/quant/factor",
        json={
            "stock_codes": ["600519"],
            "factors": [
                "momentum_1m",
                "price_rank_1y",
                "pe_ttm",
                "roe",
                "industry_pe_percentile",
                "composite_score",
            ],
            "date": "2026-04-07",
        },
    )
    payload = response.json()["data"]
    assert response.status_code == 200
    assert payload["factors"][0]["momentum_1m"] is not None
    assert payload["factors"][0]["price_rank_1y"] is not None
    assert payload["factors"][0]["pe_ttm"] == 22.3
    assert payload["factors"][0]["roe"] == 31.5
    assert payload["factors"][0]["industry_pe_percentile"] == 0.35
    assert payload["factors"][0]["composite_score"] is not None


def test_quant_services_write_graph_metric_snapshots(monkeypatch):
    _patch_quant_fundamentals(monkeypatch)
    metric_calls = []
    monkeypatch.setattr(
        quant_service._GRAPH_REPO,
        "save_metric_snapshot",
        lambda **kwargs: metric_calls.append(kwargs),
    )

    quant_service.daily_summary(["600519"], "2026-04-07", [])
    quant_service.factor_values(
        ["600519"],
        ["momentum_1m", "price_rank_1y", "pe_ttm", "roe", "industry_pe_percentile", "composite_score"],
        "2026-04-07",
    )

    metric_names = {item["metric_name"] for item in metric_calls}
    assert "close_price" in metric_names
    assert "momentum_1m" in metric_names
    assert "price_rank_1y" in metric_names
    assert "pe_ttm" in metric_names
    assert "roe" in metric_names
    assert "composite_score" in metric_names


def test_quant_daily_includes_fundamental_and_industry_analysis(monkeypatch):
    _patch_quant_fundamentals(monkeypatch)
    client = TestClient(quant_app)
    response = client.post(
        "/api/v1/quant/daily",
        json={"stock_codes": ["600519"], "date": "2026-04-07", "indicators": []},
    )
    payload = response.json()["data"]["stocks"][0]
    assert response.status_code == 200
    assert payload["pe_ttm"] == 22.3
    assert payload["roe"] == 31.5
    assert payload["industry_comparison"]["metrics"]["pe_ttm"]["percentile"] == 0.35
    assert payload["technical_score"] is not None
    assert payload["fundamental_score"] is not None
    assert payload["valuation_score"] is not None
    assert payload["composite_signal"] in {"POSITIVE", "BALANCED", "NEUTRAL", "CAUTION"}


def test_risk_check_uses_history_and_industry_breakdown():
    client = TestClient(risk_app)
    response = client.post(
        "/api/v1/risk/check",
        json={
            "portfolio": [
                {"code": "600519", "weight": 0.4},
                {"code": "300750", "weight": 0.35},
                {"code": "000001", "weight": 0.25},
            ],
            "benchmark": "000300",
            "lookback_days": 90,
            "run_scenarios": True,
        },
    )
    payload = response.json()["data"]
    assert response.status_code == 200
    assert payload["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert payload["industry_breakdown"]
    assert payload["top_industry_exposure"]["weight"] > 0
    assert "2015_crash" in payload["scenario_loss_estimate"]


def test_risk_services_write_graph_risk_snapshots(monkeypatch):
    risk_calls = []
    monkeypatch.setattr(
        risk_service._GRAPH_REPO,
        "save_risk_snapshot",
        lambda **kwargs: risk_calls.append(kwargs),
    )

    risk_service.risk_check(
        portfolio=[
            {"code": "600519", "weight": 0.4},
            {"code": "300750", "weight": 0.35},
            {"code": "000001", "weight": 0.25},
        ],
        benchmark="000300",
        lookback_days=90,
        run_scenarios=True,
    )
    risk_service.drawdown_analysis(["600519"], 90)

    risk_types = {item["risk_type"] for item in risk_calls}
    assert "portfolio_weight" in risk_types
    assert "portfolio_beta" in risk_types
    assert "max_drawdown" in risk_types


def test_drawdown_endpoint_returns_real_metrics():
    client = TestClient(risk_app)
    response = client.post(
        "/api/v1/risk/drawdown",
        json={"stock_codes": ["600519", "300750"], "lookback_days": 90},
    )
    payload = response.json()["data"]
    assert response.status_code == 200
    assert len(payload["results"]) == 2
    assert all(item["max_drawdown"] is not None for item in payload["results"])
