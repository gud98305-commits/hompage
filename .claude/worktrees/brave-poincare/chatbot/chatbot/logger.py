"""
채찍피티 구조화 로거 모듈.

Python 표준 logging 모듈로 JSON 형식 로그를 출력합니다.
Sentry/CloudWatch 등 모니터링 시스템이 구조화 데이터로
파싱할 수 있는 형태를 제공합니다.

구성:
① JsonFormatter (logging.Formatter 상속)
② ChatbotLogger 클래스
③ get_logger() 싱글턴 팩토리
"""

from __future__ import annotations

import json
import logging
from datetime import datetime


# ===========================================================================
# ① JsonFormatter (logging.Formatter 상속)
# ===========================================================================

class JsonFormatter(logging.Formatter):
    """로그를 JSON 형식으로 직렬화.

    {"timestamp": ..., "level": ..., "module": ...,
     "event": ..., "detail": ...} 형태 출력.
    CloudWatch/Sentry 파서가 구조화 데이터로 인식 가능.
    """

    def format(self, record: logging.LogRecord) -> str:
        # 구조화 JSON 출력: 모니터링 시스템(Sentry, CloudWatch)이
        # 텍스트 파싱 없이 필드 단위로 필터/알람 설정 가능
        return json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "module": record.name,
            "event": record.getMessage(),
            "detail": getattr(record, "detail", None),
        }, ensure_ascii=False)


# ===========================================================================
# ② ChatbotLogger 클래스
# ===========================================================================

class ChatbotLogger:
    """채찍피티 챗봇 전용 구조화 로거.

    운영 블라인드 방지: 조용한 실패를 ERROR 레벨로 기록하여
    Sentry/CloudWatch 등 모니터링 시스템이 알람을 보낼 수 있게 함.
    TODO: 8단계 이후 Sentry SDK 연동 시 captureException() 추가
    """

    def __init__(self, name: str = "chatbot"):
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(JsonFormatter())
            self._logger.addHandler(handler)
            # TODO: 운영 환경에서 로그 폭증(디도스 등) 시
            # StreamHandler → QueueHandler로 교체 필요.
            # QueueHandler는 별도 스레드에서 로그를 처리하여
            # 메인 이벤트 루프 블로킹 방지.
            # Sentry/CloudWatch 연동 시 반드시 비동기 처리로 전환.
            # 참고: logging.handlers.QueueHandler + QueueListener 패턴
        self._logger.setLevel(logging.DEBUG)

    def gpt_fallback(self, module: str, reason: str, exc: Exception) -> None:
        """GPT 호출 실패 → 폴백 전환 시 호출.

        운영자가 "GPT가 죽어있는데 키워드 봇이 대신 응답 중"임을
        인지할 수 있게 함.
        """
        self._logger.error(
            f"[GPT_FALLBACK] {module} → 키워드 폴백 전환",
            extra={"detail": {"reason": reason, "exception": str(exc)}},
        )

    def db_error(self, module: str, user_id: str, exc: Exception) -> None:
        """게임 DB 또는 SQLite 조회 실패 시 호출."""
        self._logger.error(
            f"[DB_ERROR] {module} user_id={user_id}",
            extra={"detail": {"exception": str(exc)}},
        )

    def rag_filtered_empty(self, module: str, original_count: int) -> None:
        """RAG 필터링 결과 0건 발생 시 호출.

        빈번하게 발생 시 임계값(RELEVANCE_THRESHOLD) 튜닝 신호.
        """
        self._logger.warning(
            f"[RAG_FILTERED_EMPTY] {module} "
            f"원본 {original_count}건 → 필터링 후 0건",
            extra={"detail": {"original_count": original_count}},
        )

    def injection_detected(
        self, module: str, user_id: str, message_preview: str,
    ) -> None:
        """프롬프트 인젝션 시도 감지 시 호출.

        빈번한 시도 → IP 차단 등 보안 대응 트리거 가능.
        """
        self._logger.warning(
            f"[INJECTION_DETECTED] {module} user_id={user_id}",
            extra={"detail": {"message_preview": message_preview[:50]}},
        )

    def api_key_missing(self, module: str) -> None:
        """OPENAI_API_KEY 미설정 감지 시 호출."""
        self._logger.critical(
            f"[API_KEY_MISSING] {module}: OPENAI_API_KEY 미설정. "
            "GPT 기능 전면 비활성화 상태.",
            extra={"detail": None},
        )


# ===========================================================================
# ③ 싱글턴 팩토리
# ===========================================================================

_logger_instance: ChatbotLogger | None = None


def get_logger() -> ChatbotLogger:
    """ChatbotLogger 싱글턴 팩토리.

    런타임: ChatbotLogger 인스턴스 1개만 유지
    테스트 주입 예시:
      app.dependency_overrides[get_logger] = lambda: MockLogger()
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = ChatbotLogger()
    return _logger_instance
