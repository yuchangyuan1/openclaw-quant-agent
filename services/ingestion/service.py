from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from services.common.paths import raw_data_dir
from services.common.repository import DocumentRepository
from services.common.stocks import load_target_stocks
from services.common.text import sha256_hexdigest, stable_uuid

from . import providers
from .state import IngestionTaskRepository

_SOURCE_GROUPS = {
    "all": ["eastmoney_news", "10jqka", "sina", "announcement", "sse", "szse"],
    "all_news": ["eastmoney_news", "10jqka", "sina"],
    "all_announcements": ["announcement", "sse", "szse"],
    "eastmoney": ["eastmoney_news", "announcement"],
    "eastmoney_news": ["eastmoney_news"],
    "10jqka": ["10jqka"],
    "sina": ["sina"],
    "announcement": ["announcement"],
    "sse": ["sse"],
    "szse": ["szse"],
}

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_REPO = DocumentRepository()
_TASK_REPO = IngestionTaskRepository()


def trigger_ingest(
    source: str,
    date: str | None,
    stock_codes: list[str],
    *,
    target_pool: bool = False,
    incremental: bool = False,
    lookback_days: int = 3,
    per_stock_limit: int = 3,
    task_name: str | None = None,
) -> dict:
    target_date = date or datetime.now().date().isoformat()
    resolved_stock_codes = _resolve_stock_codes(stock_codes, target_pool)
    resolved_sources = _resolve_sources(source or "all")
    resolved_task_name = task_name or _default_task_name(
        source or "all",
        resolved_stock_codes,
        target_pool,
        incremental,
    )
    job_id = f"ingest_{target_date.replace('-', '')}_{datetime.now().strftime('%H%M%S')}"
    with _LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "docs_collected": 0,
            "docs_failed": 0,
            "started_at": None,
            "finished_at": None,
            "backend": _REPO.backend(),
            "task_name": resolved_task_name,
            "sources": resolved_sources,
            "target_pool": target_pool,
            "incremental": incremental,
            "stock_codes": resolved_stock_codes,
            "source_runs": [],
        }

    worker = threading.Thread(
        target=_run_job,
        args=(
            job_id,
            source or "all",
            target_date,
            resolved_stock_codes,
            target_pool,
            incremental,
            lookback_days,
            per_stock_limit,
            resolved_task_name,
            _TASK_REPO,
            _persist_article,
            providers.fetch_documents,
        ),
        daemon=True,
        name=f"ingestion-{job_id}",
    )
    worker.start()
    return {
        "job_id": job_id,
        "status": "queued",
        "estimated_docs": _estimate_docs(source or "all", resolved_stock_codes, per_stock_limit),
        "task_name": resolved_task_name,
        "sources": resolved_sources,
        "target_pool": target_pool,
        "incremental": incremental,
        "stock_count": len(resolved_stock_codes),
    }


def trigger_target_pool_sync(
    *,
    source: str = "all",
    date: str | None = None,
    lookback_days: int = 2,
    per_stock_limit: int = 4,
    task_name: str = "target_pool_incremental_sync",
) -> dict:
    return trigger_ingest(
        source,
        date,
        [],
        target_pool=True,
        incremental=True,
        lookback_days=lookback_days,
        per_stock_limit=per_stock_limit,
        task_name=task_name,
    )


