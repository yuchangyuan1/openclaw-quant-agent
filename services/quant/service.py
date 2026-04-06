from __future__ import annotations

from datetime import date

from services.common.graph import GraphRepository
from services.common.paths import metadata_dir

from .akshare_fetcher import fetch_daily_hist, save_to_parquet
from .market_data import build_snapshot, compute_factor_payload, load_price_history, market_data_dir

_GRAPH_REPO = GraphRepository(metadata_dir() / "graph_manifest.json")


def daily_summary(stock_codes: list[str], trade_date: str | None, indicators: list[str]) -> dict:
    snapshots = [build_snapshot(code, trade_date=trade_date) for code in stock_codes]
    snapshots = [item for item in snapshots if item is not None]
    resolved_trade_date = trade_date or max((item.data_date for item in snapshots), default=date.today().isoformat())

    stock_payload = [
        {
            "code": item.code,
            "name": item.name,
            "close": item.close,
            "pct_change": item.pct_change,
            "volume": item.volume,
            "turnover_rate": item.turnover_rate,
            "ma5": item.ma5,
            "ma20": item.ma20,
            "ma_signal": item.ma_signal,
            "momentum_5d": item.momentum_5d,
            "momentum_20d": item.momentum_20d,
            "volatility_20d": item.volatility_20d,
            "data_date": item.data_date,
            "industry": item.industry,
            "report_period": item.report_period,
            "market_cap": item.market_cap,
            "float_market_cap": item.float_market_cap,
            "pe_ttm": item.pe_ttm,
            "pb": item.pb,
            "eps_ttm": item.eps_ttm,
            "book_value_per_share": item.book_value_per_share,
            "operating_cashflow_per_share": item.operating_cashflow_per_share,
            "roe": item.roe,
            "gross_margin": item.gross_margin,
            "net_margin": item.net_margin,
            "revenue_growth": item.revenue_growth,
            "net_profit_growth": item.net_profit_growth,
            "debt_to_asset": item.debt_to_asset,
            "current_ratio": item.current_ratio,
            "quick_ratio": item.quick_ratio,
            "industry_comparison": item.industry_comparison,
            "technical_score": item.technical_score,
            "fundamental_score": item.fundamental_score,
            "valuation_score": item.valuation_score,
            "composite_score": item.composite_score,
            "technical_view": item.technical_view,
            "fundamental_view": item.fundamental_view,
            "valuation_view": item.valuation_view,
            "composite_signal": item.composite_signal,
        }
        for item in snapshots
    ]
    for item in snapshots:
        for metric_name, metric_value in (
            ("close_price", item.close),
            ("pct_change", item.pct_change),
            ("turnover_rate", item.turnover_rate),
            ("momentum_5d", item.momentum_5d),
            ("momentum_20d", item.momentum_20d),
            ("volatility_20d", item.volatility_20d),
            ("pe_ttm", item.pe_ttm),
            ("pb", item.pb),
            ("roe", item.roe),
            ("gross_margin", item.gross_margin),
            ("net_margin", item.net_margin),
            ("revenue_growth", item.revenue_growth),
            ("net_profit_growth", item.net_profit_growth),
            ("debt_to_asset", item.debt_to_asset),
            ("current_ratio", item.current_ratio),
            ("quick_ratio", item.quick_ratio),
            ("technical_score", item.technical_score),
            ("fundamental_score", item.fundamental_score),
            ("valuation_score", item.valuation_score),
            ("composite_score", item.composite_score),
        ):
            _GRAPH_REPO.save_metric_snapshot(
                entity_key=item.code,
                entity_name=item.name,
                metric_name=metric_name,
                metric_value=metric_value,
                metric_date=item.data_date,
                source="quant_daily_summary",
                metadata={"industry": item.industry, "report_period": item.report_period},
            )

    advancing = sum(1 for item in snapshots if item.pct_change > 0)
    declining = sum(1 for item in snapshots if item.pct_change < 0)
    avg_pct_change = round(sum(item.pct_change for item in snapshots) / len(snapshots), 2) if snapshots else 0.0
    total_volume = sum(item.volume for item in snapshots)

    return {
        "trade_date": max((item.data_date for item in snapshots), default=resolved_trade_date),
        "market_summary": {
            "sh300_pct_change": avg_pct_change,
            "total_volume_billion": round(total_volume / 10000, 2),
            "advancing_stocks": advancing,
            "declining_stocks": declining,
            "coverage_count": len(snapshots),
            "data_source": "market_parquet_plus_fundamental_cache",
        },
        "stocks": stock_payload,
        "requested_trade_date": resolved_trade_date,
        "missing_codes": [code for code in stock_codes if code not in {item.code for item in snapshots}],
    }


def batch_hist(stock_codes: list[str], start_date: str, end_date: str | None, adjust: str) -> dict:
    end = end_date or date.today().isoformat()
    saved_files = []
    missing_codes = []

    for code in stock_codes:
        history = load_price_history(code, start_date=start_date, end_date=end)
        if history.empty:
            fetched = fetch_daily_hist(
                code=code,
                start=start_date.replace("-", ""),
                end=end.replace("-", ""),
                adjust=adjust,
            )
            if fetched.empty:
                missing_codes.append(code)
                continue
            path = save_to_parquet(fetched, code, str(market_data_dir()))
            saved_files.append(str(path))
            continue

        path = market_data_dir() / f"{code}_daily.parquet"
        history.to_parquet(path, index=False)
        saved_files.append(str(path))

    status = "completed" if not missing_codes else "partial"
    return {
        "job_id": f"batch_hist_{start_date.replace('-', '')}_{end.replace('-', '')}",
        "status": status,
        "saved_files": saved_files,
        "missing_codes": missing_codes,
    }


def factor_values(stock_codes: list[str], factors: list[str], trade_date: str | None) -> dict:
    resolved_factors = factors or [
        "momentum_1m",
        "volatility_1m",
        "price_rank_1y",
        "pe_ttm",
        "roe",
        "revenue_growth",
        "industry_pe_percentile",
        "composite_score",
    ]
    payload = [compute_factor_payload(code, resolved_factors, trade_date=trade_date) for code in stock_codes]
    for item in payload:
        metric_date = item.get("data_date")
        if not metric_date:
            continue
        for factor_name in resolved_factors:
            _GRAPH_REPO.save_metric_snapshot(
                entity_key=item["code"],
                entity_name=item["name"],
                metric_name=factor_name,
                metric_value=item.get(factor_name),
                metric_date=metric_date,
                source="quant_factor_values",
                metadata={
                    "industry": item.get("industry"),
                    "report_period": item.get("report_period"),
                },
            )
    dates = [item["data_date"] for item in payload if item.get("data_date")]
    return {
        "date": max(dates) if dates else (trade_date or date.today().isoformat()),
        "factors": payload,
        "requested_factors": resolved_factors,
    }
