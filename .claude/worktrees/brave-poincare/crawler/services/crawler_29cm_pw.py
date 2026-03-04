"""
crawler_29cm_pw.py  —  29cm.co.kr Playwright 크롤러

전략:
1. 시드 URL을 Playwright로 열고 domcontentloaded + 고정 sleep 후 모든 href 수집
   (CARD_SELECTOR 사전 체크 제거 — category 페이지에서 href 형식이 달라 false-reject 발생)
2. 네트워크 인터셉트: XHR/fetch 응답에서 product ID 직접 추출 (SPA 대응)
3. 수집된 URL로 상품 페이지 진입 → JSON-LD 또는 DOM 파싱
4. 이미지 /images/29cm/ 로컬 저장
"""
from __future__ import annotations

import asyncio
import json
import re

from playwright.async_api import BrowserContext, Page, Response

from crawler.services.crawler_playwright_base import PlaywrightBaseCrawler
from shared.brand_utils import extract_brand, guess_brand_origin

DOMAIN = "29cm.co.kr"

# 29cm 상품 URL 패턴: /products/12345  /catalog/12345  /product/catalog/12345
PRODUCT_RE = re.compile(r"29cm\.co\.kr/.*(products?|catalog)/\d+", re.IGNORECASE)

# 페이지/응답 본문 안에서 product ID 추출 (JSON 키 기반)
PRODUCT_ID_RE = re.compile(
    r'"(?:productId|productNo|goodsNo|itemNo|product_id)"\s*:\s*(\d+)',
    re.IGNORECASE,
)


def _norm_29cm_url(raw: str) -> str | None:
    """href 또는 숫자 ID를 정규 29cm 상품 URL로 변환. 실패 시 None."""
    raw = raw.strip()
    # 이미 완전한 URL
    if PRODUCT_RE.search(raw):
        return raw.split("?")[0]
    # 상대경로 /products/12345 또는 /catalog/12345
    m = re.match(r"^/(products?|catalog)/(\d+)", raw, re.IGNORECASE)
    if m:
        return f"https://www.29cm.co.kr/{m.group(1)}/{m.group(2)}"
    return None


