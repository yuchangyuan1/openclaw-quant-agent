from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Any

import pandas as pd

from services.common.paths import resolve_project_path
from services.common.stocks import load_target_stocks

from . import config
from .fundamentals import build_industry_comparison, load_fundamental_snapshot
from .market_fetcher import fetch_daily_hist, save_to_parquet

TRADING_DAYS_PER_YEAR = 252


@dataclass(slots=True)
class MarketSnapshot:
    code: str
    name: str
    industry: str | None
    data_date: str
    close: float
    pct_change: float
    volume: int
    turnover_rate: float
    ma5: float | None
    ma20: float | None
    ma_signal: str | None
    momentum_5d: float | None
    momentum_20d: float | None
    volatility_20d: float | None
    report_period: str | None = None
    market_cap: float | None = None
    float_market_cap: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    eps_ttm: float | None = None
    book_value_per_share: float | None = None
    operating_cashflow_per_share: float | None = None
    roe: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    revenue_growth: float | None = None
    net_profit_growth: float | None = None
    debt_to_asset: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    industry_comparison: dict[str, Any] | None = None
    technical_score: float | None = None
    fundamental_score: float | None = None
    valuation_score: float | None = None
    composite_score: float | None = None
    technical_view: str | None = None
    fundamental_view: str | None = None
    valuation_view: str | None = None
    composite_signal: str | None = None


def market_data_dir() -> Path:
    return resolve_project_path(config.MARKET_DATA_DIR, "./data/market")


def load_price_history(
    code: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    refresh_if_missing: bool = False,
) -> pd.DataFrame:
    ticker = code.upper()
    path = _resolve_market_file(ticker)
    if path is None and refresh_if_missing:
        df = fetch_daily_hist(
            code=ticker,
            start=(start_date or "2024-01-01").replace("-", ""),
            end=(end_date or pd.Timestamp.today().strftime("%Y%m%d")).replace("-", ""),
        )
        if not df.empty:
            path = save_to_parquet(df, ticker, str(market_data_dir()))

    if path is None or not path.exists():
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume"])

    df = pd.read_parquet(path)
    normalized = normalize_history(df)
    if start_date:
        normalized = normalized.loc[normalized["date"] >= pd.Timestamp(start_date)].copy()
    if end_date:
        normalized = normalized.loc[normalized["date"] <= pd.Timestamp(end_date)].copy()
    return normalized.reset_index(drop=True)


def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume"])

    normalized = df.rename(
        columns={
            "Date": "date",
            "date": "date",
            "trade_date": "date",
            "Open": "open",
            "open": "open",
            "Close": "close",
            "close": "close",
            "High": "high",
            "high": "high",
            "Low": "low",
            "low": "low",
            "Volume": "volume",
            "volume": "volume",
        }
    ).copy()
    if "date" not in normalized.columns:
        raise ValueError("missing date column in market data")

    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    normalized = normalized.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    for column in ["open", "close", "high", "low", "volume"]:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    if "volume" not in normalized.columns:
        normalized["volume"] = 0.0
    for column in ["open", "high", "low"]:
        if column not in normalized.columns:
            normalized[column] = normalized["close"] if "close" in normalized.columns else 0.0

    return normalized[["date", "open", "close", "high", "low", "volume"]].dropna(subset=["close"])


