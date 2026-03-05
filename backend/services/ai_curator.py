from __future__ import annotations

import json
import os
import random
import re
from typing import Any, cast

from openai import OpenAI  # type: ignore[import-untyped]
from shared.brand_utils import extract_brand, guess_brand_origin  # type: ignore[import-untyped]

# ── 색상 정규화 맵 (프론트에서 오는 값 → 정규화된 내부 키) ──────────────
COLOR_NORMALIZE: dict[str, list[str]] = {
    "black":      ["black","blk","jet black","noir","onyx","midnight"],
    "white":      ["white","blanc","pearl","wht"],
    "ivory":      ["ivory","ecru","cream","off-white","offwhite","oatmeal","natural","크림","아이보리"],
    "beige":      ["beige","sand","taupe","nude"],
    "gray":       ["grey","gray","silver","ash","melange","smoke","charcoal"],
    "brown":      ["brown","chocolate","mocha","cocoa"],
    "camel":      ["camel","caramel","tan","honey","biscuit"],
    "navy":       ["navy","marine","indigo"],
    "cobalt":     ["cobalt","royal blue","electric blue","blue"],
    "skyblue":    ["sky","sky blue","light blue","baby blue","skyblue"],
    "olive":      ["olive","army","khaki","military","earth"],
    "khaki":      ["khaki"],
    "deepgreen":  ["deep green","forest","hunter green","emerald","green","teal"],
    "mint":       ["mint","sage","seafoam","aqua"],
    "lavender":   ["lavender","lilac","mauve"],
    "pink":       ["pink","blush","rose","dusty rose","baby pink"],
    "red":        ["red","scarlet","tomato","cherry","crimson"],
    "burgundy":   ["burgundy","bordeaux","maroon"],
    "wine":       ["wine","merlot"],
    "yellow":     ["yellow","mustard","butter","lemon","canary"],
    "orange":     ["orange","rust","terracotta","apricot"],
    "multicolor": ["multi","multicolor","stripe","check","pattern","print","plaid"],
    "purple":     ["purple","violet","grape","plum"],
}

# 역방향 맵: alias → canonical key
_COLOR_ALIAS_MAP: dict[str, str] = {}
for canonical, aliases in COLOR_NORMALIZE.items():
    _COLOR_ALIAS_MAP[canonical] = canonical
    for alias in aliases:
        _COLOR_ALIAS_MAP[alias.lower()] = canonical

# 카테고리 그룹 (프론트 값 → 대표 카테고리)
CATEGORY_GROUPS: dict[str, set[str]] = {
    "top": {"top"},
    "bottom": {"bottom"},
    "outer": {"outer"},
    "dress": {"dress"},
}

# 세부 카테고리 → base 카테고리 역방향 맵 (sub_category 기반 대분류 판단용)
BASE_CATEGORY_FROM_FINE: dict[str, str] = {
    "tshirt": "top",  "shirt": "top",   "knit": "top",  "hoodie": "top",
    "pants":  "bottom", "skirt": "bottom", "denim": "bottom",
    "jacket": "outer",  "coat": "outer",
    "dress":  "dress",  "suit": "dress",
}

# 세부 카테고리 규칙 (정확 매칭)
FINE_CATEGORY_RULES: dict[str, dict[str, Any]] = {
    "tshirt": {
        "base": "top",
        "keywords": ["t-shirt", "tshirt", "tee", "티셔츠", "반팔", "긴팔티", "롱슬리브"],
    },
    "shirt": {
        "base": "top",
        "keywords": ["shirt", "blouse", "셔츠", "블라우스"],
    },
    "knit": {
        "base": "top",
        "keywords": ["knit", "sweater", "cardigan", "니트", "스웨터", "가디건"],
    },
    "hoodie": {
        "base": "top",
        "keywords": ["hoodie", "sweatshirt", "후드", "맨투맨", "집업", "zip-up", "zip up"],
    },
    "pants": {
        "base": "bottom",
        "keywords": ["pants", "trouser", "slacks", "팬츠", "슬랙스", "바지", "와이드", "레깅스", "jogger", "cargo"],
    },
    "skirt": {
        "base": "bottom",
        "keywords": ["skirt", "스커트", "치마"],
    },
    "denim": {
        "base": "bottom",
        "keywords": ["denim", "jean", "청바지", "데님"],
    },
    "jacket": {
        "base": "outer",
        "keywords": ["jacket", "blouson", "jumper", "자켓", "재킷", "블루종", "점퍼"],
    },
    "coat": {
        "base": "outer",
        "keywords": ["coat", "trench", "parka", "코트", "트렌치", "패딩"],
    },
    "suit": {
        "base": "dress",
        "keywords": ["suit", "jumpsuit", "점프수트", "수트", "셋업", "set-up", "set up"],
    },
}

# 색상 인접군 (0건 완화용, 완전 랜덤 확장 방지는 유지)
COLOR_FAMILIES: dict[str, set[str]] = {
    "black": {"black"},
    "white": {"white", "ivory"},
    "ivory": {"ivory", "white", "beige"},
    "gray": {"gray", "black"},
    "beige": {"beige", "ivory", "camel", "brown"},
    "brown": {"brown", "camel", "beige"},
    "olive": {"olive", "khaki", "deepgreen"},
    "red": {"red", "burgundy", "wine"},
    "cobalt": {"cobalt", "navy", "skyblue"},
    "skyblue": {"skyblue", "cobalt"},
    "pink": {"pink", "lavender"},
}

