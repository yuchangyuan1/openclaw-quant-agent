from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_project_path(value: str, default: str) -> Path:
    raw = value or default
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    return ensure_dir(resolve_project_path(os.getenv("DATA_DIR", "./data"), "./data"))


def raw_data_dir() -> Path:
    return ensure_dir(resolve_project_path(os.getenv("RAW_DATA_DIR", "./data/raw"), "./data/raw"))


def metadata_dir() -> Path:
    return ensure_dir(data_dir() / "metadata")


def reports_dir() -> Path:
    return ensure_dir(resolve_project_path(os.getenv("REPORTS_DIR", "./data/reports"), "./data/reports"))
