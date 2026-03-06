"""
OttO봇 게임 어댑터 모듈.

성수 RPG 게임 DB와 챗봇 서비스 계층을 연결합니다.
게임에서 사용자가 담은 옷 아이템을 조회하고,
게임 도메인 용어를 현실 패션 키워드로 변환하여
CuratorRequest를 구성합니다.

구성:
① GameItem (Pydantic V2 모델)
② GameDBError (ChatServiceError 상속)
③ 게임 도메인 → 현실 패션 변환 매핑 테이블
④ GameItemRepository Protocol (DIP)
⑤ SQLiteGameItemRepository (구현체)
⑥ GameItemToProductAdapter (도메인 변환)
⑦ get_game_repo() 팩토리
"""

from __future__ import annotations

from collections import Counter
from typing import Protocol

import asyncio

from pydantic import BaseModel

from backend.services.chatbot_advanced.chat_schemas import CuratorRequest
from backend.services.chatbot_advanced.chat_service import ChatServiceError
from backend.services.turso_db import InventoryItem, _get_connection


# ===========================================================================
# ① GameItem (Pydantic V2 모델)
# ===========================================================================

class GameItem(BaseModel):
    """게임에서 사용자가 담은 옷 아이템.

    chat_schemas.ProductItem과 별도 정의 →
    게임 DB 구조 변경 시 챗봇 스키마 영향 없음.
    """

    item_id: str
    name: str
    category: str  # top/bottom/outer/dress/shoes/accessory
    color: str | None = None
    brand: str | None = None
    saved_at: str | None = None
    # TODO: 게임 DB schemas.py 실제 필드명 확인 후 매핑 수정


# ===========================================================================
# ② GameDBError (ChatServiceError 상속)
# ===========================================================================

class GameDBError(ChatServiceError):
    """게임 DB 연동 예외.

    code 분류:
    - "not_found"    : user_id에 해당하는 저장 데이터 없음
    - "query_failed" : DB 조회 실패
    - "empty"        : 담은 옷 목록이 비어있음
    """

    def __init__(
        self,
        message: str,
        detail: str = "",
        code: str = "not_found",
    ) -> None:
        super().__init__(message, detail)
        self.code = code


# ===========================================================================
# ③ 게임 도메인 → 현실 패션 변환 매핑 테이블
# ===========================================================================

# 게임 아이템명을 현실 쇼핑몰 카테고리/키워드로 변환.
# 게임 특수 용어("갑옷", "로브")가 쇼핑몰 검색에
# 매칭되지 않는 문제를 최소화.
# TODO 7단계: LLM 기반 도메인 변환으로 교체 예정
GAME_TO_FASHION_CATEGORY: dict[str, str] = {
    # 아우터 계열
    "갑옷": "outer", "코트 오브": "outer", "망토": "outer",
    "클oak": "outer", "재킷": "outer", "아머": "outer",
    # 상의 계열
    "로브": "top", "셔츠 오브": "top", "튜닉": "top",
    "블라우스": "top", "저지": "top",
    # 하의 계열
    "레깅스": "bottom", "바지 오브": "bottom", "스커트 오브": "bottom",
    "슬랙스": "bottom",
    # 원피스 계열
    "드레스": "dress", "가운": "dress", "원피스": "dress",
    # 신발 계열
    "부츠": "shoes", "샌들": "shoes", "슬리퍼": "shoes",
}

GAME_TO_FASHION_KEYWORD: dict[str, str] = {
    # 게임 소재/속성 → 패션 키워드 변환
    "전설의": "프리미엄", "마법사의": "포멀",
    "전사의": "캐주얼", "용사의": "스트리트",
    "어둠의": "블랙", "빛의": "화이트",
    "화염의": "레드", "얼음의": "블루",
}


# ===========================================================================
# ④ GameItemRepository Protocol (DIP)
# ===========================================================================

class GameItemRepository(Protocol):
    """게임 아이템 저장소 프로토콜.

    DIP(Dependency Inversion Principle) 적용으로
    테스트 시 MockGameItemRepository 교체가 가능합니다.
    session 파라미터는 하위 호환성을 위해 유지하며, 구현체에서는 무시합니다.
    """

    async def get_saved_items(
        self,
        user_id: str,
        session: object,
        limit: int = 10,
    ) -> list[GameItem]:
        """사용자가 게임에서 담은 옷 목록을 조회합니다."""
        ...


# ===========================================================================
# ⑤ TursoGameItemRepository (구현체)
# ===========================================================================