STYLE_TOKEN_MAP: dict[str, dict[str, list[str]]] = {
    "minimal": {
        "plus": [
            "minimal", "basic", "클래식", "베이직", "미니멀", "clean", "심플",
            "simple", "classic", "essential", "plain", "solid", "mono",
            "clean fit", "무지", "스탠다드", "standard", "슬림", "slim",
        ],
        "minus": [
            "glitter", "글리터", "프릴", "frill", "lace", "레이스",
            "cargo", "카고", "baggy", "graphic", "그래픽", "print",
            "스트리트", "street", "파티", "party",
        ],
    },
    "street": {
        "plus": [
            "street", "스트리트", "oversize", "오버핏", "cargo", "utility",
            "와이드", "skate", "grunge", "graphic", "그래픽", "hip",
            "baggy", "bucket", "windbreaker", "워크웨어", "workwear",
        ],
        "minus": [
            "formal", "tailored", "오피스", "정장", "블레이저",
            "lace", "레이스", "프릴", "frill", "romantic",
        ],
    },
    "vintage": {
        "plus": [
            "vintage", "레트로", "복고", "washed", "워싱", "데님", "트위드",
            "retro", "corduroy", "코듀로이", "체크", "check", "플란넬",
            "flannel", "헤링본", "herringbone", "아카이브", "archive",
        ],
        "minus": [
            "formal", "tailored", "정장", "오피스", "sleek", "미니멀",
        ],
    },
    "casual": {
        "plus": [
            "casual", "데일리", "편안", "코튼", "니트", "후드", "맨투맨",
            "cotton", "daily", "sweat", "comfort", "everyday", "일상",
            "relax", "릴렉스", "lounge", "라운지",
        ],
        "minus": [
            "formal", "tailored", "정장", "오피스", "leather", "레더",
            "glitter", "글리터",
        ],
    },
    "formal": {
        "plus": [
            "formal", "tailored", "오피스", "블레이저", "슬랙스", "셔츠",
            "blazer", "slacks", "oxford", "linen", "trousers",
            "tweed", "wool", "suit", "jacket", "polo", "button",
            "버튼", "collar", "칼라", "dress pants", "dress shirt",
            "가디건", "cardigan", "니트", "knit",
            "비즈니스", "business", "오피스룩", "office",
            # "shirt" 제거 → sweatshirt 오매칭 방지. 셔츠(Korean)와 구체적 표현으로 대체
            "collar shirt", "button-down", "button down",
        ],
        "minus": [
            "후드", "hoodie", "맨투맨", "sweatshirt", "스웨트",
            "cargo", "카고", "baggy", "oversize", "오버핏",
            "그래픽", "graphic", "crop", "크롭", "스트리트", "street",
        ],
    },
    "y2k": {
        "plus": [
            "y2k", "low-rise", "로우라이즈", "크롭", "baby tee", "cargo",
            "글리터", "레트로", "2000", "millennium", "나비", "metallic",
            "메탈릭", "butterfly", "low rise", "mini", "미니",
        ],
        "minus": [
            "formal", "오피스", "정장", "tailored", "미니멀", "minimal",
        ],
    },
    "romantic": {
        "plus": [
            "romantic", "로맨틱", "레이스", "프릴", "리본", "플라워", "시어",
            "lace", "frill", "ribbon", "flower", "floral", "sheer",
            "ruffle", "러플", "puff", "퍼프", "chiffon", "시폰",
            "embroidery", "자수", "pleats", "셔링", "shirring",
        ],
        "minus": [
            "leather", "레더", "cargo", "카고", "스트리트", "street",
            "후드", "맨투맨", "hoodie", "그래픽", "graphic",
        ],
    },
    "preppy": {
        "plus": [
            "preppy", "프레피", "카라", "니트베스트", "플리츠", "로퍼",
            "polo", "check", "argyle", "아가일", "knit vest", "collar",
            "stripe", "스트라이프", "vest", "베스트", "ribbon",
        ],
        "minus": [
            "후드", "맨투맨", "hoodie", "sweatshirt", "cargo",
            "leather", "크롭", "crop", "오버핏", "oversize",
        ],
    },
}

