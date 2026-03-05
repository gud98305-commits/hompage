# OttO봇 챗봇 시스템 상세 문서

> 문제 수정 전 기초작업용 문서. 챗봇 아키텍처, 스키마, 파이프라인, 에러 처리 전반을 정리함.

---

## 파일 구조

```
backend/services/chatbot_advanced/
├── chat_service.py          # 메인 오케스트레이션 (1,016줄)
├── chat_schemas.py          # Pydantic V2 스키마 7개 (279줄)
├── chat_routes.py           # FastAPI 엔드포인트 5개 (135줄)
├── chat_db.py               # SQLite async 세션 (47줄, 스키마 미정의)
├── rag_engine.py            # Corrective RAG 6단계 파이프라인 (427줄)
├── body_analyzer.py         # 체형 분석 GPT+키워드 (339줄)
├── product_adapter.py       # ai_curator 브릿지 (357줄)
├── game_adapter.py          # 게임 DB 연동 + 도메인 변환 (297줄)
├── input_sanitizer.py       # 프롬프트 인젝션 탐지 (110줄)
├── llm_intent_classifier.py # LLM 의도 분류 (164줄)
└── logger.py                # 구조화 JSON 로깅 (139줄)

관련 파일:
├── backend/routes/chatbot.py          # 레거시 REST 엔드포인트 (deprecated)
├── backend/services/chatbot.py        # 레거시 chat 서비스 (폴백용)
└── assets/js/chatbot.js               # 프론트엔드 채팅 위젯 (23.7KB)
```

---

## 아키텍처 레이어

```
[Frontend: chatbot.js]
       ↓ HTTP
[API Routes: chat_routes.py]
       ↓ Depends()
[Service: chat_service.py - 6단계 파이프라인]
       ↓
[Intent Classification: Keyword → LLM(planned)]
       ↓
[Handlers: body_analyzer / product_adapter / game_adapter / general]
       ↓
[RAG Engine: 6단계 품질 필터링]
       ↓
[External: OpenAI GPT-4o-mini, ai_curator, Turso DB, data_store]
```

---

## 스키마 정의 (chat_schemas.py)

### IntentType (Enum)

```python
class IntentType(str, Enum):
    BODY_ANALYSIS = "body_analysis"   # 체형 분석
    RECOMMEND     = "recommend"       # 패션 추천
    GAME_ITEMS    = "game_items"      # 게임 아이템 연동
    GENERAL       = "general"         # 일반 대화
```

### ChatTurn

```python
class ChatTurn(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str   # 1~4096자
```

### ChatRequest (메인 요청)

```python
class ChatRequest(BaseModel):
    user_id: str                       # 필수, min_length=1
    message: str                       # 필수, 1~4096자
    session_id: str | None = None      # 첫 요청 시 None → 서버가 UUID 생성
    history: list[ChatTurn] = []       # 최대 50턴 (DoS 방지)
    user_meta: dict = {}               # {body_type, height, weight, ...}
```

### ChatResponse (메인 응답)

```python
class ChatResponse(BaseModel):
    response: str                                    # 텍스트 답변
    recommendations: list[ProductItem] | None        # 상품 추천 목록
    intent: IntentType                               # 분류된 의도
    session_id: str                                  # 클라이언트 반드시 저장
    body_type: str | None                            # "wave"/"straight"/"neutral"
```

### ProductItem (추천 상품)

```python
class ProductItem(BaseModel):
    item_id: str
    name: str
    brand: str
    category: str              # top/bottom/outer/dress/shoes/accessory
    colors: list[str]          # BeforeValidator 정제
    price_jpy: int
    price_krw: int
    image_url: str | None      # 깨진 URL 가능 → 프론트 onError 필요
    source_url: str | None
    reason: str = ""
    score: float | None        # RAG 평가 점수 (소수 2자리)
    mall: str
```

### CuratorRequest (ai_curator 브릿지)

```python
class CuratorRequest(BaseModel):
    body_type: str | None      # "wave"/"straight"/"neutral"
    color: str | None
    style: str | None
    keyword: str | None
    category: str | None       # top/bottom/outer/dress/shoes/accessory
    price_min: int | None
    price_max: int | None
    page: int = 1
    page_size: int = 10        # ≤ 100
```

