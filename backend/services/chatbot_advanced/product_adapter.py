"""
OttO봇 상품 어댑터 모듈.

SEOULFIT ai_curator / data_store와 챗봇 서비스 계층을 연결합니다.
DIP(Dependency Inversion Principle) 기반 ProductRepository Protocol을 정의하고,
SEOULFITProductRepository가 구현체를 제공합니다.

구성:
① import 경로 방어 (try-except ImportError)
② CacheManager (TTL 기반 캐시 무효화 래퍼)
③ ProductRepository Protocol (DIP 인터페이스)
④ SEOULFITProductRepository (구현체)
⑤ get_repo() 팩토리
⑥ 외부 진입점 함수 (chat_service에서 호출)
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Protocol

from backend.services.chatbot_advanced.chat_schemas import CuratorRequest, ProductItem
from backend.services.chatbot_advanced.chat_service import RAGEngineError


# ===========================================================================
# ① 실제 backend 서비스 연결 (stub → 실제 구현체 브리지)
# ===========================================================================

from backend.services.data_store import load_products as _real_load_products
from backend.services.ai_curator import curate_with_openai as _real_curate


def get_products() -> list[dict]:
    """CacheManager.get_products()가 asyncio.to_thread로 호출하는 동기 함수.

    실제 backend.services.data_store.load_products()를 래핑합니다.
    """
    return _real_load_products()


def curate_with_openai(
    body_type=None,
    color=None,
    style=None,
    keyword=None,
    category=None,
    price_min=None,
    price_max=None,
) -> list[dict]:
    """keyword-arg 호출 방식 → 실제 (products, req_dict) 방식 변환 브리지.

    product_adapter의 SEOULFITProductRepository.find_by_curator()는
    curate_with_openai(body_type=..., color=..., ...) 형태로 호출합니다.
    실제 backend.services.ai_curator.curate_with_openai는
    (products, req) 시그니처를 사용하므로 여기서 변환합니다.

    반환값: list[dict] (실제 함수의 {"items": [...], "total": int}에서 items 추출)
    """
    products = _real_load_products()
    req = {
        "body_type":     body_type or "standard",
        "color":         color or "",
        "style":         style or "",
        "keyword":       keyword or "",
        "category":      category or "all",
        "min_price_krw": price_min or 0,
        "max_price_krw": price_max or 99999999,
    }
    result = _real_curate(products, req, page=0, page_size=50)
    return result.get("items", [])


# ===========================================================================
# ② CacheManager (TTL 기반 캐시 무효화 래퍼)
# ===========================================================================

class CacheManager:
    """data_store.py 수정 없이 챗봇 레이어에서 캐시 갱신 전략을 적용합니다.

    동작 방식:
    - TTL(기본 5분 = 300초) 경과 시 data_store 재로딩 자동 트리거
    - invalidate() 호출 시 즉시 강제 무효화
    - get_products()가 동기 함수일 수 있으므로 asyncio.to_thread로 호출

    TODO 8단계: 관리자용 캐시 리셋 엔드포인트 추가
    DELETE /api/chat/admin/cache → cache_manager.invalidate() 호출
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._last_loaded: float = 0.0
        self._ttl: int = ttl_seconds
        self._cache: list[dict] = []

    def is_expired(self) -> bool:
        """TTL 만료 여부를 확인합니다."""
        return (time.time() - self._last_loaded) > self._ttl

    def invalidate(self) -> None:
        """강제 캐시 무효화.

        관리자 API 또는 테스트에서 호출합니다.
        TODO 8단계: DELETE /api/chat/admin/cache 엔드포인트에서 호출
        """
        self._last_loaded = 0.0
        self._cache = []

    async def get_products(self) -> list[dict]:
        """TTL 만료 시 data_store 재로딩. 유효하면 캐시를 반환합니다.

        data_store.get_products()가 동기 함수일 수 있으므로
        asyncio.to_thread로 이벤트 루프 차단을 방지합니다.
        """
        if self.is_expired():
            # data_store.get_products()는 동기 함수 가능성 있음
            # asyncio.to_thread로 별도 스레드에서 실행하여
            # 이벤트 루프 차단 방지
            self._cache = await asyncio.to_thread(get_products)
            self._last_loaded = time.time()
        return self._cache


# 모듈 레벨 캐시 매니저 인스턴스
_cache_manager = CacheManager(ttl_seconds=300)


# ===========================================================================
# ③ ProductRepository Protocol (DIP 인터페이스)
# ===========================================================================

class ProductRepository(Protocol):
    """상품 저장소 프로토콜.

    DIP(Dependency Inversion Principle) 적용으로
    테스트 시 MockProductRepository 교체가 가능합니다.
    """

    async def find_by_curator(
        self, request: CuratorRequest,
    ) -> list[ProductItem]:
        """ai_curator 기반 상품 추천 검색."""
        ...

    async def find_by_id(
        self, item_id: str,
    ) -> ProductItem | None:
        """단일 상품 ID 조회."""
        ...

    async def search_simple(
        self,
        keyword: str,
        category: str | None,
        limit: int,
    ) -> list[ProductItem]:
        """키워드 텍스트 매칭 경량 검색."""
        ...


# ===========================================================================
# ④ SEOULFITProductRepository (구현체)
# ===========================================================================

def _dict_to_product_item(item: dict, reason: str = "", score: float | None = None) -> ProductItem:
    """dict → ProductItem 변환 헬퍼.

    products_enriched.json 필드 매핑을 한 곳에서 관리합니다.
    """
    return ProductItem(
        item_id=item.get("id", ""),
        name=item.get("name", ""),
        brand=item.get("brand", ""),
        category=item.get("category", ""),
        colors=item.get("colors", []),
        price_jpy=item.get("price_jpy", 0),
        price_krw=item.get("price_krw", 0),
        image_url=item.get("main_image"),
        source_url=item.get("source_url"),
        reason=reason,
        score=score,
        mall=item.get("mall", ""),
    )


