# SEOULFIT (OttO) - AI 패션 큐레이팅 & 성수동 RPG 통합 플랫폼

AI 패션 큐레이터, 성수동 테마 RPG 게임, AI 포토부스, aeae 팝업스토어를 하나의 플랫폼에 통합한 웹 애플리케이션입니다.

## 주요 기능

### 1. AI 패션 큐레이터
- 성별, 컬러, 스타일, 체형, 가격대 등 다양한 필터 기반 상품 추천
- OpenAI 기반 코디 매칭 (상의↔하의, 아우터↔상의/하의 등 보완 추천)
- W Concept, 29CM, Musinsa 등 멀티몰 크롤링 데이터 기반

### 2. AI 포토부스
- OpenAI gpt-image-1 기반 이미지 생성 및 편집
- 셀카 업로드 + 텍스트 설명으로 4컷 프레임 생성
- 다양한 스타일 프리셋 및 포즈 프리셋 지원
- 2×2 그리드 합성 (Pillow)

### 3. 성수동 RPG 게임
- 성수동 테마 롤플레잉 게임
- 아이템 거래 시스템 (구매/판매)
- 게임 세이브/로드 및 인벤토리 관리
- 패션 아이템 수집 및 스타일 선호도 분석

### 4. aeae 팝업스토어
- AI 감성 답장 (Dear aeae — OpenAI 기반 위로 메시지 생성)
- 럭키 룰렛 룩북 (스타일 슬롯머신 + AI 운세)
- 영수증 스타일 결과물 저장/공유

### 5. AI 챗봇
- 의도 분류 (키워드 + LLM 기반)
- RAG (Retrieval-Augmented Generation) 기반 상품/게임 질의 응답
- 체형 분석 기반 맞춤 추천

### 6. 결제 시스템
- Stripe 기반 결제 (JPY 통화 지원)
- KRW ↔ JPY 환율 변환
- 이메일 영수증 발송 (SMTP)

### 7. 사용자 인증
- Google OAuth 2.0 로그인
- JWT 토큰 인증 (30일 만료)
- 위시리스트 CRUD 및 localStorage 동기화

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| **Backend** | Python 3.11, FastAPI, Uvicorn, Pydantic |
| **Database** | Turso (libsql, 클라우드), SQLite (로컬 게임/챗봇) |
| **AI/API** | OpenAI (GPT, gpt-image-1), DeepL, Stripe, Google OAuth |
| **Frontend** | HTML5/CSS3/Vanilla JS (ES6 Module) |
| **크롤링** | Playwright, BeautifulSoup, httpx, aiohttp |
| **이미지** | Pillow |
| **배포** | Docker (Python 3.11-slim), Railway |

---

## 프로젝트 구조

```
hompage/
├── backend/                    # FastAPI 애플리케이션
│   ├── app.py                 # 앱 초기화, 미들웨어, 라우트 마운트
│   ├── routes/                # API 엔드포인트
│   │   ├── auth.py           # Google OAuth + JWT + 위시리스트
│   │   ├── recommend.py      # AI 패션 큐레이션 + 상품 추천
│   │   ├── checkout.py       # Stripe 결제
│   │   ├── photobooth.py     # AI 이미지 생성
│   │   ├── rpg.py            # RPG 세이브/로드/거래
│   │   ├── game.py           # 게임 인벤토리/히스토리
│   │   ├── translate.py      # DeepL 번역
│   │   ├── aeae_receipt.py   # aeae 팝업스토어 답장
│   │   ├── my.py             # 마이페이지
│   │   ├── pages.py          # 정적 페이지 서빙
│   │   └── webhook.py        # Stripe 웹훅
│   └── services/              # 비즈니스 로직
│       ├── turso_db.py       # Turso DB 스키마/연결
│       ├── ai_curator.py     # OpenAI 큐레이션 로직
│       ├── stripe_checkout.py # Stripe 결제 처리
│       ├── photobooth_image.py # 이미지 합성 로직
│       ├── translator.py     # DeepL API 래퍼
│       ├── mailer.py         # 이메일 발송
│       ├── rpg_models.py     # RPG SQLAlchemy 모델
│       ├── rpg_logic.py      # RPG 비즈니스 로직
│       └── chatbot_advanced/ # 고급 NLP 챗봇
│
├── aeae_popup/                # aeae 팝업스토어
│   ├── index.html            # 팝업스토어 메인
│   ├── receipt.html          # AI 답장 (Dear aeae)
│   └── lookbook.html         # 럭키 룰렛 룩북
│
├── crawler/                    # 상품 데이터 크롤링
│   ├── pipeline.py           # W Concept/29CM 크롤러
│   ├── crawl_clothing.py     # Musinsa 크롤러
│   └── enrich.py             # GPT-4o-mini 메타데이터 보강
│
├── shared/                    # 공통 유틸리티
│   ├── brand_utils.py       # 브랜드 추출/판별
│   ├── fx_converter.py      # 환율 변환
│   └── image_quality.py     # 이미지 품질 검증
│
├── assets/                    # 프론트엔드 정적 파일
│   ├── css/                  # 스타일시트
│   ├── js/                   # JavaScript 모듈 (utils.js, api-client.js 등)
│   └── rpg/                  # RPG 스프라이트/그래픽
│
├── miniproject_2/photobooth/  # 포토부스 데이터/레퍼런스
├── game/                      # RPG 게임 소스 리소스
├── data/                      # 런타임 데이터 + SQLite DB
├── images/                    # 상품 이미지
│
├── index.html                 # 메인 랜딩 페이지
├── fashion.html               # AI 큐레이터 + 결제
├── rpg.html                   # 성수동 RPG 게임
├── photobooth.html            # AI 포토부스
├── my.html                    # 마이페이지
│
├── Dockerfile                 # Docker 이미지 설정
├── railway.toml               # Railway 배포 설정
├── requirements.txt           # Python 의존성
└── .env.example               # 환경변수 템플릿
```