### BodyAnalysisRequest

```python
class BodyAnalysisRequest(BaseModel):
    user_id: str
    session_id: str | None
    history: list[ChatTurn] = []
    height: float | None       # 50~250cm
    weight: float | None       # 20~300kg
    description: str | None    # 최대 1000자, 자연어
```

### GameItem

```python
class GameItem(BaseModel):
    item_id: str
    name: str
    category: str              # top/bottom/outer/dress/shoes/accessory
    color: str | None
    brand: str | None
    saved_at: str | None       # timestamp
```

---

## API 엔드포인트 (chat_routes.py)

| 엔드포인트 | 메서드 | 설명 | 요청 | 응답 |
|-----------|--------|------|------|------|
| `/api/chat` | POST | 메인 대화 | `ChatRequest` | `ChatResponse` |
| `/api/chat/analyze` | POST | 체형 분석 | `BodyAnalysisRequest` | `ChatResponse` |
| `/api/chat/recommend/{user_id}` | GET | 추천 조회 | path: user_id | `ChatResponse` |
| `/api/chat/game-items/{user_id}` | GET | 게임 아이템 | path: user_id | `dict` |
| `/api/chat/history/{session_id}` | GET | 대화 이력 | path: session_id | `list[ChatTurn]` |

### 의존성 주입

```python
@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse
```

### session_id 프로토콜

```
1. 클라이언트 첫 요청: session_id = null
2. 서버: uuid4() 생성 → ChatResponse.session_id에 포함
3. 클라이언트: localStorage["chatbot_session_id"]에 저장
4. 이후 모든 요청에 session_id 포함
5. 누락 시: 매 요청마다 새 세션 → 컨텍스트 유실
```

---

## 메인 파이프라인 (chat_service.py → process_chat)

```
┌──────────────────────────────────────────────────────┐
│ Step 1: session_id 확인                                │
│   └─ None이면 uuid.uuid4() 생성                       │
├──────────────────────────────────────────────────────┤
│ Step 2: 입력 정제 (InputSanitizer.sanitize)            │
│   ├─ 인젝션 패턴 탐지 → (False, msg) 반환 시 차단 응답   │
│   ├─ 길이 제한 (2000자)                                │
│   └─ 제어문자 제거 (\t, \n 제외)                        │
├──────────────────────────────────────────────────────┤
│ Step 3: 히스토리 절삭                                   │
│   └─ 최근 10턴만 유지 (수신 최대 50턴 중)                │
├──────────────────────────────────────────────────────┤
│ Step 4: 의도 분류 (classifier.classify)                 │
│   ├─ KeywordIntentClassifier (현재 기본)               │
│   └─ LLMIntentClassifier (Stage 7, 계획)              │
├──────────────────────────────────────────────────────┤
│ Step 5: 핸들러 라우팅 (_route)                          │
│   ├─ BODY_ANALYSIS → _handle_body_analysis()          │
│   ├─ RECOMMEND     → _handle_recommend()              │
│   ├─ GAME_ITEMS    → _handle_game_items()             │
│   └─ GENERAL       → _handle_general()                │
├──────────────────────────────────────────────────────┤
│ Step 6: ChatResponse 구성 및 반환                       │
│   └─ {response, recommendations, intent,              │
│       session_id, body_type}                          │
└──────────────────────────────────────────────────────┘
```

---

## 의도 분류 시스템

### KeywordIntentClassifier (현재 기본)

```python
# 키워드 → 의도 매핑
GAME_KEYWORDS      = {"게임", "담은 옷", "인벤토리", "보관함"}
BODY_KEYWORDS      = {"체형", "웨이브", "스트레이트", "뉴트럴", "골격", "분석"}
RECOMMEND_KEYWORDS = {"추천", "어울리는", "코디", "입을", "스타일"}

# 우선순위: GAME_ITEMS → BODY_ANALYSIS → RECOMMEND → GENERAL
# 예외: GAME + RECOMMEND 동시 매칭 → RECOMMEND 우선
```

