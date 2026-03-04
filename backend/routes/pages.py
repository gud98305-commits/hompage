from fastapi import APIRouter
from fastapi.responses import FileResponse
from pathlib import Path

# 프로젝트 루트(app.py 기준 2단계 위)
ROOT = Path(__file__).resolve().parents[2]

router = APIRouter(tags=["pages"])


@router.get("/")
def root() -> FileResponse:
    return FileResponse(ROOT / "index.html")


@router.get("/index.html")
def index_html() -> FileResponse:
    return FileResponse(ROOT / "index.html")


@router.get("/fashion.html")
def fashion_html() -> FileResponse:
    return FileResponse(ROOT / "fashion.html")


@router.get("/my.html")
def my_html() -> FileResponse:
    return FileResponse(ROOT / "my.html")


@router.get("/my")
def my_page() -> FileResponse:
    return FileResponse(ROOT / "my.html")


@router.get("/photobooth.html")
def photobooth_html() -> FileResponse:
    return FileResponse(ROOT / "photobooth.html")


@router.get("/rpg.html")
def rpg_html() -> FileResponse:
    return FileResponse(ROOT / "rpg.html")
