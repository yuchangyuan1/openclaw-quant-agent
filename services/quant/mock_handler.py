"""Development stub for the quant service."""

from datetime import date

_STUB_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com Inc.",
    "META": "Meta Platforms Inc.",
    "NVDA": "NVIDIA Corporation",
    "TSLA": "Tesla Inc.",
}


def daily_summary(stock_codes: list[str], trade_date: str | None, indicators: list[str]) -> dict:
    target_date = trade_date or date.today().strftime("%Y-%m-%d")
    stub_stocks = [
        {
            "code": code,
            "name": _STUB_NAMES.get(code, f"Stub {code}"),
            "close": 210.0,
            "pct_change": 1.23,
            "volume": 1_254_300,
            "turnover_rate": 0.21,
            "ma5": 208.4,
            "ma20": 205.8,
            "ma_signal": "bullish",
            "momentum_5d": 2.1,
            "pe_ttm": 22.3,
            "pb": 8.2,
            "data_date": target_date,
        }
        for code in stock_codes
    ]
    return {
        "trade_date": target_date,
        "market_summary": {
            "tracked_avg_pct_change": 0.85,
            "advancing_stocks": len(stub_stocks),
            "declining_stocks": 0,
            "coverage_count": len(stub_stocks),
        },
        "stocks": stub_stocks,
    }


def batch_hist(stock_codes: list[str], start_date: str, end_date: str | None, adjust: str) -> dict:
    files = [f"data/market/{code}_daily.parquet" for code in stock_codes]
    return {
        "job_id": "batch_hist_stub_001",
        "status": "completed",
        "saved_files": files,
    }


def factor_values(stock_codes: list[str], factors: list[str], date: str | None) -> dict:
    return {
        "date": date or "2026-04-08",
        "factors": [
            {"code": code, "momentum_1m": 3.2, "pe_ttm": 22.3, "roe": 31.5}
            for code in stock_codes
        ],
    }
