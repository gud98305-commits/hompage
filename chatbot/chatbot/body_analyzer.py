"""
OttO봇 체형 분석 모듈.

골격 진단 이론 기반으로 사용자 체형을 wave/straight/neutral로 분류합니다.
AsyncOpenAI(GPT-4o-mini)를 1차로 사용하고, 실패 시 키워드 폴백으로 자동 강등합니다.

구성:
① BodyType (str, Enum) - 체형 유형 열거형
② BodyAnalysisError (ChatServiceError 상속)
③ BodyAnalyzer 클래스 (GPT 분석 + 키워드 폴백 + 스타일 가이드)
④ get_body_analyzer() 팩토리
"""

from __future__ import annotations

import os
from enum import Enum

from openai import AsyncOpenAI

from chat_schemas import BodyAnalysisRequest
from chat_service import ChatServiceError


# ===========================================================================
# ① BodyType - 체형 유형 열거형
# ===========================================================================

class BodyType(str, Enum):
    """골격 진단 기반 체형 유형.

    각 체형별 골격 진단 기준과 추천 스타일을 정의합니다.

    TODO: 추후 고도화 시 BodyType별 confidence_score 도입 고려
    analyze()가 (BodyType, float) 튜플을 반환하도록 확장하면
    "확률 낮을 때 두 체형 동시 추천" 같은 유연한 로직 구현 가능
    현재는 temperature=0 결정론적 응답으로 단일값만 사용
    """

    WAVE = "wave"
    # 골격 진단 기준 곡선형: 하체 발달, 허리 길고 잘록함
    # 추천: 플레어/A라인/랩 스타일

    STRAIGHT = "straight"
    # 골격 진단 기준 직선형: 상체 발달, 허리 짧고 굴곡 적음
    # 추천: 테일러드/레이어드/와이드 팬츠

    NEUTRAL = "neutral"
    # 골격 진단 기준 균형형: 상하체 균형, 굴곡 중간
    # 추천: 다양한 스타일 가능


# ===========================================================================
# ② BodyAnalysisError
# ===========================================================================

class BodyAnalysisError(ChatServiceError):
    """체형 분석 전용 예외.

    code 분류:
    - "gpt_failed"   : OpenAI 호출 실패 → 키워드 폴백 실행
    - "parse_failed" : GPT 응답 파싱 실패 → 키워드 폴백 실행
    - "insufficient" : 정보 부족으로 분류 불가
    """

    def __init__(
        self,
        message: str,
        detail: str = "",
        code: str = "insufficient",
    ) -> None:
        super().__init__(message, detail)
        self.code = code


# ===========================================================================
# ③ BodyAnalyzer
# ===========================================================================

# GPT system 메시지 — 골격 진단 기반 정의 포함
_SYSTEM_PROMPT = (
    "당신은 한국 패션 스타일리스트입니다. "
    "골격 진단 이론을 기반으로 체형을 분류합니다.\n\n"
    "분류 기준:\n"
    "- wave: 하체(골반·허리)가 발달하고 허리가 잘록하며 "
    "굴곡이 뚜렷한 곡선형\n"
    "- straight: 상체(어깨)가 발달하고 허리가 짧으며 "
    "굴곡이 적은 직선형\n"
    "- neutral: 상하체가 균형잡히고 굴곡이 중간 정도인 균형형\n\n"
    "wave, straight, neutral 중 하나만 소문자로 반환하세요. "
    "다른 설명은 절대 추가하지 마세요."
)


