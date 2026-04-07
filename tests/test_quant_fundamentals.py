import json

from services.quant import fundamentals
from services.quant.fundamentals import FundamentalSnapshot


def test_load_fundamental_snapshot_prefers_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals, "financial_data_dir", lambda: tmp_path)
    snapshot = FundamentalSnapshot(
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
        source="test-cache",
        valuation_method="test",
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "AAPL.json").write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    loaded = fundamentals.load_fundamental_snapshot("AAPL", fetch_if_missing=False)
    assert loaded is not None
    assert loaded.code == "AAPL"
    assert loaded.pe_ttm == 22.3
    assert loaded.roe == 31.5


def test_build_industry_comparison_aggregates_peer_percentiles(monkeypatch):
    current = FundamentalSnapshot(
        code="AAPL",
        name="Apple Inc.",
        industry="Consumer Electronics",
        report_period="2025-12-31",
        data_date="2025-12-31",
        fetched_at="2026-04-06T10:00:00",
        pe_ttm=20.0,
        pb=7.0,
        roe=30.0,
        gross_margin=45.0,
        net_margin=25.0,
        revenue_growth=15.0,
        net_profit_growth=14.0,
        debt_to_asset=20.0,
        current_ratio=1.5,
        quick_ratio=1.2,
        close_price=210.0,
        market_cap=1.0,
        float_market_cap=1.0,
        eps_ttm=9.0,
        eps_latest=9.0,
        book_value_per_share=28.0,
        operating_cashflow_per_share=7.0,
    )
    peers = [
        FundamentalSnapshot(
            code="SONY",
            name="Sony Group",
            industry="Consumer Electronics",
            report_period="2025-12-31",
            data_date="2025-12-31",
            fetched_at="2026-04-06T10:00:00",
            pe_ttm=24.0,
            pb=6.0,
            roe=24.0,
            gross_margin=38.0,
            net_margin=12.0,
            revenue_growth=10.0,
            net_profit_growth=8.0,
            debt_to_asset=30.0,
            current_ratio=1.1,
            quick_ratio=0.9,
            close_price=85.0,
            market_cap=1.0,
            float_market_cap=1.0,
            eps_ttm=4.0,
            eps_latest=4.0,
            book_value_per_share=18.0,
            operating_cashflow_per_share=3.0,
        ),
        FundamentalSnapshot(
            code="DELL",
            name="Dell Technologies",
            industry="Consumer Electronics",
            report_period="2025-12-31",
            data_date="2025-12-31",
            fetched_at="2026-04-06T10:00:00",
            pe_ttm=22.0,
            pb=5.5,
            roe=26.0,
            gross_margin=30.0,
            net_margin=9.0,
            revenue_growth=9.0,
            net_profit_growth=7.0,
            debt_to_asset=28.0,
            current_ratio=1.0,
            quick_ratio=0.8,
            close_price=120.0,
            market_cap=1.0,
            float_market_cap=1.0,
            eps_ttm=6.0,
            eps_latest=6.0,
            book_value_per_share=20.0,
            operating_cashflow_per_share=4.0,
        ),
    ]
    monkeypatch.setattr(fundamentals, "load_industry_peer_snapshots", lambda *args, **kwargs: peers)
    monkeypatch.setattr(
        fundamentals,
        "load_target_stocks",
        lambda: {
            "AAPL": {"industry": "Consumer Electronics"},
            "SONY": {"industry": "Consumer Electronics"},
            "DELL": {"industry": "Consumer Electronics"},
        },
    )

    comparison = fundamentals.build_industry_comparison("AAPL", current)
    assert comparison is not None
    assert comparison["industry"] == "Consumer Electronics"
    assert comparison["peer_count"] == 3
    assert comparison["metrics"]["pe_ttm"]["relative"] == "better_than_industry"
    assert comparison["metrics"]["roe"]["relative"] == "better_than_industry"
