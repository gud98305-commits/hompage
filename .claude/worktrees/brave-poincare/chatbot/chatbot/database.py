"""
데이터베이스 세션 — 게임팀/백엔드팀 교체 필요.

[담당자에게]
DATABASE_URL을 실제 외부 DB 연결 문자열로 교체하세요.
get_db() 함수 시그니처는 변경하지 마세요 (chat_routes.py가 의존).

교체 예시:
- Supabase PostgreSQL:
    DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/dbname"
    pip install asyncpg
- MySQL:
    DATABASE_URL = "mysql+aiomysql://user:pass@host:3306/dbname"
    pip install aiomysql
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from schemas import Base

# TODO: 실제 외부 DB URL로 교체
DATABASE_URL = "sqlite+aiosqlite:///./chatbot.db"

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """테이블 생성. 서버 시작 시 호출."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI Depends용 DB 세션 제너레이터.

    이 함수의 시그니처(AsyncGenerator[AsyncSession])를 변경하지 마세요.
    chat_routes.py의 모든 엔드포인트가 Depends(get_db)로 주입받습니다.
    """
    async with AsyncSessionLocal() as session:
        yield session