def get_job_status(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
    if job:
        return job
    return {
        "job_id": job_id,
        "status": "not_found",
        "docs_collected": 0,
        "docs_failed": 0,
        "started_at": None,
        "finished_at": None,
    }


def list_documents(
    date: str | None = None,
    source: str | None = None,
    stock_code: str | None = None,
    doc_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    return _REPO.list_documents(
        date=date,
        source=source,
        stock_code=stock_code,
        doc_type=doc_type,
        limit=limit,
        offset=offset,
    )


def list_tasks() -> dict:
    items = _TASK_REPO.list_tasks()
    return {"total": len(items), "items": items}


def _run_job(
    job_id: str,
    source: str,
    date_str: str,
    stock_codes: list[str],
    target_pool: bool,
    incremental: bool,
    lookback_days: int,
    per_stock_limit: int,
    task_name: str,
    task_repo: IngestionTaskRepository | None = None,
    persist_article_func=None,
    fetch_documents_func=None,
) -> None:
    task_repo = task_repo or _TASK_REPO
    persist_article = persist_article_func or _persist_article
    fetch_documents = fetch_documents_func or providers.fetch_documents
    _update_job(job_id, status="running", started_at=_now_iso())
    docs_collected = 0
    docs_failed = 0
    source_runs: list[dict] = []

    for selected_source in _resolve_sources(source):
        date_from, date_to = task_repo.resolve_window(
            task_name=task_name,
            source=selected_source,
            explicit_date=date_str if not incremental else None,
            incremental=incremental,
            lookback_days=lookback_days,
        )
        source_collected = 0
        source_failed = 0
        status = "completed"
        try:
            articles = fetch_documents(
                selected_source,
                stock_codes,
                date_from=date_from,
                date_to=date_to,
                per_stock_limit=per_stock_limit,
            )
        except Exception:
            articles = []
            source_failed += 1
            docs_failed += 1
            status = "failed"

        for article in articles:
            try:
                if persist_article(article):
                    docs_collected += 1
                    source_collected += 1
            except Exception:
                docs_failed += 1
                source_failed += 1
                status = "completed_with_errors"

        source_run = {
            "source": selected_source,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "docs_collected": source_collected,
            "docs_failed": source_failed,
        }
        source_runs.append(source_run)
        task_repo.record_run(
            task_name=task_name,
            job_id=job_id,
            source=selected_source,
            status="completed" if status != "failed" else "failed",
            date_from=date_from,
            date_to=date_to,
            docs_collected=source_collected,
            docs_failed=source_failed,
            stock_codes=stock_codes,
            target_pool=target_pool,
            incremental=incremental,
        )

    _update_job(
        job_id,
        status="completed" if docs_failed == 0 else "completed_with_errors",
        docs_collected=docs_collected,
        docs_failed=docs_failed,
        finished_at=_now_iso(),
        source_runs=source_runs,
    )


def _resolve_stock_codes(stock_codes: list[str], target_pool: bool) -> list[str]:
    if target_pool:
        return sorted(load_target_stocks().keys())
    return list(dict.fromkeys(stock_codes))


def _resolve_sources(source: str) -> list[str]:
    resolved = _SOURCE_GROUPS.get(source)
    if resolved is None:
        return []
    return list(resolved)


def _default_task_name(source: str, stock_codes: list[str], target_pool: bool, incremental: bool) -> str:
    mode = "incremental" if incremental else "adhoc"
    scope = "target_pool" if target_pool else ("stocks_" + "_".join(stock_codes[:3]) if stock_codes else "market")
    return f"{mode}_{source}_{scope}"


def _estimate_docs(source: str, stock_codes: list[str], per_stock_limit: int) -> int:
    resolved_sources = _resolve_sources(source)
    if not stock_codes:
        return len(resolved_sources) * providers.MAX_DOCS_PER_SOURCE
    return len(resolved_sources) * len(stock_codes) * per_stock_limit


def _persist_article(article: dict) -> bool:
    content = article["content"].strip()
    content_hash = sha256_hexdigest(f"{article['title']}\n{content}")
    doc_id = stable_uuid(f"{article['source']}|{article.get('url')}|{content_hash}")
    raw_file = _raw_path(article["source"], article.get("published_at")) / f"{doc_id}.json"

    inserted, _existing = _REPO.save_document(
        {
            "id": doc_id,
            "source": article["source"],
            "doc_type": article["doc_type"],
            "title": article["title"],
            "url": article.get("url"),
            "file_path": str(raw_file),
            "content_hash": content_hash,
            "company_code": article.get("company_code"),
            "published_at": article.get("published_at"),
            "is_indexed": False,
            "is_duplicate": False,
        }
    )
    if not inserted:
        return False

    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text(
        json.dumps(
            {
                "id": doc_id,
                "source": article["source"],
                "doc_type": article["doc_type"],
                "title": article["title"],
                "url": article.get("url"),
                "company_code": article.get("company_code"),
                "published_at": article.get("published_at"),
                "pdf_url": article.get("pdf_url"),
                "metadata": article.get("metadata", {}),
                "content": content,
                "ingested_at": _now_iso(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return True


def _raw_path(source: str, published_at: str | None) -> Path:
    date_part = (published_at or datetime.now().date().isoformat())[:10]
    return raw_data_dir() / source / date_part


def _update_job(job_id: str, **fields) -> None:
    with _LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(fields)


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat()
