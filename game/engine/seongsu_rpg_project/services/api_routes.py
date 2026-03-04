# API 라우터/엔드포인트 모듈 (API Routes)
# 라우터에서 commit/rollback 호출 금지 — 위임만 담당

from fastapi import APIRouter
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from models.database import get_db
from models.schemas import GameStateCreate, GameStateResponse, GameStateUpdate, TradeRequest
from services.game_logic import save_game, load_game, list_saves, delete_game, update_game, buy_item, sell_item

router = APIRouter()


@router.get("/api/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": str(e)}


@router.post("/api/save", response_model=GameStateResponse, status_code=201)
async def create_save(data: GameStateCreate, db: AsyncSession = Depends(get_db)):
    return await save_game(db, data)


@router.get("/api/load/{save_id}", response_model=GameStateResponse)
async def get_save(save_id: int, db: AsyncSession = Depends(get_db)):
    result = await load_game(db, save_id)
    if result is None:
        raise HTTPException(status_code=404, detail="저장 데이터 없음")
    return result


@router.get("/api/saves", response_model=list[GameStateResponse])
async def get_saves(db: AsyncSession = Depends(get_db)):
    return await list_saves(db)


@router.delete("/api/save/{save_id}")
async def remove_save(save_id: int, db: AsyncSession = Depends(get_db)):
    result = await delete_game(db, save_id)
    if result is False:
        raise HTTPException(status_code=404, detail="저장 데이터 없음")
    return {"message": "삭제 완료"}


@router.patch("/api/save/{save_id}", response_model=GameStateResponse)
async def patch_save(save_id: int, data: GameStateUpdate, db: AsyncSession = Depends(get_db)):
    result = await update_game(db, save_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="저장 데이터 없음")
    return result


@router.post("/api/trade/buy/{save_id}", response_model=GameStateResponse)
async def trade_buy(save_id: int, data: TradeRequest, db: AsyncSession = Depends(get_db)):
    return await buy_item(db, save_id, data)


@router.post("/api/trade/sell/{save_id}", response_model=GameStateResponse)
async def trade_sell(save_id: int, data: TradeRequest, db: AsyncSession = Depends(get_db)):
    return await sell_item(db, save_id, data)