def build_snapshot(code: str, *, trade_date: str | None = None) -> MarketSnapshot | None:
    ticker = code.upper()
    history = load_price_history(ticker, end_date=trade_date)
    if len(history) < 2:
        return None

    latest = history.iloc[-1]
    previous = history.iloc[-2]
    ma5 = _rolling_value(history["close"], 5)
    ma20 = _rolling_value(history["close"], 20)
    momentum_5d = _window_return(history["close"], 5)
    momentum_20d = _window_return(history["close"], 20)
    volatility_20d = _annualized_volatility(history["close"].pct_change().dropna(), 20)

    if ma5 is None or ma20 is None:
        ma_signal = None
    elif latest["close"] > ma5 > ma20:
        ma_signal = "bullish"
    elif latest["close"] < ma5 < ma20:
        ma_signal = "bearish"
    else:
        ma_signal = "neutral"

    stock_item = load_target_stocks().get(ticker, {})
    fundamentals = load_fundamental_snapshot(ticker, fetch_if_missing=True)
    industry = (
        fundamentals.industry
        if fundamentals and fundamentals.industry
        else str(stock_item.get("industry")) if stock_item.get("industry") else None
    )
    industry_comparison = build_industry_comparison(ticker, fundamentals) if fundamentals else None

    technical_score = _score_technical(ma_signal, momentum_5d, momentum_20d, volatility_20d)
    fundamental_score = _score_fundamental(fundamentals)
    valuation_score = _score_valuation(fundamentals, industry_comparison)
    composite_score = _combine_scores(technical_score, fundamental_score, valuation_score)

    return MarketSnapshot(
        code=ticker,
        name=str(stock_item.get("name") or (fundamentals.name if fundamentals else ticker)),
        industry=industry,
        data_date=latest["date"].date().isoformat(),
        close=round(float(latest["close"]), 2),
        pct_change=round((float(latest["close"]) / float(previous["close"]) - 1) * 100, 2),
        volume=int(float(latest["volume"])),
        turnover_rate=0.0,
        ma5=round(ma5, 2) if ma5 is not None else None,
        ma20=round(ma20, 2) if ma20 is not None else None,
        ma_signal=ma_signal,
        momentum_5d=round(momentum_5d, 2) if momentum_5d is not None else None,
        momentum_20d=round(momentum_20d, 2) if momentum_20d is not None else None,
        volatility_20d=round(volatility_20d, 4) if volatility_20d is not None else None,
        report_period=fundamentals.report_period if fundamentals else None,
        market_cap=round(fundamentals.market_cap, 2) if fundamentals and fundamentals.market_cap is not None else None,
        float_market_cap=round(fundamentals.float_market_cap, 2)
        if fundamentals and fundamentals.float_market_cap is not None
        else None,
        pe_ttm=round(fundamentals.pe_ttm, 4) if fundamentals and fundamentals.pe_ttm is not None else None,
        pb=round(fundamentals.pb, 4) if fundamentals and fundamentals.pb is not None else None,
        eps_ttm=round(fundamentals.eps_ttm, 4) if fundamentals and fundamentals.eps_ttm is not None else None,
        book_value_per_share=round(fundamentals.book_value_per_share, 4)
        if fundamentals and fundamentals.book_value_per_share is not None
        else None,
        operating_cashflow_per_share=round(fundamentals.operating_cashflow_per_share, 4)
        if fundamentals and fundamentals.operating_cashflow_per_share is not None
        else None,
        roe=round(fundamentals.roe, 4) if fundamentals and fundamentals.roe is not None else None,
        gross_margin=round(fundamentals.gross_margin, 4)
        if fundamentals and fundamentals.gross_margin is not None
        else None,
        net_margin=round(fundamentals.net_margin, 4)
        if fundamentals and fundamentals.net_margin is not None
        else None,
        revenue_growth=round(fundamentals.revenue_growth, 4)
        if fundamentals and fundamentals.revenue_growth is not None
        else None,
        net_profit_growth=round(fundamentals.net_profit_growth, 4)
        if fundamentals and fundamentals.net_profit_growth is not None
        else None,
        debt_to_asset=round(fundamentals.debt_to_asset, 4)
        if fundamentals and fundamentals.debt_to_asset is not None
        else None,
        current_ratio=round(fundamentals.current_ratio, 4)
        if fundamentals and fundamentals.current_ratio is not None
        else None,
        quick_ratio=round(fundamentals.quick_ratio, 4)
        if fundamentals and fundamentals.quick_ratio is not None
        else None,
        industry_comparison=industry_comparison,
        technical_score=technical_score,
        fundamental_score=fundamental_score,
        valuation_score=valuation_score,
        composite_score=composite_score,
        technical_view=_technical_view(ma_signal, momentum_20d, volatility_20d),
        fundamental_view=_fundamental_view(fundamentals),
        valuation_view=_valuation_view(fundamentals, industry_comparison),
        composite_signal=_composite_signal(composite_score),
    )


