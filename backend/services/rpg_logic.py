# RPG 게임 로직 서비스
# save/load/trade 등 비즈니스 로직

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.rpg_models import GameState, GameStateCreate, GameStateUpdate, TradeRequest
from backend.services.rpg_exceptions import GameNotFoundError, InsufficientFundsError, ItemNotFoundError

import logging

logger = logging.getLogger(__name__)


async def save_game(db: AsyncSession, data: GameStateCreate) -> GameState:
    obj = GameState(**data.model_dump())
    try:
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj
    except Exception:
        await db.rollback()
        raise


async def load_game(db: AsyncSession, save_id: int) -> GameState | None:
    return await db.get(GameState, save_id)


async def list_saves(db: AsyncSession) -> Sequence[GameState]:
    result = await db.execute(
        select(GameState).order_by(GameState.saved_at.desc()).limit(10)
    )
    return result.scalars().all()


async def update_game(db: AsyncSession, save_id: int, data: GameStateUpdate) -> GameState | None:
    db_obj = await db.get(GameState, save_id)
    if db_obj is None:
        return None
    for key, value in data.model_dump(exclude_unset=True, exclude={"id", "saved_at"}).items():
        setattr(db_obj, key, value)
    try:
        await db.commit()
        await db.refresh(db_obj)
        return db_obj
    except Exception:
        await db.rollback()
        raise


async def delete_game(db: AsyncSession, save_id: int) -> bool:
    db_obj = await db.get(GameState, save_id)
    if db_obj is None:
        return False
    try:
        await db.delete(db_obj)
        await db.commit()
        return True
    except Exception:
        await db.rollback()
        raise


async def buy_item(db: AsyncSession, save_id: int, data: TradeRequest) -> GameState:
    db_obj = await db.get(GameState, save_id)
    if db_obj is None:
        raise GameNotFoundError(save_id)
    if db_obj.gold < data.price:
        raise InsufficientFundsError(required=data.price, current=db_obj.gold)
    db_obj.gold -= data.price
    db_obj.inventory = [*db_obj.inventory, data.item_name]
    try:
        await db.commit()
        await db.refresh(db_obj)
        logger.info("buy_item: save_id=%d item=%s price=%d", save_id, data.item_name, data.price)
        return db_obj
    except Exception:
        await db.rollback()
        raise


async def sell_item(db: AsyncSession, save_id: int, data: TradeRequest) -> GameState:
    db_obj = await db.get(GameState, save_id)
    if db_obj is None:
        raise GameNotFoundError(save_id)
    inv = list(db_obj.inventory)
    if data.item_name not in inv:
        raise ItemNotFoundError(data.item_name)
    inv.remove(data.item_name)
    db_obj.inventory = inv
    db_obj.gold += data.price
    try:
        await db.commit()
        await db.refresh(db_obj)
        logger.info("sell_item: save_id=%d item=%s price=%d", save_id, data.item_name, data.price)
        return db_obj
    except Exception:
        await db.rollback()
        raise