### Context Carry-over (후속 대화 유지)

```python
# 현재 의도가 GENERAL일 때, 마지막 assistant 메시지에서 의도 추출
_RECOMMEND_FOLLOWUP = {"색상", "사이즈", "예산"}
_BODY_FOLLOWUP      = {"골격", "체형"}
_GAME_FOLLOWUP      = {"인벤토리", "보관함"}

# 동작: 이전 대화 의도를 이어받아 GENERAL 대신 해당 의도 반환
```

### LLMIntentClassifier (Stage 7, 계획)

```python
# GPT-4o-mini로 전체 히스토리 기반 분류
# temperature=0, max_tokens=10
# 최근 5턴 (각 100자 제한)
# 실패 시 → KeywordIntentClassifier로 폴백

# Stage 8 Cascade (계획):
# KeywordClassifier 먼저 실행 → GENERAL일 때만 GPT 호출
# 예상 80% 비용 절감
```

### 초기화 및 폴백

```python
get_chat_service() → ChatService(classifier=LLMIntentClassifier())
# LLMIntentClassifier.__init__():
#   OPENAI_API_KEY 확인 → 없으면 gpt_enabled=False
#   → 자동으로 KeywordIntentClassifier로 폴백
```

---

## 핸들러 상세

### _handle_general()

```
- OpenAI GPT-4o-mini 직접 호출
- 시스템 프롬프트: "You are OttO bot. Fashion advice in Korean, 3 sentences max"
- 컨텍스트: 최근 10턴 (각 200자 제한)
- max_tokens=300
- API 키 없으면 → 기본 소개 텍스트 반환
```

### _handle_body_analysis()

```
- BodyAnalyzer.analyze(BodyAnalysisRequest) 호출
- 반환: (response_text, None, body_type_str)
- 스타일 가이드 + 후속 추천 유도 메시지 출력
- 유효성 오류 → 사용자 친화적 메시지
```

### _handle_recommend()

```
1. user_meta에서 body_type 추출
2. 메시지에서 category 추출 (CATEGORY_MAP 키워드 매칭)
3. CuratorRequest 구성
4. get_products_by_curator() → ai_curator 호출
5. rag_engine.run() 통과
6. body_type 가이드 포함 응답 생성
7. RAG "no_result" → 친화적 거절 메시지
```

### _handle_game_items()

```
1. game_adapter.get_game_repo().get_saved_items(user_id) 호출
2. GameItem → CuratorRequest 변환 (GameItemToProductAdapter)
3. product_adapter.get_products_by_curator() 호출
4. RAG "no_result" → Broad Search Fallback:
   - search_products_simple(color + body_type, category, limit=5)
5. rag_engine.run() 통과
6. 게임 아이템명 포함 응답 생성
7. 에러 메시지: 게임 미연동, 저장 아이템 없음, 검색 실패
```

---

## 체형 분석 (body_analyzer.py)

### BodyType Enum

```python
class BodyType(str, Enum):
    WAVE     = "wave"       # 곡선형: 하체 발달, 허리 잘록
    STRAIGHT = "straight"   # 직선형: 상체 발달, 허리 짧음
    NEUTRAL  = "neutral"    # 균형형: 상하체 균형
```

### 분석 흐름

```
1. 입력 검증: description, height, weight 중 최소 1개 필요
   - height: 50~250cm / weight: 20~300kg

2. GPT 경로 (OPENAI_API_KEY 있을 때):
   - 시스템 프롬프트: "한국 패션 스타일리스트, wave/straight/neutral 중 하나만 반환"
   - 모델: gpt-4o-mini, temperature=0, max_tokens=10
   - 파싱 실패 → 키워드 폴백
   - GPT 오류 → 키워드 폴백

3. 키워드 폴백:
   WAVE_KEYWORDS     = {"곡선", "웨이브", "골반", "허리", "플레어", ...}
   STRAIGHT_KEYWORDS = {"직선", "스트레이트", "어깨", "각", ...}
   NEUTRAL_KEYWORDS  = {"균형", "뉴트럴", "보통", "평균", ...}
   - 서브스트링 매칭 (한국어 조사 대응)
   - 최다 매칭 타입 반환 (동점 → NEUTRAL)

4. 스타일 가이드 출력:
   WAVE:     "곡선형 체형 → 플레어 스커트, A라인 원피스, 랩 스타일"
   STRAIGHT: "직선형 체형 → 테일러드 재킷, 와이드 팬츠, 레이어드 룩"
   NEUTRAL:  "균형 체형 → 다양한 스타일 가능"
```

