from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

# .env를 가장 먼저 로드해야 routes import 시점에 os.getenv()가 올바른 값을 읽음 (override=True 지정)
load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.routes.auth import router as auth_router
from backend.routes.checkout import router as checkout_router
from backend.routes.recommend import router as recommend_router
from backend.routes.translate import router as translate_router
from backend.routes.webhook import router as webhook_router
from backend.routes.my import router as my_router
from backend.routes.game import router as game_router
from backend.routes.photobooth import router as photobooth_router
from backend.routes.rpg import router as rpg_router
from backend.routes.pages import router as pages_router
from backend.routes.aeae_receipt import router as aeae_receipt_router
from backend.services.turso_db import init_db
from backend.services.chatbot_advanced.chat_routes import router as advanced_chat_router
from backend.services.chatbot_advanced.chat_service import register_chat_exception_handlers
from backend.services.chatbot_advanced.chat_db import init_chat_db
from backend.services.rpg_models import init_rpg_db, close_rpg_db
from backend.services.rpg_exceptions import RpgGameError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 실행되는 라이프사이클."""
    print("[Startup] 서버 시작 중...")
    try:
        init_db()
        print("[Startup] Turso DB 초기화 완료")
    except Exception as e:
        print(f"[Startup] Turso DB 초기화 실패 (계속 진행): {e}")
    try:
        await init_chat_db()
        print("[Startup] ChatDB 초기화 완료")
    except Exception as e:
        print(f"[Startup] ChatDB 초기화 실패 (계속 진행): {e}")
    try:
        await init_rpg_db()
        print("[Startup] RPG DB 초기화 완료")
    except Exception as e:
        print(f"[Startup] RPG DB 초기화 실패 (계속 진행): {e}")
    print("[Startup] 서버 준비 완료")
    yield
    try:
        await close_rpg_db()
    except Exception:
        pass


app = FastAPI(title='SEOULFIT API', version='0.1.0', lifespan=lifespan)

_FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")
_ALLOWED_ORIGINS = [
    _FRONTEND_URL,
    "http://localhost:8000",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router)
app.include_router(recommend_router)
app.include_router(checkout_router)
app.include_router(translate_router)
app.include_router(webhook_router)
app.include_router(my_router)
app.include_router(game_router)
app.include_router(rpg_router)
app.include_router(advanced_chat_router)
app.include_router(photobooth_router)
app.include_router(pages_router)
app.include_router(aeae_receipt_router)

# 챗봇 예외 핸들러 등록
register_chat_exception_handlers(app)


# RPG 게임 에러 핸들러
@app.exception_handler(RpgGameError)
async def rpg_game_error_handler(request, exc: RpgGameError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={'detail': exc.detail},
    )

ROOT = Path(__file__).resolve().parents[1]
app.mount('/assets', StaticFiles(directory=str(ROOT / 'assets')), name='assets')
app.mount('/images', StaticFiles(directory=str(ROOT / 'images')), name='images')
app.mount('/data', StaticFiles(directory=str(ROOT / 'data')), name='data')

# RPG 게임 에셋 + 팝업스토어 정적 파일 서빙
if (ROOT / 'aeae_popup').exists():
    app.mount('/aeae_popup', StaticFiles(directory=str(ROOT / 'aeae_popup')), name='aeae_popup')

# 포토부스 갤러리 레퍼런스 이미지 서빙
# ⚠️ 엣지케이스: 경로가 없으면 StaticFiles가 서버 시작 시 예외 발생
#    → 로컬/Docker 양쪽 경로를 순서대로 시도
_refs_candidates = [
    ROOT / 'miniproject_2' / 'photobooth' / 'public' / 'references',  # 로컬 & Docker
]
for _refs_path in _refs_candidates:
    if _refs_path.exists():
        app.mount('/references', StaticFiles(directory=str(_refs_path)), name='references')
        break


@app.get('/api/health')
def health() -> dict:
    return {'status': 'ok'}

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    favicon_path = ROOT / 'assets' / 'img' / 'otto-logo.png'
    if favicon_path.exists():
        return FileResponse(favicon_path)
    from fastapi.responses import Response
    return Response(status_code=204)
