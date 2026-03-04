# 인생네컷 AI 생성기 — 최종 기획서 (v4)

## 프로젝트 개요

셀카를 업로드하면 GPT-4o Vision이 외모를 분석하고, gpt-image-1.5가 텍스트 포즈 묘사를 참고하여 인생네컷 스타일 실사 이미지 4장을 생성, 2×2 그리드로 합성하는 웹앱.

| 항목 | 내용 |
|---|---|
| 목적 | 해커톤 데모용 MVP |
| 핵심 컨셉 | "캐릭터의 포즈/표정을 실제 사람이 따라하는 인생네컷" |
| 개발자 | 1인 (팀 6명 중 단독 개발 담당) |
| 마감 | 3/2(일) 완료 → 3/4(화) 모노레포 병합 |
| 원본 셀카 | 서버 메모리에서만 처리, 파일 저장 없음 |

---

## 기술 스택

| 구분 | 기술 |
|---|---|
| Frontend | Next.js 14 (App Router) + Tailwind CSS |
| Backend | Next.js API Routes (Node.js, 올인원) |
| 얼굴 분석 | GPT-4o Vision API |
| 이미지 생성 | gpt-image-1.5 (OpenAI Images API) |
| 이미지 합성 | Sharp (Node.js) |
| 배포 | Vercel |
| UI 언어 | 한국어 |

### 모노레포 병합 관련
- 본 프로젝트: **App Router**로 개발 완료
- 팀 모노레포가 Pages Router 기반일 경우, **본 프로젝트를 역변환하지 않음**
- 대신 모노레포 환경이 App Router를 수용하도록 병합 전략 수정:
  - Next.js 14+는 App Router와 Pages Router **공존 가능** (`app/` + `pages/` 혼용)
  - 본 프로젝트의 `app/photo-booth/`, `app/api/` 경로를 모노레포에 그대로 배치
  - `lib/`, `data/`, `public/references/`는 그대로 이동
- 라우트 경로: `/photo-booth`

```
병합 시 배치:
  app/photo-booth/page.tsx     →  app/photo-booth/page.tsx (그대로)
  app/api/generate/route.ts    →  app/api/generate/route.ts (그대로)
  app/api/presets/route.ts     →  app/api/presets/route.ts (그대로)
  lib/ (그대로)                 →  lib/ (그대로)
  data/ (그대로)                →  data/ (그대로)
  public/references/ (그대로)   →  public/references/ (그대로)
```

### 병합 시 주의사항
- `sharp`, `openai` 패키지를 모노레포 `package.json`에 추가
- `OPENAI_API_KEY` 환경 변수 공유 확인
- Tailwind 설정은 모노레포 기존 설정 따름
- Next.js 버전이 14 미만이면 14+로 업그레이드 필요 (App Router 지원)

---

## 핵심 플로우 (3단계)

```
[1] 셀카 업로드 + 스타일 선택
    └─ 이미지 용량 제한: 1MB 이하
    └─ 클라이언트에서 Canvas로 리사이즈 (max 1024px) + base64 변환
    └─ 선택한 style_id와 함께 서버로 전송
    └─ 세션당 최대 5회 생성 제한

[2] 분석 + 생성 (/api/generate)
    └─ GPT-4o Vision: 셀카 분석 → face_description JSON
        └─ 사람 얼굴 미감지 시 에러 반환
        └─ 여러 명일 경우 주 촬영 대상(가장 크고 중심에 있는 인물) 자동 식별
    └─ 프리셋 로드: style_id → pose_presets.json에서 4프레임 정보
    └─ face_description + preset + detailed_pose_description 병합 → 4개 최종 프롬프트
        └─ 스타일별 고정 파스텔 배경색 적용
        └─ 프레임/테두리/둥근 모서리 생성 금지 지시
    └─ gpt-image-1.5: 셀카 + 프롬프트로 4장 병렬 생성 (1024×1536 portrait)
    └─ Sharp: 2×2 그리드 합성 (인생네컷 스타일)
    └─ base64 결과 반환

[3] 결과 표시 + 다운로드
    └─ 클라이언트에서 결과 이미지 표시
    └─ 다운로드 버튼 제공 (life4cut.jpg)
    └─ 서버에 파일 잔류 없음
```

