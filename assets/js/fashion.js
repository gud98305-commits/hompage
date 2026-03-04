import { getRecommendations, createPaymentIntent, completePayment } from './api-client.js';

// ─── i18n ────────────────────────────────────────────────────────────────────
const I18N = {
  ko: {
    'hero.subtitle': '큐레이터',
    'hero.desc': '카테고리를 선택하면 OpenAI가 크롤링된 상품에서 의류만 분류해 정렬합니다.',
    'panel.filters': '카테고리 선택',
    'panel.results': '추천 결과',
    'email.label': '결제 완료 이메일 (선택)',
    'email.placeholder': 'you@example.com',
    'label.gender': '성별',
    'label.style': '스타일',
    'label.color': '색상',
    'label.category': '의류 카테고리',
    'label.budget': '가격대 (KRW)',
    'label.keyword': '한국 패션 키워드',
    'label.keyword.hint': '(복수 선택 가능)',
    'gender.all': '전체', 'gender.women': '여성', 'gender.men': '남성', 'gender.unisex': '젠더리스',
    'color.all': '전체 색상',
    'style.all': '전체 스타일',
    'style.minimal': '미니멀', 'style.street': '스트리트', 'style.vintage': '빈티지',
    'style.casual': '캐주얼', 'style.formal': '포멀', 'style.y2k': 'Y2K',
    'style.romantic': '로맨틱', 'style.preppy': '프레피',
    'color.black': '블랙', 'color.white': '화이트', 'color.beige': '베이지',
    'color.navy': '네이비', 'color.gray': '그레이', 'color.brown': '브라운',
    'color.ivory': '아이보리', 'color.khaki': '카키', 'color.olive': '올리브',
    'color.mint': '민트', 'color.skyblue': '스카이블루', 'color.cobalt': '코발트',
    'color.lavender': '라벤더', 'color.pink': '핑크', 'color.red': '레드',
    'color.burgundy': '버건디', 'color.yellow': '옐로우', 'color.orange': '오렌지',
    'color.camel': '카멜', 'color.deepgreen': '딥그린', 'color.wine': '와인',
    'cat.all': '의류 전체', 'cat.top': '상의 전체', 'cat.tshirt': '티셔츠',
    'cat.shirt': '셔츠/블라우스', 'cat.knit': '니트/스웨터', 'cat.hoodie': '후드/맨투맨',
    'cat.bottom': '하의 전체', 'cat.pants': '팬츠/슬랙스', 'cat.skirt': '스커트',
    'cat.denim': '청바지/데님', 'cat.outer': '아우터 전체', 'cat.jacket': '자켓',
    'cat.coat': '코트', 'cat.dress': '원피스', 'cat.suit': '수트/점프수트',
    'budget.all': '전체 가격', 'budget.1': '~5만원', 'budget.2': '5~15만원',
    'budget.3': '15~30만원', 'budget.4': '30만원+',
    'kw.gguankgu': '꾸안꾸 · 편안한 캐주얼', 'kw.gguggu': '꾸꾸꾸 · 화려한 스타일',
    'kw.devilwoman': '여자의악마 · 섹시/힙 K팝', 'kw.officecore': '출근룩 · 정석 오피스',
    'kw.reply2000s': '응답하라2000s · 복고 Y2K',
    'btn.submit': 'AI 추천 받기', 'btn.reset': '초기화', 'btn.pay': '결제',
    'btn.close': '닫기', 'btn.cancel': '취소',
    'status.loading': 'OpenAI가 카테고리 분석 및 의류 필터링 중입니다...',
    'status.error': '오류: ', 'status.pay_error': '결제 오류: ',
    'pay.heading': '결제', 'pay.product': '상품: ', 'pay.amount': '금액: ',
    'detail.heading': '상세 이미지', 'result.items': 'items',
    'result.empty': '선택한 조건에 맞는 데이터가 없습니다.',
    'result.empty.hint': '색상/의류 카테고리/가격대 조건을 완화해 보세요.',
    'status.complete': '결제가 완료되었습니다.',
    'status.processing': '결제가 처리 중입니다. 잠시 후 상태를 확인하세요.',
    'status.failed': '결제가 실패했습니다.',
    'status.pay_reflect_error': '결제 반영 오류: ',
    'badge.krw': '원화: ',
    'nav.fashion': '패션추천', 'nav.photo': 'AI 포토부스', 'nav.pixel': '픽셀 서울',
  },
  ja: {
    'hero.subtitle': 'キュレーター',
    'hero.desc': 'カテゴリーを選択するとOpenAIがクロールされた商品から衣類だけを分類して並べます。',
    'panel.filters': 'カテゴリー選択', 'panel.results': 'レコメンド結果',
    'email.label': '決済完了メール（任意）', 'email.placeholder': 'you@example.com',
    'label.gender': '性別', 'label.style': 'スタイル', 'label.color': 'カラー',
    'label.category': 'カテゴリー', 'label.budget': '価格帯 (KRW)',
    'label.keyword': 'Kファッションキーワード', 'label.keyword.hint': '（複数選択可）',
    'gender.all': '全て', 'gender.women': 'レディース', 'gender.men': 'メンズ', 'gender.unisex': 'ジェンダーレス',
    'color.all': '全カラー',
    'style.all': '全スタイル',
    'style.minimal': 'ミニマル', 'style.street': 'ストリート', 'style.vintage': 'ヴィンテージ',
    'style.casual': 'カジュアル', 'style.formal': 'フォーマル', 'style.y2k': 'Y2K',
    'style.romantic': 'ロマンティック', 'style.preppy': 'プレッピー',
    'color.black': 'ブラック', 'color.white': 'ホワイト', 'color.beige': 'ベージュ',
    'color.navy': 'ネイビー', 'color.gray': 'グレー', 'color.brown': 'ブラウン',
    'color.ivory': 'アイボリー', 'color.khaki': 'カーキ', 'color.olive': 'オリーブ',
    'color.mint': 'ミント', 'color.skyblue': 'スカイブルー', 'color.cobalt': 'コバルト',
    'color.lavender': 'ラベンダー', 'color.pink': 'ピンク', 'color.red': 'レッド',
    'color.burgundy': 'バーガンディ', 'color.yellow': 'イエロー', 'color.orange': 'オレンジ',
    'color.camel': 'キャメル', 'color.deepgreen': 'ディープグリーン', 'color.wine': 'ワイン',
    'cat.all': '全アイテム', 'cat.top': 'トップス全体', 'cat.tshirt': 'Tシャツ',
    'cat.shirt': 'シャツ/ブラウス', 'cat.knit': 'ニット/セーター', 'cat.hoodie': 'パーカー/スウェット',
    'cat.bottom': 'ボトムス全体', 'cat.pants': 'パンツ/スラックス', 'cat.skirt': 'スカート',
    'cat.denim': 'デニム', 'cat.outer': 'アウター全体', 'cat.jacket': 'ジャケット',
    'cat.coat': 'コート', 'cat.dress': 'ワンピース', 'cat.suit': 'スーツ/オールインワン',
    'budget.all': '全価格帯', 'budget.1': '〜5万ウォン', 'budget.2': '5〜15万ウォン',
    'budget.3': '15〜30万ウォン', 'budget.4': '30万ウォン+',
    'kw.gguankgu': 'クアンク · 楽なカジュアル', 'kw.gguggu': 'クックク · 華やか',
    'kw.devilwoman': '女性の悪魔 · セクシーKポップ', 'kw.officecore': '出勤ルック · 正統オフィス',
    'kw.reply2000s': '応答せよ2000s · レトロY2K',
    'btn.submit': 'AIレコメンド', 'btn.reset': 'リセット', 'btn.pay': '購入',
    'btn.close': '閉じる', 'btn.cancel': 'キャンセル',
    'status.loading': 'OpenAIがカテゴリー分析・衣類フィルタリング中です...',
    'status.error': 'エラー: ', 'status.pay_error': '決済エラー: ',
    'pay.heading': '購入', 'pay.product': '商品: ', 'pay.amount': '金額: ',
    'detail.heading': '詳細画像', 'result.items': 'アイテム',
    'result.empty': '条件に合うデータがありません。',
    'result.empty.hint': 'カラー/カテゴリー/価格条件を緩めてください。',
    'status.complete': '決済が完了しました。',
    'status.processing': '決済処理中です。しばらくお待ちください。',
    'status.failed': '決済に失敗しました。',
    'status.pay_reflect_error': '決済反映エラー: ',
    'badge.krw': '韓国ウォン: ',
    'nav.fashion': 'ファッションおすすめ', 'nav.photo': 'AIフォトブース', 'nav.pixel': 'ピクセルソウル',
  }
};

