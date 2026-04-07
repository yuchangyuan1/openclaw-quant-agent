from __future__ import annotations

import re
from functools import lru_cache

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
_TITLE_CASE_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
_CORPORATE_SUFFIXES = (
    "incorporated",
    "corporation",
    "company",
    "holdings",
    "inc",
    "corp",
    "ltd",
    "llc",
    "plc",
    "classa",
    "classc",
)

_TARGET_STOCKS = [
    {
        "code": "AAPL",
        "name": "Apple",
        "industry": "Consumer Electronics",
        "sector": "Technology",
        "cik": "0000320193",
        "aliases": ["Apple", "Apple Inc", "AAPL", "iPhone maker"],
    },
    {
        "code": "MSFT",
        "name": "Microsoft",
        "industry": "Software & Cloud",
        "sector": "Technology",
        "cik": "0000789019",
        "aliases": ["Microsoft", "Microsoft Corp", "MSFT", "Azure"],
    },
    {
        "code": "GOOGL",
        "name": "Alphabet",
        "industry": "Internet Platforms",
        "sector": "Communication Services",
        "cik": "0001652044",
        "aliases": ["Alphabet", "Google", "GOOGL", "Google parent"],
    },
    {
        "code": "AMZN",
        "name": "Amazon",
        "industry": "E-Commerce & Cloud",
        "sector": "Consumer Discretionary",
        "cik": "0001018724",
        "aliases": ["Amazon", "Amazon.com", "AMZN", "AWS"],
    },
    {
        "code": "META",
        "name": "Meta Platforms",
        "industry": "Digital Advertising",
        "sector": "Communication Services",
        "cik": "0001326801",
        "aliases": ["Meta", "Meta Platforms", "Facebook", "META"],
    },
    {
        "code": "NVDA",
        "name": "NVIDIA",
        "industry": "Semiconductors & AI Hardware",
        "sector": "Technology",
        "cik": "0001045810",
        "aliases": ["NVIDIA", "Nvidia", "NVDA", "GPU leader"],
    },
    {
        "code": "TSLA",
        "name": "Tesla",
        "industry": "EVs & Clean Energy",
        "sector": "Consumer Discretionary",
        "cik": "0001318605",
        "aliases": ["Tesla", "TSLA", "Tesla Inc"],
    },
]

_THEMES = [
    {
        "theme": "AI Infrastructure",
        "codes": ["NVDA", "MSFT", "GOOGL", "META"],
        "names": ["NVIDIA", "Microsoft", "Alphabet", "Meta Platforms"],
    },
    {
        "theme": "Consumer Platforms",
        "codes": ["AAPL", "AMZN", "GOOGL", "META"],
        "names": ["Apple", "Amazon", "Alphabet", "Meta Platforms"],
    },
    {
        "theme": "Cloud and Enterprise Software",
        "codes": ["MSFT", "AMZN", "GOOGL"],
        "names": ["Microsoft", "Amazon", "Alphabet"],
    },
    {
        "theme": "EV and Industrial AI",
        "codes": ["TSLA", "NVDA"],
        "names": ["Tesla", "NVIDIA"],
    },
]


def normalize_company_term(term: str) -> str:
    value = _NORMALIZE_RE.sub("", (term or "").lower())
    changed = True
    while changed and value:
        changed = False
        for suffix in _CORPORATE_SUFFIXES:
            if value.endswith(suffix) and len(value) > len(suffix) + 2:
                value = value[: -len(suffix)]
                changed = True
                break
    return value


def build_company_aliases(name: str, code: str | None = None, extra_aliases: list[str] | None = None) -> list[str]:
    aliases: list[str] = []
    for candidate in [name, normalize_company_term(name), code, *(extra_aliases or [])]:
        if not isinstance(candidate, str):
            continue
        normalized = candidate.strip()
        if normalized and normalized not in aliases:
            aliases.append(normalized)
    return aliases


@lru_cache(maxsize=1)
def load_target_stocks() -> dict[str, dict[str, object]]:
    mapping: dict[str, dict[str, object]] = {}
    for item in _TARGET_STOCKS:
        code = str(item["code"]).upper()
        mapping[code] = {
            "code": code,
            "name": item["name"],
            "industry": item["industry"],
            "sector": item["sector"],
            "cik": item["cik"],
            "aliases": build_company_aliases(item["name"], code, item.get("aliases", [])),
        }
    return mapping