---

## 프로젝트 구조

```
life4cut/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                      # 루트 페이지 (placeholder)
│   ├── globals.css
│   └── photo-booth/
│       └── page.tsx                  # 메인 UI (업로드 + 스타일 선택 + 결과)
│   └── api/
│       ├── generate/
│       │   └── route.ts              # 분석 + 생성 + 합성 올인원
│       └── presets/
│           └── route.ts              # 스타일 프리셋 목록 API
├── lib/
│   ├── openai.ts                     # OpenAI 클라이언트 싱글턴
│   ├── analyze.ts                    # GPT-4o Vision 분석 (얼굴 감지 포함)
│   ├── generate-image.ts             # gpt-image-1.5 호출 (셀카만 전송)
│   ├── prompt-builder.ts             # face_description + preset → 최종 프롬프트
│   ├── composite.ts                  # Sharp 2×2 인생네컷 스타일 합성
│   └── presets.ts                    # 프리셋 JSON 로더
├── types/
│   └── index.ts                      # FaceDescription, Preset 등 공통 타입
├── data/
│   └── pose_presets.json             # 5개 스타일 프리셋 (detailed_pose_description 포함)
├── public/
│   └── references/                   # 5장 캐릭터 포즈 레퍼런스 이미지 (스타일 카드 썸네일용)
│       ├── sailor_moon.jpg
│       ├── kuromi.jpg
│       ├── psyduck.jpg
│       ├── bobby_hill.jpg
│       └── spongebob.jpg
├── scripts/
│   └── analyze-references.mjs        # 레퍼런스 이미지 → 텍스트 묘사 변환 스크립트
├── test-api.mjs                      # API 테스트 스크립트
├── .env.local
├── vercel.json                          # Vercel 배포 설정 (서울 리전)
├── next.config.mjs
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

---

## 환경 변수 (.env.local)

```env
OPENAI_API_KEY=sk-...
```

---

## API 엔드포인트

| Route | Method | Input | Output |
|---|---|---|---|
| `/api/generate` | POST | `{ imageBase64, styleId }` | `{ resultImage: base64 }` |
| `/api/presets` | GET | — | `[{ style_id, display_name, border_color }]` |

---

## GPT-4o Vision 분석 (lib/analyze.ts)

### 시스템 프롬프트

```
You are a photo booth AI assistant. Analyze the uploaded selfie and extract
a detailed physical description for image generation. Return JSON only.

FIRST, check the image:
- If NO human face is found, return: { "error": "no_face" }
- If multiple people are present, identify the MAIN subject (largest face,
  most centered, or most prominent person) and describe ONLY that person.

