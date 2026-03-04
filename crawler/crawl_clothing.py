#!/usr/bin/env python3
"""
무신사 전용 Playwright 크롤러 (API 기반)

변경 사항:
  - 무신사 공개 API(api.musinsa.com/api2/dp/v2/plp/goods)로 상품 목록 수집
    → 다양한 브랜드, 정확한 가격, 메인 썸네일 URL 직접 획득
    → nextPageUrl 페이지네이션으로 수백~수천 개 수집 가능
  - 상품 상세 페이지는 detail 이미지 + 소재/세탁법만 크롤
  - msscdn.net CDN + 상품ID 필터로 브랜드 설명 이미지 완전 차단
  - 남성/여성/전체 구분 가능 (--gender 옵션)
  - --output 옵션으로 팀원별 별도 파일 저장 지원

카테고리 코드 (무신사 기준):
  상의: 001001=반소매T, 001002=셔츠/블라우스, 001004=후드T, 001005=맨투맨, 001006=니트, 001010=긴소매T
  하의: 003001=데님, 003002=슬랙스, 022=스커트
  아우터: 002001=코트, 002002=재킷, 002003=패딩
  원피스/드레스: 020=원피스, 020002=점프수트

사용법:
  # [팀원 A] 상의 여성 200개
  .venv/bin/python scripts/crawl_clothing.py --category top --gender F --per-category 200 --output crawl_A.json

  # [팀원 B] 상의 남성 200개
  .venv/bin/python scripts/crawl_clothing.py --category top --gender M --per-category 200 --output crawl_B.json

  # [팀원 C] 하의 전체 200개
  .venv/bin/python scripts/crawl_clothing.py --category bottom --gender A --per-category 200 --output crawl_C.json

  # [팀원 D] 아우터 전체 200개
  .venv/bin/python scripts/crawl_clothing.py --category outer --gender A --per-category 200 --output crawl_D.json

  # [팀원 E] 원피스 여성 200개
  .venv/bin/python scripts/crawl_clothing.py --category dress --gender F --per-category 200 --output crawl_E.json

  # 결합 (모든 crawl_*.json → products_enriched.json)
  .venv/bin/python scripts/merge_crawl.py

  # 디버깅 (브라우저 창 표시)
  .venv/bin/python scripts/crawl_clothing.py --no-headless --verbose
"""

from __future__ import annotations

import sys
import argparse
import asyncio
import io
import json
import re
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[0]
DATA_DIR = CRAWLER_ROOT / "data"
IMG_ROOT = CRAWLER_ROOT / "images"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import requests

try:
    from PIL import Image
except ImportError:
    print("ERROR: pip install Pillow  를 먼저 실행하세요.")
    sys.exit(1)

try:
    from playwright.async_api import async_playwright, Page, BrowserContext
except ImportError:
    print("ERROR: pip install playwright && playwright install chromium  를 먼저 실행하세요.")
    sys.exit(1)

ENRICHED = DATA_DIR / "products_enriched.json"

# ── 이미지 품질 기준 ────────────────────────────────────────────────────
IMG_MIN_W   = 300
IMG_MIN_H   = 300
IMG_MIN_KB  = 8
IMG_MAX_R   = 1.8   # w/h 비율 초과 = 가로 배너
IMG_MIN_R   = 0.35  # w/h 비율 미만 = 비정상

# ── 무신사 API ──────────────────────────────────────────────────────────
MUSINSA_API = "https://api.musinsa.com/api2/dp/v2/plp/goods"

# 카테고리별 무신사 API 코드 (다양한 서브카테고리 포함)
# gf: A=전체, M=남성, F=여성
CATEGORY_API_CODES: dict[str, list[str]] = {
    "top": [
        "001001",  # 반소매 티셔츠
        "001010",  # 긴소매 티셔츠
        "001005",  # 맨투맨/스웨트
        "001004",  # 후드 티셔츠
        "001006",  # 니트/스웨터
        "001002",  # 셔츠/블라우스
    ],
    "bottom": [
        "003001",  # 데님/청바지
        "003002",  # 슬랙스/팬츠
        "003003",  # 조거/카고
        "022",     # 스커트 (여성)
    ],
    "outer": [
        "002001",  # 코트
        "002002",  # 재킷/블레이저
        "002003",  # 패딩/점퍼
    ],
    "dress": [
        "020",     # 원피스 전체
        "020002",  # 점프수트
    ],
}

