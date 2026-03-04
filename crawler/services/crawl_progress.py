"""
crawl_progress.py — 크롤링 진행 상태 관리 + 병렬 실행 파일 잠금

역할:
  - 실행할 때마다 "다음 카테고리 묶음"을 자동 선택 (순환 방식)
  - data/crawl_progress.json 에 현재 위치 저장 → 재실행 시 이어서 진행
  - data/products_raw.json 에 병렬 저장 시 fcntl 잠금으로 충돌 방지

가상 페이지 전략:
  - 각 사이트별 (카테고리 × 정렬변형) 조합을 미리 정의
  - --pages N 실행 시 다음 N개 슬롯 선택 → 크롤링 → 진행 인덱스 +N 저장
  - 마지막 페이지 도달 시 자동으로 처음(0)부터 재순환
"""
from __future__ import annotations

import sys
import fcntl
import json
import re
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = CRAWLER_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

PROGRESS_PATH = DATA_DIR / "crawl_progress.json"
RAW_PATH = DATA_DIR / "products_raw.json"
LOCK_PATH = DATA_DIR / ".products_raw.lock"

# ─── 29cm 가상 페이지 목록 ────────────────────────────────────────────────
# categoryLargeCode 목록 (여성 의류 카테고리)
_29CM_BASES = [
    # 여성 상의 (tops)
    "https://www.29cm.co.kr/store/category/list?categoryLargeCode=268100100",
    # 여성 하의 (bottoms)
    "https://www.29cm.co.kr/store/category/list?categoryLargeCode=268100200",
    # 여성 아우터 (outer)
    "https://www.29cm.co.kr/store/category/list?categoryLargeCode=268100300",
    # 여성 원피스/스커트 (dress)
    "https://www.29cm.co.kr/store/category/list?categoryLargeCode=268100400",
]

# 정렬 변형: 추천순 / 신상품순 / 할인율순
_29CM_SORTS = [
    "&sort=RECOMMENDED&defaultSort=RECOMMENDED",   # 추천순
    "&sort=NEW&defaultSort=NEW",                   # 신상품순
    "&sort=DISCOUNT&defaultSort=DISCOUNT",         # 할인율순
]

VIRTUAL_PAGES_29CM: list[str] = [
    base + sort
    for sort in _29CM_SORTS      # 정렬 외 루프 → 같은 실행에 모든 카테고리 균등 수집
    for base in _29CM_BASES
]
# 총 12개 가상 페이지 (3 정렬 × 4 카테고리)
# --pages 4 → 추천순 4카테고리 전체 / --pages 8 → 추천+신상 각 4카테고리


# ─── wconcept 가상 페이지 목록 ───────────────────────────────────────────
# BEST 디스플레이 API를 카테고리별로 분리 호출
# displayCategoryType: 10101=전체, 10201=상의, 10202=하의, 10203=아우터, 10204=원피스
_WCONCEPT_BASES = [
    # 여성 전체 BEST (기존)
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10101&gnbType=Y",
    # 여성 상의 BEST
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10201&gnbType=Y",
    # 여성 하의 BEST
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10202&gnbType=Y",
    # 여성 아우터 BEST
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10203&gnbType=Y",
    # 여성 원피스 BEST
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10204&gnbType=Y",
    # 정렬 변형 — 신상 / 할인
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10101&gnbType=Y&sortType=NEW",
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10101&gnbType=Y&sortType=DISCOUNT",
]

_WCONCEPT_SORTS = [""]   # wconcept은 URL 파라미터로 이미 정렬 분리

VIRTUAL_PAGES_WCONCEPT: list[str] = [
    base + sort
    for sort in _WCONCEPT_SORTS  # sort 외 루프 유지 (wconcept은 URL에 정렬 포함)
    for base in _WCONCEPT_BASES
]
# 총 7개 가상 페이지 (카테고리별 URL로 이미 분리됨)


# ─── 무신사 가상 페이지 목록 ─────────────────────────────────────────────
# 사용자가 지정한 카테고리 URL (gf=A: 전체 성별)
_MUSINSA_BASES = [
    # 상의 (001)
    "https://www.musinsa.com/category/001/goods?gf=A",
    # 아우터 (002)
    "https://www.musinsa.com/category/002/goods?gf=A",
    # 하의·바지 (003)
    "https://www.musinsa.com/category/003/goods?gf=A",
    # 하의·원피스·스커트 (100)
    "https://www.musinsa.com/category/100/goods?gf=A",
]

# 정렬 변형: 기본(추천) / 신상품 / 인기순
_MUSINSA_SORTS = [
    "",                          # 기본(추천순)
    "&sortCode=1&sortDirection=DESC",   # 신상품순
    "&sortCode=2&sortDirection=DESC",   # 인기(판매량)순
]

VIRTUAL_PAGES_MUSINSA: list[str] = [
    base + sort
    for sort in _MUSINSA_SORTS      # 정렬 외 루프 → 같은 실행에 모든 카테고리 균등 수집
    for base in _MUSINSA_BASES
]
# 총 12개 가상 페이지 (3 정렬 × 4 카테고리)
# --pages 4 → 추천순 4카테고리 전체 / --pages 8 → 추천+신상 각 4카테고리