let currentLang = 'ko';
function t(key) { return (I18N[currentLang] || I18N.ko)[key] || (I18N.ko[key] || key); }

// ─── Toast ────────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info', duration = 3200) {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => {
    el.style.animation = 'toast-out .25s ease forwards';
    setTimeout(() => el.remove(), 260);
  }, duration);
}

// ─── Skeleton loading ─────────────────────────────────────────────────────────
function showSkeletons(count = 8) {
  const card = `
    <div class="skeleton-card">
      <div class="skeleton-thumb"></div>
      <div class="skeleton-body">
        <div class="skeleton-line s"></div>
        <div class="skeleton-line m"></div>
        <div class="skeleton-line l"></div>
        <div class="skeleton-btn"></div>
      </div>
    </div>`;
  list.innerHTML = Array(count).fill(card).join('');
}

// ─── Wishlist (localStorage) ──────────────────────────────────────────────────
let _wishIds   = new Set(JSON.parse(localStorage.getItem('seoulfit_wishlist') || '[]'));
let _wishItems = JSON.parse(localStorage.getItem('seoulfit_wishlist_data') || '{}');

function _saveWish() {
  localStorage.setItem('seoulfit_wishlist', JSON.stringify([..._wishIds]));
  localStorage.setItem('seoulfit_wishlist_data', JSON.stringify(_wishItems));
}

function _updateWishCount() {
  const el = document.getElementById('wish-count');
  if (el) el.textContent = _wishIds.size;
}

function toggleWish(id, itemSnapshot) {
  const sid = String(id);
  if (_wishIds.has(sid)) {
    _wishIds.delete(sid);
    delete _wishItems[sid];
    showToast('찜 목록에서 제거했습니다.', 'info', 2000);
  } else {
    _wishIds.add(sid);
    _wishItems[sid] = itemSnapshot;
    showToast('♡ 찜 목록에 추가했습니다!', 'success', 2400);
  }
  _saveWish();
  _updateWishCount();
  // 현재 렌더된 카드의 버튼 상태 갱신
  document.querySelectorAll(`.wish-btn[data-wish-id="${sid}"]`).forEach(btn => {
    btn.classList.toggle('on', _wishIds.has(sid));
    btn.textContent = _wishIds.has(sid) ? '♥' : '♡';
  });
}

function openWishModal() {
  const modal   = document.getElementById('wish-modal');
  const wishList = document.getElementById('wish-list');
  const emptyEl = document.getElementById('wish-empty');
  const items   = Object.values(_wishItems);
  if (items.length === 0) {
    wishList.innerHTML = '';
    emptyEl.style.display = 'block';
  } else {
    emptyEl.style.display = 'none';
    wishList.innerHTML = items.map(item => productCard(item)).join('');
  }
  modal.hidden = false;
}
function closeWishModal() { document.getElementById('wish-modal').hidden = true; }

// ─── Purchase history ─────────────────────────────────────────────────────────
function savePurchase(data) {
  const arr = JSON.parse(localStorage.getItem('seoulfit_purchases') || '[]');
  arr.push({
    payment_intent_id: data.payment_intent_id || '',
    product_id:   data.product_id   || '',
    product_name: data.product_name || '',
    amount_jpy:   data.amount_jpy   || 0,
    mall:         data.mall         || '',
    email:        data.email        || '',
    image:        data.image        || '',
    date: new Date().toISOString(),
  });
  localStorage.setItem('seoulfit_purchases', JSON.stringify(arr));
}

// ─── EmailJS ──────────────────────────────────────────────────────────────────
// ▼ EmailJS 대시보드에서 가져온 값으로 교체하세요
const EMAILJS_PUBLIC_KEY  = '1pr-z3o56OU_dQeZe';
const EMAILJS_SERVICE_ID  = 'miniproject_2';
const EMAILJS_TEMPLATE_ID = 'template_l51tu24';

