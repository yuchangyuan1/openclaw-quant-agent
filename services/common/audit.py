from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg2.extras import Json, RealDictCursor

from .paths import metadata_dir
from .repository import _connect


def _manifest_path() -> Path:
    override = os.getenv("RUN_LOG_MANIFEST_PATH")
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            path = (metadata_dir() / path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return metadata_dir() / "run_logs_manifest.json"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_manifest() -> list[dict[str, Any]]:
    path = _manifest_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manifest(items: list[dict[str, Any]]) -> None:
    path = _manifest_path()
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


class RunLogRepository:
    def __init__(self) -> None:
        self._backend = "manifest"
        self._checked_backend = False

    def backend(self) -> str:
        if not self._checked_backend:
            self._probe_backend()
        return self._backend

    def start_run(self, job_id: str, job_type: str, input_params: dict[str, Any]) -> dict[str, Any]:
        if self.backend() == "postgres":
            return self._start_postgres(job_id, job_type, input_params)
        return self._start_manifest(job_id, job_type, input_params)

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        output_summary: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        if self.backend() == "postgres":
            return self._finish_postgres(run_id, status=status, output_summary=output_summary, error_message=error_message)
        return self._finish_manifest(run_id, status=status, output_summary=output_summary, error_message=error_message)

    def list_runs(self, *, limit: int = 20, job_type: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        if self.backend() == "postgres":
            return self._list_postgres(limit=limit, job_type=job_type, status=status)
        return self._list_manifest(limit=limit, job_type=job_type, status=status)

    def get_run(self, run_id: str) -> dict[str, Any]:
        if self.backend() == "postgres":
            return self._get_postgres(run_id)
        return self._get_manifest(run_id)

    def _probe_backend(self) -> None:
        if os.getenv("RUN_LOG_MANIFEST_PATH"):
            self._backend = "manifest"
            self._checked_backend = True
            return
        try:
            with _connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
            self._backend = "postgres"
        except Exception:
            self._backend = "manifest"
        self._checked_backend = True

    def _start_postgres(self, job_id: str, job_type: str, input_params: dict[str, Any]) -> dict[str, Any]:
        with _connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                run_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO run_logs (id, job_id, job_type, status, input_params, started_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    RETURNING id, job_id, job_type, status, input_params, output_summary, error_message,
                              started_at, finished_at, duration_seconds
                    """,
                    (run_id, job_id, job_type, "running", Json(input_params)),
                )
                item = cursor.fetchone()
            conn.commit()
        return self._normalize(item)

    def _finish_postgres(
        self,
        run_id: str,
        *,
        status: str,
        output_summary: dict[str, Any] | None,
        error_message: str | None,
    ) -> dict[str, Any]:
        with _connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    UPDATE run_logs
                    SET status = %s,
                        output_summary = %s,
                        error_message = %s,
                        finished_at = NOW()
                    WHERE id = %s
                    RETURNING id, job_id, job_type, status, input_params, output_summary, error_message,
                              started_at, finished_at, duration_seconds
                    """,
                    (status, Json(output_summary) if output_summary is not None else None, error_message, run_id),
                )
                item = cursor.fetchone()
            conn.commit()
        return self._normalize(item)

    def _list_postgres(self, *, limit: int, job_type: str | None, status: str | None) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []
        if job_type:
            conditions.append("job_type = %s")
            params.append(job_type)
        if status:
            conditions.append("status = %s")
            params.append(status)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with _connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f"""
                    SELECT id, job_id, job_type, status, input_params, output_summary, error_message,
                           started_at, finished_at, duration_seconds
                    FROM run_logs
                    {where_sql}
                    ORDER BY started_at DESC
                    LIMIT %s
                    """,
                    [*params, limit],
                )
                return [self._normalize(item) for item in cursor.fetchall()]

    def _get_postgres(self, run_id: str) -> dict[str, Any]:
        with _connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT id, job_id, job_type, status, input_params, output_summary, error_message,
                           started_at, finished_at, duration_seconds
                    FROM run_logs
                    WHERE id = %s
                    """,
                    (run_id,),
                )
                item = cursor.fetchone()
        return self._normalize(item)

    def _start_manifest(self, job_id: str, job_type: str, input_params: dict[str, Any]) -> dict[str, Any]:
        items = _load_manifest()
        record = {
            "id": str(uuid.uuid4()),
            "job_id": job_id,
            "job_type": job_type,
            "status": "running",
            "input_params": input_params,
            "output_summary": None,
            "error_message": None,
            "started_at": _now_iso(),
            "finished_at": None,
            "duration_seconds": None,
        }
        items.append(record)
        items.sort(key=lambda item: item["started_at"], reverse=True)
        _save_manifest(items)
        return record

    def _finish_manifest(
        self,
        run_id: str,
        *,
        status: str,
        output_summary: dict[str, Any] | None,
        error_message: str | None,
    ) -> dict[str, Any]:
        items = _load_manifest()
        finished_at = _now_iso()
        for item in items:
            if item["id"] != run_id:
                continue
            item["status"] = status
            item["output_summary"] = output_summary
            item["error_message"] = error_message
            item["finished_at"] = finished_at
            try:
                started = datetime.fromisoformat(item["started_at"])
                finished = datetime.fromisoformat(finished_at)
                item["duration_seconds"] = max(0, int((finished - started).total_seconds()))
            except ValueError:
                item["duration_seconds"] = None
            _save_manifest(items)
            return item
        raise KeyError(f"Run log not found: {run_id}")

    def _list_manifest(self, *, limit: int, job_type: str | None, status: str | None) -> list[dict[str, Any]]:
        items = _load_manifest()
        filtered = []
        for item in items:
            if job_type and item.get("job_type") != job_type:
                continue
            if status and item.get("status") != status:
                continue
            filtered.append(item)
        filtered.sort(key=lambda item: item.get("started_at") or "", reverse=True)
        return filtered[:limit]

    def _get_manifest(self, run_id: str) -> dict[str, Any]:
        for item in _load_manifest():
            if item.get("id") == run_id:
                return self._normalize(item)
        raise KeyError(f"Run log not found: {run_id}")

    @staticmethod
    def _normalize(record: dict[str, Any] | None) -> dict[str, Any]:
        if not record:
            raise KeyError("Run log record not found")
        return {
            "id": str(record["id"]),
            "job_id": record.get("job_id"),
            "job_type": record.get("job_type"),
            "status": record.get("status"),
            "input_params": record.get("input_params") or {},
            "output_summary": record.get("output_summary"),
            "error_message": record.get("error_message"),
            "started_at": str(record.get("started_at")) if record.get("started_at") else None,
            "finished_at": str(record.get("finished_at")) if record.get("finished_at") else None,
            "duration_seconds": record.get("duration_seconds"),
        }
