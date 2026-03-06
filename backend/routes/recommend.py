from __future__ import annotations

import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.ai_curator import (
    curate_with_openai,
    _openai_select_complement,
    _product_matches_gender,
)
from backend.services.data_store import load_products
from shared.fx_converter import krw_to_jpy

router = APIRouter(prefix='/api', tags=['recommend'])


class RecommendRequest(BaseModel):
    gender: str = 'all'
    color: str = ''
    style: str = ''
    keyword: str = ''
    category: str = 'all'
    body_type: str = ''
    min_price_krw: int = 0
    max_price_krw: int = 99999999
    email: str | None = None
    page: int = Field(default=0, ge=0)
    page_size: int = Field(default=20, ge=1, le=100)


class RecommendResponse(BaseModel):
    items: list[dict] = Field(default_factory=list)
    total: int = 0


def _ensure_jpy(products: list[dict]) -> list[dict]:
    """price_jpy 미설정 상품만 복사 후 변환 — 캐시 원본 오염 방지."""
    result = []
    for item in products:
        if not item.get('price_jpy'):
            item = {**item, 'price_jpy': krw_to_jpy(int(item.get('price_krw', 0) or 0))}
        result.append(item)
    return result


@router.post('/recommend', response_model=RecommendResponse)
def recommend(payload: RecommendRequest) -> RecommendResponse:
    products = _ensure_jpy(load_products())
    if not products:
        return RecommendResponse(items=[], total=0)

    try:
        result = curate_with_openai(
            products, payload.model_dump(),
            page=payload.page, page_size=payload.page_size
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'OpenAI curation failed: {exc}') from exc
    return RecommendResponse(items=result['items'], total=result['total'])


@router.post('/recommend/', response_model=RecommendResponse, include_in_schema=False)
def recommend_slash(payload: RecommendRequest) -> RecommendResponse:
    return recommend(payload)


# ── 매치 컴플리먼트 ────────────────────────────────────────────────────

class MatchComplementRequest(BaseModel):
    current_item: dict = Field(default_factory=dict)
    gender: str = 'all'
    page_size: int = 2


@router.post('/match-complement')
def match_complement(payload: MatchComplementRequest) -> dict:
    products = _ensure_jpy(load_products())
    if not products:
        return {'items': []}

    current_cat = (payload.current_item.get('category') or '').lower()
    complement_cats: list[str] = {
        'top':    ['bottom'],
        'bottom': ['top'],
        'outer':  ['top', 'bottom'],
        'dress':  ['outer', 'top'],
    }.get(current_cat, ['top', 'bottom'])

    candidates = [
        p for p in products
        if (p.get('category', '').lower() in complement_cats
            and _product_matches_gender(p, payload.gender)
            and (p.get('is_clothing') or p.get('is_fashion')))
    ]

    if not candidates:
        return {'items': []}

    # 다양성: 매 호출마다 셔플 → AI에게 다른 40개 전달
    random.shuffle(candidates)
    sample = candidates[:40]

    selected = _openai_select_complement(payload.current_item, sample, n=payload.page_size)
    return {'items': selected}