async function sendConfirmationEmail(email, productName, amountJpy) {
  if (!email || !window.emailjs || EMAILJS_PUBLIC_KEY === 'YOUR_PUBLIC_KEY') return;

  // ── 언어별 UI 텍스트 ──
  const isJa = currentLang === 'ja';
  const ui = isJa ? {
    heading      : 'ご購入が完了しました',
    sub          : 'OttOをご利用いただきありがとうございます。以下でご注文内容をご確認ください。',
    product_label: 'PRODUCT',
    amount_label : '決済金額',
    date_label   : '決済日時',
    status_text  : '● 決済完了 — PAYMENT CONFIRMED',
    cta_text     : 'マイページで確認する →',
    footer_text  : 'このメールは自動送信されます。返信しないでください。<br/>お問い合わせ: support@seoulfit.kr',
  } : {
    heading      : '구매가 완료되었습니다',
    sub          : 'OttO를 이용해 주셔서 감사합니다. 아래에서 주문 내역을 확인하세요.',
    product_label: 'PRODUCT',
    amount_label : '결제 금액',
    date_label   : '결제 일시',
    status_text  : '● 결제 완료 — PAYMENT CONFIRMED',
    cta_text     : '마이페이지에서 확인하기 →',
    footer_text  : '본 이메일은 자동 발송됩니다. 회신하지 마세요.<br/>문의: support@seoulfit.kr',
  };

  try {
    emailjs.init({ publicKey: EMAILJS_PUBLIC_KEY });
    await emailjs.send(EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, {
      to_email     : email,
      product_name : productName,
      amount       : new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY' }).format(amountJpy),
      date         : new Date().toLocaleString(isJa ? 'ja-JP' : 'ko-KR'),
      ...ui,
    });
    showToast('📧 구매 확인 이메일을 발송했습니다.', 'success');
  } catch (e) {
    console.warn('EmailJS send failed:', e);
  }
}

// ─── i18n apply ───────────────────────────────────────────────────────────────
function applyLanguage(lang) {
  currentLang = lang;
  document.documentElement.lang = lang === 'ja' ? 'ja' : 'ko';
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.lang === lang);
  });
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const tr  = t(key);
    if (tr) el.textContent = tr;
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    const tr  = t(key);
    if (tr) el.placeholder = tr;
  });
  const cachedItems = pageCache[currentPage];
  if (cachedItems && cachedItems.length > 0) {
    if (lang === 'ja') {
      applyTranslations(cachedItems).then(translated => renderItems(translated));
    } else {
      renderItems(cachedItems);
    }
  }
}

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const form          = document.getElementById('curator-form');
const list          = document.getElementById('result-list');
const statusNode    = document.getElementById('status');
const countNode     = document.getElementById('result-count');
const payModal      = document.getElementById('pay-modal');
const payTitle      = document.getElementById('pay-title');
const payAmount     = document.getElementById('pay-amount');
const payClose      = document.getElementById('pay-close');
const paySubmit     = document.getElementById('pay-submit');
const payCancel     = document.getElementById('pay-cancel');
const detailModal   = document.getElementById('detail-modal');
const detailTitle   = document.getElementById('detail-title');
const detailMain    = document.getElementById('detail-main');
const detailStrip   = document.getElementById('detail-strip');
const detailClose   = document.getElementById('detail-close');
const detailMainWrap = document.getElementById('detail-main-wrap');

let stripe = null, elements = null, paymentElement = null, activePayment = null;

// ─── Helpers ──────────────────────────────────────────────────────────────────
function escapeHtml(v) {
  return String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
    .replaceAll('"','&quot;').replaceAll("'",'&#39;');
}
function formatJPY(v) {
  return new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY' }).format(v || 0);
}
function setStatus(text) { statusNode.textContent = text || ''; }

// ─── Tag groups ───────────────────────────────────────────────────────────────
function setupTagGroups() {
  document.querySelectorAll('.tag-group').forEach(group => {
    const single = group.dataset.single === 'true';
    group.querySelectorAll('.tag').forEach(tag => {
      tag.addEventListener('click', () => {
        if (single) {
          group.querySelectorAll('.tag').forEach(x => x.classList.remove('on'));
          tag.classList.add('on');
        } else {
          tag.classList.toggle('on');
        }
      });
    });
  });
}

function selectedTagValue(groupId, fallback = '') {
  const node = document.querySelector(`#${groupId} .tag.on`);
  return node ? (node.dataset.value ?? fallback) : fallback;
}
function selectedTagValues(groupId) {
  const nodes = document.querySelectorAll(`#${groupId} .tag.on`);
  if (!nodes.length) return '';
  return Array.from(nodes).map(n => n.dataset.value).filter(Boolean).join(',');
}
function selectedBudget() {
  const node = document.querySelector('#tg-budget .tag.on');
  if (!node) return { min: 0, max: 99999999 };
  return { min: Number(node.dataset.min || 0), max: Number(node.dataset.max || 99999999) };
}

// ─── Modals ───────────────────────────────────────────────────────────────────
function openModal()  { payModal.hidden = false; }
function closeModal() { payModal.hidden = true; }

function normalizeImage(src) {
  return (src && typeof src === 'string' && src.trim()) ? src : '/assets/cards/card-fashion.svg';
}

// ─── Zoom / Pan ───────────────────────────────────────────────────────────────
let _zoomScale = 1, _panX = 0, _panY = 0;
let _isDragging = false, _dragStartX = 0, _dragStartY = 0;
const ZOOM_MIN = 0.5, ZOOM_MAX = 4.0, ZOOM_STEP = 1.3;

function _applyTransform() {
  detailMain.style.transform = `translate(${_panX}px,${_panY}px) scale(${_zoomScale})`;
  const hint = detailMainWrap.querySelector('.detail-zoom-hint');
  if (hint) hint.textContent = `${Math.round(_zoomScale * 100)}%`;
}
function _resetZoom() { _zoomScale = 1; _panX = 0; _panY = 0; _applyTransform(); }

