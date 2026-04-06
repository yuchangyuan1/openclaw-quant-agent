from __future__ import annotations

import re
from functools import lru_cache

from .paths import PROJECT_ROOT


TARGET_STOCKS_PATH = PROJECT_ROOT / "docs" / "target-stocks.md"
_TABLE_ROW_RE = re.compile(r"^\|\s*(\d{6})\.(?:SH|SZ)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")
_THEME_HEADER_RE = re.compile(r"^###\s+主题\s*\d+[:：]\s*(.+?)\s*$")
_REPRESENTATIVE_RE = re.compile(r"代表标的[:：]\s*(.+)")
_CODE_WITH_NAME_RE = re.compile(r"(\d{6})[（(]([^）)]+)[）)]")
_CORPORATE_SUFFIXES = (
    "集团股份有限公司",
    "控股股份有限公司",
    "股份有限公司",
    "有限责任公司",
    "控股有限公司",
    "股份公司",
    "有限公司",
    "集团",
)
_COMPANY_TERM_RE = re.compile(
    r"([\u4e00-\u9fff]{2,20}(?:集团股份有限公司|控股股份有限公司|股份有限公司|有限责任公司|控股有限公司|股份公司|有限公司|集团|银行|证券|科技|信息|化工|药业|制药|电子|能源|电力|汽车|旅游|材料|医药|味业|乳业|国际|重工|智家))"
)
_PUNCTUATION_RE = re.compile(r"[\s\u3000()（）【】\[\]《》<>“”\"'':：,，。；;、\-—_]")


@lru_cache(maxsize=1)
def load_target_stocks() -> dict[str, dict[str, object]]:
    mapping: dict[str, dict[str, object]] = {}
    if not TARGET_STOCKS_PATH.exists():
        return mapping

    for line in TARGET_STOCKS_PATH.read_text(encoding="utf-8").splitlines():
        match = _TABLE_ROW_RE.match(line.strip())
        if not match:
            continue
        code, name, industry = match.groups()
        mapping[code] = {
            "code": code,
            "name": name.strip(),
            "industry": industry.strip(),
            "aliases": build_company_aliases(name.strip()),
        }
    return mapping


def build_company_aliases(name: str) -> list[str]:
    aliases = []
    for candidate in [name, normalize_company_term(name)]:
        normalized = candidate.strip()
        if normalized and normalized not in aliases:
            aliases.append(normalized)
    return aliases


def normalize_company_term(term: str) -> str:
    value = _PUNCTUATION_RE.sub("", term or "")
    changed = True
    while changed and value:
        changed = False
        for suffix in _CORPORATE_SUFFIXES:
            if value.endswith(suffix) and len(value) > len(suffix) + 1:
                value = value[: -len(suffix)]
                changed = True
                break
    return value


def extract_company_terms(text: str) -> list[str]:
    haystack = text or ""
    matched: list[str] = []

    for item in load_target_stocks().values():
        aliases = item.get("aliases", [])
        if item["code"] in haystack or any(alias and alias in haystack for alias in aliases):
            for alias in aliases:
                if alias not in matched:
                    matched.append(alias)

    for raw_term in _COMPANY_TERM_RE.findall(haystack):
        for candidate in [raw_term, normalize_company_term(raw_term)]:
            if candidate and candidate not in matched:
                matched.append(candidate)
    return matched


def matches_company_terms(text: str, company_terms: list[str]) -> bool:
    if not company_terms:
        return True
    raw_text = text or ""
    normalized_text = normalize_company_term(raw_text)
    for term in company_terms:
        normalized_term = normalize_company_term(term)
        if term and term in raw_text:
            return True
        if normalized_term and normalized_term in normalized_text:
            return True
    return False


def match_company_code(text: str) -> str | None:
    haystack = text or ""
    for code, item in load_target_stocks().items():
        aliases = item.get("aliases", [])
        if code in haystack or any(alias and alias in haystack for alias in aliases):
            return code
    return None


@lru_cache(maxsize=1)
def load_theme_pool() -> list[dict[str, object]]:
    themes: list[dict[str, object]] = []
    if not TARGET_STOCKS_PATH.exists():
        return themes

    current: dict[str, object] | None = None
    for raw_line in TARGET_STOCKS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        header = _THEME_HEADER_RE.match(line)
        if header:
            current = {"theme": header.group(1).strip(), "codes": [], "names": []}
            themes.append(current)
            continue
        if current is None:
            continue
        representative = _REPRESENTATIVE_RE.search(line)
        if not representative:
            continue
        for code, name in _CODE_WITH_NAME_RE.findall(representative.group(1)):
            current["codes"].append(code)
            current["names"].append(name)
    return themes


def extract_stock_matches(text: str) -> list[dict[str, str]]:
    haystack = text or ""
    matched: list[dict[str, str]] = []
    for code, item in load_target_stocks().items():
        aliases = item.get("aliases", [])
        if code in haystack or any(alias and alias in haystack for alias in aliases):
            matched.append({"code": code, "name": item["name"]})
    return matched


def extract_theme_matches(text: str) -> list[str]:
    haystack = text or ""
    matched: list[str] = []
    for theme in load_theme_pool():
        theme_name = theme["theme"]
        if theme_name in haystack:
            matched.append(theme_name)
            continue
        names = theme.get("names", [])
        codes = theme.get("codes", [])
        hits = 0
        for value in list(names) + list(codes):
            if value in haystack:
                hits += 1
        if hits >= 2:
            matched.append(theme_name)
    return matched


def build_research_metadata(text: str, explicit_code: str | None = None) -> dict[str, object]:
    stock_matches = extract_stock_matches(text)
    matched_codes = [item["code"] for item in stock_matches]
    if explicit_code and explicit_code not in matched_codes:
        stock_item = load_target_stocks().get(explicit_code)
        if stock_item:
            stock_matches.insert(0, {"code": explicit_code, "name": str(stock_item["name"])})
            matched_codes.insert(0, explicit_code)

    return {
        "primary_company_code": explicit_code or (matched_codes[0] if matched_codes else None),
        "matched_stocks": stock_matches,
        "matched_themes": extract_theme_matches(text),
        "company_terms": extract_company_terms(text),
    }
