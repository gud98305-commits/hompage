from __future__ import annotations
from typing import Annotated
from pydantic import BaseModel, ConfigDict, AwareDatetime, Field, StringConstraints

PlayerName = Annotated[str, StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=50,
    pattern=r"^[a-zA-Z0-9_가-힣 ]+$"
)]
ItemName = Annotated[str, StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=50
)]
EventId = Annotated[str, StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=100
)]
Coordinate = Annotated[int, Field(ge=0, le=5000)]
Gold = Annotated[int, Field(ge=0, le=9999999)]

class GameStateCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True
    )
    player_name: PlayerName
    player_x: Coordinate
    player_y: Coordinate
    gold: Gold = 0
    inventory: list[ItemName] = Field(default_factory=list, max_length=50)
    clothes: list[ItemName] = Field(default_factory=list, max_length=50)
    discovered_events: list[EventId] = Field(default_factory=list, max_length=200)

class GameStateResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True
    )
    id: int
    player_name: PlayerName
    player_x: Coordinate
    player_y: Coordinate
    gold: Gold
    inventory: list[ItemName]
    clothes: list[ItemName]
    discovered_events: list[EventId]
    saved_at: AwareDatetime

class GameStateUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True
    )
    player_x: Coordinate | None = None
    player_y: Coordinate | None = None
    gold: Gold | None = None
    inventory: list[ItemName] | None = Field(default=None, max_length=50)
    clothes: list[ItemName] | None = Field(default=None, max_length=50)
    discovered_events: list[EventId] | None = Field(default=None, max_length=200)

class TradeRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True
    )
    item_name: ItemName
    price: Gold
