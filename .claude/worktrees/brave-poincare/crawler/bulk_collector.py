"""
bulk_collector.py — wconcept / 29cm 대량 수집기 (Playwright 없이 직접 API 호출)

wconcept : BEST API 직접 호출 — category × page 순차 pagination
           확인된 endpoint:
           https://display.wconcept.co.kr/display/api/best/v1/product
           ?displayCategoryType=10201&gnbType=Y&page=0&size=100

29cm     : 카테고리 API 직접 호출 (실험적)
           endpoint를 모르면 --sniff 옵션으로 Playwright 1회 실행 → 자동 저장
           이후 실행부터는 저장된 endpoint 재사용

실행 예시:
  # wconcept 3000개 수집 (4카테고리 균등)
  python bulk_collector.py --mall wconcept --limit 3000

  # 29cm endpoint 자동 탐지 후 저장
  python bulk_collector.py --sniff 29cm

  # 29cm 3000개 수집
  python bulk_collector.py --mall 29cm --limit 3000

  # 두 사이트 동시 (각각 limit개)
  python bulk_collector.py --mall all --limit 3000

  # 수집 후 enrichment 생략
  python bulk_collector.py --mall wconcept --limit 1000 --no-enrich
"""
from __future__ import annotations

import sys
import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import AsyncIterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[0]
DATA_DIR = CRAWLER_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if str(CRAWLER_ROOT) not in sys.path:
    sys.path.append(str(CRAWLER_ROOT))

ENDPOINT_CACHE = DATA_DIR / "bulk_endpoints.json"

# ────────────────────────────────────────────────────────────────
#   wconcept  카테고리 정의
# ────────────────────────────────────────────────────────────────
WCONCEPT_CATEGORIES: list[dict] = [
    {"code": "10201", "name": "상의"},
    {"code": "10202", "name": "하의"},
    {"code": "10203", "name": "아우터"},
    {"code": "10204", "name": "원피스/스커트"},
]

WCONCEPT_BASE = (
    "https://display.wconcept.co.kr/display/api/best/v1/product"
    "?displayCategoryType={code}&gnbType=Y&page={page}&size=100"
)

# ────────────────────────────────────────────────────────────────
#   29cm 카테고리 정의
# ────────────────────────────────────────────────────────────────
CM29_CATEGORIES: list[dict] = [
    {"code": "268100100", "name": "상의"},
    {"code": "268100200", "name": "하의"},
    {"code": "268100300", "name": "아우터"},
    {"code": "268100400", "name": "원피스/스커트"},
]

# 알려진 후보 endpoint (실행 시 자동 탐지로 확인)
_CM29_ENDPOINT_CANDIDATES = [
    "https://api.29cm.co.kr/api-goods/v2/goods/category"
    "?categoryLargeCode={code}&sort=RECOMMENDED&page={page}&pageSize=100",
    "https://search.29cm.co.kr/api/search/listing"
    "?categoryCode={code}&sort=RECOMMENDED&page={page}&pageSize=100",
    "https://www.29cm.co.kr/api/v1/goods/category"
    "?categoryLargeCode={code}&sort=RECOMMENDED&page={page}&pageSize=100",
]

_CM29_PRODUCT_ID_RE = re.compile(
    r'"(?:productId|productNo|frontNo|goodsNo|itemNo|product_id)"\s*:\s*(\d+)',
    re.IGNORECASE,
)

# ────────────────────────────────────────────────────────────────
#   공통 헤더
# ────────────────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.wconcept.co.kr/",
}


# ────────────────────────────────────────────────────────────────
#   wconcept 수집기
# ────────────────────────────────────────────────────────────────

