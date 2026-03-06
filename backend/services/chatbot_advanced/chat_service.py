"""
OttO봇 챗봇 서비스 계층.

의도 분류(KeywordClassifier / LLMClassifier)와
ChatService(핸들러 라우팅 + 응답 생성)를 정의합니다.

구성:
① 예외 클래스 계층 (ChatServiceError 기반)
② IntentClassifier Protocol
③ KeywordIntentClassifier (키워드 기반 동기 매칭, async 인터페이스)
④ LLMIntentClassifier stub (7단계 교체 예정)
⑤ ChatService (의도 분류 → 핸들러 라우팅 → 응답 생성)
⑥ 의존성 팩토리 (get_chat_service)
⑦ 예외 핸들러 등록 (register_chat_exception_handlers)
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.chatbot_advanced.chat_schemas import (
    BodyAnalysisRequest,
    ChatRequest,
    ChatResponse,
    ChatTurn,
    CuratorRequest,
    IntentType,
    ProductItem,
)


# ===========================================================================
# ① 예외 클래스 계층
# ===========================================================================

class ChatServiceError(Exception):
    """챗봇 서비스 계층 기본 예외.

    모든 서비스 예외의 부모 클래스입니다.
    message: 사용자 노출 가능 메시지
    detail:  디버깅용 상세 정보
    """

    def __init__(self, message: str, detail: str = "") -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class IntentClassifyError(ChatServiceError):
    """의도 분류 실패 예외.

    KeywordClassifier 또는 LLMClassifier에서
    분류 불가능한 상황 발생 시 raise합니다.
    """


class RAGEngineError(ChatServiceError):
    """RAG 엔진(Corrective RAG) 예외.

    code 분류:
    - "timeout"   : OpenAI API 타임아웃 → 재시도 가능
    - "parse"     : 응답 파싱 실패     → 폴백 필요
    - "no_result" : 검색 결과 없음     → query refinement 필요
    - "unknown"   : 기타
    cause: 원본 예외 (디버깅용, __cause__ 체이닝)
    """

    def __init__(
        self,
        message: str,
        detail: str = "",
        code: str = "unknown",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, detail)
        self.code = code
        self.cause = cause


class GameDBError(ChatServiceError):
    """게임 DB 연동 예외.

    TODO 5단계: 성수 RPG 게임 DB 조회 실패 시 raise
    """


# ===========================================================================
# ② IntentClassifier Protocol
# ===========================================================================

class IntentClassifier(Protocol):
    """의도 분류기 프로토콜.

    KeywordIntentClassifier와 LLMIntentClassifier가 구현합니다.
    async 유지 이유: 7단계 LLMIntentClassifier(IO-bound) 교체 시
    호출부 코드 변경 없이 drop-in 교체 가능.

    주의: classify()에 AsyncSession을 주입하지 않습니다. (SRP)
    의도 분류는 순수 텍스트 분석이며 DB 접근이 불필요합니다.
    """

    async def classify(
        self,
        message: str,
        history: list[ChatTurn],
    ) -> IntentType: ...


# ===========================================================================
# ③ KeywordIntentClassifier
# ===========================================================================

class KeywordIntentClassifier:
    """키워드 기반 의도 분류기.

    공백 분리 토큰 매칭으로 사용자 의도를 분류합니다.
    Context Carry-over를 지원하여 멀티턴 대화의 맥락을 유지합니다.
    TODO 7단계: LLMIntentClassifier로 교체 예정
    """

    # 키워드 셋 — 외부 분리하여 테스트/운영 편의 확보
    # TODO: config.py 또는 DB 기반 키워드 관리로 전환 예정 (운영 유연성)
    GAME_KEYWORDS: set[str] = {"게임", "담은 옷", "인벤토리", "보관함"}
    BODY_KEYWORDS: set[str] = {"체형", "웨이브", "스트레이트", "뉴트럴", "골격", "분석"}
    RECOMMEND_KEYWORDS: set[str] = {"추천", "어울리는", "코디", "입을", "스타일"}

    # Context Carry-over용 후속 키워드
    _RECOMMEND_FOLLOWUP: set[str] = {"색상", "사이즈", "예산"}
    _BODY_FOLLOWUP: set[str] = {"골격", "체형"}
    _GAME_FOLLOWUP: set[str] = {"인벤토리", "보관함"}

    def _match_keywords(self, tokens: set[str]) -> IntentType:
        """토큰 셋 기반 우선순위 매칭.

        우선순위: GAME_ITEMS → BODY_ANALYSIS → RECOMMEND → GENERAL
        복합 의도: GAME_ITEMS + RECOMMEND 동시 감지 → RECOMMEND 우선
        (사용자가 게임 아이템 기반 추천을 원하는 것으로 판단)
        """
        has_game = bool(tokens & self.GAME_KEYWORDS)
        has_body = bool(tokens & self.BODY_KEYWORDS)
        has_recommend = bool(tokens & self.RECOMMEND_KEYWORDS)

        # 복합 의도 처리: 게임 + 추천 → 추천 우선
        if has_game and has_recommend:
            return IntentType.RECOMMEND

        if has_game:
            return IntentType.GAME_ITEMS
        if has_body:
            return IntentType.BODY_ANALYSIS
        if has_recommend:
            return IntentType.RECOMMEND

        return IntentType.GENERAL

    def _extract_last_intent(self, history: list[ChatTurn]) -> IntentType | None:
        """멀티턴 Context Carry-over: history에서 마지막 assistant 턴을
        분석하여 이전 대화의 intent를 추론합니다.

        추론 방식:
        - assistant 턴 content에 추천 후속 키워드("색상", "사이즈", "예산") 포함
          → RECOMMEND 반환
        - 체형 후속 키워드("골격", "체형") 포함
          → BODY_ANALYSIS 반환
        - 게임 후속 키워드("인벤토리", "보관함") 포함
          → GAME_ITEMS 반환
        - 해당 없으면 None 반환

        TODO 7단계: LLMIntentClassifier 교체 시 이 함수 제거.
        GPT가 history 전체 맥락으로 intent 추론하여 완전 대체.
        """
        # history를 역순으로 탐색하여 마지막 assistant 턴 찾기
        for turn in reversed(history):
            if turn.role == "assistant":
                content = turn.content

                # assistant 턴은 챗봇이 생성한 자연어 문장이므로
                # 한국어 조사("색상을", "체형에" 등)가 붙어 토큰 교집합 매칭 불가.
                # 부분 문자열 매칭(substring match)으로 후속 키워드를 검출합니다.
                if any(kw in content for kw in self._RECOMMEND_FOLLOWUP):
                    return IntentType.RECOMMEND
                if any(kw in content for kw in self._BODY_FOLLOWUP):
                    return IntentType.BODY_ANALYSIS
                if any(kw in content for kw in self._GAME_FOLLOWUP):
                    return IntentType.GAME_ITEMS

                # 첫 번째 assistant 턴만 확인 (가장 최근)
                break

        return None

    async def classify(
        self,
        message: str,
        history: list[ChatTurn],
    ) -> IntentType:
        """메시지 의도를 분류합니다.

        CPU-bound: 내부 로직은 동기 키워드 매칭입니다.
        IO-bound LLM 교체 대비 async 인터페이스를 유지합니다.
        """
        # Step A. 현재 메시지 토큰화 (split 기반 오탐 방지)
        # 단순 "in" 대신 공백 분리 토큰 매칭으로 오탐 감소
        # 예: "게임기" → {"게임기"} → "게임" 미매칭 (정확한 토큰만 매칭)
        # TODO: 형태소 분석기(Kiwi/Okt) 도입 시 토큰화 교체 예정
        tokens = set(message.split())

        # Step B. 현재 메시지 키워드 매칭
        current_intent = self._match_keywords(tokens)

        # Step C. Context Carry-over
        # 현재 메시지에서 명확한 intent 없는 경우(GENERAL)
        # history 마지막 assistant 턴의 intent를 이어받음
        # 예: 사용자 "검정색" → GENERAL이지만
        #     직전 챗봇이 "색상을 알려주세요" 였다면 → RECOMMEND 유지
        if current_intent == IntentType.GENERAL:
            last_intent = self._extract_last_intent(history)
            if last_intent is not None:
                return last_intent

        return current_intent


# ===========================================================================
# ④ LLMIntentClassifier (stub)
# ===========================================================================

class LLMIntentClassifier:
    """LLM 기반 의도 분류기 (stub).

    TODO 7단계: AsyncOpenAI로 복합/암묵적/상태 의존적 의도 분류
    history 전체를 GPT에 전달하여 Context Carry-over 완전 대체.
    폴백: OpenAI 실패 시 KeywordIntentClassifier로 자동 강등.
    """

    def __init__(self) -> None:
        self._fallback = KeywordIntentClassifier()

    async def classify(
        self,
        message: str,
        history: list[ChatTurn],
    ) -> IntentType:
        """LLM 기반 의도 분류 (미구현 stub).

        TODO 7단계:
        - AsyncOpenAI GPT-4o-mini 호출
        - system prompt에 IntentType 열거값 + 분류 기준 포함
        - history 전체를 messages로 전달
        - 응답 파싱 실패 시 KeywordClassifier 폴백
        """
        # stub: 폴백 분류기로 위임
        return await self._fallback.classify(message, history)


# ===========================================================================
# 카테고리 동의어 사전
# ===========================================================================

# 대분류 + 품목 동의어 확장
# TODO 7단계: LLM 기반 카테고리 추출로 교체 예정
CATEGORY_MAP: dict[str, str] = {
    # 상의
    "상의": "top", "티셔츠": "top", "맨투맨": "top",
    "니트": "top", "블라우스": "top", "셔츠": "top",
    # 하의
    "하의": "bottom", "바지": "bottom", "슬랙스": "bottom",
    "청바지": "bottom", "스커트": "bottom", "반바지": "bottom",
    # 아우터
    "아우터": "outer", "코트": "outer", "자켓": "outer",
    "점퍼": "outer", "패딩": "outer", "가디건": "outer",
    # 원피스
    "원피스": "dress", "드레스": "dress",
    # 신발
    "신발": "shoes", "구두": "shoes", "스니커즈": "shoes",
    "부츠": "shoes", "샌들": "shoes", "로퍼": "shoes",
    # 악세사리
    "악세사리": "accessory", "가방": "accessory",
    "벨트": "accessory", "모자": "accessory", "스카프": "accessory",
}
# 영문 직접 입력도 허용 (top/bottom/outer/dress/shoes/accessory)


# ===========================================================================
# ⑤ ChatService
# ===========================================================================

class ChatService:
    """챗봇 서비스 메인 클래스.

    의도 분류 → 핸들러 라우팅 → 응답 생성의 파이프라인을 담당합니다.
    Depends 주입 구조로 FastAPI 라우터에서 사용합니다.
    """

    def __init__(
        self,
        classifier: IntentClassifier | None = None,
        rag_engine: Any | None = None,
    ) -> None:
        self.classifier: IntentClassifier = classifier or KeywordIntentClassifier()
        # rag_engine을 __init__에서 주입받아 강한 결합 해소
        # 테스트 시: ChatService(rag_engine=MockRAGEngine())으로 주입 가능
        # 순환 import 방지를 위해 타입 힌트는 Any로 선언
        if rag_engine is not None:
            self.rag_engine: Any = rag_engine
        else:
            from backend.services.chatbot_advanced.rag_engine import get_rag_engine
            self.rag_engine = get_rag_engine()

    # -------------------------------------------------------------------
    # 유틸리티
    # -------------------------------------------------------------------

    def _safe_float(self, value: Any) -> float | None:
        """user_meta 등 외부 입력값을 float으로 안전하게 변환.

        문자열("168"), 잘못된 타입 등 변환 실패 시 None 반환.

        클래스 메서드로 정의하여 _handle_body_analysis,
        process_body_analysis 등 여러 핸들러에서 재사용 가능.
        # TODO: 다른 핸들러에서 user_meta 파싱 필요 시 이 메서드 활용
        """
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    # -------------------------------------------------------------------
    # 메인 파이프라인
    # -------------------------------------------------------------------

    async def process_chat(
        self,
        request: ChatRequest,
        session: AsyncSession,
    ) -> ChatResponse:
        """채팅 요청을 처리하여 응답을 생성합니다.

        Step 1~6의 파이프라인을 순차 실행합니다.
        """
        # Step 1. session_id 확정
        session_id = request.session_id or str(uuid.uuid4())
        # 주의: 로드밸런서 환경에서 session_id 없이 동시 요청 시
        # 각 인스턴스가 다른 ID 생성 가능.
        # TODO: 클라이언트가 첫 응답 session_id 저장 후
        #       이후 요청에 반드시 포함하는 프로토콜 정의 필요

        # [입력 위생 검사] — process_chat Step 1 직후
        from backend.services.chatbot_advanced.input_sanitizer import get_sanitizer
        sanitizer = get_sanitizer()
        is_safe, cleaned_message = sanitizer.sanitize(request.message)

        if not is_safe:
            # 인젝션 시도 감지 → 로그 기록 + 경고 응답 반환
            # OttO봇 페르소나 유지: 위협적 응답 금지
            from backend.services.chatbot_advanced.logger import get_logger
            get_logger().injection_detected(
                module="ChatService.process_chat",
                user_id=request.user_id,
                message_preview=request.message,
            )
            return ChatResponse(
                response=(
                    "저는 패션 조언만 도와드릴 수 있어요! "
                    "코디 추천이나 체형 분석을 원하시면 말씀해주세요 😊"
                ),
                recommendations=None,
                intent=IntentType.GENERAL,
                session_id=session_id,
                body_type=None,
            )
        # 이후 로직은 cleaned_message 사용
        # Pydantic V2 불변 객체 수정 방식: model_copy()로 새 인스턴스 생성
        request = request.model_copy(update={"message": cleaned_message})

        # Step 2. history truncate (최신 10턴, 서비스 계층 책임)
        # Pydantic max_length=50 으로 1차 차단 (DoS 방어)
        # 서비스에서 실제 사용할 최신 10턴만 추출
        history = request.history[-10:]

        # Step 3. 의도 분류 (Context Carry-over 포함, DB 세션 비점유)
        # KeywordClassifier: 현재 키워드 없으면 history로 보완
        # LLMClassifier(7단계): history 전체 맥락으로 정확한 분류
        try:
            intent = await self.classifier.classify(request.message, history)
        except Exception as e:
            raise IntentClassifyError(
                message="의도 분류에 실패했습니다.",
                detail=str(e),
            ) from e

        # Step 4. 핸들러 라우팅
        # 주의: ai_curator 등 Long-running 외부 호출 발생 지점
        # DB 커넥션 풀 점유 최소화 위해 Step 5(DB 저장)와 명확히 분리
        response_text, recommendations, body_type = await self._route(
            intent, request, history, session
        )

        # Step 5. 히스토리 DB 저장
        # TODO 2단계: ChatHistory 테이블 스키마 확정 후 구현
        #
        # [권장 구현 패턴 - BackgroundTasks 활용]
        # 히스토리 저장은 사용자 응답과 무관한 부가 작업 → 백그라운드 처리
        # 응답 반환 후 저장하여 사용자 체감 응답 시간 단축:
        #
        # def save_history_task(session_id, user_msg, assistant_msg):
        #     async with AsyncSessionLocal() as bg_session:
        #         async with bg_session.begin():    ← 트랜잭션 최소 범위
        #             bg_session.add(ChatHistory(...user_msg))
        #             bg_session.add(ChatHistory(...assistant_msg))
        #
        # background_tasks.add_task(save_history_task, ...)
        # → process_chat 시그니처에 background_tasks: BackgroundTasks 추가
        # → chat_routes.py에서 FastAPI BackgroundTasks Depends로 주입
        #
        # [트랜잭션 격리 원칙]
        # async with session.begin(): 블록을 저장 로직만 감싸도록 한정
        # Step 3~4의 Long-running 작업과 절대 혼재 금지

        # Step 6. ChatResponse 반환
        return ChatResponse(
            response=response_text,
            recommendations=recommendations,
            intent=intent,
            session_id=session_id,
            body_type=body_type,
        )

    # -------------------------------------------------------------------
    # 핸들러 라우팅
    # -------------------------------------------------------------------

    async def _route(
        self,
        intent: IntentType,
        request: ChatRequest,
        history: list[ChatTurn],
        session: AsyncSession,
    ) -> tuple[str, list[ProductItem] | None, str | None]:
        """의도별 핸들러로 라우팅합니다.

        Returns:
            (응답 텍스트, 추천 상품 리스트 또는 None, body_type 또는 None)
        """
        if intent == IntentType.BODY_ANALYSIS:
            return await self._handle_body_analysis(request, history, session)
        if intent == IntentType.RECOMMEND:
            return await self._handle_recommend(request, history, session)
        if intent == IntentType.GAME_ITEMS:
            return await self._handle_game_items(request, history, session)
        return await self._handle_general(request, history, session)

    # -------------------------------------------------------------------
    # 의도별 핸들러
    # -------------------------------------------------------------------

    async def _handle_general(
        self,
        request: ChatRequest,
        history: list[ChatTurn],
        session: AsyncSession,
    ) -> tuple[str, list[ProductItem] | None, str | None]:
        """GPT 직접 호출 폴백 핸들러.

        의도 분류 실패 또는 general 의도 시 실행.

        TODO 8단계: Cascade Pattern 도입 권장
        KeywordClassifier → GENERAL일 때만 LLM 호출하는 구조로 전환 시
        약 80% 요청의 응답속도 개선 및 GPT 비용 절감 가능
        """
        # Step 1. OpenAI 클라이언트 초기화
        # API 키 없으면 기본 안내 메시지 반환 (서비스 연속성)
        import os
        from openai import AsyncOpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return (
                "안녕하세요! OttO봇입니다. "
                "현재 AI 기능이 비활성화 상태예요. "
                "체형 분석이나 상품 추천을 원하시면 말씀해주세요!",
                None,
                None,
            )
        client = AsyncOpenAI(api_key=api_key)

        # Step 2. history → GPT messages 변환
        # 최근 10턴만 포함 (토큰 비용 통제)
        # turn.content[:200] 트리밍:
        # 사용자가 긴 텍스트를 붙여넣기 시 토큰 초과 방지.
        # 턴 수 기준만으로는 content 길이를 보장할 수 없으므로
        # 글자 수 기준 트리밍을 병행 적용.
        # TODO 8단계: 턴 수 기준 → 누적 글자수(총 2000자) 기준으로 개선 가능
        gpt_messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "당신은 한국의 AI 패션 어드바이저 'OttO봇'입니다. "
                    "사용자의 체형, 선호도, 상황에 맞는 패션 조언을 제공합니다. "
                    "친근하고 전문적인 톤으로 답변하세요. "
                    "답변은 3문장 이내로 간결하게 작성하세요."
                ),
            }
        ]
        for turn in history[-10:]:
            gpt_messages.append({
                "role": turn.role if turn.role in ("user", "assistant") else "user",
                "content": turn.content[:200],
                # 글자 수 기준 트리밍: 토큰 초과 방지
            })
        gpt_messages.append({
            "role": "user",
            "content": request.message[:500],
            # 현재 메시지도 500자 제한
            # (1-A max_length=4096이나 GPT 전송 시 추가 절감)
        })

        # Step 3. GPT 호출
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=gpt_messages,
                max_tokens=300,
                temperature=0.7,
            )
            answer = (response.choices[0].message.content or "").strip()

        except Exception as e:
            from backend.services.chatbot_advanced.logger import get_logger
            get_logger().gpt_fallback(
                module="ChatService._handle_general",
                reason="GPT 호출 실패",
                exc=e,
            )
            answer = (
                "죄송해요, 잠시 오류가 발생했어요. "
                "체형 분석이나 상품 추천을 원하시면 말씀해주세요!"
            )

        # Step 4. 응답 반환
        return answer, None, None

    async def _handle_body_analysis(
        self,
        request: ChatRequest,
        history: list[ChatTurn],
        session: AsyncSession,
    ) -> tuple[str, list[ProductItem] | None, str | None]:
        """체형 분석 핸들러.

        body_analyzer.py의 BodyAnalyzer를 호출하여
        사용자 메시지와 user_meta로부터 체형을 분류합니다.
        BodyAnalysisError/ValidationError 발생 시 사용자 안내 메시지를 반환합니다.
        """
        # 순환 import 방어: body_analyzer → chat_service 역참조 존재
        from backend.services.chatbot_advanced.body_analyzer import get_body_analyzer

        # Step 1. BodyAnalyzer 가져오기
        analyzer = get_body_analyzer()

        # Step 2. user_meta에서 height·weight Safe Casting
        # 프론트엔드가 문자열("168")이나 잘못된 값을 보낼 수 있으므로
        # self._safe_float()으로 안전하게 변환
        height = self._safe_float(request.user_meta.get("height"))
        weight = self._safe_float(request.user_meta.get("weight"))

        # Step 3. ChatRequest → BodyAnalysisRequest 변환
        # Pydantic ValidationError 방어: height/weight 범위 초과 시
        # (height ge=50, le=250 / weight ge=20, le=300)
        # ValidationError가 발생하므로 사용자 안내 메시지로 변환
        try:
            analysis_request = BodyAnalysisRequest(
                user_id     = request.user_id,
                session_id  = request.session_id,
                history     = request.history,
                description = request.message,
                height      = height,
                weight      = weight,
            )
        except Exception:
            return (
                "입력하신 키 또는 몸무게 값이 유효 범위를 벗어났습니다. "
                "키는 50~250cm, 몸무게는 20~300kg 범위로 입력해주세요 📐",
                None,
                None,
            )

        # Step 4. 체형 분석 실행
        # BodyAnalysisError 방어: 정보 부족/GPT 실패 등
        try:
            body_type = await analyzer.analyze(analysis_request)
        except ChatServiceError as e:
            from backend.services.chatbot_advanced.logger import get_logger
            get_logger().gpt_fallback(
                module="ChatService._handle_body_analysis",
                reason="체형 분석 GPT 실패 → 키워드 폴백",
                exc=e,
            )
            return (
                "체형 분석에 필요한 정보가 부족합니다. "
                "키, 몸무게, 또는 체형 특징을 더 자세히 알려주세요 📐",
                None,
                None,
            )

        # Step 5. 체형 결과를 DB에 저장 (로그인 유저만)
        if request.user_id:
            try:
                from backend.services.turso_db import User as TursoUser, _get_connection
                conn = _get_connection()
                try:
                    TursoUser.update_body_type(conn, int(request.user_id), body_type.value)
                finally:
                    conn.close()
            except Exception:
                pass  # 저장 실패해도 응답은 정상 반환

        # Step 6. 스타일 가이드 획득
        style_guide = analyzer.get_style_guide(body_type)

        # Step 7. 응답 생성 (body_type.value를 3번째 요소로 전달)
        response = (
            f"{style_guide}\n\n"
            "체형에 맞는 옷을 추천받고 싶으시면 "
            "'추천해줘'라고 말씀해 주세요!"
        )
        return response, None, body_type.value

    async def _handle_recommend(
        self,
        request: ChatRequest,
        history: list[ChatTurn],
        session: AsyncSession,
    ) -> tuple[str, list[ProductItem] | None, str | None]:
        """패션 추천 핸들러.

        product_adapter → Corrective RAG 파이프라인을 실행합니다.
        """
        # Step 1. body_type 추출 (user_meta 우선 → DB fallback)
        body_type = request.user_meta.get("body_type")
        if not body_type and request.user_id:
            try:
                from backend.services.turso_db import User as TursoUser, _get_connection
                conn = _get_connection()
                try:
                    user = TursoUser.get_by_id(conn, int(request.user_id))
                    if user and user.body_type:
                        body_type = user.body_type
                finally:
                    conn.close()
            except Exception:
                pass

        # Step 2. 유저 선호도 조회 (위시리스트 + 게임 히스토리)
        pref_style = None
        pref_color = None
        if request.user_id:
            try:
                from backend.services.turso_db import _get_connection, Wishlist, GameResult
                from backend.services.data_store import find_product
                conn = _get_connection()
                try:
                    # 위시리스트 → 선호 스타일 추출
                    wish_items = Wishlist.get_by_user(conn, int(request.user_id))
                    wish_styles = []
                    for w in wish_items[:10]:
                        prod = find_product(w.product_id)
                        if prod and prod.get("style"):
                            wish_styles.append(prod["style"])
                    if wish_styles:
                        from collections import Counter
                        pref_style = Counter(wish_styles).most_common(1)[0][0]

                    # 게임 결과 → 선호 색상/스타일
                    results = GameResult.get_by_user(conn, int(request.user_id), limit=5)
                    all_colors = []
                    all_styles = []
                    for r in results:
                        all_colors.extend(r.selected_colors or [])
                        all_styles.extend(r.selected_styles or [])
                    if all_colors:
                        from collections import Counter
                        pref_color = Counter(all_colors).most_common(1)[0][0]
                    if all_styles and not pref_style:
                        from collections import Counter
                        pref_style = Counter(all_styles).most_common(1)[0][0]
                finally:
                    conn.close()
            except Exception:
                pass  # 선호도 조회 실패해도 기본 추천 진행

        # Step 3. 메시지에서 카테고리 추출 (동의어 사전 기반)
        category = None
        for keyword, cat in CATEGORY_MAP.items():
            if keyword in request.message:
                category = cat
                break

        # Step 4. CuratorRequest 구성
        from backend.services.chatbot_advanced.chat_service import KeywordIntentClassifier
        stop_words = KeywordIntentClassifier.RECOMMEND_KEYWORDS | {"해줘", "부탁해", "알려줘", "오늘"}
        cleaned_words = [w for w in request.message.split() if w not in stop_words]
        final_keyword = " ".join(cleaned_words)[:100]

        curator_req = CuratorRequest(
            body_type=body_type,
            keyword=final_keyword,
            category=category,
            style=pref_style,       # 위시리스트/게임에서 추출한 선호 스타일
            color=pref_color,       # 게임에서 추출한 선호 색상
            page=1,
            page_size=5,
        )

        # Step 4. product_adapter로 1차 검색
        try:
            from backend.services.chatbot_advanced.product_adapter import get_products_by_curator
            products = await get_products_by_curator(curator_req)
        except RAGEngineError as e:
            if e.code == "no_result":
                return (
                    "죄송해요, 조건에 맞는 상품을 찾지 못했어요. "
                    "다른 스타일이나 카테고리로 다시 시도해보세요!",
                    None,
                    None,
                )
            return (
                "상품 검색 중 오류가 발생했어요. "
                "잠시 후 다시 시도해주세요!",
                None,
                None,
            )

        # Step 5. Corrective RAG 레이어 통과 (self.rag_engine 사용)
        # __init__에서 주입받은 인스턴스 사용 → 테스트 시 Mock 교체 가능
        try:
            products: list[ProductItem] = await self.rag_engine.run(
                products, curator_req,
            )
        except Exception:
            # RAG 실패 시 1차 검색 결과 그대로 사용 (서비스 연속성)
            pass

        # Step 6. 응답 텍스트 생성
        if not products:
            return (
                "조건에 맞는 상품을 찾지 못했어요. "
                "다른 키워드로 다시 시도해보세요!",
                None,
                None,
            )

        body_map = {
            "wave": "곡선형 체형에 어울리는",
            "straight": "직선형 체형에 어울리는",
            "neutral": "균형잡힌 체형에 어울리는",
        }
        body_guide = body_map.get(body_type or "", "")
        prefix = f"{body_guide} " if body_guide else ""

        response = (
            f"{prefix}상품 {len(products)}개를 추천드려요! "
            "아래 상품들을 확인해보세요 😊"
        )
        return response, products, None
        # TODO 5단계: game_items 연동 시 게임 담은 옷 기반 추천으로 확장

    async def _handle_game_items(
        self,
        request: ChatRequest,
        history: list[ChatTurn],
        session: AsyncSession,
    ) -> tuple[str, list[ProductItem] | None, str | None]:
        """게임 아이템 조회 핸들러.

        게임 DB → 도메인 변환 → product_adapter 검색 → Corrective RAG
        파이프라인을 실행합니다.
        """
        # Step 1. 게임 DB에서 담은 옷 조회
        from backend.services.chatbot_advanced.game_adapter import get_game_repo, GameDBError, GameItemToProductAdapter
        repo = get_game_repo()
        try:
            game_items = await repo.get_saved_items(
                user_id=request.user_id,
                session=session,
                limit=10,
            )
        except GameDBError as e:
            if e.code == "query_failed":
                from backend.services.chatbot_advanced.logger import get_logger
                get_logger().db_error(
                    module="ChatService._handle_game_items",
                    user_id=request.user_id,
                    exc=e,
                )
            if e.code in ("not_found", "empty"):
                return (
                    "게임에서 담은 옷이 없어요. "
                    "게임에서 마음에 드는 옷을 먼저 담아보세요! 🎮",
                    None,
                    None,
                )
            return "게임 데이터를 불러오는 중 오류가 발생했어요.", None, None
        # TODO: WAL 모드 지연으로 최신 데이터 미반영 가능성 있음.
        # 프론트엔드에서 아이템 저장 후 500ms 지연 후 조회 요청 권장.
        # 8단계 통합 테스트 시 실제 지연 여부 확인 필요.

        # Step 2. GameItem → CuratorRequest 변환
        body_type = request.user_meta.get("body_type")
        curator_req = GameItemToProductAdapter.to_curator_request(
            items=game_items,
            body_type=body_type,
            page_size=5,
        )

        # Step 3. product_adapter로 1차 검색 (게임 아이템 기반 키워드)
        products: list[ProductItem] = []
        try:
            from backend.services.chatbot_advanced.product_adapter import get_products_by_curator
            products = await get_products_by_curator(curator_req)
        except RAGEngineError as e:
            if e.code == "no_result":
                # [Broad Search 폴백]
                # 게임 아이템명이 현실 쇼핑몰에 없을 가능성이 높음.
                # 키워드 검색 실패 시 category + body_type + color로
                # 넓게 재검색하여 최소한의 추천 결과 보장.
                # category 단독 검색 시 계절/스타일 무관 상품 노출 위험이 있으므로
                # 가용한 컨텍스트 정보를 최대한 활용하여 검색 범위 축소.
                try:
                    from backend.services.chatbot_advanced.product_adapter import search_products_simple
                    broad_keyword = " ".join(filter(None, [
                        curator_req.color,  # 색상 정보 유지
                        body_type,          # 체형 정보 유지
                    ]))
                    products = await search_products_simple(
                        keyword=broad_keyword or "",
                        category=curator_req.category,
                        limit=5,
                    )
                    # TODO 7단계: LLM이 게임 아이템 문맥 전체를 해석하여
                    # 시즌/스타일까지 반영한 정교한 쿼리 생성으로 교체 예정
                except Exception:
                    return (
                        "게임에서 담으신 아이템과 어울리는 상품을 "
                        "찾지 못했어요. 직접 추천을 요청해보세요!",
                        None,
                        None,
                    )
            else:
                return "상품 검색 중 오류가 발생했어요.", None, None

        # Step 4. Corrective RAG 레이어
        # self.rag_engine: __init__에서 주입받아 Mock 교체 가능
        try:
            products = await self.rag_engine.run(products, curator_req)
        except Exception:
            pass  # RAG 실패 시 1차 검색 결과 사용 (서비스 연속성)

        # Step 5. 응답 텍스트 생성
        if not products:
            return (
                "조건에 맞는 상품을 찾지 못했어요. "
                "다른 키워드로 추천받아 보세요!",
                None,
                None,
            )
        item_names = ", ".join(item.name for item in game_items[:3])
        response = (
            f"게임에서 담으신 [{item_names}] 아이템과 "
            f"어울리는 상품 {len(products)}개를 추천드려요! 🎮"
        )
        return response, products, None

    # -------------------------------------------------------------------
    # 추가 stub 메서드 (세션 포함)
    # -------------------------------------------------------------------

    async def process_body_analysis(
        self,
        request: BodyAnalysisRequest,
        session: AsyncSession,
    ) -> ChatResponse:
        """체형 분석 전용 처리.

        POST /api/chat/analyze 엔드포인트에서 호출됩니다.
        BodyAnalysisRequest 기반으로 체형 분석 파이프라인을 실행합니다.
        """
        # 순환 import 방어: body_analyzer → chat_service 역참조 존재
        from backend.services.chatbot_advanced.body_analyzer import get_body_analyzer

        # Step 1. 입력 검증
        # description·height·weight 모두 None이면 분류 불가
        if (
            request.description is None
            and request.height is None
            and request.weight is None
        ):
            raise ChatServiceError("체형 정보를 입력해주세요")

        # Step 2. BodyAnalyzer 실행
        analyzer  = get_body_analyzer()
        body_type = await analyzer.analyze(request)

        # Step 3. 스타일 가이드 포함 응답 생성
        style_guide = analyzer.get_style_guide(body_type)
        response = (
            f"{style_guide}\n\n"
            f"분석된 체형: {body_type.value}\n"
            "이 체형에 맞는 옷을 추천받고 싶으시면 말씀해 주세요!"
        )

        # Step 4. ChatResponse 반환 (body_type 필드 포함)
        return ChatResponse(
            response        = response,
            recommendations = None,
            intent          = IntentType.BODY_ANALYSIS,
            session_id      = request.session_id or str(uuid.uuid4()),
            body_type       = body_type.value,
        )
        # TODO 4단계: recommendations에 체형 맞춤 추천 상품 바로 포함 가능

    async def get_recommendations(
        self,
        user_id: str,
        session: AsyncSession,
    ) -> ChatResponse:
        """GET /api/chat/recommend/{user_id} 전용 진입점."""
        # Step 1. 기본 CuratorRequest (체형 미지정)
        curator_req = CuratorRequest(page=1, page_size=5)

        # Step 2. 상품 검색
        try:
            from backend.services.chatbot_advanced.product_adapter import get_products_by_curator
            products = await get_products_by_curator(curator_req)
        except RAGEngineError:
            return ChatResponse(
                response="현재 추천 서비스를 이용할 수 없어요.",
                recommendations=None,
                intent=IntentType.RECOMMEND,
                session_id=str(uuid.uuid4()),
                body_type=None,
            )

        # Step 3. Corrective RAG (self.rag_engine 사용)
        try:
            products: list[ProductItem] = await self.rag_engine.run(
                products, curator_req,
            )
        except Exception:
            pass

        # Step 4. ChatResponse 반환
        return ChatResponse(
            response=f"추천 상품 {len(products)}개를 준비했어요!",
            recommendations=products or None,
            intent=IntentType.RECOMMEND,
            session_id=str(uuid.uuid4()),
            body_type=None,
        )
        # TODO 5단계: user_id로 게임 DB 조회 후 담은 옷 기반 추천 강화

    async def get_game_items(
        self,
        user_id: str,
        session: AsyncSession,
    ) -> dict:
        """GET /api/chat/game-items/{user_id} 전용 진입점."""
        # Step 1. 게임 DB 조회
        from backend.services.chatbot_advanced.game_adapter import get_game_repo, GameDBError
        repo = get_game_repo()
        try:
            game_items = await repo.get_saved_items(
                user_id=user_id,
                session=session,
                limit=20,
            )
        except GameDBError as e:
            return {
                "user_id": user_id,
                "items": [],
                "count": 0,
                "message": (
                    "게임에서 담은 옷이 없어요."
                    if e.code == "not_found"
                    else "게임 데이터 조회 실패"
                ),
            }

        # Step 2. 응답 구성
        return {
            "user_id": user_id,
            "items": [item.model_dump() for item in game_items],
            "count": len(game_items),
            "message": f"{len(game_items)}개의 아이템을 담으셨어요!",
        }
        # TODO 6단계: 프론트엔드 chatbot.js에서
        # 이 응답을 챗봇 UI 아이템 목록으로 렌더링

    async def get_chat_history(
        self,
        session_id: str,
        session: AsyncSession,
    ) -> list[ChatTurn]:
        """대화 히스토리 조회 (stub).

        TODO 2단계: ChatHistory 테이블에서 session_id 기반 조회
        """
        return []


# ===========================================================================
# ⑥ 의존성 팩토리
# ===========================================================================

_chat_service_instance: ChatService | None = None


def get_chat_service() -> ChatService:
    """ChatService 의존성 팩토리 (싱글턴).

    FastAPI Depends()로 주입합니다.
    싱글턴으로 LLMIntentClassifier·CorrectiveRAGEngine 재생성을 방지합니다.
    테스트 주입 예시:
      app.dependency_overrides[get_chat_service] = lambda: MockChatService()
    """
    global _chat_service_instance
    if _chat_service_instance is None:
        from backend.services.chatbot_advanced.llm_intent_classifier import LLMIntentClassifier
        from backend.services.chatbot_advanced.rag_engine import get_rag_engine
        _chat_service_instance = ChatService(
            classifier=LLMIntentClassifier(),
            # KeywordIntentClassifier → LLMIntentClassifier 교체.
            # LLMIntentClassifier 내부에서 GPT 실패 시
            # KeywordIntentClassifier로 자동 폴백하므로
            # 호출부 변경 없이 안전하게 교체 가능.
            # TODO: 8단계 Cascade Pattern 도입 시
            # LLMIntentClassifier.classify() 내부에서
            # KeywordClassifier 먼저 → GENERAL일 때만 GPT 호출로 전환.
            rag_engine=get_rag_engine(),
        )
    return _chat_service_instance


# ===========================================================================
# ⑦ 예외 핸들러 등록
# ===========================================================================

def register_chat_exception_handlers(app: FastAPI) -> None:
    """ChatServiceError 계층 예외 핸들러를 FastAPI 앱에 등록합니다.

    모든 ChatServiceError 하위 예외를 422 상태 코드로 통일 반환합니다.
    에러를 삼키지 않고 구조화된 JSON으로 클라이언트에 전달합니다.
    """

    @app.exception_handler(ChatServiceError)
    async def _handle_chat_service_error(
        request: object,
        exc: ChatServiceError,
    ) -> JSONResponse:
        """ChatServiceError 통합 핸들러."""
        return JSONResponse(
            status_code=422,
            content={"error": exc.message, "detail": exc.detail},
        )
