/* ── SEOULFIT AI Photobooth ─────────────────────────────────────────── */
'use strict';

const NEXT_BASE    = '';  // FastAPI 통합: 상대경로 사용
const MAX_REQUESTS = 5;

// ── i18n ─────────────────────────────────────────────────────────────────
const I18N = {
  ko: {
    'hero.title':    '포토부스',
    'hero.desc':     '사진 한 장으로 완성하는 나만의 감성 컷',
    'step.theme':    '테마',
    'step.input':    '입력',
    'step.generate': '생성',
    's1.title':      '스타일 선택',
    's1.desc':       '원하는 캐릭터 스타일을 선택해 주세요',
    's1.next':       '다음 단계 →',
    's2.title':      '입력 방법 선택',
    's2.desc':       '셀카 또는 텍스트로 나를 표현해 주세요',
    's2.tab.selfie': '📷 셀카 업로드',
    's2.tab.text':   '✏️ 텍스트 설명',
    's2.drop.title': '셀카를 드래그하거나 클릭하여 업로드',
    's2.drop.hint':  'JPG · PNG · WEBP · 최대 10MB',
    's2.drop.sub':   '이미지는 자동으로 리사이즈됩니다',
    's2.remove':     '사진 제거',
    's2.guide':      '📸 셀카를 사용하면 더 정확도가 높아요!',
    's2.placeholder':'예) 긴 검은 머리카락, 동양적인 외모, 흰 티셔츠에 청바지 착용, 20대 여성...',
    's2.outfit.label':       '🧥 원하는 의상 설명',
    's2.outfit.placeholder': '예) 검은 가죽 재킷, 흰 미니 드레스, 청바지에 오버핏 후드...',
    's2.generate':   '🎬 이미지 생성',
    's3.title':      '생성 결과',
    's3.sub':        '4장 동시 생성 · 잠시만 기다려 주세요',
    'gen.analyze':   '🔍 얼굴을 분석하고 있어요...',
    'gen.creating':  '🎨 이미지를 생성하고 있어요...',
    'gen.composing': '✨ 네컷을 합성하고 있어요...',
    'btn.prev':      '← 이전',
    'btn.download':  '다운로드 ↓',
    'btn.restart':   '처음부터 다시',
    'btn.retry':     '다시 시도',
    'btn.home':      '처음으로',
  },
  ja: {
    'hero.title':    'フォトブース',
    'hero.desc':     '一枚の写真で完成する、私だけの感性カット',
    'step.theme':    'テーマ',
    'step.input':    '入力',
    'step.generate': '生成',
    's1.title':      'スタイル選択',
    's1.desc':       'キャラクタースタイルを選んでください',
    's1.next':       '次のステップ →',
    's2.title':      '入力方法を選択',
    's2.desc':       '自撮りまたはテキストで自分を表現してください',
    's2.tab.selfie': '📷 自撮りアップロード',
    's2.tab.text':   '✏️ テキスト説明',
    's2.drop.title': '自撮りをドラッグまたはクリックしてアップロード',
    's2.drop.hint':  'JPG · PNG · WEBP · 最大 10MB',
    's2.drop.sub':   '画像は自動でリサイズされます',
    's2.remove':     '写真を削除',
    's2.guide':      '📸 自撮りを使うとより正確です！',
    's2.placeholder':'例）長い黒髪、アジア系の顔立ち、白いTシャツとジーンズ、20代女性...',
    's2.outfit.label':       '🧥 着たい服の説明',
    's2.outfit.placeholder': '例）黒いレザージャケット、白いミニドレス、デニムにオーバーサイズフーディー...',
    's2.generate':   '🎬 画像を生成',
    's3.title':      '生成結果',
    's3.sub':        '4枚同時生成 · しばらくお待ちください',
    'gen.analyze':   '🔍 顔を分析しています...',
    'gen.creating':  '🎨 画像を生成しています...',
    'gen.composing': '✨ 4カットを合成しています...',
    'btn.prev':      '← 戻る',
    'btn.download':  'ダウンロード ↓',
    'btn.restart':   '最初からやり直す',
    'btn.retry':     '再試行',
    'btn.home':      'トップへ',
  },
};

let currentLang = 'ko';
function t(key) { return (I18N[currentLang] || I18N.ko)[key] || (I18N.ko[key] || key); }

