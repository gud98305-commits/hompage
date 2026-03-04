#!/usr/bin/env python3
"""
R2 이미지 업로드 스크립트

보완 항목:
  - Content-Type(MIME) 명시 — 브라우저 강제 다운로드 방지
  - ThreadPoolExecutor 병렬 업로드 — 순차 업로드 병목 해소
  - URL 인코딩 — 한글/공백/특수문자 파일명 처리
  - 체크포인트 Atomic write — 셧다운/강제종료 시 파일 손상 방지
  - 체크포인트 기반 재개 — 중단 후 완료분 스킵
  - adaptive 재시도 — R2 Rate Limit / Timeout 대응

사용법:
  python scripts/upload_to_r2.py

필요 환경변수 (.env):
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
  R2_BUCKET_NAME, R2_PUBLIC_URL
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

import boto3
from botocore.config import Config

# ── 설정 ──────────────────────────────────────────────────────────────

R2_ACCOUNT_ID    = os.getenv('R2_ACCOUNT_ID', '')
R2_ACCESS_KEY_ID = os.getenv('R2_ACCESS_KEY_ID', '')
R2_SECRET_KEY    = os.getenv('R2_SECRET_ACCESS_KEY', '')
R2_BUCKET        = os.getenv('R2_BUCKET_NAME', '')
R2_PUBLIC_URL    = os.getenv('R2_PUBLIC_URL', '').rstrip('/')

IMAGES_DIR    = Path('/Users/choisinbi/Desktop/0227 test/images')
JSON_PATH     = Path('/Users/choisinbi/Desktop/0227 test/data/products_enriched.json')
CHECKPOINT    = Path(__file__).parent / 'upload_progress.json'
MISSING_LOG   = Path(__file__).parent / 'missing_images.txt'

MAX_WORKERS   = 16
SAVE_INTERVAL = 100  # N개 업로드마다 체크포인트 저장

# ── 환경변수 검증 ─────────────────────────────────────────────────────

for _name, _val in [
    ('R2_ACCOUNT_ID',       R2_ACCOUNT_ID),
    ('R2_ACCESS_KEY_ID',    R2_ACCESS_KEY_ID),
    ('R2_SECRET_ACCESS_KEY', R2_SECRET_KEY),
    ('R2_BUCKET_NAME',      R2_BUCKET),
    ('R2_PUBLIC_URL',       R2_PUBLIC_URL),
]:
    if not _val:
        print(f'[ERROR] {_name} 환경변수가 없습니다. .env를 확인하세요.')
        sys.exit(1)

# ── 스레드별 boto3 클라이언트 ─────────────────────────────────────────
# boto3 클라이언트는 스레드 안전하지 않음 → threading.local()로 스레드별 독립 인스턴스 생성

_thread_local = threading.local()

def _get_client():
    if not hasattr(_thread_local, 'client'):
        _thread_local.client = boto3.client(
            's3',
            endpoint_url=f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_KEY,
            region_name='auto',
            config=Config(
                retries={'max_attempts': 8, 'mode': 'adaptive'},  # Rate Limit / Timeout 대응
                connect_timeout=10,
                read_timeout=30,
            ),
        )
    return _thread_local.client


# ── 경로 변환 유틸 ────────────────────────────────────────────────────

def local_to_r2_key(local_path: str) -> str:
    """/images/musinsa/xxx.jpg → musinsa/xxx.jpg"""
    p = local_path.lstrip('/')
    if p.startswith('images/'):
        p = p[len('images/'):]
    return p


def local_to_cdn_url(local_path: str) -> str:
    key = local_to_r2_key(local_path)
    # 한글, 공백, 특수문자 URL 인코딩 ('/' 는 경로 구분자이므로 유지)
    encoded = quote(key, safe='/')
    return f'{R2_PUBLIC_URL}/{encoded}'


# ── JSON 이미지 경로 추출 ─────────────────────────────────────────────

def extract_image_paths(json_path: Path) -> list[str]:
    data = json.loads(json_path.read_text(encoding='utf-8'))
    paths: set[str] = set()
    for item in data:
        mi = item.get('main_image', '')
        if mi and isinstance(mi, str):
            paths.add(mi)
        for d in item.get('detail_images', []):
            if d and isinstance(d, str):
                paths.add(d)
    return list(paths)


# ── 체크포인트 ────────────────────────────────────────────────────────

def load_checkpoint() -> dict[str, str]:
    if CHECKPOINT.exists():
        try:
            return json.loads(CHECKPOINT.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def _write_checkpoint(mapping: dict) -> None:
    """
    Atomic write — 셧다운/강제종료 시 체크포인트 파일 손상 방지.
    임시 파일에 먼저 쓴 뒤 os.replace()로 바꿔치기 (원자적 교체).
    락 보유 중에 호출할 것.
    """
    tmp = CHECKPOINT.with_suffix('.tmp')
    tmp.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    os.replace(tmp, CHECKPOINT)  # 원자적 교체 — 중간 상태 없음


# ── 단일 파일 업로드 ──────────────────────────────────────────────────

def upload_one(
    local_path: str,
    mapping: dict,
    lock: threading.Lock,
    counter: list,        # [int] — 락 안에서만 변경
    missing: list,        # list.append는 GIL이 보호 (CPython)
) -> bool:
    """
    단일 파일 업로드.
    반환: True(성공) / False(업로드 실패) / None처럼 동작(파일 없음은 missing에 기록)
    """
    rel = local_path.lstrip('/')
    if rel.startswith('images/'):
        rel = rel[len('images/'):]
    file_path = IMAGES_DIR / rel

    # 파일 존재 여부 확인
    if not file_path.exists():
        missing.append(local_path)
        return False

    r2_key  = local_to_r2_key(local_path)
    cdn_url = local_to_cdn_url(local_path)

    # MIME 타입 자동 감지 — 누락 시 image/jpeg fallback
    mime, _ = mimetypes.guess_type(str(file_path))
    if not mime or not mime.startswith('image/'):
        mime = 'image/jpeg'

    try:
        _get_client().upload_file(
            str(file_path),
            R2_BUCKET,
            r2_key,
            ExtraArgs={'ContentType': mime},
        )
    except Exception as e:
        print(f'\n  [FAIL] {local_path}: {e}')
        return False

    with lock:
        mapping[local_path] = cdn_url
        counter[0] += 1
        if counter[0] % SAVE_INTERVAL == 0:
            _write_checkpoint(mapping)

    return True


# ── 메인 ─────────────────────────────────────────────────────────────

def main():
    print('=' * 60)
    print('  R2 이미지 업로드')
    print('=' * 60)

    # 1. 경로 추출
    print('\n[1/3] JSON 이미지 경로 추출...')
    all_paths = extract_image_paths(JSON_PATH)
    print(f'  총 {len(all_paths)}개')

    # 2. 체크포인트 로드
    mapping = load_checkpoint()
    already = len(mapping)
    todo    = [p for p in all_paths if p not in mapping]
    print(f'  완료(재개): {already}개 | 남은 대상: {len(todo)}개')

    if not todo:
        print('\n  ✅ 모든 파일이 이미 업로드되어 있습니다.')
        print(f'  체크포인트: {CHECKPOINT}')
        return

    # 3. 병렬 업로드
    print(f'\n[2/3] 업로드 시작 (병렬 워커: {MAX_WORKERS}개)...\n')
    lock    = threading.Lock()
    counter = [0]
    missing: list[str] = []
    errors: int = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(upload_one, path, mapping, lock, counter, missing): path
            for path in todo
        }
        total = len(futures)
        done  = 0

        for future in as_completed(futures):
            done += 1
            success = future.result()
            if not success and futures[future] not in missing:
                errors = errors + 1  # type: ignore[operator]
            pct = done / total * 100
            print(f'  [{pct:5.1f}%] {done}/{total}  성공:{counter[0]}  누락:{len(missing)}  오류:{errors}',
                  end='\r')

    # 최종 저장
    with lock:
        _write_checkpoint(mapping)

    # 결과
    print(f'\n\n[3/3] 완료')
    print(f'  업로드 성공 : {counter[0]}개')
    print(f'  파일 없음   : {len(missing)}개')
    print(f'  업로드 오류 : {errors}개')
    print(f'  체크포인트  : {CHECKPOINT}')

    if missing:
        MISSING_LOG.write_text('\n'.join(missing), encoding='utf-8')
        print(f'  누락 목록   : {MISSING_LOG}')


if __name__ == '__main__':
    main()
