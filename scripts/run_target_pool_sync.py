"""Trigger target-pool incremental ingestion via the local ingestion service."""

from __future__ import annotations

import argparse
import json

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run target-pool incremental ingestion.")
    parser.add_argument("--base-url", default="http://localhost:8001", help="Ingestion service base URL")
    parser.add_argument("--source", default="all", help="Source group: all | all_news | all_announcements")
    parser.add_argument("--date", default=None, help="Optional explicit date (YYYY-MM-DD)")
    parser.add_argument("--lookback-days", type=int, default=2, help="Incremental lookback days")
    parser.add_argument("--per-stock-limit", type=int, default=4, help="Per-stock fetch cap")
    parser.add_argument("--task-name", default="target_pool_incremental_sync", help="Persistent task name")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {
        "source": args.source,
        "date": args.date,
        "lookback_days": args.lookback_days,
        "per_stock_limit": args.per_stock_limit,
        "task_name": args.task_name,
    }
    with httpx.Client(timeout=args.timeout) as client:
        response = client.post(f"{args.base_url.rstrip('/')}/api/v1/ingest/target-pool/sync", json=payload)
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