def compute_factor_payload(code: str, factors: list[str], *, trade_date: str | None = None) -> dict:
    ticker = code.upper()
    snapshot = build_snapshot(ticker, trade_date=trade_date)
    stock_item = load_target_stocks().get(ticker, {})
    history = load_price_history(ticker, end_date=trade_date)

    payload = {
        "code": ticker,
        "name": snapshot.name if snapshot else str(stock_item.get("name") or ticker),
        "industry": snapshot.industry if snapshot else stock_item.get("industry"),
        "data_date": snapshot.data_date if snapshot else trade_date,
        "report_period": snapshot.report_period if snapshot else None,
    }

    factor_map = {
        "momentum_1m": snapshot.momentum_20d if snapshot else None,
        "momentum_3m": _window_return(history["close"], 60) if not history.empty else None,
        "volatility_1m": snapshot.volatility_20d if snapshot else None,
        "price_rank_1y": round(_price_rank(history["close"]), 4) if not history.empty else None,
        "pe_ttm": snapshot.pe_ttm if snapshot else None,
        "pb": snapshot.pb if snapshot else None,
        "market_cap": snapshot.market_cap if snapshot else None,
        "roe": snapshot.roe if snapshot else None,
        "gross_margin": snapshot.gross_margin if snapshot else None,
        "net_margin": snapshot.net_margin if snapshot else None,
        "revenue_growth": snapshot.revenue_growth if snapshot else None,
        "net_profit_growth": snapshot.net_profit_growth if snapshot else None,
        "debt_to_asset": snapshot.debt_to_asset if snapshot else None,
        "current_ratio": snapshot.current_ratio if snapshot else None,
        "quick_ratio": snapshot.quick_ratio if snapshot else None,
        "technical_score": snapshot.technical_score if snapshot else None,
        "fundamental_score": snapshot.fundamental_score if snapshot else None,
        "valuation_score": snapshot.valuation_score if snapshot else None,
        "composite_score": snapshot.composite_score if snapshot else None,
        "pe_rank": _industry_metric_percentile(snapshot, "pe_ttm"),
        "roe_growth": snapshot.roe if snapshot else None,
        "industry_pe_percentile": _industry_metric_percentile(snapshot, "pe_ttm"),
        "industry_pb_percentile": _industry_metric_percentile(snapshot, "pb"),
        "industry_roe_percentile": _industry_metric_percentile(snapshot, "roe"),
        "industry_revenue_growth_percentile": _industry_metric_percentile(snapshot, "revenue_growth"),
    }

    for factor in factors:
        value = factor_map.get(factor)
        payload[factor] = round(value, 4) if isinstance(value, float) else value

    payload["data_source"] = "yfinance_market_cache_plus_fundamental_cache"
    return payload


def portfolio_returns(weights: dict[str, float], *, lookback_days: int, end_date: str | None = None) -> pd.Series:
    frames = []
    for code, weight in weights.items():
        history = load_price_history(code.upper(), end_date=end_date)
        if history.empty:
            continue
        returns = history[["date", "close"]].copy()
        returns[code.upper()] = returns["close"].pct_change() * weight
        frames.append(returns[["date", code.upper()]])

    if not frames:
        return pd.Series(dtype=float)

    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="date", how="outer")
    merged = merged.sort_values("date").tail(max(lookback_days + 1, 2))
    merged = merged.fillna(0.0)
    portfolio = merged.drop(columns=["date"]).sum(axis=1)
    portfolio.index = merged["date"]
    return portfolio


def benchmark_returns(
    benchmark: str,
    *,
    lookback_days: int,
    end_date: str | None = None,
    fallback_codes: list[str] | None = None,
) -> pd.Series:
    benchmark_code = benchmark.upper().replace(".SH", "").replace(".SZ", "")
    history = load_price_history(benchmark_code, end_date=end_date)
    if len(history) >= 2:
        series = history["close"].pct_change().dropna().tail(lookback_days)
        series.index = history["date"].iloc[-len(series):]
        return series

    fallback_weights = {code: 1 / len(fallback_codes) for code in (fallback_codes or [])} if fallback_codes else {}
    return portfolio_returns(fallback_weights, lookback_days=lookback_days, end_date=end_date)


def compute_drawdown_metrics(code: str, *, lookback_days: int) -> dict:
    ticker = code.upper()
    history = load_price_history(ticker)
    if history.empty:
        return {
            "code": ticker,
            "max_drawdown": None,
            "peak_date": None,
            "trough_date": None,
            "recovery_status": "NO_DATA",
            "latest_close": None,
        }

    recent = history.tail(max(lookback_days, 2)).copy()
    cumulative = recent["close"] / recent["close"].iloc[0]
    rolling_peak = cumulative.cummax()
    drawdown = cumulative / rolling_peak - 1
    trough_index = drawdown.idxmin()
    peak_index = cumulative.loc[:trough_index].idxmax()
    latest_close = float(recent["close"].iloc[-1])

    return {
        "code": ticker,
        "max_drawdown": round(float(drawdown.min()), 4),
        "peak_date": recent.loc[peak_index, "date"].date().isoformat(),
        "trough_date": recent.loc[trough_index, "date"].date().isoformat(),
        "recovery_status": "RECOVERED" if latest_close >= float(recent.loc[peak_index, "close"]) else "UNDERWATER",
        "latest_close": round(latest_close, 2),
    }


def _resolve_market_file(code: str) -> Path | None:
    root = market_data_dir()
    candidates = [root / f"{code.upper()}_daily.parquet", root / f"{code.upper()}_1y.parquet"]
    for path in candidates:
        if path.exists():
            return path
    return None


def _rolling_value(series: pd.Series, window: int) -> float | None:
    if len(series) < window:
        return None
    return float(series.tail(window).mean())


