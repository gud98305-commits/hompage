// ═══════════════════════════════════════════════════════
//  Pixel Seongsu Adventure  –  game.js
// ═══════════════════════════════════════════════════════

// ── 1. 엔진 초기화 ──
kaplay({
  width: 800,
  height: 480,
  crisp: true,
  letterbox: true,
  background: [42, 46, 68],
})

setGravity(0)

// ── 2. 에셋 로딩 ──
// 주인공 스프라이트시트 (4x4)
loadSprite("player_char", "/assets/player_spritesheet.png", {
  sliceX: 4,
  sliceY: 4,
  anims: {
    "walk-left":  { from: 0, to: 3, speed: 8, loop: true },
    "walk-left2": { from: 4, to: 7, speed: 8, loop: true },
    "walk-right": { from: 8, to: 11, speed: 8, loop: true },
    "walk-right2":{ from: 12, to: 15, speed: 8, loop: true },
    "idle-left":  { from: 0, to: 0 },
    "idle-right": { from: 8, to: 8 },
  }
})

// 배경
loadSprite("bg_city", "/assets/final_back.jpg")
loadSprite("graffiti_wall", "/assets/graffiti_wall.png")
loadSprite("road", "/assets/road.png")

// 건물들
loadSprite("building_dior",        "/assets/building_dior.png")
loadSprite("building_onion",       "/assets/building_onion.png")
loadSprite("building_tamburins",   "/assets/building_tamburins.png")
loadSprite("building_musinsa",     "/assets/building_musinsa.png")
loadSprite("building_blueelephant","/assets/building_blueelephant.png")
loadSprite("building_covernat",    "/assets/building_covernat.png")
loadSprite("building_pointofview", "/assets/building_pointofview.png")
loadSprite("building_nyunyu",      "/assets/building_nyunyu.png")
loadSprite("building_matinkim",    "/assets/building_matinkim.png")
loadSprite("building_adererror",   "/assets/building_adererror.png")
loadSprite("building_popup1",      "/assets/building_popup1.png")
loadSprite("building_popup2",      "/assets/building_popup2.png")
loadSprite("building_photoism",    "/assets/building_photoism.png")
loadSprite("building_zenmon",      "/assets/building_zenmon.png")
loadSprite("building_zenmon_popup","/assets/building_zenmon_popup.png")
loadSprite("building_random1",     "/assets/building_random1.png")
loadSprite("building_random2",     "/assets/building_random2.png")
loadSprite("building_random3",     "/assets/building_random3.png")
loadSprite("building_random4",     "/assets/building_random4.png")
loadSprite("building_random5",     "/assets/building_random5.png")
loadSprite("building_random6",     "/assets/building_random6.png")
loadSprite("building_random7",     "/assets/building_random7.png")

// NPC (캐릭터 시트를 슬라이싱해서 첫 프레임만 사용)
loadSprite("npc_hoodie_boy",    "/assets/npc_hoodie_boy.png",    { sliceX: 5, sliceY: 2 })
loadSprite("npc_phone_girl",    "/assets/npc_phone_girl.png",    { sliceX: 4, sliceY: 2 })
loadSprite("npc_headphone_girl","/assets/npc_headphone_girl.png",{ sliceX: 3, sliceY: 2 })
loadSprite("npc_colorful_boy",  "/assets/npc_colorful_boy.png",  { sliceX: 2, sliceY: 1 })
loadSprite("npc_walking_boy",   "/assets/npc_walking_boy.png",   { sliceX: 3, sliceY: 2 })
loadSprite("npc_pink_girl",     "/assets/npc_pink_girl.png",     { sliceX: 3, sliceY: 1 })
loadSprite("npc_denim_boy",     "/assets/npc_denim_boy.png",     { sliceX: 2, sliceY: 1 })

// 포장마차
loadSprite("food_cart", "/assets/food_cart.png")

// 거리 소품
loadSprite("street_props", "/assets/street_props.png")

console.log("[ENGINE] 에셋 로딩 요청 완료")

// ── 상수 ──
const BGM_VOLUME = 0.3
const BGM_FADE_IN = 800
const BGM_MUTE = 0.01
const BGM_FADE_OUT = 500
const MAX_SLOTS = 8
const GROUND_Y = 455

// ── 3. 전역 상태 ──
let currentSceneId = 0
let gameState = {
  player_name: "플레이어",
  player_x: -1,
  energy: 100,
  gold: 0,
  inventory: [],
  clothes: [],
  discovered_events: [],
}

// ── 4. 타이틀 화면 (캔버스 위 오버레이) ──
const titleScreen = document.getElementById("title-screen")
const hudEl = document.getElementById("hud")
const invBtn = document.getElementById("inventory-btn")
const clothBtn = document.getElementById("cloth-btn")
const mobileControls = document.getElementById("mobile-controls")

let gameStarted = false
function startGame() {
  console.log("[DEBUG] startGame called, current state:", gameStarted)
  if (gameStarted) return
  gameStarted = true
  titleScreen.style.display = "none"
  hudEl.style.display = "flex"
  invBtn.style.display = "block"
  clothBtn.style.display = "block"
  if ("ontouchstart" in window) {
    mobileControls.style.display = "flex"
  }
  console.log("[DEBUG] Triggering go('main')")
  go("main")
}
function attachTitleListeners() {
  console.log("[DEBUG] Attaching titleScreen listeners")
  
  const handleStart = (e) => {
    console.log("[DEBUG] Interaction detected:", e.type)
    startGame()
  }

  titleScreen.addEventListener("click", handleStart)
  titleScreen.addEventListener("touchstart", (e) => { 
    e.preventDefault(); 
    handleStart(e) 
  }, { passive: false })

  // 전체 화면 클릭 시에도 시작되도록 폴백 (다른 요소가 막고 있을 경우 대비)
  window.addEventListener("click", (e) => {
    if (!gameStarted) {
      console.log("[DEBUG] window fallback click")
      startGame()
    }
  }, { once: true })
}

attachTitleListeners()

// ── 5. 인벤토리 시스템 ──
const invPanel = document.getElementById("inventory-panel")
const invGrid = document.getElementById("inventory-grid")
const invDesc = document.getElementById("inventory-desc")
const invCloseBtn = document.getElementById("inventory-close")
let inventoryOpen = false