---

## Corrective RAG 엔진 (rag_engine.py)

### 6단계 파이프라인

```
Step 1: 빈 결과 확인
  └─ 상품 0건 → RAGEngineError("no_result")

Step 2: GPT 사용 가능 여부
  └─ API 키 없음 → score 기준 정렬 후 그대로 반환

Step 3: Top-N 품질 사전 평가
  └─ 상위 3개(TOP_N_EVAL_COUNT) 상품 평가
  └─ 모두 score ≥ 3.0(RELEVANCE_THRESHOLD) → GPT 스킵, 바로 반환

Step 4: GPT 관련성 평가
  └─ GPT-4o-mini로 무관 상품 식별 → item_id 리스트 JSON 반환
  └─ 무관 상품 제거
  └─ 전부 제거됨 → RAGEngineError("filtered_empty")

Step 5: 쿼리 정제 + 재검색
  └─ 임계값 미달 시 (시도 ≤ MAX_REFINEMENT_ATTEMPTS=2):
     ├─ GPT로 keyword/category 재구성
     ├─ 중복 결과 감지 (item_id 집합 비교)
     └─ 중복 발견 시 조기 반환

Step 6: 최종 반환
  └─ 필터링 없음 → 원본 반환
  └─ 필터링 결과 0건 → RAGEngineError
  └─ 필터링 결과 있음 → 필터링 결과 반환
```

### 상수

```python
RELEVANCE_THRESHOLD      = 3.0   # 이 미만이면 GPT 필터링 발동
TOP_N_EVAL_COUNT         = 3     # 사전 평가 상품 수
MAX_REFINEMENT_ATTEMPTS  = 2     # 쿼리 정제 재시도 횟수
```

---

## 상품 어댑터 (product_adapter.py)

### 구조 (DIP 패턴)

```python
class ProductRepository(Protocol):          # 인터페이스
    async def find_by_curator(request: CuratorRequest) -> list[ProductItem]
    async def find_by_id(item_id: str) -> ProductItem | None
    async def search_simple(keyword, category, limit) -> list[ProductItem]

class SEOULFITProductRepository:            # 구현체
    # backend.services.ai_curator 연동
    # data_store 캐시 (TTL=300초)
```

### 캐시 매니저

```python
class CacheManager:
    ttl_seconds = 300          # 5분 TTL
    is_expired() → bool
    invalidate() → None        # 강제 초기화
    async get_products()       # asyncio.to_thread 래퍼
```

### 카테고리 매핑

```python
CATEGORY_MAP = {
    # 상의
    "상의": "top", "티셔츠": "top", "맨투맨": "top",
    "니트": "top", "블라우스": "top", "셔츠": "top",
    # 하의
    "하의": "bottom", "바지": "bottom", "슬랙스": "bottom",
    "청바지": "bottom", "스커트": "bottom", "반바지": "bottom",
    # 아우터
    "아우터": "outer", "코트": "outer", "자켓": "outer",
    "점퍼": "outer", "패딩": "outer", "가디건": "outer",
    # 원피스
    "원피스": "dress", "드레스": "dress",
    # 신발
    "신발": "shoes", "구두": "shoes", "스니커즈": "shoes",
    "부츠": "shoes", "샌들": "shoes", "로퍼": "shoes",
    # 악세사리
    "악세사리": "accessory", "가방": "accessory", "벨트": "accessory",
}
```

---

## 게임 어댑터 (game_adapter.py)

### Turso DB 연동

