#!/usr/bin/env python3
"""
SEOULFIT Crawler — 메인 진입점

사용법:
  python run.py --mall wconcept --limit 1000
  python run.py --mall 29cm    --limit 1000
  python run.py --mall all     --limit 3000   # 두 사이트 합산
  python run.py --status                       # 진행 상태 확인
  python run.py --reset                        # 진행 상태 초기화

옵션:
  --mall    : wconcept | 29cm | all (기본: all)
  --limit   : 수집할 상품 총 수 (기본: 3000)
  --no-enrich : GPT 데이터 정제 생략
  --status  : 진행 상태만 출력
  --reset   : 진행 상태 초기화
"""
from __future__ import annotations

import sys
import argparse
import json
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[0]
DATA_DIR = CRAWLER_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if str(CRAWLER_ROOT) not in sys.path:
    sys.path.append(str(CRAWLER_ROOT))

from dotenv import load_dotenv

load_dotenv(CRAWLER_ROOT / ".env")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)

from pipeline import run_bulk_crawl
from progress import progress_summary, reset_progress


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(description="SEOULFIT Crawler")
    parser.add_argument("--mall", default="all", choices=["wconcept", "29cm", "all"])
    parser.add_argument("--limit", type=int, default=3000)
    parser.add_argument("--no-enrich", action="store_true", help="GPT 정제 생략")
    parser.add_argument("--status", action="store_true", help="진행 상태 출력 후 종료")
    parser.add_argument("--reset", action="store_true", help="진행 상태 초기화")
    args = parser.parse_args()

    if args.status:
        print(progress_summary())
        return

    if args.reset:
        reset_progress()
        print("[reset] 진행 상태를 초기화했습니다.")
        return

    malls = ["wconcept", "29cm"] if args.mall == "all" else [args.mall]
    limit_each = args.limit // len(malls)

    all_products: list[dict] = []
    for mall in malls:
        print(f"\n{'='*50}")
        print(f"[{mall}] 수집 시작 (목표: {limit_each}개)")
        print(f"{'='*50}")
        products = run_bulk_crawl(mall=mall, limit=limit_each)
        all_products.extend(products)
        print(f"[{mall}] 완료: {len(products)}개 수집")

    # 기존 데이터와 병합 저장
    raw_path = DATA_DIR / "products_raw.json"
    existing: list[dict] = []
    if raw_path.exists():
        try:
            existing = json.loads(raw_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    seen_ids = {p.get("id") for p in existing if p.get("id")}
    new_products = [p for p in all_products if p.get("id") not in seen_ids]
    merged = existing + new_products

    raw_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[저장] {raw_path} — 총 {len(merged)}개 (신규 {len(new_products)}개)")

    if not args.no_enrich:
        print("\n[정제] GPT-4o-mini 데이터 정제 시작...")
        import enrich
        enrich.run(src=raw_path, dst=DATA_DIR / "products_enriched.json")
    else:
        print("\n[정제 생략] --no-enrich 플래그 감지")


if __name__ == "__main__":
    main()
