#!/usr/bin/env python3
"""
Turso DB 마이그레이션 스크립트 — 크롤링 JSON → products 테이블

사용법:
  # 1) 단일 파일
  python scripts/migrate_to_turso.py --input crawler/data/products_enriched.json

  # 2) 여러 파일 (동료 데이터 + 기존 데이터)
  python scripts/migrate_to_turso.py --input data_a.json data_b.json data_c.json

  # 3) 드라이런 (DB에 쓰지 않고 검증만)
  python scripts/migrate_to_turso.py --input data.json --dry-run

  # 4) 배치 크기 조절
  python scripts/migrate_to_turso.py --input data.json --batch-size 200

필요 환경변수 (.env 파일):
  TURSO_DATABASE_URL=libsql://your-db.turso.io
  TURSO_AUTH_TOKEN=eyJ...

의존성:
  pip install libsql python-dotenv
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ── 프로젝트 루트를 sys.path에 추가 ────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

import libsql

# ── 환경변수 ─────────────────────────────────────────────────────────
TURSO_URL   = os.getenv('TURSO_DATABASE_URL', '')
TURSO_TOKEN = os.getenv('TURSO_AUTH_TOKEN', '')

if not TURSO_URL or not TURSO_TOKEN:
    print('[ERROR] TURSO_DATABASE_URL, TURSO_AUTH_TOKEN 환경변수가 필요합니다.')
    print('        .env 파일을 확인해주세요.')
    sys.exit(1)

# ── 환율 ─────────────────────────────────────────────────────────────
JPY_RATE = float(os.getenv('JPY_RATE', '0.11'))

def krw_to_jpy(krw: int) -> int:
    return max(1, round(krw * JPY_RATE))


# ── 테이블 생성 ─────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id            TEXT PRIMARY KEY,
    mall          TEXT DEFAULT '',
    brand         TEXT DEFAULT '',
    name          TEXT NOT NULL,
    price_krw     INTEGER DEFAULT 0,
    price_jpy     INTEGER DEFAULT 0,
    main_image    TEXT DEFAULT '',
    detail_images TEXT DEFAULT '[]',
    material      TEXT DEFAULT '',
    care          TEXT DEFAULT '',
    source_url    TEXT DEFAULT '',
    category      TEXT DEFAULT '',
    sub_category  TEXT DEFAULT '',
    colors        TEXT DEFAULT '[]',
    style         TEXT DEFAULT '',
    keyword       TEXT DEFAULT '',
    tags          TEXT DEFAULT '[]',
    is_fashion    INTEGER DEFAULT 1,
    is_clothing   INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now'))
)
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)",
    "CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand)",
    "CREATE INDEX IF NOT EXISTS idx_products_price ON products(price_krw)",
    "CREATE INDEX IF NOT EXISTS idx_products_mall ON products(mall)",
]

UPSERT_SQL = """
INSERT OR REPLACE INTO products
    (id, mall, brand, name, price_krw, price_jpy,
     main_image, detail_images, material, care, source_url,
     category, sub_category, colors, style, keyword, tags,
     is_fashion, is_clothing)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


# ── JSON 로드 & 병합 ───────────────────────────────────────────────

def load_and_merge(paths: list[str]) -> list[dict]:
    """여러 JSON 파일을 로드하고 id 기준으로 중복을 제거합니다."""
    seen: dict[str, dict] = {}

    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            print(f'  [WARN] 파일 없음: {path}')
            continue

        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            print(f'  [WARN] 배열이 아닌 JSON: {path}')
            continue

        loaded = 0
        dupes = 0
        for item in data:
            pid = item.get('id', '')
            if not pid:
                continue
            if pid in seen:
                dupes += 1
            seen[pid] = item
            loaded += 1

        print(f'  ✅ {path.name}: {loaded}개 로드, {dupes}개 중복 덮어쓰기')

    products = list(seen.values())
    print(f'\n  📦 총 {len(products)}개 상품 (중복 제거 완료)\n')
    return products


# ── 데이터 검증 ─────────────────────────────────────────────────────

def validate(products: list[dict]) -> tuple[list[dict], list[str]]:
    """필수 필드 체크, price_jpy 보충. (valid, warnings) 반환."""
    valid = []
    warnings = []

    for item in products:
        pid = item.get('id', '')
        name = item.get('name', '')
        if not pid:
            warnings.append(f'id 없는 상품 스킵: name={name}')
            continue
        if not name:
            warnings.append(f'name 없는 상품: id={pid}')

        # price_jpy 보충
        if not item.get('price_jpy'):
            krw = int(item.get('price_krw', 0) or 0)
            item['price_jpy'] = krw_to_jpy(krw) if krw > 0 else 0

        valid.append(item)

    return valid, warnings


# ── 상품 → SQL 파라미터 변환 ────────────────────────────────────────

