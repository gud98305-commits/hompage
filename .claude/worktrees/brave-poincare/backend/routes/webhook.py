from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/stripe', tags=['stripe'])


@router.post('/webhook')
async def stripe_webhook(request: Request) -> dict:
    # Step 1-5: 기본 엔드포인트만 준비. 실제 검증/메일 발송은 Step 10에서 연결.
    _ = await request.body()
    return {'ok': True}
