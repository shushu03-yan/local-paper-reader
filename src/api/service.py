from __future__ import annotations

import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.config import Settings
from src.services.ocr_pipeline import OCRPipeline, OutputLayout
from src.services.ocr_service import build_ocr_client
from src.services.postprocess_service import (
    build_postprocess_backend,
    run_extraction,
    run_translation,
)
from src.services.reading_cleanup import write_reading_cleanup_artifacts
from src.services.repository import DocumentRepository
from src.utils.file_utils import build_document_id, ensure_directory
from src.utils.logging_utils import setup_logger
from src.utils.markdown_utils import split_markdown_pages


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    document_id: str
    status: str
    error: str | None = None


class DocumentService:
    def __init__(
        self,
        *,
        settings: Settings,
        ocr_client_factory: Callable[[], object] | None = None,
    ) -> None:
        self.settings = settings
        self._ocr_client_factory = ocr_client_factory or self._default_ocr_client_factory
        self.repository = DocumentRepository(self.settings.database_path)
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, self.settings.max_concurrency),
            thread_name_prefix="paper-reader-worker",
        )
        ensure_directory(self.settings.output_root)
        ensure_directory(self.settings.output_root / "_incoming")
        self._index_existing_outputs()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _default_ocr_client_factory(self) -> object:
        return build_ocr_client(self.settings)

    def _index_existing_outputs(self) -> None:
        for manifest_path in self.settings.output_root.glob("*/manifest.json"):
            try:
                self.repository.upsert_manifest(manifest_path)
            except Exception:
                continue

    def submit_document(self, filename: str, content: bytes) -> dict[str, object]:
        source_name = Path(filename).name
        if not source_name.lower().endswith(".pdf"):
            raise ValueError("Only PDF uploads are supported.")

        document_id = build_document_id(Path(source_name))
        task_id = f"ocr-{document_id}"
        incoming_path = self.settings.output_root / "_incoming" / f"{document_id}.pdf"
        incoming_path.write_bytes(content)

        with self._lock:
            self._tasks[task_id] = TaskRecord(
                task_id=task_id,
                document_id=document_id,
                status="queued",
            )
        self.repository.upsert_task(task_id, document_id, "queued", kind="ocr")

        self._executor.submit(self._run_document_pipeline, document_id, incoming_path)
        return {"task_id": task_id, "document_id": document_id, "status": "queued"}

    def _run_document_pipeline(self, document_id: str, pdf_path: Path) -> None:
        self._set_status(document_id, "running", task_id=f"ocr-{document_id}")
        layout = OutputLayout.create(self.settings.output_root, document_id)
        logger = setup_logger(
            name=f"api-ocr-{document_id}",
            log_file=layout.logs_dir / "run.log",
            level=self.settings.log_level,
        )
        try:
            client = self._ocr_client_factory()
            client.ensure_backend_available()
            pipeline = OCRPipeline(
                client=client,
                output_root=self.settings.output_root,
                logger=logger,
            )
            manifest = pipeline.process(
                pdf_path=pdf_path,
                dpi=self.settings.pdf_render_dpi,
                document_id=document_id,
                max_concurrency=self.settings.max_concurrency,
                ocr_retries=self.settings.ocr_retries,
                resume=False,
            )
            layout.manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.repository.upsert_manifest(layout.manifest_path)
            self._set_status(
                document_id,
                str(manifest.get("status", "completed")),
                task_id=f"ocr-{document_id}",
            )
        except Exception as exc:  # noqa: BLE001
            self._set_status(document_id, "failed", str(exc), task_id=f"ocr-{document_id}")
            logger.exception("Document pipeline failed")

    def list_documents(self) -> list[dict[str, object]]:
        return self.repository.list_documents()

    def get_task(self, task_id: str) -> dict[str, object]:
        return self.repository.get_task(task_id)

    def get_document(self, document_id: str) -> dict[str, object]:
        manifest = self._read_manifest(document_id)
        task = self._latest_task_for_document(document_id)
        if manifest is None and task is None:
            document = self.repository.get_document(document_id)
            manifest_path = Path(str(document.get("manifest_path") or ""))
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            else:
                return document
        base = manifest or {"document_id": document_id, "artifacts": {}}
        if task is not None:
            base["task_id"] = task.task_id
            base["status"] = task.status
            if task.error:
                base["task_error"] = task.error
        return base

    def list_pages(self, document_id: str) -> list[dict[str, object]]:
        manifest = self._require_manifest(document_id)
        return list(manifest.get("page_results", []))

    def list_artifacts(self, document_id: str) -> dict[str, object]:
        manifest = self._require_manifest(document_id)
        return dict(manifest.get("artifacts", {}))

    def get_reader_view(self, document_id: str) -> dict[str, object]:
        self.repository.get_document(document_id)
        return build_reader_view(self._manifest_path(document_id), self.repository)

    def read_artifact(self, document_id: str, artifact_name: str) -> dict[str, object]:
        artifacts = self.list_artifacts(document_id)
        if artifact_name not in artifacts:
            raise FileNotFoundError(f"Unknown artifact: {artifact_name}")
        artifact_path = Path(str(artifacts[artifact_name]))
        return read_artifact_payload(
            artifact_name,
            artifact_path,
            document_root=self.settings.output_root / document_id,
        )

    def list_page_annotations(self, document_id: str, page_number: int) -> list[dict[str, object]]:
        self.repository.get_document(document_id)
        return self.repository.list_annotations(document_id, page_number)

    def create_annotation(
        self,
        document_id: str,
        page_number: int,
        target_side: str,
        block_index: int,
        quote_text: str,
        note_text: str,
        color: str,
    ) -> dict[str, object]:
        _validate_annotation_input(target_side, block_index)
        return self.repository.create_annotation(
            document_id=document_id,
            page_number=page_number,
            target_side=target_side,
            block_index=block_index,
            quote_text=quote_text.strip(),
            note_text=note_text.strip(),
            color=color.strip() or "yellow",
        )

    def update_annotation(
        self,
        document_id: str,
        annotation_id: str,
        note_text: str,
        color: str,
    ) -> dict[str, object]:
        return self.repository.update_annotation(
            document_id,
            annotation_id,
            note_text=note_text.strip(),
            color=color.strip() or "yellow",
        )

    def delete_annotation(self, document_id: str, annotation_id: str) -> dict[str, object]:
        deleted = self.repository.delete_annotation(document_id, annotation_id)
        if not deleted:
            raise FileNotFoundError(f"Unknown annotation: {annotation_id}")
        return {"annotation_id": annotation_id, "status": "deleted"}

    def delete_document(self, document_id: str) -> dict[str, object]:
        self.repository.get_document(document_id)
        self._remove_document_files(document_id)
        deleted = self.repository.delete_document(document_id)
        if not deleted:
            raise FileNotFoundError(f"Unknown document: {document_id}")
        with self._lock:
            for task_id in [
                task_id
                for task_id, record in self._tasks.items()
                if record.document_id == document_id
            ]:
                del self._tasks[task_id]
        return {"document_id": document_id, "status": "deleted"}

    def translate_document(
        self,
        document_id: str,
        target_language: str,
        glossary: str | None = None,
    ) -> dict[str, object]:
        self._require_manifest(document_id)
        backend = build_postprocess_backend(self.settings)
        if backend is None:
            raise RuntimeError("LLM postprocess backend is disabled.")

        task_id = f"translate-{document_id}"
        task, created = self._queue_task_if_idle(task_id, document_id, "translate")
        if not created:
            return {
                "task_id": task.task_id,
                "document_id": document_id,
                "target_language": target_language,
                "status": task.status,
            }
        self._executor.submit(self._run_translation, document_id, target_language, glossary)
        return {
            "task_id": task.task_id,
            "document_id": document_id,
            "target_language": target_language,
            "status": task.status,
        }

    def _run_translation(
        self,
        document_id: str,
        target_language: str,
        glossary: str | None,
    ) -> None:
        task_id = f"translate-{document_id}"
        try:
            self._set_status(document_id, "running", task_id=task_id)
            backend = build_postprocess_backend(self.settings)
            if backend is None:
                raise RuntimeError("LLM postprocess backend is disabled.")
            run_translation(
                document_root=self.settings.output_root / document_id,
                backend=backend,
                target_language=target_language,
                glossary=glossary,
            )
            self.repository.upsert_manifest(self._manifest_path(document_id))
            self._set_status(document_id, "completed", task_id=task_id)
        except Exception as exc:  # noqa: BLE001
            self._set_status(document_id, "postprocess_failed", str(exc), task_id=task_id)

    def extract_document(self, document_id: str) -> dict[str, object]:
        self._require_manifest(document_id)
        backend = build_postprocess_backend(self.settings)
        if backend is None:
            raise RuntimeError("LLM postprocess backend is disabled.")
        task_id = f"extract-{document_id}"
        task, created = self._queue_task_if_idle(task_id, document_id, "extract")
        if not created:
            return {"task_id": task.task_id, "document_id": document_id, "status": task.status}
        self._executor.submit(self._run_extraction, document_id)
        return {"task_id": task.task_id, "document_id": document_id, "status": task.status}

    def _run_extraction(self, document_id: str) -> None:
        task_id = f"extract-{document_id}"
        try:
            self._set_status(document_id, "running", task_id=task_id)
            backend = build_postprocess_backend(self.settings)
            if backend is None:
                raise RuntimeError("LLM postprocess backend is disabled.")
            run_extraction(
                document_root=self.settings.output_root / document_id,
                backend=backend,
                extraction_profile=self.settings.extraction_profile,
            )
            self.repository.upsert_manifest(self._manifest_path(document_id))
            self._set_status(document_id, "completed", task_id=task_id)
        except Exception as exc:  # noqa: BLE001
            self._set_status(document_id, "failed", str(exc), task_id=task_id)

    def get_page_detail(
        self,
        document_id: str,
        page_number: int,
    ) -> dict[str, object]:
        page = self.repository.get_page(document_id, page_number)
        original = _read_text_path(page.get("markdown_path"))
        manifest = self._ensure_reader_artifacts(self._require_manifest(document_id))
        artifacts = dict(manifest.get("artifacts", {}))
        reader_pages = {}
        reader_path_value = artifacts.get("reader_markdown")
        if reader_path_value:
            reader_path = _resolve_document_path(
                reader_path_value,
                self.settings.output_root / document_id,
                artifact_name="reader_markdown",
                require_exists=False,
            )
            if reader_path is not None and reader_path.exists():
                reader_pages = split_markdown_pages(reader_path.read_text(encoding="utf-8"))
        translated_pages = {}
        translated_path_value = artifacts.get("translated_markdown")
        if translated_path_value:
            translated_path = _resolve_document_path(
                translated_path_value,
                self.settings.output_root / document_id,
                artifact_name="translated_markdown",
                require_exists=False,
            )
            if translated_path is not None and translated_path.exists():
                translated_pages = split_markdown_pages(translated_path.read_text(encoding="utf-8"))
        correction = self.repository.get_correction(document_id, page_number)
        return {
            "document_id": document_id,
            "page_number": page_number,
            "status": page.get("status"),
            "original_markdown": original,
            "reader_markdown": reader_pages.get(page_number, original),
            "translated_markdown": translated_pages.get(page_number, ""),
            "corrected_markdown": correction.get("corrected_markdown") if correction else None,
            "image_path": page.get("image_path"),
            "image_url": f"/documents/{document_id}/pages/{page_number}/image",
            "asset_base_url": f"/documents/{document_id}/assets/",
            "annotations": self.repository.list_annotations(document_id, page_number),
            "error": page.get("error"),
        }

    def get_page_image_path(self, document_id: str, page_number: int) -> Path:
        page = self.repository.get_page(document_id, page_number)
        image_path = Path(str(page.get("image_path") or ""))
        if not image_path.exists():
            raise FileNotFoundError(f"Page image not found: {document_id} page {page_number}")
        return image_path

    def get_document_asset_path(
        self,
        document_id: str,
        asset_path: str,
    ) -> Path:
        self.repository.get_document(document_id)
        document_root = (self.settings.output_root / document_id).resolve()
        assets_root = (document_root / "assets").resolve()
        normalized = asset_path.replace("\\", "/").lstrip("/")
        candidate = (document_root / normalized).resolve()
        if not _is_relative_to(candidate, assets_root):
            raise FileNotFoundError(f"Asset not found: {asset_path}")
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f"Asset not found: {asset_path}")
        return candidate

    def save_page_correction(
        self,
        document_id: str,
        page_number: int,
        corrected_markdown: str,
    ) -> dict[str, object]:
        correction = self.repository.save_correction(document_id, page_number, corrected_markdown)
        correction_path = self.settings.output_root / document_id / "corrections" / f"page_{page_number:03d}.md"
        ensure_directory(correction_path.parent)
        correction_path.write_text(corrected_markdown, encoding="utf-8")
        return correction

    def _manifest_path(self, document_id: str) -> Path:
        return self.settings.output_root / document_id / "manifest.json"

    def _remove_document_files(self, document_id: str) -> None:
        output_root = self.settings.output_root.resolve()
        document_root = (self.settings.output_root / document_id).resolve()
        incoming_pdf = (self.settings.output_root / "_incoming" / f"{document_id}.pdf").resolve()

        if _is_relative_to(document_root, output_root) and document_root.exists():
            shutil.rmtree(document_root)
        if _is_relative_to(incoming_pdf, output_root) and incoming_pdf.exists():
            incoming_pdf.unlink()

    def _read_manifest(self, document_id: str) -> dict[str, object] | None:
        manifest_path = self._manifest_path(document_id)
        if not manifest_path.exists():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def _require_manifest(self, document_id: str) -> dict[str, object]:
        self.repository.get_document(document_id)
        manifest = self._read_manifest(document_id)
        if manifest is None:
            raise FileNotFoundError(f"Manifest not found for {document_id}")
        return manifest

    def _ensure_reader_artifacts(self, manifest: dict[str, object]) -> dict[str, object]:
        return ensure_reader_artifacts(self._manifest_path(str(manifest.get("document_id"))), manifest)

    def _set_status(
        self,
        document_id: str,
        status: str,
        error: str | None = None,
        *,
        task_id: str | None = None,
    ) -> None:
        if task_id is not None:
            self.repository.upsert_task(task_id, document_id, status, error=error)
        with self._lock:
            record_key = task_id or f"task-{document_id}"
            record = self._tasks.get(record_key)
            if record is None:
                record = TaskRecord(
                    task_id=record_key,
                    document_id=document_id,
                    status=status,
                    error=error,
                )
                self._tasks[record_key] = record
                return
            record.status = status
            record.error = error

    def _queue_task_if_idle(self, task_id: str, document_id: str, kind: str) -> tuple[TaskRecord, bool]:
        active_statuses = {"queued", "running"}
        with self._lock:
            for record in self._tasks.values():
                if (
                    record.document_id == document_id
                    and record.task_id.startswith(f"{kind}-")
                    and record.status in active_statuses
                ):
                    return record, False
            active = self.repository.active_task_for_document_kind(document_id, kind)
            if active is not None:
                return (
                    TaskRecord(
                        task_id=str(active["task_id"]),
                        document_id=str(active["document_id"]),
                        status=str(active["status"]),
                        error=active.get("error"),
                    ),
                    False,
                )
            record = TaskRecord(task_id=task_id, document_id=document_id, status="queued")
            self._tasks[task_id] = record
            self.repository.upsert_task(task_id, document_id, "queued", kind=kind)
            return record, True

    def _latest_task_for_document(self, document_id: str) -> TaskRecord | None:
        with self._lock:
            records = [
                record
                for record in self._tasks.values()
                if record.document_id == document_id
            ]
        if not records:
            task = self.repository.latest_task_for_document(document_id)
            if task is None:
                return None
            return TaskRecord(
                task_id=str(task["task_id"]),
                document_id=str(task["document_id"]),
                status=str(task["status"]),
                error=task.get("error"),
            )
        active_statuses = {"queued", "running"}
        active = [record for record in records if record.status in active_statuses]
        return (active or records)[-1]


