#!/usr/bin/env python3
"""
Recover products by known product IDs instead of category crawling.

Examples:
  python recover_products.py --mall musinsa --ids 5961669,5961682
  python recover_products.py --ids-file data/recovery_ids.json
  python recover_products.py --from-checkpoint --limit 100
  python recover_products.py --from-images --mall musinsa --no-enrich

Supported ids-file formats:
  1. JSON object by mall:
     {"musinsa": [5961669, 5961682], "wconcept": [306634348], "29cm": [1234567]}
  2. JSON object with checkpoint-style keys:
     {"musinsa_5961669": true, "musinsa_5961682": true}
  3. Text file, one token per line:
     musinsa_5961669
     wconcept:306634348
     5961682   # requires --mall
"""
from __future__ import annotations

import sys
import argparse
import json
import re
from collections import defaultdict
from itertools import islice
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT  # 기존 코드 호환용 별칭
CRAWLER_ROOT = Path(__file__).resolve().parents[0]
DATA_DIR = CRAWLER_ROOT / "data"
IMG_ROOT = CRAWLER_ROOT / "images"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

CHECKPOINT_PATH = DATA_DIR / "enrichment_checkpoint.json"
SUPPORTED_MALLS = ("29cm", "wconcept", "musinsa")
PREFIXED_ID_RE = re.compile(r"^(29cm|wconcept|musinsa)\s*[:_/,\-]?\s*(\d+)$", re.IGNORECASE)
MUSINSA_IMAGE_ID_RE = re.compile(r"^musinsa_(\d+)_", re.IGNORECASE)


def _parse_one_token(token: str, default_mall: str | None) -> list[tuple[str, str]]:
    token = str(token).strip()
    if not token:
        return []

    hit = PREFIXED_ID_RE.match(token)
    if hit:
        return [(hit.group(1).lower(), hit.group(2))]

    if token.isdigit():
        if not default_mall:
            raise ValueError(f"Numeric id '{token}' needs --mall.")
        return [(default_mall, token)]

    pairs: list[tuple[str, str]] = []
    for mall, product_id in re.findall(r"(29cm|wconcept|musinsa)[_:](\d+)", token, re.IGNORECASE):
        pairs.append((mall.lower(), product_id))
    if pairs:
        return pairs

    raise ValueError(f"Could not parse token '{token}'.")


def _collect_pairs(value, *, default_mall: str | None) -> list[tuple[str, str]]:
    if value is None:
        return []

    if isinstance(value, dict):
        pairs: list[tuple[str, str]] = []
        mall_keys = [str(key).lower() for key in value.keys()]
        if any(key in SUPPORTED_MALLS for key in mall_keys):
            for mall, items in value.items():
                mall_name = str(mall).lower()
                if mall_name not in SUPPORTED_MALLS:
                    continue
                pairs.extend(_collect_pairs(items, default_mall=mall_name))
            return pairs

        for key in value.keys():
            pairs.extend(_collect_pairs(str(key), default_mall=default_mall))
        return pairs

    if isinstance(value, (list, tuple, set)):
        pairs: list[tuple[str, str]] = []
        for item in value:
            pairs.extend(_collect_pairs(item, default_mall=default_mall))
        return pairs

    return _parse_one_token(str(value), default_mall)


