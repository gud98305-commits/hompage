// ─── SEOULFIT My Page ─────────────────────────────────────────────────────────

function formatJPY(v) {
  return new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY' }).format(v || 0);
}
function formatDate(iso) {
  return new Date(iso).toLocaleString('ko-KR', {
    year: 'numeric', month: 'long', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}
function escHtml(v) {
  return String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
    .replaceAll('"','&quot;').replaceAll("'",'&#39;');
}

// ── 위시리스트 미리보기 ──────────────────────────────────────────────────────
function renderWishPreview() {
  const items  = Object.values(JSON.parse(localStorage.getItem('seoulfit_wishlist_data') || '{}'));
  const area   = document.getElementById('wish-preview');
  const empty  = document.getElementById('wish-empty-my');
  const label  = document.getElementById('wish-count-label');

  if (items.length === 0) {
    area.innerHTML = '';
    empty.style.display = 'block';
    label.textContent   = '0 items';
    return;
  }
  label.textContent   = `${items.length} items`;
  empty.style.display = 'none';
  area.innerHTML = items.slice(0, 8).map(item => {
    const krw = Number(item.price_krw || 0);
    const jpy = Number(item.price_jpy || 0);
    const img = item.main_image || '/assets/cards/card-fashion.svg';
    return `
      <div class="purchase-card">
        <img class="purchase-thumb" src="${escHtml(img)}" alt="${escHtml(item.name)}" onerror="this.src='/assets/cards/card-fashion.svg'"/>
        <div class="purchase-info">
          <div style="font-size:.65rem;color:var(--purple-mid);font-family:var(--f-mono);letter-spacing:.1em;text-transform:uppercase">${escHtml(item.mall||'')}</div>
          <div style="font-weight:500;font-size:.86rem;margin-top:4px;line-height:1.4">${escHtml(item.name)}</div>
          <div style="font-family:var(--f-mono);font-size:.88rem;margin-top:5px">${formatJPY(jpy)}</div>
          <div style="font-size:.7rem;color:var(--muted-ink);font-family:var(--f-mono);margin-top:2px">₩${krw.toLocaleString('ko-KR')}</div>
        </div>
        <span class="purchase-badge">♡ 찜</span>
      </div>`;
  }).join('');
  if (items.length > 8) {
    area.innerHTML += `<p style="text-align:center;font-size:.78rem;color:var(--muted-ink);padding:10px 0">+ ${items.length - 8}개 더</p>`;
  }
}

// ── 구매 이력 ─────────────────────────────────────────────────────────────────
function renderPurchases() {
  const purchases = JSON.parse(localStorage.getItem('seoulfit_purchases') || '[]');
  const listEl    = document.getElementById('purchase-list');
  const emptyEl   = document.getElementById('purchase-empty');
  const countEl   = document.getElementById('purchase-count');

  if (purchases.length === 0) {
    listEl.innerHTML    = '';
    emptyEl.style.display = 'block';
    countEl.textContent   = '0 건';
    return;
  }
  emptyEl.style.display = 'none';
  countEl.textContent   = `총 ${purchases.length}건`;

  listEl.innerHTML = purchases.slice().reverse().map(p => `
    <div class="purchase-card">
      <div class="purchase-info" style="flex:1">
        <div style="font-size:.65rem;color:var(--purple-mid);font-family:var(--f-mono);letter-spacing:.1em;text-transform:uppercase">${escHtml(p.mall||'OttO')}</div>
        <div style="font-weight:500;font-size:.88rem;margin-top:5px;line-height:1.4">${escHtml(p.product_name)}</div>
        <div style="font-family:var(--f-mono);font-size:.92rem;margin-top:6px">${formatJPY(p.amount_jpy)}</div>
        <div class="purchase-date">${formatDate(p.date)}</div>
        ${p.email ? `<div class="purchase-email">📧 ${escHtml(p.email)}</div>` : ''}
      </div>
      <span class="purchase-badge">결제 완료 ✓</span>
    </div>`).join('');
}

// ── Init ──────────────────────────────────────────────────────────────────────
renderWishPreview();
renderPurchases();
