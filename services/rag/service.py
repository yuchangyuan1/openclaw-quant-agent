from __future__ import annotations

import json
from collections import Counter
from math import log

from services.common.graph import GraphRepository
from services.common.paths import metadata_dir
from services.common.repository import DocumentRepository
from services.common.stocks import matches_company_terms
from services.common.text import build_snippet, chunk_text, normalize_text, tokenize_text

from . import chroma_client


_REPO = DocumentRepository()
_GRAPH_REPO = GraphRepository(metadata_dir() / "graph_manifest.json")


def build_index(doc_ids: list[str], force_rebuild: bool) -> dict:
    documents = _REPO.get_documents(doc_ids=doc_ids or None, only_unindexed=not force_rebuild)
    if not force_rebuild and not doc_ids:
        pending_graph_doc_ids = _GRAPH_REPO.get_unsynced_document_ids()
        if pending_graph_doc_ids:
            graph_docs = _REPO.get_documents(doc_ids=pending_graph_doc_ids)
            by_id = {item["id"]: item for item in documents}
            for item in graph_docs:
                by_id[item["id"]] = item
            documents = list(by_id.values())
    if force_rebuild and doc_ids:
        chroma_client.delete_doc_ids(doc_ids)

    indexed_doc_ids: list[str] = []
    indexed_chunks = 0
    synced_graph_docs = 0
    synced_entities = 0
    synced_relations = 0
    vector_errors: list[str] = []
    for document in documents:
        raw = _load_raw(document)
        graph_sync = _GRAPH_REPO.sync_document_graph(document, raw)
        synced_graph_docs += 1
        synced_entities += graph_sync["entities"]
        synced_relations += graph_sync["relations"]

        should_index = force_rebuild or not document.get("is_indexed")
        if not should_index:
            continue
        text = normalize_text(f"{document['title']}\n\n{raw.get('content', '')}")
        chunks = chunk_text(text)
        if not chunks:
            continue

        payload = []
        research_metadata = raw.get("metadata", {})
        for idx, chunk in enumerate(chunks):
            payload.append(
                {
                    "id": f"{document['id']}::{idx}",
                    "text": chunk,
                    "metadata": {
                        "doc_id": document["id"],
                        "title": document["title"],
                        "source": document["source"],
                        "url": document.get("url"),
                        "company_code": document.get("company_code"),
                        "doc_type": document.get("doc_type"),
                        "published_at": document.get("published_at"),
                        "primary_company_code": research_metadata.get("primary_company_code"),
                        "matched_themes": ",".join(research_metadata.get("matched_themes", [])),
                        "company_terms": ",".join(research_metadata.get("company_terms", [])),
                        "matched_stocks": ",".join(
                            item["code"] for item in research_metadata.get("matched_stocks", [])
                        ),
                        "chunk_index": idx,
                    },
                }
            )

        upsert_ok, upsert_error = chroma_client.upsert_documents(payload)
        if upsert_ok:
            indexed_doc_ids.append(document["id"])
            indexed_chunks += len(payload)
        elif upsert_error:
            vector_errors.append(f"{document['id']}: {upsert_error}")

    _REPO.mark_indexed(indexed_doc_ids)
    vector_status = chroma_client.get_status()
    return {
        "job_id": f"index_{len(indexed_doc_ids)}_{indexed_chunks}",
        "status": "completed" if not vector_errors else "completed_with_warnings",
        "indexed_docs": len(indexed_doc_ids),
        "indexed_chunks": indexed_chunks,
        "synced_graph_docs": synced_graph_docs,
        "synced_entities": synced_entities,
        "synced_relations": synced_relations,
        "backend": _REPO.backend(),
        "graph_backend": _GRAPH_REPO.backend(),
        "vector_backend": vector_status.get("backend"),
        "vector_error": vector_status.get("error"),
        "vector_warnings": vector_errors[:10],
    }


