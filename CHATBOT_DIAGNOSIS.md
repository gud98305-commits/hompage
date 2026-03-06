# OttO봇 챗봇 추천 기능 버그 진단서

## 증상

"오늘 코디 추천해줘" 퀵 버튼 클릭 시:
- 응답 텍스트: "곡선형 체형에 어울리는 상품 5개를 추천드려요! 아래 상품들을 확인해보세요 😊" — **정상 출력**
- 상품 카드: **표시되지 않음**

응답 텍스트에 "5개"라는 숫자가 포함되어 있으므로, 백엔드 `_handle_recommend`의 Step 6까지는 `products` 리스트가 비어있지 않은 상태로 도달한 것으로 판단됨.

---

## 관련 파일 및 코드 경로

| 파일 | 역할 |
|------|------|
| `assets/js/chatbot.js` | 프론트엔드 채팅 위젯 (실제 서빙 파일) |
| `backend/services/chatbot_advanced/chat_service.py` | 메인 파이프라인, `_handle_recommend()` |
| `backend/services/chatbot_advanced/chat_routes.py` | FastAPI 엔드포인트, `response_model=ChatResponse` |
| `backend/services/chatbot_advanced/chat_schemas.py` | Pydantic V2 스키마 정의 |
| `backend/services/chatbot_advanced/product_adapter.py` | ai_curator 브릿지 |
| `backend/services/chatbot_advanced/rag_engine.py` | Corrective RAG 6단계 파이프라인 |
| `backend/services/ai_curator.py` | 메타데이터 스코어링 + OpenAI 추천 이유 생성 |
| `backend/services/data_store.py` | 상품 JSON 로딩 |

---

## 요청 흐름 추적

```
프론트엔드: sendMessage("오늘 코디 추천해줘")
    ↓ POST /api/chat
    body: { user_id: "guest", message: "오늘 코디 추천해줘",
            session_id: "...", history: [...], user_meta: { body_type: "wave" } }
    ↓
chat_routes.py: chat() → service.process_chat(request, session=db)
    ↓
chat_service.py: process_chat()
    Step 1: session_id 확인
    Step 2: InputSanitizer.sanitize() — "오늘 코디 추천해줘"는 인젝션 아님 → 통과
    Step 3: history[-10:] 절삭
    Step 4: classifier.classify() → "추천", "코디" 매칭 → IntentType.RECOMMEND
    Step 5: _route() → _handle_recommend()
    ↓
_handle_recommend() (chat_service.py:625~716)
    Step 1: body_type = request.user_meta.get("body_type") → "wave"
    Step 2: CATEGORY_MAP에서 카테고리 추출 → None (메시지에 카테고리 키워드 없음)
    Step 3: CuratorRequest 구성
            keyword = "오늘 코디 추천해줘"[:100]  ← 문제 지점 ①
            category = None
            body_type = "wave"
            page_size = 5
    Step 4: get_products_by_curator(curator_req)
            → SEOULFITProductRepository.find_by_curator()
            → product_adapter.curate_with_openai() 브릿지 함수
            → ai_curator.curate_with_openai(products, req, page=0, page_size=50)
    Step 5: self.rag_engine.run(products, curator_req)  ← 문제 지점 ②
    Step 6: 응답 텍스트 구성 + return (response, products, None)
    ↓
process_chat() Step 6: ChatResponse 구성  ← 문제 지점 ③
    ChatResponse(
        response=response_text,
        recommendations=recommendations,  ← products 리스트
        intent=IntentType.RECOMMEND,
        session_id=session_id,
        body_type=None,
    )
    ↓
chat_routes.py: return → FastAPI response_model=ChatResponse 직렬화  ← 문제 지점 ④
    ↓
프론트엔드: data.recommendations → addMessage() → renderProductCards()
```

---

## 추정 원인 (우선순위순)

### 가설 A: FastAPI response_model 직렬화에서 recommendations 누락 (가장 유력)

