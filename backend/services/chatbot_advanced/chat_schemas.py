"""
OttO봇 챗봇 스키마 정의 모듈.

7개 Pydantic V2 모델을 정의합니다:
① IntentType      - 사용자 의도 분류 열거형
② ChatTurn        - 대화 단일 턴
③ ProductItem     - SEOULFIT 상품 데이터
④ CuratorRequest  - ai_curator 연동 요청
⑤ ChatRequest     - 챗봇 요청
⑥ ChatResponse    - 챗봇 응답
⑦ BodyAnalysisRequest - 체형 분석 요청
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, BeforeValidator


# ---------------------------------------------------------------------------
# ① IntentType - 사용자 의도 분류
# ---------------------------------------------------------------------------
class IntentType(str, Enum):
    """사용자 메시지의 의도를 분류하는 열거형.

    7단계 의도 분류에서 LLMIntentClassifier가 반환하는 값입니다.
    TODO(7단계): KeywordClassifier → LLMIntentClassifier 교체 시 활용
    """

    BODY_ANALYSIS = "body_analysis"  # 체형 분석 요청
    RECOMMEND = "recommend"          # 패션 추천 요청
    GAME_ITEMS = "game_items"        # 성수 RPG 게임 아이템 연동
    GENERAL = "general"              # 일반 대화 / 기타


# ---------------------------------------------------------------------------
# ② ChatTurn - 대화 단일 턴
# ---------------------------------------------------------------------------
class ChatTurn(BaseModel):
    """대화 히스토리의 단일 턴을 나타내는 모델.

    멀티턴 대화에서 각 메시지의 역할과 내용을 저장합니다.
    """

    role: Literal["user", "assistant", "system", "tool"]
    # "user"      : 사용자가 입력한 메시지
    # "assistant" : 챗봇(AI)이 생성한 응답
    # "system"    : 시스템 프롬프트 (3단계 GPT 체형 분석 도입 시 활용)
    # "tool"      : Function Call / RAG 결과 (4단계 Corrective RAG 활용)

    content: str = Field(
        min_length=1,
        max_length=4096,
        description="턴 내용. 빈 문자열 차단(min=1), DoS/OOM 방어(max=4096)",
    )


# ---------------------------------------------------------------------------
# colors BeforeValidator 헬퍼
# ---------------------------------------------------------------------------
def _sanitize_colors(v: Any) -> list[str]:
    """colors 필드 Fail-safe BeforeValidator.

    SEOULFIT 크롤링 데이터의 오염(null, 비정상 타입 등)을 방어하여
    챗봇 전체 응답 실패를 방지합니다.

    동작 규칙:
    - 입력값이 None이면 빈 리스트([]) 반환
    - 입력값이 list가 아니면 빈 리스트([]) 반환
    - list 요소 중 str이 아닌 것은 str()로 강제 변환
    """
    if v is None:
        return []
    if not isinstance(v, list):
        return []
    return [str(item) if not isinstance(item, str) else item for item in v]


# ---------------------------------------------------------------------------
# ③ ProductItem - SEOULFIT 상품 데이터
# ---------------------------------------------------------------------------
class ProductItem(BaseModel):
    """SEOULFIT products_enriched 기반 상품 데이터 모델.

    ai_curator 추천 결과를 챗봇 응답에 포함할 때 사용합니다.
    """

    item_id: str
    name: str
    brand: str
    category: str  # top / bottom / outer / dress / shoes / accessory
    colors: Annotated[list[str], BeforeValidator(_sanitize_colors)] = Field(
        default=[],
        description="상품 색상 목록. SEOULFIT 데이터 오염 방어를 위해 BeforeValidator 적용",
    )

    price_jpy: int
    price_krw: int

    image_url: str | None = Field(
        default=None,
        description=(
            "상품 이미지 URL. SEOULFIT 크롤링 데이터 기반으로 "
            "원본 쇼핑몰 정책(Hotlinking 방지)에 따라 "
            "시간 경과 후 깨진 링크(Broken Link)가 될 수 있습니다. "
            "[프론트엔드 필수 처리] "
            "img 태그에 onError 핸들러를 반드시 구현하여 "
            "대체 이미지(placeholder)를 표시하세요. "
            "백엔드 URL 유효성 검증 시 응답 지연이 심각해지므로 "
            "프론트엔드 onError 처리를 강제합니다."
        ),
    )

    source_url: str | None = None
    reason: str = ""
    score: float | None = None
    mall: str

    @field_validator("score")
    @classmethod
    def _round_score(cls, v: float | None) -> float | None:
        """score 정밀도 보정 validator.

        부동소수점 연산 오차를 방지하기 위해
        None이 아닌 경우 소수점 둘째 자리로 반올림합니다.
        형식 검증만 수행하며 비즈니스 로직을 포함하지 않습니다.
        """
        if v is not None:
            return round(v, 2)
        return v


# ---------------------------------------------------------------------------
# ④ CuratorRequest - ai_curator 연동 요청
# ---------------------------------------------------------------------------
class CuratorRequest(BaseModel):
    """ai_curator 4단계 스코어링 엔진 연동용 요청 모델.

    챗봇 파이프라인에서 추천 의도 감지 시 ai_curator에 전달할
    필터 조건과 페이지네이션 정보를 담습니다.
    TODO(4단계): Corrective RAG 스코어 임계값 미달 시 조건부 GPT 호출
    """

    body_type: str | None = None   # wave / straight / neutral
    color: str | None = None
    style: str | None = None
    keyword: str | None = None
    category: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    page: int = Field(
        default=1,
        ge=1,
        description="페이지 번호 (1부터 시작)",
    )
    page_size: int = Field(
        default=10,
        ge=1,
        le=100,
        description=(
            "페이지 당 상품 수. "
            "ai_curator 페이지네이션 미지원 시 "
            "product_adapter 내부에서 메모리 슬라이싱으로 처리"
        ),
    )


# ---------------------------------------------------------------------------
# ⑤ ChatRequest - 챗봇 요청
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    """클라이언트 → 챗봇 서버 요청 모델.

    프론트엔드에서 사용자 메시지와 세션 정보를 전달할 때 사용합니다.
    """

    user_id: str = Field(
        min_length=1,
        description="사용자 고유 식별자",
    )
    message: str = Field(
        min_length=1,
        max_length=4096,
        description="사용자 입력 메시지. DoS/OOM 방어를 위해 최대 4096자 제한",
    )
    session_id: str | None = Field(
        default=None,
        description=(
            "대화 세션 ID. 최초 요청 시 None으로 보내면 서버가 생성하여 "
            "ChatResponse.session_id로 반환합니다. "
            "클라이언트는 반환된 session_id를 로컬 스토리지에 저장하고 "
            "이후 모든 요청에 반드시 포함해야 합니다. "
            "누락 시 매 요청마다 새 세션이 생성되어 대화 맥락이 유지되지 않습니다."
        ),
    )
    history: list[ChatTurn] = Field(
        default=[],
        max_length=50,
        description=(
            "대화 히스토리. Pydantic 앞단에서 최대 50턴으로 제한하여 DoS 방어. "
            "실제 사용은 서비스 계층에서 최신 10턴만 추출"
        ),
    )
    user_meta: dict = Field(
        default={},
        description="사용자 메타데이터 (확장용)",
    )


# ---------------------------------------------------------------------------
# ⑥ ChatResponse - 챗봇 응답
# ---------------------------------------------------------------------------
class ChatResponse(BaseModel):
    """챗봇 서버 → 클라이언트 응답 모델.

    챗봇의 텍스트 응답, 추천 상품, 의도 분류 결과를 포함합니다.
    """

    response: str
    recommendations: list[ProductItem] | None = None
    intent: IntentType
    session_id: str = Field(
        description=(
            "서버가 확정한 세션 ID. 최초 응답 시 반드시 저장하여 "
            "이후 요청의 ChatRequest.session_id에 포함하세요."
        ),
    )
    body_type: str | None = Field(
        default=None,
        description=(
            "체형 분석 결과. intent가 body_analysis일 때만 값이 채워집니다. "
            "가능한 값: 'wave' / 'straight' / 'neutral'. "
            "4단계에서 이 값을 CuratorRequest.body_type에 전달하여 "
            "체형 맞춤 추천에 활용하세요."
        ),
    )


# ---------------------------------------------------------------------------
# ⑦ BodyAnalysisRequest - 체형 분석 요청
# ---------------------------------------------------------------------------
class BodyAnalysisRequest(BaseModel):
    """체형 분석 전용 요청 모델.

    3단계 체형 분석에서 사용자의 신체 정보를 수집합니다.
    자연어 서술(description)은 GPT를 통해 체형 유형으로 변환됩니다.
    TODO(3단계): AsyncOpenAI로 자연어 서술 → wave/straight/neutral 변환
    """

    user_id: str = Field(
        min_length=1,
        description="사용자 고유 식별자",
    )
    session_id: str | None = None
    history: list[ChatTurn] = Field(
        default=[],
        max_length=50,
        description="대화 히스토리 (DoS 방어 max=50)",
    )
    height: float | None = Field(
        default=None,
        ge=50,
        le=250,
        description="키 (cm). 50~250 범위 제한",
    )
    weight: float | None = Field(
        default=None,
        ge=20,
        le=300,
        description="몸무게 (kg). 20~300 범위 제한",
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="체형 자연어 서술. 3단계에서 GPT가 체형 유형으로 변환",
    )
