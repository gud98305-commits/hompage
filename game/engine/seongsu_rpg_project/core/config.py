# 설정 모듈 (Configuration)
# 환경변수 기반 설정 관리 — 하드코딩 제거

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """애플리케이션 설정 — 환경변수에서 로드"""

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./game.db"
    )
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    CORS_ORIGINS: list[str] = (
        os.getenv("CORS_ORIGINS", "*").split(",")
    )
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()
