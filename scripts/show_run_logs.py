#!/usr/bin/env python3
"""Inspect recent report pipeline run logs."""

from __future__ import annotations

import argparse
import json

from services.planner.report_pipeline import list_recent_runs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--job-type", default=None)
    parser.add_argument("--status", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    items = list_recent_runs(limit=args.limit, job_type=args.job_type, status=args.status)
    print(json.dumps({"items": items}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
