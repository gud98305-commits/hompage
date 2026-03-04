"""
AI 큐레이터 — 홈페이지팀 교체 필요.

[홈페이지팀 담당자에게]
curate_with_openai() 함수를 실제 AI 큐레이션 엔진으로 교체하세요.
함수 시그니처(파라미터명 + 반환 타입)를 변경하지 마세요.

반환 list[dict] 필수 필드:
{
    "id": str,
    "name": str,
    "brand": str,
    "category": str,
    "colors": list[str],
    "price_jpy": int,
    "price_krw": int,
    "main_image": str | None,
    "source_url": str | None,
    "mall": str,
    "score": float,    # 추천 스코어 (높을수록 관련성 높음)
    "reason": str,     # 추천 이유
}

교체 방법:
1. 실제 ai_curator.py를 이 위치에 복사
2. curate_with_openai 함수명이 같으면 그대로 동작
3. 함수명이 다르면 product_adapter.py:33의 import를 수정
"""


def curate_with_openai(
    body_type: str | None = None,
    color: str | None = None,
    style: str | None = None,
    keyword: str | None = None,
    category: str | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
) -> list[dict]:
    """상품 큐레이션 엔진.

    product_adapter.py가 asyncio.to_thread로 호출합니다 (동기 함수 유지).
    TODO: 실제 AI 스코어링 엔진으로 교체
    """
    return []
