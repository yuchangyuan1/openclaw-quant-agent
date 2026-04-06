#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

from dotenv import load_dotenv
from psycopg2.extras import Json

from services.common.audit import _manifest_path as run_log_manifest_path
from services.common.paths import metadata_dir, reports_dir
from services.common.repository import _connect
from services.common.repository import _manifest_path as document_manifest_path
from services.common.stocks import load_target_stocks

load_dotenv()

GRAPH_MANIFEST_PATH = metadata_dir() / "graph_manifest.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_stock(cursor, code: str | None, name: str | None = None, industry: str | None = None) -> None:
    if not code:
        return
    target = load_target_stocks().get(code)
    resolved_name = name or (target["name"] if target else code)
    resolved_industry = industry if industry is not None else (target.get("industry") if target else None)
    tier = "core" if target else "watchlist"
    cursor.execute(
        """
        INSERT INTO stocks (code, name, industry, tier)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE
        SET name = COALESCE(EXCLUDED.name, stocks.name),
            industry = COALESCE(EXCLUDED.industry, stocks.industry),
            updated_at = NOW()
        """,
        (code, resolved_name, resolved_industry, tier),
    )


def guess_company_name(document: dict) -> str | None:
    raw_path = document.get("file_path")
    if raw_path and Path(raw_path).exists():
        raw = load_json(Path(raw_path), {})
        for item in raw.get("metadata", {}).get("matched_stocks", []):
            if item.get("code") == document.get("company_code") and item.get("name"):
                return item["name"]
    title = str(document.get("title") or "")
    if ":" in title:
        return title.split(":", 1)[0].strip()
    return None


def migrate_stocks(cursor) -> int:
    count = 0
    for code, item in load_target_stocks().items():
        ensure_stock(cursor, code, str(item["name"]), str(item.get("industry") or ""))
        count += 1
    return count


def migrate_documents(cursor) -> int:
    documents = load_json(document_manifest_path(), [])
    count = 0
    for item in documents:
        ensure_stock(cursor, item.get("company_code"), guess_company_name(item))
        cursor.execute(
            """
            INSERT INTO documents (
                id, source, doc_type, title, url, file_path, content_hash, company_code,
                published_at, ingested_at, is_indexed, is_duplicate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET source = EXCLUDED.source,
                doc_type = EXCLUDED.doc_type,
                title = EXCLUDED.title,
                url = EXCLUDED.url,
                file_path = EXCLUDED.file_path,
                content_hash = EXCLUDED.content_hash,
                company_code = EXCLUDED.company_code,
                published_at = EXCLUDED.published_at,
                ingested_at = EXCLUDED.ingested_at,
                is_indexed = EXCLUDED.is_indexed,
                is_duplicate = EXCLUDED.is_duplicate
            """,
            (
                item["id"],
                item["source"],
                item["doc_type"],
                item["title"],
                item.get("url"),
                item.get("file_path"),
                item.get("content_hash"),
                item.get("company_code"),
                item.get("published_at"),
                item.get("ingested_at"),
                bool(item.get("is_indexed", False)),
                bool(item.get("is_duplicate", False)),
            ),
        )
        count += 1
    return count


