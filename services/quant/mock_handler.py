"""
Quant 服务 Stub 实现（阶段 0）
阶段 2 替换为真实的 Akshare 数据计算。
"""

from datetime import date


def daily_summary(stock_codes: list[str], trade_date: str | None, indicators: list[str]) -> dict:
    target_date = trade_date or date.today().strftime("%Y-%m-%d")
    stub_stocks = [
        {
            "code": code,
            "name": {"600519": "贵州茅台", "000001": "平安银行", "300750": "宁德时代",
                     "601318": "中国平安", "300059": "东方财富"}.get(code, f"股票{code}"),
            "close": 1780.00,
            "pct_change": 1.23,
            "volume": 125430,
            "turnover_rate": 0.21,
            "ma5": 1762.4,
            "ma20": 1745.8,
            "ma_signal": "bullish",
            "momentum_5d": 2.1,
            "pe_ttm": 28.5,
            "pb": 8.2,
            "data_date": target_date,
        }
        for code in stock_codes
    ]
    return {
        "trade_date": target_date,
        "market_summary": {
            "sh300_pct_change": 0.85,
            "total_volume_billion": 8523.4,
            "advancing_stocks": 2891,
            "declining_stocks": 1205,
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
        "date": date or "2026-04-07",
        "factors": [
            {"code": code, "momentum_1m": 3.2, "pe_rank": 0.65, "roe_growth": 0.12}
            for code in stock_codes
        ],
    }