**근거:**
- 응답 텍스트에 "5개"가 포함 → `_handle_recommend` Step 6의 `len(products)`가 5 → 백엔드에서 상품 리스트는 존재
- 그런데 프론트에서 카드가 안 보임 → `data.recommendations`가 `null`이거나 빈 배열

**메커니즘:**
- `chat_routes.py:56`에서 `response_model=ChatResponse` 지정
- FastAPI는 응답을 `ChatResponse` 스키마로 재직렬화(validation)함
- `ProductItem` 필수 필드 중 하나라도 Pydantic 검증 실패 시:
  - FastAPI가 해당 필드를 `None`으로 처리하거나
  - 전체 `recommendations`를 `None`으로 폴백할 수 있음
- 특히 의심 필드:
  - `colors: list[str]` — `BeforeValidator` 적용됨, 원본 데이터가 `None`이나 문자열일 경우 실패
  - `price_jpy: int` — 원본 데이터에 값이 없으면 0으로 기본값 설정되나, 브릿지에서 누락 가능
  - `image_url: str | None` — 깨진 URL은 허용되지만 타입 불일치 시 문제

**확인 방법:**
```
브라우저 Network 탭 → POST /api/chat → Response 탭
→ JSON의 "recommendations" 필드 값 확인
→ null이면 이 가설 확정
```

### 가설 B: RAG 엔진이 상품을 전부 필터링

**근거:**
- "오늘 코디 추천해줘"는 구체적 상품 요구가 아님
- RAG `_evaluate_with_gpt()`가 이 모호한 쿼리 기준으로 모든 상품을 "무관"으로 판단할 가능성

**반박:**
- 만약 RAG가 빈 리스트를 반환하면 `_handle_recommend` Step 6의 `if not products:` 분기에서 "조건에 맞는 상품을 찾지 못했어요"가 반환되어야 함
- 실제로는 "5개를 추천드려요"가 출력됨 → RAG 통과 후에도 products가 존재했다는 의미
- **단, RAG의 except 블록이 `pass`이므로** RAG 예외 발생 시 1차 검색 결과가 유지되어 5개가 살아있을 수 있음

**이 가설이 성립하려면:** RAG가 예외 없이 빈 리스트를 반환해야 하는데, 그 경우 "찾지 못했어요"가 출력되어야 하므로 증상과 불일치. → **이 가설은 단독으로는 약함**

### 가설 C: product_adapter 브릿지의 keyword 전달 문제

**근거:**
- `product_adapter.py:62-73`의 브릿지 함수:
  ```python
  req = {
      "keyword": keyword or "",  # ← "오늘 코디 추천해줘"
      "category": category or "all",
      "body_type": body_type or "standard",
      ...
  }
  result = _real_curate(products, req, page=0, page_size=50)
  ```
- `ai_curator._keyword_bonus()`에서 "오늘 코디 추천해줘"가 `K_FASHION_KEYWORD_PROFILES` 키에 없음
- 일반 텍스트 매칭: `_contains_any(text, ["오늘 코디 추천해줘"])` → 상품명에 이 문자열이 통째로 포함된 상품 없음
- 결과: 키워드 보너스 0, 약한 감점(-1.5) 적용

**영향도:** 점수가 낮아질 뿐 필터링되지는 않음 (category="all"이므로). 상품 자체는 반환됨. → **단독 원인은 아니지만 품질 저하의 원인**

### 가설 D: chat_schemas.py의 ProductItem 직렬화 불일치

**근거:**
- `product_adapter._dict_to_product_item()` (product_adapter.py:166-184):
  ```python
  ProductItem(
      item_id=item.get("id", ""),
      name=item.get("name", ""),
      ...
      colors=item.get("colors", []),  # ← 원본이 None이면?
      price_jpy=item.get("price_jpy", 0),  # ← 원본에 이 필드가 없으면?
      ...
  )
  ```
