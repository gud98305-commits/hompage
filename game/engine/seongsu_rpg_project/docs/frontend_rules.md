# 프론트엔드 규칙 (KAPLAY + 바닐라 JS)

## 기술 스택
- KAPLAY (Kaboom.js), 바닐라 HTML/CSS/JS
- 에셋 URL: /assets/{파일명} (FastAPI StaticFiles 마운트)
  반드시 uvicorn 서버로 구동할 것. Live Server 단독 사용 시 경로 오류 발생.
- 타일 크기: 16x16 (변경 시 명시적 고지)

## 에셋 네이밍 컨벤션
- 타일셋: /assets/tileset_[용도].png
- NPC: /assets/npc_[역할]_[번호].png
- 플레이어: /assets/player.png
- 맵 데이터: /assets/map_[구역명].json

## KAPLAY 생명주기 (반드시 이 순서 준수)

// 1단계: 초기화
kaplay({ crisp: true, scale: 2, letterbox: true })

// 2단계: 전역 에셋 로드 (scene 외부에서만)
loadSprite("player", "/assets/player.png")

// 3단계: 전역 상태 선언
let isDummyMode = false
// 해제 조건: 맵 재로딩 성공 시에만 false 전환.
// 씬 진입 시 자동 리셋 절대 금지.
let currentSceneId = 0

// 4단계: scene() 정의
scene("main", () => {
  const mySceneId = ++currentSceneId
  // isDummyMode 리셋 금지
  abortGetRequests()
  resetLocks()

  // 이벤트 클린업 패턴 (버전 독립적)
  const cleanups = []
  cleanups.push(onUpdate(() => {}))
  cleanups.push(onKeyDown("space", () => {}))
  onDestroy(() => cleanups.forEach(c => c?.cancel?.()))

  // 비동기 작업: 씬 ID 가드 필수
  async function initScene() {
    const data = await safeGet("init", "/api/load/latest")
    if (currentSceneId !== mySceneId) return
  }
  initScene()
})

// 5단계: 전역 onLoad()
onLoad(() => { go("main") })

// 6단계: 시작 씬
go("loading")

## KAPLAY 금지 패턴
- loadSprite를 scene() 내부에 배치 금지
- onLoad()를 scene() 내부에 선언 금지
- scene() 없이 전역에서 add() 금지
- 클래스 상속(extends) 사용 금지
- crisp: true 없이 픽셀 아트 렌더링 금지

## JSON 에러 처리
try {
  const mapData = JSON.parse(rawJson)
  isDummyMode = false  // 성공 시에만 해제
} catch (e) {
  console.error("[JSON 오류 감지:", e.message, "]")
  isDummyMode = true   // 씬 전환으로 리셋되지 않음
  loadDummyMap()
}

## 물리 엔진 규칙
모든 연속적 상태 변화에 반드시 dt() 곱셈 적용.
// ✅ 올바름
player.pos.x += speed * dt()
// ❌ 금지: 프레임 종속 (144Hz에서 충돌 터널링 발생)
player.pos.x += speed

## fetch() 동시성 제어

// GET 전용: AbortController 기반
const getControllers = {}
function abortGetRequests() {
  Object.keys(getControllers).forEach(key => {
    getControllers[key]?.abort()
    delete getControllers[key]
  })
}
async function safeGet(key, url) {
  getControllers[key]?.abort()
  const controller = new AbortController()
  getControllers[key] = controller
  try {
    const res = await fetch(url, { signal: controller.signal })
    return await res.json()
  } catch (e) {
    if (e.name === "AbortError") return null
    throw e
  } finally {
    if (getControllers[key] === controller) delete getControllers[key]
  }
}

// POST/PUT 전용: Lock 기반
// POST/PUT에 AbortController 사용 금지
// (백엔드 커밋은 계속 진행 → 상태 불일치 발생)
const postLocks = {}
function resetLocks() {
  Object.keys(postLocks).forEach(key => postLocks[key] = false)
}
async function lockCall(key, fn) {
  if (postLocks[key]) return
  if (isDummyMode) {
    console.warn("[Save 차단] 더미 모드에서는 저장 불가")
    return
  }
  postLocks[key] = true
  try { return await fn() }
  finally { postLocks[key] = false }
}

## fetch() 허용 이벤트
- 저장/불러오기 버튼 클릭
- 씬 전환 중 저장
- NPC 상점 거래 완료
- 실시간 이동·충돌·60fps 루프: 절대 금지

## 절대 금지 요약
- ❌ game.js에서 수치 직접 계산
- ❌ isDummyMode를 씬 진입 시 자동 리셋
- ❌ isDummyMode = true 상태에서 Save API 호출
- ❌ POST/PUT에 AbortController 사용
- ❌ GET에 lockCall() 사용
- ❌ dt() 없이 연속 상태 변화 코드 작성
- ❌ 씬 내부 비동기 함수에 씬 ID 가드 없이 전역 상태 변경
- ❌ 씬 내부 이벤트 cleanup 배열 없이 등록
- ❌ 게임 루프(onUpdate/60fps) 안에서 fetch() 호출