class BodyAnalyzer:
    """골격 진단 기반 체형 분석기.

    GPT-4o-mini를 1차로 사용하고, 실패 시 키워드 폴백으로 자동 강등합니다.
    API 키가 없으면 처음부터 키워드 폴백 모드로 동작합니다.
    """

    # 키워드 폴백용 키워드 셋
    _WAVE_KEYWORDS: set[str] = {
        "곡선", "웨이브", "골반", "허리", "플레어",
        "여성스", "둥글", "부드",
    }
    _STRAIGHT_KEYWORDS: set[str] = {
        "직선", "스트레이트", "어깨", "각", "보이시",
        "슬림", "일자", "평평",
    }
    _NEUTRAL_KEYWORDS: set[str] = {
        "균형", "뉴트럴", "보통", "평균", "중간",
    }

    # 체형별 스타일 가이드
    _STYLE_GUIDES: dict[BodyType, str] = {
        BodyType.WAVE: (
            "곡선형 체형이시군요! 플레어 스커트, A라인 원피스, "
            "허리를 강조하는 랩 스타일을 추천드려요. 👗"
        ),
        BodyType.STRAIGHT: (
            "직선형 체형이시군요! 테일러드 재킷, 와이드 팬츠, "
            "레이어드 룩으로 입체감을 주는 스타일을 추천드려요. 🧥"
        ),
        BodyType.NEUTRAL: (
            "균형잡힌 체형이시군요! 다양한 스타일이 잘 어울리세요. "
            "트렌디한 아이템에 도전해보시는 건 어떨까요? ✨"
        ),
    }

    def __init__(self) -> None:
        """초기화 시 OPENAI_API_KEY 즉시 검증.

        키 없으면 gpt_enabled=False → 이후 모든 GPT 호출을 키워드 폴백으로 직행.
        서버 구동 시점에 설정 누락 감지 가능.

        [운영 가이드 - 필독]
        gpt_enabled=False 상태는 서버 재시작 전까지 복구되지 않습니다.
        환경변수(OPENAI_API_KEY) 수정 후 반드시 서버를 재시작하세요.
        런타임 리로드는 지원하지 않습니다.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print(
                "[BodyAnalyzer] WARNING: OPENAI_API_KEY 환경변수가 "
                "설정되지 않았습니다.\n"
                "체형 분석이 키워드 폴백 모드로만 동작합니다.\n"
                "GPT 기능을 활성화하려면 환경변수 설정 후 "
                "서버를 재시작하세요."
            )
            self.gpt_enabled: bool = False
            self._client: AsyncOpenAI | None = None
        else:
            self.gpt_enabled = True
            self._client = AsyncOpenAI(api_key=api_key)

    # -------------------------------------------------------------------
    # GPT 분석
    # -------------------------------------------------------------------

    async def analyze_with_gpt(
        self,
        description: str | None,
        height: float | None,
        weight: float | None,
    ) -> BodyType:
        """GPT-4o-mini로 자연어 체형 서술을 분석합니다.

        temperature=0으로 결정론적 응답을 강제합니다.
        파싱 실패 시 BodyAnalysisError(code="parse_failed")를 raise합니다.
        """
        if self._client is None:
            raise BodyAnalysisError(
                "GPT 클라이언트가 초기화되지 않았습니다.",
                code="gpt_failed",
            )

        # description 토큰 비용 상한 트리밍
        # chat_schemas.py에서 max_length=1000 적용되어 있으나
        # GPT 토큰 비용 추가 절감을 위해 500자로 재트리밍
        safe_description = (description or "미제공")[:500]
        height_str = f"{height}cm" if height is not None else "미제공"
        weight_str = f"{weight}kg" if weight is not None else "미제공"

        user_message = (
            f"- 키: {height_str}\n"
            f"- 몸무게: {weight_str}\n"
            f"- 체형 서술: {safe_description}"
        )

        try:
            response = await self._client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=10,
                temperature=0,  # 결정론적 응답 강제 (confidence 소실 감수)
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
        except Exception as e:
            raise BodyAnalysisError(
                "GPT 체형 분석 호출에 실패했습니다.",
                detail=str(e),
                code="gpt_failed",
            ) from e

        # 응답 파싱
        raw = (response.choices[0].message.content or "").strip().lower()
        valid_types = {t.value for t in BodyType}

        if raw not in valid_types:
            raise BodyAnalysisError(
                f"GPT 응답을 체형으로 변환할 수 없습니다: '{raw}'",
                detail=f"expected one of {valid_types}, got '{raw}'",
                code="parse_failed",
            )

        return BodyType(raw)

    # -------------------------------------------------------------------
    # 키워드 폴백
    # -------------------------------------------------------------------

    def analyze_with_keywords(
        self,
        description: str | None,
        height: float | None,
        weight: float | None,
    ) -> BodyType:
        """GPT 실패 또는 gpt_enabled=False 시 키워드 매칭 폴백.

        서비스 연속성을 보장합니다.

        주의: 키워드 폴백은 GPT 대비 신뢰도가 낮습니다.
        TODO: 추후 confidence_score 도입 시 폴백 결과에
        낮은 점수(예: 0.4)를 부여하여 추천 로직에서 구분 가능하게 처리
        """
        text = (description or "").lower()

        # 부분 문자열 매칭 (한국어 조사 대응)
        wave_score = sum(1 for kw in self._WAVE_KEYWORDS if kw in text)
        straight_score = sum(
            1 for kw in self._STRAIGHT_KEYWORDS if kw in text
        )
        neutral_score = sum(
            1 for kw in self._NEUTRAL_KEYWORDS if kw in text
        )

        if wave_score > straight_score and wave_score > neutral_score:
            return BodyType.WAVE
        if straight_score > wave_score and straight_score > neutral_score:
            return BodyType.STRAIGHT

        # 동점이거나 키워드 없으면 NEUTRAL 기본값
        return BodyType.NEUTRAL

    # -------------------------------------------------------------------
    # 메인 분석 함수
    # -------------------------------------------------------------------

    async def analyze(self, request: BodyAnalysisRequest) -> BodyType:
        """체형 분석 메인 함수.

        GPT 분석을 시도하고, 실패 시 키워드 폴백으로 자동 강등합니다.

        TODO: 추후 고도화 시 반환 타입을 tuple[BodyType, float]로 변경
        (BodyType, confidence_score) 형태로 확장하면
        추천 로직에서 신뢰도 기반 분기 처리 가능
        현재는 단순 BodyType 반환
        """
        # Step 1. 입력 유효성 확인
        # description·height·weight 모두 None이면 분류 불가
        if (
            request.description is None
            and request.height is None
            and request.weight is None
        ):
            raise BodyAnalysisError(
                "체형 분석에 필요한 정보가 부족합니다. "
                "키, 몸무게, 또는 체형 특징 중 하나 이상을 입력해주세요.",
                code="insufficient",
            )

        # Step 2. GPT 비활성 상태면 키워드 폴백 직행
        if not self.gpt_enabled:
            return self.analyze_with_keywords(
                request.description, request.height, request.weight,
            )

        # Step 3. GPT 분석 시도
        try:
            return await self.analyze_with_gpt(
                request.description, request.height, request.weight,
            )

        # Step 4. GPT 실패 시 키워드 폴백 (에러 삼키기 금지 → 로깅 후 폴백)
        except BodyAnalysisError:
            # BodyAnalysisError는 이미 구조화된 예외
            # 키워드 폴백으로 서비스 연속성 보장
            # TODO 8단계: 로깅 시스템 연동 후 경고 레벨 로그 기록
            return self.analyze_with_keywords(
                request.description, request.height, request.weight,
            )

    # -------------------------------------------------------------------
    # 스타일 가이드
    # -------------------------------------------------------------------

    def get_style_guide(self, body_type: BodyType) -> str:
        """체형별 스타일 가이드를 반환합니다.

        챗봇 응답 생성 시 체형 분석 결과와 함께 제공됩니다.
        """
        return self._STYLE_GUIDES.get(
            body_type,
            "체형에 맞는 스타일을 찾아드릴게요!",
        )


# ===========================================================================
# ④ 팩토리 함수
# ===========================================================================

_analyzer_instance: BodyAnalyzer | None = None


def get_body_analyzer() -> BodyAnalyzer:
    """BodyAnalyzer 팩토리.

    런타임: BodyAnalyzer 싱글턴 반환
    테스트 주입 예시:
      app.dependency_overrides[get_body_analyzer] = lambda: MockAnalyzer()
    """
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = BodyAnalyzer()
    return _analyzer_instance
