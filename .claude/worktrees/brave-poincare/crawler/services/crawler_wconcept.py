from __future__ import annotations

from crawler.services.crawler_common import BaseCrawler


class WConceptCrawler(BaseCrawler):
    domain = 'wconcept.co.kr'
    mall = 'wconcept'
    sitemap_urls = (
        'https://www.wconcept.co.kr/sitemap.xml',
    )
    product_link_patterns = (
        r'/Product/',
        r'/products/',
        r'/product/',
        r'/goods/',
    )
