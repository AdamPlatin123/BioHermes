"""BioHermes centralized configuration."""
import os

MINERU_API_URL = os.getenv("MINERU_API_URL", "http://10.123.45.9:8500")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
LLM_MODEL = os.getenv("LLM_MODEL", "GLM-5.1")
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "9091"))
LOG_DIR = os.getenv("LOG_DIR", "logs")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
MAX_CONCURRENT_PARSE = int(os.getenv("MAX_CONCURRENT_PARSE", "3"))
PARSE_TIMEOUT = int(os.getenv("PARSE_TIMEOUT", "300"))