class TursoGameItemRepository:
    """Turso DB 기반 게임 아이템 저장소 구현체.

    backend.services.turso_db의 InventoryItem과 _get_connection을 사용하여
    실제 Turso DB에서 inventory_items 테이블을 조회합니다.
    session 파라미터는 Protocol 호환성을 위해 받지만 사용하지 않습니다.
    """

    def _fetch_sync(self, user_id_int: int, limit: int) -> list[dict]:
        """Turso DB에서 동기적으로 인벤토리 아이템 조회."""
        conn = _get_connection()
        try:
            items = InventoryItem.get_by_user(conn, user_id_int, limit=limit)
            return [
                {
                    "id":       item.id,
                    "name":     item.name,
                    "category": item.category,
                    "color":    item.colors[0] if item.colors else None,
                    "brand":    item.brand,
                    "saved_at": item.obtained_at,
                }
                for item in items
            ]
        finally:
            conn.close()

    async def get_saved_items(
        self,
        user_id: str,
        session: object,
        limit: int = 10,
    ) -> list[GameItem]:
        """Turso inventory_items에서 user_id의 게임 아이템 목록 조회."""
        try:
            user_id_int = int(user_id)
        except (ValueError, TypeError):
            raise GameDBError(
                f"user_id='{user_id}'는 정수여야 합니다.",
                code="not_found",
            )

        try:
            raw_items = await asyncio.to_thread(
                self._fetch_sync, user_id_int, limit
            )
        except GameDBError:
            raise
        except Exception as e:
            raise GameDBError(
                "Turso inventory_items 조회 실패",
                detail=str(e),
                code="query_failed",
            ) from e

        if not raw_items:
            raise GameDBError(
                f"user_id={user_id}의 게임 아이템이 없습니다.",
                code="not_found",
            )

        return [
            GameItem(
                item_id=str(item["id"]),
                name=item["name"] or "알 수 없는 아이템",
                category=GAME_TO_FASHION_CATEGORY.get(
                    item["category"], item["category"] or "top"
                ),
                color=item["color"],
                brand=item["brand"],
                saved_at=item["saved_at"],
            )
            for item in raw_items
        ]


# ===========================================================================
# ⑥ GameItemToProductAdapter (도메인 변환)
# ===========================================================================

class GameItemToProductAdapter:
    """게임 아이템 → CuratorRequest 변환 어댑터.

    게임 도메인 용어를 현실 패션 키워드로 변환하여
    ai_curator 검색에 적합한 CuratorRequest를 구성합니다.
    """

    @staticmethod
    def to_curator_request(
        items: list[GameItem],
        body_type: str | None = None,
        page_size: int = 5,
    ) -> CuratorRequest:
        """GameItem 목록 → CuratorRequest 변환.

        단순 "첫 번째 아이템" 방식 대신
        모든 아이템의 속성을 keyword에 나열하여 정보 손실 최소화.
        TODO 7단계: LLM 기반 복합 조건 쿼리 생성으로 교체 예정
        """
        # Step 1. 카테고리 빈도 분석 → 가장 많은 카테고리 선택
        category_counts = Counter(
            item.category for item in items if item.category
        )
        top_category = (
            category_counts.most_common(1)[0][0]
            if category_counts else None
        )

        # Step 2. 전체 아이템 패턴 분석
        keyword_parts: list[str] = []
        all_colors: list[str] = []

        for item in items:
            # 게임 용어 → 패션 용어 변환
            fashion_name = item.name
            for game_term, fashion_term in GAME_TO_FASHION_KEYWORD.items():
                if game_term in item.name:
                    fashion_name = fashion_term
                    break
            c = item.color
            if c:
                all_colors.append(c)
                keyword_parts.append(f"{c} {fashion_name}")
            else:
                keyword_parts.append(fashion_name)

        # 상위 5개 아이템으로 키워드 구성 (토큰 비용 통제)
        kw_parts = keyword_parts[:5]
        keyword = " ".join(kw_parts)[:100]

        # Step 3. 가장 많이 등장한 색상 선택
        color: str | None = None
        if all_colors:
            color = Counter(all_colors).most_common(1)[0][0]

        return CuratorRequest(
            body_type=body_type,
            keyword=keyword,
            category=top_category,
            color=color,
            page=1,
            page_size=page_size,
        )


# ===========================================================================
# ⑦ get_game_repo() 팩토리
# ===========================================================================

_game_repo_instance: GameItemRepository | None = None


def get_game_repo() -> GameItemRepository:
    """GameItemRepository 팩토리.

    런타임: TursoGameItemRepository 싱글턴 반환
    테스트 주입 예시:
      app.dependency_overrides[get_game_repo] = lambda: MockGameRepo()
    """
    global _game_repo_instance
    if _game_repo_instance is None:
        _game_repo_instance = TursoGameItemRepository()
    return _game_repo_instance
