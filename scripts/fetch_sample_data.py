#!/usr/bin/env python3
"""
Fetch sample U.S. market data for the Magnificent 7 plus SPY.

This script is intended for local bootstrap and smoke-test preparation.
"""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.common.stocks import load_target_stocks  # noqa: E402
from services.quant.market_fetcher import fetch_daily_hist, save_to_parquet  # noqa: E402

OUTPUT_DIR = PROJECT_ROOT / "data" / "market"
END_DATE = date.today()
START_DATE = END_DATE - timedelta(days=365)
BENCHMARKS = [("SPY", "SPDR S&P 500 ETF Trust", "Benchmark")]


def analyze(df, code: str, name: str) -> dict:
    if df is None or df.empty:
        return {"code": code, "name": name, "ok": False, "rows": 0}
    return {
        "code": code,
        "name": name,
        "ok": True,
        "rows": len(df),
        "date_range": f"{df['date'].min()} ~ {df['date'].max()}",
        "completeness": f"{min(len(df) / 250, 1.0):.1%}",
    }


def main() -> int:
    print("=" * 60)
    print("  OpenClaw U.S. Market Sample Data Fetch")
    print(f"  Range: {START_DATE.isoformat()} ~ {END_DATE.isoformat()}")
    print("=" * 60)

    targets = [(code, item["name"], item["industry"]) for code, item in load_target_stocks().items()]
    targets.extend(BENCHMARKS)

    results = []
    for code, name, _industry in targets:
        print(f"\n  Fetching {code} ({name})")
        try:
            df = fetch_daily_hist(
                code=code,
                start=START_DATE.strftime("%Y%m%d"),
                end=END_DATE.strftime("%Y%m%d"),
                adjust="auto",
            )
        except Exception as exc:
            print(f"  [ERROR] {code}: {exc}", file=sys.stderr)
            df = None

        if df is not None and not df.empty:
            path = save_to_parquet(df, code, str(OUTPUT_DIR))
            info = analyze(df, code, name)
            info["file"] = str(path)
            results.append(info)
            print(f"  [PASS] {code}: {info['rows']} rows | {info['date_range']} | completeness {info['completeness']}")
        else:
            results.append({"code": code, "name": name, "ok": False, "rows": 0})
            print(f"  [FAIL] {code}: no data returned")
        time.sleep(1)

    passed = [item for item in results if item.get("ok")]
    failed = [item for item in results if not item.get("ok")]

    print("\n" + "=" * 60)
    print(f"  Passed: {len(passed)} / {len(results)}")
    if failed:
        for item in failed:
            print(f"  Failed: {item['code']} {item['name']}")
        return 1
    print(f"  Output directory: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
