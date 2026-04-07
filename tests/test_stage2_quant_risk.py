import pandas as pd
from fastapi.testclient import TestClient

from services.quant import market_data as quant_market_data
from services.quant import service as quant_service
from services.quant.fundamentals import FundamentalSnapshot
from services.quant.main import app as quant_app
from services.risk import service as risk_service
from services.risk.main import app as risk_app


def _patch_quant_fundamentals(monkeypatch):
    snapshots = {
        "AAPL": FundamentalSnapshot(
            code="AAPL",
            name="Apple Inc.",
            industry="Consumer Electronics",
            report_period="2025-12-31",
            data_date="2025-12-31",
            fetched_at="2026-04-06T10:00:00",
            close_price=210.0,
            market_cap=3_200_000_000_000.0,
            float_market_cap=3_200_000_000_000.0,
            pe_ttm=22.3,
            pb=8.5,
            eps_ttm=9.4,
            eps_latest=9.4,
            book_value_per_share=24.7,
            operating_cashflow_per_share=8.1,
            roe=31.5,
            gross_margin=45.2,
            net_margin=26.4,
            revenue_growth=8.6,
            net_profit_growth=10.3,
            debt_to_asset=32.2,
            current_ratio=1.2,
            quick_ratio=0.9,
            source="test",
            valuation_method="test",
        ),
        "NVDA": FundamentalSnapshot(
            code="NVDA",
            name="NVIDIA Corporation",
            industry="Semiconductors & AI Hardware",
            report_period="2025-12-31",
            data_date="2025-12-31",
            fetched_at="2026-04-06T10:00:00",
            close_price=980.0,
            market_cap=2_400_000_000_000.0,
            float_market_cap=2_400_000_000_000.0,
            pe_ttm=24.6,
            pb=12.2,
            eps_ttm=21.0,
            eps_latest=21.0,
            book_value_per_share=80.1,
            operating_cashflow_per_share=16.2,
            roe=41.3,
            gross_margin=72.4,
            net_margin=48.6,
            revenue_growth=52.4,
            net_profit_growth=60.1,
            debt_to_asset=18.5,
            current_ratio=3.9,
            quick_ratio=3.5,
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


def _patch_market_history(monkeypatch):
    dates = pd.bdate_range("2025-12-01", "2026-04-03")

    def make_history(base_close: float) -> pd.DataFrame:
        closes = [base_close + idx * 1.5 for idx in range(len(dates))]
        rows = []
        for idx, trade_date in enumerate(dates):
            close = closes[idx]
            rows.append(
                {
                    "date": trade_date,
                    "open": close - 1.0,
                    "close": close,
                    "high": close + 2.0,
                    "low": close - 2.0,
                    "volume": 1_000_000 + idx * 1_000,
                }
            )
        return pd.DataFrame(rows)

    histories = {
        "AAPL": make_history(180.0),
        "NVDA": make_history(850.0),
        "MSFT": make_history(390.0),
        "SPY": make_history(500.0),
    }

    def fake_load_price_history(code: str, *_, start_date: str | None = None, end_date: str | None = None, **__):
        df = histories.get(code, pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume"])).copy()
        if start_date:
            df = df.loc[df["date"] >= pd.Timestamp(start_date)].copy()
        if end_date:
            df = df.loc[df["date"] <= pd.Timestamp(end_date)].copy()
        return df.reset_index(drop=True)

    monkeypatch.setattr(quant_market_data, "load_price_history", fake_load_price_history)

    def fake_portfolio_returns(weights: dict[str, float], lookback_days: int):
        weighted = []
        for code, weight in weights.items():
            history = fake_load_price_history(code)
            closes = history["close"].astype(float)
            returns = closes.pct_change().fillna(0.0) * float(weight)
            weighted.append(returns)
        if not weighted:
            return pd.Series(dtype=float)
        result = pd.concat(weighted, axis=1).sum(axis=1)
        result.index = dates
        return result.tail(lookback_days)

    def fake_benchmark_returns(code: str, lookback_days: int, fallback_codes=None):
        history = fake_load_price_history(code if code in histories else "SPY")
        closes = history["close"].astype(float)
        returns = closes.pct_change().fillna(0.0)
        returns.index = dates
        return returns.tail(lookback_days)

    def fake_compute_drawdown_metrics(code: str, lookback_days: int):
        history = fake_load_price_history(code)
        closes = history["close"].astype(float).tail(lookback_days)
        cumulative = closes / closes.iloc[0]
        peaks = cumulative.cummax()
        drawdowns = cumulative / peaks - 1
        return {
            "code": code,
            "name": code,
            "lookback_days": lookback_days,
            "max_drawdown": float(drawdowns.min()),
            "current_drawdown": float(drawdowns.iloc[-1]),
            "data_date": "2026-04-03",
        }

    monkeypatch.setattr(risk_service, "portfolio_returns", fake_portfolio_returns)
    monkeypatch.setattr(risk_service, "benchmark_returns", fake_benchmark_returns)
    monkeypatch.setattr(risk_service, "compute_drawdown_metrics", fake_compute_drawdown_metrics)


def test_quant_daily_uses_local_market_data(monkeypatch):
    _patch_quant_fundamentals(monkeypatch)
    _patch_market_history(monkeypatch)
    client = TestClient(quant_app)
    response = client.post(
        "/api/v1/quant/daily",
        json={"stock_codes": ["AAPL", "NVDA"], "date": "2026-04-07", "indicators": []},
    )
    payload = response.json()["data"]
    assert response.status_code == 200
    assert payload["trade_date"] == "2026-04-03"
    assert len(payload["stocks"]) == 2
    assert {item["code"] for item in payload["stocks"]} == {"AAPL", "NVDA"}
    assert all(item["ma_signal"] in {"bullish", "bearish", "neutral"} for item in payload["stocks"])


def test_quant_factor_endpoint_returns_real_fields(monkeypatch):
    _patch_quant_fundamentals(monkeypatch)
    _patch_market_history(monkeypatch)
    client = TestClient(quant_app)
    response = client.post(
        "/api/v1/quant/factor",
        json={
            "stock_codes": ["AAPL"],
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
    _patch_market_history(monkeypatch)
    metric_calls = []
    monkeypatch.setattr(quant_service._GRAPH_REPO, "save_metric_snapshot", lambda **kwargs: metric_calls.append(kwargs))

    quant_service.daily_summary(["AAPL"], "2026-04-07", [])
    quant_service.factor_values(
        ["AAPL"],
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
    _patch_market_history(monkeypatch)
    client = TestClient(quant_app)
    response = client.post(
        "/api/v1/quant/daily",
        json={"stock_codes": ["AAPL"], "date": "2026-04-07", "indicators": []},
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


def test_risk_check_uses_history_and_industry_breakdown(monkeypatch):
    _patch_market_history(monkeypatch)
    client = TestClient(risk_app)
    response = client.post(
        "/api/v1/risk/check",
        json={
            "portfolio": [
                {"code": "AAPL", "weight": 0.4},
                {"code": "NVDA", "weight": 0.35},
                {"code": "MSFT", "weight": 0.25},
            ],
            "benchmark": "SPY",
            "lookback_days": 90,
            "run_scenarios": True,
        },
    )
    payload = response.json()["data"]
    assert response.status_code == 200
    assert payload["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert payload["industry_breakdown"]
    assert payload["top_industry_exposure"]["weight"] > 0
    assert "dotcom_style_shock" in payload["scenario_loss_estimate"]


def test_risk_services_write_graph_risk_snapshots(monkeypatch):
    _patch_market_history(monkeypatch)
    risk_calls = []
    monkeypatch.setattr(risk_service._GRAPH_REPO, "save_risk_snapshot", lambda **kwargs: risk_calls.append(kwargs))

    risk_service.risk_check(
        portfolio=[
            {"code": "AAPL", "weight": 0.4},
            {"code": "NVDA", "weight": 0.35},
            {"code": "MSFT", "weight": 0.25},
        ],
        benchmark="SPY",
        lookback_days=90,
        run_scenarios=True,
    )
    risk_service.drawdown_analysis(["AAPL"], 90)

    risk_types = {item["risk_type"] for item in risk_calls}
    assert "portfolio_weight" in risk_types
    assert "portfolio_beta" in risk_types
    assert "max_drawdown" in risk_types


def test_drawdown_endpoint_returns_real_metrics(monkeypatch):
    _patch_market_history(monkeypatch)
    client = TestClient(risk_app)
    response = client.post(
        "/api/v1/risk/drawdown",
        json={"stock_codes": ["AAPL", "NVDA"], "lookback_days": 90},
    )
    payload = response.json()["data"]
    assert response.status_code == 200
    assert len(payload["results"]) == 2
    assert all(item["max_drawdown"] is not None for item in payload["results"])