const clothPanel = document.getElementById("cloth-panel")
const clothGrid = document.getElementById("cloth-grid")
const clothDesc = document.getElementById("cloth-desc")
const clothCloseBtn = document.getElementById("cloth-close")
let clothOpen = false

const ITEM_DB = {
  coffee:    { type: "general", icon: "\u2615", name: "성수 핸드드립 커피", desc: "어니언에서 만든 스페셜티 커피.\n에너지 +20 회복.", energy: 20 },
  fishcake:  { type: "general", icon: "\uD83C\uDF62", name: "포장마차 어묵", desc: "따끈한 어묵 한 꼬치.\n에너지 +15 회복.", energy: 15 },
  taiyaki:   { type: "general", icon: "\uD83D\uDC1F", name: "붕어빵", desc: "겨울철 인기 간식 붕어빵.\n에너지 +10 회복.", energy: 10 },
  tote_bag:  { type: "cloth", icon: "\uD83D\uDC5C", name: "무신사 에코백", desc: "무신사 스탠다드에서 받은 에코백.\n성수 패션의 상징!", energy: 0 },
  perfume:   { type: "general", icon: "\uD83E\uDDF4", name: "탬버린즈 향수 샘플", desc: "탬버린즈에서 받은 향수 샘플.\n은은한 우디향이 난다.", energy: 0 },
  photocard: { type: "general", icon: "\uD83D\uDCF8", name: "포토이즘 사진", desc: "포토이즘에서 찍은 인생네컷.\n추억이 담겨있다!", energy: 0 },
  book:      { type: "general", icon: "\uD83D\uDCD6", name: "포인트오브뷰 독립서적", desc: "성수동 독립서점의 추천 책.\n읽으면 세상이 달라 보인다.", energy: 0 },
  sticker:   { type: "general", icon: "\u2B50", name: "팝업스토어 스티커", desc: "한정판 팝업스토어 스티커.\n컬렉터 아이템!", energy: 0 },
}

// ITEM_DB에 9개의 커버낫 옷 추가
for (let i = 1; i <= 9; i++) {
  ITEM_DB[`covernat_${i}`] = {
    type: "cloth",
    icon: "\uD83D\uDC55",
    name: `커버낫 의상 ${i}`,
    desc: `커버낫 성수 팝업 한정판 의상 #${i}`,
    image: `/assets/covernat_${i}.jpg`,
    energy: 0
  };
}

const gameNoti = document.getElementById("game-notification");

function showNotification(msg) {
  gameNoti.textContent = msg;
  gameNoti.classList.remove("show-noti");
  void gameNoti.offsetWidth; 
  gameNoti.classList.add("show-noti");
  setTimeout(() => gameNoti.classList.remove("show-noti"), 2000);
}

function renderInventory() {
  invGrid.innerHTML = ""
  for (let i = 0; i < MAX_SLOTS; i++) {
    const slot = document.createElement("div")
    slot.className = "inv-slot"
    const itemKey = gameState.inventory[i]
    if (itemKey && ITEM_DB[itemKey]) {
      slot.textContent = ITEM_DB[itemKey].icon
      slot.addEventListener("click", () => {
        document.querySelectorAll("#inventory-grid .inv-slot").forEach(s => s.classList.remove("active"))
        slot.classList.add("active")
        const item = ITEM_DB[itemKey]
        let desc = `${item.name}\n${item.desc}`
        if (item.energy > 0) desc += `\n\n[클릭하여 사용 - 에너지 +${item.energy}]`
        invDesc.textContent = desc
      })
      slot.addEventListener("dblclick", () => {
        const item = ITEM_DB[itemKey]
        if (item.energy > 0) {
          gameState.energy = Math.min(100, gameState.energy + item.energy)
          gameState.inventory.splice(i, 1)
          updateHUD()
          renderInventory()
          invDesc.textContent = `${item.name}을(를) 사용했다! 에너지 +${item.energy}`
        }
      })
    }
    invGrid.appendChild(slot)
  }
  invDesc.textContent = "아이템을 클릭하면 상세정보를, 더블클릭하면 사용합니다."
}

function renderClothInventory() {
  clothGrid.innerHTML = ""
  for (let i = 0; i < MAX_SLOTS; i++) {
    const slot = document.createElement("div")
    slot.className = "inv-slot"
    slot.style.cssText = "overflow:hidden; padding:0;"
    const itemKey = gameState.clothes[i]
    if (itemKey && ITEM_DB[itemKey]) {
      const item = ITEM_DB[itemKey]
      if (item.image) {
        const img = document.createElement("img")
        img.src = item.image
        img.style.cssText = "width:100%; height:100%; object-fit:cover; border-radius:4px; display:block;"
        img.onerror = () => { slot.textContent = item.icon }
        slot.appendChild(img)
      } else {
        slot.textContent = item.icon
      }
      slot.addEventListener("click", () => {
        document.querySelectorAll("#cloth-grid .inv-slot").forEach(s => s.classList.remove("active"))
        slot.classList.add("active")
        clothDesc.textContent = `${item.name}\n${item.desc}`
      })
    }
    clothGrid.appendChild(slot)
  }
  clothDesc.textContent = "옷 아이템을 클릭하면 상세정보를 확인합니다."
}

function toggleInventory() {
  inventoryOpen = !inventoryOpen
  invPanel.style.display = inventoryOpen ? "block" : "none"
  if (inventoryOpen) {
    clothOpen = false
    clothPanel.style.display = "none"
    renderInventory()
    if (typeof fadeBgm === "function") fadeBgm(BGM_MUTE, BGM_FADE_OUT)
  } else {
    if (typeof fadeBgm === "function") fadeBgm(BGM_VOLUME, BGM_FADE_IN)
  }
}

function toggleCloth() {
  clothOpen = !clothOpen
  clothPanel.style.display = clothOpen ? "block" : "none"
  if (clothOpen) {
    inventoryOpen = false
    invPanel.style.display = "none"
    renderClothInventory()
    if (typeof fadeBgm === "function") fadeBgm(BGM_MUTE, BGM_FADE_OUT)
  } else {
    if (typeof fadeBgm === "function") fadeBgm(BGM_VOLUME, BGM_FADE_IN)
  }
}

invBtn.addEventListener("click", toggleInventory)
invCloseBtn.addEventListener("click", () => {
  inventoryOpen = false
  invPanel.style.display = "none"
  if (typeof fadeBgm === "function") fadeBgm(BGM_VOLUME, BGM_FADE_IN)
})