- `ai_curator.curate_with_openai()`의 enriched 딕셔너리에는 원본 상품 dict를 복사(`dict(p)`)하므로 원본 필드명 그대로 유지
- 만약 원본 JSON(`products_enriched.json`)의 이미지 필드가 `main_image`인데 ProductItem이 `image_url`로 매핑하는 과정에서:
  ```python
  image_url=item.get("main_image"),  # ← 필드명은 맞지만 값이 None일 수 있음
  ```
  `image_url: str | None`이므로 None은 허용 → 이 자체는 문제 아님

**가능성:** `colors` 필드의 `BeforeValidator`가 특정 상품 데이터에서 예외를 일으켜 전체 리스트 직렬화 실패 가능. → **가설 A와 연계**

---

## 종합 판단

**가장 유력한 시나리오:**

```
_handle_recommend()가 products 5개를 정상 반환
    ↓
process_chat()에서 ChatResponse(recommendations=products) 구성
    ↓
FastAPI response_model=ChatResponse 직렬화 시
ProductItem 내 특정 필드(colors, price_jpy 등) Pydantic V2 검증 실패
    ↓
recommendations 전체가 null로 폴백
    ↓
프론트엔드: data.recommendations === null → renderProductCards() 미호출
    ↓
텍스트만 표시, 상품 카드 없음
```

---

## 권장 디버깅 순서

1. **브라우저 Network 탭** — `POST /api/chat` 응답 JSON에서 `recommendations` 필드 값 확인
   - `null` → 가설 A 확정 (직렬화 문제)
   - `[]` (빈 배열) → 가설 B (RAG 필터링)
   - `[{...}, ...]` (상품 있음) → 프론트엔드 렌더링 문제

2. **서버 콘솔 DEBUG 로그** — chat_service.py에 이미 3개의 print문 존재:
   ```
   >>> [DEBUG] _handle_recommend: curator_req = ...
   >>> [DEBUG] _handle_recommend: found N products from get_products_by_curator
   >>> [DEBUG] _handle_recommend: found N products after rag_engine
   >>> [DEBUG] _handle_recommend: Returning N products to caller.
   ```
   이 로그로 각 단계별 상품 수 확인 가능

3. **Pydantic 검증 에러** — FastAPI 서버 로그에 `ValidationError` 또는 `422` 관련 경고 확인

4. **products_enriched.json 샘플 검증** — 상위 5개 상품의 필드 구조가 ProductItem 스키마와 일치하는지 확인:
   - `colors`가 `list[str]`인지 (None, 문자열, 중첩 리스트 아닌지)
   - `price_jpy`가 int 변환 가능한지
   - `id` 필드가 존재하는지

---

## 수정 방향 제안

### 즉시 수정 (버그 해결)

1. **chat_routes.py** — `response_model=ChatResponse` 제거하고 직접 dict 반환 또는 `response_model_exclude_none=False` 설정하여 직렬화 실패 원인 격리

2. **_handle_recommend** — keyword에 "오늘 코디 추천해줘" 같은 자연어가 그대로 전달되는 문제 해결:
   ```python
   # 자연어에서 의미없는 토큰 제거 후 keyword 구성
   # 또는 keyword를 비우고 body_type + category만으로 검색
   ```

3. **product_adapter._dict_to_product_item()** — 방어적 변환 강화:
   ```python
   colors = item.get("colors") or []
   if isinstance(colors, str):
       colors = [colors]
   ```

### 구조 개선 (선택)

4. **_handle_recommend Step 5** — RAG 실패 시 `pass` 대신 로깅 추가
5. **keyword 전처리** — 자연어 메시지에서 패션 관련 키워드만 추출하는 전처리 단계 추가

---

## 작업 완료 보고 (AI 처리)

진단서에 기술된 가설 A 및 가설 C를 근거로, 데이터 파싱 오류를 방지하고 추천 정확도를 올리기 위해 다음 코드 수정을 완료했습니다.

### 1. 직렬화(Serialization) 안정성 강화 (`product_adapter.py`)

