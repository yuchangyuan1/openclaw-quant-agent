from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from services.common.paths import resolve_project_path
from services.common.stocks import load_target_stocks

from . import config
from .akshare_fetcher import get_latest_close

_FALSE_LIKE = {"", "--", "nan", "none", "null", "false", "False", "不适用"}
_UNIT_MULTIPLIERS = {
    "万亿": 1_000_000_000_000,
    "亿": 100_000_000,
    "万": 10_000,
}


@dataclass(slots=True)
class FundamentalSnapshot:
    code: str
    name: str
    industry: str | None
    report_period: str | None
    data_date: str | None
    fetched_at: str
    close_price: float | None = None
    market_cap: float | None = None
    float_market_cap: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    eps_ttm: float | None = None
    eps_latest: float | None = None
    book_value_per_share: float | None = None
    operating_cashflow_per_share: float | None = None
    roe: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    revenue_growth: float | None = None
    net_profit_growth: float | None = None
    debt_to_asset: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    source: str = "cache"
    valuation_method: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FundamentalSnapshot:
        return cls(**payload)


def financial_data_dir() -> Path:
    return resolve_project_path(config.FUNDAMENTAL_DATA_DIR, "./data/financials")


def load_fundamental_snapshot(
    code: str,
    *,
    fetch_if_missing: bool = True,
    force_refresh: bool = False,
) -> FundamentalSnapshot | None:
    cached = _load_cached_snapshot(code)
    if cached and not force_refresh and not _is_stale(cached):
        return cached

    if not config.ENABLE_LIVE_FUNDAMENTAL_FETCH:
        return cached
    if not force_refresh and cached and not fetch_if_missing:
        return cached
    if cached is None and not fetch_if_missing:
        return None

    try:
        snapshot = fetch_fundamental_snapshot(code)
    except Exception:
        return cached

    if snapshot is None:
        return cached

    _save_snapshot(snapshot)
    return snapshot


def fetch_fundamental_snapshot(code: str) -> FundamentalSnapshot | None:
    import akshare as ak

    target_stocks = load_target_stocks()
    stock_item = target_stocks.get(code, {})

    info_map: dict[str, Any] = {}
    try:
        info_df = ak.stock_individual_info_em(symbol=code)
        info_map = _frame_to_item_map(info_df)
    except Exception:
        info_map = {}

    latest_row: dict[str, Any] = {}
    try:
        financial_df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
        latest_row = _latest_report_row(financial_df)
    except Exception:
        latest_row = {}
    if not latest_row:
        try:
            financial_df = ak.stock_financial_analysis_indicator_em(symbol=_with_exchange_suffix(code), indicator="按报告期")
            latest_row = _latest_report_row(financial_df)
        except Exception:
            latest_row = {}

    if not info_map and not latest_row:
        return None

    report_period = _clean_str(latest_row.get("报告期") or latest_row.get("REPORT_DATE"))
    close_price = _coerce_number(info_map.get("最新")) or get_latest_close(code)
    eps_latest = _coerce_number(latest_row.get("基本每股收益") or latest_row.get("EPSJB"))
    eps_ttm = _annualize_eps(eps_latest, report_period)
    book_value_per_share = _coerce_number(latest_row.get("每股净资产") or latest_row.get("BPS"))

    pe_ttm = round(close_price / eps_ttm, 4) if close_price and eps_ttm and eps_ttm > 0 else None
    pb = (
        round(close_price / book_value_per_share, 4)
        if close_price and book_value_per_share and book_value_per_share > 0
        else None
    )

    name = _clean_str(info_map.get("股票简称")) or str(stock_item.get("name") or code)
    industry = _clean_str(info_map.get("行业")) or str(stock_item.get("industry") or "") or None

    return FundamentalSnapshot(
        code=code,
        name=name,
        industry=industry,
        report_period=report_period,
        data_date=_normalize_report_period(report_period),
        fetched_at=datetime.now().isoformat(timespec="seconds"),
        close_price=close_price,
        market_cap=_coerce_number(info_map.get("总市值")),
        float_market_cap=_coerce_number(info_map.get("流通市值")),
        pe_ttm=pe_ttm,
        pb=pb,
        eps_ttm=eps_ttm,
        eps_latest=eps_latest,
        book_value_per_share=book_value_per_share,
        operating_cashflow_per_share=_coerce_number(latest_row.get("每股经营现金流") or latest_row.get("PER_NETCASH")),
        roe=_coerce_number(latest_row.get("净资产收益率") or latest_row.get("ROE_DILUTED")),
        gross_margin=_coerce_number(latest_row.get("销售毛利率") or latest_row.get("GROSS_PROFIT_RATIO")),
        net_margin=_coerce_number(latest_row.get("销售净利率") or latest_row.get("NET_PROFIT_RATIO")),
        revenue_growth=_coerce_number(latest_row.get("营业总收入同比增长率") or latest_row.get("TOTALOPERATEREVETZ")),
        net_profit_growth=_coerce_number(latest_row.get("净利润同比增长率") or latest_row.get("PARENTNETPROFITTZ")),
        debt_to_asset=_coerce_number(latest_row.get("资产负债率")),
        current_ratio=_coerce_number(latest_row.get("流动比率")),
        quick_ratio=_coerce_number(latest_row.get("速动比率")),
        source="akshare_financial_snapshot",
        valuation_method="derived_from_latest_price_and_financial_abstract",
    )


