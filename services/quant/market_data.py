from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Any

import pandas as pd

from services.common.paths import resolve_project_path
from services.common.stocks import load_target_stocks

from . import config
from .akshare_fetcher import fetch_daily_hist, save_to_parquet
from .fundamentals import build_industry_comparison, load_fundamental_snapshot


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
    path = _resolve_market_file(code)
    if path is None and refresh_if_missing:
        df = fetch_daily_hist(
            code=code,
            start=(start_date or "20240101").replace("-", ""),
            end=(end_date or pd.Timestamp.today().strftime("%Y%m%d")).replace("-", ""),
        )
        if not df.empty:
            path = save_to_parquet(df, code, str(market_data_dir()))

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

    column_map = {
        "日期": "date",
        "trade_date": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "amount": "amount",
    }
    normalized = df.rename(columns=column_map).copy()
    if "date" not in normalized.columns:
        raise ValueError("missing date column in market data")
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    normalized = normalized.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    for column in ["open", "close", "high", "low", "volume", "amount"]:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    if "volume" not in normalized.columns:
        normalized["volume"] = normalized["amount"] if "amount" in normalized.columns else 0.0

    for column in ["open", "close", "high", "low"]:
        if column not in normalized.columns:
            normalized[column] = normalized["close"] if "close" in normalized.columns else 0.0

    return normalized[["date", "open", "close", "high", "low", "volume"]].dropna(subset=["close"])


