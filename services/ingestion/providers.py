from __future__ import annotations

import os
from datetime import datetime

import httpx

from services.common.stocks import build_research_metadata, load_target_stocks
from services.common.text import normalize_text

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
MAX_DOCS_PER_SOURCE = 8


def fetch_documents(
    source: str,
    stock_codes: list[str],
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    per_stock_limit: int = 3,
) -> list[dict]:
    if source in {"sec_edgar", "filings", "all_news", "all_filings"}:
        return fetch_sec_edgar_filings(
            stock_codes,
            date_from=date_from,
            date_to=date_to,
            per_stock_limit=per_stock_limit,
        )
    return []


def fetch_sec_edgar_filings(
    stock_codes: list[str],
    *,
    date_from: str | None,
    date_to: str | None,
    per_stock_limit: int,
) -> list[dict]:
    stocks = load_target_stocks()
    tickers = [code.upper() for code in stock_codes if code.upper() in stocks] or list(stocks.keys())
    docs: list[dict] = []
    user_agent = os.getenv(
        "SEC_USER_AGENT",
        "openclaw-quant-agent/0.1 research-support contact@example.com",
    )

    with httpx.Client(
        timeout=httpx.Timeout(20.0, connect=8.0),
        follow_redirects=True,
        headers={
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        },
    ) as client:
        for ticker in tickers:
            stock = stocks[ticker]
            cik = str(stock.get("cik") or "").zfill(10)
            if not cik:
                continue
            try:
                payload = client.get(SEC_SUBMISSIONS_URL.format(cik=cik)).json()
            except Exception:
                continue

            recent = payload.get("filings", {}).get("recent", {})
            accession_numbers = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])
            forms = recent.get("form", [])
            primary_documents = recent.get("primaryDocument", [])
            primary_descriptions = recent.get("primaryDocDescription", [])
            report_dates = recent.get("reportDate", [])

            collected = 0
            for index, accession_number in enumerate(accession_numbers):
                filing_date = _safe_get(filing_dates, index)
                if not _date_in_range(filing_date, date_from, date_to):
                    continue

                form = _safe_get(forms, index) or "FILING"
                primary_document = _safe_get(primary_documents, index) or ""
                description = normalize_text(_safe_get(primary_descriptions, index) or form)
                report_date = _safe_get(report_dates, index)
                accession_digits = accession_number.replace("-", "") if accession_number else ""
                if not accession_digits or not primary_document:
                    continue

                filing_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_digits}/{primary_document}"
                )
                title = f"{ticker} {form} filing"
                if report_date:
                    title = f"{title} ({report_date})"

                content = normalize_text(
                    "\n".join(
                        [
                            f"Ticker: {ticker}",
                            f"Company: {stock['name']}",
                            f"Form: {form}",
                            f"Filing date: {filing_date or 'unknown'}",
                            f"Report date: {report_date or 'unknown'}",
                            f"Description: {description or form}",
                            f"SEC URL: {filing_url}",
                        ]
                    )
                )
                metadata = build_research_metadata(content, explicit_code=ticker)
                docs.append(
                    {
                        **_build_article(
                            source="sec_edgar",
                            doc_type="filing",
                            title=title,
                            url=filing_url,
                            published_at=filing_date,
                            content=content,
                            explicit_code=ticker,
                        ),
                        "metadata": metadata,
                    }
                )
                collected += 1
                if collected >= per_stock_limit:
                    break

    return docs[: MAX_DOCS_PER_SOURCE * max(len(tickers), 1)]


def _build_article(
    *,
    source: str,
    doc_type: str,
    title: str,
    url: str,
    published_at: str | None,
    content: str,
    explicit_code: str | None = None,
) -> dict:
    metadata = build_research_metadata(f"{title}\n{content}", explicit_code=explicit_code)
    return {
        "source": source,
        "doc_type": doc_type,
        "title": normalize_text(title),
        "url": url,
        "published_at": published_at,
        "company_code": metadata["primary_company_code"],
        "content": normalize_text(content),
        "metadata": metadata,
    }


def _safe_get(values: list, index: int):
    if index >= len(values):
        return None
    return values[index]


def _date_in_range(value: str | None, date_from: str | None, date_to: str | None) -> bool:
    if not value:
        return True
    try:
        current = datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return True
    if date_from:
        start = datetime.fromisoformat(date_from[:10]).date()
        if current < start:
            return False
    if date_to:
        end = datetime.fromisoformat(date_to[:10]).date()
        if current > end:
            return False
    return True
