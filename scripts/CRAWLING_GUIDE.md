# 무신사 크롤링 팀 공유 가이드

> 마지막 업데이트: 2026-03-03
> 크롤러: `scripts/crawl_clothing.py` (Playwright + 무신사 공개 API)

---

## 목차
1. [개요](#1-개요)
2. [사전 준비 (모두 동일)](#2-사전-준비-모두-동일)
3. [팀원별 담당 커맨드 (역할 분배표)](#3-팀원별-담당-커맨드-역할-분배표)
4. [실행 중 체크포인트 & 재실행](#4-실행-중-체크포인트--재실행)
5. [완료 후 파일 전달 방법](#5-완료-후-파일-전달-방법)
6. [취합 담당자: 병합 방법](#6-취합-담당자-병합-방법)
7. [자주 묻는 질문 (FAQ)](#7-자주-묻는-질문-faq)
8. [옵션 전체 목록](#8-옵션-전체-목록)

---

## 1. 개요

각 팀원이 **서로 다른 카테고리 + 성별** 조합을 담당해 크롤링하고,
개인 결과 파일(`crawl_X.json`)을 취합 담당자에게 전달합니다.
취합 담당자가 `merge_crawl.py`로 하나로 합친 뒤 서버에 반영합니다.

```
[팀원 A] crawl_A.json ─┐
[팀원 B] crawl_B.json ─┤
[팀원 C] crawl_C.json ─┼─→ merge_crawl.py → products_enriched.json → 서버
[팀원 D] crawl_D.json ─┤
[팀원 E] crawl_E.json ─┘
```

### 수집 목표
| 카테고리 | 목표 | 비고 |
|---------|------|------|
| 상의 (top) 여성 | 200개 | 반팔/긴팔/맨투맨/후드/니트/셔츠 |
| 상의 (top) 남성 | 200개 | 동일 서브카테고리 |
| 하의 (bottom) 전체 | 200개 | 데님/슬랙스/스커트/조거 |
| 아우터 (outer) 전체 | 200개 | 코트/재킷/패딩 |
| 원피스 (dress) 여성 | 200개 | 원피스/점프수트 |
| **합계** | **~1,000개** | 중복 제거 후 실제 수는 다를 수 있음 |

---

## 2. 사전 준비 (모두 동일)

### 2-1. 파일 받기
취합 담당자에게 아래 파일/폴더를 받으세요:
```
0227 test/
├── scripts/
│   ├── crawl_clothing.py   ← 크롤러 본체
│   └── merge_crawl.py      ← 취합용 (취합 담당자만 사용)
├── .venv/                  ← Python 가상환경 (아래에서 생성)
└── data/                   ← 결과 파일 저장 위치
```

### 2-2. Python 환경 설치
터미널에서 `0227 test/` 폴더로 이동 후:

```bash
# 가상환경 생성 (최초 1회)
python3 -m venv .venv

# 가상환경 활성화
source .venv/bin/activate        # Mac / Linux
# .venv\Scripts\activate.bat    # Windows

# 필수 패키지 설치
pip install playwright Pillow requests

# Playwright 브라우저 설치 (최초 1회, 약 150MB)
playwright install chromium
```

### 2-3. 설치 확인
```bash
.venv/bin/python -c "from playwright.async_api import async_playwright; print('OK')"
# → OK 출력되면 정상
```

---

## 3. 팀원별 담당 커맨드 (역할 분배표)

> ⚠️ **규칙**: 아래 표에서 **자신의 알파벳**에 해당하는 커맨드만 실행하세요.
> 같은 카테고리+성별 조합을 두 명이 실행하면 데이터가 겹칩니다.

### 커맨드 복사해서 그대로 실행 (가상환경 활성화 상태에서)

---

#### 👤 팀원 A — 상의(top) 여성
```bash
.venv/bin/python scripts/crawl_clothing.py \
  --category top \
  --gender F \
  --per-category 200 \
  --output crawl_A.json
```
- 수집 대상: 반팔T / 긴팔T / 맨투맨 / 후드 / 니트 / 셔츠 (여성)
- 예상 소요 시간: **약 60~90분**
- 결과 파일: `data/crawl_A.json`

---

#### 👤 팀원 B — 상의(top) 남성
```bash
.venv/bin/python scripts/crawl_clothing.py \
  --category top \
  --gender M \
  --per-category 200 \
  --output crawl_B.json
```
- 수집 대상: 반팔T / 긴팔T / 맨투맨 / 후드 / 니트 / 셔츠 (남성)
- 예상 소요 시간: **약 60~90분**
- 결과 파일: `data/crawl_B.json`

---

#### 👤 팀원 C — 하의(bottom) 전체
```bash
.venv/bin/python scripts/crawl_clothing.py \
  --category bottom \
  --gender A \
  --per-category 200 \
  --output crawl_C.json
```
- 수집 대상: 데님/청바지, 슬랙스, 조거/카고, 스커트
- 예상 소요 시간: **약 60~90분**
- 결과 파일: `data/crawl_C.json`

---

#### 👤 팀원 D — 아우터(outer) 전체
```bash
.venv/bin/python scripts/crawl_clothing.py \
  --category outer \
  --gender A \
  --per-category 200 \
  --output crawl_D.json
```
- 수집 대상: 코트, 재킷/블레이저, 패딩/점퍼
- 예상 소요 시간: **약 60~90분**
- 결과 파일: `data/crawl_D.json`

---

#### 👤 팀원 E — 원피스(dress) 여성
```bash
.venv/bin/python scripts/crawl_clothing.py \
  --category dress \
  --gender F \
  --per-category 200 \
  --output crawl_E.json
```
- 수집 대상: 원피스, 점프수트 (여성)
- 예상 소요 시간: **약 30~60분** (서브카테고리가 적어 빠름)
- 결과 파일: `data/crawl_E.json`

---

### ✅ 정상 실행 화면 예시
```
[시작] 저장 파일: crawl_A.json
  기존 0개 | 카테고리: ['top'] | 여성 | 정렬: POPULAR
  카테고리당 최대: 200개

[top] 시작 (API 코드: ['001001', '001010', '001005', '001004', '001006', '001002'])
  [001001] API 수집: 35개
  [001010] API 수집: 30개
  ...
  [1/200] 브랜드명 - 상품명
  [2/200] 브랜드명 - 상품명
  ...
  [중간저장] 신규 10개 → crawl_A.json
```

---

## 4. 실행 중 체크포인트 & 재실행

크롤러는 **10개마다 자동 중간저장**합니다.
인터넷 끊김, 컴퓨터 재시작 등으로 중단되면 **같은 커맨드를 다시 실행**하면 됩니다.
기존 저장된 URL은 자동으로 건너뜁니다.

```bash
# 중단 후 재실행 (이미 수집한 것은 건너뜀)
.venv/bin/python scripts/crawl_clothing.py \
  --category top --gender F --per-category 200 --output crawl_A.json
```

---

## 5. 완료 후 파일 전달 방법

### 전달해야 하는 파일 (1개)
```
data/crawl_A.json    ← 본인 알파벳 파일 1개만!
```

> ⚠️ `images/` 폴더는 **용량이 너무 커서 전달하지 않아도 됩니다.**
> (이미지는 취합 담당자가 직접 다운로드하거나 Google Drive 공유 사용)

### 전달 방법 (아무거나)
- **카카오톡/슬랙**: 파일 직접 전송 (50MB 미만이면 가능)
- **구글 드라이브**: 팀 공유 폴더에 업로드
- **WeTransfer / Dropbox**: 대용량 파일 전송
- **USB 직접 전달**

### 파일 위치 확인
```bash
ls -lh data/crawl_*.json
# 예: -rw-r--r--  1 user  staff   8.2M data/crawl_A.json
```

---

## 6. 취합 담당자: 병합 방법

### 6-1. 파일 수거
팀원 모두에게 `crawl_X.json` 파일을 받아 `data/` 폴더에 넣습니다:

```
data/
├── crawl_A.json    ← 팀원 A에게 받음
├── crawl_B.json    ← 팀원 B에게 받음
├── crawl_C.json    ← 팀원 C에게 받음
├── crawl_D.json    ← 팀원 D에게 받음
└── crawl_E.json    ← 팀원 E에게 받음
```

### 6-2. 병합 실행
```bash
.venv/bin/python scripts/merge_crawl.py
```

출력 예시:
```
[병합 시작] 5개 파일 발견
============================================================
  crawl_A.json     187개 로드, 187개 유효
  crawl_B.json     201개 로드, 201개 유효
  crawl_C.json     198개 로드, 198개 유효
  crawl_D.json     195개 로드, 195개 유효
  crawl_E.json     143개 로드, 143개 유효

  합계: 924개 (중복 제거 전)
  중복 제거: 5개 제거됨
  최종: 919개

  [카테고리 분포]
    bottom      : 198개
    dress       :  143개
    outer       : 195개
    top         : 383개

  [백업] 기존 파일 → products_enriched.BACKUP_20260303_154200.json

[저장 완료] /Users/.../data/products_enriched.json
[리포트] /Users/.../data/merge_report.txt
============================================================
✅ 병합 완료: 총 919개 상품 → products_enriched.json
```

### 6-3. 서버 재시작
```bash
# 개발 환경
.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8001 --reload

# 또는 Railway 자동 배포 (push 시 자동)
```

### 6-4. (선택) 특정 파일만 병합
```bash
# crawl_A.json과 crawl_B.json만 병합
.venv/bin/python scripts/merge_crawl.py --input "data/crawl_[AB].json"

# 다른 폴더의 파일
.venv/bin/python scripts/merge_crawl.py --input "/Downloads/crawl_*.json"

# 백업 없이
.venv/bin/python scripts/merge_crawl.py --no-backup
```

---

## 7. 자주 묻는 질문 (FAQ)

### Q: 실행 중에 브라우저가 뜨나요?
A: 기본적으로 뜨지 않습니다 (headless 모드). 화면을 보고 싶으면:
```bash
.venv/bin/python scripts/crawl_clothing.py \
  --category top --gender F --per-category 200 --output crawl_A.json \
  --no-headless
```

### Q: 중간에 멈췄어요. 어떻게 하나요?
A: **같은 커맨드를 다시 실행**하면 됩니다. 이미 수집한 URL은 건너뜁니다.

### Q: 오류가 났는데 어디에 보고하나요?
A: 터미널 출력 전체를 캡처해서 취합 담당자에게 공유해 주세요.
일시적인 네트워크 오류는 재실행으로 해결됩니다.

### Q: 200개가 다 안 채워졌어요.
A: 정상입니다. 무신사 해당 카테고리에 필터 기준(이미지 품질 등)을 통과하는
상품이 부족하면 그보다 적을 수 있습니다. 그냥 전달해 주세요.

### Q: images/ 폴더가 너무 커요 (수 GB). 어떻게 전달하나요?
A: **JSON 파일만** 전달하면 됩니다. 이미지는 서버에서 URL로 표시하거나,
취합 담당자가 Google Drive 업로드를 따로 진행합니다.

### Q: 내가 이미 수집한 것과 다른 사람 것이 겹치면?
A: `merge_crawl.py`가 `source_url` 기준으로 자동 중복 제거합니다.
같은 상품 URL이 두 파일에 있으면 먼저 온 것만 유지됩니다.

### Q: --sort 옵션을 바꿔도 되나요?
A: 네. 기본값은 `POPULAR` (인기순)이고, `DATE` (최신순)로도 바꿀 수 있습니다.
단, 역할 분배표에 적힌 category/gender는 꼭 지켜주세요.

---

## 8. 옵션 전체 목록

```
usage: crawl_clothing.py [--category {top,bottom,outer,dress}]
                         [--per-category N]
                         [--gender {A,M,F}]
                         [--sort {POPULAR,DATE,REVIEW,LOW_PRICE}]
                         [--output FILE]
                         [--delay SECONDS]
                         [--no-headless]
                         [--verbose]

옵션:
  --category    크롤할 카테고리 (기본: 전체 top+bottom+outer+dress)
  --per-category  카테고리당 최대 수집 수 (기본: 40, 팀 크롤링: 200 권장)
  --gender      A=전체, M=남성, F=여성 (기본: A)
  --sort        POPULAR=인기순, DATE=최신순, REVIEW=리뷰순, LOW_PRICE=저가순
  --output      저장 파일명 (data/ 아래 저장). 예: crawl_A.json
  --delay       상품 간 대기 시간(초) (기본: 1.0, 높일수록 안정적)
  --no-headless 브라우저 창 표시 (디버깅용)
  --verbose     URL 단위 상세 로그 출력
```

---

*문의: 취합 담당자에게 연락 주세요.*
