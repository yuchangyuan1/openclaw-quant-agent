#!/usr/bin/env python3
"""
Postgres schema 初始化脚本
在 docker-compose 启动 postgres 后运行，执行 init_schema.sql

用法：
    python scripts/init_db.py
"""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

SCRIPT_DIR = Path(__file__).parent
SQL_FILE = SCRIPT_DIR / "init_schema.sql"


def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "quant_research"),
        user=os.getenv("POSTGRES_USER", "quant"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def main():
    if not SQL_FILE.exists():
        print(f"[ERROR] SQL file not found: {SQL_FILE}", file=sys.stderr)
        sys.exit(1)

    sql = SQL_FILE.read_text(encoding="utf-8")

    try:
        conn = get_connection()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.close()
        print("[PASS] Schema initialized successfully.")
    except psycopg2.OperationalError as e:
        print(f"[FAIL] Cannot connect to Postgres: {e}", file=sys.stderr)
        print("  Make sure docker-compose is running: docker-compose up -d postgres", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[FAIL] Schema init error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
