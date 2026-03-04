# API 막힐 시 수동 대체:
# 구글맵에서 가게 이름+주소 10개를
# seongsu_poi.json에 직접 입력

import os
import json
import re
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.environ["NAVER_CLIENT_ID"]
CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]

SEARCH_URL = "https://openapi.naver.com/v1/search/local.json"
KEYWORDS   = ["성수동 옷가게", "성수동 편집숍", "성수동 빈티지"]
OUTPUT     = "seongsu_poi.json"


def strip_html(text: str) -> str:
    """네이버 API 응답의 HTML 태그 제거"""
    return re.sub(r"<[^>]+>", "", text)


def search_local(keyword: str) -> list[dict]:
    headers = {
        "X-Naver-Client-Id":     CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET,
    }
    params = {
        "query":   keyword,
        "display": 5,   # 키워드당 최대 5개
        "start":   1,
        "sort":    "random",
    }
    resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return items


def parse_item(item: dict) -> dict:
    # mapx, mapy: 카텍 좌표계 → 소수점 형식으로 변환
    mapx = int(item.get("mapx", 0)) / 10_000_000
    mapy = int(item.get("mapy", 0)) / 10_000_000
    return {
        "name":     strip_html(item.get("title", "")),
        "address":  strip_html(item.get("roadAddress") or item.get("address", "")),
        "mapx":     mapx,
        "mapy":     mapy,
        "category": strip_html(item.get("category", "")),
    }


def main():
    all_items: list[dict] = []
    seen: set[str] = set()

    for keyword in KEYWORDS:
        print(f"[검색] {keyword} ...")
        try:
            items = search_local(keyword)
        except requests.HTTPError as e:
            print(f"  [오류] HTTP {e.response.status_code}: {e}")
            continue
        except Exception as e:
            print(f"  [오류] {e}")
            continue

        for item in items:
            parsed = parse_item(item)
            key = parsed["name"] + parsed["address"]
            if key in seen:
                continue
            seen.add(key)
            all_items.append(parsed)
            print(f"  + {parsed['name']} / {parsed['address']}")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] {len(all_items)}개 저장 → {OUTPUT}")


if __name__ == "__main__":
    main()
