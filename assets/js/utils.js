// ─── SEOULFIT 공통 유틸리티 ───────────────────────────────────────────────────

export function escapeHtml(v) {
  return String(v ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
export { escapeHtml as escHtml };

export function formatJPY(v) {
  return new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY' }).format(v || 0);
}
