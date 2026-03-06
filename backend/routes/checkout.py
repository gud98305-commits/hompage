from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import stripe
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from backend.services.data_store import find_product
from backend.services.mailer import send_payment_receipt
from backend.services.stripe_checkout import create_payment_intent

router = APIRouter(prefix='/api/checkout', tags=['checkout'])

_PURCHASES_FILE = Path(__file__).resolve().parents[2] / 'backend' / 'data' / 'purchases.json'
_purchases_lock = threading.Lock()


def _append_purchase(record: dict) -> None:
    try:
        _PURCHASES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _purchases_lock:
            purchases: list = []
            if _PURCHASES_FILE.exists():
                try:
                    purchases = json.loads(_PURCHASES_FILE.read_text(encoding='utf-8'))
                except Exception as e:
                    logger.warning("purchases file read failed: %s", e)
                    purchases = []
            purchases.append(record)
            _PURCHASES_FILE.write_text(
                json.dumps(purchases, ensure_ascii=False, indent=2), encoding='utf-8'
            )
    except Exception as e:
        logger.error("purchases file write failed — record lost: %s | record: %s", e, record)


class IntentRequest(BaseModel):
    product_id: str
    email: str | None = None


class CompleteRequest(BaseModel):
    product_id: str
    payment_intent_id: str
    status: str
    email: str | None = None


@router.post('/intent')
def payment_intent(payload: IntentRequest) -> dict:
    product = find_product(payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail='product not found')

    return create_payment_intent(
        name=product['name'],
        amount_jpy=int(product['price_jpy']),
        product_id=product['id'],
        email=payload.email,
    )


@router.post('/intent/', include_in_schema=False)
def payment_intent_slash(payload: IntentRequest) -> dict:
    return payment_intent(payload)


def _verify_payment_status(payment_intent_id: str) -> str:
    """Stripe 서버에서 PaymentIntent 실제 상태를 조회. 키 없으면 demo 모드."""
    secret = os.getenv('STRIPE_SECRET_KEY', '').strip()
    if not secret:
        return 'demo_succeeded'
    try:
        stripe.api_key = secret
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        return intent.status
    except Exception as e:
        logger.error("Stripe PaymentIntent 조회 실패: %s", e)
        return 'unknown'


@router.post('/complete')
def complete_payment(payload: CompleteRequest) -> dict:
    product = find_product(payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail='product not found')

    # 클라이언트 status를 신뢰하지 않고 Stripe 서버에서 실제 상태 확인
    verified_status = _verify_payment_status(payload.payment_intent_id)
    is_succeeded = verified_status in ('succeeded', 'demo_succeeded')

    sent = False
    if is_succeeded and payload.email:
        try:
            sent = send_payment_receipt(payload.email, product['name'], int(product['price_jpy']))
        except Exception as e:
            logger.error("payment receipt email failed (to: %s): %s", payload.email, e)
            sent = False

    if is_succeeded:
        _append_purchase({
            'payment_intent_id': payload.payment_intent_id,
            'product_id': payload.product_id,
            'product_name': product['name'],
            'amount_jpy': int(product['price_jpy']),
            'mall': product.get('mall', ''),
            'email': payload.email or '',
            'date': datetime.now(timezone.utc).isoformat(),
        })

    return {
        'ok': is_succeeded,
        'payment_intent_id': payload.payment_intent_id,
        'email_sent': sent,
        'product_name': product['name'],
        'amount_jpy': int(product['price_jpy']),
        'mall': product.get('mall', ''),
    }


@router.post('/complete/', include_in_schema=False)
def complete_payment_slash(payload: CompleteRequest) -> dict:
    return complete_payment(payload)
