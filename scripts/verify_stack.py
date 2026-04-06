#!/usr/bin/env python3
"""
验收 2：基础设施连通性验证脚本

验证内容：
1. Postgres：连接 → 查询 stocks 表 → 写入测试记录 → 读回确认
2. Chroma：连接 → 创建测试 collection → 写入测试文档 → 查询确认

用法：
    python scripts/verify_stack.py

成功时退出码为 0，失败时为 1。
"""

import os
import sys
import uuid
from dotenv import load_dotenv

load_dotenv()

PASSED = []
FAILED = []


# ── Postgres 验证 ──────────────────────────────────────────────────────────

def verify_postgres():
    try:
        import psycopg2
    except ImportError:
        FAILED.append("Postgres: psycopg2-binary not installed (run: pip install psycopg2-binary)")
        return

    conn_params = dict(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "quant_research"),
        user=os.getenv("POSTGRES_USER", "quant"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    try:
        conn = psycopg2.connect(**conn_params)
        conn.autocommit = True
        with conn.cursor() as cur:
            # 基础连通
            cur.execute("SELECT 1")

            # 确认表存在
            cur.execute("SELECT COUNT(*) FROM stocks")
            count = cur.fetchone()[0]

            # 写入一条测试记录
            test_code = "TEST00"
            cur.execute(
                "INSERT INTO stocks (code, name, industry, tier) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (code) DO NOTHING",
                (test_code, "测试股票", "测试行业", "watchlist"),
            )

            # 读回确认
            cur.execute("SELECT name FROM stocks WHERE code = %s", (test_code,))
            row = cur.fetchone()
            assert row is not None, "Test record not found after insert"
            assert row[0] == "测试股票"

            # 清理测试数据
            cur.execute("DELETE FROM stocks WHERE code = %s", (test_code,))

        conn.close()
        PASSED.append(f"Postgres OK  (stocks 表现有 {count} 条记录)")
    except psycopg2.OperationalError as e:
        FAILED.append(
            f"Postgres: Cannot connect — {e}\n"
            "  → 请运行: docker-compose up -d postgres"
        )
    except Exception as e:
        FAILED.append(f"Postgres: Unexpected error — {e}")


# ── Chroma 验证 ────────────────────────────────────────────────────────────

def verify_chroma():
    try:
        import chromadb
    except ImportError:
        FAILED.append("Chroma: chromadb not installed (run: pip install chromadb)")
        return

    chroma_host = os.getenv("CHROMA_HOST", "localhost")
    chroma_port = int(os.getenv("CHROMA_PORT", "8000"))

    try:
        client = chromadb.HttpClient(host=chroma_host, port=chroma_port)

        # 心跳检查
        client.heartbeat()

        # 创建测试 collection
        collection_name = "verify_stack_test"
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

        collection = client.create_collection(collection_name)

        # 写入测试文档（使用随机向量，阶段 0 不依赖真实 embedding）
        test_id = str(uuid.uuid4())
        collection.add(
            ids=[test_id],
            embeddings=[[0.1] * 1024],   # voyage-finance-2 维度为 1024
            documents=["这是一条测试文档，用于验证 Chroma 连通性。"],
            metadatas=[{"source": "verify_stack", "date": "2026-04-07"}],
        )

        # 查询确认
        results = collection.query(
            query_embeddings=[[0.1] * 1024],
            n_results=1,
        )
        assert len(results["ids"][0]) == 1, "Query returned no results"
        assert results["ids"][0][0] == test_id

        # 清理
        client.delete_collection(collection_name)

        PASSED.append("Chroma OK  (写入并查询测试文档成功)")
    except Exception as e:
        FAILED.append(
            f"Chroma: {e}\n"
            "  → 请运行: docker-compose up -d chroma"
        )


# ── 主入口 ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  量化投研系统 — 基础设施验收检查")
    print("=" * 55)

    verify_postgres()
    verify_chroma()

    print()
    for msg in PASSED:
        print(f"  [PASS] {msg}")
    for msg in FAILED:
        print(f"  [FAIL] {msg}")

    print()
    if FAILED:
        print(f"结果：{len(PASSED)} 通过，{len(FAILED)} 失败")
        sys.exit(1)
    else:
        print(f"结果：全部 {len(PASSED)} 项通过 [PASS]")
        sys.exit(0)


if __name__ == "__main__":
    main()
