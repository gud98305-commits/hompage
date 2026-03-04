from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.data_store import find_product
from backend.services.mailer import send_payment_receipt
from backend.services.stripe_checkout import create_payment_intent

router = APIRouter(prefix='/api/checkout', tags=['checkout'])

_PURCHASES_FILE = Path(__file__).resolve().parents[2] / 'backend' / 'data' / 'purchases.json'

def _append_purchase(record: dict) -> None:
    _PURCHASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    purchases: list = []
    if _PURCHASES_FILE.exists():
        try:
            purchases = json.loads(_PURCHASES_FILE.read_text(encoding='utf-8'))
        except Exception:
            purchases = []
    purchases.append(record)
    _PURCHASES_FILE.write_text(
        json.dumps(purchases, ensure_ascii=False, indent=2), encoding='utf-8'
    )


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


@router.post('/complete')
def complete_payment(payload: CompleteRequest) -> dict:
    product = find_product(payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail='product not found')

    sent = False
    if payload.status == 'succeeded' and payload.email:
        try:
            sent = send_payment_receipt(payload.email, product['name'], int(product['price_jpy']))
        except Exception:
            sent = False

    if payload.status == 'succeeded':
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
        'ok': True,
        'payment_intent_id': payload.payment_intent_id,
        'email_sent': sent,
        'product_name': product['name'],
        'amount_jpy': int(product['price_jpy']),
        'mall': product.get('mall', ''),
    }


@router.post('/complete/', include_in_schema=False)
def complete_payment_slash(payload: CompleteRequest) -> dict:
    return complete_payment(payload)
