# 인생네컷 AI 생성기 — 주요 로직 정리

## 전체 흐름도

```
[사용자]                    [프론트엔드]                     [백엔드 API]
  │                            │                               │
  ├─ 셀카 업로드 ──────────────▶│                               │
  │                            ├─ 1MB 체크                     │
  │                            ├─ Canvas 리사이즈 (max 1024px)  │
  │                            ├─ base64 변환                   │
  │                            │                               │
  ├─ 스타일 선택 ──────────────▶│                               │
  │                            │                               │
  ├─ "생성하기" 클릭 ──────────▶│                               │
  │                            ├─ 요청 횟수 체크 (5회 제한)     │
  │                            ├─ POST /api/generate ──────────▶│
  │                            │   { imageBase64, styleId }     │
  │                            │                               ├─ [1] analyzeFace()
  │                            │                               │   └─ GPT-4o Vision → FaceDescription
  │                            │                               │
  │                            │                               ├─ [2] buildPrompts()
  │                            │                               │   └─ face + preset → 프롬프트 4개
  │                            │                               │
  │                            │                               ├─ [3] generateImages()
  │                            │                               │   └─ gpt-image-1.5 × 4 (병렬)
  │                            │                               │
  │                            │                               ├─ [4] compositeGrid()
  │                            │                               │   └─ Sharp 2×2 합성
  │                            │                               │
  │                            │◀─ { resultImage, frames } ────┤
  │                            │                               │
  │◀─ 결과 이미지 표시 ────────┤                               │
  │◀─ 다운로드 버튼 ──────────┤                               │
```

---

## 1. 얼굴 분석 — `lib/analyze.ts`

```
입력: selfie base64
출력: FaceDescription (JSON)
모델: GPT-4o Vision
```

### 로직
1. GPT-4o에 셀카를 `data:image/jpeg;base64,...` 형태로 전달
2. `response_format: { type: "json_object" }` → JSON 보장
3. 사전 검증:
   - 사람 얼굴 없음 → `{ "error": "no_face" }` → 에러 throw
   - 여러 명 → 가장 크고 중심에 있는 주 대상만 분석
4. 반환값에 fallback 적용 (필드 누락 시 기본값)

### FaceDescription 구조
```json
{
  "appearance": { "ethnicity_vibe", "age_range", "skin", "build" },
  "hair": { "description" },
  "face": { "eyes", "makeup" },
  "outfit": { "description", "accessories" }
}
```

---

## 2. 프롬프트 빌드 — `lib/prompt-builder.ts`

```
입력: FaceDescription + StylePreset
출력: string[4] (프레임당 1개 프롬프트)
순수 함수 (API 호출 없음)
```

### 로직
1. `BACKDROP_COLORS` 맵에서 스타일별 고정 파스텔 배경색 조회
2. 프리셋의 4개 프레임을 순회하며 프롬프트 생성
3. 각 프롬프트에 포함되는 정보:
   - 인물 묘사 (FaceDescription 전체)
   - 포즈/표정 (`frame.expression`, `frame.pose`, `frame.detailed_pose_description`)
   - 배경 (스타일별 고정 파스텔 hex 색상, 3회 반복 강조)
   - 금지 사항 (프레임/테두리/둥근 모서리 생성 금지)

### 스타일별 배경색
| 스타일 | 배경색 |
|---|---|
| sailor_moon | #FFB6C1 (파스텔 핑크) |
| kuromi | #D8B4FE (파스텔 라벤더) |
| psyduck | #BAE6FD (파스텔 스카이블루) |
| bobby_hill | #FECACA (파스텔 피치) |
| spongebob | #FEF08A (파스텔 옐로우) |

---

## 3. 이미지 생성 — `lib/generate-image.ts`

```
입력: prompts[4], selfieBase64
출력: FrameResult[4]
모델: gpt-image-1.5
```

### 로직
1. selfie base64 → Buffer → `toFile()` → 업로드 가능 파일로 변환
2. `openai.images.edit()` 호출:
   - `image`: 셀카만 전송 (레퍼런스 이미지 없음)
   - `size`: "1024x1536" (세로형, 인생네컷 비율)
   - `quality`: "medium"
3. `Promise.allSettled`로 4장 병렬 생성
4. 실패한 프레임만 **1회 재시도**
5. 최종 결과: `FrameResult[]` (success + base64 또는 error)

### 재시도 로직
```
1차 시도: 4장 병렬 → 성공/실패 분류
2차 시도: 실패분만 병렬 재시도
최종: 여전히 실패 → route.ts에서 회색 placeholder로 대체
```

---

## 4. 그리드 합성 — `lib/composite.ts`

```
입력: frames[4] (base64), borderColor, styleDisplayName
출력: 합성 이미지 base64
라이브러리: Sharp
```

### 레이아웃

```
┌──────────────────────────────┐
│         "AX film"            │  100px (헤더, Georgia italic)
├─────────────┬────────────────┤
│  480×640    │   480×640      │  프레임 (둥근 모서리 16px)
│  Frame 0    │   Frame 1      │
├─────────────┼────────────────┤  20px 간격
│  Frame 2    │   Frame 3      │
├─────────────┴────────────────┤
│   날짜  ✦  스타일명          │  120px (푸터)
│ ═════════════════════════════│  8px (액센트 라인)
└──────────────────────────────┘
총 크기: 1076 × 1520px
```

