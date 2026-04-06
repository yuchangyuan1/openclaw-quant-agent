#!/usr/bin/env python3
"""Local daily report MVP demo."""

from __future__ import annotations

import argparse
import json

from services.planner.report_pipeline import execute_daily_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", dest="report_date", default=None)
    parser.add_argument("--stock-code", action="append", dest="stock_codes", default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = execute_daily_report(report_date=args.report_date, stock_codes=args.stock_codes or None)
    print(
        json.dumps(
            {
                "report": result.report_payload,
                "critic": result.critic_payload,
                "evidence_count": len(result.evidence_payload.get("evidence_pack", [])),
                "quant_trade_date": result.quant_payload.get("trade_date"),
                "risk_level": result.risk_payload.get("risk_level"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