# ─── 전체 가상 페이지 맵 ─────────────────────────────────────────────────
VIRTUAL_PAGES: dict[str, list[str]] = {
    "29cm":     VIRTUAL_PAGES_29CM,
    "wconcept": VIRTUAL_PAGES_WCONCEPT,
    "musinsa":  VIRTUAL_PAGES_MUSINSA,
}


# ─── 진행 상태 읽기/쓰기 ─────────────────────────────────────────────────

def load_progress() -> dict:
    """crawl_progress.json 읽기. 없으면 초기 상태 반환."""
    if not PROGRESS_PATH.exists():
        return {}
    try:
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_progress(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_next_seeds(mall: str, pages: int) -> list[str]:
    """
    현재 진행 상태에서 다음 pages개 시드 URL을 반환.
    반환만 하고 인덱스를 업데이트하지는 않음 (advance()로 별도 업데이트).
    """
    pages_list = VIRTUAL_PAGES.get(mall, [])
    if not pages_list:
        return []

    progress = load_progress()
    idx = progress.get(mall, {}).get("next_idx", 0) % len(pages_list)

    selected: list[str] = []
    for i in range(pages):
        selected.append(pages_list[(idx + i) % len(pages_list)])
    return selected


def advance(mall: str, pages: int) -> None:
    """크롤링 완료 후 진행 인덱스를 pages만큼 전진."""
    pages_list = VIRTUAL_PAGES.get(mall, [])
    if not pages_list:
        return

    progress = load_progress()
    mall_state = progress.get(mall, {})
    current = mall_state.get("next_idx", 0)
    new_idx = (current + pages) % len(pages_list)
    progress[mall] = {
        "next_idx": new_idx,
        "last_run": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_pages": len(pages_list),
        "last_pages_crawled": pages,
    }
    save_progress(progress)
    print(
        f"[{mall}] 진행 상태 저장: {current} → {new_idx} "
        f"(전체 {len(pages_list)}개 가상 페이지 중)"
    )


def progress_summary() -> None:
    """현재 진행 상태를 터미널에 출력."""
    progress = load_progress()
    print("\n─ 크롤링 진행 상태 ──────────────────────────────────")
    for mall, pages_list in VIRTUAL_PAGES.items():
        state = progress.get(mall, {})
        idx = state.get("next_idx", 0) % len(pages_list) if pages_list else 0
        last = state.get("last_run", "없음")
        print(
            f"  {mall:10s}: 다음 시작 인덱스 {idx}/{len(pages_list)} "
            f"| 마지막 실행: {last}"
        )
    print("─────────────────────────────────────────────────\n")


# ─── 잠금 기반 저장 ───────────────────────────────────────────────────────

def locked_merge_save(new_items: list[dict]) -> int:
    """
    fcntl 파일 잠금을 획득한 뒤 products_raw.json 에 병합 저장.
    반환값: 새로 추가된 상품 수.

    중복 키 기준 (우선순위 순):
      1. mall + itemCd (상품 고유코드, wconcept/musinsa 등에서 추출)
      2. mall + URL ID (29cm: /catalog|products/{id}, wconcept: /Product/{id}, musinsa: /goods/{id})
      3. source_url 전체
      4. id 필드
      5. mall + name + price fallback
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.touch(exist_ok=True)

    lock_file = open(LOCK_PATH, "w")
    try:
        deadline = time.time() + 60
        while True:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > deadline:
                    print("⚠️  잠금 획득 시간 초과. 강제 저장 시도.")
                    break
                time.sleep(0.5)

        existing: list[dict] = []
        if RAW_PATH.exists():
            try:
                existing = json.loads(RAW_PATH.read_text(encoding="utf-8"))
            except Exception:
                existing = []

        def _dedupe_key(item: dict) -> str:
            mall = str(item.get("mall", "")).strip().lower()
            source_url = str(item.get("source_url", "")).strip()

            # ① itemCd 기반 (wconcept / musinsa)
            item_cd = str(item.get("item_cd", "") or item.get("itemCd", "")).strip()
            if item_cd and item_cd.isdigit():
                return f"{mall}:cd:{item_cd}"

            # ② URL 내 숫자 ID 추출
            if source_url:
                if mall == "29cm":
                    m = re.search(r"/(?:catalog|products)/(\d+)", source_url)
                    if m:
                        return f"29cm:{m.group(1)}"
                elif mall == "wconcept":
                    m = re.search(r"/Product/(\d+)", source_url, re.IGNORECASE)
                    if m:
                        return f"wconcept:{m.group(1)}"
                elif mall == "musinsa":
                    # 실제 URL: /products/{id}  (구 /goods/{id} 아님)
                    m = re.search(r"/products/(\d+)", source_url)
                    if m:
                        return f"musinsa:{m.group(1)}"
                return f"url:{source_url}"

            item_id = str(item.get("id", "")).strip()
            if item_id:
                return f"id:{item_id}"

            name = str(item.get("name", "")).strip().lower()
            price = int(item.get("price_krw", 0) or 0)
            return f"np:{mall}:{name}:{price}"

        merged_map: dict[str, dict] = {_dedupe_key(p): p for p in existing}
        new_count = 0
        for item in new_items:
            key = _dedupe_key(item)
            if key not in merged_map:
                new_count += 1
            merged_map[key] = item

        merged = list(merged_map.values())
        RAW_PATH.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  기존 {len(existing)}개 + 신규 {new_count}개 → 총 {len(merged)}개 저장")
        return new_count

    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
