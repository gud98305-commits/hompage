# 백엔드 규칙 (FastAPI + SQLAlchemy + SQLite)

## 필수 패키지
fastapi
uvicorn
sqlalchemy[asyncio]
aiosqlite
pydantic>=2.0

## models/database.py 필수 구성

from sqlalchemy import TypeDecorator, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from datetime import timezone

# TzAwareDateTime: SQLite 읽기 시 Naive datetime → UTC Aware 자동 변환
# 없으면 AwareDatetime 검증 시 100% ValidationError 발생
class TzAwareDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True
    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
# 사용: Column(TzAwareDateTime, ...)
# 기본 DateTime 컬럼 사용 금지

# 세션 팩토리: expire_on_commit=False 필수
# 없으면 commit() 후 ORM 객체 접근 시 DetachedInstanceError 발생
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# get_db(): yield 패턴 필수 (return 사용 금지)
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
# get_db() 내부에서 PRAGMA 실행 금지

## main.py lifespan 필수 구성

from contextlib import asynccontextmanager
from sqlalchemy import text

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) AUTOCOMMIT으로 WAL 활성화
    # engine.begin()은 트랜잭션 블록 → PRAGMA 실행 시 OperationalError 확정
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("PRAGMA journal_mode=WAL;"))

    # 2) WAL 완료 후 별도 트랜잭션으로 테이블 생성
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await engine.dispose()  # WAL 락 잔류 방지

app = FastAPI(lifespan=lifespan)

## DB 환경변수
DATABASE_URL=sqlite+aiosqlite:///./game.db       # 로컬
DATABASE_URL=sqlite+aiosqlite:////data/game.db   # 배포

create_async_engine(DATABASE_URL, connect_args={"timeout": 15})

## CORS 설정 (main.py)
개발: allow_origins=["*"]
배포: 환경변수 CORS_ORIGINS로 분리
배포 환경에서 allow_origins=["*"] 사용 금지

## 3계층 아키텍처

### services/game_logic.py — 트랜잭션 경계
async def save_game(data: SaveRequest, db: AsyncSession):
    try:
        await db.commit()    # commit은 여기서만
        return result
    except Exception as e:
        await db.rollback()  # rollback은 여기서만
        raise
- Depends()를 함수 인자에 직접 사용 금지
- 전역 세션 객체 생성 금지
- UI/DOM 코드 금지

### services/api_routes.py — 위임만
@router.post("/api/save")
async def save_route(data: SaveRequest, db: AsyncSession = Depends(get_db)):
    return await save_game(data, db)
- 라우터에서 commit/rollback 호출 금지

### models/schemas.py — Pydantic V2
from pydantic import ConfigDict, AwareDatetime

class GameStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # 필수
    saved_at: AwareDatetime  # datetime 타입 사용 금지

# 모든 시간: UTC ISO8601
# Python: datetime.now(timezone.utc).isoformat()
# JS: new Date().toISOString()
# Pydantic V1 문법 금지: .dict(), .from_orm()

## 절대 금지 요약
- ❌ get_db() yield 없이 return
- ❌ PRAGMA를 engine.begin() 내부에서 실행
- ❌ PRAGMA를 lifespan 외부에서 실행
- ❌ expire_on_commit 기본값(True) 사용
- ❌ DateTime 컬럼에 TzAwareDateTime 미적용
- ❌ 시간 필드에 datetime 타입 사용
- ❌ api_routes.py에서 commit/rollback 호출
- ❌ ConfigDict(from_attributes=True) 없이 model_validate() 호출
- ❌ ORM Lazy Loading 사용
- ❌ *.db, .env를 Git 커밋에 포함

## .gitignore 필수
*.db
.env
__pycache__/
.venv/

## 비상 대응
- 백엔드 막히면: LocalStorage 임시 대체
  { "saveSource": "local", "savedAt": "UTC ISO8601", "playerData": {...} }
- 핵심 원칙: 엔진(프론트) 완성이 백엔드보다 항상 우선
