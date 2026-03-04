# 메인 애플리케이션 엔트리포인트 (Main)
# FastAPI 앱 초기화, 미들웨어, 라우터, 글로벌 에러 핸들러

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
import httpx

from models.database import engine, Base
from services.api_routes import router
from core.config import settings
from core.logger import get_logger
from core.exceptions import GameError

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) AUTOCOMMIT 커넥션으로 WAL 활성화
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
    logger.info("SQLite WAL 모드 활성화 완료")

    # 2) WAL 완료 후 별도 트랜잭션으로 테이블 생성
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("데이터베이스 테이블 생성 완료")

    yield

    await engine.dispose()
    logger.info("데이터베이스 연결 종료")


app = FastAPI(lifespan=lifespan)

# ── 글로벌 GameError → HTTP 변환 핸들러 ──
@app.exception_handler(GameError)
async def game_error_handler(request: Request, exc: GameError):
    logger.warning("GameError: %s (status=%d)", exc.detail, exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

# ── 500 에러 로깅 핸들러 ──
@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "서버 내부 오류"},
    )

# ── CORS (settings.CORS_ORIGINS 기반) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 포함
app.include_router(router)


@app.get("/")
async def serve_index():
    return FileResponse("views/index.html")


# ── Netlify Functions 프록시 (팝업 AI API) ──
NETLIFY_BASE = "https://aeaepopup.netlify.app/.netlify/functions"

@app.post("/api/proxy/{func_name:path}")
async def proxy_netlify_function(func_name: str, request: Request):
    body = await request.body()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{NETLIFY_BASE}/{func_name}",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    try:
        content = resp.json()
    except Exception:
        content = {"detail": resp.text}
    return JSONResponse(
        status_code=resp.status_code,
        content=content,
    )


# views/ 폴더 전체를 / 경로로 마운트 (가장 마지막에 위치해야 함)
app.mount("/", StaticFiles(directory="views"), name="views")