---

## API 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/health` | GET | 헬스체크 |
| `/api/auth/google` | GET | Google OAuth URL |
| `/api/auth/callback` | GET | OAuth 콜백 |
| `/api/auth/me` | GET | 현재 사용자 정보 |
| `/api/auth/wishlist` | GET/POST | 위시리스트 CRUD |
| `/api/auth/sync` | POST | localStorage 위시리스트 동기화 |
| `/api/recommend` | POST | AI 패션 큐레이션 |
| `/api/match-complement` | POST | 코디 매칭 추천 |
| `/api/checkout/intent` | POST | Stripe 결제 생성 |
| `/api/checkout/complete` | POST | 결제 완료 처리 |
| `/api/photobooth/styles` | GET | 포토부스 스타일 목록 |
| `/api/photobooth/presets` | GET | 포즈 프리셋 목록 |
| `/api/photobooth/generate` | POST | 4컷 이미지 생성 |
| `/api/proxy/aeae-receipt` | POST | aeae 답장 생성 |
| `/api/rpg/save` | POST | 게임 저장 |
| `/api/rpg/load/{id}` | GET | 게임 불러오기 |
| `/api/rpg/saves` | GET | 저장 목록 |
| `/api/rpg/trade/buy/{id}` | POST | 아이템 구매 |
| `/api/rpg/trade/sell/{id}` | POST | 아이템 판매 |
| `/api/game/inventory` | GET | 게임 인벤토리 |
| `/api/game/history` | GET | 게임 히스토리 + 선호도 |
| `/api/chat/*` | POST | 챗봇 대화 |

---

## 환경 변수

`.env.example`을 복사하여 `.env` 파일을 생성하고 API 키를 입력합니다.

```bash
cp .env.example .env
```

| 변수명 | 설명 | 필수 |
|--------|------|------|
| `OPENAI_API_KEY` | OpenAI API 키 | O |
| `STRIPE_SECRET_KEY` | Stripe 시크릿 키 | O |
| `STRIPE_PUBLISHABLE_KEY` | Stripe 퍼블리셔블 키 | O |
| `STRIPE_WEBHOOK_SECRET` | Stripe 웹훅 시크릿 | O |
| `DEEPL_API_KEY` | DeepL 번역 API 키 | O |
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID | O |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 시크릿 | O |
| `JWT_SECRET` | JWT 토큰 서명 키 | O |
| `TURSO_DATABASE_URL` | Turso DB URL | O |
| `TURSO_AUTH_TOKEN` | Turso 인증 토큰 | O |
| `FRONTEND_URL` | 프론트엔드 URL | O |
| `REDIRECT_URI` | OAuth 리다이렉트 URI | O |
| `RPG_DATABASE_URL` | RPG 게임 DB 경로 | - |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | 이메일 발송 설정 | - |

---

## 로컬 실행 가이드

### 1. 가상환경 설정 및 패키지 설치

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일에 발급받은 API Key 입력
```

### 3. 서버 실행

```bash
uvicorn backend.app:app --reload --port 8001
```

브라우저 접속: `http://localhost:8001/`

---

## 크롤러 실행

상품 데이터를 수집하려면 아래 명령어를 실행합니다.

```bash
# 통합 크롤링 파이프라인
python -m backend.services.crawl_pipeline --source both --pages 2 --max 80

# 또는 크롤러 직접 실행
python -m crawler.run --mall all --limit 3000
```

크롤링 결과는 `data/products_raw.json`에 저장되며, `enrich.py`를 통해 GPT-4o-mini로 메타데이터(성별, 스타일, 태그, 컬러)를 보강합니다.

---

## Railway 배포

본 프로젝트는 Docker + Railway로 배포할 수 있도록 구성되어 있습니다.

1. [Railway.app](https://railway.app)에 가입 및 로그인
2. **New Project** → **Deploy from GitHub repo** 선택 후 저장소 연결
3. **Variables** 설정: `.env`에 있던 필수 키들을 모두 추가
   - `FRONTEND_URL`, `REDIRECT_URI`는 Railway 도메인으로 변경
4. **Volumes** 마운트: `/app/data` 및 `/app/images` 경로를 볼륨으로 연결
   - 컨테이너 재시작 시 SQLite DB 및 이미지 파일 유지

### 배포 설정

- **Docker**: Python 3.11-slim 기반, 포트 8000 노출
- **헬스체크**: `/api/health` (30초 타임아웃)
- **자동 재시작**: 실패 시 최대 3회 재시도
- **시작 명령**: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`

---

## 아키텍처 특징

- **비동기 처리**: FastAPI async 라우트 + aiosqlite로 논블로킹 DB 액세스
- **병렬 이미지 생성**: ThreadPoolExecutor로 4컷 이미지 동시 생성
- **멀티 데이터베이스**: Turso (클라우드 상품 데이터) + SQLite (게임/챗봇 로컬)
- **크롤러 내결함성**: 체크포인트 복구, 진행률 추적, 데이터 중복 제거
- **CORS 설정**: 크로스 도메인 프론트엔드 접근 허용
