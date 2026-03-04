from __future__ import annotations

import sys
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = CRAWLER_ROOT / "data"
IMG_ROOT = CRAWLER_ROOT / 'images'

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import requests
from bs4 import BeautifulSoup


@dataclass
class CrawlConfig:
    mall: str
    seed_urls: list[str]
    max_products: int = 80
    delay_sec: float = 0.5
    timeout_sec: int = 20
    strict_images: bool = True
    verbose: bool = False


class BaseCrawler:
    domain: str = ''
    mall: str = ''
    product_link_patterns: tuple[str, ...] = tuple()
    sitemap_urls: tuple[str, ...] = tuple()

    def __init__(self, config: CrawlConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                'User-Agent': (
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/122.0.0.0 Safari/537.36'
                ),
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            }
        )

    def fetch(self, url: str) -> str:
        if self.config.verbose:
            print(f'[{self.mall}] GET {url}')
        response = self.session.get(url, timeout=self.config.timeout_sec)
        response.raise_for_status()
        return response.text

    def discover_product_links(self) -> list[str]:
        links: list[str] = []
        seen: set[str] = set()

        for sitemap in self.sitemap_urls:
            try:
                xml = self.fetch(sitemap)
            except Exception as exc:
                if self.config.verbose:
                    print(f'[{self.mall}] sitemap failed: {sitemap} ({exc})')
                continue

            soup = BeautifulSoup(xml, 'xml')
            for loc in soup.select('url > loc'):
                full = (loc.get_text(strip=True) or '').split('?')[0]
                if self.domain not in full:
                    continue
                if not any(re.search(pattern, full) for pattern in self.product_link_patterns):
                    continue
                if full in seen:
                    continue
                seen.add(full)
                links.append(full)
                if len(links) >= self.config.max_products:
                    return links

        for seed in self.config.seed_urls:
            try:
                html = self.fetch(seed)
            except Exception as exc:
                if self.config.verbose:
                    print(f'[{self.mall}] seed failed: {seed} ({exc})')
                continue

            soup = BeautifulSoup(html, 'html.parser')
            for anchor in soup.select('a[href]'):
                href = anchor.get('href', '').strip()
                if not href:
                    continue
                full = urljoin(seed, href)
                if self.domain not in full:
                    continue
                if not any(re.search(pattern, full) for pattern in self.product_link_patterns):
                    continue
                clean = full.split('?')[0]
                if clean in seen:
                    continue
                seen.add(clean)
                links.append(clean)
                if len(links) >= self.config.max_products:
                    return links

            # Some SPA pages keep product URLs in JSON/script blocks rather than anchor tags.
            for pattern in self.product_link_patterns:
                for hit in re.findall(rf'https?://{re.escape(self.domain)}[^"\'\s]*{pattern}[^"\'\s]*', html):
                    clean = hit.split('?')[0]
                    if clean in seen:
                        continue
                    seen.add(clean)
                    links.append(clean)
                    if len(links) >= self.config.max_products:
                        return links

                for hit in re.findall(rf'/{pattern.lstrip("^/")}[^"\'\s]*', html):
                    full = urljoin(seed, hit)
                    clean = full.split('?')[0]
                    if self.domain not in clean or clean in seen:
                        continue
                    seen.add(clean)
                    links.append(clean)
                    if len(links) >= self.config.max_products:
                        return links

            time.sleep(self.config.delay_sec)

        return links

    def _extract_jsonld_product(self, soup: BeautifulSoup) -> dict:
        scripts = soup.select('script[type="application/ld+json"]')
        for script in scripts:
            raw = (script.string or script.text or '').strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue

            for node in self._walk_jsonld(payload):
                if isinstance(node, dict) and str(node.get('@type', '')).lower() == 'product':
                    return node
        return {}

    def _walk_jsonld(self, obj):
        if isinstance(obj, dict):
            yield obj
            for value in obj.values():
                yield from self._walk_jsonld(value)
        elif isinstance(obj, list):
            for value in obj:
                yield from self._walk_jsonld(value)

    def _collect_notice(self, soup: BeautifulSoup) -> str:
        keywords = ('주의', '세탁', '교환', '환불', '소재', 'care', 'caution')
        text_chunks: list[str] = []
        for tag in soup.select('p,li,span,div'):
            text = ' '.join(tag.get_text(' ', strip=True).split())
            if len(text) < 10 or len(text) > 180:
                continue
            if any(k.lower() in text.lower() for k in keywords):
                text_chunks.append(text)
            if len(text_chunks) >= 3:
                break
        return ' / '.join(text_chunks)

    def _normalize_image_url(self, src: str) -> str:
        raw = (src or '').strip()
        if not raw or raw.startswith('data:'):
            return ''
        if raw.startswith('//'):
            return f'https:{raw}'
        return urljoin(f'https://{self.domain}', raw)

    def _collect_images(self, soup: BeautifulSoup, product: dict, html: str) -> tuple[str, list[str]]:
        image_urls: list[str] = []

        if isinstance(product.get('image'), str):
            image_urls.append(product['image'])
        elif isinstance(product.get('image'), list):
            image_urls.extend([u for u in product['image'] if isinstance(u, str)])

        for meta in soup.select('meta[property="og:image"], meta[name="twitter:image"], meta[property="og:image:url"]'):
            content = (meta.get('content') or '').strip()
            if content:
                image_urls.append(content)

        for img in soup.select('img[src],img[data-src],img[data-original],img[srcset],source[srcset]'):
            srcset = img.get('srcset')
            src = None
            if srcset:
                first = srcset.split(',')[0].strip().split(' ')[0]
                if first:
                    src = first
            if not src:
                src = img.get('src') or img.get('data-src') or img.get('data-original')
            if not src:
                continue
            full = self._normalize_image_url(src)
            if any(token in full.lower() for token in ('sprite', 'icon', 'logo', 'thumb')):
                continue
            if full not in image_urls:
                image_urls.append(full)
            if len(image_urls) >= 12:
                break

        for hit in re.findall(r'https?://[^"\'\s]+\.(?:jpg|jpeg|png|webp)(?:\?[^"\'\s]*)?', html, re.IGNORECASE):
            if any(token in hit.lower() for token in ('sprite', 'icon', 'logo')):
                continue
            image_urls.append(hit)
            if len(image_urls) >= 24:
                break

        cleaned: list[str] = []
        seen: set[str] = set()
        for url in image_urls:
            full = self._normalize_image_url(url)
            if not full:
                continue
            if full in seen:
                continue
            seen.add(full)
            cleaned.append(full)

        image_urls = cleaned
        main = image_urls[0] if image_urls else ''
        details = image_urls[1:9] if len(image_urls) > 1 else []
        return main, details

    def _extract_price_krw(self, product: dict, soup: BeautifulSoup) -> int:
        offers = product.get('offers', {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            for key in ('price', 'priceSpecification'):
                value = offers.get(key)
                if isinstance(value, (int, float)):
                    return int(value)
                if isinstance(value, dict) and isinstance(value.get('price'), (int, float)):
                    return int(value['price'])
                if isinstance(value, str):
                    nums = re.sub(r'[^0-9]', '', value)
                    if nums:
                        return int(nums)

        text = soup.get_text(' ', strip=True)
        m = re.search(r'([0-9]{2,3}(?:,[0-9]{3})+)\s*원', text)
        if m:
            return int(m.group(1).replace(',', ''))
        return 0

    def _safe_name(self, text: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_-]+', '_', text).strip('_').lower()[:80] or 'item'

    def _download(self, url: str, dest: Path) -> str:
        try:
            res = self.session.get(
                url,
                timeout=self.config.timeout_sec,
                headers={'Referer': f'https://{self.domain}/'},
            )
            res.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(res.content)
            return '/' + dest.relative_to(ROOT).as_posix()
        except Exception:
            return ''

    def _download_images(self, item_id: str, main: str, details: Iterable[str]) -> tuple[str, list[str]]:
        out_dir = IMG_ROOT / self.mall
        main_path = ''
        if main:
            main_path = self._download(main, out_dir / f'{item_id}_main.jpg')

        detail_paths: list[str] = []
        for idx, url in enumerate(details, start=1):
            local = self._download(url, out_dir / f'{item_id}_detail_{idx}.jpg')
            if local:
                detail_paths.append(local)

        return main_path, detail_paths

    def parse_product(self, url: str, idx: int) -> dict | None:
        html = self.fetch(url)
        soup = BeautifulSoup(html, 'html.parser')
        product = self._extract_jsonld_product(soup)

        name = str(product.get('name', '')).strip()
        if not name:
            title = soup.find('title')
            name = title.get_text(strip=True) if title else f'{self.mall} item {idx}'

        price_krw = self._extract_price_krw(product, soup)
        main, details = self._collect_images(soup, product, html)
        notice = self._collect_notice(soup)

        slug = self._safe_name(name)
        item_id = f'{self.mall}_{idx:04d}_{slug}'
        main_local, detail_local = self._download_images(item_id, main, details)

        if self.config.strict_images and not main_local:
            return None

        return {
            'id': item_id,
            'mall': self.mall,
            'name': name,
            'price_krw': int(price_krw or 0),
            'main_image': main_local or main,
            'detail_images': detail_local or details,
            'notice': notice,
            'style': '',
            'keyword': '',
            'tags': [],
            'idol_hint': '',
            'source_url': url,
        }

    def crawl(self) -> list[dict]:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        IMG_ROOT.mkdir(parents=True, exist_ok=True)
        out: list[dict] = []
        links = self.discover_product_links()

        for idx, url in enumerate(links, start=1):
            try:
                item = self.parse_product(url, idx)
                if item:
                    out.append(item)
                    if self.config.verbose:
                        print(f'[{self.mall}] ok: {item["id"]}')
                elif self.config.verbose:
                    print(f'[{self.mall}] skipped(no local main image): {url}')
            except Exception as exc:
                if self.config.verbose:
                    print(f'[{self.mall}] parse failed: {url} ({exc})')
            time.sleep(self.config.delay_sec)

        return out