detailMainWrap.addEventListener('wheel', e => {
  e.preventDefault();
  _zoomScale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, _zoomScale * (e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP)));
  _applyTransform();
}, { passive: false });
detailMainWrap.addEventListener('mousedown', e => {
  if (e.button !== 0) return;
  _isDragging = true; _dragStartX = e.clientX - _panX; _dragStartY = e.clientY - _panY;
  detailMainWrap.classList.add('grabbing'); e.preventDefault();
});
window.addEventListener('mousemove', e => {
  if (!_isDragging) return;
  _panX = e.clientX - _dragStartX; _panY = e.clientY - _dragStartY; _applyTransform();
});
window.addEventListener('mouseup', () => { if (_isDragging) { _isDragging = false; detailMainWrap.classList.remove('grabbing'); } });
let _lastTouchDist = null;
detailMainWrap.addEventListener('touchstart', e => {
  if (e.touches.length === 2) {
    const dx = e.touches[0].clientX - e.touches[1].clientX, dy = e.touches[0].clientY - e.touches[1].clientY;
    _lastTouchDist = Math.hypot(dx, dy);
  } else if (e.touches.length === 1) {
    _isDragging = true; _dragStartX = e.touches[0].clientX - _panX; _dragStartY = e.touches[0].clientY - _panY;
  }
  e.preventDefault();
}, { passive: false });
detailMainWrap.addEventListener('touchmove', e => {
  if (e.touches.length === 2 && _lastTouchDist) {
    const dx = e.touches[0].clientX - e.touches[1].clientX, dy = e.touches[0].clientY - e.touches[1].clientY;
    const dist = Math.hypot(dx, dy);
    _zoomScale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, _zoomScale * dist / _lastTouchDist));
    _lastTouchDist = dist; _applyTransform();
  } else if (e.touches.length === 1 && _isDragging) {
    _panX = e.touches[0].clientX - _dragStartX; _panY = e.touches[0].clientY - _dragStartY; _applyTransform();
  }
  e.preventDefault();
}, { passive: false });
detailMainWrap.addEventListener('touchend', () => { _lastTouchDist = null; _isDragging = false; });
detailMainWrap.addEventListener('dblclick', _resetZoom);
document.getElementById('detail-zoom-in').addEventListener('click',    () => { _zoomScale = Math.min(ZOOM_MAX, _zoomScale * ZOOM_STEP); _applyTransform(); });
document.getElementById('detail-zoom-out').addEventListener('click',   () => { _zoomScale = Math.max(ZOOM_MIN, _zoomScale / ZOOM_STEP); _applyTransform(); });
document.getElementById('detail-zoom-reset').addEventListener('click', _resetZoom);

// ─── 매치 아이템 추천 헬퍼 ──────────────────────────────────────────────────
// 클라이언트사이드 성별 추론 (백엔드 _infer_gender 동일 로직)
function _inferGender(item) {
  const text = ((item.name || '') + ' ' + (item.brand || '')).toLowerCase();
  const wToks = ['우먼', 'women', 'womens', '여성', 'ladies', 'womenswear'];
  const mToks = ['맨즈', 'mens', '남성', 'menswear'];
  const wbRe  = tok => new RegExp('\\b' + tok.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b');
  const hasW  = wToks.some(tok => wbRe(tok).test(text));
  const hasM  = mToks.some(tok => wbRe(tok).test(text));
  if (hasW && !hasM) return 'women';
  if (hasM && !hasW) return 'men';
  return 'unisex';
}

// 현재 렌더 아이템 + 모든 캐시 페이지 아이템으로 검색 풀 구성
function _buildItemPool(excludeId) {
  const poolMap = new Map();
  for (const item of _lastRenderedItems) poolMap.set(String(item.id), item);
  for (const items of Object.values(pageCache)) {
    for (const item of items) {
      const sid = String(item.id);
      if (!poolMap.has(sid)) poolMap.set(sid, item);
    }
  }
  _matchPool.forEach((item, sid) => { if (!poolMap.has(sid)) poolMap.set(sid, item); });
  if (excludeId) poolMap.delete(String(excludeId));
  return [...poolMap.values()];
}

function _pickByGender(candidates, gender, showBoth) {
  const results = [];
  if (showBoth) {
    const w = candidates.find(i => { const g = _inferGender(i); return g === 'women' || g === 'unisex'; });
    const m = candidates.find(i => _inferGender(i) === 'men');
    if (w) results.push(w);
    if (m && m !== w) results.push(m);
    if (!w && !m && candidates[0]) results.push(candidates[0]);
  } else if (gender === 'unisex') {
    const hits = candidates.filter(i => _inferGender(i) === 'unisex').slice(0, 2);
    results.push(...(hits.length ? hits : candidates.slice(0, 1)));
  } else {
    const hit = candidates.find(i => {
      const g = _inferGender(i);
      if (gender === 'women') return g === 'women' || g === 'unisex';
      if (gender === 'men')   return g === 'men'   || g === 'unisex';
      return true;
    });
    if (hit) results.push(hit);
  }
  return results;
}

function _findComplementItems(currentId, category, selectedGender) {
  const pool = _buildItemPool(currentId);
  if (!pool.length) return [];

  const base = (category || '').toLowerCase();
  let lookFor = [];
  if      (base === 'top')    lookFor = ['bottom'];
  else if (base === 'bottom') lookFor = ['top'];
  else if (base === 'outer')  lookFor = ['top', 'bottom'];
  else if (base === 'dress')  lookFor = ['outer', 'top'];
  else                        lookFor = ['top', 'bottom'];

  const gender   = (selectedGender || '').toLowerCase();
  const showBoth = (gender === 'all' || gender === '');

  const results = [];
  for (const targetCat of lookFor) {
    const candidates = pool.filter(i => (i.category || '').toLowerCase() === targetCat);
    if (candidates.length) results.push(..._pickByGender(candidates, gender, showBoth));
  }
  return results;
}

// 매치 카드 이벤트 바인딩 (동기/비동기 렌더 공통 재사용)
function _attachMatchCardEvents(infoPanel) {
  infoPanel.querySelectorAll('.match-card').forEach(mc => {
    mc.addEventListener('click', e => {
      if (e.target.closest('.wish-btn')) return;
      const mid       = mc.dataset.matchId;
      const matchItem = _buildItemPool(null).find(it => String(it.id) === mid)
                     || JSON.parse(mc.dataset.matchSnapshot || 'null');
      if (!matchItem) return;
      const mMain    = normalizeImage(matchItem.main_image);
      const mDetails = (matchItem.detail_images || []).slice(0, 10).map(normalizeImage);
      openDetailModal(matchItem.name, [mMain, ...mDetails.filter(u => u !== mMain)], {
        itemId: String(matchItem.id),
        name: matchItem.name, mall: matchItem.mall,
        category: matchItem.category, subCategory: matchItem.sub_category,
        colors: (matchItem.colors || []).join(','),
        material: matchItem.material || '', care: matchItem.care || '',
        sourceUrl: matchItem.source_url || '',
        krw: matchItem.price_krw, jpy: matchItem.price_jpy,
      });
    });
  });
  infoPanel.querySelectorAll('.match-wish').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const sid   = btn.dataset.wishId;
      const snap  = JSON.parse(btn.closest('.match-card')?.dataset.matchSnapshot || '{}');
      toggleWish(sid, snap);
      btn.classList.toggle('on', _wishIds.has(sid));
      btn.textContent = _wishIds.has(sid) ? '♥' : '♡';
    });
  });
}

