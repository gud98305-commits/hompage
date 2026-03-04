"""
pipeline.py — SEOULFIT 크롤링 파이프라인 코어

wconcept / 29cm API 직접 호출 방식의 대량 수집.
Playwright 없이 requests로 동작합니다.
"""
from __future__ import annotations

import sys
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

import requests

# ─── W컨셉 카테고리 ──────────────────────────────────────────────────────────
WCONCEPT_CATEGORIES: list[dict] = [
    {"code": "10201", "name": "상의"},
    {"code": "10202", "name": "하의"},
    {"code": "10203", "name": "아우터"},
    {"code": "10204", "name": "원피스/스커트"},
]

WCONCEPT_API = (
    "https://display.wconcept.co.kr/display/api/best/v1/product"
    "?displayCategoryType={code}&gnbType=Y&page={page}&size=100"
)

# ─── 29cm 카테고리 ───────────────────────────────────────────────────────────
CM29_CATEGORIES: list[dict] = [
    {"code": "268100100", "name": "상의"},
    {"code": "268100200", "name": "하의"},
    {"code": "268100300", "name": "아우터"},
    {"code": "268100400", "name": "원피스/스커트"},
]

CM29_API = (
    "https://api.29cm.co.kr/api/categories/{code}/items"
    "?sort=RECOMMENDED&size=100&page={page}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


# ─── W컨셉 수집 ──────────────────────────────────────────────────────────────

def _fetch_wconcept_page(category_code: str, page: int) -> list[dict]:
    url = WCONCEPT_API.format(code=category_code, page=page)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        products = data.get("data", {}).get("list", []) or data.get("list", [])
        return products
    except Exception as e:
        print(f"  [wconcept] 페이지 {page} 오류: {e}")
        return []


def _normalize_wconcept(raw: dict, category_name: str) -> dict:
    item_no = str(raw.get("itemNo") or raw.get("itemCd") or "")
    return {
        "id": f"wconcept-{item_no}",
        "mall": "wconcept",
        "name": raw.get("itemName", ""),
        "brand": raw.get("brandName", ""),
        "category": _map_category(category_name),
        "price_krw": int(raw.get("price", 0) or 0),
        "image_url": raw.get("itemImageUrl", "") or raw.get("imgUrl", ""),
        "source_url": f"https://www.wconcept.co.kr/Product/{item_no}",
        "item_cd": item_no,
        "is_clothing": True,
    }


def collect_wconcept(limit: int) -> list[dict]:
    limit_per_cat = max(limit // len(WCONCEPT_CATEGORIES), 100)
    all_items: list[dict] = []

    for cat in WCONCEPT_CATEGORIES:
        collected = 0
        page = 0
        print(f"  [wconcept/{cat['name']}] 수집 시작 (목표: {limit_per_cat}개)")
        while collected < limit_per_cat:
            items = _fetch_wconcept_page(cat["code"], page)
            if not items:
                break
            normalized = [_normalize_wconcept(p, cat["name"]) for p in items]
            all_items.extend(normalized)
            collected += len(normalized)
            print(f"    페이지 {page} → {len(normalized)}개 (누계 {collected}개)")
            page += 1
            time.sleep(0.3)

    return all_items


# ─── 29cm 수집 ───────────────────────────────────────────────────────────────

def _fetch_29cm_page(category_code: str, page: int) -> list[dict]:
    url = CM29_API.format(code=category_code, page=page)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return (
            data.get("data", {}).get("list", [])
            or data.get("list", [])
            or data.get("items", [])
        )
    except Exception as e:
        print(f"  [29cm] 페이지 {page} 오류: {e}")
        return []


def _normalize_29cm(raw: dict, category_name: str) -> dict:
    item_id = str(raw.get("itemNo") or raw.get("id") or raw.get("productNo") or "")
    return {
        "id": f"29cm-{item_id}",
        "mall": "29cm",
        "name": raw.get("itemName", "") or raw.get("name", ""),
        "brand": raw.get("brandName", "") or raw.get("brand", ""),
        "category": _map_category(category_name),
        "price_krw": int(raw.get("salePrice", 0) or raw.get("price", 0) or 0),
        "image_url": raw.get("listImageUrl", "") or raw.get("imageUrl", ""),
        "source_url": f"https://www.29cm.co.kr/catalog/{item_id}",
        "is_clothing": True,
    }


def collect_29cm(limit: int) -> list[dict]:
    limit_per_cat = max(limit // len(CM29_CATEGORIES), 100)
    all_items: list[dict] = []

    for cat in CM29_CATEGORIES:
        collected = 0
        page = 0
        print(f"  [29cm/{cat['name']}] 수집 시작 (목표: {limit_per_cat}개)")
        while collected < limit_per_cat:
            items = _fetch_29cm_page(cat["code"], page)
            if not items:
                break
            normalized = [_normalize_29cm(p, cat["name"]) for p in items]
            all_items.extend(normalized)
            collected += len(normalized)
            print(f"    페이지 {page} → {len(normalized)}개 (누계 {collected}개)")
            page += 1
            time.sleep(0.3)

    return all_items


# ─── 카테고리 매핑 ────────────────────────────────────────────────────────────

def _map_category(category_name: str) -> str:
    mapping = {
        "상의": "top",
        "하의": "bottom",
        "아우터": "outer",
        "원피스": "dress",
        "원피스/스커트": "dress",
    }
    return mapping.get(category_name, "top")


# ─── 메인 실행 ────────────────────────────────────────────────────────────────

def run_bulk_crawl(mall: str, limit: int) -> list[dict]:
    """mall: 'wconcept' | '29cm'"""
    if mall == "wconcept":
        return collect_wconcept(limit)
    elif mall == "29cm":
        return collect_29cm(limit)
    else:
        raise ValueError(f"지원하지 않는 mall: {mall}. 'wconcept' 또는 '29cm' 사용")
