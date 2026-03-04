"""
상품 데이터 스토어 — 홈페이지팀 교체 필요.

[홈페이지팀 담당자에게]
get_products() 함수를 실제 상품 데이터 로딩으로 교체하세요.
함수 시그니처(반환 타입 list[dict])를 변경하지 마세요.

반환 dict 필수 필드:
{
    "id": str,           # 상품 고유 ID
    "name": str,         # 상품명
    "brand": str,        # 브랜드명
    "category": str,     # top/bottom/outer/dress/shoes/accessory
    "colors": list[str], # 색상 목록
    "price_jpy": int,    # 엔화 가격
    "price_krw": int,    # 원화 가격
    "main_image": str | None,   # 상품 이미지 URL
    "source_url": str | None,   # 상품 상세 페이지 URL
    "mall": str,                # 쇼핑몰명
}

교체 방법:
1. products_enriched.json 로딩 또는 DB 조회로 교체
2. 반환 형식(list[dict])만 유지하면 product_adapter.py가 자동 연동
"""


def get_products() -> list[dict]:
    """상품 목록 반환.

    product_adapter.py의 CacheManager가 호출합니다 (동기 함수 유지).
    TODO: 실제 상품 데이터 소스로 교체
    """
    return []
