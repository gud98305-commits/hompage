"""
crawler_wconcept_pw.py  —  wconcept.co.kr Playwright 크롤러

wconcept는 React SPA라 requests+BeautifulSoup으로는 렌더링된 HTML을 얻을 수 없다.

전략:
1. 네트워크 인터셉트: XHR/fetch 응답(JSON)에서 product ID 직접 추출 (가장 신뢰성 높음)
2. DOM의 모든 href 수집 후 wconcept 상품 URL 패턴으로 필터
3. 페이지 HTML 소스에서 product URL 정규식 탐지
4. 수집된 URL로 상품 페이지 진입 → 이름/가격/이미지 추출
5. 이미지 /images/wconcept/ 로컬 저장
"""
from __future__ import annotations

import asyncio
import json
import re

from playwright.async_api import BrowserContext, Page, Response

from crawler.services.crawler_playwright_base import PlaywrightBaseCrawler
from shared.brand_utils import extract_brand, guess_brand_origin

DOMAIN = "wconcept.co.kr"

# wconcept 상품 URL 패턴 (대소문자 무관)
PRODUCT_RE = re.compile(r"wconcept\.co\.kr/Product/\d+", re.IGNORECASE)

# API 응답에서 product ID 추출
PRODUCT_ID_RE = re.compile(
    r'"(?:productNo|productId|itemNo|goodsNo|product_id|itemCd|eventValue)"\s*:\s*"?(\d+)"?',
    re.IGNORECASE,
)

LANDING_URL_RE = re.compile(
    r'https?://(?:m\.)?wconcept\.co\.kr/Product/\d+',
    re.IGNORECASE,
)

_GENERIC_NAME_SET = {
    "w concept",
    "wconcept",
    "w 컨셉",
    "w컨셉",
    "[w concept]",
}


def _is_generic_name(text: str) -> bool:
    norm = re.sub(r"\s+", " ", (text or "")).strip().lower()
    return not norm or norm in _GENERIC_NAME_SET


def _is_target_apparel_row(row: dict) -> bool:
    """
    BEST API 행에서 의류(top/bottom/outer/dress 중심)만 1차 통과.
    - depth1이 의류가 아니면 제외
    - 라운지/언더웨어 등 비타겟 의류는 제외
    """
    depth1 = str(row.get("categoryDepthName1", "")).strip().lower()
    if depth1 and ("의류" not in depth1 and "clothing" not in depth1):
        return False

    depth2 = str(row.get("categoryDepthName2", "")).strip().lower()
    depth3 = str(row.get("categoryDepthName3", "")).strip().lower()
    merged = f"{depth2} {depth3}"
    if any(tok in merged for tok in ("언더웨어", "라운지", "잠옷", "underwear", "lounge")):
        return False
    return True


def _norm_wconcept_url(raw: str) -> str | None:
    """href를 정규 wconcept 상품 URL로 변환."""
    raw = str(raw).strip()
    if PRODUCT_RE.search(raw):
        m = re.search(r"/Product/(\d+)", raw, re.IGNORECASE)
        if m:
            return f"https://m.wconcept.co.kr/Product/{m.group(1)}"
    # 상대경로: /Product/12345
    m = re.match(r"^/Product/(\d+)", raw, re.IGNORECASE)
    if m:
        return f"https://m.wconcept.co.kr/Product/{m.group(1)}"
    return None


