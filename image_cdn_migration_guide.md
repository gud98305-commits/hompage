# 이미지 CDN 이관 + Turso 마이그레이션 완전 가이드

## 전체 파이프라인 개요

```
Phase 0  사전 검증       → JSON ↔ 파일 정합성 확인, Turso 현재 상태 확인
Phase 1  CDN 설정        → 버킷 생성, CORS 정책, 퍼블릭 읽기 설정
Phase 2  이미지 업로드   → 체크포인트 기반 재개 가능 업로드
Phase 3  URL 치환        → 원본 보존, 별도 파일 출력, 치환 결과 검증
Phase 4  DB INSERT       → dry-run → 실제 INSERT → 결과 검증
Phase 5  배포 후 검증    → 이미지 로드, API 응답, CORS 확인
```

---

## Phase 0 — 사전 검증

### 목표
- JSON에 기록된 이미지 경로와 실제 파일 시스템이 일치하는지 확인
- Turso DB에 현재 products 데이터가 있는지 확인
- detail_images 배열 상태 파악

### 엣지케이스

| 케이스 | 위험 | 발생 원인 |
|--------|------|-----------|
| JSON 경로는 있지만 파일 없음 | 업로드 시 FileNotFoundError | 크롤링 실패로 파일 미저장 |
| 파일은 있지만 JSON에 없음 | 고아 파일로 CDN 낭비 | 크롤링 후 JSON 미갱신 |
| detail_images가 `null` 또는 빈 문자열 | 치환 로직 예외 | 크롤러 예외 처리 부재 |
| Turso에 이미 products 데이터 있음 | INSERT OR REPLACE로 기존 데이터 교체 | 이전 테스트 실행 |

### 보완책
```bash
# 검증 스크립트 실행 (승인 후 작성)
# 출력: missing_images.txt (JSON에는 있지만 파일 없는 목록)
# 출력: orphan_images.txt  (파일은 있지만 JSON에 없는 목록)
python scripts/validate_before_migrate.py \
  --json "/Users/choisinbi/Desktop/0227 test/data/products_enriched.json" \
  --images "/Users/choisinbi/Desktop/0227 test/images"
```

**체크리스트**
- [ ] missing_images.txt가 비어있거나 허용 범위 이내인지 확인
- [ ] Turso 현재 products 행 수 확인 (`SELECT COUNT(*) FROM products`)
- [ ] detail_images가 null인 상품 수 확인

---

## Phase 1 — CDN 설정

### 최선의 선택: Cloudflare R2

**선택 이유**
- Egress(다운로드) 비용 무료 — 이미지 서빙 시 트래픽 비용 없음
- 10GB/월 무료 저장 → 현재 3.4GB 이내
- AWS S3 호환 API → 기존 boto3 코드 재사용 가능
- 국내 접근 속도 양호

**대안 비교**

| 서비스 | 무료 저장 | Egress 비용 | S3 호환 | 비고 |
|--------|-----------|-------------|---------|------|
| Cloudflare R2 | 10GB | 무료 | ✅ | **추천** |
| AWS S3 | 5GB (12개월) | $0.09/GB | 기준 | 만료 후 유료 |
| Supabase Storage | 1GB | 2GB/월 | ❌ | 소규모용 |
| Railway Volume | 1GB (플랜에 따라) | 무료 | ❌ | 재시작 시 초기화 위험 |

### 엣지케이스

**CORS 미설정 → 브라우저 차단**
Railway 앱 도메인에서 CDN 이미지를 `<img src>` 로 로드하는 것은 CORS 무관이지만,
JavaScript `fetch()` 또는 CSS `background-image`에서 호출 시 CORS 헤더가 없으면 차단됩니다.

**보완책 — R2 CORS 정책 (버킷 생성 시 적용)**
```json
[
  {
    "AllowedOrigins": ["https://your-app.railway.app", "http://localhost:*"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 86400
  }
]
```

**퍼블릭 접근 미설정 → 이미지 로드 불가**
R2 버킷 기본값은 비공개입니다.
→ 버킷 설정에서 "Public Access" 활성화 또는 커스텀 도메인 연결 필수.

**URL 포맷 결정 필수 (Phase 3 시작 전)**
업로드 후 이미지 URL이 어떤 형태인지 Phase 3 전에 확정해야 합니다.
```
# R2 퍼블릭 URL 예시
https://pub-xxxx.r2.dev/musinsa/musinsa_6013679_main.jpg

# 커스텀 도메인 연결 시
https://cdn.yourdomain.com/musinsa/musinsa_6013679_main.jpg
```

**체크리스트**
- [ ] R2 버킷 생성 완료
- [ ] CORS 정책 적용 완료
- [ ] 퍼블릭 접근 활성화 완료
- [ ] 테스트 이미지 1개 업로드 후 URL 접근 확인 (HTTP 200)
- [ ] URL 포맷 확정 후 Phase 3 진행

