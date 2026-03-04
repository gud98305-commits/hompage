"""
채찍피티 LLM 기반 의도 분류기 모듈.

AsyncOpenAI(GPT-4o-mini)로 사용자 메시지와 대화 맥락을 분석하여
의도를 분류합니다. GPT 실패 시 KeywordIntentClassifier 폴백.

구성:
① LLMIntentClassifier (IntentClassifier Protocol 구현)
② get_chat_service() 팩토리 교체 안내 (파일 하단 주석)
"""

from __future__ import annotations

import os

from openai import AsyncOpenAI

from backend.services.chatbot_advanced.chat_schemas import ChatTurn, IntentType
from backend.services.chatbot_advanced.chat_service import KeywordIntentClassifier


# ===========================================================================
# ① LLMIntentClassifier
# ===========================================================================

class LLMIntentClassifier:
    """LLM 기반 의도 분류기.

    GPT-4o-mini로 history 전체 맥락을 분석하여 의도를 분류합니다.
    GPT 실패 시 KeywordIntentClassifier로 자동 폴백합니다.
    """

    def __init__(self) -> None:
        """초기화 시 OPENAI_API_KEY 즉시 검증.

        키 없으면 gpt_enabled=False → KeywordIntentClassifier 폴백 직행.

        [운영 가이드]
        gpt_enabled=False 상태는 서버 재시작 전까지 복구되지 않습니다.

        TODO 8단계: Cascade Pattern 도입 권장
        classify() 내부에서 KeywordClassifier 먼저 실행 →
        GENERAL일 때만 GPT 호출하는 구조로 전환 시
        약 80% 요청의 응답속도 개선 및 GPT 비용 절감 가능
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print(
                "[LLMIntentClassifier] WARNING: OPENAI_API_KEY 미설정.\n"
                "KeywordIntentClassifier 폴백으로 동작합니다.\n"
                "GPT 기능 활성화는 환경변수 설정 후 서버 재시작 필요."
            )
            self.gpt_enabled: bool = False
            self._client: AsyncOpenAI | None = None
        else:
            self.gpt_enabled = True
            self._client = AsyncOpenAI(api_key=api_key)
        self._fallback = KeywordIntentClassifier()

    async def classify(
        self,
        message: str,
        history: list[ChatTurn],
    ) -> IntentType:
        """GPT로 history 전체 맥락 분석하여 의도 분류.

        KeywordClassifier 대비 장점:
        - "검정색으로 바꿔줘" 같은 맥락 의존 메시지 처리 가능
        - 부정문/복합 의도 처리 가능
        - Context Carry-over를 LLM이 자동으로 처리

        TODO 8단계: Cascade Pattern으로 전환
        현재: 모든 요청 → GPT (500ms~1s 지연)
        개선: KeywordClassifier 먼저 → GENERAL일 때만 GPT 호출
        예상 효과: 80% 요청 응답속도 개선, GPT 비용 절감
        """
        # Step 1. GPT 비활성 상태면 키워드 폴백 직행
        if not self.gpt_enabled:
            return await self._fallback.classify(message, history)

        # Step 2. GPT messages 구성
        # 최근 5턴만 포함 (의도 분류는 짧은 컨텍스트로 충분)
        # turn.content[:100] 트리밍:
        # 긴 content가 토큰 한도를 초과하는 것을 방지.
        # 턴 수 기준만으로는 content 길이를 보장할 수 없으므로
        # 글자 수 기준 트리밍을 병행 적용.
        # TODO 8단계: 누적 글자수(총 500자) 기준으로 개선 가능
        recent = history[-5:]
        context = "\n".join(
            f"{t.role}: {t.content[:100]}" for t in recent
        )

        gpt_messages = [
            {
                "role": "system",
                "content": (
                    "당신은 패션 챗봇의 의도 분류기입니다.\n"
                    "사용자 메시지와 대화 맥락을 분석하여\n"
                    "아래 4가지 중 하나만 반환하세요:\n\n"
                    "- body_analysis : 체형 분석 요청\n"
                    "- recommend     : 옷/스타일 추천 요청\n"
                    "- game_items    : 게임 아이템 연동 요청\n"
                    "- general       : 일반 패션 질문 또는 기타\n\n"
                    "소문자 단어 하나만 반환. 다른 설명 금지."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"[최근 대화]\n{context}\n\n"
                    f"[현재 메시지]\n{message[:200]}"
                    # 현재 메시지도 200자 제한 (토큰 비용 통제)
                ),
            },
        ]

        # Step 3. GPT 호출
        try:
            response = await self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=gpt_messages,
                max_tokens=10,
                temperature=0,
            )
            raw = (response.choices[0].message.content or "").strip().lower()

            # Step 4. 응답 파싱 → IntentType 반환
            # 매핑 실패 시 GENERAL로 안전하게 폴백
            intent_map = {
                "body_analysis": IntentType.BODY_ANALYSIS,
                "recommend": IntentType.RECOMMEND,
                "game_items": IntentType.GAME_ITEMS,
                "general": IntentType.GENERAL,
            }
            return intent_map.get(raw, IntentType.GENERAL)

        except Exception:
            # GPT 실패 시 KeywordClassifier 폴백 (서비스 연속성)
            # TODO 8단계: 로깅 시스템 연동
            return await self._fallback.classify(message, history)


# ===========================================================================
# ② get_chat_service() 팩토리 교체 안내
# ===========================================================================
#
# ===== 7단계 적용 시 chat_service.py 수정 필요 =====
#
# from llm_intent_classifier import LLMIntentClassifier
#
# def get_chat_service() -> ChatService:
#     global _chat_service_instance
#     if _chat_service_instance is None:
#         _chat_service_instance = ChatService(
#             classifier = LLMIntentClassifier(),  # ← KeywordClassifier 교체
#             rag_engine = get_rag_engine()
#         )
#     return _chat_service_instance
#
# TODO 8단계: Cascade Pattern 적용 시
# LLMIntentClassifier.classify() 내부에서
# KeywordClassifier 먼저 → GENERAL일 때만 GPT 호출로 전환
# =================================================