def _window_return(series: pd.Series, window: int) -> float | None:
    if len(series) < window + 1:
        return None
    start_value = float(series.iloc[-window - 1])
    end_value = float(series.iloc[-1])
    if start_value == 0:
        return None
    return (end_value / start_value - 1) * 100


def _annualized_volatility(returns: pd.Series, window: int) -> float | None:
    if len(returns) < window:
        return None
    sample = returns.tail(window)
    return float(sample.std(ddof=0) * sqrt(TRADING_DAYS_PER_YEAR))


def _price_rank(series: pd.Series) -> float:
    values = series.dropna()
    if values.empty:
        return 0.0
    latest = float(values.iloc[-1])
    min_value = float(values.min())
    max_value = float(values.max())
    if max_value == min_value:
        return 1.0
    return (latest - min_value) / (max_value - min_value)


def _score_technical(
    ma_signal: str | None,
    momentum_5d: float | None,
    momentum_20d: float | None,
    volatility_20d: float | None,
) -> float | None:
    score = 50.0
    if ma_signal == "bullish":
        score += 15
    elif ma_signal == "bearish":
        score -= 15
    if momentum_5d is not None:
        score += max(min(momentum_5d, 10), -10)
    if momentum_20d is not None:
        score += max(min(momentum_20d / 2, 10), -10)
    if volatility_20d is not None:
        score -= min(volatility_20d * 100, 15)
    return round(max(min(score, 100), 0), 2)


def _score_fundamental(snapshot) -> float | None:
    if snapshot is None:
        return None
    score = 50.0
    for value, weight in [
        (snapshot.roe, 0.4),
        (snapshot.gross_margin, 0.15),
        (snapshot.net_margin, 0.15),
        (snapshot.revenue_growth, 0.15),
        (snapshot.net_profit_growth, 0.15),
    ]:
        if value is not None:
            score += max(min(value, 30), -10) * weight
    if snapshot.debt_to_asset is not None:
        score -= min(snapshot.debt_to_asset / 4, 15)
    return round(max(min(score, 100), 0), 2)


def _score_valuation(snapshot, industry_comparison: dict[str, Any] | None) -> float | None:
    if snapshot is None:
        return None
    score = 50.0
    metrics = (industry_comparison or {}).get("metrics", {})
    for metric_name in ["pe_ttm", "pb"]:
        metric = metrics.get(metric_name)
        if metric:
            percentile = metric.get("percentile")
            if percentile is not None:
                score += (0.5 - float(percentile)) * 30
    if snapshot.pe_ttm is not None and snapshot.pe_ttm < 20:
        score += 5
    if snapshot.pb is not None and snapshot.pb < 5:
        score += 5
    return round(max(min(score, 100), 0), 2)


def _combine_scores(*scores: float | None) -> float | None:
    values = [score for score in scores if score is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _technical_view(ma_signal: str | None, momentum_20d: float | None, volatility_20d: float | None) -> str | None:
    if ma_signal == "bullish" and (momentum_20d or 0) > 0:
        return "Positive trend"
    if ma_signal == "bearish" and (momentum_20d or 0) < 0:
        return "Weak trend"
    if volatility_20d and volatility_20d > 0.4:
        return "High volatility"
    return "Mixed"


def _fundamental_view(snapshot) -> str | None:
    if snapshot is None:
        return None
    if snapshot.roe and snapshot.roe >= 20 and snapshot.revenue_growth and snapshot.revenue_growth > 10:
        return "Strong fundamentals"
    if snapshot.net_margin and snapshot.net_margin < 5:
        return "Margin pressure"
    return "Balanced fundamentals"


def _valuation_view(snapshot, industry_comparison: dict[str, Any] | None) -> str | None:
    if snapshot is None:
        return None
    metrics = (industry_comparison or {}).get("metrics", {})
    pe_metric = metrics.get("pe_ttm")
    if pe_metric and pe_metric.get("percentile") is not None:
        if float(pe_metric["percentile"]) <= 0.35:
            return "Relatively attractive"
        if float(pe_metric["percentile"]) >= 0.7:
            return "Relatively expensive"
    return "Fairly valued"


def _composite_signal(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 75:
        return "POSITIVE"
    if score >= 60:
        return "BALANCED"
    if score >= 45:
        return "NEUTRAL"
    return "CAUTION"


def _industry_metric_percentile(snapshot: MarketSnapshot | None, metric_name: str) -> float | None:
    if snapshot is None or not snapshot.industry_comparison:
        return None
    metric = snapshot.industry_comparison.get("metrics", {}).get(metric_name)
    if not metric:
        return None
    return metric.get("percentile")
