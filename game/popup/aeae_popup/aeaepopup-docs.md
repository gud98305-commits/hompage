# aeae pop-up store — 프로젝트 문서

> **URL:** [aeaepopup.netlify.app](https://aeaepopup.netlify.app)  
> **GitHub:** [github.com/tutto-unni/aeaepopup](https://github.com/tutto-unni/aeaepopup)  
> **배포:** Netlify (GitHub 연동 자동 배포)

---

## 프로젝트 개요

aeae 브랜드의 온라인 팝업스토어. 룩북 슬롯머신과 AI 감성 영수증 두 가지 인터랙티브 기능을 중심으로 구성된 단일 HTML 사이트.

---

## 파일 구조

```
AEAE_POPUP/
├── netlify.toml              # Netlify 빌드 설정
├── package.json              # npm 의존성 (openai ^4.28.0)
├── package-lock.json
├── index.html                # 메인 팝업스토어 입장 페이지
├── lookbook.html             # 룩북 슬롯머신 + AI 스타일 포춘
├── receipt.html              # AI 감성 영수증 생성기
├── images/                   # 브랜드 이미지 에셋
└── netlify/
    └── functions/
        ├── aeae-lookbook.js  # 룩북 AI API (GPT-4.1)
        ├── aeae-receipt.js   # 영수증 AI API (GPT-4.1)
        └── openai.js         # 공통 OpenAI 래퍼 (GPT-4.1-mini)
```

---

## 페이지별 설명

### 1. `index.html` — 메인 입장 페이지

브랜드 감성의 데스크 배경 위에 두 개의 오브젝트(룩북, 영수증)가 놓인 인터랙티브 입장 화면.

- `floor.png` 배경, `mat.png` 매트 레이어
- 룩북 오브젝트 클릭 → `lookbook.html`로 이동
- 영수증 오브젝트 클릭 → `receipt.html`로 이동
- 폰트: `Caveat`, `Noto Serif JP` (Google Fonts)

---

### 2. `lookbook.html` — 룩북 슬롯머신

**기능 흐름:**

```
슬롯 스핀 → 룩 선택 → AI 호출 → 스타일 설명 + 오늘의 운세 표시
```

**룩 데이터 구조:**
```javascript
{
  id: 1,
  topName: "아이템명",
  bottomName: "아이템명",
  accName: "아이템명",     // 없으면 'アクセなし'
  top: "images/top_1.jpg",
  bottom: "images/bottom_1.jpg"
}
```

**AI 호출 (`callLookAI`):**
```javascript
// POST /.netlify/functions/aeae-lookbook
{
  lookId: 1,
  topName: "...",
  bottomName: "...",
  accName: "..."
}

// 응답
{
  style: "일본어 스타일 설명",
  styleKr: "한국어 번역",
  fortune: "일본어 오늘의 운세",
  fortuneKr: "한국어 번역"
}
```

**에러 처리:** API 실패 시 하드코딩된 기본 텍스트로 폴백.

---

### 3. `receipt.html` — AI 감성 영수증

**기능 흐름:**

```
이름 + 고민 입력 → AI 호출 → 영수증 렌더링 → 이미지 저장 / SNS 공유
```

**AI 호출 (`generateReceipt`):**
```javascript
// POST /.netlify/functions/aeae-receipt
{ name: "이름", worry: "고민 내용" }

// 응답
{
  emotion: "감정 라인 (일본어)",
  message_ja: "일본어 메시지 (6~8줄)",
  message_kr: "한국어 번역",
  discount_code: "KEEPAEAE_15",
  discount_pct: 15
}
```

**영수증 구성 요소:**
- 이름, 날짜, 감정 라인
- 고민 내용
- AI 메시지 (일본어 + 한국어)
- 바코드 + QR코드 (`qrcodejs` 라이브러리)
- 15% 할인 코드

**저장/공유:**
- `html2canvas`로 영수증을 이미지 캡처 → PNG 저장
- 인스타그램 공유 버튼

---

## Netlify Functions

### `aeae-lookbook.js`

룩북용 AI. GPT-4.1을 두 번 호출해 스타일 설명과 운세를 순차 생성.

```
1단계: 코디 정보 → 스타일 설명 (일본어 + 한국어)
2단계: 스타일 설명 → 오늘의 운세 (일본어 + 한국어)
```

- 모델: `gpt-4.1`
- 톤: ため口 (반말), 손편지 감성, 2~3줄
- 구분자: `---` 로 일본어/한국어 분리

### `aeae-receipt.js`

영수증용 AI. 고민을 받아 감성 메시지와 할인 코드를 JSON으로 반환.

- 모델: `gpt-4.1` + `response_format: json_object`
- 브랜드 페르소나: 친한 친구, aeae 브랜드 보이스
- 핵심 가치: Neverland / Keepsake / Touch (직접 언급하지 않고 자연스럽게 구현)
- 고정 할인 코드: `KEEPAEAE_15` (15% OFF)

### `openai.js`

`gpt-4.1-mini` 기반 공통 래퍼. `receipt.html`의 `callOpenAI()` 함수에서 호출.

- `sys` (시스템 프롬프트), `name`, `worry` 를 body로 받음
- `response_format: json_object` 사용
- temperature: 0.8

---

## 환경변수

| 변수명 | 설명 | 설정 위치 |
|--------|------|-----------|
| `OPENAI_API_KEY` | OpenAI API 키 | Netlify → Site configuration → Environment variables |

---

## 배포 설정 (`netlify.toml`)

```toml
[build]
  functions = "netlify/functions"

[functions]
  node_bundler = "esbuild"
```

---

## 의존성

```json
{
  "dependencies": {
    "openai": "^4.28.0"
  }
}
```

> ⚠️ `package-lock.json`에 v6.25.0이 기록되어 있다면 로컬에서 `npm install` 후 재커밋 필요.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| API 404 — HTML 반환 | `netlify.toml` 없음 또는 functions 경로 미설정 | 루트에 `netlify.toml` 추가 |
| Functions 탭에 함수 없음 | GitHub push 누락 | 파일 push 후 재배포 확인 |
| `client.responses.create` 에러 | OpenAI SDK에 없는 메서드 | `chat.completions.create`로 수정 |
| ESM import 에러 | Netlify Functions는 CommonJS 기본 | `require` / `exports.handler` 방식으로 변환 |
| `openai` 설치 실패 | v6는 존재하지 않음 | `package.json`을 `^4.28.0`으로 수정 |

---

## 브랜드 보이스 가이드 (AI 프롬프트 공통)

- **언어:** 일본어 (ため口) + 한국어 번역 세트
- **톤:** 손편지처럼 따뜻하고 몽환적, 친한 친구의 말투
- **길이:** 2~3줄 (룩북), 6~8줄 (영수증)
- **브랜드 가치:** Neverland · Keepsake · Touch — 직접 언급 금지, 자연스럽게 녹여낼 것
