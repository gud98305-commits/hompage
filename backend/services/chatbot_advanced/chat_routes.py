"""
OttO봇 챗봇 API 라우터.

모든 엔드포인트는 서비스 계층(ChatService) 호출만 수행하며
비즈니스 로직을 직접 구현하지 않습니다.

엔드포인트 5개:
- POST /api/chat              : 메인 대화
- POST /api/chat/analyze      : 체형 분석
- GET  /api/chat/recommend/{user_id}    : 맞춤 추천 조회
- GET  /api/chat/game-items/{user_id}   : 게임 담은 옷 조회
- GET  /api/chat/history/{session_id}   : 대화 기록 조회

main.py 연동 방법:
# from chat_routes import router as chat_router
# from backend.services.chatbot_advanced.chat_service import register_chat_exception_handlers
# app.include_router(chat_router)
# register_chat_exception_handlers(app)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.chatbot_advanced.chat_schemas import (
    BodyAnalysisRequest,
    ChatRequest,
    ChatResponse,
    ChatTurn,
)
from backend.services.chatbot_advanced.chat_service import ChatService, get_chat_service
from backend.services.chatbot_advanced.chat_db import get_db

router = APIRouter(prefix="/api/chat", tags=["chatbot"])


# ---------------------------------------------------------------------------
# POST /api/chat — 메인 대화
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ChatResponse,
    summary="OttO봇 메인 대화",
    description=(
        "OttO봇 AI 패션 챗봇과 대화합니다.\n\n"
        "[session_id 프로토콜 - 필독]\n"
        "- 최초 요청: session_id를 None 또는 생략하여 전송\n"
        "- 서버가 session_id를 생성하여 ChatResponse.session_id로 반환\n"
        "- 클라이언트는 반환된 session_id를 반드시 로컬 스토리지에 저장\n"
        "- 이후 모든 요청: ChatRequest.session_id에 저장된 값 포함\n"
        "- 미준수 시: 매 요청마다 새 세션 생성 → 대화 맥락 유지 불가"
    ),
)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """OttO봇 메인 대화 엔드포인트."""
    result = await service.process_chat(request, session=db)
    # 명시적 JSON 직렬화: response_model 자동 직렬화 과정에서
    # recommendations(list[ProductItem])가 누락되는 문제 방지
    return JSONResponse(content=result.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# POST /api/chat/analyze — 체형 분석
# ---------------------------------------------------------------------------

@router.post(
    "/analyze",
    response_model=ChatResponse,
    summary="체형 분석",
    description="사용자 체형 정보를 분석하여 wave/straight/neutral을 분류합니다.",
)
async def analyze_body(
    request: BodyAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """체형 분석 엔드포인트."""
    return await service.process_body_analysis(request, session=db)


# ---------------------------------------------------------------------------
# GET /api/chat/recommend/{user_id} — 맞춤 추천 조회
# ---------------------------------------------------------------------------

@router.get(
    "/recommend/{user_id}",
    response_model=ChatResponse,
    summary="사용자 맞춤 추천 조회",
)
async def get_recommendations(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """사용자 맞춤 추천 조회 엔드포인트."""
    return await service.get_recommendations(user_id, session=db)


# ---------------------------------------------------------------------------
# GET /api/chat/game-items/{user_id} — 게임 담은 옷 조회
# ---------------------------------------------------------------------------

@router.get(
    "/game-items/{user_id}",
    summary="게임에서 담은 옷 목록 조회",
)
async def get_game_items(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    service: ChatService = Depends(get_chat_service),
) -> dict:
    """게임 담은 옷 목록 조회 엔드포인트."""
    return await service.get_game_items(user_id, session=db)


# ---------------------------------------------------------------------------
# GET /api/chat/history/{session_id} — 대화 기록 조회
# ---------------------------------------------------------------------------

@router.get(
    "/history/{session_id}",
    response_model=list[ChatTurn],
    summary="대화 기록 조회",
)
async def get_chat_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    service: ChatService = Depends(get_chat_service),
) -> list[ChatTurn]:
    """대화 기록 조회 엔드포인트."""
    return await service.get_chat_history(session_id, session=db)
