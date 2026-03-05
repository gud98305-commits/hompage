/**
 * OttO 글로벌 언어 관리 + DeepL 번역 유틸리티
 * - localStorage 'otto_lang' 키에 언어 저장 ('ko' | 'ja')
 * - 모든 페이지에서 공유
 * - POST /api/translate 로 DeepL 배치 번역
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'otto_lang';
  const DEFAULT_LANG = 'ko';

  const OttoI18n = {
    getLang() {
      return localStorage.getItem(STORAGE_KEY) || DEFAULT_LANG;
    },

    setLang(lang) {
      localStorage.setItem(STORAGE_KEY, lang);
      window.dispatchEvent(new CustomEvent('otto:lang', { detail: { lang } }));
    },

    isJapanese() {
      return this.getLang() === 'ja';
    },

    /**
     * 텍스트 배열을 현재 언어로 번역.
     * 한국어면 그대로 반환. 일본어면 /api/translate 호출.
     * @param {string[]} texts
     * @returns {Promise<string[]>}
     */
    async translate(texts) {
      if (!texts || texts.length === 0) return texts;
      if (this.getLang() !== 'ja') return texts;

      try {
        const res = await fetch('/api/translate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            texts: texts,
            source: 'ko',
            target: 'ja',
          }),
        });
        if (!res.ok) throw new Error('translate API error');
        const data = await res.json();
        return data.translations || texts;
      } catch (e) {
        console.warn('[OttoI18n] 번역 실패, 원본 반환:', e.message);
        return texts; // graceful fallback
      }
    },

    /**
     * 단일 텍스트 번역 (편의 메서드)
     * @param {string} text
     * @returns {Promise<string>}
     */
    async translateOne(text) {
      const results = await this.translate([text]);
      return results[0] || text;
    },

    /**
     * 모든 .lang-btn / #global-lang-toggle 의 active 상태를 현재 언어에 맞춤
     */
    syncToggles() {
      const lang = this.getLang();
      document.querySelectorAll('.lang-btn').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.lang === lang);
      });
    },

    /**
     * .lang-btn 클릭 이벤트를 등록. 페이지별로 호출.
     * @param {Function|null} onChangeCb - 언어 변경 후 콜백 (선택)
     */
    initToggles(onChangeCb) {
      this.syncToggles();
      document.querySelectorAll('.lang-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          const newLang = btn.dataset.lang;
          if (newLang === this.getLang()) return;
          this.setLang(newLang);
          this.syncToggles();
          if (typeof onChangeCb === 'function') onChangeCb(newLang);
        });
      });
    },
  };

  window.OttoI18n = OttoI18n;
})();