If a human face IS present:
Focus on: ethnicity/vibe, age range, hair, skin, outfit, accessories, makeup.
Keep descriptions concise and image-generation-friendly.
Do NOT mention the person's name or identity.
```

### 반환 JSON 구조 (FaceDescription)

```json
{
  "appearance": {
    "ethnicity_vibe": "East Asian, Korean aesthetic",
    "age_range": "early 20s",
    "skin": "light skin, smooth complexion",
    "build": "slender"
  },
  "hair": {
    "description": "shoulder-length straight black hair with see-through bangs"
  },
  "face": {
    "eyes": "dark brown eyes, natural lashes",
    "makeup": "natural daily makeup, nude lip tint"
  },
  "outfit": {
    "description": "white oversized cotton shirt",
    "accessories": "small silver stud earrings"
  }
}
```

에러 시: `{ "error": "no_face" }`

---

## 레퍼런스 이미지 활용 방식

### 핵심 전략 (텍스트 묘사 방식)

레퍼런스 이미지를 API 호출 시 매번 전송하지 않고, 사전에 GPT-4o Vision으로 분석하여
`detailed_pose_description` 텍스트로 변환 후 `pose_presets.json`에 저장.
이미지 생성 시 **셀카 + 텍스트 프롬프트**만 전달.

### gpt-image-1.5 호출 구조 (프레임당)

```typescript
const response = await openai.images.edit({
  model: "gpt-image-1.5",
  image: selfieFile,       // 셀카만 전송
  prompt: finalPrompt,     // 텍스트에 포즈 묘사 포함
  n: 1,
  size: "1024x1536",       // 세로형 (인생네컷 비율)
  quality: "medium",
});
```

- 4개 프롬프트를 `Promise.allSettled`로 병렬 호출
- 실패한 프레임은 재시도 1회, 그래도 실패 시 회색 placeholder

### 레퍼런스 이미지 주의사항
- 캐릭터 IP(캐릭터 이름, 작품명)를 프롬프트에 직접 언급하지 않음
- 포즈/표정을 텍스트로 상세 묘사하여 전달
- 결과물은 실사(photorealistic)여야 하며, 캐릭터 스타일이 섞이면 안 됨
- 프레임, 테두리, 둥근 모서리 등 장식 요소를 이미지에 포함시키지 않도록 지시

---

## 프롬프트 빌드 로직 (lib/prompt-builder.ts)

### 2레이어 병합 + 텍스트 포즈 묘사

```
Layer 1: 스타일 프리셋 (pose_presets.json)
         — 분위기, 조명, 프레임별 포즈/표정, detailed_pose_description

Layer 2: GPT-4o 분석 결과 (FaceDescription)
         — 외모, 헤어, 의상, 액세서리 묘사

+ 스타일별 고정 파스텔 배경색 (pose_presets.json의 backdrop_color)
+ 셀카: 얼굴/외모의 시각적 가이드 (이미지 입력)
```

### 스타일별 고정 배경색

| style_id | 배경색 |
|---|---|
| sailor_moon | soft pastel pink (#FFB6C1) |
| kuromi | soft pastel lavender (#D8B4FE) |
| psyduck | soft pastel sky blue (#BAE6FD) |
| bobby_hill | soft pastel peach (#FECACA) |
| spongebob | soft pastel yellow (#FEF08A) |

---

## 스타일 프리셋 (pose_presets.json) — 5개

파일 위치: `/data/pose_presets.json`

| style_id | 표시명 | border_color | 컨셉 |
|---|---|---|---|
| `sailor_moon` | 세일러문 네컷 | `#f9a8d4` | 파스텔, 클로즈업, 애교 포즈 |
| `kuromi` | 쿠로미 네컷 | `#7c3aed` | 쿨톤, 엣지+귀여움 혼합 |
| `psyduck` | 고라파덕 네컷 | `#60a5fa` | 혼돈 리액션, 코믹 표정 |
| `bobby_hill` | 바비힐 네컷 | `#92400e` | 실내 캐주얼, 코믹 리액션 |
| `spongebob` | 스폰지밥 네컷 | `#fbbf24` | 밝고 순수, 에너지 넘침 |

각 프리셋에는 GPT-4o Vision으로 사전 분석한 `detailed_pose_description` 필드가 포함되어 있어, 레퍼런스 이미지 없이도 포즈를 정확히 재현 가능.

---

## 이미지 합성 (lib/composite.ts)

### Sharp 2×2 인생네컷 스타일 그리드

```
┌──────────────────────────────┐
│         "AX film"            │  ← 헤더 (Georgia italic, border_color)
├──────────────┬───────────────┤
│   Frame 0    │   Frame 1     │  ← 480×640, 둥근 모서리 (16px)
├──────────────┼───────────────┤
│   Frame 2    │   Frame 3     │
├──────────────┴───────────────┤
│    2026.03.01  ✦  스타일명    │  ← 푸터 (날짜 + 스타일명)
│ ═════════════════════════════│  ← 하단 액센트 라인 (border_color)
└──────────────────────────────┘
```

