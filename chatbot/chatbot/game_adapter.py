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

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chat_schemas import CuratorRequest
from chat_service import ChatServiceError


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
    """

    async def get_saved_items(
        self,
        user_id: str,
        session: AsyncSession,
        limit: int = 10,
    ) -> list[GameItem]:
        """사용자가 게임에서 담은 옷 목록을 조회합니다."""
        ...


# ===========================================================================
# ⑤ SQLiteGameItemRepository (구현체)
# ===========================================================================

class SQLiteGameItemRepository:
    """게임 DB 기반 아이템 저장소 구현체.

    SQLAlchemy 비동기 세션으로 게임 DB를 조회합니다.
    """

    async def get_saved_items(
        self,
        user_id: str,
        session: AsyncSession,
        limit: int = 10,
    ) -> list[GameItem]:
        """게임 DB에서 user_id의 담은 옷 목록 조회."""
        # Step 1. SQLAlchemy 비동기 쿼리 실행
        # TODO: 실제 게임 DB 테이블명/모델명 확인 후 수정
        # 예상: SavedItemModel, 실제 확인 필요
        try:
            # 순환 import 방지 + 게임 DB 모델 lazy import
            # TODO: schemas.py 실제 모델 클래스명 확인 후 수정
            from schemas import SavedItemModel

            result = await session.execute(
                select(SavedItemModel)
                .where(SavedItemModel.user_id == user_id)
                .order_by(SavedItemModel.saved_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
        except ImportError as e:
            raise GameDBError(
                "게임 DB 모델을 찾을 수 없습니다.",
                detail=str(e),
                code="query_failed",
            ) from e
        except Exception as e:
            raise GameDBError(
                "게임 DB 조회 실패",
                detail=str(e),
                code="query_failed",
            ) from e

        # Step 2. 결과 없음 처리
        if not rows:
            raise GameDBError(
                f"user_id={user_id}의 저장된 아이템이 없습니다.",
                code="not_found",
            )

        # Step 3. DB 모델 → GameItem 변환
        # 모든 컬럼 접근에 getattr 방어 적용:
        # 게임 DB는 외부 시스템이므로 컬럼명/구조 변경 가능성 높음.
        # 필수 필드(name, category)도 예외 없이 getattr로 접근하여
        # AttributeError 방어 → 기본값 반환으로 서비스 연속성 보장
        items: list[GameItem] = []
        for row in rows:
            name = (
                getattr(row, "name", None)
                or getattr(row, "item_name", None)
                or "알 수 없는 아이템"
            )
            # TODO: 실제 컬럼명 확인 ("name" vs "item_name")

            raw_cat = (
                getattr(row, "category", None)
                or getattr(row, "item_type", None)
                or ""
            )
            # 게임 카테고리 → 패션 카테고리 변환 시도
            category = GAME_TO_FASHION_CATEGORY.get(raw_cat, raw_cat or "top")
            # TODO: 실제 카테고리 컬럼명 확인 ("category" vs "item_type")

            items.append(GameItem(
                item_id=str(getattr(row, "id", "") or ""),
                name=name,
                category=category,
                color=getattr(row, "color", None),
                brand=getattr(row, "brand", None),
                saved_at=str(getattr(row, "saved_at", "") or ""),
            ))

        return items


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

        # Step 2. 다중 속성 keyword 구성 (정보 손실 최소화)
        # 단순 "첫 번째 아이템 색상"이 아닌
        # 모든 아이템의 이름+색상 조합을 나열하여
        # 검색 엔진이 최대한 다양한 관련 상품을 찾도록 유도
        keyword_parts: list[str] = []
        for item in items[:3]:
            # 게임 용어 → 패션 용어 변환 시도
            fashion_name = item.name
            for game_term, fashion_term in GAME_TO_FASHION_KEYWORD.items():
                if game_term in item.name:
                    fashion_name = fashion_term
                    break
            # 색상 포함하여 구체적 조합 생성
            if item.color:
                keyword_parts.append(f"{item.color} {fashion_name}")
            else:
                keyword_parts.append(fashion_name)

        keyword = " ".join(keyword_parts)[:100]
        # 토큰 비용 통제: 100자 제한

        # Step 3. 첫 번째 아이템 색상 (color 파라미터용)
        color = next(
            (item.color for item in items if item.color), None
        )

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

    런타임: SQLiteGameItemRepository 싱글턴 반환
    테스트 주입 예시:
      app.dependency_overrides[get_game_repo] = lambda: MockGameRepo()
    """
    global _game_repo_instance
    if _game_repo_instance is None:
        _game_repo_instance = SQLiteGameItemRepository()
    return _game_repo_instance