// pageCache에 complement 없을 때 → 백그라운드 API 호출 후 패널 업데이트
async function _fetchAndRenderComplement(currentItemData, selectedGender, infoPanel, token) {
  const gender   = (selectedGender || '').toLowerCase();
  const showBoth = (gender === 'all' || gender === '');

  let items = [];
  try {
    const resp = await fetch('/api/match-complement', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_item: currentItemData,
        gender: gender || 'all',
        page_size: showBoth ? 4 : 2,
      }),
    });
    if (resp.ok) {
      const data = await resp.json();
      items = data.items || [];
    }
  } catch (_) {}

  // 모달이 닫혔거나 더 최신 요청이 발행됐으면 버림 (경쟁 조건 방지)
  if (token !== _matchReqToken || detailModal.hidden) return;
  const loadingEl = infoPanel?.querySelector('.match-loading');
  if (!loadingEl) return;

  if (!items.length) { loadingEl.remove(); return; }

  // 결과를 _matchPool에 등록 (클릭 시 openDetailModal에서 재활용)
  for (const it of items) { if (it.id) _matchPool.set(String(it.id), it); }

  const picked = showBoth ? items : _pickByGender(items, gender, false);
  if (!picked.length) { loadingEl.remove(); return; }

  const isJa       = currentLang === 'ja';
  const matchLabel = isJa ? 'このアイテムと合わせて' : '이 아이템과 매치해보세요';
  loadingEl.outerHTML = `
    <div class="match-section">
      <div class="match-section-title">✦ ${matchLabel}</div>
      ${picked.map(m => _matchMiniCard(m)).join('')}
    </div>`;
  _attachMatchCardEvents(infoPanel);
}

function _matchMiniCard(item) {
  const sid      = String(item.id || '');
  const isWished = _wishIds.has(sid);
  const img      = normalizeImage(item.main_image);
  const name     = escapeHtml(item.name || '');
  const jpy      = formatJPY(Number(item.price_jpy || 0));
  const snapshot = {
    id: sid, name: item.name, mall: item.mall,
    price_jpy: Number(item.price_jpy || 0), price_krw: Number(item.price_krw || 0),
    main_image: item.main_image, detail_images: item.detail_images,
    ai_reason: item.ai_reason, material: item.material, care: item.care,
    source_url: item.source_url, sub_category: item.sub_category,
    category: item.category, colors: item.colors,
  };
  const catLabelMap = { top: '상의', bottom: '하의', outer: '아우터', dress: '원피스' };
  const catLabel    = catLabelMap[(item.category || '').toLowerCase()] || '';
  const genderMap   = { women: '여성', men: '남성' };
  const gLabel      = genderMap[_inferGender(item)] || '';
  const catTagText  = [catLabel, gLabel].filter(Boolean).join(' · ');
  return `
    <div class="match-card" data-match-id="${escapeHtml(sid)}"
         data-match-snapshot="${escapeHtml(JSON.stringify(snapshot))}">
      <img class="match-thumb" src="${img}" alt="${name}"
           onerror="this.src='/assets/cards/card-fashion.svg'"/>
      <div class="match-info">
        ${catTagText ? `<span class="match-cat-tag">${catTagText}</span>` : ''}
        <div class="match-name">${name}</div>
        <div class="match-price">${jpy}</div>
      </div>
      <button class="wish-btn match-wish${isWished ? ' on' : ''}"
              data-wish-id="${escapeHtml(sid)}" type="button"
              title="찜하기">${isWished ? '♥' : '♡'}</button>
    </div>`;
}

// ─── Detail modal ─────────────────────────────────────────────────────────────
const SUBCAT_LABEL    = { tshirt:'티셔츠', shirt:'셔츠/블라우스', knit:'니트/스웨터', hoodie:'후드/맨투맨', pants:'팬츠/슬랙스', skirt:'스커트', denim:'청바지/데님', jacket:'자켓', coat:'코트', dress:'원피스', suit:'수트/점프수트', top:'상의', bottom:'하의', outer:'아우터' };
const SUBCAT_LABEL_JA = { tshirt:'Tシャツ', shirt:'シャツ/ブラウス', knit:'ニット/セーター', hoodie:'パーカー/スウェット', pants:'パンツ/スラックス', skirt:'スカート', denim:'デニム', jacket:'ジャケット', coat:'コート', dress:'ワンピース', suit:'スーツ', top:'トップス', bottom:'ボトムス', outer:'アウター' };

function _buildDetailInfo(info) {
  const isJa = currentLang === 'ja';
  const catMap  = isJa ? SUBCAT_LABEL_JA : SUBCAT_LABEL;
  const catKey  = info.subCategory || info.category;
  const catLabel = catMap[catKey] || catKey;
  const colorRaw = (info.colors || '').split(',').filter(Boolean);
  const rows = [];
  if (catLabel) rows.push({ label: isJa ? 'カテゴリー' : '카테고리', val: catLabel });
  if (colorRaw.length) rows.push({ label: isJa ? 'カラー' : '색상', val: colorRaw.join(' · ') });
  if (info.material) rows.push({ label: isJa ? '素材' : '소재', val: info.material });
  if (info.care)     rows.push({ label: isJa ? 'ケア' : '세탁', val: info.care });
  const rowsHtml = rows.map(r => `<div class="di-row"><span class="di-label">${escapeHtml(r.label)}</span><span class="di-val">${escapeHtml(r.val)}</span></div>`).join('');
  const linkLabel = isJa ? '元ページを見る →' : '원본 쇼핑몰 보기 →';
  const linkHtml  = info.sourceUrl ? `<a class="btn di-link" href="${escapeHtml(info.sourceUrl)}" target="_blank" rel="noopener noreferrer">${linkLabel}</a>` : '';
  return `
    <div class="di-mall">${escapeHtml(info.mall||'')}</div>
    <div class="di-name">${escapeHtml(info.name||'')}</div>
    <div class="di-price">${info.jpy ? formatJPY(info.jpy) : ''}</div>
    <div class="di-krw">${info.krw ? `₩${Number(info.krw).toLocaleString('ko-KR')}` : ''}</div>
    ${rowsHtml}${linkHtml}`;
}

