from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

from .paths import PROJECT_ROOT, metadata_dir
from .stocks import load_target_stocks

load_dotenv(PROJECT_ROOT / ".env")


def _manifest_path() -> Path:
    override = os.getenv("DOCUMENT_MANIFEST_PATH")
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            path = (metadata_dir() / path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return metadata_dir() / "documents_manifest.json"


def _database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


@contextmanager
def _connect():
    database_url = _database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    conn = psycopg2.connect(database_url, connect_timeout=3)
    try:
        yield conn
    finally:
        conn.close()


def _to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _load_manifest() -> list[dict[str, Any]]:
    path = _manifest_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manifest(items: list[dict[str, Any]]) -> None:
    path = _manifest_path()
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


class DocumentRepository:
    def __init__(self) -> None:
        self._backend = "manifest"
        self._checked_backend = False

    def backend(self) -> str:
        if not self._checked_backend:
            self._probe_backend()
        return self._backend

    def _probe_backend(self) -> None:
        try:
            with _connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
            self._backend = "postgres"
        except Exception:
            self._backend = "manifest"
        self._checked_backend = True

    def save_document(self, document: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        if self.backend() == "postgres":
            return self._save_postgres(document)
        return self._save_manifest(document)

    def list_documents(
        self,
        *,
        date: str | None = None,
        source: str | None = None,
        stock_code: str | None = None,
        doc_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        if self.backend() == "postgres":
            return self._list_postgres(date, source, stock_code, doc_type, limit, offset)
        return self._list_manifest(date, source, stock_code, doc_type, limit, offset)

    def get_documents(
        self,
        *,
        doc_ids: list[str] | None = None,
        only_unindexed: bool = False,
        source: str | None = None,
        stock_codes: list[str] | None = None,
        doc_types: list[str] | None = None,
        date_range: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        if self.backend() == "postgres":
            return self._get_postgres(doc_ids, only_unindexed, source, stock_codes, doc_types, date_range)
        return self._get_manifest(doc_ids, only_unindexed, source, stock_codes, doc_types, date_range)

    def mark_indexed(self, doc_ids: list[str]) -> None:
        if not doc_ids:
            return
        if self.backend() == "postgres":
            with _connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE documents SET is_indexed = TRUE WHERE id::text = ANY(%s)", (doc_ids,))
                conn.commit()
            return

        items = _load_manifest()
        changed = False
        for item in items:
            if item["id"] in doc_ids:
                item["is_indexed"] = True
                changed = True
        if changed:
            _save_manifest(items)

    def _save_postgres(self, document: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        with _connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                self._ensure_stock_exists(cursor, document.get("company_code"))
                cursor.execute(
                    """
                    SELECT id, source, doc_type, title, url, file_path, content_hash, company_code,
                           published_at, ingested_at, is_indexed, is_duplicate
                    FROM documents WHERE content_hash = %s
                    """,
                    (document["content_hash"],),
                )
                existing = cursor.fetchone()
                if existing:
                    conn.commit()
                    return False, self._normalize(existing)

                cursor.execute(
                    """
                    INSERT INTO documents (
                        id, source, doc_type, title, url, file_path, content_hash, company_code,
                        published_at, ingested_at, is_indexed, is_duplicate
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s)
                    RETURNING id, source, doc_type, title, url, file_path, content_hash, company_code,
                              published_at, ingested_at, is_indexed, is_duplicate
                    """,
                    (
                        document["id"],
                        document["source"],
                        document["doc_type"],
                        document["title"],
                        document.get("url"),
                        document.get("file_path"),
                        document["content_hash"],
                        document.get("company_code"),
                        document.get("published_at"),
                        document.get("is_indexed", False),
                        document.get("is_duplicate", False),
                    ),
                )
                inserted = cursor.fetchone()
            conn.commit()
        return True, self._normalize(inserted)

    @staticmethod
    def _ensure_stock_exists(cursor, stock_code: str | None) -> None:
        if not stock_code:
            return
        target_item = load_target_stocks().get(stock_code)
        name = target_item["name"] if target_item else stock_code
        industry = target_item.get("industry") if target_item else None
        tier = "core" if target_item else "watchlist"
        cursor.execute(
            """
            INSERT INTO stocks (code, name, industry, tier)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (code) DO NOTHING
            """,
            (stock_code, name, industry, tier),
        )

    def _list_postgres(self, date, source, stock_code, doc_type, limit, offset) -> dict[str, Any]:
        conditions = []
        params: list[Any] = []
        if date:
            conditions.append("published_at::date = %s")
            params.append(date)
        if source:
            conditions.append("source = %s")
            params.append(source)
        if stock_code:
            conditions.append("company_code = %s")
            params.append(stock_code)
        if doc_type:
            conditions.append("doc_type = %s")
            params.append(doc_type)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with _connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(f"SELECT COUNT(*) AS total FROM documents {where_sql}", params)
                total = cursor.fetchone()["total"]
                cursor.execute(
                    f"""
                    SELECT id, source, doc_type, title, url, company_code, published_at, is_indexed
                    FROM documents {where_sql}
                    ORDER BY published_at DESC NULLS LAST, ingested_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*params, limit, offset],
                )
                items = [self._normalize(row) for row in cursor.fetchall()]
        return {"total": total, "items": items}

    def _get_postgres(self, doc_ids, only_unindexed, source, stock_codes, doc_types, date_range) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []
        if doc_ids:
            conditions.append("id::text = ANY(%s)")
            params.append(doc_ids)
        if only_unindexed:
            conditions.append("is_indexed = FALSE")
        if source:
            conditions.append("source = %s")
            params.append(source)
        if stock_codes:
            conditions.append("company_code = ANY(%s)")
            params.append(stock_codes)
        if doc_types:
            conditions.append("doc_type = ANY(%s)")
            params.append(doc_types)
        if date_range:
            conditions.append("published_at::date BETWEEN %s AND %s")
            params.extend(date_range)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with _connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f"""
                    SELECT id, source, doc_type, title, url, file_path, content_hash, company_code,
                           published_at, ingested_at, is_indexed, is_duplicate
                    FROM documents {where_sql}
                    ORDER BY published_at DESC NULLS LAST, ingested_at DESC
                    """,
                    params,
                )
                return [self._normalize(row) for row in cursor.fetchall()]

    def _save_manifest(self, document: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        items = _load_manifest()
        for item in items:
            if item["content_hash"] == document["content_hash"]:
                return False, item

        record = {
            "id": document["id"],
            "source": document["source"],
            "doc_type": document["doc_type"],
            "title": document["title"],
            "url": document.get("url"),
            "file_path": document.get("file_path"),
            "content_hash": document["content_hash"],
            "company_code": document.get("company_code"),
            "published_at": _to_iso(document.get("published_at")),
            "ingested_at": datetime.now().isoformat(),
            "is_indexed": bool(document.get("is_indexed", False)),
            "is_duplicate": bool(document.get("is_duplicate", False)),
        }
        items.append(record)
        items.sort(key=lambda item: item.get("published_at") or "", reverse=True)
        _save_manifest(items)
        return True, record

    def _list_manifest(self, date, source, stock_code, doc_type, limit, offset) -> dict[str, Any]:
        items = self._get_manifest(
            None,
            False,
            source,
            [stock_code] if stock_code else None,
            [doc_type] if doc_type else None,
            (date, date) if date else None,
        )
        return {"total": len(items), "items": items[offset : offset + limit]}

    def _get_manifest(self, doc_ids, only_unindexed, source, stock_codes, doc_types, date_range) -> list[dict[str, Any]]:
        filtered = []
        for item in _load_manifest():
            if doc_ids and item["id"] not in doc_ids:
                continue
            if only_unindexed and item.get("is_indexed"):
                continue
            if source and item.get("source") != source:
                continue
            if stock_codes and item.get("company_code") not in stock_codes:
                continue
            if doc_types and item.get("doc_type") not in doc_types:
                continue
            if date_range and item.get("published_at"):
                published_date = item["published_at"][:10]
                if not (date_range[0] <= published_date <= date_range[1]):
                    continue
            filtered.append(item)
        filtered.sort(key=lambda item: item.get("published_at") or "", reverse=True)
        return filtered

    @staticmethod
    def _normalize(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(record["id"]),
            "source": record["source"],
            "doc_type": record["doc_type"],
            "title": record["title"],
            "url": record.get("url"),
            "file_path": record.get("file_path"),
            "content_hash": record.get("content_hash"),
            "company_code": record.get("company_code"),
            "published_at": _to_iso(record.get("published_at")),
            "ingested_at": _to_iso(record.get("ingested_at")),
            "is_indexed": bool(record.get("is_indexed", False)),
            "is_duplicate": bool(record.get("is_duplicate", False)),
        }
