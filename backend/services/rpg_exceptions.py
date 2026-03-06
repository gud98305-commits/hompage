# 커스텀 예외 모듈 (RPG Game Exceptions)
# 게임 비즈니스 로직 전용 예외 — HTTPException으로 변환하여 일관된 에러 응답 제공


class RpgGameError(Exception):
    """RPG 게임 로직 기본 예외"""

    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class GameNotFoundError(RpgGameError):
    """저장 데이터 미발견"""

    def __init__(self, save_id: int):
        super().__init__(
            detail=f"저장 데이터 없음 (ID: {save_id})",
            status_code=404,
        )


class InsufficientFundsError(RpgGameError):
    """재화 부족"""

    def __init__(self, required: int, current: int):
        super().__init__(
            detail=f"재화 부족: 필요 {required}, 보유 {current}",
            status_code=400,
        )


class ItemNotFoundError(RpgGameError):
    """인벤토리에 아이템 없음"""

    def __init__(self, item_name: str):
        super().__init__(
            detail=f"아이템 없음: {item_name}",
            status_code=400,
        )


class GoldOverflowError(RpgGameError):
    """골드 상한 초과"""

    def __init__(self, max_gold: int):
        super().__init__(
            detail=f"골드 상한 초과: 최대 {max_gold}",
            status_code=400,
        )
