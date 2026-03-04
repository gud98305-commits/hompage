from __future__ import annotations

import os

import stripe


def create_payment_intent(*, name: str, amount_jpy: int, product_id: str, email: str | None = None) -> dict:
    secret = os.getenv('STRIPE_SECRET_KEY', '').strip()
    publishable = os.getenv('STRIPE_PUBLISHABLE_KEY', '').strip()

    if not secret or not publishable:
        return {
            'demo_mode': True,
            'product_id': product_id,
            'product_name': name,
            'amount_jpy': int(amount_jpy),
            'publishable_key': None,
            'client_secret': 'demo_client_secret'
        }

    stripe.api_key = secret
    intent = stripe.PaymentIntent.create(
        amount=int(amount_jpy),
        currency=os.getenv('STRIPE_CURRENCY', 'jpy'),
        receipt_email=email,
        metadata={
            'product_id': product_id,
            'product_name': name,
        },
        automatic_payment_methods={'enabled': True},
    )

    return {
        'demo_mode': False,
        'product_id': product_id,
        'product_name': name,
        'amount_jpy': int(amount_jpy),
        'publishable_key': publishable,
        'client_secret': intent.client_secret,
    }
