from fastapi.testclient import TestClient

from services.ingestion import service
from services.ingestion.main import app as ingestion_app
from services.ingestion.state import IngestionTaskRepository


def test_resolve_sources_includes_new_source_groups():
    assert service._resolve_sources("all_news") == ["eastmoney_news", "10jqka", "sina"]
    assert service._resolve_sources("all_announcements") == ["announcement", "sse", "szse"]
    assert service._resolve_sources("all") == [
        "eastmoney_news",
        "10jqka",
        "sina",
        "announcement",
        "sse",
        "szse",
    ]


def test_target_pool_sync_endpoint_queues_incremental_job():
    client = TestClient(ingestion_app)
    response = client.post("/api/v1/ingest/target-pool/sync", json={"source": "all_news"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["status"] == "queued"
    assert payload["data"]["target_pool"] is True
    assert payload["data"]["incremental"] is True
    assert payload["data"]["task_name"] == "target_pool_incremental_sync"


def test_run_job_records_incremental_task_state(tmp_path, monkeypatch):
    task_repo = IngestionTaskRepository(tmp_path / "ingestion_tasks_manifest.json")
    monkeypatch.setattr(service, "_TASK_REPO", task_repo)
    monkeypatch.setattr(service, "_persist_article", lambda article: True)

    captured = []

    def fake_fetch_documents(source, stock_codes, *, date_from=None, date_to=None, per_stock_limit=3):
        captured.append((source, tuple(stock_codes), date_from, date_to, per_stock_limit))
        return [
            {
                "source": source if source != "eastmoney_news" else "eastmoney",
                "doc_type": "announcement" if source in {"announcement", "sse", "szse"} else "news",
                "title": f"{source} sample",
                "url": f"https://example.com/{source}",
                "published_at": date_to or "2026-04-06",
                "company_code": "600519",
                "content": "sample content",
                "metadata": {"matched_stocks": [{"code": "600519", "name": "贵州茅台"}]},
            }
        ]

    monkeypatch.setattr(service.providers, "fetch_documents", fake_fetch_documents)

    service._run_job(
        job_id="job-test-1",
        source="all_announcements",
        date_str="2026-04-06",
        stock_codes=["600519"],
        target_pool=False,
        incremental=True,
        lookback_days=2,
        per_stock_limit=2,
        task_name="target_pool_incremental_sync",
    )

    tasks = task_repo.list_tasks()
    assert len(tasks) == 1
    task = tasks[0]
    assert task["task_name"] == "target_pool_incremental_sync"
    assert set(task["sources"].keys()) == {"announcement", "sse", "szse"}
    assert task["sources"]["announcement"]["docs_collected"] == 1
    assert all(item[1] == ("600519",) for item in captured)
    assert all(item[4] == 2 for item in captured)