BODY_TYPE_TOKEN_MAP: dict[str, dict[str, list[str]]] = {
    # STRAIGHT형 (슬림·근육질 I라인) — 타이트/저스트핏으로 체형 라인 강조
    "slim": {
        "plus": [
            "slim", "skinny", "타이트", "슬림핏", "straight", "slim fit",
            "crop", "미니", "라인", "v넥", "v-neck", "하이게이지",
            "실크", "캐시미어", "레더", "leather",
        ],
        "minus": ["oversize", "오버핏", "baggy", "루즈", "와이드", "빅사이즈"],
    },
    # STRAIGHT형 (스포티·근육형 I라인) — 깔끔한 저스트사이즈
    "athletic": {
        "plus": [
            "straight", "와이드", "오버핏", "boxy", "relaxed", "cargo", "utility",
            "터틀넥", "turtleneck", "v넥", "트렌치", "trench",
            "울", "wool", "캐시미어", "cashmere",
        ],
        "minus": ["skinny", "슬림핏", "타이트", "보디콘"],
    },
    # WAVE형 (글래머·X라인) — 하이웨이스트·부드러운 소재로 X라인 강조
    "curvy": {
        "plus": [
            "high-waist", "하이웨이스트", "랩", "wrap", "a-line", "플레어",
            "브이넥", "v-neck", "셔링", "리브", "rib", "플리츠", "pleats",
            "쉬폰", "chiffon", "모헤어", "벨벳", "velvet", "레이스", "lace",
            "쇼트기장", "short", "퍼코트", "fur",
        ],
        "minus": ["low-rise", "로우라이즈", "skinny", "보이핏", "oversize"],
    },
    # NATURAL형 (프레임바디·A/Y라인) — 볼륨 소재·와이드·롱기장으로 자연스러운 멋
    "standard": {
        "plus": [
            "와이드", "wide", "롱기장", "오버핏", "oversize", "터틀넥", "turtleneck",
            "마", "linen", "데님", "denim", "코듀로이", "corduroy",
            "와플", "waffle", "로게이지", "울", "wool", "a-line", "a라인",
            "루즈핏", "loose", "릴렉스", "relax",
        ],
        "minus": ["슬림핏", "skinny", "타이트", "타이트핏", "slim fit"],
    },
}

# 성별 추론용 토큰 (단어 경계 매칭 사용 → "mens" ⊂ "womens" 오분류 방지)
GENDER_WOMEN_TOKENS: list[str] = [
    "우먼", "women", "womens", "여성", "ladies", "womenswear",
]
GENDER_MEN_TOKENS: list[str] = [
    "맨즈", "mens", "남성", "menswear",
]


def _gender_contains(text: str, tokens: list[str]) -> bool:
    """단어 경계(\b)를 고려한 성별 토큰 매칭 — 부분 문자열 오매칭 방지"""
    for tok in tokens:
        if re.search(r"\b" + re.escape(_norm(tok)) + r"\b", text):
            return True
    return False


def _infer_gender(product: dict[str, Any]) -> str:
    """상품명+브랜드 텍스트에서 성별을 추론. 반환값: 'women' | 'men' | 'unisex'"""
    text = _norm(f"{product.get('name', '')} {product.get('brand', '')}")
    is_women = _gender_contains(text, GENDER_WOMEN_TOKENS)
    is_men   = _gender_contains(text, GENDER_MEN_TOKENS)
    if is_women and not is_men:
        return "women"
    if is_men and not is_women:
        return "men"
    return "unisex"


def _product_matches_gender(product: dict[str, Any], requested_gender: str) -> bool:
    """
    성별 필터 매칭.
    - 여성 선택 → women + unisex 상품 포함
    - 남성 선택 → men   + unisex 상품 포함
    - 젠더리스  → unisex 전용
    """
    if not requested_gender or requested_gender == "all":
        return True
    inferred = _infer_gender(product)
    if requested_gender == "unisex":
        return inferred == "unisex"
    if requested_gender == "women":
        return inferred in {"women", "unisex"}
    if requested_gender == "men":
        return inferred in {"men", "unisex"}
    return True


