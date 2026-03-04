# 데이터베이스 연결/세션 모듈 (Database)

from sqlalchemy import TypeDecorator, DateTime, Integer, String, JSON
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from datetime import datetime, timezone
from core.config import settings

DATABASE_URL = settings.DATABASE_URL

engine = create_async_engine(DATABASE_URL, connect_args={"timeout": 15})


class TzAwareDateTime(TypeDecorator):
    """SQLite 읽기 시 Naive datetime → UTC Aware 자동 변환"""
    impl = DateTime
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    pass


class GameState(Base):
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


# expire_on_commit=False 필수: commit() 후 ORM 객체 접근 시 DetachedInstanceError 방지
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    """yield 패턴 필수 (return 사용 금지)"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
