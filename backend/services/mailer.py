from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def send_payment_receipt(email: str, item_name: str, amount_jpy: int) -> bool:
    if not email:
        logger.warning("receipt skipped — no email provided (item: %s)", item_name)
        return False

    host = os.getenv('SMTP_HOST', '').strip()
    port = int(os.getenv('SMTP_PORT', '587'))
    user = os.getenv('SMTP_USER', '').strip()
    password = os.getenv('SMTP_PASS', '').strip()
    mail_from = os.getenv('MAIL_FROM', user or 'no-reply@seoulfit.local')

    if not host:
        logger.warning("receipt skipped — SMTP_HOST not configured (to: %s, item: %s)", email, item_name)
        return False

    msg = EmailMessage()
    msg['Subject'] = f'[SEOULFIT] 결제 완료 - {item_name}'
    msg['From'] = mail_from
    msg['To'] = email
    msg.set_content(
        f'결제가 완료되었습니다.\\n\\n상품: {item_name}\\n금액: {amount_jpy} JPY\\n\\n감사합니다.'
    )

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)

    return True