def build_snapshot(code: str, *, trade_date: str | None = None) -> MarketSnapshot | None:
    history = load_price_history(code, end_date=trade_date)
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

    stock_item = load_target_stocks().get(code, {})
    fundamentals = load_fundamental_snapshot(code, fetch_if_missing=True)
    industry = (
        fundamentals.industry
        if fundamentals and fundamentals.industry
        else str(stock_item.get("industry")) if stock_item.get("industry") else None
    )
    industry_comparison = build_industry_comparison(code, fundamentals) if fundamentals else None

    technical_score = _score_technical(ma_signal, momentum_5d, momentum_20d, volatility_20d)
    fundamental_score = _score_fundamental(fundamentals)
    valuation_score = _score_valuation(fundamentals, industry_comparison)
    composite_score = _combine_scores(technical_score, fundamental_score, valuation_score)

    return MarketSnapshot(
        code=code,
        name=str(stock_item.get("name") or (fundamentals.name if fundamentals else f"Stock {code}")),
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
    snapshot = build_snapshot(code, trade_date=trade_date)
    stock_item = load_target_stocks().get(code, {})
    history = load_price_history(code, end_date=trade_date)

    payload = {
        "code": code,
        "name": snapshot.name if snapshot else str(stock_item.get("name") or f"Stock {code}"),
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

    payload["data_source"] = "market_parquet_plus_fundamental_cache"
    return payload


def portfolio_returns(weights: dict[str, float], *, lookback_days: int, end_date: str | None = None) -> pd.Series:
    frames = []
    for code, weight in weights.items():
        history = load_price_history(code, end_date=end_date)
        if history.empty:
            continue
        returns = history[["date", "close"]].copy()
        returns[code] = returns["close"].pct_change() * weight
        frames.append(returns[["date", code]])

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
    benchmark_code = benchmark.replace(".SH", "").replace(".SZ", "")
    history = load_price_history(benchmark_code, end_date=end_date)
    if len(history) >= 2:
        series = history["close"].pct_change().dropna().tail(lookback_days)
        series.index = history["date"].iloc[-len(series):]
        return series

    fallback_weights = {code: 1 / len(fallback_codes) for code in (fallback_codes or [])} if fallback_codes else {}
    return portfolio_returns(fallback_weights, lookback_days=lookback_days, end_date=end_date)


def compute_drawdown_metrics(code: str, *, lookback_days: int) -> dict:
    history = load_price_history(code)
    if history.empty:
        return {"code": code, "max_drawdown": None, "current_drawdown": None, "recovery_days": None}

    window = history.tail(max(lookback_days + 1, 2)).copy()
    rolling_peak = window["close"].cummax()
    drawdowns = window["close"] / rolling_peak - 1
    max_drawdown = float(drawdowns.min())
    current_drawdown = float(drawdowns.iloc[-1])

    if current_drawdown == 0:
        recovery_days = 0
    else:
        trough_index = drawdowns.idxmin()
        trough_close = float(window.loc[trough_index, "close"])
        prior_peak = float(rolling_peak.loc[trough_index])
        after_trough = window.loc[trough_index + 1 :].copy()
        recovered = after_trough.loc[after_trough["close"] >= prior_peak]
        recovery_days = int(len(recovered)) if not recovered.empty and trough_close < prior_peak else None

    return {
        "code": code,
        "max_drawdown": round(max_drawdown, 4),
        "current_drawdown": round(current_drawdown, 4),
        "recovery_days": recovery_days,
    }


def _resolve_market_file(code: str) -> Path | None:
    root = market_data_dir()
    for suffix in ["_daily.parquet", "_1y.parquet"]:
        path = root / f"{code}{suffix}"
        if path.exists():
            return path
    return None


def _rolling_value(series: pd.Series, window: int) -> float | None:
    if len(series) < window:
        return None
    return float(series.tail(window).mean())


def _window_return(series: pd.Series, days: int) -> float | None:
    if len(series) <= days:
        return None
    return (float(series.iloc[-1]) / float(series.iloc[-days - 1]) - 1) * 100


def _annualized_volatility(returns: pd.Series, min_periods: int) -> float | None:
    if len(returns) < min_periods:
        return None
    return float(returns.tail(min_periods).std(ddof=0) * sqrt(TRADING_DAYS_PER_YEAR))


def _price_rank(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    latest = float(series.iloc[-1])
    lower = float((series <= latest).sum())
    return lower / float(len(series))


def _score_technical(
    ma_signal: str | None,
    momentum_5d: float | None,
    momentum_20d: float | None,
    volatility_20d: float | None,
) -> float:
    score = 0.0
    if ma_signal == "bullish":
        score += 30
    elif ma_signal == "neutral":
        score += 18
    elif ma_signal == "bearish":
        score += 8

    score += _scaled_score(momentum_5d, good=6, neutral=0, cap=20) or 0.0
    score += _scaled_score(momentum_20d, good=15, neutral=0, cap=30) or 0.0

    if volatility_20d is not None:
        if volatility_20d <= 0.2:
            score += 20
        elif volatility_20d <= 0.35:
            score += 15
        elif volatility_20d <= 0.5:
            score += 8
        else:
            score += 2
    return round(min(score, 100.0), 2)


def _score_fundamental(snapshot) -> float | None:
    if snapshot is None:
        return None

    metric_scores = [
        _scaled_score(snapshot.roe, good=20, neutral=10, cap=22),
        _scaled_score(snapshot.gross_margin, good=40, neutral=25, cap=16),
        _scaled_score(snapshot.net_margin, good=15, neutral=8, cap=14),
        _scaled_score(snapshot.revenue_growth, good=15, neutral=5, cap=18),
        _scaled_score(snapshot.net_profit_growth, good=15, neutral=5, cap=18),
        _reverse_scaled_score(snapshot.debt_to_asset, good=35, neutral=50, cap=12),
    ]
    current_ratio_score = _scaled_score(snapshot.current_ratio, good=1.8, neutral=1.2, cap=10)
    quick_ratio_score = _scaled_score(snapshot.quick_ratio, good=1.2, neutral=0.8, cap=10)
    if current_ratio_score is not None or quick_ratio_score is not None:
        metric_scores.append(max(current_ratio_score or 0.0, quick_ratio_score or 0.0))
    valid_scores = [item for item in metric_scores if item is not None]
    return round(sum(valid_scores), 2) if valid_scores else None


def _score_valuation(snapshot, comparison: dict[str, Any] | None) -> float | None:
    if snapshot is None:
        return None

    metrics = comparison.get("metrics", {}) if comparison else {}
    pe_percentile = metrics.get("pe_ttm", {}).get("percentile")
    pb_percentile = metrics.get("pb", {}).get("percentile")

    scores: list[float] = []
    if pe_percentile is not None:
        scores.append(round((1 - float(pe_percentile)) * 60, 2))
    elif snapshot.pe_ttm is not None:
        fallback_score = _reverse_scaled_score(snapshot.pe_ttm, good=18, neutral=28, cap=60)
        if fallback_score is not None:
            scores.append(fallback_score)

    if pb_percentile is not None:
        scores.append(round((1 - float(pb_percentile)) * 40, 2))
    elif snapshot.pb is not None:
        fallback_score = _reverse_scaled_score(snapshot.pb, good=2, neutral=4, cap=40)
        if fallback_score is not None:
            scores.append(fallback_score)

    return round(sum(scores), 2) if scores else None


def _combine_scores(
    technical_score: float | None,
    fundamental_score: float | None,
    valuation_score: float | None,
) -> float | None:
    weighted = []
    if technical_score is not None:
        weighted.append((technical_score, 0.35))
    if fundamental_score is not None:
        weighted.append((fundamental_score, 0.4))
    if valuation_score is not None:
        weighted.append((valuation_score, 0.25))
    if not weighted:
        return None
    total_weight = sum(weight for _score, weight in weighted)
    return round(sum(score * weight for score, weight in weighted) / total_weight, 2)


def _technical_view(ma_signal: str | None, momentum_20d: float | None, volatility_20d: float | None) -> str:
    if ma_signal == "bullish" and (momentum_20d or 0) > 0 and (volatility_20d or 0.0) <= 0.35:
        return "Trend remains constructive with supportive technical momentum"
    if ma_signal == "bearish" and (momentum_20d or 0) < 0:
        return "Trend is weak and technical confirmation is still missing"
    return "Technical setup is balanced and waiting for clearer confirmation"


def _fundamental_view(snapshot) -> str:
    if snapshot is None:
        return "Fundamental data is unavailable, so the quality view is incomplete"
    positive_flags = sum(
        1
        for condition in [
            (snapshot.roe or 0) >= 15,
            (snapshot.gross_margin or 0) >= 30,
            (snapshot.revenue_growth or 0) >= 10,
            (snapshot.net_profit_growth or 0) >= 10,
            (snapshot.debt_to_asset or 100) <= 50,
        ]
        if condition
    )
    if positive_flags >= 4:
        return "Profitability and growth quality are strong"
    if positive_flags >= 2:
        return "Fundamentals are stable, but growth and leverage are mixed"
    return "Fundamentals are weaker and need further validation from future reports"


def _valuation_view(snapshot, comparison: dict[str, Any] | None) -> str:
    if snapshot is None:
        return "Valuation data is unavailable"
    metrics = comparison.get("metrics", {}) if comparison else {}
    pe_metric = metrics.get("pe_ttm")
    pb_metric = metrics.get("pb")
    if pe_metric and pb_metric:
        if pe_metric["relative"] == "better_than_industry" and pb_metric["relative"] == "better_than_industry":
            return "Valuation sits below industry averages and offers relative cushion"
        if pe_metric["relative"] == "worse_than_industry" and pb_metric["relative"] == "worse_than_industry":
            return "Valuation is richer than industry peers and needs stronger execution"
    if snapshot.pe_ttm is not None and snapshot.pe_ttm <= 20:
        return "Absolute valuation looks broadly reasonable"
    if snapshot.pe_ttm is not None and snapshot.pe_ttm >= 35:
        return "Absolute valuation is elevated and needs continued earnings delivery"
    return "Valuation is close to neutral and should be read with industry percentiles"


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


def _scaled_score(value: float | None, *, good: float, neutral: float, cap: float) -> float | None:
    if value is None:
        return None
    if value >= good:
        return cap
    if value <= neutral:
        return cap * 0.3
    ratio = (value - neutral) / (good - neutral)
    return round(cap * (0.3 + 0.7 * ratio), 2)


def _reverse_scaled_score(value: float | None, *, good: float, neutral: float, cap: float) -> float | None:
    if value is None:
        return None
    if value <= good:
        return cap
    if value >= neutral:
        return cap * 0.3
    ratio = (neutral - value) / (neutral - good)
    return round(cap * (0.3 + 0.7 * ratio), 2)


def _industry_metric_percentile(snapshot: MarketSnapshot | None, metric_name: str) -> float | None:
    if snapshot is None or not snapshot.industry_comparison:
        return None
    metric_payload = snapshot.industry_comparison.get("metrics", {}).get(metric_name, {})
    percentile = metric_payload.get("percentile")
    return round(float(percentile), 4) if percentile is not None else None
