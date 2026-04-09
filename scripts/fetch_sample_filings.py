#!/usr/bin/env python3
"""Fetch and index sample SEC EDGAR filings for local bootstrap and demos."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

from services.ingestion import providers
from services.ingestion.service import _persist_article
from services.rag.service import build_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch sample SEC EDGAR filings and build the local index.")
    parser.add_argument("--stock-code", action="append", dest="stock_codes", default=[])
    parser.add_argument("--days", type=int, default=30, help="How many days back to search for filings.")
    parser.add_argument("--per-stock-limit", type=int, default=3, help="Maximum filings to fetch per stock.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stock_codes = args.stock_codes or ["AAPL", "MSFT", "NVDA"]
    end = date.today()
    start = end - timedelta(days=args.days)

    articles = providers.fetch_documents(
        "sec_edgar",
        stock_codes,
        date_from=start.isoformat(),
        date_to=end.isoformat(),
        per_stock_limit=args.per_stock_limit,
    )

    inserted = 0
    for article in articles:
        if _persist_article(article):
            inserted += 1

    index_result = build_index([], False)
    print(
        json.dumps(
            {
                "stock_codes": stock_codes,
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
                "fetched_articles": len(articles),
                "inserted_articles": inserted,
                "index_result": index_result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