clothBtn.addEventListener("click", toggleCloth)
clothCloseBtn.addEventListener("click", () => {
  clothOpen = false
  clothPanel.style.display = "none"
  if (typeof fadeBgm === "function") fadeBgm(BGM_VOLUME, BGM_FADE_IN)
})

// ── Save 페이로드 헬퍼 ──
function buildSavePayload() {
  return {
    player_name: gameState.player_name,
    player_x: Math.max(0, gameState.player_x),
    player_y: GROUND_Y,
    gold: gameState.gold,
    inventory: gameState.inventory,
    clothes: gameState.clothes,
    discovered_events: gameState.discovered_events,
  }
}

// ── HUD 업데이트 ──
function updateHUD() {
  const energyFill = document.getElementById("hud-energy-fill")
  const energyText = document.getElementById("hud-energy-text")
  const goldText = document.getElementById("hud-gold-text")
  if (energyFill) energyFill.style.width = `${gameState.energy}%`
  if (energyText) energyText.textContent = gameState.energy
  if (goldText) goldText.textContent = gameState.gold
}

// ── 6. 네트워크 유틸 ──
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

const postLocks = {}
function resetLocks() { Object.keys(postLocks).forEach(k => postLocks[k] = false) }
async function lockCall(key, fn) {
  if (postLocks[key]) return
  postLocks[key] = true
  try { return await fn() } finally { postLocks[key] = false }
}

