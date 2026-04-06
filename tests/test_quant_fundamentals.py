from services.quant import fundamentals
from services.quant.fundamentals import FundamentalSnapshot


def test_load_fundamental_snapshot_prefers_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals, "financial_data_dir", lambda: tmp_path)
    snapshot = FundamentalSnapshot(
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
        source="test-cache",
        valuation_method="test",
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "600519.json").write_text(
        __import__("json").dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    loaded = fundamentals.load_fundamental_snapshot("600519", fetch_if_missing=False)
    assert loaded is not None
    assert loaded.code == "600519"
    assert loaded.pe_ttm == 22.3
    assert loaded.roe == 31.5


def test_build_industry_comparison_aggregates_peer_percentiles(monkeypatch):
    current = FundamentalSnapshot(
        code="600519",
        name="贵州茅台",
        industry="白酒Ⅱ",
        report_period="2025-12-31",
        data_date="2025-12-31",
        fetched_at="2026-04-06T10:00:00",
        pe_ttm=20.0,
        pb=7.0,
        roe=30.0,
        gross_margin=90.0,
        net_margin=50.0,
        revenue_growth=15.0,
        net_profit_growth=14.0,
        debt_to_asset=20.0,
        current_ratio=4.0,
        quick_ratio=3.0,
        close_price=1400.0,
        market_cap=1.0,
        float_market_cap=1.0,
        eps_ttm=70.0,
        eps_latest=70.0,
        book_value_per_share=200.0,
        operating_cashflow_per_share=30.0,
    )
    peers = [
        FundamentalSnapshot(
            code="000858",
            name="五粮液",
            industry="白酒Ⅱ",
            report_period="2025-12-31",
            data_date="2025-12-31",
            fetched_at="2026-04-06T10:00:00",
            pe_ttm=24.0,
            pb=6.0,
            roe=24.0,
            gross_margin=80.0,
            net_margin=35.0,
            revenue_growth=10.0,
            net_profit_growth=8.0,
            debt_to_asset=30.0,
            current_ratio=2.0,
            quick_ratio=1.5,
            close_price=150.0,
            market_cap=1.0,
            float_market_cap=1.0,
            eps_ttm=6.0,
            eps_latest=6.0,
            book_value_per_share=25.0,
            operating_cashflow_per_share=5.0,
        ),
        FundamentalSnapshot(
            code="000568",
            name="泸州老窖",
            industry="白酒Ⅱ",
            report_period="2025-12-31",
            data_date="2025-12-31",
            fetched_at="2026-04-06T10:00:00",
            pe_ttm=22.0,
            pb=5.5,
            roe=26.0,
            gross_margin=78.0,
            net_margin=30.0,
            revenue_growth=9.0,
            net_profit_growth=7.0,
            debt_to_asset=28.0,
            current_ratio=2.5,
            quick_ratio=1.8,
            close_price=140.0,
            market_cap=1.0,
            float_market_cap=1.0,
            eps_ttm=5.0,
            eps_latest=5.0,
            book_value_per_share=20.0,
            operating_cashflow_per_share=4.0,
        ),
    ]
    monkeypatch.setattr(
        fundamentals,
        "load_industry_peer_snapshots",
        lambda *args, **kwargs: peers,
    )
    monkeypatch.setattr(
        fundamentals,
        "load_target_stocks",
        lambda: {
            "600519": {"industry": "白酒Ⅱ"},
            "000858": {"industry": "白酒Ⅱ"},
            "000568": {"industry": "白酒Ⅱ"},
        },
    )

    comparison = fundamentals.build_industry_comparison("600519", current)
    assert comparison is not None
    assert comparison["industry"] == "白酒Ⅱ"
    assert comparison["peer_count"] == 3
    assert comparison["metrics"]["pe_ttm"]["relative"] == "better_than_industry"
    assert comparison["metrics"]["roe"]["relative"] == "better_than_industry"
