"""Pixel-level readiness checks shared by product UI evidence captures."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat


def _require_png_format(image_format: str | None) -> None:
    if image_format != "PNG":
        raise ValueError(f"expected PNG content, received {image_format or 'unknown'}")


def inspect_png_artifact(screenshot: Path) -> dict[str, object]:
    """Decode one PNG twice so verify and full pixel loading both run."""
    try:
        with Image.open(screenshot) as source:
            image_format = str(source.format or "")
            source.verify()
        _require_png_format(image_format)
        with Image.open(screenshot) as source:
            _require_png_format(source.format)
            source.load()
            width, height = source.size
            mode = source.mode
            grayscale = source.convert("L")
            histogram = grayscale.histogram()
            pixel_count = width * height
            contrast = float(ImageStat.Stat(grayscale).stddev[0])
    except Exception as exc:
        raise RuntimeError(
            f"{screenshot} could not be verified and fully decoded: {exc}"
        ) from exc

    if width <= 0 or height <= 0 or pixel_count <= 0:
        raise RuntimeError(f"{screenshot} decoded to an empty PNG image")
    visible_ratio = sum(histogram[90:]) / pixel_count
    return {
        "format": "PNG",
        "mode": mode,
        "width": width,
        "height": height,
        "pixel_count": pixel_count,
        "visible_pixel_ratio": float(visible_ratio),
        "contrast": contrast,
        "nonblank": visible_ratio >= 0.001 and contrast >= 2.0,
    }


def assert_region_has_no_unpainted_block(
    screenshot: Path,
    bounds: tuple[int, int, int, int],
    *,
    surface_name: str,
    black_threshold: int = 5,
    max_black_ratio: float = 0.14,
) -> None:
    """Reject pure-black backing-store gaps inside a required product region."""
    with Image.open(screenshot) as captured:
        image = captured.convert("RGB")
        left, top, right, bottom = _clamped_bounds(image.size, bounds)
        region = image.crop((left, top, right, bottom))
    if region.width <= 0 or region.height <= 0:
        raise RuntimeError(
            f"{surface_name} required region is outside {screenshot.name}."
        )

    pixels = list(_pixels(region))
    black_pixels = sum(max(pixel) <= black_threshold for pixel in pixels)
    black_ratio = black_pixels / max(len(pixels), 1)
    if black_ratio > max_black_ratio or _contains_black_tile(
        region,
        black_threshold=black_threshold,
    ):
        raise RuntimeError(
            f"{surface_name} contains an unpainted block in {screenshot.name} "
            f"({black_ratio:.1%} pure black)."
        )


def assert_consecutive_complete_frames(
    first: Path,
    second: Path,
    *,
    max_changed_pixel_ratio: float = 0.12,
    difference_threshold: int = 18,
) -> float:
    """Require two complete captures to settle without a large repaint transition."""
    with Image.open(first) as first_source, Image.open(second) as second_source:
        first_image = first_source.convert("RGB")
        second_image = second_source.convert("RGB")
        if first_image.size != second_image.size:
            raise RuntimeError(
                "Capture consecutive complete frames changed dimensions."
            )
        difference = ImageChops.difference(first_image, second_image)
        changed = sum(
            max(pixel) > difference_threshold for pixel in _pixels(difference)
        )
        pixel_count = max(first_image.width * first_image.height, 1)
    changed_ratio = changed / pixel_count
    if changed_ratio > max_changed_pixel_ratio:
        raise RuntimeError(
            "Capture did not produce consecutive complete frames "
            f"({changed_ratio:.1%} of pixels changed)."
        )
    return changed_ratio


def assert_region_matches_reference(
    screenshot: Path,
    bounds: tuple[int, int, int, int],
    reference: Path | Image.Image,
    *,
    surface_name: str,
    edge_threshold: int = 18,
    minimum_reference_edge_pixels: int = 4,
    minimum_edge_recall: float = 0.42,
    maximum_changed_pixel_ratio: float = 0.55,
    content_inset: int = 3,
) -> dict[str, object]:
    """Require a screenshot crop to retain a settled live reference render.

    The comparison is intentionally image-based. It checks spatial edge recall,
    local detail tiles, and broad pixel drift, so a theme-colored rectangle
    cannot replace labels, buttons, tables, or activity content.
    """
    with Image.open(screenshot) as captured:
        image = captured.convert("RGB")
        left, top, right, bottom = _clamped_bounds(image.size, bounds)
        observed = image.crop((left, top, right, bottom))
    expected = _reference_image(reference)
    if observed.width <= 0 or observed.height <= 0:
        raise RuntimeError(
            f"{surface_name} reference region is outside {screenshot.name}."
        )
    if expected.width <= 0 or expected.height <= 0:
        raise RuntimeError(f"{surface_name} live reference render is empty.")
    if expected.size != observed.size:
        expected = expected.resize(observed.size, Image.Resampling.LANCZOS)

    inset = max(
        min(
            int(content_inset),
            (observed.width - 1) // 4,
            (observed.height - 1) // 4,
        ),
        0,
    )
    if inset:
        crop_box = (
            inset,
            inset,
            observed.width - inset,
            observed.height - inset,
        )
        observed = observed.crop(crop_box)
        expected = expected.crop(crop_box)

    metrics = _reference_match_metrics(
        expected,
        observed,
        edge_threshold=edge_threshold,
    )
    if int(metrics["reference_edge_pixels"]) < minimum_reference_edge_pixels:
        raise RuntimeError(
            f"{surface_name} live reference render has no machine-checkable detail."
        )
    if (
        float(metrics["edge_recall"]) < minimum_edge_recall
        or float(metrics["missing_detail_tile_ratio"]) > 0.35
        or float(metrics["changed_pixel_ratio"]) > maximum_changed_pixel_ratio
    ):
        raise RuntimeError(
            f"{surface_name} does not match its settled live reference render in "
            f"{screenshot.name} (edge recall {metrics['edge_recall']:.1%}, "
            f"missing detail tiles {metrics['missing_detail_tile_ratio']:.1%}, "
            f"changed pixels {metrics['changed_pixel_ratio']:.1%})."
        )
    return {
        "surface_name": surface_name,
        "bounds": [left, top, right, bottom],
        "minimum_required_edge_recall": float(minimum_edge_recall),
        "maximum_allowed_changed_pixel_ratio": float(maximum_changed_pixel_ratio),
        "maximum_allowed_missing_detail_tile_ratio": 0.35,
        "minimum_reference_edge_pixels": int(minimum_reference_edge_pixels),
        **metrics,
    }


def frame_readiness_payload(
    *,
    changed_pixel_ratio: float,
    required_regions: list[str],
    reference_matches: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, object]:
    """Return the machine-readable contract recorded beside one screenshot."""
    matches = [dict(match) for match in reference_matches or ()]
    edge_recalls = [
        float(match["edge_recall"]) for match in matches if "edge_recall" in match
    ]
    changed_ratios = [
        float(match["changed_pixel_ratio"])
        for match in matches
        if "changed_pixel_ratio" in match
    ]
    return {
        "consecutive_complete_frames": 2,
        "stable": True,
        "max_changed_pixel_ratio": round(float(changed_pixel_ratio), 6),
        "required_regions": list(dict.fromkeys(required_regions)),
        "reference_validated": bool(matches),
        "reference_comparison_count": len(matches),
        "minimum_reference_edge_recall": (
            round(min(edge_recalls), 6) if edge_recalls else 0.0
        ),
        "maximum_reference_changed_pixel_ratio": (
            round(max(changed_ratios), 6) if changed_ratios else 0.0
        ),
        "reference_regions": matches,
    }


def _contains_black_tile(
    region: Image.Image,
    *,
    black_threshold: int,
) -> bool:
    tile_size = max(min(24, region.width, region.height), 8)
    if region.width < tile_size or region.height < tile_size:
        return False
    for top in range(0, region.height - tile_size + 1, tile_size):
        for left in range(0, region.width - tile_size + 1, tile_size):
            tile = region.crop(
                (left, top, left + tile_size, top + tile_size),
            )
            pixels = list(_pixels(tile))
            black = sum(max(pixel) <= black_threshold for pixel in pixels)
            if black >= len(pixels) * 0.98:
                return True
    return False


def _clamped_bounds(
    size: tuple[int, int],
    bounds: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    width, height = size
    left, top, right, bottom = bounds
    return (
        max(min(int(left), width), 0),
        max(min(int(top), height), 0),
        max(min(int(right), width), 0),
        max(min(int(bottom), height), 0),
    )


def _reference_image(reference: Path | Image.Image) -> Image.Image:
    if isinstance(reference, Path):
        with Image.open(reference) as source:
            return source.convert("RGB")
    return reference.convert("RGB").copy()


def _reference_match_metrics(
    expected: Image.Image,
    observed: Image.Image,
    *,
    edge_threshold: int,
) -> dict[str, float | int]:
    expected_gray = ImageOps.grayscale(expected)
    observed_gray = ImageOps.grayscale(observed)
    expected_edges = _edge_mask(expected_gray, threshold=edge_threshold)
    observed_edges = _edge_mask(observed_gray, threshold=edge_threshold)
    observed_nearby = observed_edges.filter(ImageFilter.MaxFilter(5))

    reference_edge_pixels = _white_pixel_count(expected_edges)
    matching_edges = _white_pixel_count(
        ImageChops.multiply(expected_edges, observed_nearby)
    )
    edge_recall = matching_edges / max(reference_edge_pixels, 1)

    difference = ImageChops.difference(expected, observed).convert("L")
    changed_pixels = sum(pixel > 24 for pixel in _pixels(difference))
    pixel_count = max(expected.width * expected.height, 1)
    changed_ratio = changed_pixels / pixel_count

    detail_tiles = 0
    missing_tiles = 0
    tile_size = max(min(48, expected.width, expected.height), 12)
    for top in range(0, expected.height, tile_size):
        for left in range(0, expected.width, tile_size):
            right = min(left + tile_size, expected.width)
            bottom = min(top + tile_size, expected.height)
            expected_tile = expected_edges.crop((left, top, right, bottom))
            edge_pixels = _white_pixel_count(expected_tile)
            if edge_pixels < 8:
                continue
            detail_tiles += 1
            matching_tile = ImageChops.multiply(
                expected_tile,
                observed_nearby.crop((left, top, right, bottom)),
            )
            tile_recall = _white_pixel_count(matching_tile) / edge_pixels
            if tile_recall < 0.25:
                missing_tiles += 1
    missing_tile_ratio = missing_tiles / max(detail_tiles, 1)
    return {
        "edge_recall": float(edge_recall),
        "changed_pixel_ratio": float(changed_ratio),
        "reference_edge_pixels": int(reference_edge_pixels),
        "detail_tile_count": int(detail_tiles),
        "missing_detail_tile_ratio": float(missing_tile_ratio),
    }


def _edge_mask(image: Image.Image, *, threshold: int) -> Image.Image:
    edges = image.filter(ImageFilter.FIND_EDGES)
    threshold_table = [255 if value >= threshold else 0 for value in range(256)]
    mask = edges.point(threshold_table, mode="1").convert("L")
    if mask.width > 4 and mask.height > 4:
        inner = mask.crop((2, 2, mask.width - 2, mask.height - 2))
        mask = Image.new("L", mask.size)
        mask.paste(inner, (2, 2))
    return mask


def _white_pixel_count(image: Image.Image) -> int:
    histogram = image.histogram()
    return int(histogram[255]) if len(histogram) > 255 else 0


def _pixels(image: Image.Image) -> Iterable[Any]:
    """Expose Pillow pixel data through a stable, typed iterable boundary."""
    flattened = getattr(image, "get_flattened_data", None)
    if callable(flattened):
        return cast(Iterable[Any], flattened())
    return cast(Iterable[Any], image.getdata())
