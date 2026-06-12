from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from src.utils.file_utils import ensure_directory


@dataclass(slots=True)
class ReadingCleanupResult:
    markdown: str
    report: dict[str, object]


IMAGE_RE = re.compile(r"<img\b[^>]*>|!\[[^\]]*\]\([^)]+\)", re.IGNORECASE)
HTML_SRC_RE = re.compile(r'\bsrc=["\'](?P<src>[^"\']+)["\']', re.IGNORECASE)
MD_SRC_RE = re.compile(r"!\[[^\]]*\]\((?P<src>[^)]+)\)")
WIDTH_RE = re.compile(r'\bwidth=["\']?(?P<width>\d+(?:\.\d+)?)%?["\']?', re.IGNORECASE)
IMAGE_BOX_RE = re.compile(r"_box_(?P<x1>\d+)_(?P<y1>\d+)_(?P<x2>\d+)_(?P<y2>\d+)", re.IGNORECASE)

NAVIGATION_BLOCKS = {
    "read online",
    "access",
    "metrics & more",
    "article recommendations",
    "supporting information",
}
HEADER_BLOCK_RE = re.compile(r"^(?:www\.)?acs[a-z0-9-]*\.org$", re.IGNORECASE)
BOILERPLATE_PREFIXES = (
    "cite this:",
)
AD_MARKERS = (
    "cas biofinder",
    "discovery platform",
    "eliminate data",
    "silos. find",
    "what you",
    "need, when",
    "you need it",
    "streamline your r&d",
)