```python
class TursoGameItemRepository:
    # turso_db.InventoryItem 조회
    async def get_saved_items(user_id: str, session, limit=10):
        # user_id → int 파싱
        # inventory_items 테이블 조회
        # Turso 필드 → GameItem 매핑
        # 에러: "not_found", "query_failed", "empty"
```

### 도메인 변환 매핑

```python
# 게임 카테고리 → 패션 카테고리
GAME_TO_FASHION_CATEGORY = {
    "갑옷": "outer",    "코트 오브": "outer",   "망토": "outer",
    "로브": "top",      "셔츠 오브": "top",     "튜닉": "top",
    "레깅스": "bottom", "바지 오브": "bottom",
    "드레스": "dress",  "가운": "dress",
    "부츠": "shoes",    "샌들": "shoes",        "슬리퍼": "shoes",
}

# 게임 속성 → 패션 키워드
GAME_TO_FASHION_KEYWORD = {
    "전설의": "프리미엄",  "마법사의": "포멀",
    "전사의": "캐주얼",    "용사의": "스트리트",
    "어둠의": "블랙",      "빛의": "화이트",
    "화염의": "레드",      "얼음의": "블루",
}
```

### GameItemToProductAdapter

```python
@staticmethod
def to_curator_request(items: list[GameItem], body_type, page_size):
    # 1. 카테고리 빈도 분석 → 최빈 카테고리
    # 2. 전체 아이템의 name + color 결합 → keyword 생성
    # 3. 첫 번째 color 추출 → color 파라미터
    # → CuratorRequest 반환
```

---

## 입력 정제 (input_sanitizer.py)

### 인젝션 패턴

```python
INJECTION_PATTERNS = [
    # 시스템 명령 우회
    "시스템 명령", "system prompt", "system message",
    "프롬프트 출력", "명령을 무시", "ignore previous",

    # 역할 탈취
    "개발자 모드", "developer mode", "debug mode",
    "jailbreak", "탈옥", "역할을 바꿔",

    # 민감 데이터 탈취
    "api key", "api 키", "openai key",
    "시스템 프롬프트를 보여",

    # 페르소나 파괴
    "OttO봇가 아니", "다른 ai", "gpt로 동작",
    "너의 진짜 정체",
]
```

### 정제 프로세스

```python
def sanitize(message: str) -> tuple[bool, str]:
    # 1. INJECTION_PATTERNS 대소문자 무시 매칭
    #    탐지 시 → (False, message) 반환
    # 2. 길이 제한: 2000자
    # 3. 제어문자 제거 (\t, \n 제외)
    # 정상 → (True, cleaned_message)
```

### 차단 응답

```
"저는 패션 조언만 도와드릴 수 있어요!
코디 추천이나 체형 분석을 원하시면 말씀해주세요 😊"
```

---

## 로깅 시스템 (logger.py)

### 출력 형식

```json
{
  "timestamp": "ISO8601",
  "level": "ERROR|WARNING|CRITICAL",
  "module": "chat_service|rag_engine|...",
  "event": "gpt_fallback|db_error|...",
  "detail": {}
}
```

### 이벤트 종류

| 이벤트 | 레벨 | 설명 |
|--------|------|------|
| `gpt_fallback` | ERROR | GPT 실패 → 폴백 전환 |
| `db_error` | ERROR | Game DB / SQLite 오류 |
| `rag_filtered_empty` | WARNING | RAG 필터링 후 0건 |
| `injection_detected` | WARNING | 인젝션 시도 감지 |
| `api_key_missing` | CRITICAL | OPENAI_API_KEY 미설정 |

---

## 예외 처리 체계

```
ChatServiceError (base)
├── IntentClassifyError        # 의도 분류 실패
├── RAGEngineError             # RAG 엔진 오류
│   └── code: "no_result" | "filtered_empty" | "gpt_eval_failed"
│            | "refinement_failed" | "timeout" | "parse" | "unknown"
├── BodyAnalysisError          # 체형 분석 오류
│   └── code: "gpt_failed" | "parse_failed" | "insufficient"
└── GameDBError                # 게임 DB 오류
    └── code: "not_found" | "query_failed" | "empty"
```

