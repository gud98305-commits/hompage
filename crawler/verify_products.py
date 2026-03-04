#!/usr/bin/env python3
"""
verify_products.py — SEOULFIT 1:1 재현 정합성 검증

검증 항목:
  1. 필수 필드 누락 여부 (id, mall, name, price_krw, main_image, detail_images, source_url)
  2. 가격 유효성 (price_krw > 0)
  3. main_image 로컬 파일 존재 여부
  4. detail_images 품질 (최소 개수/파일크기/중복률)
  5. source_url 중복 상품 여부
  6. 이름 길이 최소 체크 (3자 이상)

사용법:
  python verify_products.py                      # enriched 파일 검증
  python verify_products.py data/products_raw.json  # raw 파일 검증
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[0]
DATA_DIR = CRAWLER_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from shared.image_quality import evaluate_local_images

DEFAULT_FILE = DATA_DIR / "products_enriched.json"

REQUIRED_FIELDS = ["id", "mall", "name", "price_krw", "main_image", "detail_images", "source_url"]


def verify(
    filepath: Path,
    *,
    min_detail_images: int = 3,
    min_main_bytes: int = 3000,
    min_detail_bytes: int = 1000,
    min_detail_unique_ratio: float = 0.6,
) -> None:
    print(f"\n{'='*60}")
    print(f"  SEOULFIT 상품 정합성 검증")
    print(f"  파일: {filepath.name}")
    print(f"{'='*60}")

    if not filepath.exists():
        print(f"[ERROR] 파일을 찾을 수 없습니다: {filepath}")
        return

    with open(filepath, encoding="utf-8") as f:
        products: list[dict] = json.load(f)

    total = len(products)
    print(f"  총 {total}개 상품 로드됨\n")

    errors: list[str] = []
    warnings: list[str] = []
    seen_urls: dict[str, str] = {}  # source_url → product id
    ok_count = 0
    quality_fail_count = 0

    for idx, p in enumerate(products):
        pid = p.get("id", f"[idx:{idx}]")
        item_errors: list[str] = []

        # ① 필수 필드 체크
        for field in REQUIRED_FIELDS:
            val = p.get(field)
            if val is None or val == "" or val == 0:
                # price_krw == 0 is a warning, not an error
                if field == "price_krw" and val == 0:
                    warnings.append(f"[{pid}] price_krw = 0 (가격 미수집)")
                else:
                    item_errors.append(f"필수 필드 누락: '{field}'")

        # ② 이름 길이
        name = p.get("name", "")
        if isinstance(name, str) and len(name.strip()) < 3:
            item_errors.append(f"상품명이 너무 짧음: '{name}'")

        # ③ main_image 파일 존재 여부
        main_img: str = p.get("main_image", "")
        if main_img and not main_img.startswith("http"):
            local_path = CRAWLER_ROOT / main_img.lstrip("/")
            if not local_path.exists():
                warnings.append(f"[{pid}] main_image 파일 없음: {main_img}")
        elif isinstance(main_img, str) and main_img.startswith("http"):
            warnings.append(f"[{pid}] main_image가 원격 URL입니다 (로컬 재현성 낮음)")

        # ④ detail_images 품질 체크
        details = p.get("detail_images", [])
        if not isinstance(details, list):
            item_errors.append("detail_images 타입 오류(list 아님)")
            details = []

        if details and len(details) < min_detail_images:
            warnings.append(f"[{pid}] detail_images 개수 부족: {len(details)}개 (권장 {min_detail_images}개 이상)")

        missing_details = []
        for dimg in details:
            if dimg and isinstance(dimg, str) and not dimg.startswith("http"):
                local_path = CRAWLER_ROOT / dimg.lstrip("/")
                if not local_path.exists():
                    missing_details.append(dimg)
            elif isinstance(dimg, str) and dimg.startswith("http"):
                warnings.append(f"[{pid}] detail_images에 원격 URL 포함 (로컬 재현성 낮음)")
        if missing_details:
            warnings.append(
                f"[{pid}] detail_images 중 {len(missing_details)}개 파일 없음"
            )

        # 로컬 이미지 품질 게이트 (크롤러의 strict 이미지 기준과 동일)
        quality = evaluate_local_images(
            root=CRAWLER_ROOT,
            main_image=main_img if isinstance(main_img, str) else "",
            detail_images=[d for d in details if isinstance(d, str)],
            min_detail_images=min_detail_images,
            min_main_bytes=min_main_bytes,
            min_detail_bytes=min_detail_bytes,
            min_detail_unique_ratio=min_detail_unique_ratio,
        )
        if not quality.ok:
            quality_fail_count += 1
            item_errors.append(
                f"이미지 품질 실패: {quality.reason} "
                f"(valid={quality.valid_detail_count}, unique_ratio={quality.unique_ratio:.2f}, "
                f"same_as_main={quality.same_as_main_count}, missing={quality.missing_detail_count}, "
                f"small={quality.too_small_detail_count})"
            )

        # ⑤ source_url 중복 체크
        src_url = p.get("source_url", "")
        if src_url:
            if src_url in seen_urls:
                item_errors.append(f"중복 source_url: {src_url} (먼저 나온 ID: {seen_urls[src_url]})")
            else:
                seen_urls[src_url] = str(pid)

        if item_errors:
            errors.extend([f"[{pid}] {e}" for e in item_errors])
        else:
            ok_count += 1

    # ─── 결과 출력 ───────────────────────────────────────────────────────────
    print(f"  ✅ 정상: {ok_count}개")
    print(f"  ⚠️  경고: {len(warnings)}개")
    print(f"  ❌ 오류: {len(errors)}개")

    if warnings:
        print("\n─ 경고 목록 ──────────────────────────────────────────────")
        for w in warnings:
            print(f"  ⚠️  {w}")

    if errors:
        print("\n─ 오류 목록 ──────────────────────────────────────────────")
        for e in errors:
            print(f"  ❌ {e}")
    else:
        print("\n  모든 상품이 필수 필드 검증을 통과했습니다.")

    # ─── 통계 요약 ────────────────────────────────────────────────────────────
    print("\n─ 상품 통계 ──────────────────────────────────────────────")
    mall_counts: dict[str, int] = {}
    no_price = 0
    no_detail = 0
    for p in products:
        mall = p.get("mall", "unknown")
        mall_counts[mall] = mall_counts.get(mall, 0) + 1
        if not p.get("price_krw"):
            no_price += 1
        if not p.get("detail_images"):
            no_detail += 1

    for mall, cnt in sorted(mall_counts.items()):
        print(f"  {mall:20s}: {cnt}개")
    print(f"\n  가격 미수집 상품: {no_price}개")
    print(f"  상세 이미지 없는 상품: {no_detail}개")
    print(f"  이미지 품질 실패 상품: {quality_fail_count}개")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEOULFIT 상품 정합성 검증")
    parser.add_argument("target", nargs="?", default=str(DEFAULT_FILE))
    parser.add_argument("--min-detail-images", type=int, default=3)
    parser.add_argument("--min-main-bytes", type=int, default=3000)
    parser.add_argument("--min-detail-bytes", type=int, default=1000)
    parser.add_argument("--min-detail-unique-ratio", type=float, default=0.6)
    args = parser.parse_args()

    verify(
        Path(args.target),
        min_detail_images=args.min_detail_images,
        min_main_bytes=args.min_main_bytes,
        min_detail_bytes=args.min_detail_bytes,
        min_detail_unique_ratio=args.min_detail_unique_ratio,
    )
