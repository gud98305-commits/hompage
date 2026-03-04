"""번역 API 엔드포인트."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.translator import translate_batch

router = APIRouter(prefix="/api", tags=["translate"])


class TranslateRequest(BaseModel):
    texts: list[str]
    source: str = "ko"
    target: str = "ja"


class TranslateResponse(BaseModel):
    translations: list[str]


@router.post("/translate", response_model=TranslateResponse)
def translate(payload: TranslateRequest) -> TranslateResponse:
    translated = translate_batch(payload.texts, payload.source, payload.target)
    return TranslateResponse(translations=translated)