async def _wconcept_page(session, cat_code: str, page: int) -> tuple[list[dict], bool]:
    """
    wconcept BEST API 1페이지 호출.
    반환: (rows, is_last)
    rows 각 항목: itemCd, itemName, finalPrice, thumbnail, landingUrl, brandName
    """
    import aiohttp  # 지연 임포트
    url = WCONCEPT_BASE.format(code=cat_code, page=page)
    try:
        async with session.get(url, headers={**_HEADERS, "Referer": "https://display.wconcept.co.kr/"}) as resp:
            if resp.status != 200:
                print(f"  ⚠️  wconcept HTTP {resp.status} | {url[:80]}")
                return [], True
            payload = await resp.json(content_type=None)
    except Exception as exc:
        print(f"  ⚠️  wconcept 요청 실패: {exc}")
        return [], True

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    content = data.get("content", [])
    if not isinstance(content, list):
        return [], True

    is_last: bool = bool(data.get("last", True))
    if not content:
        return [], True

    rows: list[dict] = []
    for row in content:
        if not isinstance(row, dict):
            continue
        item_cd = str(row.get("itemCd", "")).strip()
        item_name = str(row.get("itemName", "")).strip()
        if not item_name or not item_cd:
            continue

        # 가격: finalPrice > salePrice > regularPrice
        price_raw = (
            row.get("finalPrice") or row.get("salePrice")
            or row.get("customerPrice") or row.get("regularPrice") or 0
        )
        price_krw = int(re.sub(r"[^0-9]", "", str(price_raw)) or 0)

        landing = str(row.get("landingUrl", "")).strip()
        # 정규 URL 변환
        m = re.search(r"/Product/(\d+)", landing, re.IGNORECASE)
        if m:
            source_url = f"https://m.wconcept.co.kr/Product/{m.group(1)}"
        else:
            source_url = landing or f"https://m.wconcept.co.kr/Product/{item_cd}"

        thumbnail = str(row.get("thumbnail", "") or row.get("imageUrl", "")).strip()
        brand = str(row.get("brandName", "") or row.get("brand", "")).strip()

        rows.append({
            "id": f"wconcept_bulk_{item_cd}",
            "mall": "wconcept",
            "brand": brand,
            "brand_origin": "",
            "name": item_name,
            "price_krw": price_krw,
            "price_jpy": 0,
            "main_image": thumbnail,
            "detail_images": [],
            "source_url": source_url,
            "item_cd": item_cd,
            "material": "",
            "country": "",
            "care": "",
            "notice": "",
            "style": "",
            "keyword": "",
            "tags": [],
        })
    return rows, is_last