### FastAPI 예외 핸들러

```python
@app.exception_handler(ChatServiceError)
→ JSONResponse(status_code=422, content={"error": message, "detail": detail})
```

---

## DB 스키마

### ChatDB (chat_db.py) — 현재 스텁

```python
DATABASE_URL = "sqlite+aiosqlite:///./data/chatbot_history.db"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession)

# TODO: ChatHistory 테이블 미정의
# 예상 필드: session_id, user_id, role, content, created_at
# get_chat_history() → 현재 빈 리스트 반환
```

### Game Inventory (turso_db.py) — 외부 Turso DB

```
테이블: inventory_items
├── id: str
├── user_id: int
├── name: str
├── category: str
├── colors: list[str]
├── brand: str | None
└── obtained_at: str
```

### Product Data (data_store)

```
소스: data/products_enriched.json
필드: id, name, brand, category, colors,
      price_jpy, price_krw, main_image, source_url, mall
```

---

## 프론트엔드 연동 (chatbot.js)

### 설정

```javascript
const CHATBOT_CONFIG = {
  API_BASE: "/api/chat",
  USER_ID: "guest",
  MAX_HISTORY: 10,
  PLACEHOLDER: "패션에 대해 물어보세요...",
  BOT_NAME: "OttO봇",
  WELCOME_MSG: "안녕하세요! AI 패션 어드바이저 OttO봇입니다!...",
  IMG_FALLBACK: "https://via.placeholder.com/300x400?text=No+Image",
};
```

### 상태 관리

```javascript
let sessionId    = localStorage.getItem("chatbot_session_id") || null
let history      = []                // ChatTurn 배열
let isRequesting = false             // POST 중복 방지
let abortController = null           // GET 취소 핸들
let inputMode    = "normal"          // "normal" | "awaiting_body"
let userMeta     = JSON.parse(
  localStorage.getItem("chatbot_user_meta") || "{}"
)
let isInitialized = false            // 최초 열기 플래그
```

### UI 구성

```
- 토글 버튼: 56x56px 원형, 👗 이모지
- 채팅 창: 360x520px, indigo(#6366f1) 헤더
- 퀵 버튼: "📐 체형 분석", "👗 코디 추천", "🎮 게임 연동"
- 입력 영역: Textarea + Send 버튼
- 상품 카드: 가로 스크롤 갤러리
```

### 주요 함수

```javascript
initChatbot()                          // UI 초기화
loadHistory()                          // GET /api/chat/history/{sessionId}
sendMessage(text)                      // POST /api/chat
requestBodyAnalysis()                  // POST /api/chat/analyze
fetchGameItems()                       // GET /api/chat/game-items/{userId}
addMessage(role, content, recs)        // 메시지 렌더링
renderProductCards(recommendations)    // 상품 카드 가로 스크롤
preloadProductImages(urls)             // 병렬 이미지 프리로드 (3초 타임아웃)
```

### 이미지 에러 처리

```javascript
img.onerror = function() {
  this.onerror = null;  // 무한 루프 방지
  this.src = CHATBOT_CONFIG.IMG_FALLBACK;
};
```

---

## 전체 데이터 흐름

