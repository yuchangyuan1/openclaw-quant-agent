"""
Risk 服务 Stub 实现（阶段 0）
阶段 2 替换为真实的风险指标计算。
"""

from datetime import datetime, timezone


def risk_check(portfolio: list[dict], benchmark: str, lookback_days: int, run_scenarios: bool) -> dict:
    # 检查行业集中度（stub 逻辑）
    total_weight = sum(h["weight"] for h in portfolio)
    alerts = []
    if total_weight > 1.01:
        alerts.append(f"投资组合权重之和 {total_weight:.2f} 超过 1，请检查数据")

    return {
        "risk_level": "MEDIUM",
        "max_drawdown_90d": -0.12,
        "volatility_annual": 0.24,
        "beta": 1.05,
        "top_industry_exposure": {"industry": "电力设备", "weight": 0.28},
        "industry_breakdown": [
            {"industry": "电力设备", "weight": 0.28},
            {"industry": "食品饮料", "weight": 0.18},
            {"industry": "银行", "weight": 0.15},
        ],
        "alerts": alerts,
        "scenario_loss_estimate": {
            "2015_crash": -0.18,
            "2018_trade_war": -0.12,
            "2022_russia_ukraine": -0.08,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def drawdown_analysis(stock_codes: list[str], lookback_days: int) -> dict:
    return {
        "results": [
            {
                "code": code,
                "max_drawdown": -0.08,
                "current_drawdown": -0.03,
                "recovery_days": None,
            }
            for code in stock_codes
        ]
    }
