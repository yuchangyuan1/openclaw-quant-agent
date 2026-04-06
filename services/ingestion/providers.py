from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from services.common.stocks import build_research_metadata, match_company_code
from services.common.text import normalize_text

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
EASTMONEY_LIST_URL = "https://finance.eastmoney.com/yaowen.html"
TENJQKA_LIST_URL = "https://news.10jqka.com.cn/yaowen/"
SINA_FINANCE_LIST_URL = "https://finance.sina.com.cn/roll/index.d.html"
EASTMONEY_NOTICE_LIST_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
EASTMONEY_NOTICE_CONTENT_URL = "https://np-cnotice-stock.eastmoney.com/api/content/ann"
MAX_DOCS_PER_SOURCE = 8
SKIP_PARAGRAPHS = ("手机查看财经快讯", "东方财富APP", "微信扫一扫")


def fetch_documents(
    source: str,
    stock_codes: list[str],
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    per_stock_limit: int = 3,
) -> list[dict]:
    if source == "eastmoney_news":
        return fetch_eastmoney_news(stock_codes, date_from=date_from, date_to=date_to)
    if source == "10jqka":
        return fetch_10jqka_news(stock_codes, date_from=date_from, date_to=date_to)
    if source == "sina":
        return fetch_sina_finance_news(stock_codes, date_from=date_from, date_to=date_to)
    if source == "announcement":
        return fetch_eastmoney_announcements(
            stock_codes,
            date_from=date_from,
            date_to=date_to,
            per_stock_limit=per_stock_limit,
        )
    if source in {"sse", "szse"}:
        return fetch_exchange_announcements(
            source,
            stock_codes,
            date_from=date_from,
            date_to=date_to,
            per_stock_limit=per_stock_limit,
        )
    return []


