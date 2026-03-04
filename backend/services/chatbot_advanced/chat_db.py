"""
chat_db.py — 챗봇 히스토리용 SQLite 비동기 세션.

채팅 히스토리 저장소는 현재 stub (항상 [] 반환).
AsyncSession은 chat_routes의 Depends(get_db)와 chat_service 핸들러의
Protocol 호환성을 위해 유지합니다.

향후 Turso로 마이그레이션 예정 (백로그 태스크).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Railway 볼륨 마운트를 위해 data/ 폴더 내부에 DB를 위치시킵니다.
DATABASE_URL = "sqlite+aiosqlite:///./data/chatbot_history.db"

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_chat_db() -> None:
    """채팅 히스토리 테이블 생성. app lifespan에서 호출."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[ChatDB] 채팅 히스토리 SQLite 초기화 완료")


async def get_db():
    """FastAPI Depends 제너레이터. chat_routes 엔드포인트에 AsyncSession 제공."""
    async with AsyncSessionLocal() as session:
        yield session
