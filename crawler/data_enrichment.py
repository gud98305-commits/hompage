"""
data_enrichment.py
크롤링된 products_raw.json 을 읽어
색상(colors) · 카테고리(category) · is_clothing 메타데이터를 추가한 뒤
products_enriched.json 에 저장한다.

사용법:
    cd "0227 test"
    python data_enrichment.py
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
RAW_PATH = ROOT / "data" / "products_raw.json"
OUT_PATH = ROOT / "data" / "products_enriched.json"

# ── 색상 탐지 ──────────────────────────────────────────────────────────
COLOR_KEYWORDS: dict[str, list[str]] = {
    "black":      ["black", "blk", "noir", "블랙", "onyx", "midnight", "jet"],
    "white":      ["white", "화이트", "blanc", "pearl"],
    "ivory":      ["ivory", "ecru", "cream", "off-white", "offwhite", "natural", "아이보리", "크림"],
    "beige":      ["beige", "베이지", "sand", "taupe", "nude"],
    "gray":       ["grey", "gray", "그레이", "silver", "ash", "melange", "smoke", "charcoal"],
    "brown":      ["brown", "브라운", "d.brown", "chocolate", "mocha", "cocoa"],
    "camel":      ["camel", "카멜", "tan", "caramel", "honey", "biscuit"],
    "navy":       ["navy", "네이비", "marine", "indigo"],
    "cobalt":     ["cobalt", "royal blue", "코발트"],
    "skyblue":    ["sky blue", "sky", "스카이블루", "baby blue", "light blue"],
    "olive":      ["olive", "올리브", "army", "military", "earth"],
    "khaki":      ["khaki", "카키"],
    "deepgreen":  ["deep green", "forest", "teal", "emerald", "green", "그린", "딥그린"],
    "mint":       ["mint", "민트", "sage", "seafoam", "aqua"],
    "lavender":   ["lavender", "라벤더", "lilac", "mauve"],
    "pink":       ["pink", "핑크", "blush", "dusty rose", "rose", "baby pink"],
    "red":        ["red", "레드", "scarlet", "tomato", "cherry", "crimson"],
    "burgundy":   ["burgundy", "bordeaux", "버건디", "maroon"],
    "wine":       ["wine", "와인", "merlot"],
    "yellow":     ["yellow", "옐로우", "mustard", "butter", "lemon", "canary"],
    "orange":     ["orange", "오렌지", "rust", "terracotta", "apricot"],
    "purple":     ["purple", "퍼플", "violet", "grape", "plum"],
    "multicolor": ["multicolor", "multi", "stripe", "check", "pattern", "print", "plaid",
                   "3col", "4col", "5col", "2col", "multi-color"],
}

# ── 카테고리 탐지 ──────────────────────────────────────────────────────
# 점수 기반 분류(키워드 overlap 보완). 1000개 이상 배치에서도 O(n)으로 동작.
CAT_KEYWORDS: dict[str, list[str]] = {
    "top": [
        "knit", "t-shirt", "tshirt", "shirt", "blouse", "cardigan", "sweater",
        "zip-up", "pullover", "top", "tee", "티셔츠", "셔츠", "블라우스", "니트",
        "가디건", "스웨터", "맨투맨", "후드", "hoodie", "sweatshirt", "pk", "polo",
        "tank", "tubetop", "sleeveless", "나시", "크롭탑", "집업", "zip up",
        "파자마", "pajama", "잠옷", "set-up", "셋업",
    ],
    "bottom": [
        "pants", "trouser", "skirt", "jogger", "denim", "jeans", "shorts",
        "legging", "슬랙스", "팬츠", "스커트", "청바지", "데님", "반바지",
        "와이드", "baggy", "cargo", "capri",
    ],
    "outer": [
        "coat", "jacket", "trench", "blazer", "parka", "windbreaker", "vest",
        "anorak", "코트", "자켓", "재킷", "트렌치", "패딩", "점퍼", "아우터",
        "cardigan outer", "후리스", "fleece", "가운", "robe",
    ],
    "dress": [
        "dress", "one-piece", "romper", "jumpsuit", "onepiece",
        "원피스", "점프수트", "수트",
    ],
    "shoes": [
        "shoe", "shoes", "sneaker", "sneakers", "loafer", "loafers", "heel", "heels",
        "boot", "boots", "sandal", "sandals", "slipper", "slippers", "flat", "flats",
        "스니커즈", "슈즈", "로퍼", "힐", "부츠", "샌들", "슬리퍼", "플랫",
    ],
    "accessory": [
        "bag", "bags", "backpack", "tote", "clutch", "wallet", "card case", "pouch",
        "belt", "cap", "beanie", "hat", "scarf", "muffler", "necklace", "earring",
        "ring", "bracelet", "watch", "jewelry", "jewellery", "keyring", "key case",
        "가방", "백", "토트", "클러치", "지갑", "카드지갑", "파우치", "벨트",
        "모자", "캡", "비니", "머플러", "스카프", "목걸이", "귀걸이", "반지",
        "팔찌", "시계", "주얼리", "악세서리", "액세서리",
    ],
}

# 동점일 때 우선순위
CATEGORY_PRIORITY = ("dress", "outer", "top", "bottom", "shoes", "accessory")

NON_CLOTHING_KEYWORDS: list[str] = [
    "소파", "침대", "청소기", "향수", "퍼퓸", "로션", "샴푸", "트리트먼트", "바디",
    "칼", "나이프", "냄비", "프라이팬", "주전자", "그라인더", "커피", "모카", "비알레띠",
    "화장대", "선반", "테이블", "스툴", "조명", "의자", "소품",
    "글로스", "립", "파운데이션", "쿠션", "마스카라", "아이섀도", "화장품",
    "이불", "베개", "침구", "건조대", "다림판",
    "로봇", "인덕션", "전기", "가전",
    "향초", "캔들", "디퓨저",
]


def _norm_text(text: str) -> str:
    # 한/영 혼합 문자열에서 토큰 매칭 안정화를 위해 특수문자 축소
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def detect_colors(name: str) -> list[str]:
    n = _norm_text(name)
    found = [c for c, kws in COLOR_KEYWORDS.items() if any(kw in n for kw in kws)]
    return found or ["multicolor"]


def detect_category(name: str) -> str | None:
    n = _norm_text(name)

    # 비의류 키워드가 있더라도 의류 강한 신호가 함께 있으면 의류로 판정
    has_non_clothing = any(nc in n for nc in NON_CLOTHING_KEYWORDS)

    scores: dict[str, int] = {
        "top": 0,
        "bottom": 0,
        "outer": 0,
        "dress": 0,
        "shoes": 0,
        "accessory": 0,
    }
    for cat, kws in CAT_KEYWORDS.items():
        for kw in kws:
            if kw in n:
                # 긴 키워드일수록 의미가 명확하므로 약간 가중치
                scores[cat] += 2 if len(kw) >= 6 else 1

    # 도메인 보정: 자주 혼동되는 케이스 우선 보정
    if any(k in n for k in ["jacket", "coat", "blazer", "트렌치", "패딩", "점퍼", "가운", "robe"]):
        scores["outer"] += 3
    if any(k in n for k in ["pants", "trouser", "skirt", "jeans", "슬랙스", "팬츠", "스커트", "청바지"]):
        scores["bottom"] += 3
    if any(k in n for k in ["hoodie", "sweatshirt", "후드", "맨투맨", "shirt", "blouse", "knit", "티셔츠", "셔츠"]):
        scores["top"] += 3
    if any(k in n for k in ["dress", "one-piece", "onepiece", "원피스", "jumpsuit", "점프수트"]):
        scores["dress"] += 4
    if any(k in n for k in ["shoe", "sneaker", "loafer", "heel", "boot", "sandal", "slipper", "슈즈", "스니커즈", "로퍼", "힐", "부츠", "샌들", "슬리퍼"]):
        scores["shoes"] += 4
    if any(k in n for k in ["bag", "wallet", "card case", "belt", "hat", "cap", "beanie", "watch", "jewelry", "jewellery", "가방", "지갑", "벨트", "모자", "캡", "비니", "시계", "주얼리", "액세서리", "악세서리"]):
        scores["accessory"] += 4

    best_cat = max(scores, key=scores.get)
    best_score = scores[best_cat]

    # 의류 점수가 없으면 비의류
    if best_score == 0:
        return None

    # 비의류 신호가 있고 의류 점수가 약하면 제외
    if has_non_clothing and best_score < 3:
        return None

    # 동점 처리
    tied = [cat for cat, sc in scores.items() if sc == best_score]
    if len(tied) == 1:
        return best_cat
    for cat in CATEGORY_PRIORITY:
        if cat in tied:
            return cat
    return best_cat


# ── 메인 ──────────────────────────────────────────────────────────────
def enrich(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for p in products:
        cat = detect_category(p.get("name", ""))
        if cat is None:
            continue
        ep = dict(p)
        ep["category"] = cat
        ep["colors"] = detect_colors(p.get("name", ""))
        ep["is_fashion"] = True
        ep["is_clothing"] = cat in {"top", "bottom", "outer", "dress"}
        if not ep.get("price_jpy"):
            ep["price_jpy"] = round(int(ep.get("price_krw", 0)) * 0.11 / 10) * 10
        enriched.append(ep)
    return enriched


def run_enrichment(raw_path: Path = RAW_PATH, out_path: Path = OUT_PATH) -> dict[str, Any]:
    if not raw_path.exists():
        raise FileNotFoundError(f"{raw_path} 파일이 없습니다.")

    raw: list[dict[str, Any]] = json.loads(raw_path.read_text(encoding="utf-8"))
    enriched = enrich(raw)

    out_path.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cat_counts = Counter(p["category"] for p in enriched)
    color_counts = Counter(c for p in enriched for c in p["colors"])

    return {
        "raw_count": len(raw),
        "enriched_count": len(enriched),
        "skipped_count": len(raw) - len(enriched),
        "category_counts": dict(cat_counts),
        "top_colors": color_counts.most_common(10),
        "out_path": str(out_path),
    }


if __name__ == "__main__":
    if not RAW_PATH.exists():
        print(f"❌ {RAW_PATH} 파일이 없습니다. 먼저 크롤러를 실행하세요.")
        print("   python -m backend.services.crawl_pipeline --source both --pages 2 --max 80 --verbose")
        raise SystemExit(1)

    stats = run_enrichment()

    print(f"원본 상품:     {stats['raw_count']:>4}개")
    print(f"비의류 제외:   {stats['skipped_count']:>4}개")
    print(f"최종 의류:     {stats['enriched_count']:>4}개")
    print("\n카테고리별:")
    for cat, cnt in sorted(stats["category_counts"].items(), key=lambda x: x[1], reverse=True):
        print(f"  {cat:>10}: {cnt}개")
    print("\n색상 TOP 10:")
    for color, cnt in stats["top_colors"]:
        print(f"  {color:>12}: {cnt}개")
    print(f"\n✅ 저장: {stats['out_path']}")