class SEOULFITProductRepository:
    """SEOULFIT 데이터 기반 상품 저장소 구현체.

    ai_curator(추천 스코어링)와 data_store(인메모리 캐시)를 활용합니다.
    """

    async def find_by_curator(
        self, request: CuratorRequest,
    ) -> list[ProductItem]:
        """ai_curator 기반 상품 추천 검색.

        ai_curator의 4단계 스코어링 엔진을 호출하여
        사용자 조건에 맞는 상품을 추천합니다.
        """
        # 1. ai_curator 호출 (동기/비동기 혼재 방어)
        # ai_curator.curate_with_openai가 동기 def인 경우
        # 이벤트 루프 차단 방지를 위해 asyncio.to_thread로
        # 별도 스레드에서 실행합니다.
        try:
            raw_result = await asyncio.to_thread(
                curate_with_openai,
                body_type=request.body_type,
                color=request.color,
                style=request.style,
                keyword=request.keyword,
                category=request.category,
                price_min=request.price_min,
                price_max=request.price_max,
            )
            # TODO: curate_with_openai가 async def인 경우
            # asyncio.to_thread 제거 후 직접 await으로 교체
        except asyncio.TimeoutError:
            raise RAGEngineError(
                "AI 추천 엔진 응답 타임아웃",
                code="timeout",
            )
        except Exception as e:
            raise RAGEngineError(
                "AI 추천 엔진 호출 실패",
                code="unknown",
                cause=e,
            )

        # 2. raw_result → ProductItem 리스트 변환
        # 실제 curate_with_openai는 ai_reason, ai_score 필드를 반환
        try:
            all_products: list[ProductItem] = [
                _dict_to_product_item(
                    item,
                    reason=str(item.get("ai_reason") or item.get("reason") or ""),
                    score=item.get("ai_score", item.get("score")),
                )
                for item in (raw_result or [])
            ]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise RAGEngineError(
                "추천 결과 파싱 실패",
                code="parse",
                cause=e,
            )

        # 3. 결과 0건 체크
        if not all_products:
            raise RAGEngineError(
                "추천 결과가 없습니다. 검색 조건을 변경해주세요.",
                code="no_result",
            )
            # TODO 4단계: code="no_result" 시
            # GPT query refinement → search_simple 재검색

        # 4. 페이지네이션 슬라이싱
        # ai_curator 자체 페이지네이션 미지원 대비 메모리 슬라이싱
        offset = (request.page - 1) * request.page_size
        results = all_products[offset : offset + request.page_size]
        # TODO: ai_curator 페이지네이션 지원 확인 시 슬라이싱 제거

        # TODO 4단계: Corrective RAG 레이어
        # score 임계값(예: 3.0) 미달 시 GPT 관련성 평가 → query refinement

        return results

    async def find_by_id(
        self, item_id: str,
    ) -> ProductItem | None:
        """단일 상품 조회. TTL 캐시를 경유합니다."""
        products = await _cache_manager.get_products()
        matched = [p for p in products if p.get("id") == item_id]
        if not matched:
            return None
        return _dict_to_product_item(matched[0])

    async def search_simple(
        self,
        keyword: str,
        category: str | None,
        limit: int,
    ) -> list[ProductItem]:
        """키워드 텍스트 매칭 경량 검색. TTL 캐시를 경유합니다.

        TODO 4단계: Corrective RAG 1차 검색 및 재검색용으로 사용
        """
        products = await _cache_manager.get_products()
        keyword_lower = keyword.lower()
        results = [
            p for p in products
            if keyword_lower in p.get("name", "").lower()
            and (category is None or p.get("category") == category)
        ]
        return [
            _dict_to_product_item(p)
            for p in results[:limit]
        ]


# ===========================================================================
# ⑤ get_repo() 팩토리
# ===========================================================================

_repo_instance: ProductRepository | None = None


def get_repo() -> ProductRepository:
    """ProductRepository 팩토리.

    런타임: SEOULFITProductRepository 반환
    테스트 주입 예시:
      app.dependency_overrides[get_repo] = lambda: MockProductRepository()
    싱글톤 안티패턴 회피: 전역 변수 + 팩토리 함수 패턴 사용
    """
    global _repo_instance
    if _repo_instance is None:
        _repo_instance = SEOULFITProductRepository()
    return _repo_instance


# ===========================================================================
# ⑥ 외부 진입점 함수 (chat_service에서 호출)
# ===========================================================================

async def get_products_by_curator(
    request: CuratorRequest,
    repo: ProductRepository | None = None,
) -> list[ProductItem]:
    """ai_curator 기반 상품 추천 진입점.

    chat_service._handle_recommend에서 호출합니다.
    TODO 4단계: Corrective RAG 스코어 임계값 미달 시 조건부 GPT 호출
    """
    return await (repo or get_repo()).find_by_curator(request)


async def get_product_by_id(
    item_id: str,
    repo: ProductRepository | None = None,
) -> ProductItem | None:
    """단일 상품 조회 진입점."""
    return await (repo or get_repo()).find_by_id(item_id)


async def search_products_simple(
    keyword: str,
    category: str | None = None,
    limit: int = 10,
    repo: ProductRepository | None = None,
) -> list[ProductItem]:
    """키워드 경량 검색 진입점.

    TODO 4단계: Corrective RAG no_result 시 query refinement 재검색용
    """
    return await (repo or get_repo()).search_simple(keyword, category, limit)