def fetch_eastmoney_news(stock_codes: list[str], *, date_from: str | None, date_to: str | None) -> list[dict]:
    docs: list[dict] = []
    with httpx.Client(
        timeout=httpx.Timeout(20.0, connect=8.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        list_html = client.get(EASTMONEY_LIST_URL).text
        article_urls = list(dict.fromkeys(re.findall(r"https://finance\.eastmoney\.com/a/\d+\.html", list_html)))
        for url in article_urls[: MAX_DOCS_PER_SOURCE * 3]:
            try:
                article = _fetch_eastmoney_article(client, url)
            except Exception:
                continue
            if _should_keep(article, stock_codes, date_from, date_to):
                docs.append(article)
            if len(docs) >= MAX_DOCS_PER_SOURCE:
                break
    return docs


def _fetch_eastmoney_article(client: httpx.Client, url: str) -> dict:
    html = client.get(url).text
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.select_one("h1"):
        title = normalize_text(soup.select_one("h1").get_text(" ", strip=True))
    if not title and soup.title:
        title = normalize_text(soup.title.get_text(" ", strip=True).split("_")[0])

    content_root = soup.select_one("#ContentBody")
    paragraphs = []
    if content_root:
        for paragraph in content_root.select("p"):
            text = normalize_text(paragraph.get_text(" ", strip=True))
            if not text or len(text) < 15:
                continue
            if any(marker in text for marker in SKIP_PARAGRAPHS):
                continue
            paragraphs.append(text)

    date_match = re.search(r"/a/(\d{8})", url)
    published_at = _date_from_match(date_match.group(1)) if date_match else None
    content = "\n".join(paragraphs)
    return _build_article(
        source="eastmoney",
        doc_type="news",
        title=title or url,
        url=url,
        published_at=published_at,
        content=content or title,
    )


def fetch_10jqka_news(stock_codes: list[str], *, date_from: str | None, date_to: str | None) -> list[dict]:
    docs: list[dict] = []
    headers = {"User-Agent": USER_AGENT, "Referer": "https://news.10jqka.com.cn/"}
    with httpx.Client(timeout=httpx.Timeout(20.0, connect=8.0), follow_redirects=True, headers=headers) as client:
        response = client.get(TENJQKA_LIST_URL)
        response.encoding = "gbk"
        soup = BeautifulSoup(response.text, "html.parser")

        for item in soup.select(".list-con li"):
            title_link = item.select_one("a.news-link")
            summary_link = item.select_one("a.arc-cont")
            if not title_link:
                continue

            url = title_link.get("href")
            title = normalize_text(title_link.get("title") or title_link.get_text(" ", strip=True))
            summary = normalize_text(summary_link.get_text(" ", strip=True) if summary_link else "")
            if not url or not title:
                continue

            try:
                content = _fetch_10jqka_article(client, url)
            except Exception:
                content = summary

            date_match = re.search(r"/(\d{8})/", url)
            published_at = _date_from_match(date_match.group(1)) if date_match else None
            article = _build_article(
                source="10jqka",
                doc_type="news",
                title=title,
                url=urljoin("https://news.10jqka.com.cn/", url),
                published_at=published_at,
                content=content or summary or title,
            )
            if _should_keep(article, stock_codes, date_from, date_to):
                docs.append(article)
            if len(docs) >= MAX_DOCS_PER_SOURCE:
                break
    return docs


def fetch_sina_finance_news(stock_codes: list[str], *, date_from: str | None, date_to: str | None) -> list[dict]:
    docs: list[dict] = []
    with httpx.Client(
        timeout=httpx.Timeout(20.0, connect=8.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Referer": "https://finance.sina.com.cn/"},
    ) as client:
        response = client.get(SINA_FINANCE_LIST_URL, params={"cid": "56592", "page": 1})
        response.encoding = response.encoding or "utf-8"
        article_urls = _extract_sina_article_urls(response.text)
        for url in article_urls[: MAX_DOCS_PER_SOURCE * 3]:
            try:
                article = _fetch_sina_article(client, url)
            except Exception:
                continue
            if _should_keep(article, stock_codes, date_from, date_to):
                docs.append(article)
            if len(docs) >= MAX_DOCS_PER_SOURCE:
                break
    return docs


def _fetch_sina_article(client: httpx.Client, url: str) -> dict:
    response = client.get(url)
    response.encoding = response.encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    title = ""
    if soup.select_one("h1.main-title"):
        title = normalize_text(soup.select_one("h1.main-title").get_text(" ", strip=True))
    elif soup.select_one("h1"):
        title = normalize_text(soup.select_one("h1").get_text(" ", strip=True))
    elif soup.title:
        title = normalize_text(soup.title.get_text(" ", strip=True))

    published_at = None
    for selector in ["span.date", "span#pub_date", ".date-source span.date"]:
        node = soup.select_one(selector)
        if node:
            published_at = _extract_iso_date(node.get_text(" ", strip=True))
            if published_at:
                break
    if not published_at:
        date_match = re.search(r"/(\d{4}-\d{2}-\d{2})/", url)
        if date_match:
            published_at = date_match.group(1)

    paragraphs = []
    for selector in ["#artibody p", ".article p", ".main-content p"]:
        nodes = soup.select(selector)
        if nodes:
            paragraphs = [
                normalize_text(paragraph.get_text(" ", strip=True))
                for paragraph in nodes
                if normalize_text(paragraph.get_text(" ", strip=True))
            ]
            if paragraphs:
                break
    content = "\n".join(paragraphs)
    return _build_article(
        source="sina",
        doc_type="news",
        title=title or url,
        url=url,
        published_at=published_at,
        content=content or title,
    )


def fetch_eastmoney_announcements(
    stock_codes: list[str],
    *,
    date_from: str | None,
    date_to: str | None,
    per_stock_limit: int,
) -> list[dict]:
    docs: list[dict] = []
    seen_codes: set[str] = set()
    query_params = _eastmoney_announcement_queries(stock_codes, per_stock_limit, date_from, date_to)

    with httpx.Client(
        timeout=httpx.Timeout(20.0, connect=8.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for params in query_params:
            try:
                payload = client.get(EASTMONEY_NOTICE_LIST_URL, params=params).json()
            except Exception:
                continue
            items = payload.get("data", {}).get("list", [])
            for item in items:
                art_code = item.get("art_code")
                if not art_code or art_code in seen_codes:
                    continue
                codes = item.get("codes") or []
                code_info = codes[0] if codes else {}
                stock_code = code_info.get("stock_code")
                notice_date = _extract_iso_date(item.get("notice_date"))
                if stock_codes and stock_code not in stock_codes:
                    continue
                if not _date_in_range(notice_date, date_from, date_to):
                    continue
                try:
                    detail = client.get(
                        EASTMONEY_NOTICE_CONTENT_URL,
                        params={
                            "art_code": art_code,
                            "client_source": "web",
                            "page_index": 1,
                        },
                    ).json()
                except Exception:
                    continue
                data = detail.get("data", {})
                content = normalize_text(data.get("notice_content", ""))
                if not content:
                    continue
                title = normalize_text(item.get("title") or data.get("notice_title") or "")
                company_code = stock_code or match_company_code(f"{title}\n{content}")
                docs.append(
                    {
                        **_build_article(
                            source="eastmoney",
                            doc_type="announcement",
                            title=title,
                            url=f"https://data.eastmoney.com/notices/detail/{stock_code}/{art_code}.html",
                            published_at=notice_date or _extract_iso_date(data.get("notice_date")),
                            content=content,
                            explicit_code=company_code,
                        ),
                        "pdf_url": data.get("attach_url_web"),
                    }
                )
                seen_codes.add(art_code)
            if stock_codes and len(_limit_articles_for_stocks(docs, stock_codes, per_stock_limit)) >= len(stock_codes):
                continue
    return _limit_articles_for_stocks(docs, stock_codes, per_stock_limit)


def fetch_exchange_announcements(
    exchange: str,
    stock_codes: list[str],
    *,
    date_from: str | None,
    date_to: str | None,
    per_stock_limit: int,
) -> list[dict]:
    try:
        import akshare as ak
    except Exception:
        return []

    docs: list[dict] = []
    try:
        data_frame = _call_akshare_notice_report(ak, exchange, date_to or datetime.now().date().isoformat())
    except Exception:
        return []
    if data_frame is None or data_frame.empty:
        return []

    for row in data_frame.to_dict("records"):
        stock_code = _find_first(row, ["代码", "证券代码", "stock_code", "symbol"])
        title = normalize_text(_find_first(row, ["公告标题", "标题", "name", "公告名称"]) or "")
        published_at = _extract_iso_date(
            _find_first(row, ["公告日期", "发布时间", "日期", "notice_date", "time"])
        )
        content = normalize_text(_find_first(row, ["公告摘要", "摘要", "内容", "公告内容"]) or title)
        url = _find_first(row, ["公告链接", "链接", "url", "网址"])
        if not title:
            continue
        if stock_codes and stock_code not in stock_codes:
            continue
        if not _date_in_range(published_at, date_from, date_to):
            continue
        docs.append(
            _build_article(
                source=exchange,
                doc_type="announcement",
                title=title,
                url=url,
                published_at=published_at,
                content=content or title,
                explicit_code=stock_code,
            )
        )
    return _limit_articles_for_stocks(docs, stock_codes, per_stock_limit)


def _fetch_10jqka_article(client: httpx.Client, url: str) -> str:
    response = client.get(url)
    response.encoding = "gbk"
    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = [
        normalize_text(paragraph.get_text(" ", strip=True))
        for paragraph in soup.select("div.article-content p")
        if normalize_text(paragraph.get_text(" ", strip=True))
    ]
    return "\n".join(paragraphs)


def _build_article(
    *,
    source: str,
    doc_type: str,
    title: str,
    url: str | None,
    published_at: str | None,
    content: str,
    explicit_code: str | None = None,
) -> dict:
    company_code = explicit_code or match_company_code(f"{title}\n{content}")
    metadata = build_research_metadata(f"{title}\n{content}", explicit_code=company_code)
    return {
        "source": source,
        "doc_type": doc_type,
        "title": title,
        "url": url,
        "published_at": published_at,
        "company_code": company_code,
        "content": content,
        "metadata": metadata,
    }


def _extract_sina_article_urls(html: str) -> list[str]:
    urls = re.findall(r"https://finance\.sina\.com\.cn/[^\s\"']+", html)
    cleaned: list[str] = []
    for url in urls:
        candidate = url.rstrip('",\'<>')
        if "/roll/" in candidate:
            continue
        if ".shtml" not in candidate:
            continue
        if candidate not in cleaned:
            cleaned.append(candidate)
    return cleaned


def _eastmoney_announcement_queries(
    stock_codes: list[str],
    per_stock_limit: int,
    date_from: str | None,
    date_to: str | None,
) -> list[dict]:
    base = {
        "ann_type": "A",
        "client_source": "web",
        "page_index": 1,
        "page_size": max(MAX_DOCS_PER_SOURCE * 2, 20),
        "sr": -1,
        "st": "display_time",
    }
    if date_from:
        base["begin_time"] = date_from
    if date_to:
        base["end_time"] = date_to

    queries = [base]
    for stock_code in stock_codes:
        targeted = dict(base)
        targeted["page_size"] = max(per_stock_limit * 3, 10)
        targeted["stock_list"] = stock_code
        queries.append(targeted)
    return queries


def _call_akshare_notice_report(ak_module, exchange: str, report_date: str):
    market_label = {"sse": "沪市", "szse": "深市"}.get(exchange, exchange)
    compact_date = report_date.replace("-", "")
    candidate_kwargs = [
        {"symbol": market_label, "date": compact_date},
        {"symbol": market_label, "trade_date": compact_date},
        {"stock": market_label, "date": compact_date},
        {"symbol": market_label},
    ]
    for kwargs in candidate_kwargs:
        try:
            data_frame = ak_module.stock_notice_report(**kwargs)
        except TypeError:
            continue
        if data_frame is not None and not data_frame.empty:
            return data_frame
    return ak_module.stock_notice_report(symbol=market_label)


def _find_first(payload: dict, keys: list[str]):
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "nan":
            return text
    return None


def _extract_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(\d{4}[-/.]\d{2}[-/.]\d{2})", str(value))
    if match:
        return match.group(1).replace("/", "-").replace(".", "-")
    compact_match = re.search(r"(\d{8})", str(value))
    if compact_match:
        return _date_from_match(compact_match.group(1))
    return None


def _date_from_match(value: str) -> str | None:
    try:
        return datetime.strptime(value, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def _date_in_range(published_at: str | None, date_from: str | None, date_to: str | None) -> bool:
    if not published_at:
        return True
    if date_from and published_at < date_from:
        return False
    if date_to and published_at > date_to:
        return False
    return True


def _should_keep(article: dict, stock_codes: list[str], date_from: str | None, date_to: str | None) -> bool:
    if not _date_in_range(article.get("published_at"), date_from, date_to):
        return False
    if stock_codes:
        return article.get("company_code") in stock_codes
    return True


def _limit_articles_for_stocks(docs: list[dict], stock_codes: list[str], per_stock_limit: int) -> list[dict]:
    if not stock_codes or per_stock_limit <= 0:
        return docs[: MAX_DOCS_PER_SOURCE * max(len(stock_codes), 1)]
    counts: dict[str, int] = defaultdict(int)
    limited: list[dict] = []
    for doc in docs:
        code = doc.get("company_code")
        if code not in stock_codes:
            continue
        if counts[code] >= per_stock_limit:
            continue
        counts[code] += 1
        limited.append(doc)
    return limited
