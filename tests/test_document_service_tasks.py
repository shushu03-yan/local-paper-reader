import json
from pathlib import Path

import pytest

from src.api import service as service_module
from src.api.service import DocumentService
from src.config import load_settings


class FakeBackend:
    backend_name = "fake"
    model_name = "fake-model"


def _make_service(tmp_path: Path, monkeypatch) -> DocumentService:
    output_root = tmp_path / "outputs"
    document_root = output_root / "doc-1"
    document_root.mkdir(parents=True)
    paper_path = document_root / "paper.md"
    paper_path.write_text("<!-- page: 1 -->\nAlpha", encoding="utf-8")
    manifest_path = document_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "document_id": "doc-1",
                "status": "completed",
                "pages_total": 1,
                "artifacts": {"paper_markdown": str(paper_path)},
                "page_results": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    settings = load_settings(
        env_path=tmp_path / ".env",
        overrides={
            "OUTPUT_ROOT": str(output_root),
            "DATABASE_PATH": str(tmp_path / "reader.sqlite3"),
            "LLM_BACKEND": "lmstudio",
            "LLM_MODEL_NAME": "fake-model",
        },
    )
    monkeypatch.setattr(service_module, "build_postprocess_backend", lambda settings: FakeBackend())
    return DocumentService(settings=settings)


def test_translate_and_extract_create_independent_queued_tasks(tmp_path: Path, monkeypatch) -> None:
    service = _make_service(tmp_path, monkeypatch)
    calls: list[str] = []

    def fake_translation(**kwargs) -> None:
        calls.append("translation")

    def fake_extraction(**kwargs) -> None:
        calls.append("extraction")

    monkeypatch.setattr(service_module, "run_translation", fake_translation)
    monkeypatch.setattr(service_module, "run_extraction", fake_extraction)

    translate = service.translate_document("doc-1", "zh-CN")
    extract = service.extract_document("doc-1")

    assert translate == {
        "task_id": "translate-doc-1",
        "document_id": "doc-1",
        "target_language": "zh-CN",
        "status": "queued",
    }
    assert extract == {
        "task_id": "extract-doc-1",
        "document_id": "doc-1",
        "status": "queued",
    }
    assert service.get_task("translate-doc-1")["kind"] == "translate"
    assert service.get_task("extract-doc-1")["kind"] == "extract"
    assert service.get_document("doc-1")["document_id"] == "doc-1"


def test_delete_document_removes_database_rows_output_dir_and_incoming_pdf(tmp_path: Path, monkeypatch) -> None:
    service = _make_service(tmp_path, monkeypatch)
    document_root = service.settings.output_root / "doc-1"
    incoming_pdf = service.settings.output_root / "_incoming" / "doc-1.pdf"
    incoming_pdf.write_bytes(b"%PDF-1.7 fake")
    service.repository.upsert_task("ocr-doc-1", "doc-1", "completed", kind="ocr")
    service.repository.upsert_task("translate-doc-1", "doc-1", "completed", kind="translate")

    result = service.delete_document("doc-1")

    assert result == {"document_id": "doc-1", "status": "deleted"}
    assert not document_root.exists()
    assert not incoming_pdf.exists()
    assert service.repository.list_documents() == []
    with pytest.raises(FileNotFoundError):
        service.get_document("doc-1")
