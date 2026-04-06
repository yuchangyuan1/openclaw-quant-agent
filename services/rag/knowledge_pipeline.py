from __future__ import annotations

from datetime import date, timedelta

from services.common.stocks import extract_company_terms, load_target_stocks

from . import service


def build_query_variants(question: str, stock_codes: list[str] | None = None) -> list[str]:
    base = question.strip()
    variants = [base]
    stocks = load_target_stocks()

    codes = [code for code in (stock_codes or []) if code in stocks]
    for code in codes[:2]:
        name = stocks[code]["name"]
        variants.append(f"{name} 最新动态")
        variants.append(f"{code} 公告 新闻")

    lowered = base.lower()
    if "公告" not in base:
        variants.append(f"{base} 公告")
    if "新闻" not in base and "最新" not in base:
        variants.append(f"{base} 最新进展")
    if "业绩" in base or "财报" in base:
        variants.append(f"{base} 营收 净利润")

    deduped: list[str] = []
    for item in variants:
        normalized = item.strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped[:4]


def build_evidence_pack(
    question: str,
    stock_codes: list[str] | None = None,
    company_terms: list[str] | None = None,
    doc_types: list[str] | None = None,
    days: int = 7,
    top_k: int = 5,
    min_score: float = 0.7,
) -> dict:
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=days)).isoformat()

    resolved_company_terms = company_terms or extract_company_terms(question)
    merged: dict[str, dict] = {}
    graph_context = {"companies": [], "themes": [], "industries": [], "relations": [], "doc_entity_counts": {}}
    for query in build_query_variants(question, stock_codes):
        response = service.retrieve(
            query=query,
            stock_codes=stock_codes or [],
            company_terms=resolved_company_terms,
            doc_types=doc_types or [],
            date_range={"start": start, "end": end},
            top_k=top_k,
            min_score=min_score,
        )
        graph_context = _merge_graph_context(graph_context, response.get("graph_context", {}))
        for item in response["results"]:
            existing = merged.get(item["doc_id"])
            if existing is None or item["score"] > existing["score"]:
                merged[item["doc_id"]] = item

    ranked = sorted(merged.values(), key=lambda item: item["score"], reverse=True)[:top_k]
    evidence_pack = []
    for index, item in enumerate(ranked, start=1):
        evidence_pack.append(
            {
                "evidence_id": f"E{index:03d}",
                "doc_id": item["doc_id"],
                "title": item["title"],
                "source": item["source"],
                "url": item.get("url"),
                "published_at": item.get("published_at"),
                "company_code": item.get("company_code"),
                "snippet": item.get("snippet"),
                "score": item["score"],
                "matched_themes": item.get("matched_themes", []),
                "matched_stocks": item.get("matched_stocks", []),
            }
        )

    latest_evidence_date = max(
        (item["published_at"][:10] for item in evidence_pack if item.get("published_at")),
        default=None,
    )
    matched_themes = sorted({theme for item in evidence_pack for theme in item.get("matched_themes", [])})
    matched_companies = sorted(
        {
            code
            for item in evidence_pack
            for code in ([item["company_code"]] if item.get("company_code") else []) + item.get("matched_stocks", [])
            if code
        }
    )
    coverage_warning = None
    if not evidence_pack:
        coverage_warning = "未找到相关文档"
    elif latest_evidence_date and latest_evidence_date < start:
        coverage_warning = f"证据覆盖不足：未找到 {start} 之后的相关文档"

    return {
        "query": question,
        "query_variants": build_query_variants(question, stock_codes),
        "company_terms": resolved_company_terms,
        "evidence_pack": evidence_pack,
        "synthesis": synthesize_answer(question, evidence_pack),
        "latest_evidence_date": latest_evidence_date,
        "matched_themes": matched_themes,
        "matched_companies": matched_companies,
        "coverage_warning": coverage_warning,
        "graph_context": graph_context,
    }


def _merge_graph_context(current: dict, incoming: dict) -> dict:
    merged = {
        "companies": _dedupe_entity_items(current.get("companies", []) + incoming.get("companies", [])),
        "themes": _dedupe_entity_items(current.get("themes", []) + incoming.get("themes", [])),
        "industries": _dedupe_entity_items(current.get("industries", []) + incoming.get("industries", [])),
        "relations": _dedupe_relation_items(current.get("relations", []) + incoming.get("relations", [])),
        "doc_entity_counts": dict(current.get("doc_entity_counts", {})),
    }
    for key, value in incoming.get("doc_entity_counts", {}).items():
        merged["doc_entity_counts"][key] = merged["doc_entity_counts"].get(key, 0) + value
    return merged


def _dedupe_entity_items(items: list[dict]) -> list[dict]:
    unique: dict[tuple[str, str], dict] = {}
    for item in items:
        key = (item.get("type"), item.get("key"))
        if key not in unique:
            unique[key] = item
    return list(unique.values())


def _dedupe_relation_items(items: list[dict]) -> list[dict]:
    unique: dict[tuple[str, str, str, str], dict] = {}
    for item in items:
        key = (
            item.get("src"),
            item.get("relation_type"),
            item.get("dst"),
            item.get("source_doc_id"),
        )
        if key not in unique:
            unique[key] = item
    return list(unique.values())


def synthesize_answer(question: str, evidence_pack: list[dict]) -> str:
    if not evidence_pack:
        return f"根据现有证据，暂未检索到与“{question}”直接相关的公开资料。"

    lines = []
    for item in evidence_pack[:3]:
        citation = f"[{item['evidence_id']}]"
        snippet = (item.get("snippet") or "").strip()
        if not snippet:
            snippet = item["title"]
        lines.append(f"{citation} {snippet}")
    return "根据现有证据，相关信息主要包括：" + "；".join(lines) + "。"
