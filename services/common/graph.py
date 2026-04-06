from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg2.extras import Json, RealDictCursor

from .repository import _connect, _load_manifest
from .stocks import build_company_aliases, load_target_stocks, normalize_company_term
from .text import stable_uuid


_ZERO_UUID = "00000000-0000-0000-0000-000000000000"


class GraphRepository:
    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = manifest_path
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

    def get_unsynced_document_ids(self, limit: int = 200) -> list[str]:
        if self.backend() == "postgres":
            with _connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT d.id::text
                        FROM documents d
                        LEFT JOIN document_entities de ON de.document_id = d.id
                        GROUP BY d.id, d.published_at, d.ingested_at
                        HAVING COUNT(de.id) = 0
                        ORDER BY MAX(d.published_at) DESC NULLS LAST, MAX(d.ingested_at) DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    return [row[0] for row in cursor.fetchall()]

        synced_doc_ids = {item["document_id"] for item in self._load_manifest()["document_entities"]}
        pending: list[str] = []
        for item in _load_manifest():
            if item["id"] not in synced_doc_ids:
                pending.append(item["id"])
            if len(pending) >= limit:
                break
        return pending

    def sync_document_graph(self, document: dict[str, Any], raw: dict[str, Any]) -> dict[str, int]:
        graph = extract_document_graph(document, raw)
        if self.backend() == "postgres":
            return self._sync_postgres(document, graph)
        return self._sync_manifest(document, graph)

    def get_graph_context(
        self,
        *,
        doc_ids: list[str] | None = None,
        stock_codes: list[str] | None = None,
        company_terms: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        if self.backend() == "postgres":
            return self._context_postgres(doc_ids or [], stock_codes or [], company_terms or [], limit)
        return self._context_manifest(doc_ids or [], stock_codes or [], company_terms or [], limit)

    def save_metric_snapshot(
        self,
        *,
        entity_key: str,
        entity_name: str,
        metric_name: str,
        metric_value: float | int | None,
        metric_date: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if metric_value is None:
            return
        if self.backend() == "postgres":
            self._save_metric_snapshot_postgres(
                entity_key=entity_key,
                entity_name=entity_name,
                metric_name=metric_name,
                metric_value=float(metric_value),
                metric_date=metric_date,
                source=source,
                metadata=metadata or {},
            )
            return
        self._save_metric_snapshot_manifest(
            entity_key=entity_key,
            entity_name=entity_name,
            metric_name=metric_name,
            metric_value=float(metric_value),
            metric_date=metric_date,
            source=source,
            metadata=metadata or {},
        )

    def save_risk_snapshot(
        self,
        *,
        entity_key: str,
        entity_name: str,
        risk_type: str,
        risk_level: str,
        risk_value: float | int | None,
        risk_date: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.backend() == "postgres":
            self._save_risk_snapshot_postgres(
                entity_key=entity_key,
                entity_name=entity_name,
                risk_type=risk_type,
                risk_level=risk_level,
                risk_value=None if risk_value is None else float(risk_value),
                risk_date=risk_date,
                source=source,
                metadata=metadata or {},
            )
            return
        self._save_risk_snapshot_manifest(
            entity_key=entity_key,
            entity_name=entity_name,
            risk_type=risk_type,
            risk_level=risk_level,
            risk_value=None if risk_value is None else float(risk_value),
            risk_date=risk_date,
            source=source,
            metadata=metadata or {},
        )

    def _sync_postgres(self, document: dict[str, Any], graph: dict[str, Any]) -> dict[str, int]:
        with _connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                entity_ids: dict[tuple[str, str], str] = {}
                for entity in [graph["document_entity"], *graph["entities"]]:
                    entity_ids[(entity["entity_type"], entity["entity_key"])] = self._upsert_entity(cursor, entity)

                cursor.execute("DELETE FROM document_entities WHERE document_id = %s", (document["id"],))
                cursor.execute("DELETE FROM relations WHERE source_doc_id = %s", (document["id"],))

                for mapping in graph["document_entities"]:
                    cursor.execute(
                        """
                        INSERT INTO document_entities (
                            id, document_id, entity_id, mention_text, mention_type, confidence
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (document_id, entity_id, mention_type) DO UPDATE SET
                            mention_text = EXCLUDED.mention_text,
                            confidence = EXCLUDED.confidence
                        """,
                        (
                            stable_uuid(
                                f"{document['id']}|{mapping['entity_type']}|{mapping['entity_key']}|{mapping['mention_type']}"
                            ),
                            document["id"],
                            entity_ids[(mapping["entity_type"], mapping["entity_key"])],
                            mapping.get("mention_text"),
                            mapping.get("mention_type", "extracted"),
                            mapping.get("confidence", 1.0),
                        ),
                    )

                for relation in graph["relations"]:
                    cursor.execute(
                        """
                        INSERT INTO relations (
                            id, src_entity_id, relation_type, dst_entity_id, weight, confidence,
                            source_doc_id, metadata_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            stable_uuid(
                                "|".join(
                                    [
                                        relation["src_type"],
                                        relation["src_key"],
                                        relation["relation_type"],
                                        relation["dst_type"],
                                        relation["dst_key"],
                                        relation.get("source_doc_id") or _ZERO_UUID,
                                    ]
                                )
                            ),
                            entity_ids[(relation["src_type"], relation["src_key"])],
                            relation["relation_type"],
                            entity_ids[(relation["dst_type"], relation["dst_key"])],
                            relation.get("weight", 1.0),
                            relation.get("confidence", 1.0),
                            relation.get("source_doc_id"),
                            Json(relation.get("metadata", {})),
                        ),
                    )
            conn.commit()
        return {
            "entities": len(graph["entities"]) + 1,
            "relations": len(graph["relations"]),
            "document_entities": len(graph["document_entities"]),
        }

    def _upsert_entity(self, cursor, entity: dict[str, Any]) -> str:
        cursor.execute(
            """
            INSERT INTO entities (
                id, entity_type, entity_key, name, alias_json, metadata_json, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (entity_type, entity_key) DO UPDATE SET
                name = EXCLUDED.name,
                alias_json = EXCLUDED.alias_json,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = NOW()
            RETURNING id::text
            """,
            (
                stable_uuid(f"{entity['entity_type']}|{entity['entity_key']}"),
                entity["entity_type"],
                entity["entity_key"],
                entity["name"],
                Json(entity.get("aliases", [])),
                Json(entity.get("metadata", {})),
            ),
        )
        row = cursor.fetchone()
        return row["id"] if isinstance(row, dict) else row[0]

    def _sync_manifest(self, document: dict[str, Any], graph: dict[str, Any]) -> dict[str, int]:
        state = self._load_manifest()
        entity_map = {(item["entity_type"], item["entity_key"]): item for item in state["entities"]}
        for entity in [graph["document_entity"], *graph["entities"]]:
            entity_map[(entity["entity_type"], entity["entity_key"])] = {
                "id": stable_uuid(f"{entity['entity_type']}|{entity['entity_key']}"),
                "entity_type": entity["entity_type"],
                "entity_key": entity["entity_key"],
                "name": entity["name"],
                "aliases": entity.get("aliases", []),
                "metadata": entity.get("metadata", {}),
                "updated_at": datetime.now().isoformat(),
            }
        state["entities"] = list(entity_map.values())
        state["document_entities"] = [item for item in state["document_entities"] if item["document_id"] != document["id"]]
        state["relations"] = [item for item in state["relations"] if item.get("source_doc_id") != document["id"]]

        for mapping in graph["document_entities"]:
            state["document_entities"].append(
                {
                    "id": stable_uuid(
                        f"{document['id']}|{mapping['entity_type']}|{mapping['entity_key']}|{mapping['mention_type']}"
                    ),
                    "document_id": document["id"],
                    **mapping,
                }
            )
        for relation in graph["relations"]:
            state["relations"].append(
                {
                    "id": stable_uuid(
                        "|".join(
                            [
                                relation["src_type"],
                                relation["src_key"],
                                relation["relation_type"],
                                relation["dst_type"],
                                relation["dst_key"],
                                relation.get("source_doc_id") or _ZERO_UUID,
                            ]
                        )
                    ),
                    **relation,
                }
            )
        self._save_manifest(state)
        return {
            "entities": len(graph["entities"]) + 1,
            "relations": len(graph["relations"]),
            "document_entities": len(graph["document_entities"]),
        }

    def _context_postgres(
        self,
        doc_ids: list[str],
        stock_codes: list[str],
        company_terms: list[str],
        limit: int,
    ) -> dict[str, Any]:
        with _connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                doc_entities = []
                if doc_ids:
                    cursor.execute(
                        """
                        SELECT
                            e.id::text AS id,
                            e.entity_type,
                            e.entity_key,
                            e.name,
                            e.metadata_json,
                            de.document_id::text AS document_id,
                            de.confidence
                        FROM document_entities de
                        JOIN entities e ON e.id = de.entity_id
                        WHERE de.document_id::text = ANY(%s)
                        ORDER BY de.confidence DESC, e.name
                        """,
                        (doc_ids,),
                    )
                    doc_entities = [dict(item) for item in cursor.fetchall()]

                conditions = []
                params: list[Any] = []
                if stock_codes:
                    conditions.append("(entity_type = 'company' AND entity_key = ANY(%s))")
                    params.append(stock_codes)
                normalized_terms = [normalize_company_term(item).lower() for item in company_terms if item]
                if normalized_terms:
                    conditions.append(
                        "(lower(name) = ANY(%s) OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(alias_json) alias WHERE lower(alias) = ANY(%s)))"
                    )
                    params.extend([normalized_terms, normalized_terms])
                focus_entities = []
                if conditions:
                    cursor.execute(
                        f"""
                        SELECT id::text AS id, entity_type, entity_key, name, metadata_json
                        FROM entities
                        WHERE {' OR '.join(conditions)}
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                        [*params, limit],
                    )
                    focus_entities = [dict(item) for item in cursor.fetchall()]

                relations = []
                focus_entity_ids = [item["id"] for item in focus_entities]
                relation_conditions = []
                relation_params: list[Any] = []
                if doc_ids:
                    relation_conditions.append("r.source_doc_id::text = ANY(%s)")
                    relation_params.append(doc_ids)
                if focus_entity_ids:
                    relation_conditions.append("(src.id::text = ANY(%s) OR dst.id::text = ANY(%s))")
                    relation_params.extend([focus_entity_ids, focus_entity_ids])
                if relation_conditions:
                    cursor.execute(
                        f"""
                        SELECT
                            src.name AS src_name,
                            src.entity_type AS src_type,
                            r.relation_type,
                            dst.name AS dst_name,
                            dst.entity_type AS dst_type,
                            r.source_doc_id::text AS source_doc_id,
                            r.confidence
                        FROM relations r
                        JOIN entities src ON src.id = r.src_entity_id
                        JOIN entities dst ON dst.id = r.dst_entity_id
                        WHERE {' OR '.join(relation_conditions)}
                        ORDER BY r.confidence DESC, r.weight DESC, r.created_at DESC
                        LIMIT %s
                        """,
                        [*relation_params, limit],
                    )
                    relations = [dict(item) for item in cursor.fetchall()]

        return build_graph_context_payload(doc_entities, focus_entities, relations)

    def _context_manifest(
        self,
        doc_ids: list[str],
        stock_codes: list[str],
        company_terms: list[str],
        limit: int,
    ) -> dict[str, Any]:
        state = self._load_manifest()
        entity_map = {(item["entity_type"], item["entity_key"]): item for item in state["entities"]}
        normalized_terms = {normalize_company_term(item).lower() for item in company_terms if item}
        doc_entities = []
        for item in state["document_entities"]:
            if doc_ids and item["document_id"] not in doc_ids:
                continue
            entity = entity_map.get((item["entity_type"], item["entity_key"]))
            if not entity:
                continue
            doc_entities.append(
                {
                    "id": entity["id"],
                    "entity_type": entity["entity_type"],
                    "entity_key": entity["entity_key"],
                    "name": entity["name"],
                    "metadata_json": entity.get("metadata", {}),
                    "document_id": item["document_id"],
                    "confidence": item.get("confidence", 1.0),
                }
            )

        focus_entities = []
        for entity in state["entities"]:
            aliases = [normalize_company_term(item).lower() for item in entity.get("aliases", [])]
            if entity["entity_type"] == "company" and entity["entity_key"] in stock_codes:
                focus_entities.append(
                    {
                        "id": entity["id"],
                        "entity_type": entity["entity_type"],
                        "entity_key": entity["entity_key"],
                        "name": entity["name"],
                        "metadata_json": entity.get("metadata", {}),
                    }
                )
            elif normalized_terms and (
                normalize_company_term(entity["name"]).lower() in normalized_terms or set(aliases) & normalized_terms
            ):
                focus_entities.append(
                    {
                        "id": entity["id"],
                        "entity_type": entity["entity_type"],
                        "entity_key": entity["entity_key"],
                        "name": entity["name"],
                        "metadata_json": entity.get("metadata", {}),
                    }
                )

        focus_names = {item["name"] for item in focus_entities}
        relations = []
        for item in state["relations"]:
            src = entity_map.get((item["src_type"], item["src_key"]))
            dst = entity_map.get((item["dst_type"], item["dst_key"]))
            if not src or not dst:
                continue
            if doc_ids and item.get("source_doc_id") not in doc_ids and src["name"] not in focus_names and dst["name"] not in focus_names:
                continue
            relations.append(
                {
                    "src_name": src["name"],
                    "src_type": src["entity_type"],
                    "relation_type": item["relation_type"],
                    "dst_name": dst["name"],
                    "dst_type": dst["entity_type"],
                    "source_doc_id": item.get("source_doc_id"),
                    "confidence": item.get("confidence", 1.0),
                }
            )

        return build_graph_context_payload(doc_entities[:limit], focus_entities[:limit], relations[:limit])

    def _save_metric_snapshot_postgres(self, **payload) -> None:
        with _connect() as conn:
            with conn.cursor() as cursor:
                entity_id = self._ensure_company_entity(cursor, payload["entity_key"], payload["entity_name"])
                cursor.execute(
                    """
                    INSERT INTO entity_metric_snapshots (
                        id, entity_id, metric_name, metric_value, metric_date, source, metadata_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (entity_id, metric_name, metric_date, source) DO UPDATE SET
                        metric_value = EXCLUDED.metric_value,
                        metadata_json = EXCLUDED.metadata_json
                    """,
                    (
                        stable_uuid(
                            f"{payload['entity_key']}|{payload['metric_name']}|{payload['metric_date']}|{payload['source']}"
                        ),
                        entity_id,
                        payload["metric_name"],
                        payload["metric_value"],
                        payload["metric_date"],
                        payload["source"],
                        Json(payload["metadata"]),
                    ),
                )
            conn.commit()

    def _save_metric_snapshot_manifest(self, **payload) -> None:
        state = self._load_manifest()
        item_id = stable_uuid(
            f"{payload['entity_key']}|{payload['metric_name']}|{payload['metric_date']}|{payload['source']}"
        )
        items = {
            item["id"]: item
            for item in state["metric_snapshots"]
        }
        items[item_id] = {"id": item_id, **payload}
        state["metric_snapshots"] = list(items.values())
        self._save_manifest(state)

    def _save_risk_snapshot_postgres(self, **payload) -> None:
        with _connect() as conn:
            with conn.cursor() as cursor:
                entity_id = self._ensure_company_entity(cursor, payload["entity_key"], payload["entity_name"])
                cursor.execute(
                    """
                    INSERT INTO entity_risk_snapshots (
                        id, entity_id, risk_type, risk_level, risk_value, risk_date, source, metadata_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (entity_id, risk_type, risk_date, source) DO UPDATE SET
                        risk_level = EXCLUDED.risk_level,
                        risk_value = EXCLUDED.risk_value,
                        metadata_json = EXCLUDED.metadata_json
                    """,
                    (
                        stable_uuid(
                            f"{payload['entity_key']}|{payload['risk_type']}|{payload['risk_date']}|{payload['source']}"
                        ),
                        entity_id,
                        payload["risk_type"],
                        payload["risk_level"],
                        payload["risk_value"],
                        payload["risk_date"],
                        payload["source"],
                        Json(payload["metadata"]),
                    ),
                )
            conn.commit()

    def _save_risk_snapshot_manifest(self, **payload) -> None:
        state = self._load_manifest()
        item_id = stable_uuid(
            f"{payload['entity_key']}|{payload['risk_type']}|{payload['risk_date']}|{payload['source']}"
        )
        items = {
            item["id"]: item
            for item in state["risk_snapshots"]
        }
        items[item_id] = {"id": item_id, **payload}
        state["risk_snapshots"] = list(items.values())
        self._save_manifest(state)

    def _ensure_company_entity(self, cursor, entity_key: str, entity_name: str) -> str:
        stock_item = load_target_stocks().get(entity_key, {})
        return self._upsert_entity(
            cursor,
            {
                "entity_type": "company",
                "entity_key": entity_key,
                "name": entity_name,
                "aliases": build_company_aliases(entity_name),
                "metadata": {"industry": stock_item.get("industry")},
            },
        )

    def _load_manifest(self) -> dict[str, Any]:
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._manifest_path.exists():
            return {
                "entities": [],
                "relations": [],
                "document_entities": [],
                "metric_snapshots": [],
                "risk_snapshots": [],
            }
        state = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        state.setdefault("entities", [])
        state.setdefault("relations", [])
        state.setdefault("document_entities", [])
        state.setdefault("metric_snapshots", [])
        state.setdefault("risk_snapshots", [])
        return state

    def _save_manifest(self, state: dict[str, Any]) -> None:
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._manifest_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_document_graph(document: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    metadata = raw.get("metadata", {})
    stocks = load_target_stocks()
    entities: list[dict[str, Any]] = []
    document_entities: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    seen_entities: set[tuple[str, str]] = set()

    document_entity = {
        "entity_type": document["doc_type"],
        "entity_key": document["id"],
        "name": document["title"],
        "aliases": [],
        "metadata": {
            "source": document["source"],
            "url": document.get("url"),
            "published_at": document.get("published_at"),
        },
    }

    def add_entity(entity_type: str, entity_key: str, name: str, aliases: list[str], metadata_payload: dict[str, Any]) -> None:
        key = (entity_type, entity_key)
        if key in seen_entities:
            return
        entities.append(
            {
                "entity_type": entity_type,
                "entity_key": entity_key,
                "name": name,
                "aliases": aliases,
                "metadata": metadata_payload,
            }
        )
        seen_entities.add(key)

    def add_document_entity(entity_type: str, entity_key: str, mention_text: str, mention_type: str) -> None:
        document_entities.append(
            {
                "entity_type": entity_type,
                "entity_key": entity_key,
                "mention_text": mention_text,
                "mention_type": mention_type,
                "confidence": 1.0,
            }
        )

    def add_relation(src_type: str, src_key: str, relation_type: str, dst_type: str, dst_key: str, source_doc_id: str | None) -> None:
        relations.append(
            {
                "src_type": src_type,
                "src_key": src_key,
                "relation_type": relation_type,
                "dst_type": dst_type,
                "dst_key": dst_key,
                "weight": 1.0,
                "confidence": 1.0,
                "source_doc_id": source_doc_id,
                "metadata": {},
            }
        )

    matched_stocks = metadata.get("matched_stocks", [])
    company_pairs: list[tuple[str, str]] = []
    for item in matched_stocks:
        code = str(item.get("code") if isinstance(item, dict) else item).strip()
        name = str(item.get("name") if isinstance(item, dict) else stocks.get(code, {}).get("name") or code).strip()
        if code:
            company_pairs.append((code, name))
    if document.get("company_code") and all(code != document["company_code"] for code, _ in company_pairs):
        company_pairs.insert(0, (document["company_code"], str(stocks.get(document["company_code"], {}).get("name") or document["company_code"])))

    for code, name in company_pairs:
        stock_item = stocks.get(code, {})
        add_entity("company", code, name, build_company_aliases(name), {"industry": stock_item.get("industry")})
        add_document_entity("company", code, name, "matched_stock")
        add_relation("company", code, "announced_in" if document["doc_type"] == "announcement" else "mentioned_in", document["doc_type"], document["id"], document["id"])
        if stock_item.get("industry"):
            industry = str(stock_item["industry"])
            industry_key = normalize_company_term(industry) or industry
            add_entity("industry", industry_key, industry, [industry], {})
            add_document_entity("industry", industry_key, industry, "stock_industry")
            add_relation("company", code, "belongs_to_industry", "industry", industry_key, None)

    for theme in metadata.get("matched_themes", []):
        theme_name = str(theme).strip()
        if not theme_name:
            continue
        theme_key = normalize_company_term(theme_name) or theme_name
        add_entity("theme", theme_key, theme_name, [theme_name], {})
        add_document_entity("theme", theme_key, theme_name, "matched_theme")
        add_relation("theme", theme_key, "mentioned_in", document["doc_type"], document["id"], document["id"])
        for code, _name in company_pairs:
            add_relation("company", code, "has_theme", "theme", theme_key, document["id"])

    for term in metadata.get("company_terms", []):
        normalized = normalize_company_term(str(term))
        if not normalized or any(normalized == normalize_company_term(name) for _code, name in company_pairs):
            continue
        term_key = f"term:{normalized}"
        add_entity("company_term", term_key, str(term), [normalized], {})
        add_document_entity("company_term", term_key, str(term), "company_term")
        add_relation("company_term", term_key, "mentioned_in", document["doc_type"], document["id"], document["id"])

    return {
        "document_entity": document_entity,
        "entities": entities,
        "document_entities": document_entities,
        "relations": relations,
    }


def build_graph_context_payload(
    doc_entities: list[dict[str, Any]],
    focus_entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> dict[str, Any]:
    entity_map: dict[str, dict[str, Any]] = {}
    for item in [*doc_entities, *focus_entities]:
        entity_map[item["id"]] = {
            "id": item["id"],
            "type": item["entity_type"],
            "key": item["entity_key"],
            "name": item["name"],
            "metadata": item.get("metadata_json", {}) or {},
        }
    relation_items = [
        {
            "src": item["src_name"],
            "src_type": item["src_type"],
            "relation_type": item["relation_type"],
            "dst": item["dst_name"],
            "dst_type": item["dst_type"],
            "source_doc_id": item.get("source_doc_id"),
            "confidence": item.get("confidence", 1.0),
        }
        for item in relations
    ]
    counts = Counter(item["entity_type"] for item in doc_entities)
    return {
        "companies": [item for item in entity_map.values() if item["type"] in {"company", "company_term"}],
        "themes": [item for item in entity_map.values() if item["type"] == "theme"],
        "industries": [item for item in entity_map.values() if item["type"] == "industry"],
        "relations": relation_items,
        "doc_entity_counts": dict(counts),
    }