---

## Phase 2 — 이미지 업로드

### 핵심 원칙: 체크포인트 기반 재개 가능 업로드

3.4GB 업로드 중 중단 시 처음부터 재시작하는 것을 방지합니다.

```
upload_progress.json  ← 완료된 파일 목록 기록
업로드 재실행 시 → 이미 완료된 파일 스킵 → 미완료만 업로드
```

### 엣지케이스

| 케이스 | 위험 | 보완책 |
|--------|------|--------|
| 업로드 중 네트워크 단절 | 부분 업로드, 이후 추적 불가 | 체크포인트 파일로 완료 목록 기록 |
| CDN Rate Limit | 429 에러로 일부 실패 | 지수 백오프(Exponential Backoff) 재시도 |
| 로컬 경로 → CDN 경로 불일치 | 치환 시 경로 매핑 실패 | 업로드 시 원본경로→CDN URL 매핑 테이블 생성 |
| 동일 파일명 다른 상품 | CDN에서 덮어쓰기 | id 기반 경로 구조 사용 (`/musinsa/<id>/main.jpg`) |
| 이미지 파일 손상 | CDN에 깨진 파일 업로드 | 업로드 전 파일 크기 0 체크 |

### 업로드 전략 (승인 후 구현)

```python
# 핵심 로직 개요 (실제 코드는 승인 후 작성)

# 1. 체크포인트 파일 로드 (없으면 빈 dict)
completed = load_checkpoint('upload_progress.json')

# 2. JSON에서 모든 이미지 경로 추출 (main + detail 모두)
all_images = extract_all_image_paths('products_enriched.json')

# 3. 미완료 파일만 업로드
for local_path in all_images:
    if local_path in completed:
        continue  # 스킵
    cdn_url = upload_to_r2(local_path)
    completed[local_path] = cdn_url
    save_checkpoint('upload_progress.json', completed)

# 4. 결과: upload_progress.json = { "/images/musinsa/xxx.jpg": "https://cdn.../xxx.jpg" }
```

**주의: `detail_images` 배열 내부 경로도 추출 대상**
```python
# main_image: 1개 경로
# detail_images: 배열 → 항목별 개별 추출 필요
# null, [], "" 예외 처리 필수
```

**체크리스트**
- [ ] 업로드 전 Phase 0 검증 완료 확인
- [ ] 체크포인트 파일 위치 결정
- [ ] 업로드 완료 후 `upload_progress.json` 총 항목 수 확인
- [ ] 샘플 5개 URL 브라우저에서 직접 접근 확인

---

## Phase 3 — URL 치환

### 핵심 원칙: 원본 절대 보존

```
products_enriched.json     ← 절대 수정 금지 (원본)
        ↓
products_for_turso.json    ← 치환 결과 출력 (새 파일)
```

### 엣지케이스

| 케이스 | 위험 | 보완책 |
|--------|------|--------|
| 원본 JSON 덮어쓰기 | 로컬 경로 복구 불가 | 항상 별도 파일 출력 |
| detail_images 일부 항목 치환 누락 | CDN URL과 로컬 경로 혼재 | 항목별 치환 + 치환 후 로컬 경로 잔존 여부 검증 |
| upload_progress.json에 없는 경로 | 치환 불가 → 로컬 경로 유지 | 미매핑 경로 목록 출력 후 중단 |
| 치환된 URL이 실제 접근 불가 | DB에 깨진 URL 저장 | 치환 후 샘플 10개 HTTP 200 확인 |

### 치환 검증 방법 (치환 후 필수 실행)

```bash
# 1. 로컬 경로 잔존 여부 확인 (0이어야 정상)
python -c "
import json
data = json.load(open('products_for_turso.json', encoding='utf-8'))
local = [p for item in data for p in ([item.get('main_image','')] +
         item.get('detail_images', [])) if isinstance(p, str) and p.startswith('/images/')]
print(f'로컬 경로 잔존: {len(local)}건')
if local: print('예시:', local[:3])
"

# 2. 샘플 URL 접근 확인
python -c "
import json, urllib.request
data = json.load(open('products_for_turso.json', encoding='utf-8'))
urls = [item['main_image'] for item in data[:10] if item.get('main_image')]
for url in urls:
    try:
        code = urllib.request.urlopen(url, timeout=5).getcode()
        print(f'  {code} {url[:60]}')
    except Exception as e:
        print(f'  FAIL {url[:60]} → {e}')
"
```

**체크리스트**
- [ ] `products_enriched.json` 수정 금지 확인
- [ ] `products_for_turso.json` 생성 확인
- [ ] 로컬 경로 잔존 0건 확인
- [ ] 샘플 URL 10개 HTTP 200 확인
- [ ] 치환 전후 상품 수 일치 확인