function openDetailModal(name, images, info) {
  const normalized    = (images || []).map(normalizeImage);
  const displayImages = normalized.length ? normalized : [normalizeImage('')];
  detailTitle.textContent = name || t('detail.heading');
  if (!detailMainWrap.querySelector('.detail-zoom-hint')) {
    const hint = document.createElement('span');
    hint.className = 'detail-zoom-hint'; hint.textContent = '100%';
    detailMainWrap.appendChild(hint);
  }
  _resetZoom();
  detailMain.src = displayImages[0];
  detailMain.onerror = () => { detailMain.src = '/assets/cards/card-fashion.svg'; };
  if (displayImages.length > 1) {
    detailStrip.innerHTML = displayImages.map(src => `<img src="${src}" alt="detail" loading="lazy" onerror="this.src='/assets/cards/card-fashion.svg'"/>`).join('');
    detailStrip.hidden = false;
    const imgs = detailStrip.querySelectorAll('img');
    imgs[0]?.classList.add('active');
    imgs.forEach(img => img.addEventListener('click', () => {
      detailMain.src = img.src;
      detailMain.onerror = () => { detailMain.src = '/assets/cards/card-fashion.svg'; };
      imgs.forEach(i => i.classList.remove('active')); img.classList.add('active'); _resetZoom();
    }));
  } else {
    detailStrip.innerHTML = ''; detailStrip.hidden = true;
  }
  const infoPanel = document.getElementById('detail-info');
  if (infoPanel) {
    let html = info ? _buildDetailInfo(info) : '';

    // ── 매치 추천 섹션 (항상 OpenAI로 선별) ─────────────────────────────
    const currentId      = info ? String(info.itemId || '') : '';
    const currentCat     = info ? (info.category || '') : '';
    const selectedGender = selectedTagValue('tg-gender', 'all');
    const isJa           = currentLang === 'ja';
    const matchLabel     = isJa ? 'このアイテムと合わせて' : '이 아이템과 매치해보세요';

    if (currentId) {
      // 로딩 플레이스홀더 항상 표시
      html += `<div class="match-loading match-section"
        style="opacity:.45;font-family:var(--f-mono);font-size:.6rem;
               letter-spacing:.1em;color:var(--purple);padding-top:12px;
               border-top:1px solid var(--border);margin-top:6px;">
        ✦ ${matchLabel} …
      </div>`;
    }

    infoPanel.innerHTML = html;
    _attachMatchCardEvents(infoPanel);

    if (currentId) {
      // 토큰 발행: 이전 미완료 async 요청을 무효화
      const myToken = ++_matchReqToken;
      // 풀에서 현재 아이템 전체 데이터 조회 (없으면 info로 구성)
      const fullItem = _buildItemPool(null).find(it => String(it.id) === currentId);
      const currentItemData = fullItem || {
        id: currentId,
        name: info.name || '',
        category: currentCat,
        sub_category: info.subCategory || '',
        colors: (info.colors || '').split(',').filter(Boolean),
        material: info.material || '',
        tags: [],
      };
      _fetchAndRenderComplement(currentItemData, selectedGender, infoPanel, myToken);
    }
  }
  detailModal.hidden = false;
}

function closeDetailModal() {
  detailModal.hidden = true; detailMain.src = ''; detailStrip.innerHTML = ''; detailStrip.hidden = false;
  const infoPanel = document.getElementById('detail-info');
  if (infoPanel) infoPanel.innerHTML = '';
  _resetZoom();
}

// ─── Product card (위시리스트 하트 포함) ────────────────────────────────────
function productCard(item) {
  const sid        = String(item.id || '');
  const isWished   = _wishIds.has(sid);
  const mainImage  = normalizeImage(item.main_image);
  const rawDetails = (item.detail_images || []).slice(0, 10).map(normalizeImage);
  const allImages  = [mainImage, ...rawDetails.filter(u => u !== mainImage)];
  const detailAttr = encodeURIComponent(JSON.stringify(allImages));
  const safeName   = escapeHtml(item.name);
  const safeMall   = escapeHtml(item.mall);
  const safeReason = escapeHtml(item.ai_reason || '');
  const krwVal     = Number(item.price_krw || 0);
  const jpyVal     = Number(item.price_jpy || 0);

  // 위시리스트 저장용 스냅샷 (data-* 속성에 JSON으로)
  const snapshot = {
    id: sid, name: item.name, mall: item.mall,
    price_jpy: jpyVal, price_krw: krwVal,
    main_image: item.main_image, detail_images: item.detail_images,
    ai_reason: item.ai_reason, material: item.material, care: item.care,
    source_url: item.source_url, sub_category: item.sub_category,
    category: item.category, colors: item.colors,
  };

  return `
    <article class="product"
      data-id="${escapeHtml(sid)}"
      data-detail-images="${detailAttr}"
      data-name="${safeName}"
      data-mall="${safeMall}"
      data-category="${escapeHtml(item.category||'')}"
      data-sub-category="${escapeHtml(item.sub_category||'')}"
      data-colors="${escapeHtml((item.colors||[]).join(','))}"
      data-material="${escapeHtml(item.material||'')}"
      data-care="${escapeHtml(item.care||'')}"
      data-source-url="${escapeHtml(item.source_url||'')}"
      data-krw="${krwVal}"
      data-jpy="${jpyVal}"
      data-snapshot="${escapeHtml(JSON.stringify(snapshot))}">
      <div class="thumb">
        <img src="${mainImage}" alt="${safeName}" loading="lazy" onerror="this.src='/assets/cards/card-fashion.svg'"/>
        <button class="wish-btn${isWished ? ' on' : ''}" data-wish-id="${escapeHtml(sid)}" type="button" title="찜하기">${isWished ? '♥' : '♡'}</button>
      </div>
      <div class="body">
        <div class="mall">${safeMall}</div>
        <div class="title">${safeName}</div>
        <div class="price"><strong>${formatJPY(jpyVal)}</strong></div>
        <div class="meta">
          <span class="krw-badge" data-krw="${krwVal}">${t('badge.krw')}₩${krwVal.toLocaleString('ko-KR')}</span>
        </div>
        ${safeReason ? `<div class="ai-reason"><span class="ai-reason-label">✦ AI 스타일링</span>${safeReason}</div>` : ''}
        <button class="btn primary pay" data-id="${escapeHtml(sid)}">${t('btn.pay')}</button>
      </div>
    </article>`;
}

// ─── Pagination ───────────────────────────────────────────────────────────────
const PAGE_SIZE = 20;
let currentPage = 0, totalItems = 0, pageCache = {}, lastPayload = null, _lastRenderedItems = [];
const _matchPool = new Map(); // /api/match-complement 결과 캐시 (클릭 재진입용)
let _matchReqToken = 0;        // 경쟁 조건 방지: openDetailModal 호출마다 증가
const paginationEl = document.getElementById('pagination');

