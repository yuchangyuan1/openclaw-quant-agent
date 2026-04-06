"""Chroma client wrapper with deterministic local embeddings for MVP."""

from __future__ import annotations

from pathlib import Path

import chromadb

from services.common.text import hashed_embedding, stable_uuid

from . import config

_LAST_STATUS = {
    "backend": "unknown",
    "error": None,
}


def get_client():
    last_error: Exception | None = None
    try:
        client = chromadb.HttpClient(host=config.CHROMA_HOST, port=config.CHROMA_PORT)
        client.heartbeat()
        _set_status("http", None)
        return client
    except Exception as exc:
        last_error = exc

    try:
        persist_dir = Path(config.CHROMA_PERSIST_DIR)
        persist_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(persist_dir))
        client.heartbeat()
        _set_status("persistent", f"http_unavailable: {last_error}" if last_error else None)
        return client
    except Exception as exc:
        _set_status("unavailable", str(exc if last_error is None else last_error))
        raise


def get_or_create_collection(name: str = config.COLLECTION_NAME):
    client = get_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def embed(texts: list[str]) -> list[list[float]]:
    return [hashed_embedding(text, config.EMBEDDING_DIM) for text in texts]


def get_status() -> dict[str, str | None]:
    return dict(_LAST_STATUS)


def upsert_documents(docs: list[dict], collection_name: str = config.COLLECTION_NAME) -> tuple[bool, str | None]:
    if not docs:
        return True, None
    try:
        collection = get_or_create_collection(collection_name)
        ids = [doc["id"] for doc in docs]
        metadatas = [
            {key: value for key, value in doc.get("metadata", {}).items() if value is not None}
            for doc in docs
        ]
        collection.delete(ids=ids)
        collection.add(
            ids=ids,
            embeddings=embed([doc["text"] for doc in docs]),
            documents=[doc["text"] for doc in docs],
            metadatas=metadatas,
        )
        return True, None
    except Exception as exc:
        _set_status(_LAST_STATUS["backend"], str(exc))
        return False, str(exc)


def delete_doc_ids(doc_ids: list[str], collection_name: str = config.COLLECTION_NAME) -> None:
    if not doc_ids:
        return
    try:
        collection = get_or_create_collection(collection_name)
        existing = collection.get(include=["metadatas"])
        to_delete = []
        for idx, metadata in enumerate(existing.get("metadatas", [])):
            if metadata.get("doc_id") in doc_ids:
                to_delete.append(existing["ids"][idx])
        if to_delete:
            collection.delete(ids=to_delete)
    except Exception:
        return


def insert_test_document(collection_name: str = "verify_stack_test") -> str:
    """Verification helper: write one test document and return its id."""
    client = get_client()
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(collection_name)
    test_id = stable_uuid(collection_name)
    collection.add(
        ids=[test_id],
        embeddings=[[0.1] * config.EMBEDDING_DIM],
        documents=["RAG service connectivity verification document"],
        metadatas=[{"source": "verify_stack", "date": "2026-04-07"}],
    )
    return test_id


def query(
    query_text: str,
    top_k: int = config.TOP_K_DEFAULT,
    collection_name: str = config.COLLECTION_NAME,
    where: dict | None = None,
) -> list[dict]:
    try:
        collection = get_or_create_collection(collection_name)
        query_embedding = embed([query_text])[0]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
        )
    except Exception as exc:
        _set_status(_LAST_STATUS["backend"], str(exc))
        return []
    items = []
    for i, doc_id in enumerate(results["ids"][0]):
        items.append(
            {
                "id": doc_id,
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            }
        )
    return items


def _set_status(backend: str, error: str | None) -> None:
    _LAST_STATUS["backend"] = backend
    _LAST_STATUS["error"] = error