`product_adapter._dict_to_product_item()` 함수에서 입력값 검증 로직을 추가하여 Pydantic `ChatResponse` 모델로 변환 시 직렬화 오류가 발생하지 않도록 조치했습니다.
- `colors`가 `None`일 경우 `[]` 빈 리스트 처리, 단순 문자열일 경우 `[문자열]` 리스트 래핑 처리.
- `price_jpy`, `price_krw`가 `None`일 경우 기본값 `0` 처리.

```python
def _dict_to_product_item(item: dict, reason: str = "", score: float | None = None) -> ProductItem:
    colors = item.get("colors") or []
    if isinstance(colors, str):
        colors = [colors]
        
    price_jpy = item.get("price_jpy", 0)
    if price_jpy is None:
        price_jpy = 0
        
    price_krw = item.get("price_krw", 0)
    if price_krw is None:
        price_krw = 0

    return ProductItem(...)
```

### 2. 구어체 키워드 필터링 로직 추가 (`chat_service.py`)

`chat_service.py`의 `_handle_recommend()` 메서드에서 "오늘 코디 추천해줘" 같은 발화에 불필요한 동사(예: "해줘", "부탁해", "추천")가 `keyword`로 전송되지 않도록 정제하는 로직을 추가했습니다.
- `KeywordIntentClassifier.RECOMMEND_KEYWORDS`에 포함된 추천 동사 외에도 "해줘", "부탁해", "알려줘", "오늘" 등의 스탑 워드(stop_words)를 제외한 단어만을 조립하여 `keyword`에 담습니다.

```python
        # "오늘 코디 추천해줘" 같은 발화에서 불필요한 동사 제거
        from backend.services.chatbot_advanced.chat_service import KeywordIntentClassifier
        stop_words = KeywordIntentClassifier.RECOMMEND_KEYWORDS | {"해줘", "부탁해", "알려줘", "오늘"}
        cleaned_words = [w for w in request.message.split() if w not in stop_words]
        final_keyword = " ".join(cleaned_words)[:100]

        curator_req = CuratorRequest(
            body_type=body_type,
            keyword=final_keyword,  # 토큰 비용 통제 및 추천 동사 제거
            ...
        )
```

이외의 RAG 필터링 문제나 응답 구조 누락 문제는 런타임 결과 모니터링 후 추가 처리가 필요할 수 있습니다.
현재 코드로 배포 후 "코디 추천해줘" 버그가 완화되는지 확인을 권장합니다.

---

## 2차 분석 — 1차 수정 후에도 증상 지속

### 상황

1차 수정(직렬화 방어 + stop_words 필터링) 적용 후에도 동일 증상 지속:
- "곡선형 체형에 어울리는 상품 5개를 추천드려요!" 텍스트만 출력
- 상품 카드 미표시

### 1차 수정 효과 분석

| 수정 | 효과 | 버그 해결 여부 |
|------|------|--------------|
| `_dict_to_product_item` 방어 강화 | colors/price None 방어 → 유효 | 근본 원인 아닌 것으로 판명 |
| stop_words 필터링 | "오늘 코디 추천해줘" → `""` (빈 문자열) | 키워드 감점 해소 → 추천 품질 개선만, 버그 해결 아님 |

### 코드 레벨 정밀 추적 결과 — 원인 후보 축소

코드 정적 분석으로 확인된 사실:

1. **`chat_schemas.py` 스키마**: `_sanitize_colors` BeforeValidator가 이미 None/비정상 타입을 방어하고 있음. ProductItem 스키마 자체에 직렬화 실패를 유발할 구조적 결함 없음.

2. **`product_adapter.py` 변환 흐름**: `_dict_to_product_item()` → `ProductItem()` 생성 시 Pydantic `ValidationError`가 발생하면 `except (json.JSONDecodeError, KeyError, TypeError)` 블록에 **잡히지 않음** → 처리되지 않은 예외가 상위로 전파. 그러나 이 경우 "5개를 추천드려요" 텍스트까지 도달 불가 → **ValidationError는 발생하지 않은 것으로 판단**