K_FASHION_KEYWORD_PROFILES: dict[str, dict[str, Any]] = {
    "꾸안꾸": {
        "tokens": [
            "데일리", "편안", "코튼", "니트", "가디건", "basic", "minimal",
            "casual", "simple", "cotton", "everyday", "일상", "심플",
            "무지", "plain", "standard", "스탠다드",
        ],
        "exclude_tokens": [
            "글리터", "glitter", "레이스", "lace", "leather", "레더",
            "프릴", "frill", "bodycon", "파티", "party", "시퀸", "sequin",
        ],
        "prefer_categories": {"top", "bottom", "outer"},
    },
    "꾸꾸꾸": {
        "tokens": [
            "트위드", "레이스", "새틴", "실크", "프릴", "glam", "party",
            "shiny", "satin", "silk", "sequin", "시퀸", "pearl",
            "글리터", "glitter", "크리스탈", "자수", "embroidery",
        ],
        "exclude_tokens": [
            "후드", "맨투맨", "hoodie", "sweatshirt", "cargo", "카고",
            "기본", "basic", "plain", "무지",
        ],
        "prefer_categories": {"top", "dress", "outer"},
    },
    "여자의악마": {
        "tokens": [
            "leather", "레더", "슬림핏", "slim fit", "타이트", "tight",
            "크롭", "crop", "short", "mini", "미니", "skinny", "스키니",
            "stretch", "스트레치", "body", "바디", "zip", "지퍼",
            "camisole", "캐미솔", "tank", "탱크", "sleeveless", "민소매",
            "cutout", "cut out", "off shoulder", "오프숄더",
            # 추가 섹시/바디컨셔스 토큰
            "코르셋", "corset", "bodysuit", "홀터", "halter",
            "섹시", "sexy", "핫팬츠", "hot pants", "short pants",
            "미니스커트", "mini skirt", "tube", "튜브",
        ],
        "exclude_tokens": [
            "후드", "맨투맨", "hoodie", "sweatshirt", "오버핏", "oversize",
            "baggy", "루즈", "오피스", "office", "formal", "정장",
            "카고", "cargo",
            # 추가 배제: 기모·트레이닝류는 확실히 제거
            "기모", "트레이닝", "training", "집업", "zip-up", "zipup",
            "플리스", "fleece", "와이드", "wide", "루즈핏", "loose fit",
        ],
        "exclude_weight": 12.0,   # H: 기본 7.0 → 12.0 (강한 배제)
        "match_weight":   7.0,    # H: 기본 5.0 → 7.0 (명확한 매치 강화)
        "sub_category_block": ["hoodie"],  # H: hoodie 카테고리 하드 블록
        "prefer_categories": {"top", "outer", "dress"},
    },
    "출근룩": {
        "tokens": [
            "블레이저", "자켓", "셔츠", "슬랙스", "오피스", "정장",
            "tailored", "classic", "blazer", "jacket", "slacks",
            "trousers", "oxford", "linen", "wool", "suit", "collar",
            "칼라", "button", "버튼", "polo", "니트", "knit",
            "비즈니스", "business", "office", "dress pants", "dress shirt",
            # "shirt" 제거 → sweatshirt 오매칭 방지
            "collar shirt", "button-down", "button down",
        ],
        "exclude_tokens": [
            "후드", "맨투맨", "hoodie", "sweatshirt", "카고", "cargo",
            "오버핏", "oversize", "그래픽", "graphic", "크롭", "crop",
            "스트리트", "street", "baggy",
            # 추가 배제: 기모·트레이닝·집업
            "기모", "트레이닝", "training", "집업", "zip-up", "zipup",
            "플리스", "fleece",
        ],
        "exclude_weight": 12.0,   # H: 기본 7.0 → 12.0 (강한 배제)
        "sub_category_block": ["hoodie"],  # H: hoodie 카테고리 하드 블록
        "prefer_categories": {"top", "bottom", "outer"},
    },
    "응답하라2000s": {
        "tokens": [
            "y2k", "레트로", "복고", "로우라이즈", "low-rise", "low rise",
            "cargo", "카고", "데님", "글리터", "glitter", "baby tee",
            "트랙", "2000", "metallic", "메탈릭", "나비", "butterfly",
            "mini", "미니", "크롭", "crop",
        ],
        "exclude_tokens": [
            "formal", "오피스", "tailored", "정장", "미니멀", "minimal",
            "business", "비즈니스",
        ],
        "prefer_categories": {"top", "bottom", "outer"},
    },
}


def _canonical_product_key(product: dict[str, Any]) -> str:
    """
    추천 단계에서 중복 제거를 위한 정규화 키.
    - 29cm: /catalog/{id}, /products/{id}를 동일 상품으로 취급
    - wconcept: /Product/{id} 기준
    """
    mall = _norm(str(product.get("mall", "")))
    src = str(product.get("source_url", "")).strip()

    if src:
        if mall == "29cm":
            m = re.search(r"/(?:catalog|products)/(\d+)", src)
            if m:
                return f"29cm:{m.group(1)}"
        elif mall == "wconcept":
            m = re.search(r"/Product/(\d+)", src, re.IGNORECASE)
            if m:
                return f"wconcept:{m.group(1)}"
        return f"url:{src}"

    pid = str(product.get("id", "")).strip()
    if pid:
        return f"id:{pid}"

    name = _norm(str(product.get("name", "")))
    price = int(product.get("price_krw", 0) or 0)
    return f"np:{mall}:{name}:{price}"


