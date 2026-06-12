from __future__ import annotations

from pathlib import Path

import fitz

from src.utils.file_utils import ensure_directory


MAX_DPI = 600
MAX_PIXEL_AREA = 100_000_000


def render_pdf_to_images(
    pdf_path: Path,
    output_dir: Path,
    *,
    dpi: int = 200,
    start_page: int | None = None,
    end_page: int | None = None,
) -> list[Path]:
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {pdf_path}")
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if dpi < 1 or dpi > MAX_DPI:
        raise ValueError(f"dpi must be between 1 and {MAX_DPI}.")

    ensure_directory(output_dir)

    doc = fitz.open(pdf_path)
    try:
        page_total = len(doc)
        if page_total == 0:
            raise ValueError(f"PDF contains no pages: {pdf_path}")

        start_index = max(1, start_page or 1)
        end_index = min(page_total, end_page or page_total)
        if start_index > end_index:
            raise ValueError("start_page cannot be greater than end_page")

        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        image_paths: list[Path] = []

        for page_number in range(start_index, end_index + 1):
            page = doc[page_number - 1]
            pixel_area = (page.rect.width * zoom) * (page.rect.height * zoom)
            if pixel_area > MAX_PIXEL_AREA:
                raise ValueError(
                    f"Rendered page {page_number} would exceed the {MAX_PIXEL_AREA} pixel limit."
                )
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image_path = output_dir / f"page_{page_number:03d}.png"
            pixmap.save(image_path)
            image_paths.append(image_path)

        return image_paths
    finally:
        doc.close()