### 합성 스펙

```typescript
const FRAME_W = 480;
const FRAME_H = 640;
const GAP = 20;
const PADDING_X = 48;
const PADDING_TOP = 100;
const PADDING_BOTTOM = 120;
const ROUND_RADIUS = 16;

const CANVAS_W = PADDING_X * 2 + FRAME_W * 2 + GAP;   // 1076
const CANVAS_H = PADDING_TOP + FRAME_H * 2 + GAP + PADDING_BOTTOM;  // 1520
```

- 배경색: 흰색
- 헤더: "AX film" (Georgia italic, 프리셋 border_color)
- 프레임: 둥근 모서리 (SVG dest-in 마스크)
- 푸터: 날짜 + 스타일명
- 하단 액센트 라인: 프리셋 border_color (8px)
- 출력 포맷: JPEG (quality 92)
- base64로 인코딩하여 클라이언트로 반환

---

## /api/generate 처리 흐름

```typescript
export async function POST(req: Request) {
  // 1. 입력 파싱 + 검증
  const { imageBase64, styleId } = await req.json();

  // 2. 프리셋 로드
  const preset = getPreset(styleId);

  // 3. GPT-4o Vision 분석 (얼굴 감지 + 주 대상 식별)
  const faceDescription = await analyzeFace(imageBase64);

  // 4. 프롬프트 빌드 (face + preset + 고정 배경색)
  const prompts = buildPrompts(faceDescription, preset);

  // 5. gpt-image-1.5 4장 병렬 생성 (셀카만 전송)
  const frameResults = await generateImages(prompts, imageBase64);

  // 6. 실패 프레임 → 회색 placeholder 대체 (캐싱됨)
  const placeholder = await getPlaceholder();
  const frameImages = frameResults.map(r => r.success ? r.imageBase64 : placeholder);

  // 7. Sharp 인생네컷 스타일 합성
  const resultImage = await compositeGrid(frameImages, preset.border_color, preset.display_name);

  // 8. 반환 (서버에 파일 잔류 없음, resultImage만 반환하여 페이로드 최소화)
  return NextResponse.json({ resultImage });
}
```

---

## 프론트엔드 UI (app/photo-booth/page.tsx)

### 화면 구성 (단일 페이지, 한국어)

```
┌──────────────────────────────────────────┐
│          📸 인생네컷 AI 생성기            │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │                                    │  │
│  │     셀카를 업로드해주세요            │  │
│  │     (드래그 앤 드롭 / 클릭)         │  │
│  │     (1MB 이하)                     │  │
│  │                                    │  │
│  └────────────────────────────────────┘  │
│                                          │
│  스타일을 선택해주세요:                    │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐│
│  │세일 │ │쿠로 │ │고라 │ │바비 │ │스폰 ││
│  │러문 │ │ 미  │ │파덕 │ │ 힐  │ │지밥 ││
│  │(썸네│ │(썸네│ │(썸네│ │(썸네│ │(썸네││
│  │ 일) │ │ 일) │ │ 일) │ │ 일) │ │ 일) ││
│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘│
│                                          │
│         [ 🎬 생성하기 ]                   │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │     생성 결과 (2×2 그리드)          │  │
│  └────────────────────────────────────┘  │
│                                          │
│    [ 📥 다운로드 ]  [ 🔄 다시 만들기 ]    │
│                                          │
└──────────────────────────────────────────┘
```

### UI 상태 흐름

```
idle → uploaded → style_selected → generating → done
                                       │
                                       └─ error (재시도 가능)
```

### 입력 검증
- 이미지 타입: `image/*`만 허용
- 이미지 용량: 1MB 이하 제한
- 얼굴 감지: 사람 얼굴 미감지 시 에러 ("사람 얼굴이 감지되지 않았습니다")
- 다수 인물: 주 촬영 대상 자동 식별하여 진행
- 요청 횟수: 세션당 최대 5회 제한 (API 남용 방지)

