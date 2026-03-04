#!/usr/bin/env python3
"""
enrich.py — GPT-4o-mini로 상품 데이터 정제

products_raw.json → products_enriched.json
추가 필드: gender, style, tags, colors, sub_category, is_clothing

사용법:
  python enrich.py                     # 기본 (raw → enriched)
  python enrich.py --reset             # enriched 초기화 후 전체 재처리
  python enrich.py --batch-size 50     # 배치 크기 조정

체크포인트:
  data/enrichment_checkpoint.json 에 처리된 ID 기록 → 중단 후 재실행 시 이어서 처리
"""
from __future__ import annotations

import sys
import argparse
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

# 로컬 실행 시 .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv(CRAWLER_ROOT / ".env")
except ImportError:
    pass

try:
    from openai import OpenAI
    _openai_available = True
except ImportError:
    _openai_available = False

BATCH_SIZE = 25

# ─── 성별 감지 키워드 ─────────────────────────────────────────────────────────
WOMEN_KW = ["우먼", "우먼즈", "여성", "레이디", "women", "woman", "ladies", "girl"]
MEN_KW = ["남성", "맨즈", "남자", "men", "man", "mens", "boy"]


def _detect_gender(name: str, brand: str = "") -> str:
    text = f"{name} {brand}".lower()
    is_women = any(k in text for k in WOMEN_KW)
    is_men = any(k in text for k in MEN_KW)
    if is_women and not is_men:
        return "women"
    if is_men and not is_women:
        return "men"
    return "unisex"


# ─── GPT 배치 정제 ────────────────────────────────────────────────────────────

def _enrich_batch(client: "OpenAI", items: list[dict]) -> list[dict]:
    """GPT-4o-mini로 배치 정제. 실패 시 원본 반환."""
    compact = [
        {"id": p.get("id"), "name": p.get("name", ""), "brand": p.get("brand", "")}
        for p in items
    ]
    prompt = (
        "다음 K-패션 상품 목록의 각 항목에 대해 JSON으로 분석해주세요.\n"
        "반환 형식 (배열):\n"
        "[\n"
        '  {"id": "...", "style": "casual|minimal|street|vintage|formal|y2k|romantic|preppy",\n'
        '   "tags": ["태그1","태그2","태그3"],\n'
        '   "colors": ["black","white","..."],\n'
        '   "sub_category": "tshirt|shirt|knit|hoodie|pants|skirt|denim|jacket|coat|dress|suit",\n'
        '   "is_clothing": true|false}\n'
        "]\n\n"
        "상품 목록:\n"
        + json.dumps(compact, ensure_ascii=False)
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "K-패션 전문가. 반드시 JSON 배열을 'items' 키 안에 반환."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            timeout=60,
        )
        parsed = json.loads(resp.choices[0].message.content)
        result_list = parsed.get("items", parsed) if isinstance(parsed, dict) else parsed
        id_map = {r.get("id"): r for r in result_list if r.get("id")}

        enriched = []
        for item in items:
            out = dict(item)
            ai = id_map.get(item.get("id"), {})
            if ai:
                out["style"] = ai.get("style", "")
                out["tags"] = ai.get("tags", [])
                out["colors"] = ai.get("colors", [])
                out["sub_category"] = ai.get("sub_category", "")
                out["is_clothing"] = ai.get("is_clothing", True)
            enriched.append(out)
        return enriched

    except Exception as e:
        print(f"  [GPT 오류] {e} — 이 배치는 원본 유지")
        return items


# ─── 메인 실행 ────────────────────────────────────────────────────────────────

def run(
    src: Path | None = None,
    dst: Path | None = None,
    batch_size: int = BATCH_SIZE,
    reset: bool = False,
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    src = src or DATA_DIR / "products_raw.json"
    dst = dst or DATA_DIR / "products_enriched.json"
    checkpoint_path = DATA_DIR / "enrichment_checkpoint.json"

    if not src.exists():
        print(f"[오류] {src} 파일이 없습니다. 먼저 크롤링을 실행하세요.")
        return

    products: list[dict] = json.loads(src.read_text(encoding="utf-8"))

    # 체크포인트 로드
    done_ids: set[str] = set()
    if not reset and checkpoint_path.exists():
        try:
            done_ids = set(json.loads(checkpoint_path.read_text(encoding="utf-8")))
            print(f"[체크포인트] 이미 처리된 {len(done_ids)}개 → 건너뜁니다.")
        except Exception:
            done_ids = set()

    # 기존 enriched 로드
    existing_enriched: dict[str, dict] = {}
    if not reset and dst.exists():
        try:
            for p in json.loads(dst.read_text(encoding="utf-8")):
                existing_enriched[p.get("id", "")] = p
        except Exception:
            pass

    # gender는 rule-based로 먼저 처리
    for p in products:
        if not p.get("gender"):
            p["gender"] = _detect_gender(p.get("name", ""), p.get("brand", ""))

    # GPT가 필요한 항목만 필터
    todo = [p for p in products if p.get("id") not in done_ids]
    print(f"[정제] 전체 {len(products)}개 중 미처리 {len(todo)}개")

    if not todo:
        print("[정제] 모두 처리 완료.")
        return

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("[경고] OPENAI_API_KEY 없음 → gender만 저장하고 종료.")
        merged = {**existing_enriched, **{p["id"]: p for p in products if p.get("id")}}
        dst.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=2))
        return

    if not _openai_available:
        print("[경고] openai 패키지 미설치 → pip install openai")
        return

    client = OpenAI(api_key=api_key)

    for i in range(0, len(todo), batch_size):
        batch = todo[i:i + batch_size]
        print(f"  배치 {i//batch_size + 1}/{(len(todo) + batch_size - 1)//batch_size} ({len(batch)}개)...")
        enriched_batch = _enrich_batch(client, batch)

        # enriched 업데이트
        for p in enriched_batch:
            existing_enriched[p.get("id", "")] = p
            done_ids.add(p.get("id", ""))

        # 체크포인트 저장
        checkpoint_path.write_text(
            json.dumps(list(done_ids), ensure_ascii=False), encoding="utf-8"
        )
        # enriched 저장 (중간 저장)
        dst.write_text(
            json.dumps(list(existing_enriched.values()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        time.sleep(0.5)

    print(f"\n[완료] {dst} — 총 {len(existing_enriched)}개")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()
    run(reset=args.reset, batch_size=args.batch_size)
