# 로깅 모듈 (Logger)
# 중앙 집중식 로거 설정 — print 대신 구조화된 로그 사용

import logging
import sys
import io
from core.config import settings

LOG_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s - %(message)s"


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거 생성"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    return logger
