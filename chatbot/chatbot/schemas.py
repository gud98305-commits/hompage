"""
게임 DB 모델 — 게임팀 교체 필요.

[게임팀 담당자에게]
이 파일을 게임 프로젝트의 실제 DB 모델로 교체하세요.
챗봇이 사용하는 필드: user_id, name, category, color, brand, saved_at

교체 방법:
1. 게임 프로젝트의 schemas.py (또는 models.py)를 이 위치에 복사
2. SavedItemModel 클래스명이 다르면 game_adapter.py:152의 import를 수정
3. 컬럼명이 다르면 game_adapter.py:188~210의 getattr 매핑을 수정
"""

from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime


class Base(DeclarativeBase):
    pass


class SavedItemModel(Base):
    """게임에서 사용자가 담은 옷 아이템 테이블.

    게임팀 확인 필요:
    - __tablename__: 실제 테이블명으로 변경
    - 컬럼명: 실제 DB 스키마에 맞게 변경
    - game_adapter.py가 getattr로 접근하므로 컬럼명 불일치 시에도 동작하나
      정확한 매핑을 위해 확인 필요
    """

    __tablename__ = "saved_items"  # TODO: 게임팀 실제 테이블명 확인

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    item_name = Column(String, nullable=True)
    category = Column(String, nullable=True)
    item_type = Column(String, nullable=True)
    color = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    saved_at = Column(DateTime, default=datetime.utcnow)