// ── State ────────────────────────────────────────────────────────────────
const S = {
  step:            1,
  styleId:         null,
  styleName:       null,
  styleColor:      null,
  inputMode:        'selfie',
  imageBase64:      null,
  textDescription:  null,
  outfitDescription: null,
  resultImage:      null,
  requestCount:    0,
  styles:          [],
};

const nameTranslations = {};

// ── DOM helpers ──────────────────────────────────────────────────────────
const $    = id => document.getElementById(id);
const show = el => el && el.classList.remove('pb-hidden');
const hide = el => el && el.classList.add('pb-hidden');

// ── 클라이언트 이미지 리사이즈 ──────────────────────────────────────────
function resizeImage(file, maxPx = 1024) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = e => {
      const img = new Image();
      img.onerror = reject;
      img.onload = () => {
        let { width: w, height: h } = img;
        if (w > maxPx || h > maxPx) {
          const ratio = Math.min(maxPx / w, maxPx / h);
          w = Math.round(w * ratio);
          h = Math.round(h * ratio);
        }
        const canvas = document.createElement('canvas');
        canvas.width  = w;
        canvas.height = h;
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL('image/jpeg', 0.9).split(',')[1]);
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  });
}

// ── 스타일 로드 ──────────────────────────────────────────────────────────
async function fetchStyles() {
  const res = await fetch(`/api/photobooth/styles`);
  if (!res.ok) throw new Error('스타일 로드 실패');
  return res.json();
}

// ── DeepL 번역 (스타일 이름용) ───────────────────────────────────────────
async function translateName(koName) {
  if (nameTranslations[koName]) return nameTranslations[koName];
  try {
    const res = await fetch('/api/translate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ texts: [koName], source: 'ko', target: 'ja' }),
    });
    if (res.ok) {
      const data = await res.json();
      nameTranslations[koName] = data.translations[0] || koName;
    }
  } catch (_) { /* 실패 시 원본 유지 */ }
  return nameTranslations[koName] || koName;
}

// ── i18n 적용 (data-i18n 전체) ───────────────────────────────────────────
function applyI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const val = t(el.getAttribute('data-i18n'));
    if (val) el.textContent = val;
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const val = t(el.getAttribute('data-i18n-placeholder'));
    if (val) el.placeholder = val;
  });
}

// ── 선택된 스타일 pill 업데이트 ──────────────────────────────────────────
function updateSelectedPill() {
  const pill = $('selected-style-pill');
  if (!S.styleId || !pill) { hide(pill); return; }

  const dot   = pill.querySelector('.pill-dot');
  const label = pill.querySelector('.pill-label');

  if (dot) dot.style.background = S.styleColor || '#888';
  if (label) label.textContent = currentLang === 'ja'
    ? (nameTranslations[S.styleName] || S.styleName)
    : S.styleName || '';

  show(pill);
}

// ── 갤러리 렌더링 ────────────────────────────────────────────────────────
function renderStyles(styles) {
  const grid = $('theme-grid');
  grid.innerHTML = styles.map(s => `
    <div class="gallery-item"
         data-style="${s.style_id}"
         data-name="${s.display_name}"
         data-color="${s.border_color}"
         data-img="${NEXT_BASE}/${s.gallery_image}"
         role="button" tabindex="0"
         title="${s.display_name}"
         aria-label="${s.display_name}">
      <img
        src="${NEXT_BASE}/${s.gallery_image}"
        alt="${s.display_name}"
        loading="lazy"
        onerror="this.parentElement.style.background='${s.border_color}22'"
      />
      <div class="gallery-overlay">
        <div class="gallery-overlay-name" data-ko="${s.display_name}">${s.display_name}</div>
      </div>
    </div>
  `).join('');

  grid.querySelectorAll('.gallery-item').forEach(item => {
    // 단일 클릭 → 선택
    const select = () => {
      grid.querySelectorAll('.gallery-item').forEach(c => c.classList.remove('selected'));
      item.classList.add('selected');
      S.styleId    = item.dataset.style;
      S.styleName  = item.dataset.name;
      S.styleColor = item.dataset.color;
      $('step1-next').disabled = false;
      updateSelectedPill();
    };
    item.addEventListener('click', select);
    item.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(); }
    });

    // 더블 클릭 → 라이트박스
    item.addEventListener('dblclick', e => {
      e.stopPropagation();
      openLightbox(item.dataset.img, item.dataset.name);
    });
  });
}