def _read_text_path(path_value: object) -> str:
    path = Path(str(path_value or ""))
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_annotation_input(target_side: str, block_index: int) -> None:
    if target_side not in {"ocr", "translation"}:
        raise ValueError("target_side must be 'ocr' or 'translation'.")
    if block_index < 0:
        raise ValueError("block_index must be non-negative.")


def read_artifact_payload(
    artifact_name: str,
    artifact_path: Path,
    *,
    document_root: Path | None = None,
) -> dict[str, object]:
    artifact_path = artifact_path.resolve()
    if document_root is not None:
        artifact_path = _resolve_document_path(
            artifact_path,
            document_root,
            artifact_name=artifact_name,
            require_exists=True,
        )
    if not artifact_path.exists() or not artifact_path.is_file():
        raise FileNotFoundError(f"Artifact not found: {artifact_name}")
    suffix = artifact_path.suffix.lower()
    if suffix == ".json":
        return {
            "artifact": artifact_name,
            "kind": "json",
            "content": json.loads(artifact_path.read_text(encoding="utf-8")),
        }
    if suffix in {".md", ".txt", ".log"}:
        return {
            "artifact": artifact_name,
            "kind": "text",
            "content": artifact_path.read_text(encoding="utf-8"),
        }
    return {
        "artifact": artifact_name,
        "kind": "binary",
        "path": str(artifact_path),
    }


