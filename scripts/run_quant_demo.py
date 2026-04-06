#!/usr/bin/env python3
"""Local Quant MVP demo for daily summary and factor analysis."""

from __future__ import annotations

import argparse
import json

from services.quant import service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-code", action="append", dest="stock_codes", required=True)
    parser.add_argument("--date", default=None)
    parser.add_argument("--factor", action="append", dest="factors", default=[])
    parser.add_argument("--mode", choices=["daily", "factor"], default="daily")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "factor":
        result = service.factor_values(args.stock_codes, args.factors, args.date)
    else:
        result = service.daily_summary(args.stock_codes, args.date, indicators=[])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
