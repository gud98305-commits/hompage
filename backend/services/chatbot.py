"""
chatbot.py — 홈페이지 챗봇 서비스
"""
from __future__ import annotations

import os
from typing import Any

import requests

from backend.services.turso_db import GameResult, InventoryItem

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


def get_user_context(user_id: int, db) -> str:
    inventory = InventoryItem.get_by_user(db, user_id, limit=50)
    results   = GameResult.get_by_user(db, user_id, limit=10)

    style_counter:   dict[str, int] = {}
    color_counter:   dict[str, int] = {}
    keyword_counter: dict[str, int] = {}

    for r in results:
        for s in (r.selected_styles or []):
            style_counter[s] = style_counter.get(s, 0) + 1
        for c in (r.selected_colors or []):
            color_counter[c] = color_counter.get(c, 0) + 1
        for k in (r.selected_keywords or []):
            keyword_counter[k] = keyword_counter.get(k, 0) + 1

    top_styles   = sorted(style_counter,   key=style_counter.get,   reverse=True)[:3]
    top_colors   = sorted(color_counter,   key=color_counter.get,   reverse=True)[:3]
    top_keywords = sorted(keyword_counter, key=keyword_counter.get, reverse=True)[:3]

    inv_summary: list[str] = []
    for item in inventory[:20]:
        tags_str   = ", ".join(item.tags or [])
        colors_str = ", ".join(item.colors or [])
        inv_summary.append(
            f"- {item.name} ({item.brand or '브랜드미상'}) / "
            f"카테고리:{item.category} / 스타일:{item.style} / "
            f"색상:{colors_str} / 태그:{tags_str}"
        )

    context_parts: list[str] = []
    if top_styles or top_colors or top_keywords:
        context_parts.append("【유저 스타일 선호도】")
        if top_styles:
            context_parts.append(f"  선호 스타일: {', '.join(top_styles)}")
        if top_colors:
            context_parts.append(f"  선호 색상:   {', '.join(top_colors)}")
        if top_keywords:
            context_parts.append(f"  패션 키워드: {', '.join(top_keywords)}")
    if inv_summary:
        context_parts.append("\n【보유 옷 인벤토리 (최근 20개)】")
        context_parts.extend(inv_summary)
    if not context_parts:
        return ""
    return "\n".join(context_parts)


def chat(
    message: str,
    user_id: int | None,
    db=None,
    conversation_history: list[dict] | None = None,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return "죄송합니다, 현재 챗봇 서비스를 사용할 수 없습니다."

    user_context = ""
    if user_id and db:
        try:
            user_context = get_user_context(user_id, db)
        except Exception as e:
            print(f"[Chatbot] 컨텍스트 로드 실패: {e}")

    system_prompt = (
        "당신은 SEOULFIT의 K-패션 스타일 어시스턴트입니다.\n"
        "사용자에게 한국 패션 트렌드와 코디를 추천해주세요.\n"
        "응답은 항상 한국어로, 친근하고 전문적인 톤으로 작성하세요.\n"
        "상품 추천 시 구체적인 스타일링 팁을 함께 제공하세요."
    )
    if user_context:
        system_prompt += (
            "\n\n아래는 이 유저의 게임 인벤토리와 스타일 선호도입니다. "
            "추천 시 이 정보를 적극 활용하세요:\n\n" + user_context
        )
    else:
        system_prompt += (
            "\n\n이 유저는 아직 로그인하지 않았거나 게임 이력이 없습니다. "
            "일반적인 K-패션 트렌드 기반으로 추천해주세요."
        )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({"role": "user", "content": message})

    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 800,
    }
    try:
        resp = requests.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[Chatbot] GPT 호출 실패: {e}")
        return "죄송합니다, 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요."


def get_saved_items(user_id: int, db) -> list[dict[str, Any]]:
    items = InventoryItem.get_by_user(db, user_id, limit=1000)
    return [
        {
            "product_id":   i.product_id,
            "name":         i.name,
            "brand":        i.brand,
            "category":     i.category,
            "sub_category": i.sub_category,
            "style":        i.style,
            "colors":       i.colors or [],
            "tags":         i.tags or [],
            "image_url":    i.image_url,
            "price_krw":    i.price_krw,
            "source_url":   i.source_url,
            "obtained_at":  i.obtained_at if i.obtained_at else None,
        }
        for i in items
    ]
