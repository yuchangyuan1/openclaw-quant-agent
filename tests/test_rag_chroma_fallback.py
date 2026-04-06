from services.rag import chroma_client
from services.rag import service as rag_service


class _FakeClient:
    def heartbeat(self):
        return "ok"

    def get_or_create_collection(self, name, metadata=None):
        return _FakeCollection()


class _FakeCollection:
    def delete(self, ids=None):
        return None

    def add(self, ids=None, embeddings=None, documents=None, metadatas=None):
        return None

    def query(self, query_embeddings=None, n_results=None, where=None):
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


def test_chroma_client_falls_back_to_persistent(monkeypatch, tmp_path):
    monkeypatch.setattr(chroma_client.config, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))

    def fail_http(*args, **kwargs):
        raise ValueError("http unavailable")

    persistent_calls = []

    def fake_persistent(*args, **kwargs):
        persistent_calls.append(kwargs.get("path") or (args[0] if args else None))
        return _FakeClient()

    monkeypatch.setattr(chroma_client.chromadb, "HttpClient", fail_http)
    monkeypatch.setattr(chroma_client.chromadb, "PersistentClient", fake_persistent)

    collection = chroma_client.get_or_create_collection("test_collection")

    assert isinstance(collection, _FakeCollection)
    assert persistent_calls
    assert chroma_client.get_status()["backend"] == "persistent"


def test_build_index_reports_vector_backend(monkeypatch):
    monkeypatch.setattr(
        rag_service._REPO,
        "get_documents",
        lambda **kwargs: [
            {
                "id": "doc-1",
                "source": "eastmoney",
                "doc_type": "announcement",
                "title": "测试公告",
                "url": "https://example.com/doc-1",
                "file_path": "",
                "company_code": "600519",
                "published_at": "2026-04-06",
                "is_indexed": False,
            }
        ],
    )
    monkeypatch.setattr(rag_service, "_load_raw", lambda document: {"content": "测试内容", "metadata": {}})
    monkeypatch.setattr(rag_service._GRAPH_REPO, "sync_document_graph", lambda document, raw: {"entities": 1, "relations": 1})
    monkeypatch.setattr(rag_service.chroma_client, "upsert_documents", lambda docs: (True, None))
    monkeypatch.setattr(rag_service.chroma_client, "get_status", lambda: {"backend": "persistent", "error": None})
    marked = []
    monkeypatch.setattr(rag_service._REPO, "mark_indexed", lambda doc_ids: marked.extend(doc_ids))

    payload = rag_service.build_index([], False)

    assert payload["status"] == "completed"
    assert payload["vector_backend"] == "persistent"
    assert payload["indexed_docs"] == 1
    assert marked == ["doc-1"]
