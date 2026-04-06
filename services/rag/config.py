import os
from dotenv import load_dotenv

from services.common.paths import data_dir
from services.common.paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

PORT = int(os.getenv("RAG_PORT", "8002"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_PERSIST_DIR = str(data_dir() / "chroma")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
APP_ENV = os.getenv("APP_ENV", "development")

COLLECTION_NAME = "quant_research_docs"
EMBEDDING_DIM = 1024          # voyage-finance-2 维度
TOP_K_DEFAULT = 5
MIN_SCORE_DEFAULT = 0.7
