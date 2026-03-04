"""
crawler_playwright_base.py
Playwright 기반 비동기 크롤러 공통 베이스.
각 쇼핑몰 크롤러는 이 클래스를 상속하여 구현한다.
"""
from __future__ import annotations

import sys
import asyncio
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = CRAWLER_ROOT / "data"
IMG_ROOT = CRAWLER_ROOT / "images"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import requests
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)
from shared.image_quality import evaluate_local_images, ImageQualityResult


class PlaywrightCrawlerConfig:
    def __init__(
        self,
        mall: str,
        seed_urls: list[str],
        max_products: int = 200,
        delay_sec: float = 1.0,
        timeout_ms: int = 30_000,
        strict_images: bool = True,
        verbose: bool = False,
        headless: bool = True,
        min_detail_images: int = 3,
        min_main_bytes: int = 3000,
        min_detail_bytes: int = 1000,
        min_detail_unique_ratio: float = 0.6,
    ):
        self.mall = mall
        self.seed_urls = seed_urls
        self.max_products = max_products
        self.delay_sec = delay_sec
        self.timeout_ms = timeout_ms
        self.strict_images = strict_images
        self.verbose = verbose
        self.headless = headless
        self.min_detail_images = min_detail_images
        self.min_main_bytes = min_main_bytes
        self.min_detail_bytes = min_detail_bytes
        self.min_detail_unique_ratio = min_detail_unique_ratio


class PlaywrightBaseCrawler:
    """Playwright 기반 크롤러 공통 베이스 클래스."""

    domain: str = ""
    mall: str = ""

    def __init__(self, config: PlaywrightCrawlerConfig):
        self.config = config
        # 이미지 다운로드용 requests 세션 (재사용)
        self._http = requests.Session()
        self._http.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            }
        )

    # ── 서브클래스 구현 필수 ────────────────────────────────────────────
    async def discover_links(self, context: BrowserContext) -> list[str]:
        """카테고리·시드 URL에서 상품 URL 목록을 수집한다."""
        raise NotImplementedError

    async def parse_product(self, page: Page, url: str, idx: int) -> dict | None:
        """상품 페이지 1개를 파싱해 dict 반환. 실패 시 None."""
        raise NotImplementedError

    # ── 공통 유틸 ───────────────────────────────────────────────────────
    def _log(self, msg: str) -> None:
        if self.config.verbose:
            print(f"[{self.config.mall}] {msg}")

    def _safe_name(self, text: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_").lower()[:80] or "item"

    def _normalize_url(self, src: str) -> str:
        raw = (src or "").strip()
        if not raw or raw.startswith("data:"):
            return ""
        if raw.startswith("//"):
            return f"https:{raw}"
        if raw.startswith("http"):
            return raw
        return f"https://{self.domain}{raw}"

    def _download(self, url: str, dest: Path) -> str:
        """URL → 로컬 파일 저장. 성공 시 웹 경로 반환, 실패 시 ''."""
        if not url:
            return ""
        try:
            res = self._http.get(
                url,
                timeout=20,
                headers={"Referer": f"https://{self.domain}/"},
            )
            res.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(res.content)
            return "/" + dest.relative_to(ROOT).as_posix()
        except Exception as exc:
            self._log(f"image download failed: {url} ({exc})")
            return ""

    def _download_images(
        self, item_id: str, main_url: str, detail_urls: list[str]
    ) -> tuple[str, list[str]]:
        """대표 이미지 + 상세 이미지를 /images/{mall}/ 아래 저장."""
        out_dir = IMG_ROOT / self.config.mall
        main_local = self._download(main_url, out_dir / f"{item_id}_main.jpg")
        detail_local: list[str] = []
        for idx, url in enumerate(detail_urls[:8], start=1):
            local = self._download(url, out_dir / f"{item_id}_detail_{idx}.jpg")
            if local:
                detail_local.append(local)
        return main_local, detail_local

    def _evaluate_image_quality(
        self,
        main_local: str,
        detail_local: list[str],
    ) -> ImageQualityResult:
        return evaluate_local_images(
            root=ROOT,
            main_image=main_local,
            detail_images=detail_local,
            min_detail_images=self.config.min_detail_images,
            min_main_bytes=self.config.min_main_bytes,
            min_detail_bytes=self.config.min_detail_bytes,
            min_detail_unique_ratio=self.config.min_detail_unique_ratio,
        )

    async def _scroll_to_bottom(self, page: Page, times: int = 5) -> None:
        """SPA 무한스크롤 대응: 천천히 하단까지 스크롤."""
        for _ in range(times):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.0)

    async def _safe_goto(self, page: Page, url: str) -> bool:
        """페이지 이동. 타임아웃·에러 시 False 반환."""
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.config.timeout_ms,
            )
            return True
        except Exception as exc:
            self._log(f"goto failed: {url} ({exc})")
            return False

    # ── 메인 크롤 루프 ──────────────────────────────────────────────────
    async def _run(self) -> list[dict]:
        results: list[dict] = []
        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(
                headless=self.config.headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context: BrowserContext = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="ko-KR",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            )
            # 불필요한 리소스(폰트·트래커) 차단 → 속도 향상
            await context.route(
                re.compile(r"\.(woff2?|ttf|otf)$"),
                lambda route, _: route.abort(),
            )

            print(f"[{self.config.mall}] 🔍 상품 링크 수집 중... (시드 {len(self.config.seed_urls)}개)")
            self._log("링크 수집 중...")
            links = await self.discover_links(context)
            print(f"[{self.config.mall}] 링크 {len(links)}개 수집 완료 → 상품 파싱 시작")
            self._log(f"링크 {len(links)}개 수집 완료")

            total = min(len(links), self.config.max_products)
            for idx, url in enumerate(links[:total], start=1):
                page: Page = await context.new_page()
                try:
                    item = await self.parse_product(page, url, idx)
                    if item:
                        results.append(item)
                        # 항상 표시: 10개마다 진행 상황 출력
                        if idx % 10 == 0 or idx == total:
                            print(
                                f"[{self.config.mall}] ✓ {idx}/{total} | "
                                f"수집 {len(results)}개 | {item['name'][:30]}"
                            )
                        self._log(f"ok ({idx}/{total}): {item['name'][:40]}")
                    else:
                        if idx % 10 == 0 or idx == total:
                            print(
                                f"[{self.config.mall}] ✗ {idx}/{total} | "
                                f"수집 {len(results)}개 | skipped"
                            )
                        self._log(f"skipped: {url}")
                except Exception as exc:
                    self._log(f"parse error: {url} ({exc})")
                finally:
                    await page.close()

                await asyncio.sleep(self.config.delay_sec)

            await browser.close()
        return results

    def crawl(self) -> list[dict]:
        """동기 진입점 — crawl_pipeline.py 에서 호출."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        IMG_ROOT.mkdir(parents=True, exist_ok=True)
        return asyncio.run(self._run())