async function goToPage(page) {
  if (pageCache[page]) {
    currentPage = page;
    renderItems(currentLang === 'ja' ? await applyTranslations(pageCache[page]) : pageCache[page]);
    renderPagination();
    list.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  setStatus(t('status.loading'));
  showSkeletons(8);
  try {
    const result  = await getRecommendations({ ...lastPayload, page, page_size: PAGE_SIZE });
    currentPage   = page; totalItems = result.total; pageCache[page] = result.items;
    const items   = currentLang === 'ja' ? await applyTranslations(result.items) : result.items;
    renderItems(items); renderPagination();
    list.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) { setStatus(`${t('status.error')}${err.message}`); }
  finally { setStatus(''); }
}

function renderItems(items) { _lastRenderedItems = items; list.innerHTML = items.map(productCard).join(''); }

function renderPagination() {
  if (!paginationEl) return;
  const totalPages = Math.ceil(totalItems / PAGE_SIZE);
  if (totalPages <= 1) { paginationEl.innerHTML = ''; return; }
  const start = currentPage * PAGE_SIZE + 1;
  const end   = Math.min((currentPage + 1) * PAGE_SIZE, totalItems);
  const half  = 2;
  let from = Math.max(0, currentPage - half), to = Math.min(totalPages - 1, currentPage + half);
  if (to - from < 4) { if (from === 0) to = Math.min(totalPages - 1, 4); else from = Math.max(0, to - 4); }
  const pageButtons = [];
  for (let i = from; i <= to; i++) {
    pageButtons.push(`<button class="page-num${i === currentPage ? ' active' : ''}" data-page="${i}">${i + 1}</button>`);
  }
  paginationEl.innerHTML = `
    <button class="page-btn" id="btn-prev" ${currentPage === 0 ? 'disabled' : ''}>← 이전</button>
    ${pageButtons.join('')}
    <button class="page-btn" id="btn-next" ${currentPage >= totalPages - 1 ? 'disabled' : ''}>다음 →</button>
    <span class="page-info">${start}–${end} / 총 ${totalItems}개</span>`;
  document.getElementById('btn-prev')?.addEventListener('click', () => goToPage(currentPage - 1));
  document.getElementById('btn-next')?.addEventListener('click', () => goToPage(currentPage + 1));
  paginationEl.querySelectorAll('.page-num').forEach(btn => {
    btn.addEventListener('click', () => goToPage(Number(btn.dataset.page)));
  });
}

// ─── Translation (JA mode) ────────────────────────────────────────────────────
const _translationCache = {};
async function applyTranslations(items) {
  const toTranslate = [];
  items.forEach(item => {
    [item.name, item.material, item.care, item.ai_reason].forEach(text => {
      if (text && !_translationCache[text]) toTranslate.push(text);
    });
  });
  if (toTranslate.length > 0) {
    try {
      const resp = await fetch('/api/translate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texts: toTranslate, source: 'ko', target: 'ja' }),
      });
      if (resp.ok) {
        const data = await resp.json();
        toTranslate.forEach((text, i) => { _translationCache[text] = data.translations[i] || text; });
      }
    } catch (_) { /* 실패 시 원본 */ }
  }
  return items.map(item => ({
    ...item,
    name:      _translationCache[item.name]      || item.name,
    material:  _translationCache[item.material]  || item.material,
    care:      _translationCache[item.care]       || item.care,
    ai_reason: _translationCache[item.ai_reason] || item.ai_reason,
  }));
}

// ─── Recommendations ──────────────────────────────────────────────────────────
async function fetchRecommendations() {
  const budget   = selectedBudget();
  const keywords = selectedTagValues('tg-keyword');
  lastPayload = {
    gender:       selectedTagValue('tg-gender', 'all'),
    color:        selectedTagValue('tg-color', ''),
    style:        selectedTagValue('tg-style', ''),
    keyword:      keywords,
    category:     selectedTagValue('tg-category', 'all'),
    min_price_krw: budget.min,
    max_price_krw: budget.max,
    email:        null,
  };
  pageCache = {}; currentPage = 0; totalItems = 0;
  setStatus(t('status.loading'));
  showSkeletons(8);
  try {
    const result = await getRecommendations({ ...lastPayload, page: 0, page_size: PAGE_SIZE });
    totalItems     = result.total;
    pageCache[0]   = result.items;
    if (totalItems === 0) {
      countNode.textContent = `0 ${t('result.items')}`;
      list.innerHTML = `<div class="empty-state"><p class="empty-msg">${t('result.empty')}</p><p class="empty-hint">${t('result.empty.hint')}</p></div>`;
      if (paginationEl) paginationEl.innerHTML = '';
      return;
    }
    countNode.textContent = `총 ${totalItems} ${t('result.items')}`;
    const items = currentLang === 'ja' ? await applyTranslations(result.items) : result.items;
    renderItems(items);
    renderPagination();
  } catch (err) {
    setStatus(`${t('status.error')}${err.message}`);
    list.innerHTML = '';
  } finally { setStatus(''); }
}

// ─── Stripe ───────────────────────────────────────────────────────────────────
async function prepareStripe(publishableKey, clientSecret) {
  if (!window.Stripe) throw new Error('Stripe.js 로드 실패');
  if (!stripe) stripe = window.Stripe(publishableKey);
  if (paymentElement) { paymentElement.unmount(); paymentElement = null; }
  elements = stripe.elements({ clientSecret, locale: currentLang === 'ja' ? 'ja' : 'ko' });
  paymentElement = elements.create('payment', { layout: 'tabs' });
  paymentElement.mount('#payment-element');
}

async function startPayment(productId, cardName = null) {
  const email  = document.getElementById('pay-email').value.trim() || null;
  const intent = await createPaymentIntent({ product_id: productId, email });
  activePayment = intent;
  payTitle.textContent  = cardName || intent.product_name;
  payAmount.textContent = formatJPY(intent.amount_jpy);
  if (intent.demo_mode) {
    document.getElementById('card-wrap').hidden = true;
    openModal(); return;
  }
  document.getElementById('card-wrap').hidden = false;
  await prepareStripe(intent.publishable_key, intent.client_secret);
  openModal();
}

async function _handlePaymentSuccess(paymentIntentId) {
  const email       = document.getElementById('pay-email').value.trim() || null;
  const productName = activePayment?.product_name || payTitle.textContent;
  const amountJpy   = activePayment?.amount_jpy   || 0;
  const mall        = activePayment?.mall          || '';

  try {
    const res = await completePayment({
      product_id: activePayment?.product_id || '',
      payment_intent_id: paymentIntentId,
      email, status: 'succeeded',
    });
    savePurchase({
      payment_intent_id: paymentIntentId,
      product_id:   activePayment?.product_id || '',
      product_name: res.product_name || productName,
      amount_jpy:   res.amount_jpy   || amountJpy,
      mall:         res.mall         || mall,
      email:        email || '',
      image:        '',
    });
    if (email) await sendConfirmationEmail(email, res.product_name || productName, res.amount_jpy || amountJpy);
    showToast('🎉 결제가 완료되었습니다!', 'success', 4000);
  } catch (err) {
    setStatus(`${t('status.pay_reflect_error')}${err.message}`);
  }
  closeModal();
}

