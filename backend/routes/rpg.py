"""
rpg.py — RPG 게임 세이브/로드/거래 API
prefix: /api/rpg
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.rpg_models import (
    GameStateCreate,
    GameStateResponse,
    GameStateUpdate,
    TradeRequest,
    get_rpg_db,
)
from backend.services.rpg_logic import (
    save_game,
    load_game,
    list_saves,
    delete_game,
    update_game,
    buy_item,
    sell_item,
)

router = APIRouter(prefix="/api/rpg", tags=["rpg"])


@router.get("/health")
async def rpg_health_check(db: AsyncSession = Depends(get_rpg_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": str(e)}


@router.post("/save", response_model=GameStateResponse, status_code=201)
async def create_save(data: GameStateCreate, db: AsyncSession = Depends(get_rpg_db)):
    return await save_game(db, data)


@router.get("/load/{save_id}", response_model=GameStateResponse)
async def get_save(save_id: int, db: AsyncSession = Depends(get_rpg_db)):
    result = await load_game(db, save_id)
    if result is None:
        raise HTTPException(status_code=404, detail="저장 데이터 없음")
    return result


@router.get("/saves", response_model=list[GameStateResponse])
async def get_saves(db: AsyncSession = Depends(get_rpg_db)):
    return await list_saves(db)


@router.delete("/save/{save_id}")
async def remove_save(save_id: int, db: AsyncSession = Depends(get_rpg_db)):
    result = await delete_game(db, save_id)
    if result is False:
        raise HTTPException(status_code=404, detail="저장 데이터 없음")
    return {"message": "삭제 완료"}


@router.patch("/save/{save_id}", response_model=GameStateResponse)
async def patch_save(save_id: int, data: GameStateUpdate, db: AsyncSession = Depends(get_rpg_db)):
    result = await update_game(db, save_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="저장 데이터 없음")
    return result


@router.post("/trade/buy/{save_id}", response_model=GameStateResponse)
async def trade_buy(save_id: int, data: TradeRequest, db: AsyncSession = Depends(get_rpg_db)):
    return await buy_item(db, save_id, data)


@router.post("/trade/sell/{save_id}", response_model=GameStateResponse)
async def trade_sell(save_id: int, data: TradeRequest, db: AsyncSession = Depends(get_rpg_db)):
    return await sell_item(db, save_id, data)
