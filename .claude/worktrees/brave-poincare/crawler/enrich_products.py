#!/usr/bin/env python3
"""
Products data enrichment script.
Adds gender, style, tags fields to products_enriched.json
using rule-based gender detection + GPT-4o-mini batch style/tags.

Usage:
  python enrich_products.py            # enrich all missing fields
  python enrich_products.py --reset    # re-enrich everything from scratch
"""
from __future__ import annotations

import sys
import json
import os
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[0]
DATA_DIR = CRAWLER_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(PROJECT_ROOT / "backend" / ".env")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DATA_FILE = DATA_DIR / "products_enriched.json"
CHECKPOINT_FILE = DATA_DIR / "enrichment_checkpoint.json"

BATCH_SIZE = 25

# ── Gender detection ─────────────────────────────────────────────────────────
WOMEN_KEYWORDS = [
    "우먼", "우먼즈", "여성", "레이디", "레이디스",
    "women", "woman", "ladies", "lady", "girl", "girls",
]
MEN_KEYWORDS = [
    "남성", "맨즈", "남자",
    "men", "man", "mens", "mens", "boy", "boys",
]


def detect_gender(product: dict) -> str:
    text = (product.get("brand", "") + " " + product.get("name", "")).lower()
    for kw in WOMEN_KEYWORDS:
        if kw.lower() in text:
            return "women"
    for kw in MEN_KEYWORDS:
        if kw.lower() in text:
            return "men"
    return "unisex"


# ── GPT batch enrichment ─────────────────────────────────────────────────────
STYLE_OPTIONS = "캐주얼/스트리트/미니멀/페미닌/스포티/포멀/빈티지/아웃도어/워크웨어/아메카지"


def enrich_batch_with_gpt(products: list[dict]) -> list[dict]:
    """Call GPT-4o-mini to classify style + generate tags for a batch."""
    items_text = "\n".join(
        f'{i+1}. [{p["id"]}] {p.get("brand","")} | {p.get("name","")} | '
        f'{p.get("category","")}/{p.get("sub_category","")} | 색상: {", ".join(p.get("colors", []))}'
        for i, p in enumerate(products)
    )

    prompt = f"""한국 패션 상품들을 분류해주세요.

상품 목록:
{items_text}

각 상품에 대해 JSON으로 응답하세요:
{{
  "results": [
    {{
      "id": "상품 ID",
      "style": "{STYLE_OPTIONS} 중 하나",
      "tags": ["태그1", "태그2", "태그3"]
    }}
  ]
}}

tags는 3~5개, 한국어 키워드 (예: "오버핏", "베이직", "데일리룩", "루즈핏", "트렌디").
JSON만 반환하세요."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("results", [])
    except Exception as e:
        print(f"  GPT error: {e}")
        return []


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    reset = "--reset" in sys.argv

    print("Loading products_enriched.json...")
    with open(DATA_FILE, encoding="utf-8") as f:
        products: list[dict] = json.load(f)
    print(f"Total: {len(products)} products")

    # Load checkpoint
    checkpoint: dict[str, bool] = {}
    if not reset and CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            checkpoint = json.load(f)
        print(f"Checkpoint: {len(checkpoint)} already enriched")

    # ── Step 1: Rule-based gender detection ──
    print("\nStep 1: Gender detection (rule-based)...")
    gender_added = 0
    for p in products:
        if not p.get("gender"):
            p["gender"] = detect_gender(p)
            gender_added += 1
    print(f"  Added gender to {gender_added} products")

    # ── Step 2: GPT batch enrichment ──
    to_enrich = [p for p in products if not checkpoint.get(p["id"])]
    print(f"\nStep 2: Style & tags enrichment (GPT-4o-mini)...")
    print(f"  Needs enrichment: {len(to_enrich)} products")

    if not to_enrich:
        print("  All products already enriched!")
    else:
        total_batches = (len(to_enrich) + BATCH_SIZE - 1) // BATCH_SIZE
        for batch_num, i in enumerate(range(0, len(to_enrich), BATCH_SIZE), 1):
            batch = to_enrich[i : i + BATCH_SIZE]
            print(f"  Batch {batch_num}/{total_batches} ({len(batch)} items)...", end=" ", flush=True)

            results = enrich_batch_with_gpt(batch)
            result_map = {r["id"]: r for r in results}

            enriched_in_batch = 0
            for product in products:
                if product["id"] in result_map:
                    r = result_map[product["id"]]
                    product["style"] = r.get("style", "")
                    product["tags"] = r.get("tags", [])
                    checkpoint[product["id"]] = True
                    enriched_in_batch += 1

            print(f"OK ({enriched_in_batch} enriched)")

            # Save checkpoint + intermediate results after every batch
            with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, ensure_ascii=False)
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(products, f, ensure_ascii=False, indent=2)

            # Rate limit
            if batch_num < total_batches:
                time.sleep(0.3)

    # Final save
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    # Summary
    print("\n── Summary ──────────────────────────────────────────")
    has_gender = sum(1 for p in products if p.get("gender"))
    has_style  = sum(1 for p in products if p.get("style"))
    has_tags   = sum(1 for p in products if p.get("tags"))
    print(f"gender : {has_gender}/{len(products)}")
    print(f"style  : {has_style}/{len(products)}")
    print(f"tags   : {has_tags}/{len(products)}")
    print(f"\nSaved → {DATA_FILE}")


if __name__ == "__main__":
    main()
