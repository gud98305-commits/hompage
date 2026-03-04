"""
crawl_pipeline.py — SEOULFIT 크롤링 파이프라인

사용법:
  # 기본 실행 (29cm만, 다음 2개 가상 페이지 크롤링)
  python -m backend.services.crawl_pipeline --source 29cm --pages 2

  # wconcept 3페이지
  python -m backend.services.crawl_pipeline --source wconcept --pages 3

  # 무신사 4카테고리 균등 (--pages 4 → 추천순 4개)
  python -m backend.services.crawl_pipeline --source musinsa --pages 4

  # 병렬 실행 (터미널 2개에서 동시에)
  터미널1: python -m backend.services.crawl_pipeline --source 29cm --pages 2
  터미널2: python -m backend.services.crawl_pipeline --source wconcept --pages 2

  # ★ 대량 수집 (API 직접 호출, Playwright 없이)
  python -m backend.services.crawl_pipeline --bulk wconcept --limit 3000
  python -m backend.services.crawl_pipeline --bulk 29cm --limit 3000
  python -m backend.services.crawl_pipeline --bulk all --limit 3000

  # 진행 상태 확인
  python -m backend.services.crawl_pipeline --status

  # 진행 상태 초기화 (처음부터 다시)
  python -m backend.services.crawl_pipeline --reset-progress

옵션:
  --source     : 29cm | wconcept | musinsa | both | all (기본: both)
  --pages      : 한 번에 크롤링할 가상 페이지 수 (기본: 2)
  --max        : 페이지당 최대 상품 수 (기본: 80)
  --bulk       : 대량 수집 모드 (wconcept | 29cm | all) — API 직접 호출
  --limit      : --bulk 모드에서 수집할 총 상품 수 (기본: 3000)
  --status     : 진행 상태만 출력하고 종료
  --reset-progress : 진행 상태 초기화
  --verbose    : 상세 로그 출력
"""
from __future__ import annotations

import sys
import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = CRAWLER_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from shared.fx_converter import krw_to_jpy
from crawler.services.crawl_progress import (
    get_next_seeds,
    advance,
    locked_merge_save,
    progress_summary,
    save_progress,
)

try:
    from data_enrichment import (
        run_enrichment as run_data_enrichment,
        detect_category as detect_fashion_category,
    )
    _ENRICHMENT_AVAILABLE = True
except Exception:
    _ENRICHMENT_AVAILABLE = False

# Playwright 크롤러 (playwright 패키지 설치된 경우에만)
try:
    from crawler.services.crawler_29cm_pw import TwentyNineCrawlerPW
    from crawler.services.crawler_wconcept_pw import WConceptCrawlerPW
    from crawler.services.crawler_musinsa_pw import MusinsaCrawlerPW
    from crawler.services.crawler_playwright_base import PlaywrightCrawlerConfig
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

# 구형 requests 크롤러 (fallback)
try:
    from crawler.services.crawler_29cm import TwentyNineCrawler
    from crawler.services.crawler_wconcept import WConceptCrawler
    from crawler.services.crawler_common import CrawlConfig
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

RAW_PATH = DATA_DIR / "products_raw.json"
ENRICHED_PATH = DATA_DIR / "products_enriched.json"
_TARGET_CACHE_CATEGORIES = {"top", "bottom", "outer", "dress"}


def run_enrichment_step() -> bool:
    """products_raw.json -> products_enriched.json 추출 실행."""
    if not _ENRICHMENT_AVAILABLE:
        print("⚠️  data_enrichment 모듈을 불러오지 못해 추출 단계를 건너뜁니다.")
        return False
    try:
        stats = run_data_enrichment(raw_path=RAW_PATH, out_path=ENRICHED_PATH)
        print(
            "[추출] raw {raw_count}개 -> enriched {enriched_count}개 "
            "(비의류 제외 {skipped_count}개)".format(**stats)
        )
        print(f"       enriched 파일: {stats['out_path']}")
        return True
    except Exception as exc:
        print(f"⚠️  추출(enrichment) 실패: {exc}")
        return False