def _dedupe_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    동일 상품 중복 제거.
    같은 키가 여러 개면 상세이미지 수가 많은 항목을 우선 유지.
    """
    kept: dict[str, dict[str, Any]] = {}
    for p in products:
        key = _canonical_product_key(p)
        prev = kept.get(key)
        if not prev:
            kept[key] = p
            continue

        prev_n = len(prev.get("detail_images") or [])
        cur_n = len(p.get("detail_images") or [])
        if cur_n > prev_n:
            kept[key] = p
    return list(kept.values())


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _contains_any(text: str, tokens: list[str]) -> bool:
    return any(_norm(tok) in text for tok in tokens if tok)


def _product_text(product: dict[str, Any]) -> str:
    return " ".join(
        [
            _norm(product.get("name", "")),
            _norm(product.get("style", "")),
            _norm(product.get("keyword", "")),
            _norm(" ".join(product.get("tags", []))),
        ]
    )


def _canonical_color(raw: str) -> str:
    """프론트에서 오는 색상값을 정규화된 키로 변환"""
    return _COLOR_ALIAS_MAP.get(_norm(raw), _norm(raw))


def _product_matches_color(product: dict[str, Any], requested_color: str) -> bool:
    """
    상품이 요청된 색상에 해당하는지 확인.
    1차: products_enriched.json 의 colors 메타데이터 사용 (확실한 색상이 있으면 여기서 확정)
    2차: 색상 메타데이터가 없거나 multicolor일 때만 상품명 텍스트로 탐지
    """
    if not requested_color or requested_color == "":
        return True

    req_canon = _canonical_color(requested_color)
    allowed_colors = COLOR_FAMILIES.get(req_canon, {req_canon})

    # 1차: 메타데이터의 colors 리스트 (크롤러가 상품명에서 추출한 색상)
    meta_colors_raw = product.get("colors") or []
    meta_colors = {_canonical_color(c) for c in meta_colors_raw}

    # 확실한 색상 정보가 있으면 메타데이터만으로 판단 (텍스트 fallback 없음)
    # → "multicolor"만 있거나 비어있을 때만 텍스트 탐지로 보완
    definitive_colors = meta_colors - {"multicolor"}
    if definitive_colors:
        return bool(definitive_colors & allowed_colors)

    # 2차: 메타데이터에 확실한 색상이 없을 때만 상품명 텍스트 탐지
    text = _product_text(product)
    aliases: list[str] = []
    for color in allowed_colors:
        aliases.extend(COLOR_NORMALIZE.get(color, [color]))
    return _contains_any(text, aliases)


def _product_matches_category(product: dict[str, Any], requested_category: str) -> bool:
    if not requested_category or requested_category == "all":
        return True

    prod_cat = _norm(product.get("category", ""))
    req_cat = _norm(requested_category)

    if req_cat in FINE_CATEGORY_RULES:
        rule = FINE_CATEGORY_RULES[req_cat]
        base = _norm(rule.get("base", ""))
        # base 카테고리가 다르면 즉시 제외
        if prod_cat != base:
            return False
        # 1순위: 크롤러가 저장한 sub_category 필드 (정확)
        sub_cat = _norm(product.get("sub_category", ""))
        if sub_cat:
            return sub_cat == req_cat
        # 2순위: 상품명·태그 텍스트 키워드 매칭
        if _contains_any(_product_text(product), rule.get("keywords", [])):
            return True
        # 3순위: sub_category 데이터 없는 구 데이터는 base 카테고리 선택 시에만 포함
        # (세부 카테고리 선택 시엔 키워드 미매칭이면 제외 — 노이즈 방지)
        return False

    # "top" / "bottom" / "outer" / "dress" 선택 시
    # → 해당 base 카테고리 전체 + 세부 카테고리 상품 모두 포함
    allowed = CATEGORY_GROUPS.get(req_cat, {req_cat})
    if prod_cat in allowed:
        return True
    # sub_category 경로: category 필드가 비어 있을 때만 사용
    # (category가 명시된 상품은 그 값을 신뢰 → sub_category가 override하지 않도록)
    if not prod_cat:
        sub_cat = _norm(product.get("sub_category", ""))
        if sub_cat:
            sub_base = BASE_CATEGORY_FROM_FINE.get(sub_cat, "")
            return sub_base in allowed
    return False


def _style_bonus(product: dict[str, Any], requested_style: str) -> float:
    style_req = _norm(requested_style)
    if not style_req:
        return 0.0
    rule = STYLE_TOKEN_MAP.get(style_req)
    if not rule:
        return 0.0
    text = _product_text(product)
    score = 0.0
    if _contains_any(text, rule.get("plus", [])):
        score += 10.0   # B: 가중치 대폭 상향
    if _contains_any(text, rule.get("minus", [])):
        score -= 8.0    # A: 스타일 배제 토큰 매칭 시 강한 감점
    return score


def _body_type_bonus(product: dict[str, Any], body_type: str) -> float:
    body = _norm(body_type)
    # 체형 미선택("") → 보너스/감점 없음
    if not body:
        return 0.0

    rule = BODY_TYPE_TOKEN_MAP.get(body)
    if not rule:
        return 0.0

    text = _product_text(product)
    score = 0.0
    if _contains_any(text, rule.get("plus", [])):
        score += 3.0    # 체형 매칭 가점 상향
    if _contains_any(text, rule.get("minus", [])):
        score -= 1.5    # 체형 불일치 감점
    return score


# 체형 코드 → 한국어 레이블 맵
_BODY_TYPE_LABELS_MAP: dict[str, str] = {
    "slim":     "슬림형(STRAIGHT I라인)",
    "athletic": "스포티형(STRAIGHT 근육질)",
    "curvy":    "글래머형(WAVE X라인)",
    "standard": "내추럴형(NATURAL A/Y라인)",
}


def _best_body_type_label(product: dict[str, Any]) -> str:
    """제품 속성(소재·태그·카테고리) 기반으로 가장 어울리는 체형 레이블을 반환.
    모든 체형에 점수가 0이면 내추럴형을 기본값으로 반환."""
    scores = {bt: _body_type_bonus(product, bt) for bt in BODY_TYPE_TOKEN_MAP}
    best_key = max(scores, key=lambda k: scores[k])
    return _BODY_TYPE_LABELS_MAP.get(best_key, "내추럴형(NATURAL A/Y라인)")


def _keyword_bonus(product: dict[str, Any], keyword_csv: str) -> float:
    kws = [kw.strip() for kw in str(keyword_csv or "").split(",") if kw.strip()]
    if not kws:
        return 0.0

    text = _product_text(product)
    cat = _norm(product.get("category", ""))
    score = 0.0

    for kw in kws:
        profile = K_FASHION_KEYWORD_PROFILES.get(kw)
        if not profile:
            if _contains_any(text, [kw]):
                score += 2.0
            continue

        has_match   = _contains_any(text, profile.get("tokens", []))
        has_exclude = _contains_any(text, profile.get("exclude_tokens", []))

        match_weight   = float(profile.get("match_weight",   5.0))  # H: 프로파일별 가중치
        exclude_weight = float(profile.get("exclude_weight", 7.0))  # H: 프로파일별 배제 가중치

        if has_match:
            score += match_weight               # D/H: 키워드 매칭 가점 (프로파일별 조정)
        if has_exclude:
            score -= exclude_weight             # D/H: 명백 배제 토큰 → 강한 감점 (프로파일별)
        if not has_match and not has_exclude:
            score -= 1.5                        # D: 매칭도 배제도 아님 → 약한 감점

        if cat in profile.get("prefer_categories", set()):
            score += 0.8

    return score


def _brand_origin(product: dict[str, Any]) -> str:
    origin = _norm(product.get("brand_origin", ""))
    if origin in {"korean", "overseas", "unknown"}:
        return origin
    name = str(product.get("name", ""))
    brand = str(product.get("brand", "")) or extract_brand(name)
    return guess_brand_origin(name=name, brand=brand)


def _score_product(product: dict[str, Any], req: dict[str, Any]) -> float:
    """메타데이터 기반 점수 계산 (OpenAI 없이)"""
    score: float = 0.0

    # 가격 범위
    min_price = int(req.get("min_price_krw", 0) or 0)
    max_price = int(req.get("max_price_krw", 99999999) or 99999999)
    price = int(product.get("price_krw", 0) or 0)
    if min_price <= price <= max_price:
        score += 5.0

    # 색상 매치
    req_color = _norm(req.get("color", ""))
    if req_color and _product_matches_color(product, req_color):
        score += 8.0

    # 카테고리 매치
    req_cat = _norm(req.get("category", "all"))
    if req_cat and req_cat != "all" and _product_matches_category(product, req_cat):
        score += 7.0

    # 스타일/체형/한국 패션 키워드 반영
    style_score   = _style_bonus(product, req.get("style", ""))
    keyword_score = _keyword_bonus(product, req.get("keyword", ""))
    score += style_score
    score += _body_type_bonus(product, req.get("body_type", "standard"))
    score += keyword_score

    # G: 스타일 + 키워드 동시 선택됐는데 둘 다 미매칭이면 추가 감점
    req_style = _norm(req.get("style", ""))
    req_kw    = str(req.get("keyword", "") or "").strip()
    if req_style and req_kw:
        style_rule  = STYLE_TOKEN_MAP.get(req_style, {})
        kw_list     = [k.strip() for k in req_kw.split(",") if k.strip()]
        text        = _product_text(product)
        style_hit   = _contains_any(text, style_rule.get("plus", []))
        kw_hit      = any(
            _contains_any(text, K_FASHION_KEYWORD_PROFILES.get(kw, {}).get("tokens", []))
            for kw in kw_list if kw in K_FASHION_KEYWORD_PROFILES
        )
        if not style_hit and not kw_hit:
            score -= 5.0    # G: 둘 다 미매칭 시 추가 감점

    # H: 키워드별 sub_category 하드 블록 (예: 여자의악마 + hoodie → 즉시 강한 감점)
    prod_subcat = _norm(product.get("sub_category", ""))
    if prod_subcat and req_kw:
        block_penalty: float = 0.0
        for kw_h in [k.strip() for k in req_kw.split(",") if k.strip()]:
            kw_p    = K_FASHION_KEYWORD_PROFILES.get(kw_h, {})
            blocked = [_norm(c) for c in kw_p.get("sub_category_block", [])]
            if prod_subcat in blocked:
                block_penalty = block_penalty + 15.0  # H: sub_category 직접 블록
        score = score - block_penalty

    # 쇼핑몰 보너스
    if _norm(product.get("mall", "")) in {"wconcept", "29cm"}:
        score += 1.0

    # 한국 브랜드 우선 추천 (해외 브랜드는 상대적 감점)
    origin = _brand_origin(product)
    if origin == "korean":
        score += 3.0
    elif origin == "overseas":
        score -= 1.5

    return score


# ── OpenAI 클라이언트 (모듈 레벨 싱글턴) ────────────────────────────────
def _get_openai_client() -> OpenAI | None:
    """API 키가 있을 때만 OpenAI 클라이언트를 반환. 없으면 None."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


