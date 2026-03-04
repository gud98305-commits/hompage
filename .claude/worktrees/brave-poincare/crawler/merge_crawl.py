#!/usr/bin/env python3
"""
크롤링 결과 파일 결합 스크립트
────────────────────────────────────────────────────────────────────
팀원 각자가 crawl_A.json / crawl_B.json / ... 을 보내오면,
이 스크립트가 data/ 폴더의 crawl_*.json 파일을 모두 읽어
source_url 기준으로 중복 제거 후 products_enriched.json 으로 저장.

사용법:
  1. data/ 폴더에 팀원 파일 모두 복사:
       data/crawl_A.json
       data/crawl_B.json
       data/crawl_C.json
       ...

  2. 실행:
       .venv/bin/python scripts/merge_crawl.py

  3. 결과:
       data/products_enriched.json  ← 서버가 읽는 파일
       data/merge_report.txt        ← 결합 상세 리포트

옵션:
  --input  : crawl_*.json 이외 파일 패턴 지정  (기본: data/crawl_*.json)
  --output : 최종 저장 경로 (기본: data/products_enriched.json)
  --backup : 기존 products_enriched.json 백업 (기본: True)
────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sys
import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[0]
DATA_DIR = CRAWLER_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

ENRICHED = DATA_DIR / "products_enriched.json"


def load_json_file(path: Path) -> list[dict]:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        print(f"  [경고] {path.name}: 리스트 형식이 아님 → 건너뜀")
        return []
    except json.JSONDecodeError as e:
        print(f"  [오류] {path.name}: JSON 파싱 실패 → {e}")
        return []
    except Exception as e:
        print(f"  [오류] {path.name}: 읽기 실패 → {e}")
        return []


def merge(
    input_pattern: str,
    output_path: Path,
    backup: bool,
) -> None:
    # ── 입력 파일 검색 ────────────────────────────────────────────────
    input_files = sorted(CRAWLER_ROOT.glob(input_pattern))
    if not input_files:
        print(f"[오류] 파일을 찾을 수 없습니다: {input_pattern}")
        print("  → data/ 폴더에 crawl_A.json, crawl_B.json 등을 복사했는지 확인하세요.")
        sys.exit(1)

    print(f"\n[병합 시작] {len(input_files)}개 파일 발견")
    print("=" * 60)

    # ── 파일별 로드 ───────────────────────────────────────────────────
    all_products: list[dict] = []
    file_stats: list[tuple[str, int, int]] = []  # (이름, 원본, 유효)

    for fpath in input_files:
        products = load_json_file(fpath)
        valid    = [p for p in products if p.get("source_url")]
        print(f"  {fpath.name:30s}  {len(products):>4d}개 로드, {len(valid):>4d}개 유효")
        file_stats.append((fpath.name, len(products), len(valid)))
        all_products.extend(valid)

    print(f"\n  합계: {len(all_products)}개 (중복 제거 전)")

    # ── source_url 기준 중복 제거 ──────────────────────────────────────
    seen_urls:  set[str]   = set()
    unique:     list[dict] = []
    duplicates: int        = 0

    for p in all_products:
        url = p.get("source_url", "")
        if url in seen_urls:
            duplicates += 1
            continue
        seen_urls.add(url)
        unique.append(p)

    print(f"  중복 제거: {duplicates}개 제거됨")
    print(f"  최종: {len(unique)}개")

    # ── 카테고리별 통계 ────────────────────────────────────────────────
    cat_stats: dict[str, int] = {}
    gender_stats: dict[str, int] = {"남성": 0, "여성": 0, "공용": 0, "미분류": 0}
    for p in unique:
        cat = p.get("category", "기타")
        cat_stats[cat] = cat_stats.get(cat, 0) + 1
        g = p.get("gender", "")
        if g == "M":
            gender_stats["남성"] += 1
        elif g == "F":
            gender_stats["여성"] += 1
        elif g == "A":
            gender_stats["공용"] += 1
        else:
            gender_stats["미분류"] += 1

    print("\n  [카테고리 분포]")
    for cat, cnt in sorted(cat_stats.items()):
        print(f"    {cat:12s}: {cnt:>4d}개")

    print("\n  [성별 분포]")
    for g, cnt in gender_stats.items():
        print(f"    {g:6s}: {cnt:>4d}개")

    # ── 기존 파일 백업 ─────────────────────────────────────────────────
    if backup and output_path.exists():
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = output_path.with_suffix(f".BACKUP_{ts}.json")
        shutil.copy2(output_path, bak)
        print(f"\n  [백업] 기존 파일 → {bak.name}")

    # ── 저장 ───────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(unique, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[저장 완료] {output_path}")

    # ── 리포트 저장 ────────────────────────────────────────────────────
    report_path = DATA_DIR / "merge_report.txt"
    with report_path.open("w", encoding="utf-8") as f:
        f.write(f"병합 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"입력 파일: {len(input_files)}개\n\n")
        f.write("파일별 현황:\n")
        for name, total, valid in file_stats:
            f.write(f"  {name}: {total}개 로드, {valid}개 유효\n")
        f.write(f"\n중복 제거: {duplicates}개\n")
        f.write(f"최종 상품 수: {len(unique)}개\n\n")
        f.write("카테고리 분포:\n")
        for cat, cnt in sorted(cat_stats.items()):
            f.write(f"  {cat}: {cnt}개\n")
        f.write("\n성별 분포:\n")
        for g, cnt in gender_stats.items():
            f.write(f"  {g}: {cnt}개\n")
    print(f"[리포트] {report_path}")

    print("\n" + "=" * 60)
    print(f"✅ 병합 완료: 총 {len(unique)}개 상품 → {output_path.name}")
    print("   이제 서버를 재시작하면 새 데이터가 반영됩니다.")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(
        description="크롤링 결과 JSON 파일 결합 (source_url 기준 중복 제거)"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/crawl_*.json",
        help="입력 파일 glob 패턴 (기본: data/crawl_*.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(ENRICHED),
        help=f"출력 파일 경로 (기본: {ENRICHED})",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="기존 products_enriched.json 백업 안 함",
    )
    args = parser.parse_args()

    merge(
        input_pattern=args.input,
        output_path=Path(args.output),
        backup=not args.no_backup,
    )


if __name__ == "__main__":
    main()