// ── 라이트박스 ───────────────────────────────────────────────────────────
function openLightbox(src, name) {
  $('pb-lightbox-img').src = src;
  $('pb-lightbox-name').textContent = currentLang === 'ja'
    ? (nameTranslations[name] || name)
    : name;
  show($('pb-lightbox'));
  document.body.style.overflow = 'hidden';
}

function closeLightbox() {
  hide($('pb-lightbox'));
  document.body.style.overflow = '';
}

function setupLightbox() {
  $('pb-lightbox-close').addEventListener('click', closeLightbox);
  $('pb-lightbox').addEventListener('click', e => {
    if (e.target === $('pb-lightbox')) closeLightbox();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeLightbox();
  });
}

// ── 언어 적용 ────────────────────────────────────────────────────────────
async function applyLang(lang) {
  currentLang = lang;

  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.lang === lang);
  });

  if (lang === 'ja') {
    await Promise.all(S.styles.map(s => translateName(s.display_name)));
    document.querySelectorAll('.gallery-overlay-name').forEach(el => {
      const ko = el.dataset.ko || el.textContent;
      el.textContent = nameTranslations[ko] || ko;
    });
  } else {
    document.querySelectorAll('.gallery-overlay-name').forEach(el => {
      el.textContent = el.dataset.ko || el.textContent;
    });
  }

  applyI18n();
  updateSelectedPill();
}

// ── 언어 토글 설정 ───────────────────────────────────────────────────────
function setupLangToggle() {
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.addEventListener('click', () => applyLang(btn.dataset.lang));
  });
}

// ── Step 2 입력 탭 ────────────────────────────────────────────────────────
function setupInputTabs() {
  const tabs = document.querySelectorAll('.pb-tab[data-tab]');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      S.inputMode = tab.dataset.tab;
      tabs.forEach(t => t.classList.toggle('active', t === tab));
      show($('pane-selfie'));
      hide($('pane-text'));
      if (S.inputMode === 'text') {
        hide($('pane-selfie'));
        show($('pane-text'));
      }
      updateStep2Next();
    });
  });
}

// ── Step 2 다음 버튼 상태 ─────────────────────────────────────────────────
function updateStep2Next() {
  const btn = $('step2-next');
  if (!btn) return;
  btn.disabled = S.inputMode === 'selfie'
    ? !S.imageBase64
    : ($('pb-text-input')?.value || '').trim().length === 0;
}

// ── Step 이동 ────────────────────────────────────────────────────────────
function goToStep(n) {
  document.querySelectorAll('.pb-panel').forEach(p => p.classList.add('pb-hidden'));
  const panel = $(`step-${n}`);
  if (panel) panel.classList.remove('pb-hidden');

  document.querySelectorAll('.pb-step').forEach(s => {
    const sn = parseInt(s.dataset.step, 10);
    s.classList.remove('active', 'done');
    if (sn === n)    s.classList.add('active');
    else if (sn < n) s.classList.add('done');
  });

  S.step = n;
  if (n === 3) startGeneration();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── 셀카 드롭존 ──────────────────────────────────────────────────────────
function setupDropzone() {
  const zone      = $('face-dropzone');
  const fileInput = $('face-file');
  if (!zone || !fileInput) return;

  zone.addEventListener('click', () => fileInput.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) loadSelfie(file);
  });
  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) loadSelfie(fileInput.files[0]);
  });

  $('face-remove').addEventListener('click', () => {
    S.imageBase64 = null;
    hide($('face-preview'));
    show(zone);
    fileInput.value = '';
    updateStep2Next();
  });
}

async function loadSelfie(file) {
  try {
    S.imageBase64 = await resizeImage(file);
    $('face-preview-img').src = `data:image/jpeg;base64,${S.imageBase64}`;
    hide($('face-dropzone'));
    show($('face-preview'));
    updateStep2Next();
  } catch (err) {
    console.error('이미지 로드 실패:', err);
  }
}

// ── Progress 메시지 ──────────────────────────────────────────────────────
let progressTimers = [];

function clearProgressTimers() {
  progressTimers.forEach(clearTimeout);
  progressTimers = [];
}

function getProgressMessages(isSelfie) {
  return isSelfie
    ? [
        { key: 'gen.analyze',   delay: 0 },
        { key: 'gen.creating',  delay: 3000 },
        { key: 'gen.composing', delay: 18000 },
      ]
    : [
        { key: 'gen.creating',  delay: 0 },
        { key: 'gen.composing', delay: 18000 },
      ];
}

