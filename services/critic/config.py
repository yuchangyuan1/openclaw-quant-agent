import os

from dotenv import load_dotenv
from services.common.paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

PORT = int(os.getenv("CRITIC_PORT", "8007"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
APP_ENV = os.getenv("APP_ENV", "development")
