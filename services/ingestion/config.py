import os

from dotenv import load_dotenv

from services.common.paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

PORT = int(os.getenv("INGESTION_PORT", "8001"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DATA_DIR = os.getenv("DATA_DIR", "./data")
RAW_DATA_DIR = os.getenv("RAW_DATA_DIR", "./data/raw")
APP_ENV = os.getenv("APP_ENV", "development")