def filter_items_for_cache(items: list[dict]) -> tuple[list[dict], int]:
    """
    캐시에 저장할 상품 범위를 제한.
    요구사항: 의류(top/bottom/outer/dress)만 유지.
    """
    if not _ENRICHMENT_AVAILABLE:
        return items, 0

    kept: list[dict] = []
    dropped = 0
    for item in items:
        cat = detect_fashion_category(item.get("name", ""))
        if cat in _TARGET_CACHE_CATEGORIES:
            row = dict(item)
            row["fashion_category_hint"] = cat
            kept.append(row)
        else:
            dropped += 1
    return kept, dropped


def run_one_mall(
    mall: str,
    *,
    pages: int,
    max_per_page: int,
    verbose: bool,
) -> list[dict]:
    """
    한 사이트의 다음 pages개 가상 페이지를 크롤링.
    크롤링 완료 후 진행 상태 업데이트.
    반환값: 수집된 상품 목록.
    """
    if not _PLAYWRIGHT_AVAILABLE:
        print("⚠️  playwright 패키지가 설치되어 있지 않습니다.")
        print("   pip install playwright --break-system-packages")
        print("   playwright install chromium")
        return []

    seeds = get_next_seeds(mall, pages)
    if not seeds:
        print(f"[{mall}] 등록된 가상 페이지 없음")
        return []

    print(f"\n[{mall}] {pages}개 가상 페이지 크롤링 시작")
    for i, s in enumerate(seeds, 1):
        print(f"  {i}. {s}")

    config = PlaywrightCrawlerConfig(
        mall=mall,
        seed_urls=seeds,
        max_products=max_per_page * pages,
        delay_sec=1.0,
        strict_images=True,
        verbose=verbose,
    )

    if mall == "29cm":
        crawler = TwentyNineCrawlerPW(config)
    elif mall == "wconcept":
        crawler = WConceptCrawlerPW(config)
    elif mall == "musinsa":
        crawler = MusinsaCrawlerPW(config)
    else:
        print(f"[{mall}] 지원하지 않는 사이트")
        return []

    items = crawler.crawl()

    # KRW → JPY 변환
    for item in items:
        item["price_jpy"] = krw_to_jpy(int(item.get("price_krw", 0)))

    items, dropped = filter_items_for_cache(items)
    print(f"[{mall}] {len(items)}개 수집 완료 (범위 외 제외 {dropped}개)")

    # 진행 상태 업데이트 (크롤링 성공 여부와 무관하게 항상 전진)
    advance(mall, pages)

    return items


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(
        description="SEOULFIT 크롤링 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        default="both",
        choices=["29cm", "wconcept", "musinsa", "both", "all"],
        help="크롤링 대상 사이트 (기본: both = 29cm+wconcept, all = 3개 전부)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=2,
        help="한 번에 크롤링할 가상 페이지 수 (기본: 2)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=80,
        dest="max_per_page",
        help="가상 페이지당 최대 상품 수 (기본: 80)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="진행 상태만 출력하고 종료",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="진행 상태를 처음(0)으로 초기화",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="상세 로그 출력",
    )
    parser.add_argument(
        "--bulk",
        metavar="MALL",
        default=None,
        choices=["wconcept", "29cm", "all"],
        help="대량 수집 모드: API 직접 호출 (Playwright 불필요). wconcept | 29cm | all",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3000,
        help="--bulk 모드에서 수집할 총 상품 수 (기본: 3000, 4카테고리 균등 분배)",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="크롤링 후 products_enriched.json 자동 생성 생략",
    )
    # 구형 호환 옵션 (무시)
    parser.add_argument("--malls", help=argparse.SUPPRESS)
    parser.add_argument("--max-products", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--playwright", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--allow-remote-image", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--force-empty", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    # ── 진행 상태 출력 모드 ───────────────────────────────────────────────
    if args.status:
        progress_summary()
        # 현재 raw 파일 통계도 출력
        if RAW_PATH.exists():
            try:
                raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
                mall_counts: dict[str, int] = {}
                for p in raw:
                    m = p.get("mall", "?")
                    mall_counts[m] = mall_counts.get(m, 0) + 1
                print("  캐시 현황:")
                for m, cnt in sorted(mall_counts.items()):
                    print(f"    {m:10s}: {cnt}개")
                print(f"  총 {len(raw)}개\n")
            except Exception:
                print("  (products_raw.json 읽기 실패)\n")
        return

    # ── 진행 상태 초기화 ─────────────────────────────────────────────────
    if args.reset_progress:
        save_progress({})
        print("✅  진행 상태가 초기화되었습니다. 다음 실행 시 처음부터 시작합니다.")
        progress_summary()
        return

    # ── 대량 수집 모드 (--bulk) ───────────────────────────────────────────
    if args.bulk:
        try:
            from bulk_collector import collect_wconcept, collect_29cm, _save_and_enrich
        except ImportError:
            print("❌  bulk_collector.py를 찾을 수 없습니다.")
            print("   프로젝트 루트에 bulk_collector.py 파일이 있는지 확인하세요.")
            return

        import asyncio as _asyncio

        bulk_malls = ["wconcept", "29cm"] if args.bulk == "all" else [args.bulk]
        bulk_items: list[dict] = []
        for mall in bulk_malls:
            if mall == "wconcept":
                items = _asyncio.run(collect_wconcept(args.limit))
            elif mall == "29cm":
                items = _asyncio.run(collect_29cm(args.limit))
            else:
                items = []
            bulk_items.extend(items)

        if bulk_items:
            _save_and_enrich(bulk_items, no_enrich=args.no_enrich)
            print(f"\n✅  대량 수집 완료: {len(bulk_items)}개")
        else:
            print("\n⚠️  수집된 상품 없음.")
        return

    # ── 크롤링 대상 결정 ─────────────────────────────────────────────────
    if args.source == "both":
        malls = ["29cm", "wconcept"]
    elif args.source == "all":
        malls = ["29cm", "wconcept", "musinsa"]
    else:
        malls = [args.source]

    # 진행 상태 미리 표시
    progress_summary()

    all_items: list[dict] = []
    for mall in malls:
        items = run_one_mall(
            mall,
            pages=args.pages,
            max_per_page=args.max_per_page,
            verbose=args.verbose,
        )
        all_items.extend(items)

    if not all_items:
        print("\n⚠️  수집된 상품 없음. products_raw.json 변경하지 않음.")
        if not args.no_enrich and RAW_PATH.exists():
            print("[추출] 기존 raw 캐시 기준으로 enriched 재생성 시도...")
            run_enrichment_step()
        return

    # ── 잠금 기반 병합 저장 (병렬 실행 안전) ────────────────────────────
    print(f"\n[저장] {len(all_items)}개 상품 병합 저장 중...")
    new_count = locked_merge_save(all_items)

    enriched_ok = False
    if args.no_enrich:
        print("\n[추출] --no-enrich 옵션으로 자동 추출을 생략했습니다.")
    else:
        print("\n[추출] products_enriched.json 생성 중...")
        enriched_ok = run_enrichment_step()

    print(f"\n✅  완료!")
    print(f"   이번 수집: {len(all_items)}개 | 신규 추가: {new_count}개")
    print(f"   raw 파일: {RAW_PATH}")
    if not enriched_ok:
        print("\n다음 단계: python data_enrichment.py")


# ── 하위 호환: run_crawlers / save API (다른 모듈에서 import 시) ─────────────

def run_crawlers(
    *,
    malls: list[str],
    max_products: int,
    strict_images: bool,
    verbose: bool,
    use_playwright: bool = True,
) -> list[dict]:
    """구형 API 호환용 래퍼."""
    all_items: list[dict] = []
    for mall in malls:
        if not _PLAYWRIGHT_AVAILABLE:
            break
        pages = max(1, max_products // 80)
        items = run_one_mall(mall, pages=pages, max_per_page=80, verbose=verbose)
        all_items.extend(items)
    return all_items


def save(items: list[dict], force_empty: bool = False) -> None:
    """구형 API 호환용 래퍼."""
    if not items and not force_empty:
        print("no items crawled; keeping existing dataset")
        return
    locked_merge_save(items)


if __name__ == "__main__":
    main()