// ── 이미지 생성 ──────────────────────────────────────────────────────────
async function startGeneration() {
  const isSelfie = S.inputMode === 'selfie';

  if (isSelfie && !S.imageBase64) return;
  if (!isSelfie) {
    S.textDescription = ($('pb-text-input')?.value || '').trim();
    if (!S.textDescription) return;
  }
  if (!S.styleId) return;

  if (S.requestCount >= MAX_REQUESTS) {
    $('pb-error-msg').textContent = currentLang === 'ja'
      ? `リクエスト回数が${MAX_REQUESTS}回を超えました。ページを更新してください。`
      : `요청 횟수가 ${MAX_REQUESTS}회를 초과했습니다. 페이지를 새로고침해주세요.`;
    hide($('pb-generating'));
    show($('pb-error'));
    return;
  }

  show($('pb-generating'));
  hide($('pb-result'));
  hide($('pb-error'));

  clearProgressTimers();
  const msgs = getProgressMessages(isSelfie);
  $('pb-gen-text').textContent = t(msgs[0].key);
  $('pb-gen-sub').textContent  = t('s3.sub');

  msgs.slice(1).forEach(({ key, delay }) => {
    progressTimers.push(setTimeout(() => {
      $('pb-gen-text').textContent = t(key);
    }, delay));
  });

  S.outfitDescription = ($('pb-outfit-input')?.value || '').trim() || null;

  const payload = { styleId: S.styleId };
  if (isSelfie) payload.imageBase64     = S.imageBase64;
  else          payload.textDescription = S.textDescription;
  if (S.outfitDescription) payload.outfitDescription = S.outfitDescription;

  try {
    const res = await fetch(`/api/photobooth/generate`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });

    clearProgressTimers();

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `서버 오류 (${res.status})`);

    S.resultImage = data.resultImage;
    S.requestCount++;
    showResult();
  } catch (err) {
    clearProgressTimers();
    hide($('pb-generating'));
    const prefix = currentLang === 'ja' ? 'エラーが発生しました: ' : '오류가 발생했어요: ';
    $('pb-error-msg').textContent = prefix + err.message;
    show($('pb-error'));
  }
}

// ── 결과 표시 ────────────────────────────────────────────────────────────
function showResult() {
  hide($('pb-generating'));
  $('pb-result-images').innerHTML = `
    <div class="pb-result-img" style="max-width:420px;margin:0 auto">
      <img src="data:image/jpeg;base64,${S.resultImage}" alt="인생네컷 합성본">
    </div>`;
  show($('pb-result'));
}

// ── 다운로드 ─────────────────────────────────────────────────────────────
function downloadImage() {
  if (!S.resultImage) return;
  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const a = document.createElement('a');
  a.href     = `data:image/jpeg;base64,${S.resultImage}`;
  a.download = `seoulfit-${S.styleId}-${dateStr}.jpg`;
  a.click();
}

// ── Init ─────────────────────────────────────────────────────────────────
async function init() {
  try {
    const styles = await fetchStyles();
    S.styles = styles;
    renderStyles(styles);
  } catch {
    $('theme-grid').innerHTML = '<p class="status">스타일을 불러오지 못했습니다. Next.js 서버가 실행 중인지 확인해 주세요.</p>';
  }

  setupLangToggle();
  setupLightbox();

  $('step1-next').addEventListener('click', () => goToStep(2));

  $('pill-remove').addEventListener('click', () => {
    S.styleId = S.styleName = S.styleColor = null;
    document.querySelectorAll('.gallery-item').forEach(c => c.classList.remove('selected'));
    hide($('selected-style-pill'));
    $('step1-next').disabled = true;
  });

  setupInputTabs();
  setupDropzone();
  $('pb-text-input')?.addEventListener('input', updateStep2Next);
  $('step2-prev').addEventListener('click', () => goToStep(1));
  $('step2-next').addEventListener('click', () => {
    if (!$('step2-next').disabled) goToStep(3);
  });

  $('pb-download').addEventListener('click', downloadImage);
  $('pb-restart').addEventListener('click', () => location.reload());
  $('pb-retry').addEventListener('click', () => startGeneration());
  $('pb-error-restart').addEventListener('click', () => location.reload());
}

document.addEventListener('DOMContentLoaded', init);