def product_to_params(item: dict) -> tuple:
    """dict → UPSERT 파라미터 tuple 변환."""
    return (
        item.get('id', ''),
        item.get('mall', ''),
        item.get('brand', ''),
        item.get('name', ''),
        int(item.get('price_krw', 0) or 0),
        int(item.get('price_jpy', 0) or 0),
        item.get('main_image', ''),
        json.dumps(item.get('detail_images', []), ensure_ascii=False),
        item.get('material', ''),
        item.get('care', ''),
        item.get('source_url', ''),
        item.get('category', ''),
        item.get('sub_category', ''),
        json.dumps(item.get('colors', []), ensure_ascii=False),
        item.get('style', ''),
        item.get('keyword', ''),
        json.dumps(item.get('tags', []), ensure_ascii=False),
        1 if item.get('is_fashion', True) else 0,
        1 if item.get('is_clothing', True) else 0,
    )


# ── 메인 마이그레이션 ──────────────────────────────────────────────

def migrate(products: list[dict], batch_size: int = 500, dry_run: bool = False):
    """products 리스트를 Turso DB에 배치 INSERT."""

    if dry_run:
        print('[DRY RUN] DB에 쓰지 않고 검증만 합니다.\n')
        for i, item in enumerate(products[:5]):
            print(f'  [{i+1}] {item["id"]} | {item.get("brand","")} | {item["name"]}')
        if len(products) > 5:
            print(f'  ... 외 {len(products)-5}개')
        print(f'\n  ✅ 총 {len(products)}개 상품이 INSERT 대상입니다.')
        return

    print(f'[DB] Turso 연결 중... {TURSO_URL[:40]}...')
    conn = libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)

    # 테이블 생성
    print('[DB] products 테이블 생성...')
    conn.execute(CREATE_TABLE_SQL)
    for idx_sql in CREATE_INDEXES_SQL:
        conn.execute(idx_sql)
    conn.commit()
    print('  ✅ 테이블 + 인덱스 생성 완료\n')

    # 배치 INSERT
    total = len(products)
    inserted = 0
    errors = 0
    start_time = time.time()

    for i in range(0, total, batch_size):
        batch = products[i:i + batch_size]
        try:
            for item in batch:
                params = product_to_params(item)
                conn.execute(UPSERT_SQL, params)
            conn.commit()
            inserted += len(batch)
        except Exception as e:
            conn.rollback()
            errors += len(batch)
            print(f'  ❌ 배치 {i//batch_size + 1} 실패: {e}')
            # 개별 재시도
            for item in batch:
                try:
                    conn.execute(UPSERT_SQL, product_to_params(item))
                    conn.commit()
                    inserted += 1
                    errors -= 1
                except Exception as e2:
                    conn.rollback()
                    print(f'     ❌ {item.get("id","?")}: {e2}')

        # 진행률
        pct = min(100, (i + len(batch)) / total * 100)
        elapsed = time.time() - start_time
        print(f'  [{pct:5.1f}%] {inserted}/{total} 완료 ({elapsed:.1f}s)', end='\r')

    elapsed = time.time() - start_time
    print(f'\n\n  ✅ 마이그레이션 완료!')
    print(f'     성공: {inserted}개')
    print(f'     실패: {errors}개')
    print(f'     소요: {elapsed:.1f}초')

    # 검증
    cur = conn.execute('SELECT COUNT(*) FROM products')
    count = cur.fetchone()[0]
    print(f'     DB 총 상품수: {count}개')

    conn.close()


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='크롤링 JSON → Turso products 테이블 마이그레이션'
    )
    parser.add_argument(
        '--input', '-i',
        nargs='+',
        required=True,
        help='입력 JSON 파일 경로 (여러 개 가능)',
    )
    parser.add_argument(
        '--batch-size', '-b',
        type=int,
        default=500,
        help='배치 크기 (기본값: 500)',
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='DB에 쓰지 않고 검증만',
    )
    args = parser.parse_args()

    print('=' * 60)
    print('  크롤링 데이터 → Turso DB 마이그레이션')
    print('=' * 60)
    print()

    # 1. 로드 & 병합
    print('[1/3] JSON 파일 로드 & 병합')
    products = load_and_merge(args.input)
    if not products:
        print('[ERROR] 로드된 상품이 없습니다.')
        sys.exit(1)

    # 2. 검증
    print('[2/3] 데이터 검증')
    valid, warnings = validate(products)
    if warnings:
        for w in warnings[:10]:
            print(f'  ⚠️  {w}')
        if len(warnings) > 10:
            print(f'  ... 외 {len(warnings)-10}개 경고')
    print(f'  ✅ {len(valid)}개 유효 상품\n')

    # 3. 마이그레이션
    print(f'[3/3] Turso DB 적재 (배치 {args.batch_size}행)')
    migrate(valid, batch_size=args.batch_size, dry_run=args.dry_run)

    print()
    print('=' * 60)
    print('  완료!')
    print('=' * 60)


if __name__ == '__main__':
    main()
