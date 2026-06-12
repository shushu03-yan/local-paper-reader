from __future__ import annotations

import json
import logging
import shutil
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol
from src.services.ocr_service import OCRPageContent
from src.services.reading_cleanup import write_reading_cleanup_artifacts
from src.services.pdf_service import render_pdf_to_images
from src.utils.file_utils import build_document_id, ensure_directory


class OCRClient(Protocol):
    backend_name: str
    model_name: str
    pipeline_version: str
    device: str | None
    engine: str | None

    def ocr_image(self, image_path: Path) -> str | OCRPageContent: ...


@dataclass(slots=True)
class PageResult:
    page_number: int
    image_path: Path
    markdown_path: Path
    raw_path: Path
    status: str
    attempts: int = 1
    elapsed_seconds: float = 0.0
    error: str | None = None


@dataclass(slots=True)
class OutputLayout:
    root: Path
    source_dir: Path
    pages_dir: Path
    ocr_pages_dir: Path
    reader_pages_dir: Path
    raw_dir: Path
    assets_dir: Path
    logs_dir: Path
    paper_path: Path
    reader_path: Path
    paper_json_path: Path
    reading_cleanup_report_path: Path
    manifest_path: Path

    @classmethod
    def create(cls, output_root: Path, document_id: str) -> "OutputLayout":
        root = output_root / document_id
        layout = cls(
            root=root,
            source_dir=root / "source",
            pages_dir=root / "pages",
            ocr_pages_dir=root / "ocr_pages",
            reader_pages_dir=root / "reader_pages",
            raw_dir=root / "raw",
            assets_dir=root / "assets",
            logs_dir=root / "logs",
            paper_path=root / "paper.md",
            reader_path=root / "reader.md",
            paper_json_path=root / "paper.json",
            reading_cleanup_report_path=root / "reading_cleanup_report.json",
            manifest_path=root / "manifest.json",
        )
        for directory in (
            layout.root,
            layout.source_dir,
            layout.pages_dir,
            layout.ocr_pages_dir,
            layout.reader_pages_dir,
            layout.raw_dir,
            layout.assets_dir,
            layout.logs_dir,
        ):
            ensure_directory(directory)
        return layout


def merge_page_markdown(page_markdowns: Mapping[int, str], output_path: Path) -> Path:
    ensure_directory(output_path.parent)
    ordered_pages = []
    for page_number in sorted(page_markdowns):
        ordered_pages.append(f"<!-- page: {page_number} -->\n{page_markdowns[page_number].rstrip()}\n")
    output_path.write_text("\n".join(ordered_pages), encoding="utf-8")
    return output_path


