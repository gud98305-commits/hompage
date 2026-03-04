"""
crawler_musinsa_pw.py  —  musinsa.com Playwright 크롤러

전략:
1. 카테고리 페이지를 Playwright로 열고 무한스크롤 + 네트워크 인터셉트
   → XHR/fetch 응답 JSON에서 상품 goodsNo 직접 추출 (SPA 대응)
2. 수집된 URL로 상품 페이지 진입
   → 내부 Goods API (goods.musinsa.com/api2/goods/v1/detail) 인터셉트
   → 텍스트 상세정보(소재·사이즈·제조국 등) 추출
3. 이미지 /images/musinsa/ 로컬 저장

카테고리 코드:
  001 = 상의   002 = 아우터   003 = 하의(바지)   100 = 원피스·스커트
"""
from __future__ import annotations

import asyncio
import json
import re

from playwright.async_api import BrowserContext, Page, Response

from crawler.services.crawler_playwright_base import PlaywrightBaseCrawler
from shared.brand_utils import extract_brand, guess_brand_origin

DOMAIN = "musinsa.com"

# 무신사 상품 URL 패턴 (실제 확인된 형식: /products/{id})
PRODUCT_RE = re.compile(r"musinsa\.com/products/(\d+)(?:[/?#]|$)", re.IGNORECASE)

# API 응답에서 goodsNo / productId 추출 (범용 fallback)
GOODS_NO_RE = re.compile(
    r'"(?:goodsNo|productId|goods_no|goodsId|itemNo)"\s*:\s*"?(\d+)"?',
    re.IGNORECASE,
)

# 무신사 상품 목록 PLP API (실제 확인된 엔드포인트)
# api.musinsa.com/api2/dp/v2/plp/goods?gf=A&sortCode=POPULAR&category=001&size=60&page=N
LIST_API_RE = re.compile(
    r"api\.musinsa\.com/api2/dp/v\d+/plp/goods",
    re.IGNORECASE,
)

# 무신사 상품 상세 API (여러 버전 대응)
GOODS_API_RE = re.compile(
    r"(?:goods\.musinsa\.com/api2/goods/v\d+/detail"
    r"|api\.musinsa\.com/api2/dp/v\d+/(?:pdp|goods)/detail"
    r"|api\.musinsa\.com/api2/dp/v\d+/pdp"
    r"|musinsa\.com/api.*goods.*detail)",
    re.IGNORECASE,
)


def _norm_musinsa_url(raw: str) -> str | None:
    """href 또는 goodsNo → 정규 무신사 상품 URL. 실패 시 None."""
    raw = str(raw).strip()
    # 완전한 URL — 실제 형식: /products/{id}
    m = PRODUCT_RE.search(raw)
    if m:
        return f"https://www.musinsa.com/products/{m.group(1)}"
    # 상대경로 /products/12345
    m = re.match(r"^/products/(\d+)(?:[/?#]|$)", raw, re.IGNORECASE)
    if m:
        return f"https://www.musinsa.com/products/{m.group(1)}"
    return None


