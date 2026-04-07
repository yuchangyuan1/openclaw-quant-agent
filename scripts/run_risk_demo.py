#!/usr/bin/env python3
"""Local Risk MVP demo for portfolio checks and drawdown analysis."""

from __future__ import annotations

import argparse
import json

from services.risk import service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--holding", action="append", dest="holdings", default=[])
    parser.add_argument("--stock-code", action="append", dest="stock_codes", default=[])
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--lookback-days", type=int, default=90)
    parser.add_argument("--mode", choices=["check", "drawdown"], default="check")
    return parser.parse_args()


def parse_holdings(raw_holdings: list[str]) -> list[dict]:
    holdings = []
    for item in raw_holdings:
        code, weight = item.split(":", maxsplit=1)
        holdings.append({"code": code, "weight": float(weight)})
    return holdings


def main() -> None:
    args = parse_args()
    if args.mode == "drawdown":
        result = service.drawdown_analysis(args.stock_codes, args.lookback_days)
    else:
        holdings = parse_holdings(args.holdings)
        result = service.risk_check(holdings, args.benchmark, args.lookback_days, run_scenarios=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
