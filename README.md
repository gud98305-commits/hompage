# SEOULFIT & Seongsu RPG Project

통합 웹 애플리케이션 프로젝트입니다. AI 큐레이터(의류 추천), 성수동 RPG 게임, 포토부스, aeae 팝업스토어 기능을 모두 포함하는 단일 FastAPI 백엔드로 구성되어 있습니다.

## 주요 기능 및 스택

- **Backend**: Python 3.11, FastAPI, Uvicorn
- **Database**: Turso (libsql) — 크롤링 및 제품 데이터 저장 / SQLite (RPG 게임, 챗봇 등 로컬 데이터)
- **AI/API**: OpenAI (챗봇/큐레이터/aeae 답장), DeepL (번역), Stripe (결제), Google OAuth
- **Frontend**: HTML/CSS/JS (Vanilla, ES6 Module)

## 주요 페이지

| 경로 | 설명 |
|------|------|
| `/` | 메인 랜딩 (SEOULFIT) |
| `/fashion.html` | AI 패션 큐레이터 + 결제 |
| `/rpg.html` | 성수동 RPG 게임 |
| `/photobooth.html` | AI 포토부스 |
| `/my.html` | 마이페이지 (구매내역/위시리스트) |
| `/aeae_popup/` | aeae 팝업스토어 (답장/룩북/룰렛) |

## 폴더 구조

```
├── index.html, fashion.html, rpg.html, photobooth.html, my.html
├── assets/
│   ├── css/          # 페이지별 스타일 (theme, fashion, rpg, photobooth)
│   ├── js/           # 페이지별 로직 + 공통 유틸 (utils.js, api-client.js, auth.js, i18n.js)
│   └── rpg/          # RPG 게임 스프라이트/배경/음악
├── aeae_popup/       # aeae 팝업스토어 (index, lookbook, receipt)
├── backend/
│   ├── app.py        # FastAPI 앱 엔트리
│   ├── routes/       # API 라우트 (auth, recommend, checkout, rpg, photobooth, aeae_receipt 등)
│   └── services/     # 비즈니스 로직 (ai_curator, chatbot_advanced, stripe, turso_db 등)
├── shared/           # 공통 유틸 (brand_utils, fx_converter, image_quality)
├── crawler/          # W컨셉, 29CM 상품 크롤링
├── miniproject_2/    # 포토부스 데이터/레퍼런스 이미지
├── game/             # RPG 게임 소스 리소스
├── data/             # 크롤링 데이터, SQLite DB
└── images/           # 상품 이미지
```

## 로컬 실행 가이드

### 1) 패키지 설치 및 가상환경 설정
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2) 환경 변수 설정
```bash
cp .env.example .env
```
`.env` 파일에 필요한 API Key를 입력합니다:

| 변수 | 용도 |
|------|------|
| `OPENAI_API_KEY` | AI 큐레이터, 챗봇, aeae 답장 |
| `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY` | 결제 |
| `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` | 제품 DB |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | OAuth 로그인 |
| `JWT_SECRET` | 세션 토큰 |
| `DEEPL_API_KEY` | 번역 |
| `R2_*` | Cloudflare R2 이미지 저장 |

### 3) 서버 실행
```bash
uvicorn backend.app:app --reload --port 8001
```
브라우저 접속: `http://localhost:8001/`

## Railway 배포 가이드

`Dockerfile`, `railway.toml` 포함되어 있어 Railway에서 즉시 배포 가능합니다.

1. [Railway.app](https://railway.app) 에 가입 및 로그인
2. **New Project** → **Deploy from GitHub repo** 선택 후 저장소 연결
3. **Variables** 설정: `.env`의 필수 키들을 모두 추가
   - `FRONTEND_URL`, `REDIRECT_URI`는 Railway 도메인으로 변경
4. **Volumes** 마운트: `/app/data` 및 `/app/images` 경로를 볼륨으로 연결

## 크롤러 실행

```bash
python -m backend.services.crawl_pipeline --source both --pages 2 --max 80
```
결과물은 `data/products_raw.json`으로 저장됩니다.
