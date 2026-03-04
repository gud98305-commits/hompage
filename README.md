# SEOULFIT & Seongsu RPG Project

통합 웹 애플리케이션 프로젝트입니다. AI 큐레이터(의류 추천), 성수동 RPG 게임, 포토부스 기능을 모두 포함하는 단일 FastAPI 백엔드로 구성되어 있습니다.

## 🚀 주요 기능 및 스택

- **Backend**: Python 3.11, FastAPI, Uvicorn
- **Database**: Turso (libsql) - 크롤링 및 제품 데이터 저장 / SQLite (RPG 게임 등 로컬 데이터)
- **AI/API**: OpenAI (챗봇/큐레이터), DeepL (번역), Stripe (결제), Google OAuth (크롤러 연동)
- **Frontend**: HTML/CSS/JS (Vanilla)

## 📁 주요 폴더 구조

- `index.html`: 메인 랜딩 (SEOULFIT)
- `fashion.html`: AI 큐레이터 화면 + 결제
- `rpg.html`: 성수동 RPG 게임
- `photobooth.html`: 포토부스 기능
- `backend/`: FastAPI API 서버 구동 로직 (`app.py`, `routes/`, `services/`)
- `crawler/`: W컨셉, 29CM 상품 크롤링 및 전처리 로직
- `game/`: RPG 게임 소스 코드 및 관련 리소스
- `miniproject_2/`: 포토부스 등 미니 프로젝트 소스 (통합됨)
- `data/`, `images/`: 크롤링된 데이터 결과 및 의류/게임 이미지

## 💻 로컬 실행 가이드

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
`.env` 파일에 발급받은 API Key(OpenAI, Stripe, Turso 등)를 입력합니다.

### 3) 서버 실행
```bash
uvicorn backend.app:app --reload --port 8000
```
- 브라우저 접속: `http://localhost:8000/`

## 🚂 Railway 배포 가이드

본 프로젝트는 GitHub과 연동하여 **Railway**에 즉시 배포할 수 있도록 구성되어 있습니다 (`Dockerfile`, `railway.toml` 포함).

1. [Railway.app](https://railway.app) 에 가입 및 로그인
2. **New Project** -> **Deploy from GitHub repo** 선택 후 해당 저장소 연결
3. **Variables** 설정: 로컬 `.env` 에 있던 필수 키들(`OPENAI_API_KEY`, `JWT_SECRET`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` 등)을 모두 추가해주세요.
   - `FRONTEND_URL`, `REDIRECT_URI`는 Railway에서 발급받은 도메인(예: `https://your-app.up.railway.app`)으로 변경해야 합니다.
4. **Volumes** 마운트: `/app/data` 및 `/app/images` 경로를 볼륨으로 연결해야 컨테이너 재시작 시 SQLite DB 내역(RPG 데이터) 및 이미지 파일이 소실되지 않습니다.

## 🕷 크롤러 및 데이터 갱신 가이드

데이터(상품 목록)를 수집하려면 다음 커맨드를 통해 크롤링을 실행합니다.

```bash
python -m backend.services.crawl_pipeline --source both --pages 2 --max 80
```
크롤링된 결과물은 `data/products_raw.json` 으로 저장되며, 이후 전처리 과정을 거쳐 화면에 출력됩니다.