# ── 이미지 CDN 필터 (무신사 전용) ──────────────────────────────────────
# msscdn.net + 경로에 상품ID 포함된 이미지만 허용
# goods_img = 메인 갤러리, prd_img = 공식 상세 이미지
MUSINSA_CDN = {
    "domain":       "image.msscdn.net",
    "path_include": ["/goods_img/", "/prd_img/"],
}

# ── 세부 카테고리 키워드 매핑 ────────────────────────────────────────────
SUBCATEGORY_MAP: list[tuple[str, list[str]]] = [
    ("tshirt",  ["티셔츠", "t-shirt", "tshirt", "tee", "반팔", "긴팔티", "롱슬리브"]),
    ("shirt",   ["셔츠", "블라우스", "shirt", "blouse"]),
    ("knit",    ["니트", "가디건", "스웨터", "knit", "sweater", "cardigan", "knitwear"]),
    ("hoodie",  ["후드", "맨투맨", "hoodie", "sweatshirt", "zip-up", "집업"]),
    ("pants",   ["팬츠", "슬랙스", "바지", "pants", "trousers", "slacks", "jogger", "cargo"]),
    ("skirt",   ["스커트", "치마", "skirt"]),
    ("denim",   ["청바지", "데님", "denim", "jeans"]),
    ("jacket",  ["자켓", "재킷", "블루종", "점퍼", "블레이저", "jacket", "blouson", "jumper", "blazer"]),
    ("coat",    ["코트", "트렌치", "패딩", "coat", "trench", "parka"]),
    ("dress",   ["원피스", "dress", "one-piece"]),
    ("suit",    ["수트", "점프수트", "suit", "jumpsuit", "셋업"]),
]

BASE_CATEGORY_MAP: dict[str, str] = {
    "tshirt": "top",  "shirt": "top",   "knit": "top",  "hoodie": "top",
    "pants":  "bottom", "skirt": "bottom", "denim": "bottom",
    "jacket": "outer",  "coat": "outer",
    "dress":  "dress",  "suit": "dress",
}

COLOR_KEYWORDS: dict[str, list[str]] = {
    "black":      ["black", "blk", "noir", "블랙"],
    "white":      ["white", "blanc", "화이트"],
    "ivory":      ["ivory", "cream", "off-white", "아이보리", "크림"],
    "beige":      ["beige", "sand", "nude", "베이지"],
    "gray":       ["grey", "gray", "silver", "charcoal", "그레이", "차콜"],
    "brown":      ["brown", "mocha", "브라운"],
    "camel":      ["camel", "caramel", "tan", "카멜"],
    "navy":       ["navy", "marine", "네이비"],
    "cobalt":     ["cobalt", "royal blue", "blue", "코발트"],
    "skyblue":    ["sky blue", "light blue", "baby blue", "스카이블루"],
    "olive":      ["olive", "khaki", "army", "올리브", "카키"],
    "deepgreen":  ["deep green", "forest", "emerald", "green", "딥그린"],
    "mint":       ["mint", "sage", "민트"],
    "lavender":   ["lavender", "lilac", "라벤더"],
    "pink":       ["pink", "blush", "핑크"],
    "red":        ["red", "scarlet", "레드"],
    "burgundy":   ["burgundy", "bordeaux", "maroon", "버건디"],
    "wine":       ["wine", "merlot", "와인"],
    "yellow":     ["yellow", "mustard", "옐로우", "머스타드"],
    "orange":     ["orange", "rust", "오렌지"],
    "multicolor": ["multi", "stripe", "check", "pattern", "print", "멀티", "스트라이프", "체크"],
    "purple":     ["purple", "violet", "퍼플"],
}


# ─────────────────────────────────────────────────────────────────────────
# 이미지 다운로드 + 품질 검사
# ─────────────────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://www.musinsa.com/",
    })
    return s


