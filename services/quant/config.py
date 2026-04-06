import os

from dotenv import load_dotenv

from services.common.paths import PROJECT_ROOT


load_dotenv(PROJECT_ROOT / ".env")

PORT = int(os.getenv("QUANT_PORT", "8003"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MARKET_DATA_DIR = os.getenv("MARKET_DATA_DIR", "./data/market")
FUNDAMENTAL_DATA_DIR = os.getenv("FUNDAMENTAL_DATA_DIR", "./data/financials")
APP_ENV = os.getenv("APP_ENV", "development")
ENABLE_LIVE_FUNDAMENTAL_FETCH = os.getenv("ENABLE_LIVE_FUNDAMENTAL_FETCH", "1") == "1"
FUNDAMENTAL_CACHE_HOURS = int(os.getenv("FUNDAMENTAL_CACHE_HOURS", "168"))
INDUSTRY_COMPARISON_MAX_PEERS = int(os.getenv("INDUSTRY_COMPARISON_MAX_PEERS", "8"))

# Akshare request delay in seconds to avoid provider throttling.
AKSHARE_DELAY = float(os.getenv("AKSHARE_DELAY", "1.0"))
