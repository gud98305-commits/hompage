# RPG 게임 데이터베이스 모델 + Pydantic 스키마
# 메인 Turso DB와 별도의 SQLite DB (rpg_game.db) 사용

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, AwareDatetime, Field, StringConstraints
from sqlalchemy import TypeDecorator, DateTime, Integer, String, JSON
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ── DB 연결 ──

RPG_DATABASE_URL = os.getenv("RPG_DATABASE_URL", "sqlite+aiosqlite:///./data/rpg_game.db")
rpg_engine = create_async_engine(RPG_DATABASE_URL, connect_args={"timeout": 15})


class TzAwareDateTime(TypeDecorator):
    """SQLite 읽기 시 Naive datetime → UTC Aware 자동 변환"""
    impl = DateTime
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class RpgBase(DeclarativeBase):
    pass


class GameState(RpgBase):
    __tablename__ = "game_states"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_name: Mapped[str] = mapped_column(String, nullable=False)
    player_x: Mapped[int] = mapped_column(Integer, nullable=False)
    player_y: Mapped[int] = mapped_column(Integer, nullable=False)
    gold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inventory: Mapped[list[str]] = mapped_column(JSON, default=list)
    clothes: Mapped[list[str]] = mapped_column(JSON, default=list)
    discovered_events: Mapped[list[str]] = mapped_column(JSON, default=list)
    saved_at: Mapped[datetime] = mapped_column(
        TzAwareDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )


RpgAsyncSessionLocal = sessionmaker(
    rpg_engine, class_=AsyncSession, expire_on_commit=False
)


async def get_rpg_db():
    """yield 패턴 필수 (return 사용 금지)"""
    async with RpgAsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_rpg_db():
    """RPG DB 테이블 초기화"""
    from sqlalchemy import text
    async with rpg_engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
    async with rpg_engine.begin() as conn:
        await conn.run_sync(RpgBase.metadata.create_all)


async def close_rpg_db():
    """RPG DB 연결 해제"""
    await rpg_engine.dispose()


# ── Pydantic 스키마 ──

PlayerName = Annotated[str, StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=50,
    pattern=r"^[a-zA-Z0-9_가-힣 ]+$"
)]
ItemName = Annotated[str, StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=50
)]
EventId = Annotated[str, StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=100
)]
Coordinate = Annotated[int, Field(ge=0, le=10000)]
Gold = Annotated[int, Field(ge=0, le=9999999)]


class GameStateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    player_name: PlayerName
    player_x: Coordinate
    player_y: Coordinate
    gold: Gold = 0
    inventory: list[ItemName] = Field(default_factory=list, max_length=50)
    clothes: list[ItemName] = Field(default_factory=list, max_length=50)
    discovered_events: list[EventId] = Field(default_factory=list, max_length=200)


class GameStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, validate_assignment=True)
    id: int
    player_name: PlayerName
    player_x: Coordinate
    player_y: Coordinate
    gold: Gold
    inventory: list[ItemName]
    clothes: list[ItemName]
    discovered_events: list[EventId]
    saved_at: AwareDatetime


class GameStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    player_x: Coordinate | None = None
    player_y: Coordinate | None = None
    gold: Gold | None = None
    inventory: list[ItemName] | None = Field(default=None, max_length=50)
    clothes: list[ItemName] | None = Field(default=None, max_length=50)
    discovered_events: list[EventId] | None = Field(default=None, max_length=200)


TradeGold = Annotated[int, Field(ge=1, le=9999999)]


class TradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    item_name: ItemName
    price: TradeGold