def _is_valid_image(data: bytes) -> bool:
    size_kb = len(data) / 1024
    if size_kb < IMG_MIN_KB:
        return False
    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w < IMG_MIN_W or h < IMG_MIN_H:
            return False
        ratio = w / h
        if ratio > IMG_MAX_R or ratio < IMG_MIN_R:
            return False
        return True
    except Exception:
        return False


def _download_image(url: str, dest: Path, session: requests.Session) -> str:
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        if not _is_valid_image(r.content):
            return ""
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return "/" + dest.relative_to(ROOT).as_posix()
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────
# 텍스트 분석 헬퍼
# ─────────────────────────────────────────────────────────────────────────

def _detect_subcategory(text: str) -> str:
    low = text.lower()
    for sub_cat, keywords in SUBCATEGORY_MAP:
        if any(kw.lower() in low for kw in keywords):
            return sub_cat
    return ""


def _detect_colors(text: str) -> list[str]:
    low = text.lower()
    found: list[str] = []
    for color, aliases in COLOR_KEYWORDS.items():
        if any(a.lower() in low for a in aliases):
            found.append(color)
    return found if found else ["multicolor"]


# ─────────────────────────────────────────────────────────────────────────
# 무신사 API 기반 상품 목록 수집
# ─────────────────────────────────────────────────────────────────────────

def _thumbnail_to_big(url: str) -> str:
    """API 썸네일 URL(_500.jpg / _500.png)을 고해상도로 변환.
    확장자를 유지한다 (PNG → _big.png, JPG → _big.jpg).
    """
    def _keep_ext(m: re.Match) -> str:
        ext = m.group(1).lower()
        return f"_big.{ext}"
    return re.sub(r'_\d+\.(jpg|jpeg|png|webp)$', _keep_ext, url, flags=re.I)


async def _collect_via_api(
    context: BrowserContext,
    category_code: str,
    gender: str,
    max_products: int,
    sort_code: str = "POPULAR",
    verbose: bool = False,
) -> list[dict]:
    """무신사 API로 상품 목록 수집.

    전략:
    1. 카테고리 페이지 로드 → 첫 API 응답 intercept
    2. 이후 nextPageUrl을 fetch()로 호출하여 페이지네이션
    """
    collected: list[dict] = []
    first_response: dict = {}

    # ── Step 1: 카테고리 페이지 로드 + 첫 응답 intercept ─────────────────
    # gf 파라미터: A=전체, M=남성, F=여성 → 성별 필터 적용
    seed_url = f"https://www.musinsa.com/categories/item/{category_code}?gf={gender}"
    page = await context.new_page()

    async def intercept(r):
        nonlocal first_response
        if (
            "dp/v2/plp/goods" in r.url
            and f"category={category_code}" in r.url
            and not first_response
        ):
            try:
                first_response = await r.json()
            except Exception:
                pass

    page.on("response", intercept)

    try:
        await page.goto(seed_url, wait_until="networkidle", timeout=25_000)
        await page.wait_for_timeout(2_000)
    except Exception as e:
        if verbose:
            print(f"    [카테고리 페이지 오류] {seed_url}: {e}")

    if not first_response or not first_response.get("data"):
        await page.close()
        return []

    def _parse_items(data: dict) -> list[dict]:
        result = []
        for item in data["data"].get("list", []):
            pid   = str(item["goodsNo"])
            thumb = item.get("thumbnail", "")
            price = item.get("price") or item.get("normalPrice") or 0
            result.append({
                "product_id":    pid,
                "url":           item["goodsLinkUrl"],
                "name":          item["goodsName"],
                "price_krw":     int(price),
                "brand":         item.get("brandName", ""),
                "thumbnail_url": _thumbnail_to_big(thumb) if thumb else "",
            })
        return result

    collected.extend(_parse_items(first_response))

    # ── Step 2: nextPageUrl로 페이지네이션 ───────────────────────────────
    pagination   = first_response["data"].get("pagination", {})
    next_page_url: str = pagination.get("nextPageUrl", "")

    while len(collected) < max_products and next_page_url:
        try:
            result = await page.evaluate(
                """async (url) => {
                    const r = await fetch(url, {
                        headers: {
                            "Accept": "application/json",
                            "Referer": "https://www.musinsa.com/"
                        }
                    });
                    if (!r.ok) return null;
                    return await r.json();
                }""",
                next_page_url,
            )
        except Exception as e:
            if verbose:
                print(f"    [페이지네이션 오류] {e}")
            break

        if not result or not result.get("data"):
            break

        collected.extend(_parse_items(result))

        pg = result["data"].get("pagination", {})
        if not pg.get("hasNext"):
            break
        next_page_url = pg.get("nextPageUrl", "")
        await asyncio.sleep(0.4)

    await page.close()
    return collected[:max_products]


