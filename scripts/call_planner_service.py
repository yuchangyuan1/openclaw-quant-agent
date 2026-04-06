#!/usr/bin/env python3
"""Call the local planner HTTP service and print a compact JSON response."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("message", help="Incoming user message")
    parser.add_argument("--base-url", default="http://localhost:8005", help="Planner service base URL")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds")
    parser.add_argument("--no-refresh-index", action="store_true", help="Disable index refresh before query")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.dumps(
        {
            "message": args.message,
            "refresh_index": not args.no_refresh_index,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        url=args.base_url.rstrip("/") + "/api/v1/planner/query",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(
            json.dumps(
                {
                    "success": False,
                    "error": f"planner service returned HTTP {exc.code}",
                    "body": body,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    except urllib.error.URLError as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": f"planner service unavailable: {exc.reason}",
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "planner service returned invalid JSON",
                    "body": raw_body,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