def build_industry_comparison(
    code: str,
    snapshot: FundamentalSnapshot | None,
    *,
    max_peers: int | None = None,
) -> dict[str, Any] | None:
    if snapshot is None or not snapshot.industry:
        return None

    peer_snapshots = load_industry_peer_snapshots(
        code,
        industry=snapshot.industry,
        fetch_missing=True,
        max_peers=max_peers or config.INDUSTRY_COMPARISON_MAX_PEERS,
    )
    peer_map = {item.code: item for item in peer_snapshots}
    peer_map[code] = snapshot
    peers = list(peer_map.values())
    if len(peers) <= 1:
        return {
            "industry": snapshot.industry,
            "peer_count": 1,
            "coverage_count": 1,
            "metrics": {},
        }

    metric_specs = {
        "pe_ttm": {"lower_is_better": True},
        "pb": {"lower_is_better": True},
        "roe": {"lower_is_better": False},
        "gross_margin": {"lower_is_better": False},
        "net_margin": {"lower_is_better": False},
        "revenue_growth": {"lower_is_better": False},
        "net_profit_growth": {"lower_is_better": False},
        "debt_to_asset": {"lower_is_better": True},
    }
    metrics: dict[str, Any] = {}
    for metric_name, spec in metric_specs.items():
        stock_value = getattr(snapshot, metric_name)
        peer_values = [getattr(item, metric_name) for item in peers if getattr(item, metric_name) is not None]
        if stock_value is None or not peer_values:
            continue
        sorted_values = sorted(float(item) for item in peer_values)
        avg_value = sum(sorted_values) / len(sorted_values)
        median_value = _median(sorted_values)
        percentile = sum(item <= float(stock_value) for item in sorted_values) / len(sorted_values)
        metrics[metric_name] = {
            "stock_value": round(float(stock_value), 4),
            "industry_avg": round(avg_value, 4),
            "industry_median": round(median_value, 4),
            "percentile": round(percentile, 4),
            "relative": _relative_label(float(stock_value), avg_value, spec["lower_is_better"]),
        }

    return {
        "industry": snapshot.industry,
        "peer_count": len(
            [item for item in load_target_stocks().values() if item.get("industry") == snapshot.industry]
        ),
        "coverage_count": len(peers),
        "metrics": metrics,
    }