def clean_reading_markdown(
    markdown: str,
    *,
    asset_root: Path | None,
    page_number: int,
) -> ReadingCleanupResult:
    blocks = _split_blocks(markdown)
    kept: list[str] = []
    removed: list[dict[str, object]] = []
    in_ad = False

    for index, block in enumerate(blocks):
        stripped = block.strip()
        if not stripped:
            continue
        normalized = _normalize_block_text(stripped)
        lowered = normalized.lower()
        next_lowered = ""
        if index + 1 < len(blocks):
            next_lowered = _normalize_block_text(blocks[index + 1]).lower()

        if _is_ad_block(lowered):
            in_ad = True
        elif in_ad:
            in_ad = False
        if in_ad:
            removed.append(_removed("advertising", stripped, page_number))
            continue
        if _is_image_only_block(stripped) and _is_ad_block(next_lowered):
            removed.append(_removed("advertising_image", stripped, page_number))
            continue

        if _is_navigation_or_header(lowered):
            removed.append(_removed("navigation", stripped, page_number))
            continue

        if _is_decorative_image_block(stripped, asset_root):
            removed.append(_removed("decorative_image", stripped, page_number))
            continue

        kept.append(stripped)

    cleaned = "\n\n".join(kept)
    cleaned = _move_sentence_breaking_images(cleaned)
    cleaned = _repair_interrupted_words(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return ReadingCleanupResult(
        markdown=cleaned,
        report={
            "page_number": page_number,
            "removed_blocks": len(removed),
            "removed_images": sum(1 for item in removed if item["reason"] == "decorative_image"),
            "removed": removed,
        },
    )


def write_reading_cleanup_artifacts(
    *,
    page_markdowns: Mapping[int, str],
    document_root: Path,
    asset_root: Path | None,
) -> dict[str, object]:
    reader_pages_dir = document_root / "reader_pages"
    reader_path = document_root / "reader.md"
    report_path = document_root / "reading_cleanup_report.json"
    ensure_directory(reader_pages_dir)

    cleaned_pages: dict[int, str] = {}
    page_reports: list[dict[str, object]] = []
    for page_number in sorted(page_markdowns):
        result = clean_reading_markdown(
            page_markdowns[page_number],
            asset_root=asset_root,
            page_number=page_number,
        )
        cleaned_pages[page_number] = result.markdown
        page_reports.append(result.report)
        (reader_pages_dir / f"page_{page_number:03d}.md").write_text(
            result.markdown,
            encoding="utf-8",
        )

    reader_path.write_text(
        "\n\n".join(
            f"<!-- page: {page_number} -->\n{cleaned_pages[page_number].rstrip()}\n"
            for page_number in sorted(cleaned_pages)
        ),
        encoding="utf-8",
    )
    report = {
        "pages": page_reports,
        "removed_blocks": sum(int(page["removed_blocks"]) for page in page_reports),
        "removed_images": sum(int(page["removed_images"]) for page in page_reports),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "reader_markdown": str(reader_path),
        "reader_pages": str(reader_pages_dir),
        "reading_cleanup_report": str(report_path),
    }


def _split_blocks(markdown: str) -> list[str]:
    return [block for block in re.split(r"\n\s*\n", markdown.replace("\r\n", "\n")) if block.strip()]


def _normalize_block_text(block: str) -> str:
    text = IMAGE_RE.sub("", block)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_navigation_or_header(lowered: str) -> bool:
    if not lowered:
        return False
    if lowered in NAVIGATION_BLOCKS:
        return True
    if HEADER_BLOCK_RE.match(lowered):
        return True
    return any(lowered.startswith(prefix) for prefix in BOILERPLATE_PREFIXES)


def _is_ad_block(lowered: str) -> bool:
    return any(marker in lowered for marker in AD_MARKERS)


def _is_decorative_image_block(block: str, asset_root: Path | None) -> bool:
    if not _is_image_only_block(block):
        return False
    matches = list(IMAGE_RE.finditer(block))
    return all(_is_small_image(match.group(0), asset_root) for match in matches)


def _is_image_only_block(block: str) -> bool:
    matches = list(IMAGE_RE.finditer(block))
    if not matches:
        return False
    text_without_images = IMAGE_RE.sub("", block)
    text_without_images = re.sub(r"<[^>]+>", "", text_without_images).strip()
    return not text_without_images


def _is_small_image(image_markup: str, asset_root: Path | None) -> bool:
    width = _extract_declared_width_percent(image_markup)
    if width is not None and width <= 4:
        return True

    src = _extract_src(image_markup)
    dimensions = _dimensions_from_src(src)
    if dimensions is not None:
        image_width, image_height = dimensions
        if image_width <= 90 and image_height <= 90:
            return True

    if asset_root is not None and src:
        dimensions = _dimensions_from_file(asset_root / src)
        if dimensions is not None:
            image_width, image_height = dimensions
            return image_width <= 90 and image_height <= 90

    return False


def _extract_declared_width_percent(image_markup: str) -> float | None:
    match = WIDTH_RE.search(image_markup)
    return float(match.group("width")) if match else None


def _extract_src(image_markup: str) -> str:
    html_match = HTML_SRC_RE.search(image_markup)
    if html_match:
        return html_match.group("src")
    md_match = MD_SRC_RE.search(image_markup)
    return md_match.group("src") if md_match else ""


def _dimensions_from_src(src: str) -> tuple[int, int] | None:
    match = IMAGE_BOX_RE.search(src)
    if not match:
        return None
    x1 = int(match.group("x1"))
    y1 = int(match.group("y1"))
    x2 = int(match.group("x2"))
    y2 = int(match.group("y2"))
    return abs(x2 - x1), abs(y2 - y1)


def _dimensions_from_file(path: Path) -> tuple[int, int] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        import fitz

        pixmap = fitz.Pixmap(str(path))
        return int(pixmap.width), int(pixmap.height)
    except Exception:
        return None


def _repair_interrupted_words(markdown: str) -> str:
    return re.sub(r"([A-Za-z])-\n\n([a-z])", r"\1\2", markdown)


def _move_sentence_breaking_images(markdown: str) -> str:
    image_block = r"(?P<image>(?:<div\b[^>]*>\s*)?<img\b[^>]*>(?:\s*</div>)?|!\[[^\]]*\]\([^)]+\))"
    pattern = re.compile(rf"(?P<head>[A-Za-z])-\n\n{image_block}\n\n(?P<tail>[a-z][^\n]*)", re.IGNORECASE)
    return pattern.sub(r"\g<head>\g<tail>\n\n\g<image>", markdown)


def _removed(reason: str, block: str, page_number: int) -> dict[str, object]:
    return {
        "page_number": page_number,
        "reason": reason,
        "preview": _normalize_block_text(block)[:120],
    }