### 생성 중 프로그레스 메시지 (한/일 병행, 60초 커버)

```
"📸 셀카를 분석하고 있어요... (セルカを分析中...)"                    (0~3초)
"🎨 예쁘게 그리는 중이에요! (可愛く描いています！)"                  (3~8초)
"✨ 인화지에 잉크를 채우는 중... (インクを注入中...)"                 (8~14초)
"💖 거의 다 됐어요, 조금만 기다려주세요! (もう少しお待ちください！)"   (14~20초)
"🌟 세상에 하나뿐인 네컷 완성 직전! (完成直前！)"                    (20~30초)
"⏳ 마무리 작업 중이에요... (仕上げ中...)"                           (30~40초)
"🎀 거의 완성이에요! (もうすぐ完成！)"                               (40~50초)
"📷 최종 보정 중... (最終補正中...)"                                 (50초~)
```

### 주요 인터랙션
- 셀카 업로드: 드래그앤드롭 + 파일 선택 (accept: image/*)
- 업로드 시 클라이언트에서 Canvas 리사이즈 (max 1024px) + base64 변환
- 스타일 선택: 5개 카드 (레퍼런스 이미지 썸네일 + 스타일명 + border_color 하이라이트)
- 생성 중: 스피너 + 단계별 프로그레스 메시지
- 결과: 2×2 인생네컷 그리드 이미지 + 다운로드 (life4cut.jpg) + 다시 만들기

---

## 비용 추정 (1회 생성)

```
GPT-4o Vision 분석:        ~$0.01
gpt-image-1.5 × 4장:      ~$0.16–0.24 (medium quality)
총:                        ~$0.17–0.25/회
```

---

## Vercel 배포 시 주의사항

- **실행 리전:** 서울 (`icn1`)로 설정 (`vercel.json`의 `"regions": ["icn1"]`)
  - 기본값(미국 동부 iad1) 대비 한국 사용자 응답 시간 대폭 단축
- **Function 타임아웃:** `maxDuration = 60` 설정 적용 (`route.ts`)
  - GPT-4o Vision (~3초) + gpt-image-1.5 ×4 병렬 (~15초) + Sharp (~2초) ≈ 20초
  - 60초 내 충분히 처리 가능
- Sharp: Vercel Serverless Function에서 사용 가능
- Payload 크기: request body 4.5MB 제한
  - 셀카 base64 (~1MB 이하, 클라이언트에서 제한) → OK
  - 응답: `resultImage`만 반환 (개별 프레임 미포함, 페이로드 최소화)
- 환경 변수: Vercel Dashboard에서 OPENAI_API_KEY 설정

---

## 보안 / 개인정보

- 원본 셀카: 서버 메모리에서만 처리, 디스크/클라우드 저장 없음
- API 호출 시: OpenAI 서버에 전송 (OpenAI 데이터 정책 적용)
- 생성 결과: base64로 클라이언트에 반환, 서버에 미저장
- 레퍼런스 이미지: public 폴더에 정적 호스팅 (스타일 카드 썸네일용)
- 요청 제한: 세션당 최대 5회 (API 남용 방지)
- 사전 고지: 업로드 영역에 개인정보 처리 안내 문구 상시 표시
  - "업로드된 사진은 AI 분석 후 즉시 삭제되며, 서버에 저장되지 않습니다."

---

## 플랜B (리스크 대응)

| 리스크 | 대응 |
|---|---|
| gpt-image-1.5 얼굴 유사도 부족 | 프롬프트 튜닝 + quality: "high"로 상향 |
| gpt-image-1.5 API 장애/속도 | Replicate API (FLUX img2img)로 교체 |
| 4컷 간 스타일 불일치 | 고정 파스텔 배경색 + 프롬프트 강화 (구현 완료) |
| Vercel 60초 타임아웃 | quality를 low로 변경 또는 2장씩 순차 생성 |
| Sharp 빌드 이슈 (Vercel) | canvas 패키지 또는 클라이언트 사이드 합성으로 대체 |
