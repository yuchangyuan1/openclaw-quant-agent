#!/usr/bin/env python3
"""Knowledge MVP demo: build Evidence Pack from local ingestion + RAG data."""

from __future__ import annotations

import argparse
import json

from services.rag.knowledge_pipeline import build_evidence_pack


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", help="Research question")
    parser.add_argument("--stock-code", action="append", default=[], dest="stock_codes")
    parser.add_argument("--doc-type", action="append", default=[], dest="doc_types")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-score", type=float, default=0.7)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_evidence_pack(
        question=args.question,
        stock_codes=args.stock_codes,
        doc_types=args.doc_types,
        days=args.days,
        top_k=args.top_k,
        min_score=args.min_score,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