### 로직
1. 각 프레임을 480×640으로 리사이즈 (`fit: "cover"`)
2. SVG 마스크로 둥근 모서리 적용 (`dest-in` 블렌드)
3. 흰색 캔버스 생성
4. Sharp `composite()`로 레이어 합성:
   - "AX film" 텍스트 (프리셋 border_color)
   - 4개 프레임 (계산된 좌표에 배치)
   - 날짜 + 스타일명 텍스트
   - 하단 액센트 라인 (border_color, 8px)
5. JPEG quality 92로 출력

### SVG 헬퍼
텍스트, 도형을 SVG 문자열 → Buffer로 변환하여 Sharp에 전달:
```typescript
function svg(width, height, content): Buffer
  → Buffer.from(`<svg ...>${content}</svg>`)
```

---

## 5. API 라우트 — `app/api/generate/route.ts`

```
POST /api/generate
입력: { imageBase64: string, styleId: string }
출력: { resultImage: string, frames: string[] }
```

### 처리 순서
1. 입력 검증 (imageBase64, styleId 필수)
2. data URI prefix 제거 (`data:image/...;base64,` 부분)
3. `getPreset(styleId)` → 프리셋 조회
4. `analyzeFace(imageBase64)` → 얼굴 분석
5. `buildPrompts(face, preset)` → 프롬프트 4개 생성
6. `generateImages(prompts, imageBase64)` → 이미지 4장 생성
7. 실패 프레임 → `createPlaceholder()` (1024×1024 회색 이미지)
8. `compositeGrid(frames, borderColor, displayName)` → 합성
9. JSON 응답 반환

### 에러 처리
- 400: 필수 파라미터 누락, 알 수 없는 스타일
- 500: 내부 오류 (OpenAI API 에러 등)

---

## 6. 프론트엔드 — `app/photo-booth/page.tsx`

### 상태 머신
```
idle ──[파일 업로드]──▶ uploaded ──[스타일 선택]──▶ style_selected
                                                        │
                                                  [생성하기 클릭]
                                                        │
                                                        ▼
                                                   generating
                                                    │       │
                                              [성공]▼       ▼[실패]
                                               done       error
                                                │           │
                                          [다시 만들기]  [다시 시도]
                                                │           │
                                                ▼           ▼
                                              idle    style_selected
```

### 주요 기능
| 기능 | 구현 |
|---|---|
| 이미지 업로드 | 드래그앤드롭 + 파일 선택 (accept: image/*) |
| 리사이즈 | Canvas API, max 1024px, JPEG 0.9 |
| 용량 제한 | 1MB 초과 시 에러 |
| 스타일 카드 | `/api/presets` GET → 5개 카드 렌더링 |
| 카드 썸네일 | `/references/{style_id}.jpg` (Next.js Image) |
| 선택 하이라이트 | border_color 테두리 + scale(1.05) |
| 생성 요청 | POST `/api/generate` |
| 로딩 UI | 스피너 + 단계별 메시지 (타이머 기반) |
| 결과 표시 | base64 → img src |
| 다운로드 | base64 → Blob → `<a download>` |
| 요청 제한 | 세션당 MAX_REQUESTS = 5 |

---

## 7. 프리셋 데이터 — `data/pose_presets.json`

### 구조
```json
{
  "style_id": "sailor_moon",
  "display_name": "세일러문 네컷",
  "border_color": "#f9a8d4",
  "base_prompt": {
    "background": "...",
    "lighting": "...",
    "color_grading": "...",
    "shot_type": "close-up to upper body"
  },
  "frames": [
    {
      "frame_index": 0,
      "expression": "confident smile, pointing finger forward",
      "pose": "one hand pointing at camera",
      "pose_description_ko": "세일러문 전용 피스",
      "detailed_pose_description": "GPT-4o로 사전 분석한 상세 포즈 묘사..."
    }
    // ... 3개 더
  ]
}
```

### detailed_pose_description
- `scripts/analyze-references.mjs`로 생성
- GPT-4o Vision이 레퍼런스 이미지를 분석하여 포즈를 텍스트로 변환
- 이미지 생성 시 레퍼런스 이미지 대신 이 텍스트를 프롬프트에 삽입

---

## 8. 모듈 의존 관계

```
page.tsx (프론트엔드)
  │
  ├─▶ GET /api/presets ──▶ lib/presets.ts ──▶ data/pose_presets.json
  │
  └─▶ POST /api/generate (route.ts)
        │
        ├─▶ lib/presets.ts ──▶ data/pose_presets.json
        ├─▶ lib/analyze.ts ──▶ lib/openai.ts
        ├─▶ lib/prompt-builder.ts
        ├─▶ lib/generate-image.ts ──▶ lib/openai.ts
        └─▶ lib/composite.ts

types/index.ts ──▶ 모든 lib 파일에서 import
lib/openai.ts ──▶ analyze.ts, generate-image.ts에서 공유
```