async def collect_wconcept(limit: int) -> list[dict]:
    """
    wconcept 4카테고리에서 균등하게 limit개 수집.
    """
    try:
        import aiohttp
    except ImportError:
        print("❌  aiohttp 미설치: pip install aiohttp --break-system-packages")
        return []

    per_cat = max(1, (limit + len(WCONCEPT_CATEGORIES) - 1) // len(WCONCEPT_CATEGORIES))
    all_items: list[dict] = []
    seen_ids: set[str] = set()

    async with aiohttp.ClientSession() as session:
        for cat in WCONCEPT_CATEGORIES:
            cat_items: list[dict] = []
            page = 0
            print(f"\n[wconcept/{cat['name']}] 수집 시작 (목표: {per_cat}개)")

            while len(cat_items) < per_cat:
                rows, is_last = await _wconcept_page(session, cat["code"], page)
                new = 0
                for r in rows:
                    key = r["item_cd"]
                    if key not in seen_ids:
                        seen_ids.add(key)
                        cat_items.append(r)
                        new += 1

                print(f"  page {page:3d} | +{new:3d}개 | 누계 {len(cat_items)}개")
                page += 1

                if is_last or not rows:
                    print(f"  → 마지막 페이지 도달 (page {page-1})")
                    break
                await asyncio.sleep(0.3)   # 서버 부하 완화

            all_items.extend(cat_items[:per_cat])
            print(f"[wconcept/{cat['name']}] 완료: {len(cat_items[:per_cat])}개")

    print(f"\n[wconcept] 총 {len(all_items)}개 수집")
    return all_items


# ────────────────────────────────────────────────────────────────
#   29cm endpoint 탐지 (Playwright 1회)
# ────────────────────────────────────────────────────────────────

def _load_endpoints() -> dict:
    if ENDPOINT_CACHE.exists():
        try:
            return json.loads(ENDPOINT_CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_endpoints(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ENDPOINT_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def sniff_29cm_endpoint() -> str | None:
    """
    Playwright로 29cm 카테고리 페이지를 열어 실제 API endpoint를 탐지.
    탐지 성공 시 data/bulk_endpoints.json에 저장 후 반환.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌  playwright 미설치")
        return None

    seed = (
        "https://www.29cm.co.kr/store/category/list"
        "?categoryLargeCode=268100100&sort=RECOMMENDED&defaultSort=RECOMMENDED"
    )
    candidates: list[str] = []

    print("\n[29cm 탐지] Playwright로 카테고리 페이지 로드 중...")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ko-KR",
            user_agent=_HEADERS["User-Agent"],
        )
        page = await context.new_page()

        async def on_response(response):
            try:
                ctype = response.headers.get("content-type", "")
                if "json" not in ctype:
                    return
                url = response.url
                # product ID가 여러 개 포함된 JSON 응답 endpoint만 기록
                body = await response.text()
                ids = _CM29_PRODUCT_ID_RE.findall(body)
                if len(ids) >= 5:
                    candidates.append(url)
            except Exception:
                pass

        page.on("response", on_response)
        await page.goto(seed, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(5)
        for _ in range(4):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
        await browser.close()

    # 후보 중 카테고리 관련 API endpoint 추출
    api_endpoint = None
    for url in candidates:
        # 카테고리 코드가 포함된 endpoint 우선
        if "268100100" in url or "category" in url.lower():
            # 쿼리 제거 → 템플릿 변환
            base = url.split("?")[0]
            api_endpoint = base
            print(f"[29cm 탐지] endpoint 후보 발견: {base}")
            break

    if not api_endpoint and candidates:
        api_endpoint = candidates[0].split("?")[0]
        print(f"[29cm 탐지] fallback endpoint: {api_endpoint}")

    if api_endpoint:
        endpoints = _load_endpoints()
        endpoints["29cm"] = {
            "base": api_endpoint,
            "detected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "candidates": [c.split("?")[0] for c in candidates[:5]],
        }
        _save_endpoints(endpoints)
        print(f"✅  endpoint 저장 완료: {ENDPOINT_CACHE}")
        return api_endpoint

    print("⚠️  29cm API endpoint를 자동 탐지하지 못했습니다.")
    print("   candidates:", candidates[:3])
    return None


# ────────────────────────────────────────────────────────────────
#   29cm 수집기
# ────────────────────────────────────────────────────────────────

async def _cm29_page(session, endpoint_tpl: str, cat_code: str, page: int) -> tuple[list[dict], bool]:
    """
    29cm 카테고리 API 1페이지 호출.
    반환: (rows, is_last)
    """
    import aiohttp
    url = endpoint_tpl.format(code=cat_code, page=page)
    try:
        async with session.get(url, headers={**_HEADERS, "Referer": "https://www.29cm.co.kr/"}) as resp:
            if resp.status != 200:
                return [], True
            payload = await resp.json(content_type=None)
    except Exception as exc:
        print(f"  ⚠️  29cm 요청 실패: {exc}")
        return [], True

    # 여러 응답 구조 처리
    if not isinstance(payload, dict):
        return [], True

    # 공통 패턴: data.items / data.products / data.list / items / products
    items_raw: list = []
    for key_path in [
        ["data", "items"], ["data", "products"], ["data", "list"],
        ["items"], ["products"], ["list"], ["data", "content"],
    ]:
        node = payload
        for k in key_path:
            if isinstance(node, dict):
                node = node.get(k)
            else:
                node = None
                break
        if isinstance(node, list) and node:
            items_raw = node
            break

    if not items_raw:
        # fallback: JSON 전체에서 productId 추출
        body_str = json.dumps(payload)
        ids = _CM29_PRODUCT_ID_RE.findall(body_str)
        if ids:
            rows = []
            for pid in ids:
                rows.append({
                    "id": f"29cm_bulk_{pid}",
                    "mall": "29cm",
                    "brand": "",
                    "brand_origin": "",
                    "name": "",
                    "price_krw": 0,
                    "price_jpy": 0,
                    "main_image": "",
                    "detail_images": [],
                    "source_url": f"https://www.29cm.co.kr/products/{pid}",
                    "item_cd": pid,
                    "material": "",
                    "country": "",
                    "care": "",
                    "notice": "",
                    "style": "",
                    "keyword": "",
                    "tags": [],
                })
            return rows, len(rows) < 50

        return [], True

    # 구조화된 items 처리
    rows: list[dict] = []
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        pid = str(
            item.get("productId") or item.get("frontNo") or item.get("productNo")
            or item.get("goodsNo") or item.get("itemNo") or ""
        ).strip()
        if not pid:
            continue

        name = str(
            item.get("productName") or item.get("name") or item.get("goodsName") or ""
        ).strip()
        price_raw = (
            item.get("finalDiscountedPrice") or item.get("salePrice")
            or item.get("price") or item.get("consumerPrice") or 0
        )
        price_krw = int(re.sub(r"[^0-9]", "", str(price_raw)) or 0)
        thumbnail = str(
            item.get("listImageUrl") or item.get("imageUrl")
            or item.get("thumbnail") or item.get("mainImageUrl") or ""
        ).strip()
        brand = str(
            item.get("brandNameKo") or item.get("brandName") or item.get("brand") or ""
        ).strip()
        source_url = (
            item.get("pcDetailUrl") or item.get("mobileDetailUrl")
            or f"https://www.29cm.co.kr/products/{pid}"
        )

        rows.append({
            "id": f"29cm_bulk_{pid}",
            "mall": "29cm",
            "brand": brand,
            "brand_origin": "",
            "name": name,
            "price_krw": price_krw,
            "price_jpy": 0,
            "main_image": thumbnail,
            "detail_images": [],
            "source_url": str(source_url),
            "item_cd": pid,
            "material": "",
            "country": "",
            "care": "",
            "notice": "",
            "style": "",
            "keyword": "",
            "tags": [],
        })

    # 마지막 페이지 판단
    total = (
        payload.get("data", {}).get("total")
        or payload.get("data", {}).get("totalElements")
        or payload.get("total")
        or None
    )
    if total is not None:
        is_last = (page + 1) * 100 >= int(total)
    else:
        is_last = len(rows) < 50

    return rows, is_last


async def _try_cm29_endpoint(session, tpl: str) -> bool:
    """endpoint 템플릿이 실제로 동작하는지 확인 (1페이지 시범 호출)."""
    rows, _ = await _cm29_page(session, tpl, "268100100", 1)
    return bool(rows)


async def collect_29cm(limit: int) -> list[dict]:
    """
    29cm 4카테고리에서 균등하게 limit개 수집.
    endpoint가 없으면 자동 탐지 시도.
    """
    try:
        import aiohttp
    except ImportError:
        print("❌  aiohttp 미설치: pip install aiohttp --break-system-packages")
        return []

    # ── endpoint 결정 ───────────────────────────────────────────
    endpoint_tpl: str | None = None

    endpoints = _load_endpoints()
    saved_base = endpoints.get("29cm", {}).get("base", "")
    if saved_base:
        # 저장된 base에 쿼리 파라미터 붙이기 (추측)
        endpoint_tpl = saved_base + "?categoryLargeCode={code}&sort=RECOMMENDED&page={page}&pageSize=100"
        print(f"[29cm] 저장된 endpoint 사용: {saved_base}")

    if endpoint_tpl is None:
        # 후보 순서로 시도
        print("[29cm] endpoint 탐지 중 (candidate 테스트)...")
        async with aiohttp.ClientSession() as sess:
            for tpl in _CM29_ENDPOINT_CANDIDATES:
                ok = await _try_cm29_endpoint(sess, tpl)
                if ok:
                    endpoint_tpl = tpl
                    print(f"  ✅  동작하는 endpoint: {tpl.split('?')[0]}")
                    break
                else:
                    print(f"  ✗  {tpl.split('?')[0][:60]}")

    if endpoint_tpl is None:
        print(
            "\n⚠️  29cm API endpoint를 자동으로 찾지 못했습니다.\n"
            "   다음 명령으로 Playwright 탐지를 실행하세요:\n"
            "   python bulk_collector.py --sniff 29cm\n"
        )
        return []

    # ── 수집 ────────────────────────────────────────────────────
    per_cat = max(1, (limit + len(CM29_CATEGORIES) - 1) // len(CM29_CATEGORIES))
    all_items: list[dict] = []
    seen_ids: set[str] = set()

    async with aiohttp.ClientSession() as session:
        for cat in CM29_CATEGORIES:
            cat_items: list[dict] = []
            page = 1
            print(f"\n[29cm/{cat['name']}] 수집 시작 (목표: {per_cat}개)")

            while len(cat_items) < per_cat:
                rows, is_last = await _cm29_page(session, endpoint_tpl, cat["code"], page)
                new = 0
                for r in rows:
                    key = r["item_cd"]
                    if key not in seen_ids:
                        seen_ids.add(key)
                        cat_items.append(r)
                        new += 1

                print(f"  page {page:3d} | +{new:3d}개 | 누계 {len(cat_items)}개")
                page += 1

                if is_last or not rows:
                    print(f"  → 마지막 페이지 도달 (page {page-1})")
                    break
                await asyncio.sleep(0.2)

            all_items.extend(cat_items[:per_cat])
            print(f"[29cm/{cat['name']}] 완료: {len(cat_items[:per_cat])}개")

    print(f"\n[29cm] 총 {len(all_items)}개 수집")
    return all_items


# ────────────────────────────────────────────────────────────────
#   저장 + enrichment
# ────────────────────────────────────────────────────────────────

def _save_and_enrich(items: list[dict], no_enrich: bool) -> None:
    from crawler.services.crawl_progress import locked_merge_save
    from shared.fx_converter import krw_to_jpy

    # JPY 변환
    for item in items:
        if not item.get("price_jpy") and item.get("price_krw"):
            item["price_jpy"] = krw_to_jpy(int(item["price_krw"]))

    print(f"\n[저장] {len(items)}개 상품 products_raw.json 병합 저장...")
    locked_merge_save(items)

    if no_enrich:
        return

    try:
        from data_enrichment import run_enrichment
        raw_path = DATA_DIR / "products_raw.json"
        enriched_path = DATA_DIR / "products_enriched.json"
        stats = run_enrichment(raw_path=raw_path, out_path=enriched_path)
        print(
            f"[추출] enriched 생성 완료: {stats.get('enriched_count', '?')}개"
        )
    except Exception as exc:
        print(f"⚠️  enrichment 실패: {exc}")
        print("   python data_enrichment.py  로 수동 실행 가능")


# ────────────────────────────────────────────────────────────────
#   CLI
# ────────────────────────────────────────────────────────────────

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(
        description="wconcept / 29cm 대량 수집기 (API 직접 호출)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mall",
        default="wconcept",
        choices=["wconcept", "29cm", "all"],
        help="수집 대상 (기본: wconcept)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3000,
        help="총 수집 목표 개수 (기본: 3000). 4카테고리 균등 분배",
    )
    parser.add_argument(
        "--sniff",
        metavar="MALL",
        default=None,
        choices=["29cm"],
        help="Playwright로 API endpoint를 탐지하고 저장 (29cm 전용)",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="수집 후 data_enrichment.py 자동 실행 생략",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="저장하지 않고 수집 수만 출력 (테스트용)",
    )
    args = parser.parse_args()

    # ── endpoint 탐지 모드 ───────────────────────────────────────
    if args.sniff:
        result = asyncio.run(sniff_29cm_endpoint())
        if result:
            print(f"\n✅  탐지된 endpoint: {result}")
            print("   다음 실행: python bulk_collector.py --mall 29cm --limit 3000")
        else:
            print("\n❌  탐지 실패. 수동으로 endpoint를 확인해야 합니다.")
        return

    # ── 수집 모드 ────────────────────────────────────────────────
    malls = ["wconcept", "29cm"] if args.mall == "all" else [args.mall]
    all_items: list[dict] = []

    for mall in malls:
        if mall == "wconcept":
            items = asyncio.run(collect_wconcept(args.limit))
        else:
            items = asyncio.run(collect_29cm(args.limit))
        all_items.extend(items)

    print(f"\n{'='*50}")
    print(f"수집 완료 | 총 {len(all_items)}개")
    print(f"{'='*50}")

    if args.no_save:
        print("--no-save 옵션: 저장 생략")
        return

    if all_items:
        _save_and_enrich(all_items, no_enrich=args.no_enrich)
        print("\n✅  완료!")
        print("   다음 단계: python export_csv.py")
    else:
        print("\n⚠️  수집된 상품 없음. 저장 생략.")


if __name__ == "__main__":
    main()
