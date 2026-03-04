from __future__ import annotations

from crawler.services.crawler_common import BaseCrawler


class TwentyNineCrawler(BaseCrawler):
    domain = '29cm.co.kr'
    mall = '29cm'
    sitemap_urls = (
        'https://www.29cm.co.kr/sitemap.xml',
    )
    product_link_patterns = (
        r'/catalog/',
        r'/products/',
        r'/product/',
    )