class MusinsaCrawlerPW(PlaywrightBaseCrawler):
    domain = DOMAIN
    mall = "musinsa"

    # ── 1단계: 상품 링크 수집 ───────────────────────────────────────────
    async def discover_links(self, context: BrowserContext) -> list[str]:
        seen: set[str] = set()
        links: list[str] = []
        api_ids: set[str] = set()

        async def _intercept(response: Response) -> None:
            """
            PLP API (api2/dp/v2/plp/goods) 응답에서 goodsLinkUrl + goodsNo 직접 추출.
            실제 확인된 응답 구조:
              {"data":{"list":[{"goodsNo":5961669,"goodsName":"...","goodsLinkUrl":"https://www.musinsa.com/products/5961669","thumbnail":"..."}]}}
            """
            try:
                ctype = response.headers.get("content-type", "")
                if "json" not in ctype:
                    return
                body = await response.text()

                # ① PLP 상품 목록 API (확인된 엔드포인트)
                if LIST_API_RE.search(response.url):
                    try:
                        payload = json.loads(body)
                        items = payload.get("data", {}).get("list", [])
                        if isinstance(items, list):
                            for row in items:
                                if not isinstance(row, dict):
                                    continue
                                # goodsLinkUrl 우선 사용 (정확한 URL)
                                link_url = str(row.get("goodsLinkUrl", "")).strip()
                                norm = _norm_musinsa_url(link_url)
                                if norm:
                                    api_ids.add(PRODUCT_RE.search(norm).group(1))
                                    continue
                                # fallback: goodsNo로 직접 생성
                                gno = str(row.get("goodsNo", "")).strip()
                                if gno.isdigit():
                                    api_ids.add(gno)
                        return
                    except Exception:
                        pass

                # ② 범용 fallback — goodsLinkUrl 패턴 탐지
                for hit in re.findall(r'"goodsLinkUrl"\s*:\s*"(https://www\.musinsa\.com/products/(\d+))"', body):
                    api_ids.add(hit[1])

                # ③ 범용 goodsNo fallback
                for gno in GOODS_NO_RE.findall(body):
                    api_ids.add(gno)

            except Exception:
                pass

        for seed in self.config.seed_urls:
            if len(api_ids) >= self.config.max_products * 2:
                break

            page: Page = await context.new_page()
            page.on("response", _intercept)
            try:
                self._log(f"카테고리 진입: {seed}")
                ok = await self._safe_goto(page, seed)
                if not ok:
                    continue

                # Next.js 렌더링 대기
                await asyncio.sleep(4)

                # 무한스크롤: 최대 10회 스크롤
                for _ in range(10):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1.5)

                # DOM href에서도 추출 (goodsLinkUrl: /products/{id} 형식)
                try:
                    hrefs: list = await page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(e => e.href || e.getAttribute('href') || '')",
                    )
                    for href in hrefs:
                        url = _norm_musinsa_url(href)
                        if url and url not in seen:
                            m = PRODUCT_RE.search(url)
                            if m:
                                api_ids.add(m.group(1))
                except Exception:
                    pass

                # HTML 소스에서 /products/{id} 패턴 탐지
                try:
                    html = await page.content()
                    for m in re.finditer(r'musinsa\.com/products/(\d+)(?:[/"\'?#]|$)', html):
                        api_ids.add(m.group(1))
                except Exception:
                    pass

                self._log(
                    f"  링크 누적: {len(links)}개 | 네트워크 IDs: {len(api_ids)}개"
                )

            except Exception as exc:
                self._log(f"시드 실패: {seed} ({exc})")
            finally:
                page.remove_listener("response", _intercept)
                await page.close()

        # ID → 올바른 URL 변환
        for gno in api_ids:
            url = f"https://www.musinsa.com/products/{gno}"
            if url not in seen:
                seen.add(url)
                links.append(url)

        self._log(f"링크 총 {len(links)}개 수집 완료")
        return links

    # ── 2단계: 상품 상세 파싱 ──────────────────────────────────────────
    async def parse_product(self, page: Page, url: str, idx: int) -> dict | None:
        # URL에서 goodsNo 추출 (/products/{id} 형식)
        m = PRODUCT_RE.search(url)
        target_goods_no = m.group(1) if m else ""

        # API 인터셉트로 텍스트 상세정보 수집
        api_detail: dict = {}

        async def _capture_goods_api(response: Response) -> None:
            """
            무신사 Goods API 응답에서 텍스트 상세정보 추출.
            - goods.musinsa.com/api2/goods/v1/detail?goodsNo={id}
            - 또는 goodsNo={id}를 포함하는 모든 JSON API 응답
            """
            try:
                url_lower = response.url.lower()
                is_goods_api = (
                    GOODS_API_RE.search(response.url)
                    or (target_goods_no and f"goodsno={target_goods_no}" in url_lower)
                    or (target_goods_no and f"goodsno%3d{target_goods_no}" in url_lower)
                    or (target_goods_no and f"/{target_goods_no}" in url_lower and "goods" in url_lower)
                )
                if not is_goods_api:
                    return
                ctype = (response.headers.get("content-type") or "").lower()
                if "json" not in ctype:
                    return

                payload = json.loads(await response.text())
                data = payload.get("data", {})
                if not isinstance(data, dict):
                    return

                goods_info = data.get("goodsInfo", data)

                # 상품명
                name = str(
                    goods_info.get("goodsNm")
                    or goods_info.get("goodsName")
                    or goods_info.get("name")
                    or ""
                ).strip()
                if name:
                    api_detail["name"] = name

                # 브랜드
                brand = str(
                    goods_info.get("brandName")
                    or goods_info.get("brand", {}).get("brandName", "") if isinstance(goods_info.get("brand"), dict) else ""
                    or ""
                ).strip()
                if brand:
                    api_detail["brand"] = brand

                # 가격
                for key in ("goodsPrice", "price", "salePrice", "finalPrice"):
                    raw = goods_info.get(key)
                    if raw is not None:
                        nums = re.sub(r"[^0-9]", "", str(raw))
                        if nums:
                            api_detail["price"] = int(nums)
                            break

                # 소재 / 제조국 / 기타 텍스트 상세정보
                detail_info = data.get("goodsDetailInfo", {}) or {}
                if isinstance(detail_info, dict):
                    material = str(detail_info.get("material") or detail_info.get("소재") or "").strip()
                    country = str(detail_info.get("madeCountry") or detail_info.get("제조국") or "").strip()
                    care = str(detail_info.get("laundry") or detail_info.get("세탁방법") or "").strip()
                    if material:
                        api_detail["material"] = material
                    if country:
                        api_detail["country"] = country
                    if care:
                        api_detail["care"] = care

                # 카테고리
                cat_info = goods_info.get("category", {})
                if isinstance(cat_info, dict):
                    api_detail["musinsa_category"] = str(
                        cat_info.get("categoryName") or cat_info.get("name") or ""
                    ).strip()

                # goodsNo 확인
                gno = str(goods_info.get("goodsNo") or target_goods_no).strip()
                if gno:
                    api_detail["item_cd"] = gno

            except Exception:
                pass

        page.on("response", _capture_goods_api)
        try:
            ok = await self._safe_goto(page, url)
            if not ok:
                return None

            await asyncio.sleep(3)

            # 상품명 대기
            try:
                await page.wait_for_selector(
                    "h2.goods_name, h1, [class*='goods-name'], [class*='GoodsName'], "
                    "[class*='product-name'], [class*='ProductName']",
                    timeout=8_000,
                )
            except Exception:
                pass

            # 스크롤로 상세 이미지 및 정보 로드
            await self._scroll_to_bottom(page, times=4)
            await asyncio.sleep(1)

            # 상품명 추출
            name = str(api_detail.get("name", "")).strip()
            if not name:
                name = await self._extract_name(page)
            if not name:
                return None

            # 가격 추출
            price_krw = int(api_detail.get("price", 0) or 0)
            if price_krw == 0:
                price_krw = await self._extract_price(page)

            # 이미지 추출
            main_url, detail_urls = await self._extract_images(page)
            if not main_url:
                return None

            slug = self._safe_name(name)
            item_id = f"musinsa_{idx:04d}_{slug}"
            main_local, detail_local = self._download_images(item_id, main_url, detail_urls)

            quality = self._evaluate_image_quality(main_local, detail_local)
            if self.config.strict_images and not quality.ok:
                self._log(f"quality reject: {url} ({quality.reason})")
                return None

            detail_payload = quality.filtered_detail_images or detail_local

            brand = str(api_detail.get("brand", "")).strip() or extract_brand(name)
            brand_origin = guess_brand_origin(name=name, brand=brand)

            # 상세 텍스트 정보 (SPA API 인터셉트로 가져온 값)
            notice_parts = []
            if api_detail.get("material"):
                notice_parts.append(f"소재: {api_detail['material']}")
            if api_detail.get("country"):
                notice_parts.append(f"제조국: {api_detail['country']}")
            if api_detail.get("care"):
                notice_parts.append(f"세탁: {api_detail['care']}")

            return {
                "id": item_id,
                "mall": "musinsa",
                "brand": brand,
                "brand_origin": brand_origin,
                "name": name,
                "price_krw": price_krw,
                "main_image": main_local or main_url,
                "detail_images": detail_payload or detail_urls[:4],
                "notice": " | ".join(notice_parts),
                "material": api_detail.get("material", ""),
                "country": api_detail.get("country", ""),
                "care": api_detail.get("care", ""),
                "musinsa_category": api_detail.get("musinsa_category", ""),
                "item_cd": api_detail.get("item_cd", target_goods_no),
                "style": "",
                "keyword": "",
                "tags": [],
                "idol_hint": "",
                "source_url": f"https://www.musinsa.com/products/{target_goods_no}",
                "main_image_source_url": main_url,
                "detail_image_source_urls": detail_urls[:8],
                "image_quality": {
                    "ok": quality.ok,
                    "reason": quality.reason,
                    "valid_detail_count": quality.valid_detail_count,
                    "detail_unique_ratio": round(quality.unique_ratio, 3),
                    "same_as_main_count": quality.same_as_main_count,
                    "missing_detail_count": quality.missing_detail_count,
                    "too_small_detail_count": quality.too_small_detail_count,
                    "main_size_bytes": quality.main_size_bytes,
                },
            }
        finally:
            page.remove_listener("response", _capture_goods_api)

    # ── 내부 헬퍼 ───────────────────────────────────────────────────────
    async def _extract_name(self, page: Page) -> str:
        # 1) JSON-LD
        ld = await self._get_jsonld(page)
        if ld.get("name"):
            return str(ld["name"]).strip()

        # 2) OG 메타
        try:
            og: list = await page.eval_on_selector_all(
                'meta[property="og:title"]',
                "els => els.map(e => e.getAttribute('content') || '')",
            )
            for raw in og:
                cleaned = re.sub(r"\s*[|–-]\s*MUSINSA.*$", "", str(raw), flags=re.IGNORECASE).strip()
                if cleaned and len(cleaned) > 2:
                    return cleaned
        except Exception:
            pass

        # 3) DOM 선택자 (무신사 실제 DOM 구조 대응)
        for sel in [
            # 무신사 신규 Next.js 구조
            "[class*='_goodsName']", "[class*='goodsName']",
            "[class*='goods_name']", "[class*='goods-name']",
            "h2.goods_name", "h1.goods_name",
            # 무신사 구형 구조
            ".goods_name", "#goods_name",
            "[class*='GoodsName']",
            "[class*='product-name']", "[class*='ProductName']",
            "h1", "h2",
        ]:
            try:
                text = await page.inner_text(sel, timeout=2_000)
                text = str(text).strip()
                if text and len(text) > 2:
                    return text
            except Exception:
                continue
        return ""

    async def _extract_price(self, page: Page) -> int:
        candidates: list[int] = []

        # 1) JSON-LD
        ld = await self._get_jsonld(page)
        offers = ld.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            for key in ("price", "lowPrice"):
                val = offers.get(key)
                if val:
                    nums = re.sub(r"[^0-9]", "", str(val))
                    if nums:
                        n = int(nums)
                        if 1_000 <= n <= 10_000_000:
                            candidates.append(n)

        # 2) 가격 선택자
        for sel in [
            "[class*='price']", "[class*='Price']",
            ".price_box", ".goods_price",
        ]:
            try:
                texts: list = await page.eval_on_selector_all(
                    sel,
                    "els => els.slice(0, 20).map(e => (e.textContent || '').trim())",
                )
                for text in texts:
                    nums = re.sub(r"[^0-9]", "", str(text))
                    if nums:
                        n = int(nums)
                        if 1_000 <= n <= 10_000_000:
                            candidates.append(n)
            except Exception:
                continue

        # 3) 페이지 소스
        try:
            content = await page.content()
            for m in re.finditer(r"([0-9]{2,3}(?:,[0-9]{3})+)\s*원", content):
                n = int(m.group(1).replace(",", ""))
                if 1_000 <= n <= 10_000_000:
                    candidates.append(n)
        except Exception:
            pass

        return min(candidates) if candidates else 0  # 할인가(최저가) 선택

    # 무신사 이미지 CDN 도메인
    # 실제 무신사 CDN: msscdn.net (Musinsa Static CDN)
    _PRODUCT_IMG_DOMAINS = (
        "msscdn.net",           # 메인 CDN (image.msscdn.net)
        "image.msscdn.net",
        "image.musinsa.com",
        "img.musinsa.com",
        "static.musinsa.com",
        "cdn.musinsa.com",
        "musinsa-static.s3",
        "musinsa.com",          # fallback: 도메인에 musinsa 포함이면 허용
    )

    async def _extract_images(self, page: Page) -> tuple[str, list[str]]:
        collected: list[str] = []
        seen: set[str] = set()
        seen_base: set[str] = set()

        def _add(src: str) -> None:
            full = self._normalize_url(str(src))
            if not full or full in seen:
                return
            low = full.lower()
            # UI 요소 제거
            if any(tok in low for tok in ("icon", "logo", "sprite", "badge", "btn", "banner")):
                return
            # 무신사 CDN 도메인 필터
            from urllib.parse import urlparse
            host = urlparse(full).netloc.lower()
            if not any(d in host for d in self._PRODUCT_IMG_DOMAINS):
                # CDN 외 도메인이라도 musinsa 관련이면 허용
                if "musinsa" not in host and "msscdn" not in host:
                    return
            # 소형 썸네일 제외
            if re.search(r"_\d{2,3}x\d{2,3}\.", low):
                return
            if any(s in low for s in ("/50/", "/100/", "/150/", "/200/", "_s.", "_xs.", "_sm")):
                return
            base = full.split("?")[0]
            if base in seen_base:
                return
            seen_base.add(base)
            seen.add(full)
            collected.append(full)

        # 1) JSON-LD
        ld = await self._get_jsonld(page)
        img_field = ld.get("image")
        if isinstance(img_field, str):
            _add(img_field)
        elif isinstance(img_field, list):
            for u in img_field:
                if isinstance(u, str):
                    _add(u)

        # 2) OG 이미지
        try:
            og_imgs: list = await page.eval_on_selector_all(
                'meta[property="og:image"], meta[property="og:image:url"]',
                "els => els.map(e => e.getAttribute('content') || '')",
            )
            for u in og_imgs:
                _add(str(u))
        except Exception:
            pass

        # 3) 렌더링된 img
        try:
            imgs: list = await page.eval_on_selector_all(
                "img",
                "els => els.map(e => e.currentSrc || e.src || e.getAttribute('data-src') || '')",
            )
            for src in imgs:
                _add(str(src))
        except Exception:
            pass

        # 4) HTML 소스에서 이미지 URL 추출
        try:
            html = await page.content()
            for hit in re.findall(
                r'https?://[^\"\'\s<>]+\.(?:jpg|jpeg|png|webp)(?:\?[^\"\'\s<>]*)?',
                html, re.IGNORECASE,
            ):
                _add(hit)
        except Exception:
            pass

        if not collected:
            return "", []

        def _looks_large(u: str) -> bool:
            return not any(s in u for s in ("thumb", "_s.", "_xs.", "50x", "100x", "200x", "sm_"))

        large = [u for u in collected if _looks_large(u)]
        ordered = (large + [u for u in collected if u not in large])[:8]
        return ordered[0], ordered[1:]

    async def _get_jsonld(self, page: Page) -> dict:
        try:
            scripts: list = await page.eval_on_selector_all(
                'script[type="application/ld+json"]',
                "els => els.map(e => e.textContent || '')",
            )
            for raw in scripts:
                try:
                    obj = json.loads(str(raw))
                except Exception:
                    continue
                for node in self._walk(obj):
                    if isinstance(node, dict) and str(node.get("@type", "")).lower() == "product":
                        return node
        except Exception:
            pass
        return {}

    def _walk(self, obj):
        if isinstance(obj, dict):
            yield obj
            for v in obj.values():
                yield from self._walk(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from self._walk(v)