# ── OpenAI 호출 (AI 추천 이유 생성용) ─────────────────────────────────
def _openai_reason(
    items: list[dict[str, Any]],
    req: dict[str, Any],
    max_items: int = 40,
) -> dict[str, dict]:
    """
    OpenAI로 각 상품의 추천 이유(reason)와 relevance score만 받음.
    분류/필터링은 이미 메타데이터로 완료된 상태.
    """
    client = _get_openai_client()
    if not client:
        return {}

    subset: list[dict[str, Any]] = cast("list[dict[str, Any]]", items[:max_items])
    compact = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "brand": p.get("brand", ""),
            "category": p.get("category"),
            "sub_category": p.get("sub_category", ""),
            "colors": p.get("colors", []),
            "tags": p.get("tags", []),
            "material": p.get("material", ""),
            "price_krw": int(p.get("price_krw", 0) or 0),
        }
        for p in subset
    ]

    kw_raw = req.get("keyword", "") or ""
    keywords_list = [k.strip() for k in kw_raw.split(",") if k.strip()]

    # 체형 한국어 레이블
    body_type_label = {
        "slim": "슬림 체형",
        "athletic": "스포티/근육형 체형",
        "curvy": "글래머/곡선 체형",
        "standard": "표준 체형",
    }.get(req.get("body_type", "standard") or "standard", "표준 체형")

    style_label = {
        "minimal": "미니멀",
        "street": "스트리트",
        "vintage": "빈티지",
        "casual": "캐주얼",
        "formal": "포멀",
        "y2k": "Y2K",
        "romantic": "로맨틱",
        "preppy": "프레피",
    }.get(req.get("style", "") or "", "")

    system = (
        "당신은 10년 경력의 한국 패션 스타일리스트입니다. "
        "사전 필터링된 K-패션 의류 아이템과 사용자 선호 정보를 바탕으로, "
        "각 아이템에 대해 개인화된 스타일링 조언을 제공합니다.\n\n"
        "추천 이유(reason) 작성 규칙:\n"
        "1. 반드시 한국어로 작성하세요.\n"
        "2. 사용자의 체형 또는 선택 스타일과 연결되는 핵심 포인트 하나만 언급하세요.\n"
        "3. 반드시 1문장으로만 작성하세요. 마침표는 딱 1개.\n"
        "4. 자연스럽고 간결한 어조로 쓰세요. "
        "예: '루즈한 실루엣이 꾸안꾸 스타일에 딱 맞아요.' / "
        "'슬림핏이 체형 라인을 깔끔하게 잡아줍니다.'\n"
        "5. 브랜드명을 직접 언급하지 마세요.\n"
        "6. 30~50자 사이로 유지하세요.\n\n"
        "keyword_score: 사용자가 선택한 한국 패션 키워드(꾸안꾸/꾸꾸꾸/여자의악마/출근룩/응답하라2000s)와 "
        "아이템의 일치도를 0-100으로 평가하세요. 키워드 미선택 시 50.\n"
        "Return strict JSON only."
    )
    user_payload = {
        "user_preferences": {
            "body_type": body_type_label,
            "color": req.get("color", ""),
            "style": style_label,
            "keywords": keywords_list,
            "category": req.get("category", "all"),
        },
        "items": compact,
        "output_schema": {
            "items": [
                {
                    "id": "string",
                    "score": "0-100",
                    "reason": (
                        "체형·스타일·키워드를 반영한 개인화 스타일링 조언 "
                        "(체형/스타일 적합 이유 포함). 30~50자, 1문장, 한국어"
                    ),
                    "keyword_score": "0-100 (한국 패션 키워드 일치도. 키워드 없으면 50)"
                }
            ]
        },
    }

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            timeout=60,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        result_map: dict[str, dict] = {}
        for r in parsed.get("items", []):
            pid = str(r.get("id", ""))
            result_map[pid] = {
                "ai_score":  float(r.get("score", 50) or 50),
                "ai_reason": str(r.get("reason", "")).strip(),
                "keyword_score": float(r.get("keyword_score", 50) or 50),
            }
        return result_map
    except Exception:
        return {}