def build_reader_view(
    manifest_path: Path,
    repository: DocumentRepository | None = None,
) -> dict[str, object]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = ensure_reader_artifacts(
        manifest_path,
        json.loads(manifest_path.read_text(encoding="utf-8")),
    )
    artifacts = manifest.get("artifacts", {})
    paper_path = _resolve_document_path(
        artifacts.get("paper_markdown", ""),
        manifest_path.parent,
        artifact_name="paper_markdown",
        require_exists=True,
    )
    reader_path_value = artifacts.get("reader_markdown")
    reader_path = (
        _resolve_document_path(
            reader_path_value,
            manifest_path.parent,
            artifact_name="reader_markdown",
            require_exists=False,
        )
        if reader_path_value
        else None
    )
    translated_path_value = artifacts.get("translated_markdown")
    translated_path = (
        _resolve_document_path(
            translated_path_value,
            manifest_path.parent,
            artifact_name="translated_markdown",
            require_exists=False,
        )
        if translated_path_value
        else None
    )

    original_pages = split_markdown_pages(paper_path.read_text(encoding="utf-8"))
    reader_pages = (
        split_markdown_pages(reader_path.read_text(encoding="utf-8"))
        if reader_path is not None and reader_path.exists()
        else original_pages
    )
    translated_pages = (
        split_markdown_pages(translated_path.read_text(encoding="utf-8"))
        if translated_path is not None and translated_path.exists()
        else {}
    )

    page_numbers = sorted(set(original_pages) | set(reader_pages) | set(translated_pages))
    pages = [
        {
            "page_number": page_number,
            "original_markdown": original_pages.get(page_number, ""),
            "reader_markdown": reader_pages.get(page_number, original_pages.get(page_number, "")),
            "translated_markdown": translated_pages.get(page_number, ""),
            "corrected_markdown": (
                correction.get("corrected_markdown")
                if repository is not None
                and (
                    correction := repository.get_correction(
                        str(manifest.get("document_id")),
                        page_number,
                    )
                )
                else None
            ),
            "image_url": f"/documents/{manifest.get('document_id')}/pages/{page_number}/image",
            "asset_base_url": f"/documents/{manifest.get('document_id')}/assets/",
        }
        for page_number in page_numbers
    ]

    return {
        "document_id": manifest.get("document_id"),
        "translated_available": bool(translated_pages),
        "pages": pages,
    }