def load_industry_peer_snapshots(
    code: str,
    *,
    industry: str | None = None,
    fetch_missing: bool = False,
    max_peers: int | None = None,
) -> list[FundamentalSnapshot]:
    target_stocks = load_target_stocks()
    resolved_industry = industry or str(target_stocks.get(code, {}).get("industry") or "") or None
    if not resolved_industry:
        return []

    peer_codes = [
        item_code
        for item_code, item in target_stocks.items()
        if item_code != code and item.get("industry") == resolved_industry
    ]
    peer_codes = peer_codes[: max_peers or len(peer_codes)]

    snapshots: list[FundamentalSnapshot] = []
    missing_codes: list[str] = []
    for peer_code in peer_codes:
        snapshot = load_fundamental_snapshot(peer_code, fetch_if_missing=False)
        if snapshot is None:
            missing_codes.append(peer_code)
        else:
            snapshots.append(snapshot)

    if fetch_missing and config.ENABLE_LIVE_FUNDAMENTAL_FETCH:
        for peer_code in missing_codes[: max_peers or len(missing_codes)]:
            snapshot = load_fundamental_snapshot(peer_code, fetch_if_missing=True)
            if snapshot is not None:
                snapshots.append(snapshot)
    return snapshots


def _load_cached_snapshot(code: str) -> FundamentalSnapshot | None:
    path = financial_data_dir() / f"{code}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return FundamentalSnapshot.from_dict(payload)


def _save_snapshot(snapshot: FundamentalSnapshot) -> None:
    root = financial_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{snapshot.code}.json"
    path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _is_stale(snapshot: FundamentalSnapshot) -> bool:
    try:
        fetched_at = datetime.fromisoformat(snapshot.fetched_at)
    except ValueError:
        return True
    return fetched_at < datetime.now() - timedelta(hours=config.FUNDAMENTAL_CACHE_HOURS)


def _frame_to_item_map(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {}
    item_column = next((column for column in ["item", "指标", "项目"] if column in df.columns), None)
    value_column = next((column for column in ["value", "值", "最新值"] if column in df.columns), None)
    if item_column is None or value_column is None:
        return {}
    return {
        _clean_str(row[item_column]): row[value_column]
        for _, row in df.iterrows()
        if _clean_str(row[item_column])
    }


def _latest_report_row(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty or "报告期" not in df.columns:
        return {}
    ranked = df.copy()
    ranked["_sort_key"] = ranked["报告期"].map(_normalize_report_period)
    ranked = ranked.dropna(subset=["_sort_key"]).sort_values("_sort_key")
    if ranked.empty:
        return {}
    latest = ranked.iloc[-1].drop(labels=["_sort_key"])
    return latest.to_dict()


def _annualize_eps(eps_latest: float | None, report_period: str | None) -> float | None:
    if eps_latest is None or eps_latest <= 0:
        return None
    return round(eps_latest * _report_period_factor(report_period), 4)


def _report_period_factor(report_period: str | None) -> float:
    normalized = _normalize_report_period(report_period)
    if normalized is None:
        return 1.0
    month_day = normalized[5:]
    if month_day == "03-31":
        return 4.0
    if month_day == "06-30":
        return 2.0
    if month_day == "09-30":
        return 4.0 / 3.0
    return 1.0


def _normalize_report_period(value: Any) -> str | None:
    text = _clean_str(value)
    if not text:
        return None
    if re.fullmatch(r"\d{4}", text):
        return f"{text}-12-31"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", text):
        return text.replace("/", "-")
    if re.fullmatch(r"\d{8}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return None


def _coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = _clean_str(value)
    if not text or text in _FALSE_LIKE:
        return None

    multiplier = 1.0
    for unit, unit_multiplier in _UNIT_MULTIPLIERS.items():
        if text.endswith(unit):
            multiplier = float(unit_multiplier)
            text = text[: -len(unit)]
            break

    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1]

    text = text.replace(",", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if is_percent else number * multiplier


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _relative_label(value: float, avg_value: float, lower_is_better: bool) -> str:
    if avg_value == 0:
        return "in_line"
    delta_ratio = (value - avg_value) / abs(avg_value)
    if abs(delta_ratio) <= 0.05:
        return "in_line"
    if lower_is_better:
        return "better_than_industry" if value < avg_value else "worse_than_industry"
    return "better_than_industry" if value > avg_value else "worse_than_industry"


def _with_exchange_suffix(code: str) -> str:
    if code.startswith(("5", "6", "9")):
        return f"{code}.SH"
    return f"{code}.SZ"
