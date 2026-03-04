from __future__ import annotations

import os


def krw_to_jpy(krw: int) -> int:
    rate = float(os.getenv('JPY_RATE', '0.11'))
    return max(1, round(krw * rate))
