"""
export_csv.py — products_enriched.json → CSV 내보내기

용도:
  - 상세 이미지(detail_images)는 제외 → API 코스트 절감
  - 대표 이미지(main_image) 경로는 포함
  - 텍스트 상세정보(material, country, care, notice 등) 포함
  - 더미/mock 이미지 참조 상품 자동 필터링

실행:
  python export_csv.py
  python export_csv.py --source raw         # products_raw.json 기준
  python export_csv.py --out my_products.csv
  python export_csv.py --all                # 비의류 포함 전체 출력
"""
from __future__ import annotations

import sys
import argparse
import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[0]
DATA_DIR = CRAWLER_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# CSV에 포함할 컬럼 순서 (detail_images 제외)
COLUMNS = [
    "id",
    "mall",
    "brand",
    "brand_origin",
    "name",
    "price_krw",
    "price_jpy",
    "category",
    "colors",
    "style",
    "keyword",
    "tags",
    "material",
    "country",
    "care",
    "notice",
    "musinsa_category",
    "is_fashion",
    "is_clothing",
    "main_image",
    "source_url",
    "item_cd",
]


def _safe(value) -> str:
    """CSV 셀 값으로 안전하게 변환."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def export_csv(
    source: str = "enriched",
    out_path: Path | None = None,
    include_all: bool = False,
) -> Path:
    # 소스 파일 결정
    if source == "raw":
        src_file = DATA_DIR / "products_raw.json"
    else:
        enriched = DATA_DIR / "products_enriched.json"
        src_file = enriched if enriched.exists() else DATA_DIR / "products_raw.json"

    if not src_file.exists():
        print(f"❌  파일 없음: {src_file}")
        sys.exit(1)

    products: list[dict] = json.loads(src_file.read_text(encoding="utf-8"))
    print(f"✅  로드: {src_file.name} ({len(products)}개)")

    # 더미(mock) 이미지 상품 필터링
    before = len(products)
    products = [
        p for p in products
        if "mock" not in str(p.get("main_image", ""))
    ]
    if len(products) < before:
        print(f"   더미 이미지 상품 제외: {before - len(products)}개")

    # 의류 필터 (--all 없을 때)
    if not include_all:
        before = len(products)
        products = [
            p for p in products
            if p.get("is_fashion", True) or p.get("is_clothing", True)
        ]
        if len(products) < before:
            print(f"   비의류 제외: {before - len(products)}개")

    # CSV 출력 경로
    if out_path is None:
        out_path = CRAWLER_ROOT / "products_export.csv"

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for p in products:
            row = {col: _safe(p.get(col, "")) for col in COLUMNS}
            writer.writerow(row)

    print(f"✅  CSV 저장 완료: {out_path}")
    print(f"   총 {len(products)}개 상품 | 컬럼 {len(COLUMNS)}개")
    print(f"   ※ detail_images 제외됨 (on-click API로 제공)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="products JSON → CSV 내보내기")
    parser.add_argument(
        "--source",
        default="enriched",
        choices=["enriched", "raw"],
        help="소스 파일 (기본: products_enriched.json)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="출력 CSV 경로 (기본: products_export.csv)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_all",
        help="비의류 포함 전체 출력",
    )
    args = parser.parse_args()

    out = Path(args.out) if args.out else None
    export_csv(source=args.source, out_path=out, include_all=args.include_all)


if __name__ == "__main__":
    main()
