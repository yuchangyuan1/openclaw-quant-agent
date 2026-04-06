import os
from dotenv import load_dotenv
from services.common.paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

PORT = int(os.getenv("RISK_PORT", "8004"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MARKET_DATA_DIR = os.getenv("MARKET_DATA_DIR", "./data/market")
APP_ENV = os.getenv("APP_ENV", "development")

INDUSTRY_CONCENTRATION_THRESHOLD = 0.30   # 单行业超过 30% 触发告警
DRAWDOWN_ALERT_THRESHOLD = -0.15           # 最大回撤超过 -15% 触发告警
