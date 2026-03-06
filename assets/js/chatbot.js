/**
 * OttO봇 챗봇 프론트엔드.
 *
 * Vanilla JS + HTML5 (프레임워크 없이 독립 동작).
 * KAPLAY 게임 화면 위에 오버레이로 렌더링됩니다.
 *
 * 구성:
 * ① ChatbotConfig (상수)
 * ② 상태 관리 (모듈 스코프 변수)
 * ③ UI 구조 생성 (initChatbot)
 * ④ 히스토리 복원 (loadHistory)
 * ⑤ 메시지 렌더링 (addMessage, renderProductCards)
 * ⑥ API 통신 (sendMessage, fetchGameItems, requestBodyAnalysis)
 * ⑦ 이벤트 핸들러
 * ⑧ 초기화
 */

// =========================================================================
// ① ChatbotConfig (상수)
// =========================================================================

const CHATBOT_CONFIG = {
  API_BASE: "/api/chat",
  USER_ID: "guest",
  MAX_HISTORY: 10,
  PLACEHOLDER: "패션에 대해 물어보세요...",
  BOT_NAME: "OttO봇",
  WELCOME_MSG:
    "안녕하세요! 저는 AI 패션 어드바이저 OttO봇입니다! " +
    "체형 분석, 코디 추천, 게임 아이템 연동까지 도와드릴게요 😊",
  IMG_FALLBACK: "https://via.placeholder.com/300x400?text=No+Image",
  // 서버 /static 경로 불존재 문제 방지 → 외부 URL 사용
};

// =========================================================================
// ② 상태 관리 (모듈 스코프 변수)
// =========================================================================

// session_id: localStorage에서 복원하여 대화 맥락 유지.
// 최초 서버 응답에서 확정값을 받아 갱신.
// 새로고침 후에도 대화 맥락 유지를 위해 localStorage 사용.
let sessionId = localStorage.getItem("chatbot_session_id") || null;

// ChatTurn 배열. 최대 MAX_HISTORY 유지.
// 새로고침 시 loadHistory()로 서버에서 복원.
// TODO 8단계: ChatResponse에 truncated_history 포함 시
// 서버 응답으로 클라이언트 history 동기화하는 구조로 개선 가능
let history = [];

// POST 중복 요청 방지 Lock.
// finally 블록에서 반드시 false로 해제.
let isRequesting = false;

// GET 요청 AbortController.
// 새 요청 전 이전 요청 abort() 호출.
let abortController = null;

// 입력 라우팅 상태.
// "normal"        : 기본 sendMessage → POST /api/chat
// "awaiting_body" : 체형 분석 대기 → requestBodyAnalysis 호출
// [체형 분석] 버튼 클릭 시 "awaiting_body"로 전환,
// 전송 완료 시 "normal"로 복귀.
let inputMode = "normal";

// 사용자 메타데이터 (체형, 선호도 등).
// session_id와 동일한 영속성: localStorage에서 복원/저장.
// 새로고침 후에도 체형 분석 결과(body_type 등) 유지.
// 저장 시점: requestBodyAnalysis 응답에서 body_type 수신 시.
// 예: { body_type: "wave", height: 165, weight: 55 }
let userMeta = JSON.parse(
  localStorage.getItem("chatbot_user_meta") || "{}"
);

// 챗봇 창 최초 오픈 여부 플래그.
// WELCOME_MSG 또는 loadHistory 중복 실행 방지.
// 토글 버튼 클릭 시 isInitialized가 false일 때만
// 초기화 로직(loadHistory/WELCOME_MSG)을 실행.
let isInitialized = false;

// =========================================================================
// ③ UI 구조 생성
// =========================================================================

