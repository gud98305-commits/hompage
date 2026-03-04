"""
chatbot.py — 챗봇 API 라우트
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from backend.services.chatbot import chat
from backend.services.turso_db import User, get_db

router = APIRouter(prefix="/api", tags=["chatbot"])


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class ChatResponse(BaseModel):
    reply: str
    is_personalized: bool = False


def _optional_user(
    authorization: str | None = Header(default=None),
    db=Depends(get_db),
) -> tuple:
    """로그인 유저면 User 반환, 아니면 None (데모 모드)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None, db
    from backend.routes.auth import decode_jwt
    try:
        payload = decode_jwt(authorization.split(" ", 1)[1])
        user = User.get_by_id(db, int(payload["sub"]))
        return user, db
    except Exception:
        return None, db


@router.post("/chat", response_model=ChatResponse)
def chatbot_endpoint(
    payload: ChatRequest,
    auth_info: tuple = Depends(_optional_user),
) -> ChatResponse:
    user, db = auth_info
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="메시지를 입력해주세요.")
    reply = chat(
        message=payload.message,
        user_id=user.id if user else None,
        db=db if user else None,
        conversation_history=payload.history,
    )
    return ChatResponse(
        reply=reply,
        is_personalized=user is not None,
    )
