"""
game.py — 게임 저장/로드 API
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.routes.auth import get_current_user
from backend.services.turso_db import (
    GameResult,
    GameSession,
    InventoryItem,
    User,
    get_db,
    row_to_dict,
)

router = APIRouter(prefix="/api/game", tags=["game"])


class ItemData(BaseModel):
    product_id:   str
    name:         str = ""
    brand:        str = ""
    category:     str = ""
    sub_category: str = ""
    style:        str = ""
    colors:       list[str] = []
    tags:         list[str] = []
    image_url:    str = ""
    price_krw:    int = 0
    source_url:   str = ""


class GameSaveRequest(BaseModel):
    acquired_items:      list[ItemData] = []
    selected_styles:     list[str] = []
    selected_colors:     list[str] = []
    selected_categories: list[str] = []
    selected_keywords:   list[str] = []


class InventoryResponse(BaseModel):
    items: list[dict] = []
    total: int = 0


@router.post("/save")
def save_game(
    payload: GameSaveRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    # 1. 인벤토리 저장 (UNIQUE 제약으로 중복 자동 스킵)
    saved_ids: list[str] = []
    for item in payload.acquired_items:
        result = InventoryItem.create(db, current_user.id, item.dict())
        if result is not None:
            saved_ids.append(item.product_id)

    # 2. 게임 세션 기록 (ended_at, is_completed, items_count 포함)
    session_cur = db.execute(
        """INSERT INTO game_sessions
           (user_id, game_type, ended_at, is_completed, items_count)
           VALUES (?, ?, ?, ?, ?) RETURNING *""",
        (
            current_user.id,
            "fashion_curator",
            datetime.utcnow().isoformat(),
            1,
            len(payload.acquired_items),
        ),
    )
    session_row = session_cur.fetchone()
    db.commit()
    session = GameSession(row_to_dict(session_cur, session_row))

    # 3. 게임 결과 저장
    GameResult.create(db, current_user.id, session.id, {
        "selected_styles":     payload.selected_styles,
        "selected_colors":     payload.selected_colors,
        "selected_categories": payload.selected_categories,
        "selected_keywords":   payload.selected_keywords,
        "acquired_item_ids":   [i.product_id for i in payload.acquired_items],
        "style_profile":       "",
    })

    return {
        "ok":         True,
        "saved_items": len(saved_ids),
        "session_id":  session.id,
        "message":    f"{len(saved_ids)}개 아이템이 옷장에 추가됐어요!",
    }


@router.get("/inventory", response_model=InventoryResponse)
def get_inventory(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> InventoryResponse:
    items = InventoryItem.get_by_user(db, current_user.id, limit=1000)
    return InventoryResponse(
        items=[
            {
                "product_id":   i.product_id,
                "name":         i.name,
                "brand":        i.brand,
                "category":     i.category,
                "sub_category": i.sub_category,
                "style":        i.style,
                "colors":       i.colors or [],
                "tags":         i.tags or [],
                "image_url":    i.image_url,
                "price_krw":    i.price_krw,
                "source_url":   i.source_url,
                "obtained_at":  i.obtained_at if i.obtained_at else None,
            }
            for i in items
        ],
        total=len(items),
    )


@router.get("/history")
def get_history(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    results = GameResult.get_by_user(db, current_user.id, limit=20)

    style_counter:   dict[str, int] = {}
    color_counter:   dict[str, int] = {}
    keyword_counter: dict[str, int] = {}

    for r in results:
        for s in (r.selected_styles or []):
            style_counter[s] = style_counter.get(s, 0) + 1
        for c in (r.selected_colors or []):
            color_counter[c] = color_counter.get(c, 0) + 1
        for k in (r.selected_keywords or []):
            keyword_counter[k] = keyword_counter.get(k, 0) + 1

    top_styles   = sorted(style_counter,   key=style_counter.get,   reverse=True)[:3]
    top_colors   = sorted(color_counter,   key=color_counter.get,   reverse=True)[:3]
    top_keywords = sorted(keyword_counter, key=keyword_counter.get, reverse=True)[:3]

    return {
        "history": [
            {
                "session_id":       r.session_id,
                "selected_styles":  r.selected_styles,
                "selected_colors":  r.selected_colors,
                "selected_keywords": r.selected_keywords,
                "acquired_count":   len(r.acquired_item_ids or []),
                "saved_at":         r.saved_at if r.saved_at else None,
            }
            for r in results
        ],
        "preference_summary": {
            "top_styles":   top_styles,
            "top_colors":   top_colors,
            "top_keywords": top_keywords,
        },
    }
