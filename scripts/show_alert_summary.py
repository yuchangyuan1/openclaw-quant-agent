#!/usr/bin/env python3
"""Inspect recent alert summary for report pipelines."""

from __future__ import annotations

import argparse
import json

from services.planner.report_pipeline import summarize_alerts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(summarize_alerts(limit=args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