class WConceptCrawlerPW(PlaywrightBaseCrawler):
    domain = DOMAIN
    mall = "wconcept"

    # ── 1단계: 상품 링크 수집 ───────────────────────────────────────────
    async def discover_links(self, context: BrowserContext) -> list[str]:
        seen: set[str] = set()
        links: list[str] = []
        api_ids: set[str] = set()
        api_urls: set[str] = set()

        async def _intercept(response: Response) -> None:
            """JSON XHR/fetch에서 product ID 추출."""
            try:
                ctype = response.headers.get("content-type", "")
                if "json" not in ctype:
                    return
                body = await response.text()

                # 최신 display BEST API는 landingUrl / itemCd를 제공함.
                # 이 경로를 우선 사용하면 DOM href가 없어도 링크 수집이 가능하다.
                if "/display/api/best/v1/product" in response.url:
                    try:
                        payload = json.loads(body)
                        rows = (
                            payload.get("data", {}).get("content", [])
                            if isinstance(payload, dict)
                            else []
                        )
                        for row in rows:
                            if not isinstance(row, dict):
                                continue
                            if not _is_target_apparel_row(row):
                                continue

                            landing = _norm_wconcept_url(str(row.get("landingUrl", "")))
                            if landing:
                                api_urls.add(landing)

                            item_cd = str(row.get("itemCd", "")).strip()
                            if item_cd.isdigit():
                                api_ids.add(item_cd)
                        return
                    except Exception:
                        # JSON 구조가 바뀐 경우 아래 범용 정규식 fallback 사용
                        pass

                for hit in LANDING_URL_RE.findall(body):
                    norm = _norm_wconcept_url(hit)
                    if norm:
                        api_urls.add(norm)
                for pid in PRODUCT_ID_RE.findall(body):
                    api_ids.add(pid)
            except Exception:
                pass

        for seed in self.config.seed_urls:
            if len(links) + len(api_ids) + len(api_urls) >= self.config.max_products * 2:
                break

            page: Page = await context.new_page()
            page.on("response", _intercept)
            try:
                self._log(f"카테고리 진입: {seed}")
                ok = await self._safe_goto(page, seed)
                if not ok:
                    continue

                # React 렌더링 대기
                await asyncio.sleep(4)

                # 무한스크롤: 스크롤하며 새 상품 로드
                for _ in range(8):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)

                # ① DOM href 수집
                try:
                    hrefs: list = await page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(e => e.href || e.getAttribute('href') || '')",
                    )
                    for href in hrefs:
                        url = _norm_wconcept_url(str(href))
                        if url and url not in seen:
                            seen.add(url)
                            links.append(url)
                except Exception:
                    pass

                # ② DOM data 속성에서 product ID 추출
                # wconcept는 종종 data-product-no, data-goods-no 등에 ID를 노출함
                try:
                    data_ids: list = await page.evaluate("""
                        () => {
                            const attrs = ['data-product-no','data-product-id','data-goods-no',
                                           'data-item-no','data-productno','data-id'];
                            const ids = new Set();
                            document.querySelectorAll('[' + attrs.join('],[') + ']').forEach(el => {
                                attrs.forEach(a => {
                                    const v = el.getAttribute(a);
                                    if (v && /^\\d+$/.test(v.trim())) ids.add(v.trim());
                                });
                            });
                            return Array.from(ids);
                        }
                    """)
                    for pid in data_ids:
                        url = f"https://m.wconcept.co.kr/Product/{pid}"
                        if url not in seen:
                            seen.add(url)
                            links.append(url)
                except Exception:
                    pass

                # ③ HTML 소스에서 패턴 탐지 (JSON 키 및 URL 경로 모두)
                try:
                    html = await page.content()
                    for m in re.finditer(r'["/]Product/(\d+)', html, re.IGNORECASE):
                        url = f"https://m.wconcept.co.kr/Product/{m.group(1)}"
                        if url not in seen:
                            seen.add(url)
                            links.append(url)
                    # JSON 키 기반 ID 추출 (window.__NEXT_DATA__ 등)
                    for m in re.finditer(
                        r'"(?:productNo|productId|goodsNo|itemNo|product_no)"\s*:\s*(\d+)',
                        html, re.IGNORECASE
                    ):
                        url = f"https://m.wconcept.co.kr/Product/{m.group(1)}"
                        if url not in seen:
                            seen.add(url)
                            links.append(url)
                except Exception:
                    pass

                self._log(
                    f"  링크 누적: {len(links)}개 | 네트워크 IDs: {len(api_ids)}개 | API URLs: {len(api_urls)}개"
                )

            except Exception as exc:
                self._log(f"시드 실패: {seed} ({exc})")
            finally:
                page.remove_listener("response", _intercept)
                await page.close()

        # ③ 네트워크 인터셉트로 잡은 landingUrl → URL
        for url in api_urls:
            norm = _norm_wconcept_url(url)
            if norm and norm not in seen:
                seen.add(norm)
                links.append(norm)

        # ④ 네트워크 인터셉트로 잡은 ID → URL
        for pid in api_ids:
            url = f"https://m.wconcept.co.kr/Product/{pid}"
            if url not in seen:
                seen.add(url)
                links.append(url)

        self._log(f"링크 총 {len(links)}개 수집 완료")
        return links

    # ── 2단계: 상품 상세 파싱 ──────────────────────────────────────────
    async def parse_product(self, page: Page, url: str, idx: int) -> dict | None:
        target_item_cd = ""
        m = re.search(r"/Product/(\d+)", url, re.IGNORECASE)
        if m:
            target_item_cd = m.group(1)

        detail_meta: dict[str, str | int] = {}

        async def _capture_detail_meta(response: Response) -> None:
            try:
                if "/api/v1/search/product/list" not in response.url:
                    return
                ctype = (response.headers.get("content-type") or "").lower()
                if "json" not in ctype:
                    return
                payload = json.loads(await response.text())
                items = payload.get("data", {}).get("items", [])
                if not isinstance(items, list):
                    return

                for row in items:
                    if not isinstance(row, dict):
                        continue
                    item_cd = str(row.get("itemCd", "")).strip()
                    if target_item_cd and item_cd and item_cd != target_item_cd:
                        continue

                    name = str(row.get("itemName", "")).strip()
                    if name and not _is_generic_name(name):
                        detail_meta["name"] = name

                    for key in ("finalPrice", "salePrice", "customerPrice", "price"):
                        raw = row.get(key)
                        if raw is None:
                            continue
                        nums = re.sub(r"[^0-9]", "", str(raw))
                        if nums:
                            detail_meta["price"] = int(nums)
                            break

                    landing = _norm_wconcept_url(str(row.get("landingUrl", "")))
                    if landing:
                        detail_meta["landing_url"] = landing
                    break
            except Exception:
                pass

        page.on("response", _capture_detail_meta)
        try:
            ok = await self._safe_goto(page, url)
            if not ok:
                return None

            await asyncio.sleep(3)
            try:
                await page.wait_for_selector(
                    "h1, h2, [class*='product-name'], [class*='ProductName'], "
                    "[class*='item-name'], [class*='goods-name']",
                    timeout=8_000,
                )
            except Exception:
                pass

            name = str(detail_meta.get("name", "")).strip()
            if not name or _is_generic_name(name):
                name = await self._extract_name(page)
            if not name:
                return None

            api_price = int(detail_meta.get("price", 0) or 0)
            price_krw = api_price if api_price > 0 else await self._extract_price(page)

            await self._scroll_to_bottom(page, times=4)
            await asyncio.sleep(1)

            main_url, detail_urls = await self._extract_images(page)
            if not main_url:
                return None

            slug = self._safe_name(name)
            item_id = f"wconcept_{idx:04d}_{slug}"
            main_local, detail_local = self._download_images(item_id, main_url, detail_urls)

            quality = self._evaluate_image_quality(main_local, detail_local)
            if self.config.strict_images and not quality.ok:
                self._log(f"quality reject: {url} ({quality.reason})")
                return None

            detail_payload = quality.filtered_detail_images or detail_local
            brand = extract_brand(name)
            brand_origin = guess_brand_origin(name=name, brand=brand)
            source_url = str(detail_meta.get("landing_url", "")).strip() or page.url or url
            return {
                "id": item_id,
                "mall": "wconcept",
                "brand": brand,
                "brand_origin": brand_origin,
                "name": name,
                "price_krw": price_krw,
                "main_image": main_local or main_url,
                "detail_images": detail_payload or detail_urls[:4],
                "notice": "",
                "style": "",
                "keyword": "",
                "tags": [],
                "idol_hint": "",
                "source_url": source_url,
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
            page.remove_listener("response", _capture_detail_meta)

    # ── 내부 헬퍼 ───────────────────────────────────────────────────────
    async def _extract_name(self, page: Page) -> str:
        # 1) JSON-LD
        ld = await self._get_jsonld(page)
        name_val = ld.get("name")
        if name_val:
            candidate = str(name_val).strip()
            if candidate and not _is_generic_name(candidate):
                return candidate

        # 2) OG 메타 (getAttribute 사용 — 반환값 항상 str)
        try:
            og: list = await page.eval_on_selector_all(
                'meta[property="og:title"]',
                "els => els.map(e => e.getAttribute('content') || '')",
            )
            for raw in og:
                cleaned = str(raw).strip()
                cleaned = re.sub(
                    r"\s*[|–-]\s*W\s*CONCEPT.*$",
                    "",
                    cleaned,
                    flags=re.IGNORECASE,
                ).strip()
                if cleaned and not _is_generic_name(cleaned):
                    return cleaned
        except Exception:
            pass

        # 3) DOM 선택자
        for sel in [
            "[class*='ProductName']", "[class*='product-name']",
            "[class*='goods-name']", "[class*='item-name']",
            "h1", "h2",
        ]:
            try:
                text = await page.inner_text(sel, timeout=2_000)
                text = str(text).strip()
                if text and len(text) > 2 and not _is_generic_name(text):
                    return text
            except Exception:
                continue

        try:
            title = await page.title()
            cleaned = str(title).strip()
            if cleaned and not _is_generic_name(cleaned):
                return cleaned
            return ""
        except Exception:
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
        for sel in ["[class*='price']", "[class*='Price']", "[class*='sale']"]:
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

        # 3) 페이지 소스 패턴
        try:
            content = await page.content()
            for m in re.finditer(r"([0-9]{2,3}(?:,[0-9]{3})+)\s*원", content):
                n = int(m.group(1).replace(",", ""))
                if 1_000 <= n <= 10_000_000:
                    candidates.append(n)
            for m in re.finditer(
                r'"(?:finalPrice|salePrice|customerPrice|price)"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
                content,
                re.IGNORECASE,
            ):
                n = int(float(m.group(1)))
                if 1_000 <= n <= 10_000_000:
                    candidates.append(n)
        except Exception:
            pass

        if not candidates:
            return 0
        return max(candidates)

    # wconcept 상품 이미지 CDN 도메인
    _PRODUCT_IMG_DOMAINS = (
        "sitem.ssgcdn.com",
        "sui.ssgcdn.com",
        "wconcept.co.kr",
        "cdn.wconcept.co.kr",
        "static.wconcept.co.kr",
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
            # ① UI 요소 제거
            if any(tok in low for tok in ("icon", "logo", "sprite", "badge", "btn", "banner", "event", "notice")):
                return
            # ② wconcept CDN 도메인 필터
            from urllib.parse import urlparse
            host = urlparse(full).netloc.lower()
            if not any(d in host for d in self._PRODUCT_IMG_DOMAINS):
                return
            # ③ ssgcdn 소형 썸네일 제외 (예: _80.jpg, _100.jpg 등)
            if re.search(r"_\d{2,3}\.(jpg|jpeg|png|webp)$", low):
                pixel_match = re.search(r"_(\d{2,3})\.(jpg|jpeg|png|webp)$", low)
                if pixel_match and int(pixel_match.group(1)) < 300:
                    return
            # ④ URL path 내 크기 지정 패턴 제외
            if any(s in low for s in ("/50/", "/100/", "/150/", "/200/", "_s.", "_xs.", "_sm")):
                return
            # ⑤ 베이스 URL 중복 방지
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

        # 4) HTML 소스
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
            return not any(s in u for s in ("thumb", "_s.", "_xs.", "50x", "100x", "200x", "sm_", "small"))

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