# ─────────────────────────────────────────────────────────────────────────
# 상품 상세 페이지 크롤 (detail 이미지 + 소재/세탁법)
# ─────────────────────────────────────────────────────────────────────────

def _filter_musinsa_detail_imgs(urls: list[str], product_id: str) -> list[str]:
    """msscdn.net CDN + prd_img 경로 + 상품ID 포함된 상세 이미지만 반환."""
    result = []
    for u in urls:
        if MUSINSA_CDN["domain"] not in u:
            continue
        if "/prd_img/" not in u:
            continue
        if product_id not in u:
            continue
        result.append(u)
    return result


async def _extract_material_care(page: Page) -> tuple[str, str]:
    material_kws = ["소재", "material", "fabric", "원단", "성분"]
    care_kws     = ["세탁", "care", "세탁방법", "취급", "드라이"]

    text = await page.evaluate("() => document.body.innerText") or ""
    lines = [ln.strip() for ln in text.splitlines() if 5 < len(ln.strip()) < 200]

    material_lines: list[str] = []
    care_lines:     list[str] = []

    for ln in lines:
        low = ln.lower()
        if any(k in low for k in material_kws) and len(material_lines) < 3:
            material_lines.append(ln)
        elif any(k in low for k in care_kws) and len(care_lines) < 3:
            care_lines.append(ln)

    return " / ".join(material_lines), " / ".join(care_lines)


async def crawl_detail(
    page: Page,
    prefetch: dict,
    session: requests.Session,
    verbose: bool,
) -> dict[str, Any] | None:
    """
    상세 페이지 크롤 (detail 이미지 + 소재/세탁법만 보완).
    이름·가격·메인이미지는 API prefetch 데이터 사용.
    """
    url        = prefetch["url"]
    product_id = prefetch["product_id"]
    name       = prefetch["name"]
    price_krw  = prefetch["price_krw"]
    brand      = prefetch["brand"]
    thumb_url  = prefetch["thumbnail_url"]

    # ── 상세 페이지 로드 ─────────────────────────────────────────────────
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(1_500)
        # 스크롤로 lazy-load 트리거
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, 600)")
            await page.wait_for_timeout(400)
    except Exception as e:
        if verbose:
            print(f"    [페이지 오류] {url}: {e}")
        return None

    # ── 소재·세탁법 ──────────────────────────────────────────────────────
    material, care = await _extract_material_care(page)

    # ── breadcrumb + sub_category ────────────────────────────────────────
    try:
        bread_el = await page.query_selector(
            "nav[aria-label*='breadcrumb'], .breadcrumb, [class*='breadcrumb']"
        )
        breadcrumb = (await bread_el.inner_text()).strip() if bread_el else ""
    except Exception:
        breadcrumb = ""

    sub_category = _detect_subcategory(f"{breadcrumb} {name}")
    colors       = _detect_colors(name)
    base_cat_raw = prefetch.get("base_category", "top")
    final_base   = BASE_CATEGORY_MAP.get(sub_category, base_cat_raw)

    # ── 이미지 수집 (msscdn.net + prd_img + 상품ID 필터) ─────────────────
    img_srcs: list[str] = await page.evaluate("""() => {
        const skip = ['sprite', 'icon', 'logo', 'favicon'];
        const out = [];
        document.querySelectorAll('img').forEach(img => {
            const src = img.currentSrc || img.src || '';
            if (!src || src.startsWith('data:')) return;
            const low = src.toLowerCase();
            if (skip.some(s => low.includes(s))) return;
            out.push(src.split('?')[0]);
        });
        return [...new Set(out)];
    }""")

    detail_raw = _filter_musinsa_detail_imgs(img_srcs, product_id)

    # ── 이미지 다운로드 ───────────────────────────────────────────────────
    item_id  = f"musinsa_{product_id}"
    out_dir  = IMG_ROOT / "musinsa"

    # 메인 이미지 (API 썸네일 → _big.jpg)
    main_local = ""
    if thumb_url:
        main_dest  = out_dir / f"{item_id}_main.jpg"
        main_local = _download_image(thumb_url, main_dest, session)

    # 상세 이미지 (prd_img/detail_)
    detail_locals: list[str] = []
    for idx, img_url in enumerate(detail_raw):
        dest  = out_dir / f"{item_id}_detail_{idx + 1}.jpg"
        local = _download_image(img_url, dest, session)
        if local:
            detail_locals.append(local)
        if len(detail_locals) >= 8:
            break

    if not main_local:
        if verbose:
            print(f"    [메인이미지 없음] {url}")
        return None

    if verbose:
        print(f"    OK {item_id} | {brand} | {sub_category or final_base} | 상세{len(detail_locals)}장 | ₩{price_krw:,}")

    return {
        "id":            item_id,
        "mall":          "musinsa",
        "brand":         brand,
        "name":          name,
        "price_krw":     price_krw,
        "main_image":    main_local,
        "detail_images": detail_locals,
        "material":      material,
        "care":          care,
        "source_url":    url,
        "category":      final_base,
        "sub_category":  sub_category,
        "colors":        colors,
        "is_fashion":    True,
        "is_clothing":   final_base in {"top", "bottom", "outer", "dress"},
        "style":         "",
        "keyword":       "",
        "tags":          [],
    }