def write_paper_json(
    page_markdowns: Mapping[int, str],
    output_path: Path,
) -> Path:
    ensure_directory(output_path.parent)
    payload = {
        "pages": [
            {
                "page_number": page_number,
                "markdown": page_markdowns[page_number],
            }
            for page_number in sorted(page_markdowns)
        ],
        "combined_markdown": "\n".join(page_markdowns[page] for page in sorted(page_markdowns)),
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def build_manifest(
    *,
    document_id: str,
    source_pdf: Path,
    backend: str,
    model: str,
    pipeline_version: str,
    device: str | None,
    engine: str | None,
    dpi: int,
    started_at: str,
    finished_at: str,
    page_results: list[PageResult],
) -> dict[str, object]:
    succeeded = sum(1 for result in page_results if result.status == "completed")
    failed = sum(1 for result in page_results if result.status == "failed")
    total = len(page_results)

    if total == 0 or succeeded == 0:
        status = "failed"
    elif failed == 0:
        status = "completed"
    else:
        status = "partial"

    page_status = {
        str(result.page_number): result.status
        for result in page_results
    }
    total_seconds = round(
        max(
            0.0,
            datetime.fromisoformat(finished_at.replace("Z", "+00:00")).timestamp()
            - datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp(),
        ),
        3,
    )

    return {
        "document_id": document_id,
        "source_pdf": str(source_pdf),
        "backend": backend,
        "model": model,
        "ocr_backend": backend,
        "ocr_model": model,
        "pipeline_version": pipeline_version,
        "device": device,
        "engine": engine,
        "dpi": dpi,
        "status": status,
        "pages_total": total,
        "pages_succeeded": succeeded,
        "pages_failed": failed,
        "started_at": started_at,
        "finished_at": finished_at,
        "page_status": page_status,
        "timings": {
            "started_at": started_at,
            "finished_at": finished_at,
            "total_seconds": total_seconds,
        },
        "page_results": [
            {
                **asdict(result),
                "image_path": str(result.image_path),
                "markdown_path": str(result.markdown_path),
                "raw_path": str(result.raw_path),
            }
            for result in page_results
        ],
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


PAGE_IMAGE_STEM_RE = re.compile(r"^page_(?P<number>\d+)$")


def _page_number_from_path(image_path: Path) -> int:
    """Return the page number for renderer output named like page_001.png."""
    match = PAGE_IMAGE_STEM_RE.match(image_path.stem)
    if match is None:
        raise ValueError(f"Expected page image filename like page_001.png, got: {image_path.name}")
    return int(match.group("number"))


class OCRPipeline:
    def __init__(
        self,
        client: OCRClient,
        output_root: Path,
        logger: logging.Logger,
    ) -> None:
        self.client = client
        self.output_root = output_root
        self.logger = logger

    def process(
        self,
        pdf_path: Path,
        *,
        dpi: int,
        document_id: str | None = None,
        max_concurrency: int = 1,
        ocr_retries: int = 0,
        resume: bool = False,
        start_page: int | None = None,
        end_page: int | None = None,
    ) -> dict[str, object]:
        started_at = _utc_now()
        document_id = document_id or build_document_id(pdf_path)
        layout = OutputLayout.create(self.output_root, document_id)
        source_pdf = layout.source_dir / "original.pdf"
        shutil.copy2(pdf_path, source_pdf)

        self.logger.info("Rendering PDF pages from %s", pdf_path)
        image_paths = render_pdf_to_images(
            pdf_path=pdf_path,
            output_dir=layout.pages_dir,
            dpi=dpi,
            start_page=start_page,
            end_page=end_page,
        )
        self.logger.info("Rendered %s page image(s)", len(image_paths))
        return self.process_rendered_pages(
            pdf_path=pdf_path,
            image_paths=image_paths,
            dpi=dpi,
            document_id=document_id,
            max_concurrency=max_concurrency,
            ocr_retries=ocr_retries,
            resume=resume,
            started_at=started_at,
            source_pdf=source_pdf,
            layout=layout,
        )

    def process_rendered_pages(
        self,
        pdf_path: Path,
        image_paths: list[Path],
        *,
        dpi: int,
        document_id: str | None = None,
        max_concurrency: int = 1,
        ocr_retries: int = 0,
        resume: bool = False,
        started_at: str | None = None,
        source_pdf: Path | None = None,
        layout: OutputLayout | None = None,
    ) -> dict[str, object]:
        started_at = started_at or _utc_now()
        document_id = document_id or build_document_id(pdf_path)
        layout = layout or OutputLayout.create(self.output_root, document_id)
        source_pdf = source_pdf or layout.source_dir / "original.pdf"
        if pdf_path.exists() and not source_pdf.exists():
            shutil.copy2(pdf_path, source_pdf)
        if max_concurrency <= 1:
            page_results = [
                self._process_single_page(image_path, layout, resume, ocr_retries)
                for image_path in image_paths
            ]
        else:
            page_results = self._process_pages_concurrently(
                image_paths=image_paths,
                layout=layout,
                resume=resume,
                ocr_retries=ocr_retries,
                max_concurrency=max_concurrency,
            )

        page_markdowns = {
            result.page_number: result.markdown_path.read_text(encoding="utf-8")
            for result in page_results
            if result.status == "completed" and result.markdown_path.exists()
        }
        if page_markdowns:
            merge_page_markdown(page_markdowns, layout.paper_path)
            write_paper_json(page_markdowns, layout.paper_json_path)
            reading_artifacts = write_reading_cleanup_artifacts(
                page_markdowns=page_markdowns,
                document_root=layout.root,
                asset_root=layout.root,
            )
        else:
            reading_artifacts = {}

        finished_at = _utc_now()
        manifest = build_manifest(
            document_id=document_id,
            source_pdf=source_pdf,
            backend=self.client.backend_name,
            model=self.client.model_name,
            pipeline_version=self.client.pipeline_version,
            device=self.client.device,
            engine=self.client.engine,
            dpi=dpi,
            started_at=started_at,
            finished_at=finished_at,
            page_results=sorted(page_results, key=lambda result: result.page_number),
        )
        manifest["artifacts"] = {
            "source_pdf": str(source_pdf),
            "paper_markdown": str(layout.paper_path),
            "paper_json": str(layout.paper_json_path),
            "manifest": str(layout.manifest_path),
            "logs": str(layout.logs_dir / "run.log"),
            "assets": str(layout.assets_dir),
            **reading_artifacts,
        }
        layout.manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return manifest

    def _process_pages_concurrently(
        self,
        *,
        image_paths: list[Path],
        layout: OutputLayout,
        resume: bool,
        ocr_retries: int,
        max_concurrency: int,
    ) -> list[PageResult]:
        page_results: list[PageResult] = []
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            futures = {
                executor.submit(
                    self._process_single_page,
                    image_path,
                    layout,
                    resume,
                    ocr_retries,
                ): image_path
                for image_path in image_paths
            }
            for future in as_completed(futures):
                page_results.append(future.result())
        return page_results

    def _process_single_page(
        self,
        image_path: Path,
        layout: OutputLayout,
        resume: bool,
        ocr_retries: int,
    ) -> PageResult:
        page_number = _page_number_from_path(image_path)
        markdown_path = layout.ocr_pages_dir / f"page_{page_number:03d}.md"
        raw_path = layout.raw_dir / f"page_{page_number:03d}.txt"

        if resume and markdown_path.exists() and raw_path.exists():
            self.logger.info("Skipping page %s due to --resume", page_number)
            return PageResult(
                page_number=page_number,
                image_path=image_path,
                markdown_path=markdown_path,
                raw_path=raw_path,
                status="completed",
                attempts=0,
                elapsed_seconds=0.0,
                error=None,
            )

        self.logger.info("OCR started for page %s", page_number)
        start_time = time.perf_counter()
        last_error: str | None = None
        attempts = max(1, ocr_retries + 1)
        for attempt in range(1, attempts + 1):
            content = None
            try:
                ocr_content = self.client.ocr_image(image_path)
                if isinstance(ocr_content, str):
                    content = OCRPageContent(markdown=ocr_content, asset_dir=None)
                else:
                    content = ocr_content
                raw_text = _rewrite_and_copy_assets(
                    markdown=content.markdown,
                    source_asset_dir=content.asset_dir,
                    page_asset_dir=layout.assets_dir / f"page_{page_number:03d}",
                )
                raw_path.write_text(raw_text, encoding="utf-8")
                markdown_path.write_text(raw_text, encoding="utf-8")
                elapsed = round(time.perf_counter() - start_time, 3)
                self.logger.info("OCR completed for page %s on attempt %s", page_number, attempt)
                return PageResult(
                    page_number=page_number,
                    image_path=image_path,
                    markdown_path=markdown_path,
                    raw_path=raw_path,
                    status="completed",
                    attempts=attempt,
                    elapsed_seconds=elapsed,
                    error=None,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                self.logger.exception(
                    "OCR failed for page %s on attempt %s",
                    page_number,
                    attempt,
                )
            finally:
                if content is not None and content.asset_dir is not None and content.asset_dir.exists():
                    shutil.rmtree(content.asset_dir, ignore_errors=True)

        return PageResult(
            page_number=page_number,
            image_path=image_path,
            markdown_path=markdown_path,
            raw_path=raw_path,
            status="failed",
            attempts=attempts,
            elapsed_seconds=round(time.perf_counter() - start_time, 3),
            error=last_error,
        )


IMG_SRC_RE = re.compile(r'(?P<prefix>\bsrc=["\'])(?P<src>[^"\']+)(?P<suffix>["\'])')
MD_IMG_RE = re.compile(r'(?P<prefix>!\[[^\]]*\]\()(?P<src>[^)]+)(?P<suffix>\))')


def _copy_asset_file(source_asset_dir: Path, src: str, page_asset_dir: Path) -> str:
    clean_src = src.split("#", 1)[0].split("?", 1)[0].replace("\\", "/")
    if "://" in clean_src or clean_src.startswith("data:") or clean_src.startswith("/"):
        return src
    candidates = [
        source_asset_dir / clean_src,
        source_asset_dir / "imgs" / Path(clean_src).name,
    ]
    source_file = next((candidate for candidate in candidates if candidate.exists() and candidate.is_file()), None)
    if source_file is None:
        return src
    ensure_directory(page_asset_dir)
    target = page_asset_dir / source_file.name
    shutil.copy2(source_file, target)
    return f"{page_asset_dir.parent.name}/{page_asset_dir.name}/{target.name}"


def _rewrite_and_copy_assets(
    *,
    markdown: str,
    source_asset_dir: Path | None,
    page_asset_dir: Path,
) -> str:
    if source_asset_dir is None or not source_asset_dir.exists():
        return markdown

    def replace_html(match: re.Match[str]) -> str:
        rewritten = _copy_asset_file(source_asset_dir, match.group("src"), page_asset_dir)
        return f"{match.group('prefix')}{rewritten}{match.group('suffix')}"

    def replace_markdown(match: re.Match[str]) -> str:
        rewritten = _copy_asset_file(source_asset_dir, match.group("src"), page_asset_dir)
        return f"{match.group('prefix')}{rewritten}{match.group('suffix')}"

    rewritten_markdown = IMG_SRC_RE.sub(replace_html, markdown)
    return MD_IMG_RE.sub(replace_markdown, rewritten_markdown)
