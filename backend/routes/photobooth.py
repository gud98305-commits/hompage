"""
photobooth.py — FastAPI 포토부스 라우터
Next.js miniproject_2/photobooth/app/api/ 포팅

엔드포인트:
  GET  /api/photobooth/styles   — 스타일 목록
  GET  /api/photobooth/presets  — 프리셋 목록
  POST /api/photobooth/generate — 이미지 생성 (gpt-image-1 + Pillow 합성)
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.photobooth_image import PLACEHOLDER_B64, composite_grid

router = APIRouter(prefix="/api/photobooth", tags=["photobooth"])

# ── 정적 데이터 로드 (앱 시작 시 1회) ─────────────────────────────────
_DATA_DIR = Path(__file__).resolve().parents[2] / "miniproject_2" / "photobooth" / "data"

try:
    with open(_DATA_DIR / "styles.json", encoding="utf-8") as f:
        _STYLES: list[dict] = json.load(f)
    with open(_DATA_DIR / "pose_presets.json", encoding="utf-8") as f:
        _PRESETS: list[dict] = json.load(f)
except FileNotFoundError as e:
    raise RuntimeError(f"[Photobooth] 데이터 파일 없음: {e}")

_STYLE_MAP = {s["style_id"]: s for s in _STYLES}

# ── OpenAI 클라이언트 (지연 초기화: OPENAI_API_KEY 없어도 서버 기동) ──
_openai_client = None


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=503, detail="OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# ── 요청/응답 모델 ────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    styleId: str
    imageBase64: Optional[str] = None        # selfie → images.edit()
    textDescription: Optional[str] = None   # 텍스트 입력
    outfitDescription: Optional[str] = None # 의상 설명


# ── 라우트 ────────────────────────────────────────────────────────────

@router.get("/styles")
def get_styles() -> list[dict]:
    return _STYLES


@router.get("/presets")
def get_presets() -> list[dict]:
    data = [
        {
            "style_id":    p["style_id"],
            "display_name": p["display_name"],
            "border_color": p["border_color"],
        }
        for p in _PRESETS
    ]
    return data


@router.post("/generate")
async def generate(body: GenerateRequest) -> dict:
    # ── 입력 검증 ────────────────────────────────────────────────────
    if not body.styleId:
        raise HTTPException(status_code=400, detail="styleId는 필수입니다.")

    style = _STYLE_MAP.get(body.styleId)
    if not style:
        raise HTTPException(status_code=400, detail=f"알 수 없는 스타일: {body.styleId}")

    if not body.imageBase64 and not body.textDescription:
        raise HTTPException(
            status_code=400,
            detail="imageBase64 또는 textDescription 중 하나는 필수입니다.",
        )

    prompts_raw: list[str] = style.get("prompts", [])
    if len(prompts_raw) < 4:
        raise HTTPException(status_code=500, detail=f"스타일 '{body.styleId}'의 프롬프트가 4개 미만입니다.")

    # ── 셀카 base64 → bytes 변환 ──────────────────────────────────────
    # ⚠️ 엣지케이스: data URL prefix 포함될 수 있음 ("data:image/jpeg;base64,...")
    selfie_bytes: Optional[bytes] = None
    if body.imageBase64:
        raw_b64 = body.imageBase64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        try:
            selfie_bytes = base64.b64decode(raw_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="imageBase64 디코딩 실패: 유효하지 않은 base64입니다.")

        # ⚠️ 엣지케이스: OpenAI images.edit 최대 20MB 제한
        if len(selfie_bytes) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="이미지가 너무 큽니다. 최대 20MB입니다.")

    # ── 컨텍스트 프롬프트 조합 ───────────────────────────────────────
    context_parts: list[str] = []
    if body.textDescription:
        context_parts.append(f"Person characteristics: {body.textDescription}")
    if body.outfitDescription:
        context_parts.append(f"Outfit style: {body.outfitDescription}")

    context = "\n".join(context_parts)
    prompts = (
        [f"{context}\n\n{p}" for p in prompts_raw]
        if context
        else prompts_raw
    )

    # ── 4장 병렬 생성 ────────────────────────────────────────────────
    frame_results = await _generate_all_frames(prompts, selfie_bytes)

    # 실패 프레임은 placeholder로 대체
    frame_images: list[str] = [
        r["imageBase64"] if r["success"] else PLACEHOLDER_B64
        for r in frame_results
    ]

    # ── 2×2 그리드 합성 ──────────────────────────────────────────────
    try:
        result_image = composite_grid(
            frame_images,
            style.get("border_color", "#888888"),
            style.get("display_name", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 합성 실패: {e}")

    return {"resultImage": result_image, "frames": frame_images}


# ── OpenAI 호출 (동기 → 스레드풀) ────────────────────────────────────

def _generate_one_sync(prompt: str, selfie_bytes: Optional[bytes]) -> str:
    """
    gpt-image-1로 프레임 1장 생성.
    ⚠️ 동기 함수 — asyncio.run_in_executor로 호출해야 함
    """
    client = _get_openai()

    if selfie_bytes:
        # ⚠️ 엣지케이스: BytesIO에 .name 속성 필수 (MIME 타입 추론용)
        selfie_io = io.BytesIO(selfie_bytes)
        selfie_io.name = "selfie.jpg"
        response = client.images.edit(
            model="gpt-image-1",
            image=selfie_io,
            prompt=prompt,
            n=1,
            size="1024x1536",
            quality="high",
        )
    else:
        response = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            n=1,
            size="1024x1536",
            quality="high",
        )

    # ⚠️ 엣지케이스: gpt-image-1은 항상 b64_json 반환 (url 없음)
    b64 = response.data[0].b64_json
    if not b64:
        raise ValueError("OpenAI 응답에 b64_json이 없습니다.")
    return b64


async def _generate_all_frames(
    prompts: list[str],
    selfie_bytes: Optional[bytes],
) -> list[dict]:
    """
    4장 병렬 생성 + 실패 시 1회 재시도.
    ⚠️ 엣지케이스: gpt-image-1 rate limit — 최대 4 concurrent requests
    """
    loop = asyncio.get_event_loop()
    # ⚠️ ThreadPoolExecutor는 함수 종료 시 명시적 shutdown 필요
    executor = ThreadPoolExecutor(max_workers=4)

    try:
        first_attempt = await asyncio.gather(
            *[
                loop.run_in_executor(executor, _generate_one_sync, p, selfie_bytes)
                for p in prompts
            ],
            return_exceptions=True,
        )

        results: list[dict] = []
        retry_indices: list[int] = []

        for i, outcome in enumerate(first_attempt):
            if isinstance(outcome, Exception):
                retry_indices.append(i)
                results.append({"success": False, "error": str(outcome)})
            else:
                results.append({"success": True, "imageBase64": outcome})

        # 실패 프레임 재시도
        if retry_indices:
            retry_attempt = await asyncio.gather(
                *[
                    loop.run_in_executor(executor, _generate_one_sync, prompts[i], selfie_bytes)
                    for i in retry_indices
                ],
                return_exceptions=True,
            )
            for j, outcome in enumerate(retry_attempt):
                orig_i = retry_indices[j]
                if not isinstance(outcome, Exception):
                    results[orig_i] = {"success": True, "imageBase64": outcome}

        return results

    finally:
        executor.shutdown(wait=False)
