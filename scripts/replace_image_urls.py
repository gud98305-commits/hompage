#!/usr/bin/env python3
"""
이미지 URL 치환 스크립트

- upload_progress.json 매핑으로 로컬 경로 → R2 CDN URL 치환
- 원본 products_enriched.json 절대 수정 안 함
- 매핑에 없는 경로(누락 36개) → "" 처리 (로컬 경로 DB 적재 방지)
- detail_images 빈 문자열 항목 제거
- 치환 후 로컬 경로 잔존 여부 검증
- 출력: scripts/products_for_turso.json

사용법:
  python scripts/replace_image_urls.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

JSON_PATH   = Path('/Users/choisinbi/Desktop/0227 test/data/products_enriched.json')
CHECKPOINT  = Path(__file__).parent / 'upload_progress.json'
OUTPUT_PATH = Path(__file__).parent / 'products_for_turso.json'


def replace_path(path: str, mapping: dict[str, str]) -> str:
    """
    로컬 경로 → CDN URL 치환.
    - 매핑에 없는 로컬 경로 → "" (쓰레기값 DB 적재 방지)
    - 이미 URL이면 그대로 반환
    - None / 빈값 → ""
    """
    if not path or not isinstance(path, str):
        return ''
    if path.startswith('/images/'):
        return mapping.get(path, '')   # 누락 → "" 명시적 처리
    return path                         # 이미 CDN URL이면 그대로


def main():
    print('=' * 60)
    print('  이미지 URL 치환')
    print('=' * 60)

    # 1. 체크포인트 로드
    if not CHECKPOINT.exists():
        print(f'[ERROR] {CHECKPOINT} 없음.')
        print('        upload_to_r2.py 를 먼저 실행하세요.')
        sys.exit(1)

    mapping: dict[str, str] = json.loads(CHECKPOINT.read_text(encoding='utf-8'))
    print(f'\n  매핑 로드: {len(mapping)}개')

    # 2. 원본 JSON 로드
    data: list[dict] = json.loads(JSON_PATH.read_text(encoding='utf-8'))
    print(f'  상품 수  : {len(data)}개')

    # 3. 치환
    main_replaced:   int = 0
    main_missing:    int = 0
    detail_replaced: int = 0
    detail_missing:  int = 0
    detail_removed:  int = 0

    for item in data:
        # main_image
        mi = item.get('main_image', '')
        new_mi = replace_path(mi, mapping)
        if mi.startswith('/images/'):
            if new_mi:
                main_replaced += 1  # type: ignore[operator]
            else:
                main_missing += 1  # type: ignore[operator]
        item['main_image'] = new_mi

        # detail_images
        new_details = []
        for d in item.get('detail_images', []):
            new_d = replace_path(d, mapping)
            if isinstance(d, str) and d.startswith('/images/'):
                if new_d:
                    detail_replaced += 1  # type: ignore[operator]
                else:
                    detail_missing += 1  # type: ignore[operator]
            if new_d:                       # 빈 문자열 항목 제거
                new_details.append(new_d)
            else:
                detail_removed += 1  # type: ignore[operator]
        item['detail_images'] = new_details

    # 4. 검증 — 로컬 경로 잔존 확인
    local_remaining = sum(
        1
        for item in data
        for path in ([item.get('main_image', '')] + item.get('detail_images', []))
        if isinstance(path, str) and path.startswith('/images/')
    )

    # URL 길이 통계 (한글 인코딩 폭주 감지)
    # Turso는 TEXT 타입으로 길이 제한 없음 — 단, 비정상 케이스 로깅
    URL_WARN_LEN = 500
    all_urls = [
        path
        for item in data
        for path in ([item.get('main_image', '')] + item.get('detail_images', []))
        if isinstance(path, str) and path.startswith('http')
    ]
    long_urls = [u for u in all_urls if len(u) > URL_WARN_LEN]
    max_url_len = max((len(u) for u in all_urls), default=0)

    print(f'\n  [main_image]')
    print(f'    치환 성공  : {main_replaced}개')
    print(f'    빈값 처리  : {main_missing}개  (파일 없어 누락)')
    print(f'\n  [detail_images]')
    print(f'    치환 성공  : {detail_replaced}개')
    print(f'    빈값 처리  : {detail_missing}개  (파일 없어 누락)')
    print(f'    빈항목 제거: {detail_removed}개')
    print(f'\n  [URL 길이]  최대: {max_url_len}자  |  {URL_WARN_LEN}자 초과: {len(long_urls)}개')
    if long_urls:
        print(f'    예시: {long_urls[0]}')

    if local_remaining > 0:
        print(f'\n  ⚠️  로컬 경로 잔존: {local_remaining}개 — 확인 필요!')
    else:
        print(f'\n  ✅ 로컬 경로 잔존: 0개')

    # 캐시 버스팅 안내
    # 현재는 1회성 초기 마이그레이션이므로 문제없음.
    # 향후 이미지 재업로드 시: 동일 파일명으로 R2 덮어쓰면 Cloudflare Edge Cache가
    # 최대 수일간 구버전을 서빙할 수 있음.
    # 대응: 파일명에 타임스탬프/해시 추가 (예: musinsa_123_main_1709532100.jpg)

    # 5. 출력
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f'\n  출력 파일: {OUTPUT_PATH}')
    print(f'  상품 수  : {len(data)}개')
    print('\n다음 단계:')
    print(f'  python scripts/migrate_to_turso.py --input {OUTPUT_PATH} --dry-run')
    print(f'  python scripts/migrate_to_turso.py --input {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
