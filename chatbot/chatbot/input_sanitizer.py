"""
채찍피티 입력 위생 검사 모듈.

프롬프트 인젝션/탈옥 시도를 탐지하고,
제어 문자 제거 및 길이 트리밍을 수행합니다.
외부 의존성 없이 순수 Python으로 구현.

구성:
① INJECTION_PATTERNS (모듈 상수)
② InputSanitizer 클래스
③ get_sanitizer() 싱글턴 팩토리
"""

from __future__ import annotations

import re


# ===========================================================================
# ① INJECTION_PATTERNS (모듈 상수)
# ===========================================================================

# 프롬프트 인젝션/탈옥 시도 탐지 패턴 목록.
# 한국어 + 영문 패턴 포함.
# TODO: 운영 데이터 기반으로 패턴 지속 확장 필요
# TODO: 정규식 고도화 시 ReDoS 안전성 검토 필수.
#       특히 (a+)+ 같은 중첩 수량자 패턴은 ReDoS에 취약하므로
#       re2 라이브러리 도입 또는 패턴 복잡도 제한 고려.
INJECTION_PATTERNS: list[str] = [
    # 시스템 명령 무력화 시도
    "시스템 명령", "system prompt", "system message",
    "프롬프트 출력", "명령을 무시", "ignore previous",
    "ignore all", "disregard",
    # 역할 탈취 시도
    "개발자 모드", "developer mode", "debug mode",
    "jailbreak", "탈옥", "역할을 바꿔",
    # 민감 정보 탈취 시도
    "api key", "api 키", "openai key",
    "시스템 프롬프트를 보여", "내부 설정",
    # 페르소나 파괴 시도
    "채찍피티가 아니", "다른 ai", "gpt로 동작",
    "너의 진짜 정체",
]


# ===========================================================================
# ② InputSanitizer 클래스
# ===========================================================================

class InputSanitizer:
    """채찍피티 입력 위생 검사기.

    인젝션 감지 시 에러 raise가 아닌 bool 반환으로
    호출부에서 유연하게 대응할 수 있도록 설계.
    """

    # re.compile로 사전 컴파일:
    # sanitize()가 매 요청마다 호출되므로
    # 패턴을 매번 컴파일하지 않고 클래스 변수로 캐싱하여 성능 향상.
    # TODO: 정규식 고도화 시 ReDoS 안전성 검토 필수.
    _CONTROL_CHAR_RE = re.compile(
        r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]'
        # 탭(\t=\x09), 개행(\n=\x0a) 제외: 정상 입력 허용
    )

    def is_injection_attempt(self, message: str) -> bool:
        """인젝션 패턴 포함 여부 검사. 대소문자 무관."""
        lower_msg = message.lower()
        return any(
            pattern.lower() in lower_msg
            for pattern in INJECTION_PATTERNS
        )

    def sanitize(self, message: str) -> tuple[bool, str]:
        """메시지 위생 검사 후 (is_safe, cleaned_message) 반환."""

        # Step 1. 인젝션 패턴 탐지
        # 감지 시 False 반환 → 호출부에서 경고 응답 + logger 호출
        if self.is_injection_attempt(message):
            return False, message

        # Step 2. 길이 초과 트리밍
        # Pydantic 1-A max_length=4096 외 추가 방어선
        cleaned = message[:2000]

        # Step 3. 제어 문자 제거 (사전 컴파일 패턴 재사용)
        # 매 요청 컴파일 오버헤드 제거 → 성능 향상
        cleaned = self._CONTROL_CHAR_RE.sub('', cleaned)

        return True, cleaned


# ===========================================================================
# ③ 싱글턴 팩토리
# ===========================================================================

_sanitizer_instance: InputSanitizer | None = None


def get_sanitizer() -> InputSanitizer:
    """InputSanitizer 싱글턴 팩토리.

    테스트 주입 예시:
      app.dependency_overrides[get_sanitizer] = lambda: MockSanitizer()
    """
    global _sanitizer_instance
    if _sanitizer_instance is None:
        _sanitizer_instance = InputSanitizer()
    return _sanitizer_instance
