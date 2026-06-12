from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_settings
from src.services.ocr_pipeline import OCRPipeline, OutputLayout
from src.services.ocr_service import build_ocr_client
from src.services.postprocess_service import (
    build_postprocess_backend,
    run_extraction,
    run_reading_notes,
    run_translation,
)
from src.services.self_check import run_self_check
from src.utils.file_utils import build_document_id
from src.utils.logging_utils import setup_logger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process a PDF through local PaddleOCR-VL.")
    parser.add_argument("input_pdf", nargs="?", help="Path to the input PDF file.")
    parser.add_argument("--output-dir", help="Root output directory.")
    parser.add_argument("--dpi", type=int, help="PDF render DPI.")
    parser.add_argument(
        "--pipeline-version",
        help="PaddleOCRVL pipeline version such as v1, v1.5, or v1.6.",
    )
    parser.add_argument("--device", help="PaddleOCR device override, for example cpu or xpu.")
    parser.add_argument("--engine", help="PaddleOCR engine override, for example transformers.")
    parser.add_argument("--max-concurrency", type=int, help="Maximum parallel OCR requests.")
    parser.add_argument("--resume", action="store_true", help="Skip pages with existing outputs.")
    parser.add_argument("--start-page", type=int, help="1-based start page.")
    parser.add_argument("--end-page", type=int, help="1-based end page.")
    parser.add_argument("--self-check", action="store_true", help="Run environment self-check and exit.")
    parser.add_argument("--translate", action="store_true", help="Run translation postprocess after OCR.")
    parser.add_argument("--extract", action="store_true", help="Run structured extraction postprocess after OCR.")
    parser.add_argument("--reading-notes", action="store_true", help="Run reading notes postprocess after OCR.")
    parser.add_argument("--target-language", help="Override target language for postprocess outputs.")
    parser.add_argument("--glossary", help="Path to a domain glossary used during translation.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    overrides = {
        "PADDLEOCR_PIPELINE_VERSION": args.pipeline_version,
        "PADDLEOCR_DEVICE": args.device,
        "PADDLEOCR_ENGINE": args.engine,
        "PDF_RENDER_DPI": args.dpi,
        "MAX_CONCURRENCY": args.max_concurrency,
        "OUTPUT_ROOT": args.output_dir,
    }
    settings = load_settings(overrides=overrides)

    if args.self_check:
        result = run_self_check(settings)
        print(f"status: {result['status']}")
        print(f"ocr_backend: {result['ocr_backend']['backend']}")
        print(f"ocr_model: {result['ocr_backend']['model']}")
        print(f"pipeline_version: {result['ocr_backend']['pipeline_version']}")
        if "paddle_version" in result["ocr_backend"]:
            print(f"paddle_version: {result['ocr_backend']['paddle_version']}")
        if "base_url" in result["ocr_backend"]:
            print(f"ocr_base_url: {result['ocr_backend']['base_url']}")
        print(f"llm_backend: {result['llm_backend']['backend']}")
        if "status" in result["llm_backend"]:
            print(f"llm_status: {result['llm_backend']['status']}")
        if "error" in result["llm_backend"]:
            print(f"llm_error: {result['llm_backend']['error']}")
        return 0

    if not args.input_pdf:
        parser.error("input_pdf is required unless --self-check is used.")

    pdf_path = Path(args.input_pdf).expanduser().resolve()
    if not pdf_path.exists():
        parser.error(f"Input PDF does not exist: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        parser.error(f"Input file must be a PDF: {pdf_path}")

    preview_document_id = build_document_id(pdf_path)
    preview_layout = OutputLayout.create(settings.output_root, preview_document_id)
    logger = setup_logger(
        name=f"ocr-cli-{preview_document_id}",
        log_file=preview_layout.logs_dir / "run.log",
        level=settings.log_level,
    )

    client = build_ocr_client(settings)

    try:
        logger.info("Checking PaddleOCR backend availability")
        client.ensure_backend_available()
        pipeline = OCRPipeline(
            client=client,
            output_root=settings.output_root,
            logger=logger,
        )
        manifest = pipeline.process(
            pdf_path=pdf_path,
            dpi=settings.pdf_render_dpi,
            document_id=preview_document_id,
            max_concurrency=settings.max_concurrency,
            ocr_retries=settings.ocr_retries,
            resume=args.resume,
            start_page=args.start_page,
            end_page=args.end_page,
        )

        if args.translate or args.extract or args.reading_notes:
            backend = build_postprocess_backend(settings)
            if backend is None:
                raise RuntimeError("LLM postprocess is disabled. Set LLM_BACKEND and LLM_MODEL_NAME first.")
            target_language = args.target_language or settings.target_language
            glossary = _read_text_file(Path(args.glossary).expanduser()) if args.glossary else _read_text_file(settings.glossary_path)
            if args.translate:
                run_translation(
                    document_root=preview_layout.root,
                    backend=backend,
                    target_language=target_language,
                    glossary=glossary,
                )
            if args.extract:
                run_extraction(
                    document_root=preview_layout.root,
                    backend=backend,
                    extraction_profile=settings.extraction_profile,
                )
            if args.reading_notes:
                run_reading_notes(
                    document_root=preview_layout.root,
                    backend=backend,
                    target_language=target_language,
                )
    except Exception as exc:  # noqa: BLE001
        logger.exception("OCR pipeline failed")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"document_id: {manifest['document_id']}")
    print(f"status: {manifest['status']}")
    print(f"pages_total: {manifest['pages_total']}")
    print(f"pages_succeeded: {manifest['pages_succeeded']}")
    print(f"pages_failed: {manifest['pages_failed']}")

    return 0 if manifest["status"] == "completed" else 2


def _read_text_file(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    content = path.read_text(encoding="utf-8").strip()
    return content or None


if __name__ == "__main__":
    raise SystemExit(main())