function initChatbot() {
  // --- 컨테이너 ---
  const container = document.createElement("div");
  container.id = "chatbot-container";
  Object.assign(container.style, {
    position: "fixed",
    bottom: "20px",
    right: "20px",
    zIndex: "9999",
    fontFamily: "'Noto Sans KR', sans-serif",
  });

  // --- 토글 버튼 ---
  const toggleBtn = document.createElement("button");
  toggleBtn.id = "chatbot-toggle-btn";
  toggleBtn.textContent = "👗";
  Object.assign(toggleBtn.style, {
    width: "56px",
    height: "56px",
    borderRadius: "50%",
    background: "#6366f1",
    color: "#fff",
    border: "none",
    fontSize: "24px",
    cursor: "pointer",
    boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
  });

  // --- 채팅창 ---
  const chatWindow = document.createElement("div");
  chatWindow.id = "chatbot-window";
  Object.assign(chatWindow.style, {
    display: "none",
    width: "360px",
    height: "520px",
    borderRadius: "16px",
    boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
    background: "#fff",
    flexDirection: "column",
    overflow: "hidden",
    position: "absolute",
    bottom: "68px",
    right: "0",
  });

  // --- 헤더 ---
  const header = document.createElement("div");
  header.id = "chatbot-header";
  Object.assign(header.style, {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 16px",
    background: "#6366f1",
    color: "#fff",
    fontWeight: "bold",
    fontSize: "15px",
  });
  const titleSpan = document.createElement("span");
  titleSpan.textContent = CHATBOT_CONFIG.BOT_NAME;
  const closeBtn = document.createElement("button");
  closeBtn.textContent = "\u2715";
  Object.assign(closeBtn.style, {
    background: "none",
    border: "none",
    color: "#fff",
    fontSize: "16px",
    cursor: "pointer",
  });
  header.appendChild(titleSpan);
  header.appendChild(closeBtn);

  // --- 메시지 영역 ---
  const messages = document.createElement("div");
  messages.id = "chatbot-messages";
  Object.assign(messages.style, {
    flex: "1",
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    padding: "12px",
    background: "#fafafa",
  });

  // --- 퀵 버튼 영역 ---
  const quickBtns = document.createElement("div");
  quickBtns.id = "chatbot-quick-btns";
  Object.assign(quickBtns.style, {
    display: "flex",
    gap: "6px",
    padding: "8px 12px",
    flexWrap: "wrap",
    borderTop: "1px solid #e5e7eb",
    background: "#fff",
  });

  const btnStyle = {
    background: "#ede9fe",
    color: "#6366f1",
    border: "none",
    borderRadius: "16px",
    padding: "4px 12px",
    cursor: "pointer",
    fontSize: "13px",
  };

  const bodyBtn = document.createElement("button");
  bodyBtn.textContent = "📐 체형 분석";
  Object.assign(bodyBtn.style, btnStyle);

  const recommendBtn = document.createElement("button");
  recommendBtn.textContent = "👗 코디 추천";
  Object.assign(recommendBtn.style, btnStyle);

  const gameBtn = document.createElement("button");
  gameBtn.textContent = "🎮 게임 연동";
  Object.assign(gameBtn.style, btnStyle);

  quickBtns.appendChild(bodyBtn);
  quickBtns.appendChild(recommendBtn);
  quickBtns.appendChild(gameBtn);

  // --- 입력 영역 ---
  const inputArea = document.createElement("div");
  inputArea.id = "chatbot-input-area";
  Object.assign(inputArea.style, {
    display: "flex",
    gap: "8px",
    padding: "8px 12px",
    borderTop: "1px solid #e5e7eb",
    background: "#fff",
  });

  const input = document.createElement("textarea");
  input.id = "chatbot-input";
  input.placeholder = CHATBOT_CONFIG.PLACEHOLDER;
  input.rows = 1;
  Object.assign(input.style, {
    flex: "1",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    padding: "8px",
    resize: "none",
    fontSize: "14px",
    height: "40px",
    fontFamily: "inherit",
    outline: "none",
  });

  const sendBtn = document.createElement("button");
  sendBtn.id = "chatbot-send-btn";
  sendBtn.textContent = "↑";
  Object.assign(sendBtn.style, {
    background: "#6366f1",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    padding: "8px 14px",
    cursor: "pointer",
    fontSize: "16px",
    flexShrink: "0",
  });

  inputArea.appendChild(input);
  inputArea.appendChild(sendBtn);

  // --- 조립 ---
  chatWindow.appendChild(header);
  chatWindow.appendChild(messages);
  chatWindow.appendChild(quickBtns);
  chatWindow.appendChild(inputArea);
  container.appendChild(chatWindow);
  container.appendChild(toggleBtn);
  document.body.appendChild(container);

  // =====================================================================
  // ⑦ 이벤트 핸들러
  // =====================================================================

  // 토글 버튼 클릭 시 채팅창 토글
  toggleBtn.addEventListener("click", () => {
    const isHidden = chatWindow.style.display === "none";
    chatWindow.style.display = isHidden ? "flex" : "none";

    // isInitialized 플래그:
    // 최초 오픈 시에만 loadHistory/WELCOME_MSG 실행.
    // 이후 토글(닫기/열기)에서는 중복 실행 방지.
    if (isHidden && !isInitialized) {
      isInitialized = true;
      if (sessionId) {
        loadHistory();
      } else {
        addMessage("assistant", CHATBOT_CONFIG.WELCOME_MSG, null);
      }
    }
  });

  // 닫기 버튼
  closeBtn.addEventListener("click", () => {
    chatWindow.style.display = "none";
  });

  // 전송 버튼 클릭
  sendBtn.addEventListener("click", () => {
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    sendMessage(text);
  });

  // textarea Enter → 전송 (Shift+Enter는 줄바꿈 허용)
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      input.value = "";
      sendMessage(text);
    }
  });

  // [체형 분석] 버튼
  bodyBtn.addEventListener("click", () => {
    inputMode = "awaiting_body";
    addMessage(
      "assistant",
      "키, 몸무게, 체형을 알려주세요! " +
      "(예: 키 165cm, 몸무게 55kg, 허리가 잘록한 편)",
      null
    );
  });

  // [코디 추천] 버튼
  recommendBtn.addEventListener("click", () => {
    sendMessage("오늘 코디 추천해줘");
  });

  // [게임 연동] 버튼
  gameBtn.addEventListener("click", () => {
    fetchGameItems();
  });
}

