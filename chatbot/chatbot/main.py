"""
OttO봇 챗봇 서버 엔트리포인트.

실행: uvicorn main:app --reload --port 8000
"""

from dotenv import load_dotenv
load_dotenv()  # .env 파일에서 환경변수 로드 (OPENAI_API_KEY 등)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from chat_routes import router as chat_router
from chat_service import register_chat_exception_handlers
from database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 실행되는 라이프사이클."""
    # 시작: stub DB 테이블 생성
    await init_db()
    print("[OttO봇] 서버 시작 완료")
    yield
    # 종료
    print("[OttO봇] 서버 종료")


app = FastAPI(
    title="OttO봇 AI 패션 챗봇",
    description="체형 분석 + 옷 추천 + 게임 아이템 연동 챗봇 API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 설정 (프론트엔드 로컬 개발용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 프론트엔드 static 파일 서빙
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# 챗봇 API 라우터 등록
app.include_router(chat_router)

# 예외 핸들러 등록
register_chat_exception_handlers(app)


@app.get("/")
async def root():
    """프론트엔드 HTML 반환."""
    return {
        "message": "OttO봇 API 서버",
        "docs": "/docs",
        "frontend": "/static/index.html",
    }