3. **body_type 매핑 불일치 (신규 발견)**:
   - 챗봇 `BodyType`: `wave` / `straight` / `neutral`
   - `ai_curator` `BODY_TYPE_TOKEN_MAP`: `slim` / `athletic` / `curvy` / `standard`
   - `product_adapter` 브릿지: `body_type or "standard"` → `"wave"`가 truthy이므로 `"wave"` 그대로 전달
   - `ai_curator._body_type_bonus("wave")` → `BODY_TYPE_TOKEN_MAP.get("wave")` → **None** → 보너스 0점
   - 영향: 체형 보너스 미적용이지만 상품 반환 자체에는 무관

4. **stop_words 필터링 후 keyword 빈 문자열 문제**:
   - "오늘 코디 추천해줘" → stop_words 제거 → "코디"도 `RECOMMEND_KEYWORDS`에 포함 → **전부 제거되어 `final_keyword = ""`**
   - 빈 keyword → `ai_curator`에서 `_keyword_bonus()` 0점 → 동작에는 문제없음

### 런타임 확인 필수 항목

코드 정적 분석만으로는 원인을 더 이상 축소할 수 없음. 다음 3가지 런타임 확인이 필요:

| 확인 항목 | 방법 | 판별 |
|----------|------|------|
| **응답 JSON 실체** | 브라우저 Network 탭 → `POST /api/chat` → Response | `recommendations`가 `null` / `[]` / `[{...}]` 중 어떤 것인지 |
| **서버 DEBUG 로그** | 서버 콘솔에서 `>>> [DEBUG]` 접두사 로그 4줄 확인 | 각 단계별 상품 수로 소실 지점 특정 |
| **서버 에러 로그** | FastAPI 500 에러, `ValidationError`, `RAGEngineError` 유무 | 직렬화 실패 vs RAG 필터링 vs 기타 |

### 가설 재평가

| 가설 | 1차 판단 | 2차 판단 | 근거 |
|------|---------|---------|------|
| A: FastAPI 직렬화 실패 | 가장 유력 | **가능하나 약화** | `_sanitize_colors` BeforeValidator가 이미 방어 중. 1차 수정으로 추가 방어했으나 미해결 |
| B: RAG 전부 필터링 | 약함 | **재부상** | RAG `filtered_empty` → except에서 `pass` → 1차 검색 결과 유지 → "5개" 출력. 그러나 이후 FastAPI 직렬화 단계에서 별도 문제 가능 |
| C: keyword 전달 문제 | 품질 저하 | **1차에서 수정 완료** | stop_words 필터링 적용됨 |
| D: ProductItem 직렬화 | 가설 A 연계 | **가능하나 약화** | 방어 코드 추가했으나 미해결 |
| **E: (신규) 근본 원인이 코드 외부** | — | **확인 필요** | 데이터 자체 문제, 환경 변수, DB 연결 등 |

### 신규 가설 E: 데이터/환경 문제

가능성:
- `data_store.load_products()` → Turso DB 연결 실패 → JSON fallback → `products_enriched.json` 없음 → 빈 리스트
- 그러나 이 경우 `ai_curator`에서 `{"items": [], "total": 0}` 반환 → `RAGEngineError("no_result")` → "조건에 맞는 상품을 찾지 못했어요" 출력 → 증상과 불일치
- **그러므로 데이터는 정상 로드되고 있음**

### 결론

**코드 정적 분석의 한계에 도달. 런타임 확인 없이는 원인 특정 불가.**

가장 효율적인 디버깅 순서:
1. 브라우저 Network 탭에서 `POST /api/chat` 응답 JSON의 `recommendations` 필드 값 확인
2. 서버 콘솔 `>>> [DEBUG]` 로그 4줄 확인
3. 서버 에러 로그 확인