// =========================================================================
// ④ 히스토리 복원
// =========================================================================

async function loadHistory() {
  if (abortController) abortController.abort();
  abortController = new AbortController();

  try {
    const res = await fetch(
      `${CHATBOT_CONFIG.API_BASE}/history/${sessionId}`,
      { signal: abortController.signal }
    );
    const data = await res.json();

    // [유연한 파싱 로직]
    // 백엔드 GET /api/chat/history/{id}는 list[ChatTurn] 반환.
    // JSON 루트가 배열([])일 수도, {turns:[]} 객체일 수도 있음.
    // Array.isArray 체크로 두 구조 모두 안전하게 처리.
    const turns = Array.isArray(data) ? data : data.turns || [];

    if (turns.length > 0) {
      turns.forEach((turn) => {
        addMessage(turn.role, turn.content, null);
        history.push({ role: turn.role, content: turn.content });
      });
    } else {
      // 히스토리 없으면 WELCOME_MSG 출력
      addMessage("assistant", CHATBOT_CONFIG.WELCOME_MSG, null);
    }
  } catch (err) {
    if (err.name === "AbortError") return;
    // 히스토리 조회 실패 시 WELCOME_MSG 폴백 (서비스 연속성)
    addMessage("assistant", CHATBOT_CONFIG.WELCOME_MSG, null);
  }
}

// =========================================================================
// ⑤ 메시지 렌더링
// =========================================================================

