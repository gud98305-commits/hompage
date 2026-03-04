/**
 * game.js — 게임 데모/로그인 모드 분기 모듈
 *
 * 의존성: auth.js (window.SeoulFitAuth)
 * 사용법: fashion.html에서 auth.js 다음에 로드
 *
 * 역할:
 *  1. 게임 진입 시 로그인 여부 확인 → 데모/정식 모드 설정
 *  2. 로그인 유저: 게임 종료 시 /api/game/save 호출 → Supabase 저장
 *  3. 비로그인(데모 모드): 게임 종료 시 로그인 유도 모달 표시
 */

const SeoulFitGame = (() => {
  // ── 상태 ──────────────────────────────────────────────────────────────────
  let _isDemoMode = true;
  let _currentSession = {
    acquiredItems: [],       // 이번 게임에서 획득한 아이템
    selectedStyles: [],
    selectedColors: [],
    selectedCategories: [],
    selectedKeywords: [],
    startedAt: null,
  };

  // ── 초기화 ────────────────────────────────────────────────────────────────

  /**
   * 게임 진입 시 호출.
   * URL 파라미터 또는 localStorage JWT 토큰으로 로그인 여부 판별.
   */
  function init() {
    // URL 파라미터에서 토큰 확인 (OAuth 콜백 후 리다이렉트 케이스)
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get('token');
    if (urlToken) {
      localStorage.setItem('sf_token', urlToken);
      // 토큰 파라미터 제거 (히스토리 정리)
      const cleanUrl = window.location.pathname;
      window.history.replaceState({}, '', cleanUrl);
    }

    const token = localStorage.getItem('sf_token');
    _isDemoMode = !token;

    if (_isDemoMode) {
      _showDemoBanner();
    } else {
      _loadInventoryForGame();
    }

    _currentSession.startedAt = new Date().toISOString();
    console.log(`[Game] 모드: ${_isDemoMode ? '데모' : '정식 (로그인)'}`);
  }

  /**
   * 현재 데모 모드 여부 반환.
   */
  function isDemoMode() {
    return _isDemoMode;
  }

  // ── 세션 데이터 수집 ──────────────────────────────────────────────────────

  /**
   * 게임에서 아이템을 획득할 때 호출.
   * @param {Object} item — 상품 데이터 (product_id, name, category 등)
   */
  function onItemAcquired(item) {
    if (!item || !item.product_id) return;
    const alreadyHas = _currentSession.acquiredItems.some(
      (i) => i.product_id === item.product_id
    );
    if (!alreadyHas) {
      _currentSession.acquiredItems.push(item);
      console.log(`[Game] 아이템 획득: ${item.name}`);
    }
  }

  /**
   * 선택된 필터 정보 업데이트 (스타일, 색상, 키워드 등).
   */
  function updateSelections({ styles, colors, categories, keywords } = {}) {
    if (styles)     _currentSession.selectedStyles = styles;
    if (colors)     _currentSession.selectedColors = colors;
    if (categories) _currentSession.selectedCategories = categories;
    if (keywords)   _currentSession.selectedKeywords = keywords;
  }

  // ── 게임 종료 ─────────────────────────────────────────────────────────────

  /**
   * 게임 종료 시 호출.
   * - 로그인 유저: Supabase에 저장
   * - 데모 모드: 로그인 유도 모달 표시
   */
  async function onGameEnd() {
    if (_isDemoMode) {
      _showLoginPromptModal();
      return;
    }

    try {
      await _saveToServer();
      _showSaveSuccessToast();
    } catch (err) {
      console.error('[Game] 저장 실패:', err);
      _showSaveErrorToast();
    }
  }

  // ── 서버 저장 ─────────────────────────────────────────────────────────────

  async function _saveToServer() {
    const token = localStorage.getItem('sf_token');
    if (!token) throw new Error('토큰 없음');

    const payload = {
      acquired_items: _currentSession.acquiredItems.map((item) => ({
        product_id: item.product_id || item.id || '',
        name:        item.name || '',
        brand:       item.brand || '',
        category:    item.category || '',
        sub_category: item.sub_category || '',
        style:       item.style || '',
        colors:      item.colors || [],
        tags:        item.tags || [],
        image_url:   item.image_url || item.imageUrl || '',
        price_krw:   item.price_krw || 0,
        source_url:  item.source_url || '',
      })),
      selected_styles:     _currentSession.selectedStyles,
      selected_colors:     _currentSession.selectedColors,
      selected_categories: _currentSession.selectedCategories,
      selected_keywords:   _currentSession.selectedKeywords,
    };

    const resp = await fetch('/api/game/save', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const data = await resp.json();
    console.log(`[Game] 저장 완료: ${data.message}`);
    return data;
  }

  // ── 인벤토리 로드 (게임 진입 시) ─────────────────────────────────────────

  async function _loadInventoryForGame() {
    const token = localStorage.getItem('sf_token');
    if (!token) return;

    try {
      const resp = await fetch('/api/game/inventory', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) return;
      const data = await resp.json();
      // 전역으로 노출 → fashion.js 등에서 인벤토리 배지 표시에 활용
      window._sfInventory = data.items || [];
      console.log(`[Game] 인벤토리 로드: ${data.total}개`);
      _dispatchInventoryLoaded(data.items);
    } catch (err) {
      console.warn('[Game] 인벤토리 로드 실패:', err);
    }
  }

  function _dispatchInventoryLoaded(items) {
    window.dispatchEvent(
      new CustomEvent('sf:inventoryLoaded', { detail: { items } })
    );
  }

  // ── UI 헬퍼 ──────────────────────────────────────────────────────────────

  function _showDemoBanner() {
    const banner = document.createElement('div');
    banner.id = 'sf-demo-banner';
    banner.style.cssText = `
      position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
      background: rgba(0,0,0,0.85); color: #fff; padding: 12px 24px;
      border-radius: 999px; font-size: 14px; z-index: 9000;
      display: flex; align-items: center; gap: 12px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    `;
    banner.innerHTML = `
      <span>👗 <strong>데모 모드</strong> — 로그인하면 인벤토리에 저장돼요</span>
      <button onclick="window.SeoulFitAuth && window.SeoulFitAuth.login()"
        style="background:#fff; color:#000; border:none; padding:6px 14px;
               border-radius:999px; cursor:pointer; font-size:13px; font-weight:600;">
        로그인
      </button>
    `;
    document.body.appendChild(banner);
  }

  /**
   * 게임 종료 시 비로그인 유저에게 로그인 유도 모달 표시.
   */
  function _showLoginPromptModal() {
    // 기존 모달 제거
    const existing = document.getElementById('sf-login-prompt-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'sf-login-prompt-modal';
    modal.style.cssText = `
      position: fixed; inset: 0; background: rgba(0,0,0,0.6);
      display: flex; align-items: center; justify-content: center;
      z-index: 10000;
    `;
    modal.innerHTML = `
      <div style="
        background: #fff; border-radius: 20px; padding: 40px 32px;
        max-width: 400px; width: 90%; text-align: center;
        box-shadow: 0 20px 60px rgba(0,0,0,0.2);
      ">
        <div style="font-size: 48px; margin-bottom: 16px;">👗</div>
        <h2 style="margin: 0 0 12px; font-size: 22px; font-weight: 700;">
          스타일이 마음에 드셨나요?
        </h2>
        <p style="color: #666; font-size: 15px; line-height: 1.6; margin-bottom: 28px;">
          로그인을 하시면 인벤토리의 아이템들로<br>
          <strong>맞춤 옷 추천</strong>을 받으실 수 있어요.
        </p>
        <div style="display: flex; flex-direction: column; gap: 12px;">
          <button
            onclick="window.SeoulFitAuth && window.SeoulFitAuth.login()"
            style="
              background: #000; color: #fff; border: none;
              padding: 14px 24px; border-radius: 12px;
              font-size: 16px; font-weight: 600; cursor: pointer;
            "
          >
            Google로 로그인하기
          </button>
          <button
            onclick="document.getElementById('sf-login-prompt-modal').remove()"
            style="
              background: transparent; color: #999; border: none;
              padding: 10px; font-size: 14px; cursor: pointer;
            "
          >
            나중에 하기
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    // 배경 클릭 시 닫기
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.remove();
    });
  }

  function _showSaveSuccessToast() {
    _showToast('👗 옷장에 저장됐어요!', '#22c55e');
  }

  function _showSaveErrorToast() {
    _showToast('⚠️ 저장 중 오류가 발생했어요.', '#ef4444');
  }

  function _showToast(message, bgColor = '#333') {
    const toast = document.createElement('div');
    toast.style.cssText = `
      position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
      background: ${bgColor}; color: #fff; padding: 12px 24px;
      border-radius: 999px; font-size: 14px; font-weight: 600;
      z-index: 10000; box-shadow: 0 4px 16px rgba(0,0,0,0.2);
      animation: sf-toast-in 0.3s ease;
    `;
    toast.textContent = message;

    // 애니메이션 스타일
    if (!document.getElementById('sf-toast-style')) {
      const style = document.createElement('style');
      style.id = 'sf-toast-style';
      style.textContent = `
        @keyframes sf-toast-in {
          from { opacity: 0; transform: translateX(-50%) translateY(16px); }
          to   { opacity: 1; transform: translateX(-50%) translateY(0); }
        }
      `;
      document.head.appendChild(style);
    }

    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  // ── 공개 API ──────────────────────────────────────────────────────────────
  return {
    init,
    isDemoMode,
    onItemAcquired,
    updateSelections,
    onGameEnd,
  };
})();

// 자동 초기화 (DOM 로드 완료 후)
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', SeoulFitGame.init);
} else {
  SeoulFitGame.init();
}

window.SeoulFitGame = SeoulFitGame;