def migrate_reports(cursor) -> int:
    count = 0
    for report_type in ("daily", "weekly"):
        report_dir = reports_dir() / report_type
        if not report_dir.exists():
            continue
        for path in sorted(report_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            report_date = path.stem
            if report_type == "weekly":
                report_date = report_date[:10]
            critic_match = re.search(r"Critic 校验[：:]\s*([A-Z_]+)", content)
            critic_status = (critic_match.group(1).lower() if critic_match else "pending")
            cursor.execute(
                """
                INSERT INTO reports (report_type, report_date, content, file_path, critic_status)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (report_type, report_date) DO UPDATE
                SET content = EXCLUDED.content,
                    file_path = EXCLUDED.file_path,
                    critic_status = EXCLUDED.critic_status
                """,
                (report_type, report_date, content, str(path), critic_status),
            )
            count += 1
    return count


def migrate_run_logs(cursor) -> int:
    items = load_json(run_log_manifest_path(), [])
    count = 0
    for item in items:
        cursor.execute(
            """
            INSERT INTO run_logs (
                id, job_id, job_type, status, input_params, output_summary, error_message, started_at, finished_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET job_id = EXCLUDED.job_id,
                job_type = EXCLUDED.job_type,
                status = EXCLUDED.status,
                input_params = EXCLUDED.input_params,
                output_summary = EXCLUDED.output_summary,
                error_message = EXCLUDED.error_message,
                started_at = EXCLUDED.started_at,
                finished_at = EXCLUDED.finished_at
            """,
            (
                item["id"],
                item["job_id"],
                item.get("job_type"),
                item["status"],
                Json(item.get("input_params")),
                Json(item.get("output_summary")) if item.get("output_summary") is not None else None,
                item.get("error_message"),
                item.get("started_at"),
                item.get("finished_at"),
            ),
        )
        count += 1
    return count


def migrate_graph(cursor) -> dict[str, int]:
    graph = load_json(
        GRAPH_MANIFEST_PATH,
        {"entities": [], "document_entities": [], "relations": [], "metric_snapshots": [], "risk_snapshots": []},
    )
    entity_ids: dict[tuple[str, str], str] = {}
    counts = {"entities": 0, "document_entities": 0, "relations": 0, "metric_snapshots": 0, "risk_snapshots": 0}

    for entity in graph["entities"]:
        cursor.execute(
            """
            INSERT INTO entities (id, entity_type, entity_key, name, alias_json, metadata_json, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (entity_type, entity_key) DO UPDATE
            SET name = EXCLUDED.name,
                alias_json = EXCLUDED.alias_json,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = EXCLUDED.updated_at
            RETURNING id
            """,
            (
                entity["id"],
                entity["entity_type"],
                entity["entity_key"],
                entity["name"],
                Json(entity.get("aliases", [])),
                Json(entity.get("metadata", {})),
                entity.get("updated_at"),
            ),
        )
        entity_ids[(entity["entity_type"], entity["entity_key"])] = cursor.fetchone()[0]
        counts["entities"] += 1

    for item in graph["document_entities"]:
        entity_id = entity_ids.get((item["entity_type"], item["entity_key"]))
        if not entity_id:
            continue
        cursor.execute(
            """
            INSERT INTO document_entities (
                id, document_id, entity_id, mention_text, mention_type, confidence
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id, entity_id, mention_type) DO UPDATE
            SET mention_text = EXCLUDED.mention_text,
                confidence = EXCLUDED.confidence
            """,
            (
                item["id"],
                item["document_id"],
                entity_id,
                item.get("mention_text"),
                item.get("mention_type", "extracted"),
                item.get("confidence", 1.0),
            ),
        )
        counts["document_entities"] += 1

    for item in graph["relations"]:
        src_id = entity_ids.get((item["src_type"], item["src_key"]))
        dst_id = entity_ids.get((item["dst_type"], item["dst_key"]))
        if not src_id or not dst_id:
            continue
        cursor.execute(
            """
            INSERT INTO relations (
                id, src_entity_id, relation_type, dst_entity_id, weight, confidence, source_doc_id, metadata_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (src_entity_id, relation_type, dst_entity_id, COALESCE(source_doc_id, '00000000-0000-0000-0000-000000000000'::uuid))
            DO UPDATE SET
                weight = EXCLUDED.weight,
                confidence = EXCLUDED.confidence,
                metadata_json = EXCLUDED.metadata_json
            """,
            (
                item["id"],
                src_id,
                item["relation_type"],
                dst_id,
                item.get("weight", 1.0),
                item.get("confidence", 1.0),
                item.get("source_doc_id"),
                Json(item.get("metadata", {})),
            ),
        )
        counts["relations"] += 1

    for item in graph["metric_snapshots"]:
        key = ("company", item["entity_key"])
        entity_id = entity_ids.get(key)
        if not entity_id:
            ensure_stock(cursor, item["entity_key"], item.get("entity_name"))
            cursor.execute(
                """
                INSERT INTO entities (entity_type, entity_key, name, alias_json, metadata_json)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (entity_type, entity_key) DO UPDATE
                SET name = EXCLUDED.name
                RETURNING id
                """,
                ("company", item["entity_key"], item.get("entity_name") or item["entity_key"], Json([]), Json({})),
            )
            entity_id = cursor.fetchone()[0]
            entity_ids[key] = entity_id
        cursor.execute(
            """
            INSERT INTO entity_metric_snapshots (
                id, entity_id, metric_name, metric_value, metric_date, source, metadata_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (entity_id, metric_name, metric_date, source) DO UPDATE
            SET metric_value = EXCLUDED.metric_value,
                metadata_json = EXCLUDED.metadata_json
            """,
            (
                item["id"],
                entity_id,
                item["metric_name"],
                item["metric_value"],
                item["metric_date"],
                item["source"],
                Json(item.get("metadata", {})),
            ),
        )
        counts["metric_snapshots"] += 1

    for item in graph["risk_snapshots"]:
        key = ("company", item["entity_key"])
        entity_id = entity_ids.get(key)
        if not entity_id:
            ensure_stock(cursor, item["entity_key"], item.get("entity_name"))
            cursor.execute(
                """
                INSERT INTO entities (entity_type, entity_key, name, alias_json, metadata_json)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (entity_type, entity_key) DO UPDATE
                SET name = EXCLUDED.name
                RETURNING id
                """,
                ("company", item["entity_key"], item.get("entity_name") or item["entity_key"], Json([]), Json({})),
            )
            entity_id = cursor.fetchone()[0]
            entity_ids[key] = entity_id
        cursor.execute(
            """
            INSERT INTO entity_risk_snapshots (
                id, entity_id, risk_type, risk_level, risk_value, risk_date, source, metadata_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (entity_id, risk_type, risk_date, source) DO UPDATE
            SET risk_level = EXCLUDED.risk_level,
                risk_value = EXCLUDED.risk_value,
                metadata_json = EXCLUDED.metadata_json
            """,
            (
                item["id"],
                entity_id,
                item["risk_type"],
                item["risk_level"],
                item.get("risk_value"),
                item["risk_date"],
                item["source"],
                Json(item.get("metadata", {})),
            ),
        )
        counts["risk_snapshots"] += 1

    return counts


def main() -> int:
    with _connect() as conn:
        with conn.cursor() as cursor:
            migrated = {
                "stocks": migrate_stocks(cursor),
                "documents": migrate_documents(cursor),
                "reports": migrate_reports(cursor),
                "run_logs": migrate_run_logs(cursor),
            }
            migrated.update(migrate_graph(cursor))
        conn.commit()
    print(json.dumps(migrated, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
