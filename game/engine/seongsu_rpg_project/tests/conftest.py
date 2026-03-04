# 공유 테스트 Fixture (conftest.py)
# 인메모리 DB, 클라이언트, 테스트 데이터 — 모든 test_*.py에서 공유

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, get_db
from main import app

# ── 인메모리 SQLite 테스트 DB ──

TEST_DATABASE_URL = "sqlite+aiosqlite:///"

test_engine = create_async_engine(TEST_DATABASE_URL, connect_args={"timeout": 15})
TestSessionLocal = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """각 테스트마다 테이블 생성/삭제로 DB 초기화"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── 공통 테스트 데이터 ──

VALID_SAVE = {
    "player_name": "테스터",
    "player_x": 100,
    "player_y": 64,
    "gold": 500,
    "inventory": ["열쇠", "빵"],
    "discovered_events": ["npc_dummy_01"],
}
