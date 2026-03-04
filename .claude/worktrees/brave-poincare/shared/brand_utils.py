from __future__ import annotations

import re


_OVERSEAS_HINTS = (
    "overseas",
    "global",
    "import",
    "paris",
    "london",
    "new york",
    "tokyo",
    "made in italy",
    "made in france",
    "made in usa",
    "해외브랜드",
)

_KOREAN_HINTS = (
    "korean",
    "korea",
    "seoul",
    "k-brand",
    "국내브랜드",
    "한국",
)


def extract_brand(name: str) -> str:
    """
    상품명에서 브랜드 문자열을 추정.
    예) [BRAND] item name -> BRAND
    """
    text = (name or "").strip()
    if not text:
        return ""

    bracket = re.match(r"^\s*\[([^\]]{1,80})\]", text)
    if bracket:
        return bracket.group(1).strip()

    token = re.split(r"[\s/|]", text, maxsplit=1)[0].strip("[]()")
    return token[:80]


def guess_brand_origin(
    *,
    name: str,
    brand: str = "",
    context_text: str = "",
) -> str:
    """
    브랜드 국가를 휴리스틱으로 추정.
    반환값: korean | overseas | unknown
    """
    b = (brand or "").strip()
    if not b:
        b = extract_brand(name)

    text = f"{name} {b} {context_text}".lower()

    if any(h in text for h in _OVERSEAS_HINTS):
        return "overseas"
    if any(h in text for h in _KOREAN_HINTS):
        return "korean"

    # 브랜드명에 한글이 포함되면 한국 브랜드로 우선 추정
    if re.search(r"[가-힣]", b):
        return "korean"

    # 이름에 한글이 충분히 포함되고 해외 힌트가 없으면 한국 우선
    if len(re.findall(r"[가-힣]", name or "")) >= 2:
        return "korean"

    return "unknown"