def _openai_select_complement(
    current_item: dict[str, Any],
    candidates: list[dict[str, Any]],
    n: int = 2,
) -> list[dict[str, Any]]:
    """
    현재 아이템과 가장 잘 어울리는 complement 아이템을 OpenAI로 선별.
    candidates 리스트(이미 셔플된 40개 이하)에서 n개를 골라 반환.
    """
    client = _get_openai_client()
    if not client or not candidates:
        return cast("list[dict[str, Any]]", candidates[:n])
    assert client is not None

    compact_current = {
        "name": current_item.get("name", ""),
        "category": current_item.get("category", ""),
        "sub_category": current_item.get("sub_category", ""),
        "colors": current_item.get("colors", []),
        "tags": current_item.get("tags", []),
        "material": current_item.get("material", ""),
    }
    compact_candidates = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "category": p.get("category"),
            "sub_category": p.get("sub_category", ""),
            "colors": p.get("colors", []),
            "tags": p.get("tags", []),
            "material": p.get("material", ""),
            "price_krw": int(p.get("price_krw", 0) or 0),
        }
        for p in candidates
    ]

    system = (
        "당신은 10년 경력의 한국 패션 스타일리스트입니다. "
        "주어진 메인 아이템과 가장 잘 어울리는 코디 아이템을 candidates 목록에서 골라주세요.\n\n"
        "선별 기준:\n"
        "1. 색상 조화 (보색, 유사색, 모노톤 등)\n"
        "2. 스타일 통일성 (캐주얼+캐주얼, 포멀+포멀, 스트리트+스트리트 등)\n"
        "3. 소재 밸런스 (두꺼운 상의 + 얇은 하의 등 레이어링 고려)\n"
        "4. 실제 한국 길거리 패션에서 보이는 자연스러운 코디 조합\n\n"
        "Return strict JSON only."
    )
    user_payload = {
        "main_item": compact_current,
        "candidates": compact_candidates,
        "select_n": n,
        "output_schema": {
            "selected": [
                {
                    "id": "candidates에서 선택한 id (string)",
                    "match_reason": "이 조합이 어울리는 이유 1문장 (한국어, 30~50자)"
                }
            ]
        },
    }

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            timeout=30,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        id_to_item   = {str(p.get("id")): p for p in candidates}
        id_to_reason = {str(s.get("id", "")): s.get("match_reason", "") for s in parsed.get("selected", [])}
        result = []
        for sid in [str(s.get("id", "")) for s in parsed.get("selected", [])]:
            if sid in id_to_item:
                item = dict(id_to_item[sid])
                item["match_reason"] = id_to_reason.get(sid, "")
                result.append(item)
        return result if result else cast("list[dict[str, Any]]", candidates[:n])
    except Exception:
        return cast("list[dict[str, Any]]", candidates[:n])


