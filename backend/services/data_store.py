from __future__ import annotations

import json
from pathlib import Path

try:
    from data_enrichment import enrich as enrich_products
    _ENRICH_AVAILABLE = True
except Exception:
    _ENRICH_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / 'data'
RAW_PATH = DATA_DIR / 'products_raw.json'
ENRICHED_PATH = DATA_DIR / 'products_enriched.json'

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


def load_products() -> list[dict]:
    global _CACHE_SIG, _CACHE_PRODUCTS

    raw_mtime = _mtime_ns(RAW_PATH)
    enriched_mtime = _mtime_ns(ENRICHED_PATH)
    sig = (raw_mtime, enriched_mtime)
    if _CACHE_SIG == sig and _CACHE_PRODUCTS is not None:
        return _CACHE_PRODUCTS

    # enriched가 raw보다 최신이거나 동일하면 enriched 우선 사용
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
                # stale enriched 방지: raw가 더 최신이면 메모리에서 즉시 재추출
                products = enrich_products(raw)
                _save_json(ENRICHED_PATH, products)
            except Exception:
                products = raw
        else:
            products = raw

    _CACHE_SIG = sig
    _CACHE_PRODUCTS = products
    return products


def find_product(product_id: str) -> dict | None:
    for item in load_products():
        if item.get('id') == product_id:
            return item
    return None