async function submitPayment() {
  if (!activePayment) return;
  paySubmit.disabled = true;
  try {
    if (activePayment.demo_mode) {
      await _handlePaymentSuccess('demo_intent'); return;
    }
    const result = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: `${window.location.origin}/fashion.html?product_id=${encodeURIComponent(activePayment.product_id)}` },
      redirect: 'if_required',
    });
    if (result.error) { setStatus(result.error.message || t('status.failed')); return; }
    const status = result.paymentIntent?.status;
    if (status === 'succeeded') { await _handlePaymentSuccess(result.paymentIntent.id); return; }
    if (status === 'processing' || status === 'requires_action') {
      setStatus(t('status.processing')); closeModal(); return;
    }
    setStatus(`결제 상태: ${status || 'unknown'}`);
  } catch (error) {
    setStatus(`${t('status.error')}${error.message}`);
  } finally { paySubmit.disabled = false; }
}

async function handleRedirectReturn() {
  const params         = new URLSearchParams(window.location.search);
  const intentId       = params.get('payment_intent');
  const redirectStatus = params.get('redirect_status');
  const productId      = params.get('product_id');
  if (!intentId && !redirectStatus) return;
  try {
    if (redirectStatus === 'succeeded' && productId) {
      await _handlePaymentSuccess(intentId || 'redirect_intent');
    } else if (redirectStatus === 'processing') { setStatus(t('status.processing'));
    } else if (redirectStatus === 'failed')     { setStatus(t('status.failed')); }
  } catch (error) { setStatus(`${t('status.pay_reflect_error')}${error.message}`); }
  finally { history.replaceState({}, '', '/fashion.html'); }
}

// ─── Event listeners ──────────────────────────────────────────────────────────
form.addEventListener('submit', async e => {
  e.preventDefault();
  try { await fetchRecommendations(); } catch (err) { setStatus(`${t('status.error')}${err.message}`); }
});

document.getElementById('btn-reset').addEventListener('click', () => {
  form.reset(); pageCache = {}; currentPage = 0; totalItems = 0; lastPayload = null;
  countNode.textContent = `0 ${t('result.items')}`;
  list.innerHTML = ''; if (paginationEl) paginationEl.innerHTML = ''; setStatus('');
  document.querySelectorAll('.tag-group').forEach(group => {
    if (group.dataset.single === 'true') {
      const active = group.querySelector('.tag.on');
      if (!active) group.querySelector('.tag')?.classList.add('on');
    } else {
      group.querySelectorAll('.tag.on').forEach(tag => tag.classList.remove('on'));
    }
  });
});

// 결과 리스트 이벤트 (위시리스트 + 결제 + 상세)
list.addEventListener('click', async e => {
  // 위시리스트 버튼
  const wishBtn = e.target.closest('.wish-btn');
  if (wishBtn) {
    e.stopPropagation();
    const card     = wishBtn.closest('.product');
    const snapshot = JSON.parse(decodeURIComponent(card?.dataset.snapshot || '{}'));
    toggleWish(wishBtn.dataset.wishId, snapshot);
    return;
  }
  // 결제 버튼
  const payBtn = e.target.closest('button[data-id]');
  if (payBtn && payBtn.classList.contains('pay')) {
    const card     = payBtn.closest('.product');
    const cardName = card?.dataset.name || null;
    try { await startPayment(payBtn.dataset.id, cardName); }
    catch (err) { setStatus(`${t('status.pay_error')}${err.message}`); }
    return;
  }
  // 상세 이미지 모달
  try {
    const card = e.target.closest('.product');
    if (!card) return;
    const images = JSON.parse(decodeURIComponent(card.dataset.detailImages || '[]'));
    openDetailModal(card.dataset.name || t('detail.heading'), images, {
      itemId: card.dataset.id,
      name: card.dataset.name, mall: card.dataset.mall,
      category: card.dataset.category, subCategory: card.dataset.subCategory,
      colors: card.dataset.colors, material: card.dataset.material,
      care: card.dataset.care, sourceUrl: card.dataset.sourceUrl,
      krw: card.dataset.krw, jpy: card.dataset.jpy,
    });
  } catch (_) { openDetailModal(t('detail.heading'), ['/assets/cards/card-fashion.svg'], null); }
});

// 위시리스트 모달 안 이벤트 (위시 토글 + 결제)
document.getElementById('wish-list').addEventListener('click', async e => {
  const wishBtn = e.target.closest('.wish-btn');
  if (wishBtn) {
    e.stopPropagation();
    const card     = wishBtn.closest('.product');
    const snapshot = JSON.parse(decodeURIComponent(card?.dataset.snapshot || '{}'));
    toggleWish(wishBtn.dataset.wishId, snapshot);
    // 위시 모달 재렌더
    const items = Object.values(_wishItems);
    const wl    = document.getElementById('wish-list');
    const we    = document.getElementById('wish-empty');
    if (items.length === 0) { wl.innerHTML = ''; we.style.display = 'block'; }
    else { we.style.display = 'none'; wl.innerHTML = items.map(productCard).join(''); }
    return;
  }
  const payBtn = e.target.closest('button[data-id]');
  if (payBtn && payBtn.classList.contains('pay')) {
    closeWishModal();
    const card     = payBtn.closest('.product');
    const cardName = card?.dataset.name || null;
    try { await startPayment(payBtn.dataset.id, cardName); }
    catch (err) { setStatus(`${t('status.pay_error')}${err.message}`); }
  }
});

paySubmit.addEventListener('click', submitPayment);
payClose.addEventListener('click',  closeModal);
payCancel.addEventListener('click', closeModal);
detailClose.addEventListener('click', closeDetailModal);

// 위시리스트 헤더 버튼
document.getElementById('open-wish').addEventListener('click', openWishModal);
document.getElementById('wish-close').addEventListener('click', closeWishModal);

// 언어 토글
document.querySelectorAll('.lang-btn').forEach(btn => {
  btn.addEventListener('click', () => applyLanguage(btn.dataset.lang));
});

// ─── Init ─────────────────────────────────────────────────────────────────────
setupTagGroups();
_updateWishCount();
handleRedirectReturn();
applyLanguage('ko');