# ── 메인 큐레이션 함수 ─────────────────────────────────────────────────
def curate_with_openai(
    products: list[dict[str, Any]],
    req: dict[str, Any],
    page: int = 0,
    page_size: int = 20,
) -> dict[str, Any]:
    """
    1. 메타데이터(is_clothing, color, category, price)로 필터링
    2. 로컬 점수 계산 후 점수 내림차순 정렬
    3. 현재 page에 해당하는 page_size개만 슬라이스
    4. OpenAI로 추천 이유 생성 (해당 페이지 아이템에만, 실패 시 무시)
    5. {"items": [...], "total": int} 반환
    """
    min_price  = int(req.get("min_price_krw", 0) or 0)
    max_price  = int(req.get("max_price_krw", 99999999) or 99999999)
    req_color  = _norm(req.get("color", ""))
    req_cat    = _norm(req.get("category", "all"))
    req_gender = _norm(req.get("gender", "all"))

    # 저장 캐시에 이미 중복이 있더라도 응답에서는 즉시 제거
    products = _dedupe_products(products)

    # ── Step 1: 필터링 ─────────────────────────────────────────────
    filtered: list[dict[str, Any]] = []
    for p in products:
        if "is_fashion" in p:
            if not bool(p.get("is_fashion")):
                continue
        elif not p.get("is_clothing", True):
            continue
        price = int(p.get("price_krw", 0) or 0)
        if not (min_price <= price <= max_price):
            continue
        if req_cat != "all" and not _product_matches_category(p, req_cat):
            continue
        if req_color and not _product_matches_color(p, req_color):
            continue
        if req_gender != "all" and not _product_matches_gender(p, req_gender):
            continue
        filtered.append(p)

    if not filtered:
        return {"items": [], "total": 0}

    # ── Step 2: 로컬 점수 계산 + 정렬 ──────────────────────────────
    scored = [(p, _score_product(p, req)) for p in filtered]
    scored.sort(key=lambda x: x[1], reverse=True)
    total = len(scored)

    # ── Step 3: 현재 페이지 슬라이스 (서버 사이드 페이지네이션) ──────
    start = page * page_size
    end   = start + page_size
    scored_page: list[tuple[dict[str, Any], float]] = cast(
        "list[tuple[dict[str, Any], float]]", scored[start:end]
    )
    page_items = [p for p, _ in scored_page]

    # ── Step 4: OpenAI 추천 이유 (현재 페이지 아이템에만) ───────────
    reason_map = _openai_reason(page_items, req, max_items=page_size)

    enriched: list[dict[str, Any]] = []
    for p in page_items:
        out = dict(p)
        pid = str(p.get("id", ""))
        ai_info     = reason_map.get(pid, {})
        meta_score  = _score_product(p, req)
        ai_score    = float(ai_info.get("ai_score", meta_score * 5) or meta_score * 5)
        kw_raw      = req.get("keyword", "") or ""
        has_kw      = bool(kw_raw.strip())
        ai_kw_score = float(ai_info.get("keyword_score", 50) or 50)
        kw_ai_bonus = (ai_kw_score / 100.0) * 8.0 if has_kw else 0.0
        out["ai_score"]    = meta_score * 3 + ai_score * 0.5 + kw_ai_bonus
        out["ai_reason"]   = ai_info.get("ai_reason", "")
        out["ai_category"] = p.get("category", "other_clothing")
        enriched.append(out)

    return {"items": enriched, "total": total}


# ── 하위 호환: 기존 curate 함수 ───────────────────────────────────────
def curate(
    products: list[dict[str, Any]],
    req: dict[str, Any],
    page: int = 0,
    page_size: int = 20,
) -> dict[str, Any]:
    return curate_with_openai(products, req, page=page, page_size=page_size)