class TwentyNineCrawlerPW(PlaywrightBaseCrawler):
    domain = DOMAIN
    mall = "29cm"

    # ── 1단계: 상품 링크 수집 ───────────────────────────────────────────
    async def discover_links(self, context: BrowserContext) -> list[str]:
        seen: set[str] = set()
        links: list[str] = []

        # 네트워크 응답에서 product ID를 잡을 공용 세트
        api_ids: set[str] = set()

        async def _intercept(response: Response) -> None:
            """XHR/fetch 응답에서 productId 추출."""
            try:
                ctype = response.headers.get("content-type", "")
                if "json" not in ctype:
                    return
                body = await response.text()
                for pid in PRODUCT_ID_RE.findall(body):
                    api_ids.add(pid)
            except Exception:
                pass

        for seed in self.config.seed_urls:
            if len(links) >= self.config.max_products * 2:
                break

            page: Page = await context.new_page()
            page.on("response", _intercept)
            try:
                self._log(f"카테고리 진입: {seed}")
                ok = await self._safe_goto(page, seed)
                if not ok:
                    continue

                # React 렌더링 대기 (networkidle 미사용)
                await asyncio.sleep(4)

                # 무한스크롤: 페이지 하단까지 스크롤하며 새 상품 로드
                for _ in range(6):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)

                # ① DOM의 모든 href 수집
                hrefs: list[str] = await page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.href || e.getAttribute('href') || '')"
                )
                for href in hrefs:
                    url = _norm_29cm_url(href)
                    if url and url not in seen:
                        seen.add(url)
                        links.append(url)

                # ② 페이지 HTML 소스에서 추가 패턴 탐지
                try:
                    html = await page.content()
                    # "/products/12345" 형태 추출
                    for m in re.finditer(r'"/(products?|catalog)/(\d+)"', html, re.IGNORECASE):
                        url = f"https://www.29cm.co.kr/{m.group(1)}/{m.group(2)}"
                        if url not in seen:
                            seen.add(url)
                            links.append(url)
                    # JSON 키 기반 ID 추출
                    for pid in PRODUCT_ID_RE.findall(html):
                        url = f"https://www.29cm.co.kr/products/{pid}"
                        if url not in seen:
                            seen.add(url)
                            links.append(url)
                except Exception:
                    pass

                # ③ data-* 속성의 숫자 ID 추출
                try:
                    data_ids: list = await page.evaluate("""
                        () => {
                            const attrs = ['data-product-id','data-product-no','data-goods-no','data-item-no'];
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
                        url = f"https://www.29cm.co.kr/products/{pid}"
                        if url not in seen:
                            seen.add(url)
                            links.append(url)
                except Exception:
                    pass

                self._log(f"  링크 누적: {len(links)}개 (API IDs 대기 중: {len(api_ids)}개)")

            except Exception as exc:
                self._log(f"시드 실패: {seed} ({exc})")
            finally:
                page.remove_listener("response", _intercept)
                await page.close()

        # ③ 네트워크 인터셉트로 잡은 product ID → URL 변환
        for pid in api_ids:
            url = f"https://www.29cm.co.kr/products/{pid}"
            if url not in seen:
                seen.add(url)
                links.append(url)

        self._log(f"링크 총 {len(links)}개 수집 완료")
        return links

    # ── 2단계: 상품 상세 파싱 ──────────────────────────────────────────
    async def parse_product(self, page: Page, url: str, idx: int) -> dict | None:
        ok = await self._safe_goto(page, url)
        if not ok:
            return None

        await asyncio.sleep(2)

        try:
            await page.wait_for_selector(
                "h1, h2, [class*='name'], [class*='title'], [class*='product']",
                timeout=8_000,
            )
        except Exception:
            pass

        name = await self._extract_name(page)
        if not name:
            return None

        price_krw = await self._extract_price(page)

        # 상세 이미지 로드를 위해 스크롤
        await self._scroll_to_bottom(page, times=3)
        await asyncio.sleep(1)

        main_url, detail_urls = await self._extract_images(page)
        if not main_url:
            return None

        slug = self._safe_name(name)
        item_id = f"29cm_{idx:04d}_{slug}"
        main_local, detail_local = self._download_images(item_id, main_url, detail_urls)

        quality = self._evaluate_image_quality(main_local, detail_local)
        if self.config.strict_images and not quality.ok:
            self._log(f"quality reject: {url} ({quality.reason})")
            return None

        detail_payload = quality.filtered_detail_images or detail_local
        brand = extract_brand(name)
        brand_origin = guess_brand_origin(name=name, brand=brand)
        return {
            "id": item_id,
            "mall": "29cm",
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
            "source_url": url,
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

    # ── 내부 헬퍼 ───────────────────────────────────────────────────────
    async def _extract_name(self, page: Page) -> str:
        # 1) JSON-LD
        ld = await self._get_jsonld(page)
        name_val = ld.get("name")
        if name_val:
            return str(name_val).strip()

        # 2) OG 메타 — str() 강제 변환 (dict 직렬화 방어)
        try:
            og: list = await page.eval_on_selector_all(
                'meta[property="og:title"]',
                "els => els.map(e => e.getAttribute('content') || '')",
            )
            if og and og[0]:
                return str(og[0]).strip()
        except Exception:
            pass

        # 3) 제목 선택자 순서대로 시도
        for sel in [
            "[class*='product-name']", "[class*='ProductName']",
            "[class*='item-name']", "[class*='goods-name']",
            "h1", "h2",
        ]:
            try:
                text = await page.inner_text(sel, timeout=2_000)
                text = str(text).strip()
                if text and len(text) > 2:
                    return text
            except Exception:
                continue

        # 4) title 태그
        try:
            title = await page.title()
            return str(title).strip()
        except Exception:
            return ""

    async def _extract_price(self, page: Page) -> int:
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
                        return int(nums)

        # 2) 페이지 소스에서 가격 패턴
        try:
            content = await page.content()
            m = re.search(r"([0-9]{2,3}(?:,[0-9]{3})+)\s*원", content)
            if m:
                return int(m.group(1).replace(",", ""))
        except Exception:
            pass
        return 0

    # 29cm 상품 이미지 CDN 도메인 (이외 도메인은 배너/광고일 가능성 높음)
    _PRODUCT_IMG_DOMAINS = (
        "img.29cm.co.kr",
        "imgcdn.29cm.co.kr",
        "media.29cm.co.kr",
        "29cm.co.kr",
    )

    async def _extract_images(self, page: Page) -> tuple[str, list[str]]:
        collected: list[str] = []
        seen: set[str] = set()
        # 쿼리스트링 제거 후 중복 체크용 (같은 원본 이미지 다른 크기 파라미터 제거)
        seen_base: set[str] = set()

        def _add(src: str) -> None:
            full = self._normalize_url(str(src))
            if not full or full in seen:
                return
            low = full.lower()
            # ① UI 요소 제거
            if any(tok in low for tok in ("icon", "logo", "sprite", "badge", "arrow", "btn", "banner", "event", "notice")):
                return
            # ② CDN 도메인 필터 (29cm 전용 CDN이 아닌 외부 이미지 제외)
            from urllib.parse import urlparse
            host = urlparse(full).netloc.lower()
            if not any(d in host for d in self._PRODUCT_IMG_DOMAINS):
                return
            # ③ w= 파라미터로 소형 썸네일 제외 (300px 미만)
            w_match = re.search(r"[?&]w=(\d+)", full)
            if w_match and int(w_match.group(1)) < 300:
                return
            # ④ URL에서 크기 지정 경로 패턴 제외
            if any(s in low for s in ("_50.", "_100.", "_150.", "_200.", "/50/", "/100/", "/150/", "/200/")):
                return
            # ⑤ 쿼리스트링 없는 베이스 URL로 중복 방지
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

        # 3) 실제 렌더링된 img src
        try:
            imgs: list = await page.eval_on_selector_all(
                "img",
                "els => els.map(e => e.currentSrc || e.src || e.getAttribute('data-src') || '')",
            )
            for src in imgs:
                _add(str(src))
        except Exception:
            pass

        # 4) HTML 소스에서 이미지 URL 정규식
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
            return not any(s in u for s in ("thumb", "_s.", "_xs.", "50x", "100x", "200x", "_sm", "small"))

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