def _parse_ids_arg(raw: str, *, default_mall: str | None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for token in raw.split(","):
        pairs.extend(_parse_one_token(token, default_mall))
    return pairs


def _load_ids_file(path: Path, *, default_mall: str | None) -> list[tuple[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        return _collect_pairs(payload, default_mall=default_mall)

    pairs: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        pairs.extend(_parse_one_token(line, default_mall))
    return pairs


def _load_checkpoint_ids() -> list[tuple[str, str]]:
    if not CHECKPOINT_PATH.exists():
        return []
    payload = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return _collect_pairs(payload, default_mall=None)


def _load_ids_from_images() -> list[tuple[str, str]]:
    image_dir = IMG_ROOT / "musinsa"
    if not image_dir.exists():
        return []

    pairs: list[tuple[str, str]] = []
    for path in image_dir.iterdir():
        if not path.is_file():
            continue
        hit = MUSINSA_IMAGE_ID_RE.match(path.name)
        if hit:
            pairs.append(("musinsa", hit.group(1)))
    return pairs


def _group_pairs(
    pairs: list[tuple[str, str]],
    *,
    limit: int | None,
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()

    for mall, product_id in pairs:
        mall_name = str(mall).lower()
        pid = str(product_id).strip()
        if mall_name not in SUPPORTED_MALLS or not pid.isdigit():
            continue
        key = f"{mall_name}:{pid}"
        if key in seen:
            continue
        seen.add(key)
        grouped[mall_name].append(pid)

    if limit is not None and limit > 0:
        for mall in list(grouped.keys()):
            grouped[mall] = grouped[mall][:limit]

    return dict(grouped)


def _build_product_url(mall: str, product_id: str) -> str:
    if mall == "musinsa":
        return f"https://www.musinsa.com/products/{product_id}"
    if mall == "wconcept":
        return f"https://m.wconcept.co.kr/Product/{product_id}"
    if mall == "29cm":
        return f"https://www.29cm.co.kr/products/{product_id}"
    raise ValueError(f"Unsupported mall: {mall}")


def _chunked(values: list[str], size: int):
    if size <= 0:
        yield values
        return
    it = iter(values)
    while True:
        batch = list(islice(it, size))
        if not batch:
            break
        yield batch


def _recover_one_mall(
    mall: str,
    product_ids: list[str],
    *,
    strict_images: bool,
    headless: bool,
    verbose: bool,
    delay_sec: float,
) -> list[dict]:
    try:
        from crawler.services.crawler_playwright_base import PlaywrightCrawlerConfig
        from crawler.services.crawler_29cm_pw import TwentyNineCrawlerPW
        from crawler.services.crawler_wconcept_pw import WConceptCrawlerPW
        from crawler.services.crawler_musinsa_pw import MusinsaCrawlerPW
    except ImportError as exc:
        raise RuntimeError(
            "Playwright crawler dependencies are missing. "
            "Install with `pip install -r backend/requirements.txt` and `playwright install chromium`."
        ) from exc

    urls = [_build_product_url(mall, product_id) for product_id in product_ids]
    config = PlaywrightCrawlerConfig(
        mall=mall,
        seed_urls=urls,
        max_products=len(urls),
        delay_sec=delay_sec,
        strict_images=strict_images,
        verbose=verbose,
        headless=headless,
    )

    class _DirectLinksMixin:
        def __init__(self, cfg, direct_urls):
            super().__init__(cfg)
            self._direct_urls = direct_urls

        async def discover_links(self, context):
            return self._direct_urls

    class DirectTwentyNineCrawler(_DirectLinksMixin, TwentyNineCrawlerPW):
        pass

    class DirectWConceptCrawler(_DirectLinksMixin, WConceptCrawlerPW):
        pass

    class DirectMusinsaCrawler(_DirectLinksMixin, MusinsaCrawlerPW):
        pass

    crawler_map = {
        "29cm": DirectTwentyNineCrawler,
        "wconcept": DirectWConceptCrawler,
        "musinsa": DirectMusinsaCrawler,
    }
    crawler_cls = crawler_map[mall]
    crawler = crawler_cls(config, urls)
    return crawler.crawl()


def _run_enrichment() -> None:
    from data_enrichment import run_enrichment

    stats = run_enrichment()
    print(
        "[enrich] raw {raw_count} -> enriched {enriched_count} "
        "(skipped {skipped_count})".format(**stats)
    )


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMG_ROOT.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(
        description="Recover product data from known product ids.",
    )
    parser.add_argument(
        "--mall",
        choices=SUPPORTED_MALLS,
        help="Mall for bare numeric ids. Also filters recovery to that mall.",
    )
    parser.add_argument(
        "--ids",
        help="Comma-separated product ids. Prefix with mall when mixing malls.",
    )
    parser.add_argument(
        "--ids-file",
        type=Path,
        help="JSON/TXT file containing product ids.",
    )
    parser.add_argument(
        "--from-checkpoint",
        action="store_true",
        help="Load ids from data/enrichment_checkpoint.json.",
    )
    parser.add_argument(
        "--from-images",
        action="store_true",
        help="Extract recoverable ids from image filenames (currently musinsa only).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum ids per mall after de-duplication.",
    )
    parser.add_argument(
        "--strict-images",
        action="store_true",
        help="Reject products that fail local image quality checks.",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run browser in visible mode for debugging.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between product pages in seconds (default: 0.5).",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip products_enriched.json regeneration.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose crawler logs.",
    )
    parser.add_argument(
        "--save-every",
        type=int,
        default=0,
        help="Merge-save every N requested ids (default: save once at the end).",
    )
    args = parser.parse_args()

    all_pairs: list[tuple[str, str]] = []

    if args.ids:
        all_pairs.extend(_parse_ids_arg(args.ids, default_mall=args.mall))
    if args.ids_file:
        all_pairs.extend(_load_ids_file(args.ids_file, default_mall=args.mall))
    if args.from_checkpoint:
        all_pairs.extend(_load_checkpoint_ids())
    if args.from_images:
        all_pairs.extend(_load_ids_from_images())

    if not all_pairs:
        parser.error("No product ids provided. Use --ids, --ids-file, --from-checkpoint, or --from-images.")

    grouped = _group_pairs(all_pairs, limit=args.limit)
    if args.mall:
        selected = grouped.get(args.mall, [])
        grouped = {args.mall: selected} if selected else {}
    if not grouped:
        parser.error("No valid recoverable ids were found.")

    from crawler.services.crawl_progress import locked_merge_save
    from shared.fx_converter import krw_to_jpy

    requested_total = 0
    recovered_total = 0
    merged_new_total = 0

    for mall in SUPPORTED_MALLS:
        product_ids = grouped.get(mall, [])
        if not product_ids:
            continue

        requested_total += len(product_ids)
        batch_size = args.save_every if args.save_every and args.save_every > 0 else len(product_ids)
        mall_recovered = 0
        mall_merged_new = 0
        print(f"[{mall}] recovering {len(product_ids)} products by id...")

        for batch_idx, batch_ids in enumerate(_chunked(product_ids, batch_size), start=1):
            batch_label = f"{batch_idx}"
            print(
                f"[{mall}] batch {batch_label}: requested {len(batch_ids)} "
                f"(save_every={batch_size if args.save_every else 'end'})"
            )
            try:
                items = _recover_one_mall(
                    mall,
                    batch_ids,
                    strict_images=args.strict_images,
                    headless=not args.headful,
                    verbose=args.verbose,
                    delay_sec=max(0.0, args.delay),
                )
            except Exception as exc:
                print(f"[{mall}] batch {batch_label} failed: {exc}")
                continue

            for item in items:
                if not item.get("price_jpy"):
                    item["price_jpy"] = krw_to_jpy(int(item.get("price_krw", 0) or 0))

            mall_recovered += len(items)
            recovered_total += len(items)

            if items:
                new_count = locked_merge_save(items)
                mall_merged_new += new_count
                merged_new_total += new_count
                print(
                    f"[{mall}] batch {batch_label}: recovered {len(items)} "
                    f"-> merged {new_count} new items"
                )
            else:
                print(f"[{mall}] batch {batch_label}: no recovered items")

        print(
            f"[{mall}] requested {len(product_ids)} -> recovered {mall_recovered} "
            f"(new merged {mall_merged_new})"
        )

    if not recovered_total:
        print("No products were recovered. products_raw.json was not changed.")
        return

    print(
        f"[done] requested {requested_total}, recovered {recovered_total}, "
        f"merged as {merged_new_total} new items"
    )

    if args.no_enrich:
        print("[enrich] skipped (--no-enrich)")
        return

    _run_enrichment()


if __name__ == "__main__":
    main()