---

## Phase 4 — Turso DB INSERT

### 엣지케이스

| 케이스 | 위험 | 보완책 |
|--------|------|--------|
| 기존 products 데이터 존재 | INSERT OR REPLACE로 교체 | INSERT 전 현재 행 수 확인 후 명시적 동의 |
| detail_images 배열이 매우 커 row 크기 초과 | Turso HTTP 페이로드 제한 | batch_size 100으로 줄여서 실행 |
| 네트워크 중단 | 일부만 INSERT된 불완전 상태 | INSERT OR REPLACE이므로 재실행 안전 |
| `name` 필드 빈 값 (NOT NULL 제약) | INSERT 에러 | Phase 0에서 사전 검증 |

### 권장 실행 순서

```bash
# 1. 현재 Turso 상태 확인
python -c "
import os; from dotenv import load_dotenv; load_dotenv()
import libsql
conn = libsql.connect(os.getenv('TURSO_DATABASE_URL'), auth_token=os.getenv('TURSO_AUTH_TOKEN'))
try:
    n = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    print(f'현재 products 행 수: {n}')
except:
    print('products 테이블 없음 (정상)')
conn.close()
"

# 2. dry-run (스키마 검증 포함)
python scripts/migrate_to_turso.py \
  --input products_for_turso.json \
  --dry-run

# 3. 실제 INSERT (배치 100)
python scripts/migrate_to_turso.py \
  --input products_for_turso.json \
  --batch-size 100
```

**체크리스트**
- [ ] dry-run 경고 0건 확인
- [ ] 실제 INSERT 완료 후 DB 총 행 수 = JSON 상품 수 일치
- [ ] Turso 대시보드에서 샘플 5행 직접 확인

---

## Phase 5 — 배포 후 검증

### 엣지케이스

| 케이스 | 위험 | 보완책 |
|--------|------|--------|
| `_USE_DB` 캐시로 JSON fallback 유지 | 배포 직후 DB 데이터가 안 보임 | 앱 재시작 또는 5분 대기 후 확인 |
| CORS 에러 (JS fetch 사용 시) | 이미지 일부 로드 실패 | 브라우저 콘솔 Network 탭 확인 |
| Railway 환경변수 미설정 | 앱 시작 시 RuntimeError | Railway 대시보드 Variables 확인 |
| CDN 퍼블릭 접근이 배포 후 막힘 | 전체 이미지 로드 실패 | 배포 직후 이미지 URL 직접 접근 테스트 |

### 검증 엔드포인트

```bash
# 상품 목록 응답 확인
curl https://your-app.railway.app/api/products | python3 -m json.tool | head -50

# 단일 상품 확인 (이미지 URL이 CDN URL인지 검증)
curl https://your-app.railway.app/api/products/musinsa_6013679
```

**체크리스트**
- [ ] `/api/products` 응답에서 `main_image`가 CDN URL인지 확인
- [ ] 브라우저에서 상품 카드 이미지 로드 확인
- [ ] 브라우저 콘솔 CORS 에러 없는지 확인
- [ ] Railway 로그에서 `[DATA] Turso products 테이블 사용` 메시지 확인

---

## 알려진 미해결 약점

### 1. `price_jpy` 환율 고착
현재 `.env`의 `JPY_RATE` 기준으로 계산된 값이 DB에 고정됩니다.
환율 변동 시 일괄 UPDATE가 필요합니다.
```sql
-- 환율 업데이트 시 실행할 SQL (향후)
UPDATE products SET price_jpy = ROUND(price_krw * 0.XX) WHERE price_krw > 0;
```

### 2. 이미지 추가 크롤링 시 파이프라인 재실행 필요
새 상품 크롤링 후 이미지를 CDN에 올리고 JSON을 업데이트하고 DB에 UPSERT하는 전체 파이프라인을 다시 돌려야 합니다. 현재는 수동 프로세스입니다.

### 3. CDN 이미지 삭제/갱신 수단 없음
상품이 DB에서 삭제되어도 CDN의 이미지 파일은 그대로 남습니다. 스토리지 낭비가 누적될 수 있습니다.

---

## 실행 순서 요약

```
[사전 확인]
  □ Phase 0: validate_before_migrate.py 실행 → 정합성 확인
  □ Phase 1: R2 버킷 생성 + CORS + 퍼블릭 + URL 포맷 확정

[작업 실행]
  □ Phase 2: 이미지 업로드 (체크포인트 기반)
  □ Phase 3: URL 치환 → products_for_turso.json 생성 + 검증
  □ Phase 4: dry-run → INSERT → DB 행 수 검증

[배포]
  □ Phase 5: Railway 배포 → 이미지/API 검증
```
