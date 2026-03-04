"""
채찍피티 Corrective RAG 엔진 모듈.

상품 추천 결과의 품질을 GPT-4o-mini로 평가하고,
임계값 미달 시 query refinement → 재검색으로 결과를 개선합니다.

구성:
① 상수 정의 (RELEVANCE_THRESHOLD, TOP_N_EVAL_COUNT, MAX_REFINEMENT_ATTEMPTS)
② CorrectiveRAGEngine 클래스
  - _is_below_threshold : 상위 N개 score 기준 GPT 트리거 판단
  - _strip_markdown     : GPT JSON 응답 마크다운 제거 전처리
  - _evaluate_with_gpt  : GPT 관련성 평가 → 저품질 상품 필터링
  - _refine_query       : GPT query refinement (keyword, category 재조정)
  - run                 : Corrective RAG 메인 파이프라인 (6-Step)
③ get_rag_engine() 팩토리
"""

from __future__ import annotations

import json
import os

from openai import AsyncOpenAI

from chat_schemas import CuratorRequest, ProductItem
from chat_service import RAGEngineError


# ===========================================================================
# ① 상수 정의
# ===========================================================================

RELEVANCE_THRESHOLD: float = 3.0
# score가 이 값 미만이면 품질 미달로 판단
# TODO: 운영 데이터 기반으로 임계값 튜닝 필요

TOP_N_EVAL_COUNT: int = 3
# 전체 비율이 아닌 상위 N개 품질만 평가
# 사용자에게 실제로 노출될 상위 상품 기준으로 GPT 트리거 결정
# 예: 상위 3개 모두 score >= 3.0이면 하위 품질 무관하게 GPT 생략

MAX_REFINEMENT_ATTEMPTS: int = 2
# query refinement 최대 재시도 횟수 (무한 루프 방지)


# ===========================================================================
# ② CorrectiveRAGEngine
# ===========================================================================