@lru_cache(maxsize=1)
def load_theme_pool() -> list[dict[str, object]]:
    return [dict(item) for item in _THEMES]


def extract_company_terms(text: str) -> list[str]:
    if not text:
        return []

    haystack = text
    lowered = haystack.lower()
    matched: list[str] = []
    stocks = load_target_stocks()

    for ticker in _TICKER_RE.findall(haystack.upper()):
        if ticker in stocks and str(stocks[ticker]["name"]) not in matched:
            matched.append(str(stocks[ticker]["name"]))

    for item in stocks.values():
        aliases = item.get("aliases", [])
        for alias in aliases:
            alias_lower = alias.lower()
            if alias.isupper():
                if re.search(rf"\b{re.escape(alias)}\b", haystack.upper()) and str(item["name"]) not in matched:
                    matched.append(str(item["name"]))
                    break
            elif alias_lower and alias_lower in lowered and str(item["name"]) not in matched:
                matched.append(str(item["name"]))
                break

    if matched:
        return matched

    title_case_matches = _TITLE_CASE_RE.findall(haystack)
    if title_case_matches:
        phrase = title_case_matches[0].strip()
        if phrase:
            matched.append(phrase)
            shortened = phrase.split()[0]
            if shortened and shortened not in matched:
                matched.append(shortened)
    return matched


def matches_company_terms(text: str, company_terms: list[str]) -> bool:
    if not company_terms:
        return True
    lowered = (text or "").lower()
    normalized_text = normalize_company_term(text or "")
    for term in company_terms:
        term_lower = term.lower()
        term_normalized = normalize_company_term(term)
        if term_lower and term_lower in lowered:
            return True
        if term_normalized and term_normalized in normalized_text:
            return True
    return False


def match_company_code(text: str) -> str | None:
    if not text:
        return None
    haystack = text
    lowered = haystack.lower()
    for code, item in load_target_stocks().items():
        if re.search(rf"\b{re.escape(code)}\b", haystack.upper()):
            return code
        for alias in item.get("aliases", []):
            alias_lower = alias.lower()
            if alias.isupper() and re.search(rf"\b{re.escape(alias)}\b", haystack.upper()):
                return code
            if alias_lower and alias_lower in lowered:
                return code
    return None


def extract_stock_matches(text: str) -> list[dict[str, str]]:
    matched: list[dict[str, str]] = []
    lowered = (text or "").lower()
    for code, item in load_target_stocks().items():
        aliases = item.get("aliases", [])
        hit = re.search(rf"\b{re.escape(code)}\b", (text or "").upper()) is not None
        if not hit:
            hit = any(alias.lower() in lowered for alias in aliases if not alias.isupper())
        if not hit:
            hit = any(
                re.search(rf"\b{re.escape(alias)}\b", (text or "").upper()) is not None
                for alias in aliases
                if alias.isupper()
            )
        if hit:
            matched.append({"code": code, "name": str(item["name"])})
    return matched


def extract_theme_matches(text: str) -> list[str]:
    haystack = (text or "").lower()
    matched_codes = {item["code"] for item in extract_stock_matches(text)}
    matched: list[str] = []
    for theme in load_theme_pool():
        theme_name = str(theme["theme"])
        if theme_name.lower() in haystack:
            matched.append(theme_name)
            continue
        theme_hits = sum(1 for code in theme.get("codes", []) if code in matched_codes)
        if theme_hits >= 2:
            matched.append(theme_name)
    return matched


def build_research_metadata(text: str, explicit_code: str | None = None) -> dict[str, object]:
    stock_matches = extract_stock_matches(text)
    matched_codes = [item["code"] for item in stock_matches]
    explicit = explicit_code.upper() if explicit_code else None
    if explicit and explicit not in matched_codes:
        stock_item = load_target_stocks().get(explicit)
        if stock_item:
            stock_matches.insert(0, {"code": explicit, "name": str(stock_item["name"])})
            matched_codes.insert(0, explicit)

    return {
        "primary_company_code": explicit or (matched_codes[0] if matched_codes else None),
        "matched_stocks": stock_matches,
        "matched_themes": extract_theme_matches(text),
        "company_terms": extract_company_terms(text),
    }
