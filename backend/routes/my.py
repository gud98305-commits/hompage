from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/my', tags=['my'])

_PURCHASES_FILE = Path(__file__).resolve().parents[2] / 'backend' / 'data' / 'purchases.json'
_ROOT = Path(__file__).resolve().parents[2]


@router.get('/purchases')
def get_purchases() -> dict:
    if not _PURCHASES_FILE.exists():
        return {'purchases': []}
    try:
        purchases = json.loads(_PURCHASES_FILE.read_text(encoding='utf-8'))
        return {'purchases': purchases}
    except Exception as e:
        logger.warning("purchases load failed: %s", e)
        return {'purchases': []}
