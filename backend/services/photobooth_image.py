"""
photobooth_image.py — Pillow 기반 2×2 그리드 합성
Next.js composite.ts 포팅
"""
from __future__ import annotations

import base64
import io
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# ── 레이아웃 상수 (composite.ts 동일) ────────────────────────────────
FRAME_W      = 480
FRAME_H      = 640
GAP          = 20
PADDING_X    = 48
PADDING_TOP  = 100
PADDING_BOT  = 120
ROUND_RADIUS = 16

CANVAS_W = PADDING_X * 2 + FRAME_W * 2 + GAP
CANVAS_H = PADDING_TOP + FRAME_H * 2 + GAP + PADDING_BOT

FRAME_POSITIONS = [
    (PADDING_X,              PADDING_TOP),
    (PADDING_X + FRAME_W + GAP, PADDING_TOP),
    (PADDING_X,              PADDING_TOP + FRAME_H + GAP),
    (PADDING_X + FRAME_W + GAP, PADDING_TOP + FRAME_H + GAP),
]

# ── 폰트 경로 후보 (Docker slim + 로컬 Windows/Mac) ───────────────────
_FONT_CANDIDATES_TITLE = [
    "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
]
_FONT_CANDIDATES_BODY = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    # Pillow 10.1+ load_default supports size
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _make_rounded_mask(w: int, h: int, radius: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return mask


def _cover_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """sharp의 { fit: 'cover' } 동일: 비율 유지 + 중앙 크롭."""
    img_ratio = img.width / img.height
    target_ratio = target_w / target_h
    if img_ratio > target_ratio:
        new_h = target_h
        new_w = round(img.width * target_h / img.height)
    else:
        new_w = target_w
        new_h = round(img.height * target_w / img.width)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top  = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _process_frame(b64: str, index: int) -> tuple[Image.Image, tuple[int, int]]:
    img_bytes = base64.b64decode(b64)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    img = _cover_resize(img, FRAME_W, FRAME_H)

    # 둥근 모서리 마스크 적용
    mask = _make_rounded_mask(FRAME_W, FRAME_H, ROUND_RADIUS)
    img.putalpha(mask)
    return img, FRAME_POSITIONS[index]


def _make_placeholder() -> str:
    """생성 실패 시 회색 플레이스홀더 base64 반환."""
    img = Image.new("RGB", (1024, 1536), (200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


PLACEHOLDER_B64 = _make_placeholder()


def composite_grid(frames: list[str], border_color: str, style_display_name: str = "") -> str:
    """
    4장의 base64 이미지를 2×2 그리드로 합성.
    Returns: base64 JPEG string
    """
    if len(frames) != 4:
        raise ValueError(f"Expected 4 frames, got {len(frames)}")

    color_rgb = _hex_to_rgb(border_color)

    # 흰 배경 RGBA 캔버스
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (255, 255, 255, 255))

    for i, b64 in enumerate(frames):
        try:
            frame_img, (x, y) = _process_frame(b64, i)
            canvas.paste(frame_img, (x, y), frame_img)
        except Exception:
            # ⚠️ 엣지케이스: 개별 프레임 처리 실패 → 회색 placeholder
            placeholder = Image.new("RGBA", (FRAME_W, FRAME_H), (200, 200, 200, 255))
            x, y = FRAME_POSITIONS[i]
            canvas.paste(placeholder, (x, y))

    # RGBA → RGB (JPEG는 알파 채널 미지원)
    result = Image.new("RGB", (CANVAS_W, CANVAS_H), (255, 255, 255))
    result.paste(canvas, mask=canvas.split()[3])

    draw = ImageDraw.Draw(result)
    title_font = _load_font(_FONT_CANDIDATES_TITLE, 36)
    body_font  = _load_font(_FONT_CANDIDATES_BODY,  28)

    # ── "AX film" 상단 중앙 ───────────────────────────────────────────
    ax_text = "AX film"
    ax_bbox = draw.textbbox((0, 0), ax_text, font=title_font)
    ax_w    = ax_bbox[2] - ax_bbox[0]
    ax_h    = ax_bbox[3] - ax_bbox[1]
    draw.text(
        ((CANVAS_W - ax_w) // 2, (PADDING_TOP - ax_h) // 2),
        ax_text, font=title_font, fill=color_rgb,
    )

    # ── 날짜 + 스타일명 하단 중앙 ─────────────────────────────────────
    now      = datetime.now()
    date_str = f"{now.year}.{now.month:02d}.{now.day:02d}"
    # ⚠️ 엣지케이스: ✦ 는 특수 유니코드 — 폰트가 지원 안 할 수 있음 → * 로 안전하게 대체
    sep          = "*"
    bottom_text  = f"{date_str}  {sep}  {style_display_name}" if style_display_name else date_str

    b_bbox = draw.textbbox((0, 0), bottom_text, font=body_font)
    b_w    = b_bbox[2] - b_bbox[0]
    b_h    = b_bbox[3] - b_bbox[1]
    date_area_top = CANVAS_H - PADDING_BOT
    draw.text(
        ((CANVAS_W - b_w) // 2, date_area_top + (PADDING_BOT - b_h) // 2),
        bottom_text, font=body_font, fill=(136, 136, 136),
    )

    # ── 하단 컬러 바 8px ──────────────────────────────────────────────
    draw.rectangle([0, CANVAS_H - 8, CANVAS_W, CANVAS_H], fill=color_rgb)

    buf = io.BytesIO()
    result.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode()
