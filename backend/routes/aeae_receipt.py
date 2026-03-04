"""
aeae_receipt.py — Dear aeae 영수증 생성 프록시 API
프론트엔드(receipt.html)에서 { name, worry }를 받아
OpenAI API로 위로 메시지를 생성하고 JSON을 반환한다.
"""
from __future__ import annotations

import json
import os
import re

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/proxy", tags=["aeae-receipt"])

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

SYSTEM_PROMPT = """You are a close friend — warm, perceptive, and the kind of person who always knows what to say. You don't sound like a therapist or a counselor. You sound like someone who has been through things and genuinely gets it. You speak casually, intimately, like a late-night conversation with someone you trust completely.

You also carry the voice of the Korean fashion brand "aeae" — soft, nostalgic, like a handwritten letter from someone who knew you before you grew up.

Brand values (never state these explicitly — just embody them naturally):
- Neverland: the tender part of a person that resists hardening
- Keepsake: feelings worth holding, even when they're complicated
- Touch: the relief of being truly understood

OUTPUT — JSON only, no markdown fences:
{
  "emotion": "感情ライン（日本語・短く）",
  "message_ja": "日本語メッセージ（6〜8行、\\nで改行）",
  "message_kr": "한국어 번역（6〜8줄、\\n으로 줄바꿈）",
  "discount_code": "KEEPAEAE_15",
  "discount_pct": 15
}"""


class ReceiptRequest(BaseModel):
    name: str = ""
    worry: str = ""


@router.post("/aeae-receipt")
def generate_receipt(payload: ReceiptRequest) -> dict:
    worry = payload.worry.strip()
    if not worry:
        raise HTTPException(status_code=400, detail="worry is required")

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    display_name = payload.name.strip() or "あなた"
    user_msg = f"名前: {display_name}\n悩み: {worry}"

    try:
        resp = requests.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.85,
                "max_tokens": 600,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI request failed: {exc}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI API error {resp.status_code}: {resp.text[:300]}",
        )

    try:
        content = resp.json()["choices"][0]["message"]["content"]
        # markdown 코드 블록 제거
        content = re.sub(r"```json\s*", "", content)
        content = re.sub(r"```\s*$", "", content)
        content = content.strip()
        data = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to parse OpenAI response: {exc}",
        )

    return {
        "emotion": data.get("emotion", "—"),
        "message_ja": data.get("message_ja", "—"),
        "message_kr": data.get("message_kr", ""),
        "discount_code": data.get("discount_code", "KEEPAEAE_15"),
        "discount_pct": data.get("discount_pct", 15),
    }
