from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from services.common.paths import resolve_project_path
from services.common.stocks import load_target_stocks

from . import config
from .market_fetcher import get_latest_close


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
    if cached is None and not fetch_if_missing:
        return None
    if cached is not None and not force_refresh and not fetch_if_missing:
        return cached

    try:
        snapshot = fetch_fundamental_snapshot(code)
    except Exception:
        return cached

    if snapshot is None:
        return cached
    _save_snapshot(snapshot)
    return snapshot


def fetch_fundamental_snapshot(code: str) -> FundamentalSnapshot | None:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is required for live U.S. fundamental fetches") from exc

    ticker = code.upper()
    stock_item = load_target_stocks().get(ticker, {})
    info = yf.Ticker(ticker).info or {}
    if not info:
        return None

    current_price = _coerce_number(
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or info.get("previousClose")
        or get_latest_close(ticker)
    )
    market_cap = _coerce_number(info.get("marketCap"))
    shares_outstanding = _coerce_number(info.get("sharesOutstanding"))
    float_shares = _coerce_number(info.get("floatShares")) or shares_outstanding
    float_market_cap = (current_price * float_shares) if current_price and float_shares else market_cap

    balance_sheet = _read_statement(getattr(yf.Ticker(ticker), "balance_sheet", None))
    cashflow = _read_statement(getattr(yf.Ticker(ticker), "cashflow", None))
    data_date = _normalize_date(
        info.get("mostRecentQuarter")
        or _statement_date(balance_sheet)
        or _statement_date(cashflow)
    )

    total_assets = _extract_statement_value(balance_sheet, ["Total Assets", "TotalAssets"])
    current_assets = _extract_statement_value(balance_sheet, ["Current Assets", "CurrentAssets"])
    current_liabilities = _extract_statement_value(balance_sheet, ["Current Liabilities", "CurrentLiabilities"])
    cash_and_equivalents = _extract_statement_value(
        balance_sheet,
        ["Cash And Cash Equivalents", "CashAndCashEquivalents", "Cash"],
    )
    receivables = _extract_statement_value(balance_sheet, ["Receivables", "Accounts Receivable"])
    short_term_investments = _extract_statement_value(
        balance_sheet,
        ["Other Short Term Investments", "ShortTermInvestments"],
    )
    total_debt = _coerce_number(info.get("totalDebt")) or _extract_statement_value(balance_sheet, ["Total Debt", "TotalDebt"])
    operating_cash_flow = _extract_statement_value(
        cashflow,
        ["Operating Cash Flow", "OperatingCashFlow", "Total Cash From Operating Activities"],
    )

    roe = _normalize_ratio(info.get("returnOnEquity"))
    gross_margin = _normalize_ratio(info.get("grossMargins"))
    net_margin = _normalize_ratio(info.get("profitMargins"))
    revenue_growth = _normalize_ratio(info.get("revenueGrowth"))
    net_profit_growth = _normalize_ratio(info.get("earningsGrowth"))
    debt_to_asset = _safe_percent(total_debt, total_assets)
    current_ratio = _safe_ratio(current_assets, current_liabilities)
    quick_assets = None
    if any(value is not None for value in [cash_and_equivalents, receivables, short_term_investments]):
        quick_assets = (cash_and_equivalents or 0.0) + (receivables or 0.0) + (short_term_investments or 0.0)
    quick_ratio = _safe_ratio(quick_assets, current_liabilities)
    operating_cashflow_per_share = _safe_ratio(operating_cash_flow, shares_outstanding)

    return FundamentalSnapshot(
        code=ticker,
        name=str(stock_item.get("name") or info.get("shortName") or info.get("longName") or ticker),
        industry=str(stock_item.get("industry") or info.get("industry") or "").strip() or None,
        report_period=data_date,
        data_date=data_date,
        fetched_at=datetime.now().isoformat(timespec="seconds"),
        close_price=current_price,
        market_cap=market_cap,
        float_market_cap=float_market_cap,
        pe_ttm=_coerce_number(info.get("trailingPE")),
        pb=_coerce_number(info.get("priceToBook")),
        eps_ttm=_coerce_number(info.get("trailingEps")),
        eps_latest=_coerce_number(info.get("currentEps") or info.get("trailingEps")),
        book_value_per_share=_coerce_number(info.get("bookValue")),
        operating_cashflow_per_share=operating_cashflow_per_share,
        roe=roe,
        gross_margin=gross_margin,
        net_margin=net_margin,
        revenue_growth=revenue_growth,
        net_profit_growth=net_profit_growth,
        debt_to_asset=debt_to_asset,
        current_ratio=current_ratio,
        quick_ratio=quick_ratio,
        source="yfinance_fundamental_snapshot",
        valuation_method="yfinance_info_and_statement_snapshot",
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
        for peer_code in missing_codes:
            snapshot = load_fundamental_snapshot(peer_code, fetch_if_missing=True)
            if snapshot is not None:
                snapshots.append(snapshot)
    return snapshots


def _load_cached_snapshot(code: str) -> FundamentalSnapshot | None:
    path = financial_data_dir() / f"{code.upper()}.json"
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
    path = root / f"{snapshot.code.upper()}.json"
    path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _is_stale(snapshot: FundamentalSnapshot) -> bool:
    try:
        fetched_at = datetime.fromisoformat(snapshot.fetched_at)
    except ValueError:
        return True
    return fetched_at < datetime.now() - timedelta(hours=config.FUNDAMENTAL_CACHE_HOURS)


def _read_statement(statement: Any) -> pd.DataFrame:
    if isinstance(statement, pd.DataFrame):
        return statement
    return pd.DataFrame()


def _statement_date(statement: pd.DataFrame) -> str | None:
    if statement.empty:
        return None
    latest_column = next(iter(statement.columns), None)
    return _normalize_date(latest_column)


def _extract_statement_value(statement: pd.DataFrame, candidates: list[str]) -> float | None:
    if statement.empty:
        return None
    for candidate in candidates:
        if candidate in statement.index:
            series = statement.loc[candidate]
            if isinstance(series, pd.Series):
                return _coerce_number(series.iloc[0])
            return _coerce_number(series)
    return None


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, pd.Timestamp):
            return value.date().isoformat()
        return pd.Timestamp(value).date().isoformat()
    except Exception:
        text = str(value).strip()
        return text[:10] if len(text) >= 10 else None


def _normalize_ratio(value: Any) -> float | None:
    numeric = _coerce_number(value)
    if numeric is None:
        return None
    if -1.0 <= numeric <= 1.0:
        numeric *= 100
    return round(numeric, 4)


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None
    return round(float(numerator) / float(denominator), 4)


def _safe_percent(numerator: float | None, denominator: float | None) -> float | None:
    ratio = _safe_ratio(numerator, denominator)
    return round(ratio * 100, 4) if ratio is not None else None


def _coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    mid = len(values) // 2
    if len(values) % 2 == 1:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def _relative_label(stock_value: float, industry_avg: float, lower_is_better: bool) -> str:
    if abs(stock_value - industry_avg) <= max(abs(industry_avg) * 0.05, 0.1):
        return "in_line_with_industry"
    if lower_is_better:
        return "better_than_industry" if stock_value < industry_avg else "worse_than_industry"
    return "better_than_industry" if stock_value > industry_avg else "worse_than_industry"
