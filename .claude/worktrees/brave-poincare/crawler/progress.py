"""
progress.py — 크롤링 진행 상태 관리

역할:
  - data/progress.json 에 현재 위치 저장 → 재실행 시 이어서 진행
  - data/products_raw.json 에 병렬 저장 시 fcntl 잠금으로 충돌 방지
"""
from __future__ import annotations

import sys
import fcntl
import json
import re
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[0]
DATA_DIR = CRAWLER_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

PROGRESS_PATH = DATA_DIR / "progress.json"
RAW_PATH = DATA_DIR / "products_raw.json"
LOCK_PATH = DATA_DIR / ".products_raw.lock"

# ─── 29cm 가상 페이지 ─────────────────────────────────────────────────────────
_29CM_BASES = [
    "https://www.29cm.co.kr/store/category/list?categoryLargeCode=268100100",  # 상의
    "https://www.29cm.co.kr/store/category/list?categoryLargeCode=268100200",  # 하의
    "https://www.29cm.co.kr/store/category/list?categoryLargeCode=268100300",  # 아우터
    "https://www.29cm.co.kr/store/category/list?categoryLargeCode=268100400",  # 원피스
]
_29CM_SORTS = [
    "&sort=RECOMMENDED&defaultSort=RECOMMENDED",
    "&sort=NEW&defaultSort=NEW",
    "&sort=DISCOUNT&defaultSort=DISCOUNT",
]
VIRTUAL_PAGES_29CM: list[str] = [
    base + sort for sort in _29CM_SORTS for base in _29CM_BASES
]

# ─── W컨셉 가상 페이지 ────────────────────────────────────────────────────────
_WCONCEPT_BASES = [
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10101&gnbType=Y",
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10201&gnbType=Y",
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10202&gnbType=Y",
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10203&gnbType=Y",
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10204&gnbType=Y",
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10101&gnbType=Y&sortType=NEW",
    "https://display.wconcept.co.kr/rn/best?displayCategoryType=10101&gnbType=Y&sortType=DISCOUNT",
]
VIRTUAL_PAGES_WCONCEPT: list[str] = _WCONCEPT_BASES

VIRTUAL_PAGES: dict[str, list[str]] = {
    "29cm":     VIRTUAL_PAGES_29CM,
    "wconcept": VIRTUAL_PAGES_WCONCEPT,
}


# ─── 진행 상태 관리 ───────────────────────────────────────────────────────────

def load_progress() -> dict:
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


def reset_progress() -> None:
    if PROGRESS_PATH.exists():
        PROGRESS_PATH.unlink()


def get_next_seeds(mall: str, pages: int) -> list[str]:
    pages_list = VIRTUAL_PAGES.get(mall, [])
    if not pages_list:
        return []
    progress = load_progress()
    idx = progress.get(mall, {}).get("next_idx", 0) % len(pages_list)
    return [pages_list[(idx + i) % len(pages_list)] for i in range(pages)]


def advance(mall: str, pages: int) -> None:
    pages_list = VIRTUAL_PAGES.get(mall, [])
    if not pages_list:
        return
    progress = load_progress()
    current = progress.get(mall, {}).get("next_idx", 0)
    new_idx = (current + pages) % len(pages_list)
    progress[mall] = {
        "next_idx": new_idx,
        "last_run": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_pages": len(pages_list),
        "last_pages_crawled": pages,
    }
    save_progress(progress)


def progress_summary() -> str:
    progress = load_progress()
    lines = ["\n─ 크롤링 진행 상태 ──────────────────────────────────"]
    for mall, pages_list in VIRTUAL_PAGES.items():
        state = progress.get(mall, {})
        idx = state.get("next_idx", 0) % len(pages_list) if pages_list else 0
        last = state.get("last_run", "없음")
        lines.append(
            f"  {mall:10s}: 다음 시작 {idx}/{len(pages_list)} | 마지막 실행: {last}"
        )
    lines.append("─────────────────────────────────────────────────\n")
    return "\n".join(lines)


# ─── 잠금 기반 병합 저장 ──────────────────────────────────────────────────────

def locked_merge_save(new_items: list[dict]) -> int:
    """fcntl 잠금으로 products_raw.json 에 안전하게 병합 저장. 반환: 신규 추가 수."""
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

        def _key(item: dict) -> str:
            mall = str(item.get("mall", "")).strip().lower()
            url = str(item.get("source_url", "")).strip()
            item_cd = str(item.get("item_cd", "") or item.get("itemCd", "")).strip()
            if item_cd and item_cd.isdigit():
                return f"{mall}:cd:{item_cd}"
            if url:
                if mall == "29cm":
                    m = re.search(r"/(?:catalog|products)/(\d+)", url)
                    if m:
                        return f"29cm:{m.group(1)}"
                elif mall == "wconcept":
                    m = re.search(r"/Product/(\d+)", url, re.IGNORECASE)
                    if m:
                        return f"wconcept:{m.group(1)}"
                return f"url:{url}"
            pid = str(item.get("id", "")).strip()
            if pid:
                return f"id:{pid}"
            return f"np:{mall}:{item.get('name','')}:{item.get('price_krw',0)}"

        merged_map: dict[str, dict] = {_key(p): p for p in existing}
        new_count = 0
        for item in new_items:
            k = _key(item)
            if k not in merged_map:
                new_count += 1
            merged_map[k] = item

        merged = list(merged_map.values())
        RAW_PATH.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  기존 {len(existing)}개 + 신규 {new_count}개 → 총 {len(merged)}개 저장")
        return new_count

    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
