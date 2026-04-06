from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from services.common.graph import GraphRepository
from services.common.paths import metadata_dir
from services.common.stocks import load_target_stocks
from services.quant.market_data import benchmark_returns, compute_drawdown_metrics, portfolio_returns

_GRAPH_REPO = GraphRepository(metadata_dir() / "graph_manifest.json")


def risk_check(portfolio: list[dict], benchmark: str, lookback_days: int, run_scenarios: bool) -> dict:
    weights = {item["code"]: float(item["weight"]) for item in portfolio}
    total_weight = sum(weights.values())
    returns = portfolio_returns(weights, lookback_days=lookback_days)
    peer_benchmark = benchmark_returns(
        benchmark,
        lookback_days=lookback_days,
        fallback_codes=list(weights),
    )

    alerts = []
    if total_weight > 1.01:
        alerts.append(f"组合总权重为 {total_weight:.2f}，超过 1.00，请检查持仓输入。")
    elif total_weight < 0.99:
        alerts.append(f"组合总权重为 {total_weight:.2f}，低于 1.00，当前结果基于未满仓组合估算。")

    if returns.empty:
        return {
            "risk_level": "HIGH",
            "max_drawdown_90d": 0.0,
            "volatility_annual": 0.0,
            "beta": None,
            "top_industry_exposure": None,
            "industry_breakdown": [],
            "alerts": alerts + ["未找到可用的历史行情数据，风险结果仅返回空壳结构。"],
            "scenario_loss_estimate": {},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    cumulative = (1 + returns.fillna(0.0)).cumprod()
    rolling_peak = cumulative.cummax()
    drawdowns = cumulative / rolling_peak - 1
    max_drawdown = float(drawdowns.min())
    volatility = float(returns.std(ddof=0) * (252**0.5))
    beta = _beta_against_benchmark(returns, peer_benchmark)

    industry_breakdown = _industry_breakdown(weights)
    top_industry = industry_breakdown[0] if industry_breakdown else None
    if top_industry and top_industry["weight"] >= 0.4:
        alerts.append(
            f"行业集中度偏高，{top_industry['industry']} 权重达到 {top_industry['weight']:.2%}。"
        )
    if max_drawdown <= -0.15:
        alerts.append(f"最近 {lookback_days} 日最大回撤达到 {max_drawdown:.2%}。")
    if volatility >= 0.3:
        alerts.append(f"组合年化波动率为 {volatility:.2%}，处于偏高水平。")

    scenario_loss = _scenario_losses(max_drawdown, volatility, beta, run_scenarios)
    risk_level = _risk_level(max_drawdown, volatility, top_industry["weight"] if top_industry else 0.0)
    risk_date = datetime.now().date().isoformat()
    for item in portfolio:
        code = item["code"]
        weight = float(item["weight"])
        entity_name = str(load_target_stocks().get(code, {}).get("name") or code)
        _GRAPH_REPO.save_risk_snapshot(
            entity_key=code,
            entity_name=entity_name,
            risk_type="portfolio_weight",
            risk_level=risk_level,
            risk_value=weight,
            risk_date=risk_date,
            source="risk_check",
            metadata={"benchmark": benchmark, "lookback_days": lookback_days},
        )
        _GRAPH_REPO.save_risk_snapshot(
            entity_key=code,
            entity_name=entity_name,
            risk_type="portfolio_beta",
            risk_level=risk_level,
            risk_value=beta,
            risk_date=risk_date,
            source="risk_check",
            metadata={"benchmark": benchmark, "lookback_days": lookback_days},
        )
    return {
        "risk_level": risk_level,
        "max_drawdown_90d": round(max_drawdown, 4),
        "volatility_annual": round(volatility, 4),
        "beta": round(beta, 4) if beta is not None else None,
        "top_industry_exposure": top_industry,
        "industry_breakdown": industry_breakdown,
        "alerts": alerts,
        "scenario_loss_estimate": scenario_loss,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def drawdown_analysis(stock_codes: list[str], lookback_days: int) -> dict:
    results = [compute_drawdown_metrics(code, lookback_days=lookback_days) for code in stock_codes]
    risk_date = datetime.now().date().isoformat()
    stock_map = load_target_stocks()
    for item in results:
        entity_name = str(stock_map.get(item["code"], {}).get("name") or item["code"])
        _GRAPH_REPO.save_risk_snapshot(
            entity_key=item["code"],
            entity_name=entity_name,
            risk_type="max_drawdown",
            risk_level=_drawdown_risk_level(item.get("max_drawdown")),
            risk_value=item.get("max_drawdown"),
            risk_date=risk_date,
            source="drawdown_analysis",
            metadata={"lookback_days": lookback_days},
        )
    return {"results": results}


def _industry_breakdown(weights: dict[str, float]) -> list[dict]:
    stock_map = load_target_stocks()
    exposures: dict[str, float] = {}
    for code, weight in weights.items():
        industry = str(stock_map.get(code, {}).get("industry") or "未知行业")
        exposures[industry] = exposures.get(industry, 0.0) + weight
    ranked = sorted(exposures.items(), key=lambda item: item[1], reverse=True)
    return [{"industry": industry, "weight": round(weight, 4)} for industry, weight in ranked]


def _beta_against_benchmark(returns: pd.Series, benchmark: pd.Series) -> float | None:
    if returns.empty or benchmark.empty:
        return None
    merged = pd.concat([returns.rename("portfolio"), benchmark.rename("benchmark")], axis=1).dropna()
    if len(merged) < 5 or merged["benchmark"].var(ddof=0) == 0:
        return None
    covariance = merged["portfolio"].cov(merged["benchmark"])
    variance = merged["benchmark"].var(ddof=0)
    if variance == 0:
        return None
    return float(covariance / variance)


def _scenario_losses(max_drawdown: float, volatility: float, beta: float | None, run_scenarios: bool) -> dict[str, float]:
    if not run_scenarios:
        return {}
    beta_multiplier = abs(beta) if beta is not None else 1.0
    severe = max(abs(max_drawdown) * 1.6, volatility * 1.8, 0.08) * beta_multiplier
    medium = max(abs(max_drawdown) * 1.2, volatility * 1.2, 0.05) * beta_multiplier
    mild = max(abs(max_drawdown) * 0.8, volatility * 0.8, 0.03) * beta_multiplier
    return {
        "2015_crash": round(-severe, 4),
        "2018_trade_war": round(-medium, 4),
        "2022_russia_ukraine": round(-mild, 4),
    }


def _risk_level(max_drawdown: float, volatility: float, top_industry_weight: float) -> str:
    if max_drawdown <= -0.25 or volatility >= 0.45 or top_industry_weight >= 0.6:
        return "CRITICAL"
    if max_drawdown <= -0.18 or volatility >= 0.3 or top_industry_weight >= 0.45:
        return "HIGH"
    if max_drawdown <= -0.1 or volatility >= 0.18 or top_industry_weight >= 0.3:
        return "MEDIUM"
    return "LOW"


def _drawdown_risk_level(max_drawdown: float | None) -> str:
    if max_drawdown is None:
        return "UNKNOWN"
    if max_drawdown <= -0.25:
        return "CRITICAL"
    if max_drawdown <= -0.18:
        return "HIGH"
    if max_drawdown <= -0.1:
        return "MEDIUM"
    return "LOW"
