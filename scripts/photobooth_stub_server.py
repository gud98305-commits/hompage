from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parents[1]
PHOTO_ROOT = ROOT / "miniproject_2" / "photobooth"
STYLES_PATH = PHOTO_ROOT / "data" / "styles.json"
REFERENCES_DIR = PHOTO_ROOT / "public" / "references"

styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))

app = FastAPI(title="OttO Photobooth Stub", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/styles")
def get_styles():
    return styles


@app.post("/api/generate")
def generate_unavailable():
    return JSONResponse(
        {
            "error": "임시 서버에서는 이미지 생성을 지원하지 않습니다. 스타일 선택과 레이아웃 확인만 가능합니다."
        },
        status_code=501,
    )


if REFERENCES_DIR.exists():
    app.mount("/references", StaticFiles(directory=str(REFERENCES_DIR)), name="references")
