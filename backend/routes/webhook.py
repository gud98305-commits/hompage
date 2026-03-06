from __future__ import annotations

import logging
import os

import stripe
from fastapi import APIRouter, Request, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/stripe', tags=['stripe'])

STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')


@router.post('/webhook')
async def stripe_webhook(request: Request) -> dict:
    payload = await request.body()

    # 웹훅 시크릿 미설정 시 검증 불가 → 거부
    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("STRIPE_WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    sig_header = request.headers.get('stripe-signature', '')
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except ValueError:
        logger.warning("Stripe webhook payload invalid")
        raise HTTPException(status_code=400, detail="Invalid payload")

    # 이벤트 타입별 처리 (필요 시 확장)
    logger.info("Stripe webhook received: %s", event['type'])

    return {'ok': True}