// ═══════════════════════════════════════════════════════
//  7. 메인 게임 씬
// ═══════════════════════════════════════════════════════
scene("main", () => {
  const mySceneId = ++currentSceneId
  abortGetRequests()
  resetLocks()

  // ── 맵 상수 ──
  const MAP_WIDTH = 8000          
  const PLAYER_SCALE = 0.75
  const SPEED = 180
  const BG_HEIGHT = 480

  // ── 대화 상태 ──
  let isDialogOpen = false
  let isTyping = false
  let isAdvancing = false
  let dialogLines = []
  let dialogIndex = 0
  let loopCtrl = null
  let currentNPCPortrait = ""

  // ── BGM 설정 ──
  const bgm = new Audio('/assets/main_bgm1.mp3')
  bgm.loop = true
  bgm.volume = BGM_VOLUME
  bgm.play().catch(() => {
    document.addEventListener('click', () => bgm.play(), { once: true })
  })

  // ── NPC 대화 효과음 ──
  const sfxDialog = new Audio('/assets/npc_sound.mp3')
  sfxDialog.volume = 0.6

  // ── BGM 페이드 함수 ──
  function fadeBgm(targetVolume, duration) {
    const step = (targetVolume - bgm.volume) / (duration / 50)
    const interval = setInterval(() => {
      const next = bgm.volume + step
      if ((step > 0 && next >= targetVolume) || (step < 0 && next <= targetVolume)) {
        bgm.volume = targetVolume
        clearInterval(interval)
      } else {
        bgm.volume = Math.max(0, Math.min(1, next))
      }
    }, 50)
  }

  const dialogBox = document.getElementById("dialog-box")
  const dialogName = document.getElementById("dialog-name")
  const dialogText = document.getElementById("dialog-text")
  const dialogPortrait = document.getElementById("dialog-portrait")
  const dialogActionBtns = document.getElementById("dialog-action-btns")
  const dialogBtnIn = document.getElementById("dialog-btn-in")
  const dialogBtnOut = document.getElementById("dialog-btn-out")
  const exitModal = document.getElementById("exit-modal")
  const exitModalConfirm = document.getElementById("exit-modal-confirm")
  const exitModalCancel = document.getElementById("exit-modal-cancel")

  function openExitModal() {
    exitModal.style.display = "flex"
    fadeBgm(BGM_MUTE, BGM_FADE_OUT)
  }

  function closeExitModal() {
    exitModal.style.display = "none"
    fadeBgm(BGM_VOLUME, BGM_FADE_IN)
  }

  exitModalConfirm.addEventListener("click", () => {
    window.location.href = "/"
  })

  exitModalCancel.addEventListener("click", () => {
    closeExitModal()
  })

  document.getElementById("exit-modal-overlay").addEventListener("click", () => {
    closeExitModal()
  })

  const shopModal = document.getElementById("shop-modal")
  const shopModalName = document.getElementById("shop-modal-name")
  const shopModalImg = document.getElementById("shop-modal-img")
  const shopModalDesc = document.getElementById("shop-modal-desc")
  const shopModalLink = document.getElementById("shop-modal-link")
  const shopModalClose = document.getElementById("shop-modal-close")
  
  const webviewModal = document.getElementById("webview-modal")
  const webviewModalName = document.getElementById("webview-modal-name")
  const webviewIframe = document.getElementById("webview-iframe")
  const webviewModalClose = document.getElementById("webview-modal-close")
  
  let currentNPCModal = null
  let currentNPCIsExit = false

  // ── 브랜드 모달 통합 (covernat / matinkim / musinsa) ──
  const BRAND_CONFIG = {
    covernat: {
      icon: "👕",
      warnMsg: "⚠️ カバーナットアイテムは1つだけ保存できます！\n⚠️ 커버낫 아이템은 1개만 저장 가능합니다!",
      dialogLines: [
        "カバーナット聖水へようこそ！\n커버낫 성수에 오신 것을 환영합니다!",
        "右上からお好みの服を選べますよ！\n오른쪽 상단에서 마음에 드는 옷을 고르실 수 있어요!"
      ],
    },
    matinkim: {
      icon: "👗",
      warnMsg: "⚠️ マタンキムアイテムは1つだけ保存できます！\n⚠️ 마뗑킴 아이템은 1개만 저장 가능합니다!",
      dialogLines: [
        "マタンキム聖水へようこそ！\n마뗑킴 성수에 오신 걸 환영합니다!",
        "右上からお好みの服を選べますよ！\n오른쪽 상단에서 마음에 드는 옷을 고르실 수 있어요!"
      ],
    },
    musinsa: {
      icon: "👕",
      warnMsg: "⚠️ ムシンサアイテムは1つだけ保存できます！\n⚠️ 무신사 아이템은 1개만 저장 가능합니다!",
      dialogLines: [
        "ムシンサスタンダード聖水へようこそ！\n무신사 스탠다드 성수에 오신 걸 환영합니다!",
        "右上からお好みの服を選べますよ！\n오른쪽 상단에서 마음에 드는 옷을 고르실 수 있어요!"
      ],
    },
  }

  function openBrandModal(brandId) {
    const cfg = BRAND_CONFIG[brandId]
    if (!cfg) return

    const modal = document.getElementById(`${brandId}-modal`)
    const dialogEl = document.getElementById(`${brandId}-modal-dialog`)
    const grid = document.getElementById(`${brandId}-modal-grid`)
    if (!modal || !dialogEl || !grid) return

    modal.style.display = "flex"
    fadeBgm(BGM_MUTE, BGM_FADE_OUT)

    let idx = 0
    dialogEl.style.display = "block"
    grid.classList.add(`${brandId}-grid-disabled`)

    const newDialogEl = dialogEl.cloneNode(true)
    dialogEl.parentNode.replaceChild(newDialogEl, dialogEl)
    newDialogEl.querySelector("p").textContent = cfg.dialogLines[0]

    newDialogEl.onclick = () => {
      idx++
      if (idx < cfg.dialogLines.length) {
        newDialogEl.querySelector("p").textContent = cfg.dialogLines[idx]
      } else {
        newDialogEl.style.display = "none"
        grid.classList.remove(`${brandId}-grid-disabled`)
      }
    }

    document.querySelectorAll(`.${brandId}-item`).forEach(item => {
      const cloned = item.cloneNode(true)
      item.parentNode.replaceChild(cloned, item)
      cloned.addEventListener("click", () => {
        openBrandPreview(brandId, cloned.dataset.name, cloned.dataset.brand, cloned.dataset.img)
      })
    })
  }

  function openBrandPreview(brandId, name, brand, imgSrc) {
    const cfg = BRAND_CONFIG[brandId]
    if (!cfg) return

    const preview = document.getElementById(`${brandId}-item-preview`)
    const previewImg = document.getElementById(`${brandId}-preview-img`)
    const saveBtn = document.getElementById(`${brandId}-preview-save`)
    const cancelBtn = document.getElementById(`${brandId}-preview-cancel`)
    const toast = document.getElementById(`${brandId}-modal-toast`)
    if (!preview || !previewImg || !saveBtn || !cancelBtn) return

    previewImg.src = imgSrc
    preview.style.display = "flex"

    const newSave = saveBtn.cloneNode(true)
    saveBtn.parentNode.replaceChild(newSave, saveBtn)
    const newCancel = cancelBtn.cloneNode(true)
    cancelBtn.parentNode.replaceChild(newCancel, cancelBtn)

    newSave.addEventListener("click", () => {
      preview.style.display = "none"
      const alreadyHas = gameState.clothes.some(k => k && k.startsWith(`${brandId}_`))
      if (alreadyHas) {
        toast.textContent = cfg.warnMsg
      } else if (gameState.clothes.length >= MAX_SLOTS) {
        toast.textContent = "❌ CLOTHがいっぱいです！\n❌ CLOTH가 가득 찼습니다!"
      } else {
        const itemKey = `${brandId}_saved`
        ITEM_DB[itemKey] = {
          type: "cloth",
          icon: cfg.icon,
          name: name,
          desc: `${brand} 성수 플래그십 한정 아이템`,
          image: imgSrc,
          energy: 0
        }
        gameState.clothes.push(itemKey)
        renderClothInventory()
        toast.textContent = "✔ CLOTHに保存されました！\n✔ CLOTH에 저장되었습니다!"
      }
      toast.style.display = "block"
      setTimeout(() => { toast.style.display = "none" }, 2000)
    })

    newCancel.addEventListener("click", () => {
      preview.style.display = "none"
    })
  }

  function closeBrandModal(brandId) {
    const modal = document.getElementById(`${brandId}-modal`)
    if (modal) modal.style.display = "none"
    fadeBgm(BGM_VOLUME, BGM_FADE_IN)
    const preview = document.getElementById(`${brandId}-item-preview`)
    if (preview) preview.style.display = "none"
  }

  // 각 브랜드 모달의 닫기 버튼/오버레이 이벤트 등록
  for (const brandId of Object.keys(BRAND_CONFIG)) {
    const closeBtn = document.getElementById(`${brandId}-modal-close`)
    const overlay = document.getElementById(`${brandId}-modal-overlay`)
    if (closeBtn) closeBtn.addEventListener("click", () => closeBrandModal(brandId))
    if (overlay) overlay.addEventListener("click", () => closeBrandModal(brandId))
  }

  function openModalByType(modalData) {
    if (!modalData) return
    if (BRAND_CONFIG[modalData.type]) {
      openBrandModal(modalData.type)
    } else {
      openShopModal(modalData)
    }
  }

  function openShopModal(modalData) {
    if (!modalData) return
    
    // 특정 URL인 경우 웹뷰 모달로 열기
    if (modalData.link === "/aeae_popup/index.html") {
      webviewModalName.textContent = modalData.name
      webviewIframe.src = modalData.link
      webviewModal.style.display = "flex"
      fadeBgm(BGM_MUTE, BGM_FADE_OUT)
      return
    }

    shopModalName.textContent = modalData.name
    shopModalImg.src = modalData.image
    shopModalDesc.textContent = modalData.desc
    shopModalLink.href = modalData.link
    shopModal.style.display = "flex"
    fadeBgm(BGM_MUTE, BGM_FADE_OUT)
  }

  function closeShopModal() {
    shopModal.style.display = "none"
    webviewModal.style.display = "none"
    webviewIframe.src = "" // 리소스 해제
    fadeBgm(BGM_VOLUME, BGM_FADE_IN)
  }

  shopModalClose.addEventListener("click", closeShopModal)
  document.getElementById("shop-modal-overlay").addEventListener("click", closeShopModal)
  
  webviewModalClose.addEventListener("click", closeShopModal)
  document.getElementById("webview-modal-overlay").addEventListener("click", closeShopModal)

  // ── 배경 (패럴랙스) ──
  const BG_SCALE_Y = BG_HEIGHT / 254
  const BG_TILE_W = 1024 * BG_SCALE_Y
  const BG_TILES = Math.ceil(MAP_WIDTH / BG_TILE_W) + 2
  for (let i = 0; i < BG_TILES; i++) {
    const bx = i * BG_TILE_W
    add([
      sprite("bg_city"),
      pos(bx, 0),
      anchor("topleft"),
      scale(BG_SCALE_Y),
      z(-100),
      "bg_far",
    ])
  }

  // ── 건물 배치 데이터 ──
  const BUILDINGS = [
    { spr: "building_random1",      x: 7600,  y: 10, s: 0.30 },
    { spr: "building_random2",      x: 7900,  y: 20, s: 0.25 },
    { spr: "building_popup1",       x: 850,  y: -30, s: 0.35 },
    { spr: "building_random3",      x: 2150, y: 0, s: 0.30 },
    { spr: "building_random4",      x: 5650, y: -10, s: 0.30 },
    { spr: "building_musinsa",      x: 1800, y: 0, s: 0.40 },
    { spr: "building_covernat",     x: 150, y: 10, s: 0.40 },
    { spr: "building_matinkim",     x: 2550, y: 10, s: 0.20 },
    { spr: "building_adererror",    x: 6500, y: 40, s: 0.25 },
    { spr: "building_zenmon",       x: 3425, y: -20, s: 0.55 },
    { spr: "building_dior",         x: 1325, y: 60, s: 0.50 },
    { spr: "building_tamburins",    x: 4250, y: 60, s: 0.35 },
    { spr: "building_blueelephant", x: 4650, y: 30, s: 0.30 },
    { spr: "building_photoism",     x: 5000, y: 10, s: 0.30 },
    { spr: "building_onion",        x: 5325, y: 0, s: 0.35 },
    { spr: "building_zenmon_popup", x: 6000, y: 30, s: 0.35 },
    { spr: "food_cart",             x: 3900, y: 0, s: 0.10 },
    { spr: "building_pointofview",  x: 3000, y: -20, s: 0.30 },
    { spr: "building_nyunyu",       x: 6950, y: -5, s: 0.30 },
    { spr: "building_random5",      x: 7300, y: -5, s: 0.30 },
    { spr: "building_random6",      x: 450, y: 25, s: 0.30 },
    { spr: "building_random7",      x: 3705, y: 0, s: 0.30 },
  ]

  BUILDINGS.forEach(b => {
    add([
      sprite(b.spr),
      pos(b.x, GROUND_Y + (b.y || 0)),
      anchor("bot"),
      scale(b.s),
      z(-10),
      "building",
    ])
  })

  // ── NPC 데이터 & 배치 ──
  const NPCS = [
    {
      id: "npc_food_cart_vendor",
      name: "포장마차 아주머니",
      spriteKey: null,
      x: 3900, npcScale: 0.1,
      portrait: "/assets/npc_phone_girl.png",
      modal: null,
      lines: [
        "いらっしゃいませ～温かいおでんはいかがですか？\n어서 와요~ 따끈한 어묵 드실래요?",
        "聖水洞を回ってお腹が空いたらここに来ればいいですよ！\n성수동 구경하다 배고프면 여기 오면 돼요!",
        "さあ、おでんを一本どうぞ！\n자, 어묵 한 꼬치 드릴게요!",
      ],
      revisit_lines: [
        "또 왔네요~ 오늘도 어묵 한 꼬치 드릴게요!",
        "추운 날엔 어묵 국물이 최고죠!",
      ],
      reward: { item: "fishcake", gold: 0 },
    },
    {
      id: "npc_onion_barista",
      name: "어니언 바리스타",
      spriteKey: "npc_headphone_girl",
      x: 5475, npcScale: 0.25,
      portrait: "/assets/npc_headphone_girl.png",
      modal: { name: "어니언 성수", image: "/assets/building_onion.png", desc: "성수동 대표 카페. 공장을 개조한 독특한 인테리어.", link: "https://www.instagram.com/onion.seongsu" },
      lines: [
        "ようこそ、オニオンへ！\n어서오세요, 어니언에 오신 걸 환영해요!",
        "この建物はもとも도工場でしたが、\n今はカフェになりました。\n이 건물은 원래 공장이었는데, 지금은 카페로 변했답니다.",
        "ハンドドリップコーヒーをどうぞ！\n핸드드립 커피 한 잔 드릴게요!",
      ],
      revisit_lines: [
        "またいらっしゃいましたね！今日の豆はエチオピア産です。\n또 오셨네요! 오늘의 원두는 에티오피아산이에요.",
        "ゆっくり楽しんでいってください！\n여유롭게 즐기다 가세요!",
      ],
      reward: { item: "coffee", gold: 0 },
    },
    {
      id: "npc_dior_staff",
      name: "디올 성수 스태프",
      spriteKey: "npc_pink_girl",
      x: 1275, npcScale: 0.13,
      portrait: "/assets/npc_pink_girl.png",
      modal: { name: "디올 성수", image: "/assets/building_dior.png", desc: "디올의 성수동 플래그십 스토어. 화려한 외관이 인상적.", link: "https://www.dior.com" },
      lines: [
        "ディオール聖水へようこそ。\n디올 성수에 오신 걸 환영합니다.",
        "この建物はディオールが聖水洞に作った\n特別なフラッグシップストアです。\n이 건물은 디올이 성수동에 만든 특별한 플래그십 스토어예요.",
        "展示もぜひご覧ください！\n전시도 구경하고 가세요!",
      ],
      revisit_lines: [
        "今日から新しい展示が始まりました！\n오늘은 새로운 전시가 시작됐어요!",
        "写真映えするフォトゾーンもありますよ。\n사진 찍기 좋은 포토존도 있답니다.",
      ],
      reward: { item: null, gold: 10 },
    },
    {
      id: "npc_tamburins_guide",
      name: "탬버린즈 안내원",
      spriteKey: "npc_phone_girl",
      x: 4375, npcScale: 0.32,
      portrait: "/assets/npc_phone_girl.png",
      modal: { name: "탬버린즈", image: "/assets/building_tamburins.png", desc: "젠틀몬스터 그룹의 향수 브랜드. 독창적인 향수 라인업.", link: "https://www.tamburins.com" },
      lines: [
        "タンバリンズへようこそ！\n탬버린즈에 오신 걸 환영해요!",
        "ジェントルモンスターグループの香水ブランドです。\n젠틀몬스터 그룹의 향수 브랜드예요.",
        "この香水サンプルをどうぞ！\n이 향수 샘플 하나 가져가세요!",
      ],
      revisit_lines: [
        "香水は気に入っていただけましたか？\n향수 마음에 드셨어요?",
        "新しいラインも出ましたのでぜひ見てください！\n새로운 라인도 나왔으니 구경해 보세요!",
      ],
      reward: { item: "perfume", gold: 0 },
    },
    {
      id: "npc_musinsa_staff",
      name: "무신사 스탠다드 직원",
      spriteKey: "npc_hoodie_boy",
      x: 1950, npcScale: 0.35,
      portrait: "/assets/npc_hoodie_boy.png",
      modal: { name: "무신사 스탠다드 성수", image: "/assets/building_musinsa.png", desc: "무신사의 오프라인 플래그십 스토어.", link: "https://store.musinsa.com", type: "musinsa" },
      lines: [
        "ムシンサスタンダード聖水へようこそ！\n무신사 스탠다드 성수에 오신 걸 환영합니다!",
        "最近はベーシックな無地Tシャツが一番人気です。\n요즘 베이직 무지 티가 제일 잘 나가요.",
        "エコバッグをどうぞ、お買い物にお使いください！\n에코백 하나 드릴게요, 쇼핑할 때 쓰세요!",
      ],
      revisit_lines: [
        "おっ、エコバッグ使ってくれてますね！\n오~ 에코백 잘 쓰고 계시네요!",
        "新作フーディも出ましたのでご覧ください。\n신상 후드도 나왔으니 구경해 보세요.",
      ],
      reward: { item: "tote_bag", gold: 0 },
    },
    {
      id: "npc_blueelephant_artist",
      name: "블루엘리펀트 아티스트",
      spriteKey: "npc_colorful_boy",
      x: 4725, npcScale: 0.12,
      portrait: "/assets/npc_colorful_boy.png",
      modal: { name: "블루엘리펀트", image: "/assets/building_blueelephant.png", desc: "성수동 복합문화공간. 전시와 공연이 열리는 곳.", link: "https://www.instagram.com/blueelephant_seoul" },
      lines: [
        "ここはブルーエレファント、複合文化スペースだよ！\n여기는 블루엘리펀트, 복합문화공간이야!",
        "展示もあるし、公演もあるし...\n聖水洞のアートの心臓みたいな場所だよ。\n전시도 하고, 공연도 하고... 성수동의 예술 심장 같은 곳이지.",
        "今日の展示은絶対見ていって！\n오늘 전시 꼭 보고 가!",
      ],
      revisit_lines: [
        "今月新しい展示が始まったよ！\n이번 달 새 전시 시작했어!",
        "来るたびに違う作品が見られるんだよ。\n매번 올 때마다 다른 작품을 볼 수 있지.",
      ],
      reward: { item: null, gold: 15 },
    },
    {
      id: "npc_covernat_designer",
      name: "커버낫 디자이너",
      spriteKey: "npc_denim_boy",
      x: 300, npcScale: 0.15,
      portrait: "/assets/npc_denim_boy.png",
      modal: { name: "커버낫 성수", image: "/assets/building_covernat.png", desc: "스트릿 캐주얼 브랜드 커버낫의 성수 플래그십.", link: "https://covernat.net", type: "covernat" },
      lines: [
        "カバーナット聖水フラッグシップへようこそ！\n커버낫 성수 플래그십에 온 걸 환영해!",
        "聖水洞といえばストリートファッションだよ。\n성수동하면 스트릿 패션이지.",
        "今シーズンのコレクション、ぜひ見てみて！\n이번 시즌 컬렉션 한번 봐봐!",
      ],
      revisit_lines: [
        "スタイルいいね？うちの服が似合いそう！\n스타일 좋은데? 우리 옷이 잘 어울릴 듯!",
        "コラボアイテムも出たから確認してみて！\n콜라보 아이템도 나왔으니 확인해 봐!",
      ],
      reward: { item: null, gold: 10 },
    },
    {
      id: "npc_pointofview_owner",
      name: "포인트오브뷰 서점 주인",
      spriteKey: "npc_walking_boy",
      x: 3150, npcScale: 0.26,
      portrait: "/assets/npc_walking_boy.png",
      modal: { name: "포인트오브뷰", image: "/assets/building_pointofview.png", desc: "성수동의 독립서점. 감성적인 독립출판물이 가득.", link: "https://www.instagram.com/point.of.view.seoul" },
      lines: [
        "ポイントオブビューへようこそ。\n포인트오브뷰에 오신 걸 환영합니다.",
        "ここは聖水洞の独立書店です。\n여기는 성수동의 독립서점이에요.",
        "この本を一冊おすすめします！\n이 책 한 권 추천드릴게요!",
      ],
      revisit_lines: [
        "読み終わりましたか？感想が気になります。\n다 읽으셨어요? 소감이 궁금하네요.",
        "新しく入った本もありますのでご覧ください。\n새로 들어온 책들도 있으니 구경해 보세요.",
      ],
      reward: { item: "book", gold: 0 },
    },
    {
      id: "npc_matinkim_fan",
      name: "마뗑킴 매니아",
      spriteKey: "npc_pink_girl",
      x: 2650, npcScale: 0.12,
      portrait: "/assets/npc_pink_girl.png",
      modal: { name: "마뗑킴", image: "/assets/building_matinkim.png", desc: "감각적인 여성 패션 브랜드 마뗑킴의 성수 매장.", link: "https://www.matinkim.com", type: "matinkim" },
      lines: [
        "マタンキム！最近一番ホットなブランドだよ！\n마뗑킴! 요즘 제일 핫한 브랜드잖아!",
        "聖水にオフライン店があるなんて...\n直接来ないとわからない感じがあるよ！\n성수에 오프라인 매장이 있다니... 직접 와봐야 느낌이 달라!",
        "このバッグ、めちゃくちゃかわいくない？！\n이 가방 너무 예쁘지 않아?!",
      ],
      revisit_lines: [
        "結局バッグ買っちゃった...後悔なし！\n나 결국 가방 샀어... 후회 없음!",
        "あなたも一つ買ってみて！\n너도 하나 질러봐!",
      ],
      reward: { item: null, gold: 20 },
    },
    {
      id: "npc_adererror_hipster",
      name: "아더에러 패피",
      spriteKey: "npc_colorful_boy",
      x: 6475, npcScale: 0.12,
      portrait: "/assets/npc_colorful_boy.png",
      modal: { name: "아더에러", image: "/assets/building_adererror.png", desc: "성수동 본사를 둔 감성 스트릿 브랜드.", link: "https://adererror.com" },
      lines: [
        "アーダーエラー聖水本社前だよ。\n아더에러 성수 본사 앞이야.",
        "このレンガ建物の雰囲気、やばくない？\n이 벽돌 건물 분위기 미쳤지?",
        "エラーからインスピレーションを得るブランドなんて、クールじゃない？\n에러에서 영감을 얻는 브랜드라니, 쿨하지 않아?",
      ],
      revisit_lines: [
        "今日もOOTD撮りに来たよ！\n오늘도 OOTD 찍으러 왔어!",
        "聖水は毎日来ても写真映えするものがあふれてる。\n성수는 매일 와도 사진 찍을 게 넘쳐.",
      ],
      reward: { item: null, gold: 10 },
    },
    {
      id: "npc_popup_explorer",
      name: "팝업 탐험가",
      spriteKey: "npc_hoodie_boy",
      x: 900, npcScale: 0.35,
      portrait: "/assets/npc_hoodie_boy.png",
      modal: { name: "AEAE 팝업스토어", image: "/assets/building_popup1.png", desc: "지금 성수에서 가장 핫한 AEAE 팝업스토어입니다!", link: "/aeae_popup/index.html" },
      lines: [
        "ここのポップアップストア見た？！\n여기 팝업스토어 봤어?!",
        "AEAEというブランドで今聖水で\n一番ホットな場所だよ！\nAEAE라는 브랜드인데 지금 성수에서 제일 핫한 곳이야!",
        "ちょっと入って見てみて！\n한번 들어가서 구경해봐!",
      ],
      revisit_lines: [
        "AEAEポップアップまた行く？\nAEAE 팝업 또 가보게?",
        "あそこのグッズ、本当にかわいいんだよ！\n거기 굿즈들이 정말 예쁘더라구!",
      ],
      reward: { item: "sticker", gold: 0 },
    },
    {
      id: "npc_photoism_staff",
      name: "포토이즘 직원",
      spriteKey: "npc_phone_girl",
      x: 5000, npcScale: 0.30,
      portrait: "/assets/npc_phone_girl.png",
      modal: { name: "포토이즘", image: "/assets/building_photoism.png", desc: "인생네컷 포토부스. 다양한 테마의 사진을 남길 수 있다.", link: "https://photoism.co.kr" },
      lines: [
        "フォトイズムへようこそ！\n포토이즘에 오신 걸 환영해요!",
        "人生4カット、一枚撮っていってください～\n인생네컷 한 장 찍어 가세요~",
        "はい、写真です！よく撮れましたよ！\n자, 여기 사진이요! 잘 나왔네요!",
      ],
      revisit_lines: [
        "또 찍으러 오셨어요? 오늘은 새 프레임이 있어요!\n또 찍으러 오셨어요? 오늘은 새 프레임이 있어요!",
        "写真は思い出ですから！\n사진은 추억이니까요!",
      ],
      reward: { item: "photocard", gold: 0 },
    },
    {
      id: "npc_exit",
      name: "성수동 안내원",
      spriteKey: "npc_phone_girl",
      x: 7850,
      npcScale: 0.32,
      portrait: null,
      modal: null,
      isExit: true,
      lines: [
        "聖水洞の探索を終えましたね！\n성수동 탐험을 마치셨군요!",
        "今日も聖水洞を楽しんでいただきありがとうございます🙏\n오늘 하루도 성수동을 즐겨주셔서 감사해요 🙏",
        "ウェブページに戻りますか？\n웹페이지로 돌아가시겠어요?"
      ],
      reward: null
    },
  ]

  NPCS.forEach(npc => {
    add([
      rect(140, 200),
      pos(npc.x, GROUND_Y),
      area(),
      anchor("bot"),
      opacity(0),
      z(-1),
      "npc_trigger",
      { npcData: npc },
    ])
    if (npc.spriteKey) {
      add([
        sprite(npc.spriteKey, { frame: 0 }),
        pos(npc.x, GROUND_Y),
        anchor("bot"),
        scale(npc.npcScale),
        z(5),
        "npc_sprite",
        { npcId: npc.id },
      ])
    }
    const bubbleY = GROUND_Y - 210
    add([
      rect(20, 26, { radius: 3 }),
      pos(npc.x, bubbleY),
      anchor("center"),
      color(255, 220, 0),
      z(14),
      "npc_bubble_bg",
    ])
    add([
      text("!", { size: 20 }),
      pos(npc.x, bubbleY),
      anchor("center"),
      color(0, 0, 0),
      z(15),
      "npc_bubble",
      { npcId: npc.id, baseY: bubbleY, t: Math.random() * Math.PI * 2 },
    ])
  })

  onUpdate("npc_bubble", (bubble) => {
    bubble.t += dt() * 2.5
    bubble.pos.y = bubble.baseY + Math.sin(bubble.t) * 5
  })

  const initX = gameState.player_x >= 0 ? gameState.player_x : 150
  const player = add([
    sprite("player_char", { anim: "idle-right" }),
    scale(PLAYER_SCALE),
    pos(Math.max(30, Math.min(initX, MAP_WIDTH - 30)), GROUND_Y),
    anchor("bot"),
    area(),
    z(10),
    "player",
  ])

  const CAM_Y = GROUND_Y - height() * 0.35
  function clampCamX(px) {
    if (MAP_WIDTH <= width()) return MAP_WIDTH / 2
    return Math.max(width() / 2, Math.min(px, MAP_WIDTH - width() / 2))
  }
  camPos(vec2(clampCamX(player.pos.x), CAM_Y))

  let facingRight = true
  let mobileDir = 0

  onUpdate(() => {
    if (inventoryOpen || clothOpen) return
    if (isDialogOpen) return

    let dir = mobileDir
    if (isKeyDown("left") || isKeyDown("a")) dir = -1
    if (isKeyDown("right") || isKeyDown("d")) dir = 1

    if (dir !== 0) {
      player.move(dir * SPEED, 0)
      player.pos.x = Math.max(30, Math.min(player.pos.x, MAP_WIDTH - 30))
    }
    if (dir < 0) {
      facingRight = false
      if (player.curAnim() !== "walk-left") player.play("walk-left")
    } else if (dir > 0) {
      facingRight = true
      if (player.curAnim() !== "walk-right") player.play("walk-right")
    } else {
      const cur = player.curAnim()
      if (cur && cur.startsWith("walk")) {
        player.play(facingRight ? "idle-right" : "idle-left")
      }
    }
    camPos(vec2(clampCamX(player.pos.x), CAM_Y))
    gameState.player_x = Math.floor(player.pos.x)
  })

  function startTypewriter(txt, onComplete) {
    if (loopCtrl) { loopCtrl.cancel(); loopCtrl = null }
    dialogText.textContent = ""
    isTyping = true
    isAdvancing = false
    let i = 0
    loopCtrl = loop(0.04, () => {
      if (currentSceneId !== mySceneId) { loopCtrl.cancel(); loopCtrl = null; return }
      dialogText.textContent += txt[i]
      i++
      if (i >= txt.length) {
        loopCtrl.cancel(); loopCtrl = null
        isTyping = false
        isAdvancing = false
        onComplete?.()
      }
    })
  }

  function openDialog(npcName, lines, portrait, modalData, isExit) {
    isDialogOpen = true
    sfxDialog.currentTime = 0
    sfxDialog.play()
    fadeBgm(BGM_MUTE, BGM_FADE_OUT)
    isAdvancing = false
    dialogLines = lines
    dialogIndex = 0
    currentNPCPortrait = portrait || ""
    currentNPCModal = modalData || null
    currentNPCIsExit = isExit || false
    dialogActionBtns.style.display = "none"
    dialogBox.classList.add("open")
    dialogBox.style.display = "flex"
    dialogName.textContent = npcName
    if (currentNPCPortrait) {
      dialogPortrait.src = currentNPCPortrait
      dialogPortrait.style.display = "block"
    } else {
      dialogPortrait.style.display = "none"
    }
    startTypewriter(dialogLines[dialogIndex], null)
  }

  function closeDialog(skipBgm = false) {
    if (loopCtrl) { loopCtrl.cancel(); loopCtrl = null }
    isDialogOpen = false
    isTyping = false
    isAdvancing = false
    dialogLines = []
    dialogIndex = 0
    dialogBox.classList.remove("open")
    dialogBox.style.display = "none"
    dialogText.textContent = ""
    dialogName.textContent = ""
    dialogActionBtns.style.display = "none"
    if (!skipBgm) fadeBgm(BGM_VOLUME, BGM_FADE_IN)
  }

  function advanceDialog() {
    if (!isDialogOpen) return
    if (isAdvancing) return
    isAdvancing = true
    if (isTyping) {
      isAdvancing = false
      if (loopCtrl) { loopCtrl.cancel(); loopCtrl = null }
      isTyping = false
      dialogText.textContent = dialogLines[dialogIndex]
      return
    }
    dialogIndex++
    if (dialogIndex >= dialogLines.length) {
      if (currentNPCIsExit) {
        closeDialog(true)
        openExitModal()
      } else if (currentNPCModal) {
        dialogActionBtns.style.display = "flex"
        dialogBtnIn.onclick = () => {
          closeDialog(true)
          openModalByType(currentNPCModal)
        }
        dialogBtnOut.onclick = () => { closeDialog() }
      } else {
        closeDialog()
      }
    } else {
      startTypewriter(dialogLines[dialogIndex], null)
    }
  }

  function triggerNearestNPC() {
    if (isDialogOpen) return
    const triggers = get("npc_trigger")
    let nearestNPC = null
    let nearestDist = 100
    for (const t of triggers) {
      const dist = Math.abs(player.pos.x - t.pos.x)
      if (dist < nearestDist) {
        nearestDist = dist
        nearestNPC = t.npcData
      }
    }
    if (!nearestNPC) return
    const isRevisit = gameState.discovered_events.includes(nearestNPC.id)
    const lines = (isRevisit && nearestNPC.revisit_lines) ? nearestNPC.revisit_lines : nearestNPC.lines
    if (!isRevisit) {
      gameState.discovered_events.push(nearestNPC.id)
      if (nearestNPC.reward) {
        if (nearestNPC.reward.item) {
          const itemData = ITEM_DB[nearestNPC.reward.item]
          if (itemData && itemData.type === "cloth") {
            if (gameState.clothes.length < MAX_SLOTS) gameState.clothes.push(nearestNPC.reward.item)
          } else if (itemData) {
            if (gameState.inventory.length < MAX_SLOTS) gameState.inventory.push(nearestNPC.reward.item)
          }
        }
        if (nearestNPC.reward.gold) gameState.gold += nearestNPC.reward.gold
        gameState.energy = Math.max(0, gameState.energy - 5)
        updateHUD()
      }
      lockCall("autoSave", async () => {
        try {
          await fetch("/api/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(buildSavePayload()),
          })
        } catch (e) { console.error("[자동저장 실패]", e) }
      })
    }
    openDialog(nearestNPC.name, lines, nearestNPC.portrait, nearestNPC.modal, nearestNPC.isExit)
  }

  onKeyPress("space", () => {
    if (inventoryOpen || clothOpen) return
    if (isDialogOpen) { advanceDialog(); return }
    triggerNearestNPC()
  })

  onKeyPress("up", () => {
    if (isDialogOpen && currentNPCModal && dialogActionBtns.style.display !== "none") {
      closeDialog(true)
      openModalByType(currentNPCModal)
    }
  })

  onKeyPress("down", () => {
    if (isDialogOpen && dialogActionBtns.style.display !== "none") closeDialog()
  })

  onKeyPress("e", () => {
    if (isDialogOpen) return
    inventoryOpen = !inventoryOpen
    invPanel.style.display = inventoryOpen ? "block" : "none"
    if (inventoryOpen) {
      clothOpen = false
      clothPanel.style.display = "none"
      renderInventory()
      fadeBgm(BGM_MUTE, BGM_FADE_OUT)
    } else {
      fadeBgm(BGM_VOLUME, BGM_FADE_IN)
    }
  })

  onKeyPress("c", () => {
    if (isDialogOpen) return
    clothOpen = !clothOpen
    clothPanel.style.display = clothOpen ? "block" : "none"
    if (clothOpen) {
      inventoryOpen = false
      invPanel.style.display = "none"
      renderClothInventory()
      fadeBgm(BGM_MUTE, BGM_FADE_OUT)
    } else {
      fadeBgm(BGM_VOLUME, BGM_FADE_IN)
    }
  })

  updateHUD()
  console.log("[ENGINE] 메인 씬 초기화 완료")
})

onLoad(() => {
  console.log("[ENGINE] 모든 에셋 로딩 완료")
})
