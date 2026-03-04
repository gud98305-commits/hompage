from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ImageQualityResult:
    ok: bool
    reason: str
    filtered_detail_images: list[str]
    valid_detail_count: int
    unique_ratio: float
    same_as_main_count: int
    missing_detail_count: int
    too_small_detail_count: int
    main_size_bytes: int


def _web_path_to_local(root: Path, web_path: str) -> Path | None:
    if not web_path or web_path.startswith("http"):
        return None
    return root / web_path.lstrip("/")


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def evaluate_local_images(
    *,
    root: Path,
    main_image: str,
    detail_images: list[str],
    min_detail_images: int = 3,
    min_main_bytes: int = 3000,
    min_detail_bytes: int = 1000,
    min_detail_unique_ratio: float = 0.6,
) -> ImageQualityResult:
    main_local = _web_path_to_local(root, main_image)
    if main_local is None or not main_local.exists():
        return ImageQualityResult(
            ok=False,
            reason="main image missing",
            filtered_detail_images=[],
            valid_detail_count=0,
            unique_ratio=0.0,
            same_as_main_count=0,
            missing_detail_count=0,
            too_small_detail_count=0,
            main_size_bytes=0,
        )

    try:
        main_size = main_local.stat().st_size
    except OSError:
        main_size = 0
    if main_size < min_main_bytes:
        return ImageQualityResult(
            ok=False,
            reason=f"main image too small ({main_size}B)",
            filtered_detail_images=[],
            valid_detail_count=0,
            unique_ratio=0.0,
            same_as_main_count=0,
            missing_detail_count=0,
            too_small_detail_count=0,
            main_size_bytes=main_size,
        )

    try:
        main_digest = _sha1(main_local)
    except Exception:
        main_digest = ""

    valid_hashes: list[str] = []
    unique_hashes: set[str] = set()
    filtered_details: list[str] = []
    same_as_main = 0
    missing = 0
    too_small = 0

    for web_path in detail_images:
        local = _web_path_to_local(root, web_path)
        if local is None or not local.exists():
            missing += 1
            continue
        try:
            size = local.stat().st_size
        except OSError:
            missing += 1
            continue
        if size < min_detail_bytes:
            too_small += 1
            continue

        try:
            digest = _sha1(local)
        except Exception:
            continue

        valid_hashes.append(digest)
        if digest == main_digest:
            same_as_main += 1

        if digest in unique_hashes:
            continue
        unique_hashes.add(digest)
        filtered_details.append(web_path)

    valid_count = len(valid_hashes)
    unique_ratio = (len(unique_hashes) / valid_count) if valid_count else 0.0

    if valid_count < min_detail_images:
        return ImageQualityResult(
            ok=False,
            reason=f"detail images too few ({valid_count} < {min_detail_images})",
            filtered_detail_images=filtered_details,
            valid_detail_count=valid_count,
            unique_ratio=unique_ratio,
            same_as_main_count=same_as_main,
            missing_detail_count=missing,
            too_small_detail_count=too_small,
            main_size_bytes=main_size,
        )

    if unique_ratio < min_detail_unique_ratio:
        return ImageQualityResult(
            ok=False,
            reason=f"detail diversity low ({unique_ratio:.2f} < {min_detail_unique_ratio:.2f})",
            filtered_detail_images=filtered_details,
            valid_detail_count=valid_count,
            unique_ratio=unique_ratio,
            same_as_main_count=same_as_main,
            missing_detail_count=missing,
            too_small_detail_count=too_small,
            main_size_bytes=main_size,
        )

    if main_digest and same_as_main >= max(2, valid_count // 2):
        return ImageQualityResult(
            ok=False,
            reason=f"detail images mostly same as main ({same_as_main}/{valid_count})",
            filtered_detail_images=filtered_details,
            valid_detail_count=valid_count,
            unique_ratio=unique_ratio,
            same_as_main_count=same_as_main,
            missing_detail_count=missing,
            too_small_detail_count=too_small,
            main_size_bytes=main_size,
        )

    return ImageQualityResult(
        ok=True,
        reason="ok",
        filtered_detail_images=filtered_details,
        valid_detail_count=valid_count,
        unique_ratio=unique_ratio,
        same_as_main_count=same_as_main,
        missing_detail_count=missing,
        too_small_detail_count=too_small,
        main_size_bytes=main_size,
    )
