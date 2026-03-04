from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

try:
    from data_enrichment import enrich as enrich_products
    _ENRICH_AVAILABLE = True
except Exception:
    _ENRICH_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / 'data'
RAW_PATH = DATA_DIR / 'products_raw.json'
ENRICHED_PATH = DATA_DIR / 'products_enriched.json'

# ── Turso 연결 (products 테이블이 있으면 사용) ─────────────────────────
_USE_DB: Optional[bool] = None   # None = 아직 체크 안 함


def _check_db_available() -> bool:
    """Turso products 테이블에 데이터가 있는지 확인."""
    global _USE_DB
    if _USE_DB is not None:
        return _USE_DB

    try:
        from backend.services.turso_db import _get_connection
        conn = _get_connection()
        cur = conn.execute('SELECT COUNT(*) FROM products')
        count = cur.fetchone()[0]
        conn.close()
        _USE_DB = count > 0
        if _USE_DB:
            print(f'[DATA] Turso products 테이블 사용 ({count}개 상품)')
        else:
            print('[DATA] Turso products 비어있음 → JSON fallback')
    except Exception:
        _USE_DB = False
        print('[DATA] Turso products 접근 불가 → JSON fallback')

    return _USE_DB


def _load_from_db() -> list[dict]:
    """Turso products 테이블에서 전체 상품을 로드."""
    from backend.services.turso_db import _get_connection
    conn = _get_connection()
    cur = conn.execute('SELECT * FROM products')
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    conn.close()

    products = []
    for row in rows:
        item = dict(zip(columns, row))
        # JSON 문자열 필드 → 파이썬 리스트로 파싱
        for key in ('detail_images', 'colors', 'tags'):
            val = item.get(key)
            if isinstance(val, str):
                try:
                    item[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    item[key] = []
        # 정수 → 불리언
        item['is_fashion'] = bool(item.get('is_fashion', 1))
        item['is_clothing'] = bool(item.get('is_clothing', 1))
        products.append(item)

    return products


def _find_from_db(product_id: str) -> dict | None:
    """Turso에서 단일 상품 조회."""
    from backend.services.turso_db import _get_connection
    conn = _get_connection()
    cur = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    columns = [desc[0] for desc in cur.description]
    item = dict(zip(columns, row))
    conn.close()

    for key in ('detail_images', 'colors', 'tags'):
        val = item.get(key)
        if isinstance(val, str):
            try:
                item[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                item[key] = []
    item['is_fashion'] = bool(item.get('is_fashion', 1))
    item['is_clothing'] = bool(item.get('is_clothing', 1))
    return item


# ── JSON fallback (기존 로직) ─────────────────────────────────────────

_CACHE_SIG: tuple[int, int] | None = None
_CACHE_PRODUCTS: list[dict] | None = None


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return []


def _mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except Exception:
        return 0


def _looks_enriched(products: list[dict]) -> bool:
    if not products:
        return True
    sample = products[: min(len(products), 20)]
    required = ('category', 'colors', 'is_clothing')
    return all(all(key in item for key in required) for item in sample)


def _save_json(path: Path, items: list[dict]) -> None:
    try:
        path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
    except Exception:
        pass


def _load_from_json() -> list[dict]:
    """기존 JSON 파일 기반 로드 로직 (fallback)."""
    global _CACHE_SIG, _CACHE_PRODUCTS

    raw_mtime = _mtime_ns(RAW_PATH)
    enriched_mtime = _mtime_ns(ENRICHED_PATH)
    sig = (raw_mtime, enriched_mtime)
    if _CACHE_SIG == sig and _CACHE_PRODUCTS is not None:
        return _CACHE_PRODUCTS

    if ENRICHED_PATH.exists() and enriched_mtime >= raw_mtime:
        enriched = _load_json(ENRICHED_PATH)
        if _looks_enriched(enriched):
            products = enriched
        else:
            raw = _load_json(RAW_PATH)
            if raw and _ENRICH_AVAILABLE:
                try:
                    products = enrich_products(raw)
                    _save_json(ENRICHED_PATH, products)
                except Exception:
                    products = raw
            else:
                products = raw
    else:
        raw = _load_json(RAW_PATH)
        if raw and _ENRICH_AVAILABLE:
            try:
                products = enrich_products(raw)
                _save_json(ENRICHED_PATH, products)
            except Exception:
                products = raw
        else:
            products = raw

    _CACHE_SIG = sig
    _CACHE_PRODUCTS = products
    return products


# ── 공개 API (기존과 동일한 인터페이스) ────────────────────────────────

def load_products() -> list[dict]:
    """상품 목록 로드. Turso에 데이터가 있으면 DB, 없으면 JSON fallback."""
    if _check_db_available():
        return _load_from_db()
    return _load_from_json()


def find_product(product_id: str) -> dict | None:
    """단일 상품 조회. Turso 우선, 없으면 JSON fallback."""
    if _check_db_available():
        return _find_from_db(product_id)
    for item in load_products():
        if item.get('id') == product_id:
            return item
    return None