# ─────────────────────────────────────────────────────────────────────────
# 메인 크롤 루프
# ─────────────────────────────────────────────────────────────────────────

async def run_crawl(
    categories: list[str],
    per_category: int,
    gender: str,
    sort_code: str,
    headless: bool,
    verbose: bool,
    delay: float,
    output: Path | None = None,
) -> None:
    # --output 지정 시 해당 파일, 미지정 시 기본 products_enriched.json
    out_path = output if output is not None else ENRICHED

    existing_products: list[dict] = []
    if out_path.exists():
        try:
            existing_products = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing_urls: set[str] = {p.get("source_url", "") for p in existing_products}
    new_products:  list[dict] = []

    gender_label = {"A": "전체", "M": "남성", "F": "여성"}.get(gender, gender)
    print(f"\n[시작] 저장 파일: {out_path.name}")
    print(f"  기존 {len(existing_products)}개 | 카테고리: {categories} | {gender_label} | 정렬: {sort_code}")
    print(f"  카테고리당 최대: {per_category}개\n")

    session = _make_session()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context: BrowserContext = await browser.new_context(
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )

        for cat in categories:
            api_codes = CATEGORY_API_CODES.get(cat, [])
            if not api_codes:
                print(f"[{cat}] 코드 없음, 건너뜀")
                continue

            print(f"[{cat}] 시작 (API 코드: {api_codes})")

            # 각 서브카테고리 API 코드에서 상품 수집
            cat_prefetches: list[dict] = []
            per_code = max(15, per_category // len(api_codes) + 15)  # 여유 있게

            for code in api_codes:
                fetched = await _collect_via_api(
                    context, code, gender, per_code, sort_code, verbose
                )
                for item in fetched:
                    item["base_category"] = cat
                cat_prefetches.extend(fetched)
                print(f"  [{code}] API 수집: {len(fetched)}개")

            # 중복 제거 (URL 기준)
            seen_urls: set[str] = set(existing_urls)
            new_prefetches: list[dict] = []
            for pf in cat_prefetches:
                if pf["url"] not in seen_urls:
                    seen_urls.add(pf["url"])
                    new_prefetches.append(pf)

            print(f"  [{cat}] 신규: {len(new_prefetches)}개 → 최대 {per_category}개 크롤")

            # 상세 페이지 크롤
            crawled = 0
            detail_page = await context.new_page()

            for pf in new_prefetches[:per_category]:
                if not verbose:
                    print(f"  [{crawled+1}/{min(per_category, len(new_prefetches))}] {pf['brand']} - {pf['name'][:35]}")
                else:
                    print(f"  → {pf['url']}")

                item = await crawl_detail(detail_page, pf, session, verbose)
                if item:
                    new_products.append(item)
                    existing_urls.add(pf["url"])
                    crawled += 1

                    if len(new_products) % 10 == 0:
                        _save_merged(existing_products, new_products, out_path)
                        print(f"  [중간저장] 신규 {len(new_products)}개 → {out_path.name}")

                await asyncio.sleep(delay)

            await detail_page.close()
            print(f"[{cat}] 완료: {crawled}개 수집\n")

        await browser.close()

    _save_merged(existing_products, new_products, out_path)
    total = len(existing_products) + len(new_products)
    print(f"\n[완료] 신규 {len(new_products)}개 추가 → 총 {total}개")
    print(f"저장: {out_path}")

    # 이미지 필터 자동 실행
    print("\n[자동] 이미지 필터링...")
    _run_image_filter()


def _save_merged(existing: list[dict], new_items: list[dict], out_path: Path | None = None) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = out_path if out_path is not None else ENRICHED
    try:
        from shared.fx_converter import krw_to_jpy
        for item in new_items:
            if not item.get("price_jpy") and item.get("price_krw"):
                item["price_jpy"] = krw_to_jpy(int(item["price_krw"]))
    except Exception:
        for item in new_items:
            if not item.get("price_jpy") and item.get("price_krw"):
                item["price_jpy"] = round(int(item["price_krw"]) * 0.11)

    merged = existing + new_items
    dest.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _run_image_filter() -> None:
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "filter_detail_images",
            CRAWLER_ROOT / "filter_detail_images.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        mod.filter_enriched()
    except Exception as e:
        print(f"  [이미지 필터 오류] {e}")


# ─────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMG_ROOT.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(
        description="무신사 API 기반 의류 크롤러 (다양한 브랜드 수집)"
    )
    parser.add_argument(
        "--category", choices=["top", "bottom", "outer", "dress"], default=None,
        help="특정 카테고리만 크롤 (기본: 전체 top+bottom+outer+dress)"
    )
    parser.add_argument(
        "--per-category", type=int, default=40,
        help="카테고리당 최대 수집 수 (기본: 40)"
    )
    parser.add_argument(
        "--gender", choices=["A", "M", "F"], default="A",
        help="A=전체, M=남성, F=여성 (기본: A)"
    )
    parser.add_argument(
        "--sort", choices=["POPULAR", "DATE", "REVIEW", "LOW_PRICE"], default="POPULAR",
        help="정렬 기준: POPULAR=인기순, DATE=최신순 (기본: POPULAR)"
    )
    parser.add_argument(
        "--no-headless", action="store_true",
        help="브라우저 창 표시 (디버깅용)"
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="상품 간 대기 시간(초) (기본: 1.0)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="상세 로그 출력"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="FILE",
        help=(
            "결과 저장 파일명 (data/ 폴더에 저장). 예: crawl_A.json\n"
            "미지정 시 기본값: data/products_enriched.json\n"
            "팀원별 분리 저장 후 merge_crawl.py로 결합하세요."
        ),
    )
    args = parser.parse_args()

    cats = [args.category] if args.category else ["top", "bottom", "outer", "dress"]

    # --output 처리: 파일명만 주면 data/ 아래에 저장
    out_path: Path | None = None
    if args.output:
        name = args.output if args.output.endswith(".json") else args.output + ".json"
        out_path = DATA_DIR / name

    asyncio.run(run_crawl(
        categories=cats,
        per_category=args.per_category,
        gender=args.gender,
        sort_code=args.sort,
        headless=not args.no_headless,
        verbose=args.verbose,
        delay=args.delay,
        output=out_path,
    ))


if __name__ == "__main__":
    main()
