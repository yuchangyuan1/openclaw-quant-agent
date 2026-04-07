"""
Market-data fetcher for the U.S. equity version of the project.

This module uses yfinance as the live source for daily OHLCV data.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import config


def _parse_yyyymmdd(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.columns, pd.MultiIndex):
        return df
    flattened = []
    for column in df.columns:
        labels = [str(item) for item in column if item]
        flattened.append(labels[0] if labels else "")
    df.columns = flattened
    return df


def fetch_daily_hist(
    code: str,
    start: str,
    end: str | None = None,
    adjust: str = "auto",
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is required for live U.S. market data fetches") from exc

    ticker = code.upper()
    start_date = _parse_yyyymmdd(start)
    end_date = _parse_yyyymmdd(end) or date.today().isoformat()
    end_inclusive = (datetime.fromisoformat(end_date) + timedelta(days=1)).date().isoformat()
    auto_adjust = adjust not in {"", "raw", "none"}

    df = yf.download(
        ticker,
        start=start_date,
        end=end_inclusive,
        interval="1d",
        auto_adjust=auto_adjust,
        progress=False,
        actions=False,
        threads=False,
    )
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume"])

    df = _flatten_columns(df.reset_index())
    rename_map = {
        "Date": "date",
        "Open": "open",
        "Close": "close",
        "High": "high",
        "Low": "low",
        "Volume": "volume",
        "Adj Close": "adj_close",
    }
    normalized = df.rename(columns=rename_map)
    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for column in ["open", "close", "high", "low", "volume"]:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    columns = [column for column in ["date", "open", "close", "high", "low", "volume"] if column in normalized.columns]
    return normalized[columns].dropna(subset=["date", "close"]).reset_index(drop=True)


def save_to_parquet(df: pd.DataFrame, code: str, data_dir: str | None = None) -> Path:
    dir_path = Path(data_dir or config.MARKET_DATA_DIR)
    dir_path.mkdir(parents=True, exist_ok=True)
    out_path = dir_path / f"{code.upper()}_daily.parquet"
    df.to_parquet(out_path, index=False)
    return out_path


def fetch_all_targets(
    codes: list[str],
    start: str,
    end: str | None = None,
    delay: float = config.MARKET_DATA_FETCH_DELAY,
) -> dict[str, pd.DataFrame]:
    results: dict[str, pd.DataFrame] = {}
    for index, code in enumerate(codes):
        if index > 0:
            time.sleep(delay)
        df = fetch_daily_hist(code, start, end)
        results[code.upper()] = df
    return results


def get_latest_close(code: str) -> float | None:
    parquet_path = Path(config.MARKET_DATA_DIR) / f"{code.upper()}_daily.parquet"
    if not parquet_path.exists():
        return None
    df = pd.read_parquet(parquet_path)
    if df.empty or "close" not in df.columns:
        return None
    return float(df["close"].iloc[-1])