def retrieve(
    query: str,
    stock_codes: list[str],
    company_terms: list[str],
    doc_types: list[str],
    date_range: dict | None,
    top_k: int,
    min_score: float,
) -> dict:
    documents = _REPO.get_documents(
        stock_codes=None,
        doc_types=doc_types or None,
        date_range=(date_range["start"], date_range["end"]) if date_range else None,
    )
    keyword_results = _keyword_results(documents, query, stock_codes, company_terms)
    dense_results = _dense_results(query, stock_codes, company_terms, doc_types, date_range, top_k)

    merged: dict[str, dict] = {}
    for item in keyword_results:
        merged[item["doc_id"]] = item
    for item in dense_results:
        existing = merged.get(item["doc_id"])
        if not existing:
            merged[item["doc_id"]] = item
            continue
        existing["score"] = max(existing["score"], item["score"])
        existing["retrieval_method"] = "dense+keyword"
        existing["company_code"] = existing.get("company_code") or item.get("company_code")
        existing["matched_themes"] = sorted(
            set(existing.get("matched_themes", [])) | set(item.get("matched_themes", []))
        )
        existing["matched_stocks"] = sorted(
            set(existing.get("matched_stocks", [])) | set(item.get("matched_stocks", []))
        )

    ranked = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
    results = [item for item in ranked if item["score"] >= min_score][:top_k]
    graph_context = _GRAPH_REPO.get_graph_context(
        doc_ids=[item["doc_id"] for item in results],
        stock_codes=stock_codes,
        company_terms=company_terms,
        limit=max(top_k * 2, 6),
    )
    return {
        "query": query,
        "results": results,
        "total_retrieved": len(results),
        "graph_context": graph_context,
    }


def _load_raw(document: dict) -> dict:
    if not document.get("file_path"):
        return {}
    with open(document["file_path"], "r", encoding="utf-8") as handle:
        return json.load(handle)


def _keyword_results(
    documents: list[dict],
    query: str,
    stock_codes: list[str],
    company_terms: list[str],
) -> list[dict]:
    query_tokens = tokenize_text(query)
    corpus_tokens: dict[str, list[str]] = {}
    raw_docs: dict[str, dict] = {}
    df = Counter()

    for document in documents:
        raw = _load_raw(document)
        raw_docs[document["id"]] = raw
        text = normalize_text(f"{document['title']}\n{raw.get('content', '')}")
        tokens = tokenize_text(text)
        corpus_tokens[document["id"]] = tokens
        df.update(set(tokens))

    if not documents:
        return []

    avgdl = sum(len(tokens) for tokens in corpus_tokens.values()) / max(1, len(corpus_tokens))
    query_tf = Counter(query_tokens)
    scored = []
    for document in documents:
        tokens = corpus_tokens.get(document["id"], [])
        if not tokens:
            continue
        raw = raw_docs[document["id"]]
        if stock_codes and not _raw_matches_stock_codes(document, raw, stock_codes):
            continue
        if company_terms and not _raw_matches_company_terms(document, raw, company_terms):
            continue
        tf = Counter(tokens)
        score = 0.0
        for token, qf in query_tf.items():
            if token not in tf:
                continue
            idf = log(1 + (len(documents) - df[token] + 0.5) / (df[token] + 0.5))
            denom = tf[token] + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / max(1.0, avgdl))
            score += qf * idf * (tf[token] * 2.5) / denom
        if score <= 0:
            continue
        matched_stocks = _raw_matched_stocks(raw)
        score = _boost_score_for_stock_match(score, matched_stocks, stock_codes)
        score = _boost_score_for_company_terms(score, raw, document, company_terms)
        scored.append((document, raw, score, build_snippet(raw.get("content", document["title"]), query)))

    if not scored:
        return []

    max_score = max(score for _, _, score, _ in scored)
    return [
        {
            "doc_id": document["id"],
            "title": document["title"],
            "source": document["source"],
            "url": document.get("url"),
            "published_at": document.get("published_at"),
            "company_code": document.get("company_code"),
            "snippet": snippet,
            "score": round(score / max_score, 4),
            "retrieval_method": "keyword",
            "matched_themes": raw.get("metadata", {}).get("matched_themes", []),
            "matched_stocks": _raw_matched_stocks(raw),
        }
        for document, raw, score, snippet in scored
    ]


