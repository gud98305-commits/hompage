"""
DeepL API 기반 한→일 번역 서비스.

환경변수:
  DEEPL_API_KEY: DeepL API 인증 키 (.env에 설정)
                 무료 키는 접미사 ":fx" 가 붙습니다.
                 (예: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:fx)

DeepL 키가 없으면 원본 텍스트 그대로 반환 (graceful fallback).

Note: DEEPL_API_KEY는 함수 호출 시점에 읽음 (lazy load).
      app.py에서 load_dotenv()가 import 이후에 실행되므로
      모듈 로드 시점에 os.getenv()를 호출하면 빈 값이 됩니다.
"""
from __future__ import annotations

import os

import requests

_FREE_URL = "https://api-free.deepl.com/v2/translate"
_PRO_URL  = "https://api.deepl.com/v2/translate"

_LANG_MAP: dict[str, str] = {
    "ko": "KO",
    "ja": "JA",
    "en": "EN-US",
}

# 번역 결과 메모리 캐시 (프로세스 재시작 전까지 유지)
_cache: dict[str, str] = {}


def _api_key() -> str:
    """매 호출 시점에 환경변수를 읽음 (load_dotenv 이후 반영 보장)."""
    return os.getenv("DEEPL_API_KEY", "").strip()


def _deepl_url() -> str:
    return _FREE_URL if _api_key().endswith(":fx") else _PRO_URL


def _to_deepl_lang(lang: str) -> str:
    return _LANG_MAP.get(lang.lower(), lang.upper())


def translate_batch(
    texts: list[str],
    source: str = "ko",
    target: str = "ja",
) -> list[str]:
    """
    DeepL API로 여러 텍스트를 한 번의 배치 요청으로 번역.

    - 캐시 히트: API 호출 없이 즉시 반환
    - 캐시 미스: 미스된 텍스트만 DeepL에 배치 전송
    - 키 없음 / API 오류: 원본 텍스트 그대로 반환 (graceful fallback)
    """
    if not texts:
        return []

    api_key  = _api_key()
    src_lang = _to_deepl_lang(source)
    tgt_lang = _to_deepl_lang(target)

    # ── 캐시 미스 목록 추출 ─────────────────────────────────────────────
    miss_indices: list[int] = []
    miss_texts:   list[str] = []

    for i, text in enumerate(texts):
        if not text or not text.strip():
            continue
        cache_key = f"{source}:{target}:{text}"
        if cache_key not in _cache:
            miss_indices.append(i)
            miss_texts.append(text)

    # ── 캐시 미스가 있고 API 키가 있으면 DeepL 배치 요청 ───────────────
    if miss_texts and api_key:
        try:
            resp = requests.post(
                _deepl_url(),
                headers={
                    "Authorization": f"DeepL-Auth-Key {api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "text":        miss_texts,   # 배열로 한 번에 전송
                    "source_lang": src_lang,
                    "target_lang": tgt_lang,
                },
                timeout=15,
            )
            resp.raise_for_status()
            translations = resp.json().get("translations", [])
            for idx, orig_i in enumerate(miss_indices):
                orig_text  = texts[orig_i]
                translated = (
                    translations[idx].get("text", orig_text)
                    if idx < len(translations)
                    else orig_text
                )
                _cache[f"{source}:{target}:{orig_text}"] = translated
        except Exception:
            pass  # 실패 시 아래에서 원본 fallback

    # ── 최종 결과 조립 (캐시 또는 원본 fallback) ────────────────────────
    results: list[str] = []
    for text in texts:
        if not text or not text.strip():
            results.append(text)
            continue
        results.append(_cache.get(f"{source}:{target}:{text}", text))
    return results