def ensure_reader_artifacts(manifest_path: Path, manifest: dict[str, object]) -> dict[str, object]:
    artifacts = dict(manifest.get("artifacts", {}))
    reader_path_value = artifacts.get("reader_markdown")
    report_path_value = artifacts.get("reading_cleanup_report")
    reader_path = (
        _resolve_document_path(
            reader_path_value,
            manifest_path.parent,
            artifact_name="reader_markdown",
            require_exists=False,
        )
        if reader_path_value
        else None
    )
    report_path = (
        _resolve_document_path(
            report_path_value,
            manifest_path.parent,
            artifact_name="reading_cleanup_report",
            require_exists=False,
        )
        if report_path_value
        else None
    )
    if reader_path is not None and reader_path.exists() and report_path is not None and report_path.exists():
        return manifest

    paper_path = _resolve_document_path(
        artifacts.get("paper_markdown", ""),
        manifest_path.parent,
        artifact_name="paper_markdown",
        require_exists=False,
    )
    if paper_path is None or not paper_path.exists():
        return manifest

    page_markdowns = split_markdown_pages(paper_path.read_text(encoding="utf-8"))
    if not page_markdowns:
        return manifest

    artifacts.update(
        write_reading_cleanup_artifacts(
            page_markdowns=page_markdowns,
            document_root=manifest_path.parent,
            asset_root=manifest_path.parent,
        )
    )
    manifest["artifacts"] = artifacts
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _resolve_document_path(
    path_value: object,
    document_root: Path,
    *,
    artifact_name: str,
    require_exists: bool,
) -> Path | None:
    if path_value is None or str(path_value).strip() == "":
        if require_exists:
            raise FileNotFoundError(f"Artifact not found: {artifact_name}")
        return None
    root = document_root.resolve()
    candidate = Path(str(path_value)).resolve()
    if not _is_relative_to(candidate, root):
        raise FileNotFoundError(f"Artifact not found: {artifact_name}")
    if require_exists and (not candidate.exists() or not candidate.is_file()):
        raise FileNotFoundError(f"Artifact not found: {artifact_name}")
    return candidate
