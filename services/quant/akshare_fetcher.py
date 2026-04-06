"""
Akshare 行情数据获取模块（阶段 0 唯一真实实现）

主要函数：
- fetch_daily_hist(code, start, end) -> pd.DataFrame
- save_to_parquet(df, code, data_dir) -> Path
- fetch_all_targets(codes) -> dict[str, pd.DataFrame]
"""

import time
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from . import config


def with_exchange_prefix(code: str) -> str:
    """将 6 位股票代码转换为 Akshare 某些接口需要的带交易所前缀格式。"""
    if code.startswith(("5", "6", "9")):
        return f"sh{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


def filter_by_date(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """兼容中英文日期列，裁剪到请求区间。"""
    date_col = next((c for c in ["日期", "date", "trade_date"] if c in df.columns), None)
    if date_col is None or df.empty:
        return df

    normalized = df.copy()
    normalized[date_col] = pd.to_datetime(normalized[date_col], errors="coerce")
    start_dt = pd.to_datetime(start, format="%Y%m%d", errors="coerce")
    end_dt = pd.to_datetime(end, format="%Y%m%d", errors="coerce")
    normalized = normalized.loc[
        normalized[date_col].between(start_dt, end_dt, inclusive="both")
    ].copy()

    if pd.api.types.is_datetime64_any_dtype(normalized[date_col]):
        normalized[date_col] = normalized[date_col].dt.strftime("%Y-%m-%d")
    return normalized


def fetch_daily_hist(
    code: str,
    start: str,
    end: Optional[str] = None,
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    拉取单只股票日行情（前复权）。

    参数：
        code: 6 位股票代码，如 "600519"
        start: 开始日期，格式 "YYYYMMDD"
        end: 结束日期，格式 "YYYYMMDD"，默认当天
        adjust: 复权方式，qfq=前复权 | hfq=后复权 | "" =不复权

    返回：
        DataFrame，列：日期/开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/涨跌额/换手率
        若拉取失败，返回空 DataFrame。
    """
    import akshare as ak

    if end is None:
        end = date.today().strftime("%Y%m%d")

    sources = [
        ("eastmoney_hist", lambda: ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start,
            end_date=end,
            adjust=adjust,
        )),
        ("tencent_hist", lambda: ak.stock_zh_a_hist_tx(
            symbol=with_exchange_prefix(code),
            start_date=start,
            end_date=end,
            adjust=adjust,
        )),
        ("daily_fallback", lambda: ak.stock_zh_a_daily(
            symbol=with_exchange_prefix(code),
            start_date=start,
            end_date=end,
            adjust=adjust,
        )),
    ]

    for source_name, fetcher in sources:
        try:
            df = fetcher()
            if df is None or df.empty:
                continue
            if source_name == "daily_fallback":
                df = filter_by_date(df, start, end)
            print(f"[akshare] {code} fetched via {source_name}: {len(df)} rows")
            return df
        except Exception as e:
            print(f"[akshare] {source_name} failed for {code}: {e}")

    return pd.DataFrame()


def save_to_parquet(df: pd.DataFrame, code: str, data_dir: Optional[str] = None) -> Path:
    """
    将 DataFrame 保存为 Parquet 文件。

    返回：文件路径。
    """
    dir_path = Path(data_dir or config.MARKET_DATA_DIR)
    dir_path.mkdir(parents=True, exist_ok=True)
    out_path = dir_path / f"{code}_daily.parquet"
    df.to_parquet(out_path, index=False)
    return out_path


def fetch_all_targets(
    codes: list[str],
    start: str,
    end: Optional[str] = None,
    delay: float = config.AKSHARE_DELAY,
) -> dict[str, pd.DataFrame]:
    """
    批量拉取多只股票行情，带延迟防止限速。

    返回：{code: DataFrame}，失败的 code 对应空 DataFrame。
    """
    results = {}
    for i, code in enumerate(codes):
        if i > 0:
            time.sleep(delay)
        df = fetch_daily_hist(code, start, end)
        results[code] = df
        status = f"{len(df)} 行" if not df.empty else "失败"
        print(f"  [{i+1}/{len(codes)}] {code}: {status}")
    return results


def get_latest_close(code: str) -> Optional[float]:
    """从本地 Parquet 文件读取最新收盘价（避免重复 API 调用）。"""
    parquet_path = Path(config.MARKET_DATA_DIR) / f"{code}_daily.parquet"
    if not parquet_path.exists():
        return None
    df = pd.read_parquet(parquet_path)
    if df.empty:
        return None
    # 兼容不同列名
    close_col = next((c for c in ["收盘", "close", "close_price"] if c in df.columns), None)
    if close_col is None:
        return None
    return float(df[close_col].iloc[-1])
