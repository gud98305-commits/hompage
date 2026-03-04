#!/usr/bin/env python3
"""
products_enriched.json의 detail_images에서 쓸데없는 이미지(로고, 배너, 썸네일)를 제거합니다.
PIL로 각 이미지의 크기·비율·파일사이즈를 검사하여 실제 상품 사진만 남깁니다.

사용법:
    python scripts/filter_detail_images.py
    python scripts/filter_detail_images.py --dry-run   # 실제 저장 없이 결과만 출력
    python scripts/filter_detail_images.py --min-width 400  # 기준 변경
"""

from __future__ import annotations

import sys
import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[0]
DATA_DIR = CRAWLER_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow가 설치되지 않았습니다. 다음 명령 실행: pip install Pillow")
    raise

ENRICHED_PATH = DATA_DIR / "products_enriched.json"

# ── 기본 필터 기준 ──────────────────────────────────────────────────────
DEFAULT_MIN_WIDTH  = 300    # px
DEFAULT_MIN_HEIGHT = 300    # px
DEFAULT_MIN_KB     = 8      # KB  (아이콘·썸네일 제거)
DEFAULT_MAX_RATIO  = 1.8    # w/h (가로 배너 제거)
DEFAULT_MIN_RATIO  = 0.35   # w/h (비정상적 세로 이미지 제거)


def is_valid_product_image(
    path: Path,
    min_width: int,
    min_height: int,
    min_kb: float,
    max_ratio: float,
    min_ratio: float,
) -> bool:
    """상품 사진으로 적합한지 판단."""
    if not path.exists():
        return False

    size_kb = path.stat().st_size / 1024
    if size_kb < min_kb:
        return False

    try:
        with Image.open(path) as img:
            w, h = img.size
            if w < min_width or h < min_height:
                return False
            ratio = w / h
            if ratio > max_ratio or ratio < min_ratio:
                return False
        return True
    except Exception:
        return False


def filter_enriched(
    min_width: int = DEFAULT_MIN_WIDTH,
    min_height: int = DEFAULT_MIN_HEIGHT,
    min_kb: float = DEFAULT_MIN_KB,
    max_ratio: float = DEFAULT_MAX_RATIO,
    min_ratio: float = DEFAULT_MIN_RATIO,
    dry_run: bool = False,
) -> None:
    if not ENRICHED_PATH.exists():
        print(f"ERROR: 파일 없음: {ENRICHED_PATH}")
        return

    products = json.loads(ENRICHED_PATH.read_text(encoding="utf-8"))

    total_before = 0
    total_after  = 0
    removed      = 0
    missing      = 0
    changed_products = 0

    for p in products:
        original = list(p.get("detail_images") or [])
        total_before += len(original)

        if not original:
            continue

        filtered: list[str] = []
        for img_path in original:
            local = ROOT / img_path.lstrip("/")
            if not local.exists():
                missing += 1
                continue
            if is_valid_product_image(local, min_width, min_height, min_kb, max_ratio, min_ratio):
                filtered.append(img_path)
            else:
                removed += 1

        total_after += len(filtered)

        if filtered != original:
            changed_products += 1
            if dry_run:
                print(f"[DRY] {p.get('id','?')}: {len(original)} → {len(filtered)} 장")
            else:
                p["detail_images"] = filtered

    print(f"\n{'[DRY RUN] ' if dry_run else ''}필터링 완료")
    print(f"  처리 상품 수  : {len(products)}")
    print(f"  변경된 상품   : {changed_products}")
    print(f"  이미지 (전)   : {total_before}")
    print(f"  파일 없음     : {missing}")
    print(f"  제거됨 (불량) : {removed}")
    print(f"  이미지 (후)   : {total_after}")

    if not dry_run:
        ENRICHED_PATH.write_text(
            json.dumps(products, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n저장 완료: {ENRICHED_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="detail_images 불량 이미지 필터링")
    parser.add_argument("--dry-run", action="store_true", help="실제 저장하지 않고 결과만 출력")
    parser.add_argument("--min-width",  type=int,   default=DEFAULT_MIN_WIDTH)
    parser.add_argument("--min-height", type=int,   default=DEFAULT_MIN_HEIGHT)
    parser.add_argument("--min-kb",     type=float, default=DEFAULT_MIN_KB)
    parser.add_argument("--max-ratio",  type=float, default=DEFAULT_MAX_RATIO)
    parser.add_argument("--min-ratio",  type=float, default=DEFAULT_MIN_RATIO)
    args = parser.parse_args()

    filter_enriched(
        min_width=args.min_width,
        min_height=args.min_height,
        min_kb=args.min_kb,
        max_ratio=args.max_ratio,
        min_ratio=args.min_ratio,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