function addMessage(role, content, recommendations) {
  const messagesEl = document.getElementById("chatbot-messages");
  if (!messagesEl) return;

  // 말풍선 래퍼
  const wrapper = document.createElement("div");
  Object.assign(wrapper.style, {
    display: "flex",
    justifyContent: role === "user" ? "flex-end" : "flex-start",
  });

  // 말풍선
  const bubble = document.createElement("div");
  Object.assign(bubble.style, {
    maxWidth: "80%",
    padding: "8px 12px",
    fontSize: "13px",
    lineHeight: "1.5",
    wordBreak: "break-word",
    whiteSpace: "pre-wrap",
    ...(role === "user"
      ? {
        alignSelf: "flex-end",
        background: "#6366f1",
        color: "#fff",
        borderRadius: "12px 12px 2px 12px",
      }
      : {
        alignSelf: "flex-start",
        background: "#f3f4f6",
        color: "#111",
        borderRadius: "12px 12px 12px 2px",
      }),
  });
  bubble.textContent = content;

  wrapper.appendChild(bubble);
  messagesEl.appendChild(wrapper);

  // 상품 카드 렌더링
  if (recommendations && recommendations.length > 0) {
    renderProductCards(recommendations);
    // 카드 렌더링 후 다시 스크롤 (카드 높이만큼 추가)
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // 자동 스크롤
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function preloadProductImages(recommendations) {
  const TIMEOUT = 3000; // 3초 이내 로드 안 되면 스킵
  const urls = recommendations.map(
    (item) => item.image_url || CHATBOT_CONFIG.IMG_FALLBACK
  );
  return Promise.all(
    urls.map(
      (url) =>
        new Promise((resolve) => {
          const img = new Image();
          const timer = setTimeout(resolve, TIMEOUT);
          img.onload = () => { clearTimeout(timer); resolve(); };
          img.onerror = () => { clearTimeout(timer); resolve(); };
          img.src = url;
        })
    )
  );
}

function renderProductCards(recommendations) {
  const messagesEl = document.getElementById("chatbot-messages");
  if (!messagesEl) return;

  // 가로 스크롤 카드 컨테이너
  const cardsWrapper = document.createElement("div");
  cardsWrapper.className = "product-cards-wrap";
  Object.assign(cardsWrapper.style, {
    overflowX: "auto",
    display: "flex",
    gap: "10px",
    padding: "8px 0",
  });

  recommendations.forEach((item) => {
    const card = document.createElement("div");
    card.className = "product-card";
    Object.assign(card.style, {
      minWidth: "140px",
      border: "1px solid #e5e7eb",
      borderRadius: "10px",
      overflow: "hidden",
      flexShrink: "0",
      background: "#fff",
    });

    const img = document.createElement("img");
    img.src = item.image_url || CHATBOT_CONFIG.IMG_FALLBACK;
    Object.assign(img.style, {
      width: "140px",
      height: "160px",
      objectFit: "cover",
      display: "block",
    });
    // onerror=null: 폴백 이미지도 실패 시 무한 루프 방지
    img.onerror = function () {
      this.onerror = null;
      this.src = CHATBOT_CONFIG.IMG_FALLBACK;
    };

    // 카드 바디
    const cardBody = document.createElement("div");
    cardBody.className = "card-body";
    Object.assign(cardBody.style, {
      padding: "8px",
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
    });

    // 상품명 (2줄 말줄임)
    const nameEl = document.createElement("p");
    nameEl.className = "product-name";
    nameEl.textContent = item.name || "";
    Object.assign(nameEl.style, {
      fontSize: "12px",
      margin: "0 0 4px",
      overflow: "hidden",
      display: "-webkit-box",
      WebkitLineClamp: "2",
      WebkitBoxOrient: "vertical",
      color: "inherit",
      textDecoration: "none",
    });

    // 브랜드
    const brandEl = document.createElement("p");
    brandEl.className = "product-brand";
    brandEl.textContent = item.brand || "";
    Object.assign(brandEl.style, {
      fontSize: "11px",
      color: "#888",
      margin: "0 0 4px",
      textDecoration: "none",
    });

    // 가격 (원화 locale)
    const priceEl = document.createElement("p");
    priceEl.className = "product-price";
    priceEl.textContent = item.price_krw
      ? `${item.price_krw.toLocaleString()}원`
      : "";
    Object.assign(priceEl.style, {
      fontSize: "13px",
      fontWeight: "bold",
      margin: "0 0 6px",
      color: "#111",
      textDecoration: "none",
    });

    cardBody.appendChild(nameEl);
    cardBody.appendChild(brandEl);
    cardBody.appendChild(priceEl);

    if (item.source_url) {
      const wrapperLink = document.createElement("a");
      wrapperLink.href = item.source_url;
      wrapperLink.target = "_blank";
      wrapperLink.rel = "noopener noreferrer";
      Object.assign(wrapperLink.style, {
        textDecoration: "none",
        color: "inherit",
        display: "block",
        cursor: "pointer",
        transition: "transform 0.2s allow-discrete",
      });
      // hover animation (simple workaround without external stylesheet)
      wrapperLink.onmouseover = () => { wrapperLink.style.transform = "scale(0.98)"; };
      wrapperLink.onmouseout = () => { wrapperLink.style.transform = "scale(1)"; };

      wrapperLink.appendChild(img);
      wrapperLink.appendChild(cardBody);
      card.appendChild(wrapperLink);
    } else {
      card.appendChild(img);
      card.appendChild(cardBody);
    }

    cardsWrapper.appendChild(card);
  });

  messagesEl.appendChild(cardsWrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// =========================================================================
// ⑥ API 통신
// =========================================================================

async function sendMessage(message) {
  if (!message || !message.trim()) return;

  // [inputMode 라우팅]
  // "awaiting_body" 상태면 체형 분석 엔드포인트로 분기.
  // 전송 즉시 "normal"로 복귀하여 다음 입력은 일반 대화로 처리.
  if (inputMode === "awaiting_body") {
    inputMode = "normal";
    await requestBodyAnalysis(message);
    return;
  }

  // [Lock 메커니즘] 중복 클릭/연속 Enter 방지
  if (isRequesting) return;
  isRequesting = true;

  document.getElementById("chatbot-input").value = "";
  addMessage("user", message, null);
  history.push({ role: "user", content: message });
  showTypingIndicator();

  try {
    const res = await fetch(`${CHATBOT_CONFIG.API_BASE}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: CHATBOT_CONFIG.USER_ID,
        message: message,
        session_id: sessionId,
        // 최대 MAX_HISTORY 턴만 전송 (토큰 비용 통제)
        // TODO: 서버 truncated_history 응답으로 동기화 개선 가능
        history: history.slice(-CHATBOT_CONFIG.MAX_HISTORY),
        user_meta: userMeta,
        // 체형 분석 결과 등 누적 메타데이터 포함.
        // localStorage에서 복원되므로 새로고침 후에도 유지.
      }),
    });

    // 서버 에러 응답 처리 (4xx, 5xx)
    if (!res.ok) {
      console.error("[OttO봇] API 에러:", res.status, res.statusText);
      removeTypingIndicator();
      addMessage(
        "assistant",
        "서버에서 오류가 발생했어요. 잠시 후 다시 시도해주세요.",
        null
      );
      return;
    }

    const data = await res.json();
    console.log("[OttO봇] API 응답:", JSON.stringify(data).substring(0, 500));

    // session_id: 최초 응답에서 서버 확정값 저장.
    // 이후 모든 요청에 포함하여 대화 맥락 유지.
    if (data.session_id) {
      sessionId = data.session_id;
      localStorage.setItem("chatbot_session_id", sessionId);
    }

    // 상품 추천이 있으면 이미지를 먼저 프리로드한 후 메시지 표시
    const recs = data.recommendations;
    if (recs && Array.isArray(recs) && recs.length > 0) {
      console.log("[OttO봇] 추천 상품 수:", recs.length);
      try {
        await preloadProductImages(recs);
      } catch (_) { /* 프리로드 실패해도 계속 진행 */ }
    } else {
      console.log("[OttO봇] 추천 상품 없음. recommendations:", typeof recs, recs);
    }

    removeTypingIndicator();
    addMessage("assistant", data.response, recs || null);
    history.push({ role: "assistant", content: data.response });
  } catch (err) {
    removeTypingIndicator();
    addMessage(
      "assistant",
      "잠시 오류가 발생했어요. 다시 시도해주세요.",
      null
    );
  } finally {
    isRequesting = false; // Lock 반드시 해제
  }
}

async function fetchGameItems() {
  // AbortController: 버튼 연타 시 이전 요청 취소
  if (abortController) abortController.abort();
  abortController = new AbortController();

  try {
    const res = await fetch(
      `${CHATBOT_CONFIG.API_BASE}/game-items/${CHATBOT_CONFIG.USER_ID}`,
      { signal: abortController.signal }
    );
    const data = await res.json();

    if (data.count > 0) {
      const names = data.items
        .slice(0, 3)
        .map((i) => i.name)
        .join(", ");
      addMessage(
        "assistant",
        `게임에서 담으신 아이템: [${names}] 외 ${data.count}개\n` +
        "이 아이템들과 어울리는 옷을 추천해드릴까요?",
        null
      );
    } else {
      addMessage(
        "assistant",
        data.message || "담은 아이템이 없어요.",
        null
      );
    }
  } catch (err) {
    if (err.name === "AbortError") return;
    addMessage("assistant", "게임 데이터를 불러오지 못했어요.", null);
  }
}

async function requestBodyAnalysis(description) {
  if (isRequesting) return;
  isRequesting = true;

  document.getElementById("chatbot-input").value = "";
  addMessage("user", description, null);
  showTypingIndicator();

  try {
    const res = await fetch(`${CHATBOT_CONFIG.API_BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: CHATBOT_CONFIG.USER_ID,
        session_id: sessionId,
        description: description,
        history: history.slice(-CHATBOT_CONFIG.MAX_HISTORY),
      }),
    });
    const data = await res.json();

    // body_type → userMeta 저장 + localStorage 동기화.
    // 새로고침 후 선언부에서 자동 복원됨.
    // session_id와 동일한 영속성 보장.
    if (data.body_type) {
      userMeta.body_type = data.body_type;
      localStorage.setItem("chatbot_user_meta", JSON.stringify(userMeta));
    }

    if (data.session_id) {
      sessionId = data.session_id;
      localStorage.setItem("chatbot_session_id", sessionId);
    }

    removeTypingIndicator();
    addMessage("assistant", data.response, null);
    history.push({ role: "assistant", content: data.response });
  } catch (err) {
    removeTypingIndicator();
    addMessage("assistant", "체형 분석 중 오류가 발생했어요.", null);
  } finally {
    isRequesting = false;
  }
}

// =========================================================================
// ⑧ 로딩 인디케이터
// =========================================================================

let typingEl = null;

function showTypingIndicator() {
  const messagesEl = document.getElementById("chatbot-messages");
  if (!messagesEl || typingEl) return;

  typingEl = document.createElement("div");
  Object.assign(typingEl.style, {
    display: "flex",
    justifyContent: "flex-start",
  });

  const bubble = document.createElement("div");
  Object.assign(bubble.style, {
    padding: "8px 16px",
    fontSize: "13px",
    background: "#f3f4f6",
    color: "#888",
    borderRadius: "12px 12px 12px 2px",
    animation: "chatbot-pulse 1.4s ease-in-out infinite",
  });
  bubble.textContent = "답변을 생성하고 있어요...";

  typingEl.appendChild(bubble);
  messagesEl.appendChild(typingEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function removeTypingIndicator() {
  if (typingEl) {
    typingEl.remove();
    typingEl = null;
  }
}

// pulse 애니메이션 주입
(function injectChatbotStyle() {
  if (document.getElementById("chatbot-anim-style")) return;
  const style = document.createElement("style");
  style.id = "chatbot-anim-style";
  style.textContent = `
    @keyframes chatbot-pulse {
      0%, 100% { opacity: .5; }
      50% { opacity: 1; }
    }`;
  document.head.appendChild(style);
})();

// =========================================================================
// ⑨ 초기화
// =========================================================================

document.addEventListener("DOMContentLoaded", initChatbot);
