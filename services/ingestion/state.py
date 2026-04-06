from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from services.common.paths import metadata_dir


def _today_iso() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


class IngestionTaskRepository:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (metadata_dir() / "ingestion_tasks_manifest.json")

    def list_tasks(self) -> list[dict[str, Any]]:
        payload = self._load()
        tasks = list(payload["tasks"].values())
        tasks.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return tasks

    def get_task(self, task_name: str) -> dict[str, Any] | None:
        return self._load()["tasks"].get(task_name)

    def resolve_window(
        self,
        *,
        task_name: str,
        source: str,
        explicit_date: str | None,
        incremental: bool,
        lookback_days: int,
        overlap_days: int = 1,
    ) -> tuple[str | None, str]:
        end_date = explicit_date or _today_iso()
        if not incremental:
            return explicit_date, end_date

        task = self.get_task(task_name) or {}
        last_success_date = ((task.get("sources") or {}).get(source) or {}).get("last_success_date")
        if last_success_date:
            start_date = (
                datetime.fromisoformat(last_success_date).date() - timedelta(days=overlap_days)
            ).isoformat()
        else:
            start_date = (date.fromisoformat(end_date) - timedelta(days=lookback_days - 1)).isoformat()
        return start_date, end_date

    def record_run(
        self,
        *,
        task_name: str,
        job_id: str,
        source: str,
        status: str,
        date_from: str | None,
        date_to: str | None,
        docs_collected: int,
        docs_failed: int,
        stock_codes: list[str],
        target_pool: bool,
        incremental: bool,
    ) -> None:
        payload = self._load()
        tasks = payload["tasks"]
        task = tasks.get(task_name) or {
            "task_name": task_name,
            "created_at": _now_iso(),
            "sources": {},
        }
        task.update(
            {
                "updated_at": _now_iso(),
                "last_job_id": job_id,
                "last_status": status,
                "last_run_at": _now_iso(),
                "target_pool": target_pool,
                "incremental": incremental,
                "stock_codes": stock_codes,
            }
        )
        task_sources = task.setdefault("sources", {})
        task_sources[source] = {
            "last_job_id": job_id,
            "last_status": status,
            "last_requested_from": date_from,
            "last_requested_to": date_to,
            "last_run_at": _now_iso(),
            "docs_collected": docs_collected,
            "docs_failed": docs_failed,
            "last_success_date": date_to if status == "completed" else task_sources.get(source, {}).get("last_success_date"),
            "last_success_at": _now_iso() if status == "completed" else task_sources.get(source, {}).get("last_success_at"),
        }
        tasks[task_name] = task
        self._save(payload)

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"tasks": {}}
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        payload.setdefault("tasks", {})
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
