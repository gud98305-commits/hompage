# 크롤링 데이터 → Turso 마이그레이션 가이드

## 📌 배포 vs 마이그레이션 순서

**마이그레이션 먼저 → 배포** 가 맞습니다.

```
[1] 동료 컴퓨터에서 마이그레이션 스크립트 실행 → Turso에 products 데이터 적재
[2] 데이터 확인 (Turso 대시보드에서 products 테이블 확인)
[3] Railway 배포 → 앱이 Turso에서 상품 자동 로드
```

**이유:**
- Railway 배포 시 앱이 시작하면 `init_db()`가 products 테이블을 생성하지만 **데이터는 비어 있음**
- `data_store.py`가 Turso products가 0행이면 자동으로 JSON fallback → 배포해도 동작은 하지만 의미 없음
- 마이그레이션으로 데이터를 먼저 넣어두면, 배포 후 바로 DB에서 상품 서빙

---

## ✅ 변경된 파일 목록

### 1. [신규] `scripts/migrate_to_turso.py`
**역할:** 크롤링 JSON → Turso products 테이블 배치 INSERT

**주요 기능:**
- 여러 JSON 파일 병합 (`--input a.json b.json c.json`)
- `id` 기준 중복 자동 제거 (나중 파일이 덮어쓰기)
- `price_jpy` 자동 보충 (없으면 환율 변환)
- 배치 INSERT (기본 500행씩, `--batch-size`로 조절)
- `INSERT OR REPLACE` (UPSERT) → 재실행해도 안전
- `--dry-run` 옵션으로 DB에 쓰지 않고 검증만 가능
- 실패 배치 개별 재시도
- 진행률 표시 + 최종 검증 (DB 총 행 수 조회)

**사용법:**
```bash
# 드라이런
python scripts/migrate_to_turso.py --input data.json --dry-run

# 실행
python scripts/migrate_to_turso.py --input data.json

# 여러 파일
python scripts/migrate_to_turso.py --input 기존.json 동료.json
```

---

### 2. [수정] `backend/services/turso_db.py`
**변경 내용:** `init_db()` 함수의 `statements` 리스트에 추가

**추가된 SQL:**
```sql
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
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);
CREATE INDEX IF NOT EXISTS idx_products_price ON products(price_krw);
```

**기존 테이블 영향:** 없음 (기존 5개 테이블은 그대로 유지)

---

### 3. [수정] `backend/services/data_store.py`
**변경 내용:** 전면 재작성 — Turso 우선 + JSON fallback 하이브리드

**핵심 로직:**
```
앱 시작 → _check_db_available()
            ├─ Turso products에 데이터 있음 → DB에서 로드
            └─ 비어있거나 접근 불가 → 기존 JSON에서 로드 (원래 방식)
```

**변경된 함수:**

| 함수 | 변경 전 | 변경 후 |
|------|---------|---------|
| `load_products()` | JSON 파일만 읽음 | Turso 우선 → JSON fallback |
| `find_product()` | 전체 순회 검색 | Turso `SELECT WHERE id=?` 우선 → JSON fallback |

**추가된 함수:**

| 함수 | 역할 |
|------|------|
| `_check_db_available()` | Turso products 테이블 존재+데이터 확인 |
| `_load_from_db()` | Turso에서 전체 상품 로드 + JSON 필드 파싱 |
| `_find_from_db()` | Turso에서 단일 상품 조회 |
| `_load_from_json()` | 기존 JSON 로드 로직 (이름만 변경) |

**호환성:** `load_products()`와 `find_product()` 인터페이스가 동일 → `recommend.py`, `checkout.py`, `ai_curator.py` 등 **수정 불필요**

---

### 4. [신규] `crawling_data_migration_guide.md` (이 파일)
변경 이력과 실행 가이드 문서

---

## 🚀 실행 순서 (동료 컴퓨터)

```bash
# 0. 코드 최신화
git pull

# 1. 의존성 확인
pip install libsql python-dotenv

# 2. .env 파일에 Turso 환경변수 확인
#    TURSO_DATABASE_URL=libsql://your-db.turso.io
#    TURSO_AUTH_TOKEN=eyJ...
#    JPY_RATE=0.11

# 3. 드라이런 (검증만)
python scripts/migrate_to_turso.py --input 동료데이터경로.json --dry-run

# 4. 실제 마이그레이션
python scripts/migrate_to_turso.py --input 동료데이터경로.json

# 5. Turso 대시보드에서 확인
#    → products 테이블에 데이터가 들어갔는지 확인
```

---

## ⚠️ 주의사항

1. **`.env` 필수** — Turso URL/Token이 없으면 스크립트가 즉시 종료
2. **이미지는 별도** — 이 스크립트는 JSON 메타데이터만 DB에 넣음. 이미지(3.1GB+)는 CDN 이관 별도 진행
3. **재실행 안전** — `INSERT OR REPLACE` 사용으로 같은 스크립트를 여러 번 돌려도 데이터 꼬이지 않음
4. **롤백 방법** — Turso 대시보드에서 `DROP TABLE products;` 실행하면 초기 상태로 복원. 앱은 자동으로 JSON fallback