def _dense_results(
    query: str,
    stock_codes: list[str],
    company_terms: list[str],
    doc_types: list[str],
    date_range: dict | None,
    top_k: int,
) -> list[dict]:
    items = chroma_client.query(query_text=query, top_k=max(top_k * 4, 10))
    results = []
    for item in items:
        metadata = item.get("metadata", {})
        published_at = metadata.get("published_at")
        matched_stocks = _metadata_matched_stocks(metadata)
        if stock_codes and not _metadata_matches_stock_codes(metadata, stock_codes):
            continue
        if company_terms and not _metadata_matches_company_terms(item, metadata, company_terms):
            continue
        if doc_types and metadata.get("doc_type") not in doc_types:
            continue
        if date_range and published_at:
            published_date = published_at[:10]
            if not (date_range["start"] <= published_date <= date_range["end"]):
                continue
        score = round(max(0.0, 1.0 - float(item.get("distance", 1.0))), 4)
        score = _boost_score_for_stock_match(score, matched_stocks, stock_codes)
        score = _boost_score_for_company_terms(score, {"content": item.get("document", "")}, metadata, company_terms)
        results.append(
            {
                "doc_id": metadata.get("doc_id") or item["id"].split("::")[0],
                "title": metadata.get("title"),
                "source": metadata.get("source"),
                "url": metadata.get("url"),
                "published_at": published_at,
                "company_code": metadata.get("company_code"),
                "snippet": build_snippet(item.get("document", ""), query),
                "score": score,
                "retrieval_method": "dense",
                "matched_themes": metadata.get("matched_themes", "").split(",")
                if metadata.get("matched_themes")
                else [],
                "matched_stocks": matched_stocks,
            }
        )
    return results


def _boost_score_for_stock_match(score: float, matched_stocks: list[str], stock_codes: list[str]) -> float:
    if not stock_codes:
        return score
    if set(matched_stocks) & set(stock_codes):
        return round(min(1.0, score + 0.15), 4)
    return score


def _boost_score_for_company_terms(score: float, raw: dict, document: dict, company_terms: list[str]) -> float:
    if not company_terms:
        return score
    haystack = "\n".join(
        [
            str(document.get("title") or ""),
            str(raw.get("content") or ""),
            str(document.get("snippet") or ""),
        ]
    )
    if matches_company_terms(haystack, company_terms):
        return round(min(1.0, score + 0.12), 4)
    return score


def _raw_matches_stock_codes(document: dict, raw: dict, stock_codes: list[str]) -> bool:
    if not stock_codes:
        return True
    candidates = {code for code in _raw_matched_stocks(raw) if code}
    if document.get("company_code"):
        candidates.add(document["company_code"])
    return bool(candidates & set(stock_codes))


def _raw_matches_company_terms(document: dict, raw: dict, company_terms: list[str]) -> bool:
    haystack = "\n".join([str(document.get("title") or ""), str(raw.get("content") or "")])
    return matches_company_terms(haystack, company_terms)


def _raw_matched_stocks(raw: dict) -> list[str]:
    metadata = raw.get("metadata", {})
    codes = []
    primary_code = metadata.get("primary_company_code")
    if primary_code:
        codes.append(primary_code)
    for item in metadata.get("matched_stocks", []):
        if isinstance(item, dict):
            code = item.get("code")
        else:
            code = str(item)
        if code and code not in codes:
            codes.append(code)
    return codes


def _metadata_matches_stock_codes(metadata: dict, stock_codes: list[str]) -> bool:
    if not stock_codes:
        return True
    candidates = {code for code in _metadata_matched_stocks(metadata) if code}
    company_code = metadata.get("company_code")
    if company_code:
        candidates.add(company_code)
    return bool(candidates & set(stock_codes))


def _metadata_matches_company_terms(item: dict, metadata: dict, company_terms: list[str]) -> bool:
    haystack = "\n".join(
        [
            str(metadata.get("title") or ""),
            str(item.get("document") or ""),
        ]
    )
    return matches_company_terms(haystack, company_terms)


def _metadata_matched_stocks(metadata: dict) -> list[str]:
    codes = []
    primary_code = metadata.get("primary_company_code")
    if primary_code:
        codes.append(primary_code)
    raw_codes = metadata.get("matched_stocks")
    if isinstance(raw_codes, str):
        values = [item.strip() for item in raw_codes.split(",") if item.strip()]
    elif isinstance(raw_codes, list):
        values = [str(item).strip() for item in raw_codes if str(item).strip()]
    else:
        values = []
    for code in values:
        if code not in codes:
            codes.append(code)
    return codes
