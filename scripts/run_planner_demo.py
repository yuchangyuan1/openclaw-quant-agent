#!/usr/bin/env python3
"""Local Planner MVP demo for DOC_QA and report routing."""

from __future__ import annotations

import argparse
import json

from services.planner.pipeline import execute_message


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("message", help="Incoming user message")
    parser.add_argument("--no-refresh-index", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = execute_message(args.message, refresh_index=not args.no_refresh_index)
    print(
        json.dumps(
            {
                "intent": result.intent,
                "latest_data_date": result.latest_data_date,
                "sources": result.sources,
                "critic_status": result.critic_status,
                "evidence_count": result.evidence_count,
                "company_terms": result.company_terms,
                "matched_companies": result.matched_companies,
                "matched_company_names": result.matched_company_names,
                "matched_themes": result.matched_themes,
                "reply_markdown": result.reply_markdown,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
