# SEOULFIT Crawler

K-패션 쇼핑몰(29cm, W컨셉, 무신사) 상품 데이터 수집 + Google Drive 업로드 독립 패키지.

> 이 폴더는 메인 서버(`backend/`)와 **완전히 분리**되어 있습니다.
> 크롤링 담당자는 이 폴더만 복사해 사용할 수 있습니다.

---

## 빠른 시작

```bash
# 1. 의존성 설치
pip install -r requirements.txt
playwright install chromium   # Playwright 크롤러 사용 시

# 2. 환경변수 설정
cp .env.example .env
# .env 파일에 OPENAI_API_KEY, Google 서비스 계정 경로 입력

# 3. 크롤링 실행
python run.py --mall wconcept --limit 1000
python run.py --mall 29cm    --limit 1000
python run.py --mall all     --limit 3000

# 4. 데이터 정제 (GPT-4o-mini로 style/tags 추가)
python enrich.py

# 5. Google Drive 업로드
python gdrive/upload.py
```

---

## 파일 구조

```
crawler/
├── README.md               ← 이 파일
├── requirements.txt        ← 크롤러 전용 의존성
├── .env.example            ← 환경변수 템플릿
├── run.py                  ← 메인 진입점 (CLI)
├── pipeline.py             ← 크롤링 파이프라인 코어
├── progress.py             ← 진행 상태 관리 (체크포인트)
├── enrich.py               ← GPT-4o-mini 데이터 정제
│
├── sources/                ← 사이트별 크롤러
│   ├── common.py           ← 공통 베이스 클래스
│   ├── playwright_base.py  ← Playwright 베이스
│   ├── wconcept.py         ← W컨셉 (requests)
│   ├── wconcept_pw.py      ← W컨셉 (Playwright)
│   ├── cm29.py             ← 29cm (requests)
│   └── cm29_pw.py          ← 29cm (Playwright)
│
├── gdrive/                 ← Google Drive 연동
│   ├── upload.py           ← 업로드 스크립트
│   └── service_account.json.example
│
└── data/                   ← 수집 결과 (gitignore)
    ├── products_raw.json
    ├── products_enriched.json
    └── progress.json
```

---

## 환경변수

| 변수 | 설명 |
|------|------|
| `OPENAI_API_KEY` | GPT-4o-mini 데이터 정제용 |
| `GDRIVE_SERVICE_ACCOUNT_PATH` | Google 서비스 계정 JSON 파일 경로 |
| `GDRIVE_FOLDER_ID` | 업로드할 Google Drive 폴더 ID |

---

## 출력 형식

`data/products_enriched.json` — 상품 배열:

```json
[
  {
    "id": "wconcept-123456",
    "name": "오버핏 셔츠",
    "brand": "BRAND_NAME",
    "mall": "wconcept",
    "category": "top",
    "sub_category": "shirt",
    "price_krw": 59000,
    "colors": ["white", "black"],
    "gender": "women",
    "style": "casual",
    "tags": ["오버핏", "기본템", "데일리"],
    "image_url": "https://...",
    "source_url": "https://..."
  }
]
```

---

## Google Drive 구조

업로드 후 Drive 폴더 구조:

```
seoulfit-data/
├── metadata/
│   ├── products_enriched.json   ← 서버가 시작 시 로드
│   └── gallery-index.json       ← 이미지 파일 ID 매핑
└── images/
    ├── wconcept/
    ├── 29cm/
    └── generated/               ← AI Photobooth 결과
```
