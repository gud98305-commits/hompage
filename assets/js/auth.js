// ─── SEOULFIT Auth ──────────────────────────────────────────────────────────
// Google OAuth + JWT helpers
// Include this script before my.js on pages that need auth.

(function () {
  'use strict';

  // ── Token storage ──────────────────────────────────────────────────────────
  const TOKEN_KEY = 'seoulfit_jwt';
  const AUTH_NEXT_KEY = 'seoulfit_auth_next';

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }
  function setToken(t) {
    localStorage.setItem(TOKEN_KEY, t);
  }
  function removeToken() {
    localStorage.removeItem(TOKEN_KEY);
  }
  function setAuthNext(path) {
    if (!path) return;
    localStorage.setItem(AUTH_NEXT_KEY, path);
  }
  function popAuthNext() {
    const path = localStorage.getItem(AUTH_NEXT_KEY);
    if (path) localStorage.removeItem(AUTH_NEXT_KEY);
    return path;
  }
  function isLoggedIn() {
    return !!getToken();
  }

  // ── Capture token from URL (after OAuth callback redirect) ─────────────────
  (async function captureTokenFromUrl() {
    // fragment(#token=...)를 우선 확인, 없으면 query(?token=...) fallback
    const hashParams = new URLSearchParams(window.location.hash.slice(1));
    const queryParams = new URLSearchParams(window.location.search);
    const token = hashParams.get('token') || queryParams.get('token');
    if (!token) return;
    setToken(token);
    // Clean URL
    const url = new URL(window.location.href);
    url.searchParams.delete('token');
    url.hash = '';
    window.history.replaceState({}, '', url.toString());
    // Sync localStorage wishlist → backend
    await _syncWishlist(token);
    const next = popAuthNext();
    if (next) window.location.replace(next);
  })();

  // ── API helpers ────────────────────────────────────────────────────────────
  async function apiFetch(path, options = {}) {
    const token = getToken();
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(path, { ...options, headers });
    if (res.status === 401) {
      removeToken();
      return null;
    }
    return res.ok ? res.json() : null;
  }

  async function fetchMe() {
    if (!isLoggedIn()) return null;
    return apiFetch('/api/auth/me');
  }

  async function googleLogin(nextPath = null) {
    if (nextPath) setAuthNext(nextPath);
    const data = await apiFetch('/api/auth/google');
    if (data?.url) window.location.href = data.url;
  }

  function logout() {
    removeToken();
    window.location.reload();
  }

  // ── Wishlist sync (localStorage → backend) ─────────────────────────────────
  async function _syncWishlist(token) {
    const raw = localStorage.getItem('seoulfit_wishlist_data');
    const ids = Object.keys(JSON.parse(raw || '{}'));
    if (ids.length === 0) return;
    await fetch('/api/auth/sync', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ wishlist_ids: ids }),
    }).catch(() => {});
  }

  // ── Add/remove wishlist (also syncs to backend when logged in) ──────────────
  async function addWishlist(productId) {
    if (!isLoggedIn()) return;
    await apiFetch('/api/auth/wishlist', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId }),
    });
  }

  async function removeWishlist(productId) {
    if (!isLoggedIn()) return;
    await apiFetch(`/api/auth/wishlist/${encodeURIComponent(productId)}`, {
      method: 'DELETE',
    });
  }

  // ── Expose API ─────────────────────────────────────────────────────────────
  window.SeoulFitAuth = {
    isLoggedIn,
    getToken,
    fetchMe,
    googleLogin,
    setAuthNext,
    logout,
    addWishlist,
    removeWishlist,
  };
})();
