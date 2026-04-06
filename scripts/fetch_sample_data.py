#!/usr/bin/env python3
"""
验收 3：Akshare 行情数据拉取脚本

功能：
- 对 5 只代表性股票拉取近 1 年日行情数据
- 保存为 data/market/{code}_1y.parquet
- 打印数据行数、日期范围、缺失率统计
- 所有股票成功才以 0 退出，任意失败以 1 退出

用法：
    python scripts/fetch_sample_data.py
"""

import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 5 只代表性股票（覆盖 4 个板块）
TARGET_STOCKS = [
    ("600519", "贵州茅台", "食品饮料"),
    ("000001", "平安银行", "银行"),
    ("300750", "宁德时代", "电力设备"),
    ("601318", "中国平安", "非银金融"),
    ("300059", "东方财富", "非银金融"),
]

OUTPUT_DIR = PROJECT_ROOT / "data" / "market"
END_DATE = date.today()
START_DATE = END_DATE - timedelta(days=365)


def fetch_stock(code: str, name: str) -> pd.DataFrame | None:
    try:
        from services.quant.akshare_fetcher import fetch_daily_hist

        return fetch_daily_hist(
            code=code,
            start=START_DATE.strftime("%Y%m%d"),
            end=END_DATE.strftime("%Y%m%d"),
            adjust="qfq",
        )
    except Exception as e:
        print(f"  [ERROR] {code} ({name}): {e}", file=sys.stderr)
        return None


def save_parquet(df: pd.DataFrame, code: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{code}_1y.parquet"
    df.to_parquet(out_path, index=False)
    return out_path


def analyze(df: pd.DataFrame, code: str, name: str) -> dict:
    if df is None or df.empty:
        return {"code": code, "name": name, "ok": False, "rows": 0}

    # Akshare 返回的列名根据版本可能不同，做兼容处理
    date_col = None
    for col in ["日期", "date", "trade_date"]:
        if col in df.columns:
            date_col = col
            break

    info = {
        "code": code,
        "name": name,
        "ok": True,
        "rows": len(df),
        "date_range": f"{df[date_col].min()} ~ {df[date_col].max()}" if date_col else "N/A",
    }

    # 粗略估算完整度（近 1 年约 250 个交易日）
    expected = 250
    completeness = min(len(df) / expected, 1.0)
    info["completeness"] = f"{completeness:.1%}"
    info["pass"] = completeness >= 0.95

    return info


def main():
    print("=" * 60)
    print("  量化投研系统 — Akshare 行情数据验收")
    print(f"  区间：{START_DATE} ~ {END_DATE}")
    print("=" * 60)

    results = []
    for code, name, industry in TARGET_STOCKS:
        print(f"\n  正在拉取 {code} ({name}) …")
        df = fetch_stock(code, name)

        if df is not None and not df.empty:
            path = save_parquet(df, code)
            info = analyze(df, code, name)
            info["file"] = str(path)
            results.append(info)
            status = "[PASS]" if info.get("pass") else "[WARN]"
            print(f"  {status} {code} {name}: {info['rows']} 行, {info.get('date_range', 'N/A')}, "
                  f"完整度 {info.get('completeness', 'N/A')}")
        else:
            results.append({"code": code, "name": name, "ok": False, "rows": 0})
            print(f"  [FAIL] {code} {name}: 无数据")

        time.sleep(1)  # 避免 Akshare 限速

    # 汇总
    print()
    print("=" * 60)
    passed = [r for r in results if r.get("ok") and r.get("pass")]
    failed = [r for r in results if not r.get("ok") or not r.get("pass")]

    print(f"  通过：{len(passed)} / {len(results)}")
    if failed:
        for r in failed:
            print(f"  未通过：{r['code']} {r['name']}")
        print()
        print("  部分股票数据拉取失败，请检查 Akshare 连接和版本。")
        sys.exit(1)
    else:
        print(f"  全部 {len(passed)} 只股票数据拉取成功 [PASS]")
        print(f"  文件已保存至 {OUTPUT_DIR}/")
        sys.exit(0)


if __name__ == "__main__":
    main()
