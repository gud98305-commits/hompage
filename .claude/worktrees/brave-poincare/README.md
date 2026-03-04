# SEOULFIT AI Curator

`index.html` 디자인 톤을 유지하면서 `fashion.html`에서 아래를 수행합니다.

- 사용자 입력(체형/색/스타일/키워드/가격)
- AI 큐레이션 정렬(현재는 룰 기반, OpenAI 연동 포인트 포함)
- W컨셉/29CM 크롤링 데이터 표시
- KRW -> JPY 변환 가격 표시
- `fashion.html` 내부 Stripe Elements 결제
- 이메일 입력 시 결제 완료 메일 발송(선택)

## 폴더 구조

- `index.html`: 메인 랜딩
- `fashion.html`: AI 큐레이터 화면 + 결제 모달
- `assets/css/theme.css`: 공통 디자인 토큰
- `assets/css/fashion.css`: 큐레이터 화면 스타일
- `assets/js/fashion.js`: 추천/결제 UI 로직
- `backend/app.py`: FastAPI 서버 + 정적 파일 서빙
- `backend/routes/recommend.py`: 추천 API
- `backend/routes/checkout.py`: PaymentIntent/결제완료 API
- `backend/services/crawl_pipeline.py`: Step 6 크롤링 실행 엔트리
- `backend/services/crawler_wconcept.py`: W컨셉 크롤러
- `backend/services/crawler_29cm.py`: 29CM 크롤러
- `data/products_enriched.json`: 화면 렌더링 데이터
- `images/wconcept`, `images/29cm`: 다운로드 이미지 저장

## VSCode + Terminal 실행 가이드

### 1) VSCode에서 폴더 열기

- VSCode -> `File` -> `Open Folder...`
- `/Users/choisinbi/Desktop/0227 test` 선택

### 2) 가상환경/패키지 설치

```bash
cd /Users/choisinbi/Desktop/0227\ test
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 3) 환경변수 준비

```bash
cp backend/.env.example backend/.env
```

- Stripe 실제 테스트 결제까지 보려면 `backend/.env`에
  - `STRIPE_SECRET_KEY`
  - `STRIPE_PUBLISHABLE_KEY`
- 메일 발송까지 보려면 SMTP 항목 입력

### 4) 서버 실행

```bash
uvicorn backend.app:app --reload --port 8000
```

브라우저에서:

- `http://localhost:8000/index.html`
- 카드 `AI 큐레이터` -> `추천 받기`

### 5) Step 6 크롤링 실행 (가장 중요)

새 터미널에서:

```bash
cd /Users/choisinbi/Desktop/0227\ test
source .venv/bin/activate
python -m backend.services.crawl_pipeline --source both --pages 2 --max 80
```

옵션:

- 자동 추출 생략: `--no-enrich`
- 진행 상태 확인: `--status`
- 기본은 로컬 이미지가 없는 상품을 제외(`strict_images`)하므로 로컬 표시 보장에 유리

### 6) 결과 파일 확인

- `data/products_raw.json`
- `data/products_enriched.json`
- `images/wconcept/*`, `images/29cm/*`

`crawl_pipeline` 실행 시 `products_raw.json` 병합 저장 후
`products_enriched.json` 추출이 자동으로 실행됩니다.

수집 품질 검증:

```bash
python verify_products.py data/products_raw.json
python verify_products.py data/products_enriched.json --min-detail-images 3 --min-detail-unique-ratio 0.6
```

### 7) 화면 검증 체크리스트

1. `fashion.html`에서 추천 결과 카드에 아래가 모두 뜨는지 확인
   - 쇼핑몰명
   - 상품명
   - 대표 이미지
   - 상세 이미지
   - 엔화 가격
2. 카드 `결제하기` 클릭 시 같은 페이지에서 결제 모달이 뜨는지 확인
3. Stripe 키 미설정이면 데모 결제가 완료되는지 확인
4. Stripe 키 설정 시 테스트카드 `4242 4242 4242 4242`로 결제 성공 확인
5. 이메일 입력 후 결제 시 완료 메일 수신 확인(SMTP 설정 필요)

## 현재 한계

- W컨셉/29CM 구조 변경/봇 방어 정책에 따라 크롤러는 수정이 필요할 수 있습니다.
- 이 프로젝트는 기술 데모 목적이며, 운영 단계에서는 크롤러 유지보수 작업이 상시 필요합니다.