class CorrectiveRAGEngine:
    """Corrective RAG 엔진.

    상품 추천 결과의 품질을 GPT로 평가하고,
    임계값 미달 시 query refinement → 재검색을 수행합니다.

    GPT 비활성 시 score 정렬만 수행하여 서비스 연속성을 보장합니다.
    """

    def __init__(self) -> None:
        """초기화 시 OPENAI_API_KEY 즉시 검증.

        키 없으면 gpt_enabled=False → score 정렬만 수행.

        [운영 가이드]
        gpt_enabled=False 상태는 서버 재시작 전까지 복구되지 않습니다.
        환경변수 설정 후 반드시 서버를 재시작하세요.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print(
                "[CorrectiveRAGEngine] WARNING: OPENAI_API_KEY 미설정.\n"
                "GPT 관련성 평가 비활성화. score 정렬만 수행합니다.\n"
                "GPT 기능 활성화는 환경변수 설정 후 서버 재시작 필요."
            )
            self.gpt_enabled: bool = False
            self._client: AsyncOpenAI | None = None
        else:
            self.gpt_enabled = True
            self._client = AsyncOpenAI(api_key=api_key)

    # -------------------------------------------------------------------
    # _is_below_threshold
    # -------------------------------------------------------------------

    def _is_below_threshold(self, products: list[ProductItem]) -> bool:
        """상위 TOP_N_EVAL_COUNT개의 score 기준으로 GPT 트리거 결정.

        [상위 N개 기준으로 변경한 이유]
        전체 비율 방식의 문제:
        - 상위 3개가 완벽(score 8.0)해도 하위 7개 때문에 GPT 호출 발생
        - 실제 사용자에게 노출되지 않는 상품까지 평가하는 비용 낭비

        변경된 방식:
        - 상위 TOP_N_EVAL_COUNT개 중 하나라도 score < THRESHOLD이면 True
        - score=None은 임계값 미달로 간주
        """
        top_n = products[:TOP_N_EVAL_COUNT]
        return any(
            (p.score is None or p.score < RELEVANCE_THRESHOLD)
            for p in top_n
        )

    # -------------------------------------------------------------------
    # _strip_markdown
    # -------------------------------------------------------------------

    def _strip_markdown(self, text: str) -> str:
        """GPT JSON 응답에서 마크다운 코드 블록 제거.

        [이 함수가 필요한 이유]
        GPT는 "다른 설명 금지" 지시에도 마크다운 포맷팅을 추가하는 경향이 있음.
        예: ```json\\n["id1"]\\n``` → ["id1"]
        json.loads 전 반드시 이 함수로 전처리 필요.
        """
        text = text.strip()
        # ```json ... ``` 또는 ``` ... ``` 패턴 제거
        if text.startswith("```"):
            lines = text.split("\n")
            # 첫 줄(```json 또는 ```) 제거
            lines = lines[1:] if len(lines) > 1 else lines
            # 마지막 줄(```) 제거
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    # -------------------------------------------------------------------
    # _evaluate_with_gpt
    # -------------------------------------------------------------------

    async def _evaluate_with_gpt(
        self,
        products: list[ProductItem],
        request: CuratorRequest,
    ) -> list[ProductItem]:
        """GPT가 상품 목록의 쿼리 관련성을 평가하여 저품질 상품 필터링.

        [공집합 역설 방지]
        필터링 후 0건이면 원본 반환하지 않고 에러 raise.
        이유: "관련 없는 상품 10개"를 다시 보여주는 것보다
        "적절한 상품을 찾지 못했다"고 명확히 알리는 것이 UX상 낫다.
        호출부(run())에서 filtered_empty를 잡아 재검색 또는 거절 처리.
        """
        if self._client is None:
            return products

        # 상위 10개만 전달 (토큰 비용 통제)
        eval_items = [
            {
                "item_id": p.item_id,
                "name": p.name,
                "category": p.category,
                "colors": p.colors,
            }
            for p in products[:10]
        ]

        system_msg = (
            "당신은 패션 추천 품질 평가자입니다.\n"
            "사용자 조건과 상품 목록을 비교하여\n"
            "관련성 없는 상품의 item_id 목록만 JSON 배열로 반환하세요.\n"
            '형식: ["id1", "id2"]\n'
            "관련 없는 상품이 없으면 빈 배열 []을 반환하세요.\n"
            "마크다운 코드 블록 없이 순수 JSON만 반환하세요."
        )

        user_msg = (
            "사용자 조건:\n"
            f"- 체형: {request.body_type or '미제공'}\n"
            f"- 색상: {request.color or '미제공'}\n"
            f"- 스타일: {request.style or '미제공'}\n"
            f"- 카테고리: {request.category or '미제공'}\n"
            f"- 키워드: {request.keyword or '미제공'}\n\n"
            "상품 목록 (상위 10개, 토큰 비용 통제):\n"
            f"{json.dumps(eval_items, ensure_ascii=False)}"
        )

        try:
            response = await self._client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=500,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
            )
        except Exception as e:
            raise RAGEngineError(
                "GPT 관련성 평가 호출 실패",
                detail=str(e),
                code="gpt_eval_failed",
                cause=e,
            ) from e

        # 응답 파싱 — _strip_markdown 전처리 필수
        raw = (response.choices[0].message.content or "").strip()
        cleaned = self._strip_markdown(raw)

        try:
            excluded_ids: list[str] = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError) as e:
            raise RAGEngineError(
                "GPT 평가 응답 파싱 실패",
                detail=f"raw='{raw}'",
                code="gpt_eval_failed",
                cause=e,
            ) from e

        excluded_set = set(excluded_ids)
        filtered = [p for p in products if p.item_id not in excluded_set]

        # [공집합 역설 방지]
        # 필터링 후 0건이면 원본 반환하지 않고 에러 raise.
        # 이유: "관련 없는 상품 10개"를 다시 보여주는 것보다
        # "적절한 상품을 찾지 못했다"고 명확히 알리는 것이 UX상 낫다.
        # 호출부(run())에서 filtered_empty를 잡아 재검색 또는 거절 처리.
        if not filtered:
            # 운영 모니터링: 빈번 발생 시 RELEVANCE_THRESHOLD 튜닝 신호
            from logger import get_logger
            get_logger().rag_filtered_empty(
                module="CorrectiveRAGEngine",
                original_count=len(products),
            )
            raise RAGEngineError(
                "GPT 필터링 결과 0건",
                code="filtered_empty",
            )

        return filtered

    # -------------------------------------------------------------------
    # _refine_query
    # -------------------------------------------------------------------

    async def _refine_query(
        self,
        request: CuratorRequest,
        attempt: int,
    ) -> CuratorRequest:
        """검색 결과 품질 미달 시 GPT가 keyword, category 재조정."""
        if self._client is None:
            return request

        system_msg = (
            "당신은 패션 검색 쿼리 최적화 전문가입니다.\n"
            "keyword와 category만 수정하여 JSON으로 반환하세요.\n"
            '형식: {"keyword": "...", "category": "..."}\n'
            "category는 top/bottom/outer/dress/shoes/accessory 중 하나 또는 null.\n"
            "마크다운 코드 블록 없이 순수 JSON만 반환하세요."
        )

        user_msg = (
            "현재 검색 조건:\n"
            f"- keyword : {request.keyword}\n"
            f"- category: {request.category}\n"
            f"- 체형    : {request.body_type}\n"
            f"- 시도    : {attempt}번째 refinement"
        )

        try:
            response = await self._client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=200,
                temperature=0.3,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
            )
        except Exception as e:
            raise RAGEngineError(
                "query refinement GPT 호출 실패",
                detail=str(e),
                code="refinement_failed",
                cause=e,
            ) from e

        # _strip_markdown 전처리 후 json.loads
        raw = (response.choices[0].message.content or "").strip()
        cleaned = self._strip_markdown(raw)

        try:
            refined: dict = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            # 파싱 실패 시 원본 request 반환
            return request

        # keyword, category만 교체한 새 CuratorRequest 생성
        return request.model_copy(
            update={
                "keyword": refined.get("keyword", request.keyword),
                "category": refined.get("category", request.category),
            },
        )

    # -------------------------------------------------------------------
    # run — Corrective RAG 메인 파이프라인
    # -------------------------------------------------------------------

    async def run(
        self,
        products: list[ProductItem],
        request: CuratorRequest,
        repo: object | None = None,
    ) -> list[ProductItem]:
        """Corrective RAG 메인 함수.

        6-Step 파이프라인:
        1. 결과 없음 즉시 처리
        2. GPT 비활성 → score 정렬만
        3. 상위 N개 임계값 평가
        4. GPT 관련성 평가 → 저품질 필터링
        5. 필터링 후에도 미달 → query refinement + 재검색
        6. 최종 결과 반환

        repo 파라미터는 product_adapter.ProductRepository 구현체.
        순환 import 방지를 위해 타입 힌트를 object로 선언하고
        런타임에서 product_adapter를 lazy import합니다.
        """
        # Step 1. 결과 없음 즉시 처리
        if not products:
            raise RAGEngineError("검색 결과 없음", code="no_result")

        # Step 2. GPT 비활성 상태면 score 정렬만 수행
        if not self.gpt_enabled:
            return sorted(
                products, key=lambda p: p.score or 0.0, reverse=True,
            )

        # Step 3. 상위 N개 score 기준 임계값 평가
        # 전체 비율이 아닌 상위 TOP_N_EVAL_COUNT개 품질만 확인
        # 상위 상품이 충분히 좋으면 GPT 호출 없이 반환 (비용 절약)
        if not self._is_below_threshold(products):
            return products

        # filtered 초기값: None (필터링 미실행 상태)
        # None: 필터링 미실행 상태
        # []: 필터링 실행됨, 결과 없음 (빈 리스트)
        # [items]: 필터링 실행됨, 결과 있음
        filtered = None

        # Step 4. GPT 관련성 평가 → 저품질 상품 필터링
        try:
            filtered = await self._evaluate_with_gpt(products, request)
        except RAGEngineError as e:
            if e.code == "filtered_empty":
                filtered = []  # 명시적 빈 리스트 (원본 재사용 금지)
            else:
                # 기타 GPT 평가 실패 시 원본 반환
                return products
        except Exception:
            return products

        # Step 5. query refinement (filtered가 None이 아닌 빈 리스트일 때)
        # [중복 결과 감지 로직 이유]
        # GPT refinement가 동일한 keyword/category를 반환하면
        # 재검색 결과도 동일 → 무의미한 반복 방지를 위해
        # item_id 집합을 비교하여 중복 시 즉시 중단
        prev_ids = {p.item_id for p in (filtered or [])}

        if filtered is not None and self._is_below_threshold(
            filtered or products,
        ):
            for attempt in range(1, MAX_REFINEMENT_ATTEMPTS + 1):
                try:
                    refined_request = await self._refine_query(
                        request, attempt,
                    )

                    # 순환 import 방지: 런타임 lazy import
                    from product_adapter import search_products_simple

                    new_products = await search_products_simple(
                        keyword=refined_request.keyword or "",
                        category=refined_request.category,
                        limit=request.page_size,
                        repo=repo,
                    )

                    # 중복 결과 감지: 이전 결과와 동일하면 refinement 효과 없음
                    new_ids = {p.item_id for p in new_products}
                    if new_ids == prev_ids:
                        break  # 동일 결과 반복 → 즉시 중단

                    if new_products:
                        filtered = new_products
                        prev_ids = new_ids  # 다음 비교용 갱신
                        break

                except Exception:
                    break

        # Step 6. 최종 반환
        # filtered가 None이면 필터링 미실행 → 원본 반환
        # filtered가 []이면 필터링 실행됐으나 결과 없음 → 원본 재사용 금지
        # filtered가 [items]이면 필터링 결과 반환
        if filtered is None:
            return products
        elif not filtered:
            raise RAGEngineError(
                "필터링 후 결과 없음",
                code="filtered_empty",
            )
        else:
            return filtered


# ===========================================================================
# ③ get_rag_engine() 팩토리
# ===========================================================================

_rag_engine_instance: CorrectiveRAGEngine | None = None


def get_rag_engine() -> CorrectiveRAGEngine:
    """CorrectiveRAGEngine 팩토리.

    런타임: CorrectiveRAGEngine 싱글턴 반환
    테스트 주입 예시:
      app.dependency_overrides[get_rag_engine] = lambda: MockRAGEngine()
    """
    global _rag_engine_instance
    if _rag_engine_instance is None:
        _rag_engine_instance = CorrectiveRAGEngine()
    return _rag_engine_instance