```
┌──────────────────────────────────────────────────┐
│              Frontend (chatbot.js)                │
│                                                   │
│  sessionId + history + message                    │
│         ↓ POST /api/chat                          │
│  ChatResponse ← response + recommendations       │
│         ↓                                         │
│  renderProductCards() (가로 스크롤 갤러리)           │
└──────────────────────────────────────────────────┘
                     ↓ HTTP
┌──────────────────────────────────────────────────┐
│         FastAPI Router (chat_routes.py)           │
│  Depends(get_chat_service) & Depends(get_db)     │
└──────────────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────┐
│          ChatService.process_chat()               │
│                                                   │
│  1. session_id 확인/생성                           │
│  2. InputSanitizer.sanitize()                     │
│  3. history[-10:] 절삭                             │
│  4. classifier.classify() → IntentType            │
│  5. _route() → _handle_*()                        │
│  6. ChatResponse 구성                              │
└──────────────────────────────────────────────────┘
                     ↓
    ┌────────────────┼────────────────┐
    ↓                ↓                ↓
┌────────┐   ┌────────────┐   ┌────────────┐
│BODY    │   │RECOMMEND   │   │GAME_ITEMS  │
│ANALYSIS│   │            │   │            │
│        │   │ ai_curator │   │ Turso DB   │
│ GPT /  │   │     ↓      │   │     ↓      │
│Keyword │   │ RAG Engine │   │ 도메인 변환  │
│        │   │     ↓      │   │     ↓      │
│→Style  │   │ ProductItem│   │ ai_curator │
│  Guide │   │   list     │   │     ↓      │
└────────┘   └────────────┘   │ RAG Engine │
                              │     ↓      │
                  ┌───────┐   │ ProductItem│
                  │GENERAL│   │   list     │
                  │       │   └────────────┘
                  │Direct │
                  │GPT    │
                  │Call   │
                  └───────┘
```

---

## 환경 변수

| 변수 | 용도 | 챗봇 영향 |
|------|------|----------|
| `OPENAI_API_KEY` | OpenAI API | 없으면 전체 GPT 비활성 → 키워드 전용 모드 |
| `TURSO_DATABASE_URL` | Turso DB | 게임 아이템 조회 불가 |
| `TURSO_AUTH_TOKEN` | Turso 인증 | 게임 아이템 조회 불가 |

**참고:** API 키 변경 시 서버 재시작 필요 (런타임 리로드 없음)

---

## 의존성 주입 & 테스트

### 싱글턴 팩토리

```python
get_chat_service()   → ChatService 인스턴스
get_body_analyzer()  → BodyAnalyzer 인스턴스
get_rag_engine()     → CorrectiveRAGEngine 인스턴스
get_sanitizer()      → InputSanitizer 인스턴스
get_logger()         → ChatbotLogger 인스턴스
```

### 테스트 오버라이드

```python
# Protocol 기반 DIP → 모킹 가능
app.dependency_overrides[get_chat_service] = lambda: MockChatService()
app.dependency_overrides[get_repo]         = lambda: MockProductRepository()
app.dependency_overrides[get_game_repo]    = lambda: MockGameRepo()
```

---

## 디버깅 체크리스트

| 증상 | 확인 포인트 |
|------|-----------|
| GPT 응답 없음 | `OPENAI_API_KEY` 설정 확인 → 로그에 `api_key_missing` |
| 컨텍스트 유실 | `session_id` localStorage 저장 여부 확인 |
| 의도 오분류 | KeywordIntentClassifier 키워드 매칭 확인 |
| 상품 검색 실패 | ai_curator 동작 여부, data_store 로드 확인 |
| RAG 결과 0건 | `RELEVANCE_THRESHOLD=3.0` 과대 여부 |
| 이미지 깨짐 | 프론트 onError 핸들러 동작 확인 |
| 체형 미저장 | `user_meta` localStorage 확인 |
| 게임 아이템 없음 | `InventoryItem.get_by_user()` 반환값 확인 |
| 대화 이력 미복원 | `GET /api/chat/history` → 스텁 (빈 리스트 반환) |
| 인젝션 차단 오탐 | `INJECTION_PATTERNS` 패턴 검토 |

---

## 미구현 / TODO 항목

| 항목 | 현재 상태 | 비고 |
|------|----------|------|
| ChatHistory 테이블 | 스텁 (빈 리스트 반환) | chat_db.py에 스키마 미정의 |
| LLM Cascade (Stage 8) | 미구현 | Keyword→GENERAL일 때만 GPT |
| truncated_history 응답 | 미구현 | ChatResponse에 동기화용 히스토리 |
| 관리자 캐시 초기화 | 미구현 | DELETE /api/chat/admin/cache |
| BodyType 신뢰도 점수 | 미구현 | (BodyType, float) 튜플 반환 |
| LLM 쿼리 생성 | 미구현 | 키워드 카테고리 추출 → GPT |
| QueueHandler 비동기 로깅 | 미구현 | 메인 루프 블로킹 방지 |
