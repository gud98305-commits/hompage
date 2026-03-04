# API 통합 테스트 (Test API)

import pytest
from httpx import AsyncClient
from conftest import VALID_SAVE


# ── POST /api/save ──


@pytest.mark.asyncio
async def test_save_create_success(client: AsyncClient):
    res = await client.post("/api/save", json=VALID_SAVE)
    assert res.status_code == 201
    data = res.json()
    assert data["player_name"] == "테스터"
    assert data["gold"] == 500
    assert data["id"] is not None
    assert data["saved_at"] is not None  # UTC aware datetime 반환 확인


@pytest.mark.asyncio
async def test_save_create_validation_error(client: AsyncClient):
    """player_name 누락 시 422"""
    bad = {"player_x": 100, "player_y": 64}
    res = await client.post("/api/save", json=bad)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_save_create_extra_field_rejected(client: AsyncClient):
    """extra='forbid' 설정에 의해 정의되지 않은 필드 거부"""
    bad = {**VALID_SAVE, "hacked_gold": 9999999}
    res = await client.post("/api/save", json=bad)
    assert res.status_code == 422


# ── GET /api/load/{save_id} ──


@pytest.mark.asyncio
async def test_load_success(client: AsyncClient):
    create = await client.post("/api/save", json=VALID_SAVE)
    save_id = create.json()["id"]

    res = await client.get(f"/api/load/{save_id}")
    assert res.status_code == 200
    assert res.json()["player_name"] == "테스터"
    assert res.json()["inventory"] == ["열쇠", "빵"]


@pytest.mark.asyncio
async def test_load_not_found(client: AsyncClient):
    res = await client.get("/api/load/9999")
    assert res.status_code == 404


# ── GET /api/saves ──


@pytest.mark.asyncio
async def test_saves_list(client: AsyncClient):
    await client.post("/api/save", json=VALID_SAVE)
    await client.post("/api/save", json={**VALID_SAVE, "gold": 1000})

    res = await client.get("/api/saves")
    assert res.status_code == 200
    saves = res.json()
    assert len(saves) == 2


@pytest.mark.asyncio
async def test_saves_list_empty(client: AsyncClient):
    res = await client.get("/api/saves")
    assert res.status_code == 200
    assert res.json() == []


# ── DELETE /api/save/{save_id} ──


@pytest.mark.asyncio
async def test_delete_success(client: AsyncClient):
    create = await client.post("/api/save", json=VALID_SAVE)
    save_id = create.json()["id"]

    res = await client.delete(f"/api/save/{save_id}")
    assert res.status_code == 200
    assert res.json()["message"] == "삭제 완료"

    # 삭제 후 조회 시 404
    res2 = await client.get(f"/api/load/{save_id}")
    assert res2.status_code == 404


@pytest.mark.asyncio
async def test_delete_not_found(client: AsyncClient):
    res = await client.delete("/api/save/9999")
    assert res.status_code == 404


# ── PATCH /api/save/{save_id} ──


@pytest.mark.asyncio
async def test_patch_partial_update(client: AsyncClient):
    """골드만 부분 업데이트"""
    create = await client.post("/api/save", json=VALID_SAVE)
    save_id = create.json()["id"]

    res = await client.patch(f"/api/save/{save_id}", json={"gold": 9999})
    assert res.status_code == 200
    data = res.json()
    assert data["gold"] == 9999
    assert data["player_name"] == "테스터"  # 다른 필드 유지


@pytest.mark.asyncio
async def test_patch_not_found(client: AsyncClient):
    res = await client.patch("/api/save/9999", json={"gold": 100})
    assert res.status_code == 404


# ── GET /api/health ──


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    res = await client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"


# ── POST /api/trade/buy ──


@pytest.mark.asyncio
async def test_trade_buy_success(client: AsyncClient):
    create = await client.post("/api/save", json=VALID_SAVE)
    save_id = create.json()["id"]

    res = await client.post(
        f"/api/trade/buy/{save_id}",
        json={"item_name": "커피", "price": 100}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["gold"] == 400  # 500 - 100
    assert "커피" in data["inventory"]


@pytest.mark.asyncio
async def test_trade_buy_insufficient_funds(client: AsyncClient):
    create = await client.post("/api/save", json=VALID_SAVE)
    save_id = create.json()["id"]

    res = await client.post(
        f"/api/trade/buy/{save_id}",
        json={"item_name": "다이아몬드", "price": 9999}
    )
    assert res.status_code == 400
    assert "재화 부족" in res.json()["detail"]


# ── POST /api/trade/sell ──


@pytest.mark.asyncio
async def test_trade_sell_success(client: AsyncClient):
    create = await client.post("/api/save", json=VALID_SAVE)
    save_id = create.json()["id"]

    res = await client.post(
        f"/api/trade/sell/{save_id}",
        json={"item_name": "열쇠", "price": 50}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["gold"] == 550  # 500 + 50
    assert "열쇠" not in data["inventory"]


@pytest.mark.asyncio
async def test_trade_sell_item_not_found(client: AsyncClient):
    create = await client.post("/api/save", json=VALID_SAVE)
    save_id = create.json()["id"]

    res = await client.post(
        f"/api/trade/sell/{save_id}",
        json={"item_name": "없는아이템", "price": 50}
    )
    assert res.status_code == 400
    assert "아이템 없음" in res.json()["detail"]


@pytest.mark.asyncio
async def test_trade_save_not_found(client: AsyncClient):
    res = await client.post(
        "/api/trade/buy/9999",
        json={"item_name": "빵", "price": 10}
    )
    assert res.status_code == 404
