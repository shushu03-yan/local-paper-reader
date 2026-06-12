import json
from pathlib import Path

from src.services.ocr_pipeline import OutputLayout
from src.services.postprocess_service import run_extraction, run_translation


class RecordingBackend:
    backend_name = "fake"
    model_name = "fake-model"

    def __init__(self) -> None:
        self.translation_calls: list[str] = []

    def health_check(self) -> dict[str, object]:
        return {"status": "ok"}

    def translate_document(self, markdown: str, target_language: str, glossary: str | None = None) -> str:
        self.translation_calls.append(markdown)
        suffix = f"\nGlossary: {glossary}" if glossary else ""
        return f"[{target_language}]\n{markdown}{suffix}"

    def extract_structured_data(self, markdown: str, extraction_profile: str) -> dict[str, object]:
        return {
            "title": "T",
            "authors": [],
            "abstract": "",
            "methods": [],
            "datasets": [],
            "metrics": [],
            "results": [],
            "limitations": [],
            "tables": [],
            "figures": [],
            "equations": [],
        }

    def build_reading_notes(self, markdown: str, target_language: str) -> dict[str, object]:
        return {"summary": "", "key_terms": [], "open_questions": [], "action_items": []}


def test_translation_runs_page_by_page_and_writes_quality_report(tmp_path: Path) -> None:
    layout = OutputLayout.create(tmp_path, "doc")
    layout.paper_path.write_text(
        "<!-- page: 1 -->\nAlpha\n\n<!-- page: 2 -->\nBeta",
        encoding="utf-8",
    )
    layout.manifest_path.write_text(
        json.dumps({"document_id": "doc", "artifacts": {"paper_markdown": str(layout.paper_path)}}),
        encoding="utf-8",
    )
    backend = RecordingBackend()

    artifacts = run_translation(
        document_root=layout.root,
        backend=backend,
        target_language="zh-CN",
        glossary="Alpha=阿尔法",
    )

    assert len(backend.translation_calls) == 2
    translated = artifacts.translated_markdown.read_text(encoding="utf-8")
    assert "<!-- page: 1 -->" in translated
    assert "<!-- page: 2 -->" in translated
    report = json.loads(artifacts.quality_report.read_text(encoding="utf-8"))
    assert report["page_count_match"] is True
    assert report["missing_translation_pages"] == []


def test_extraction_schema_contains_research_fields(tmp_path: Path) -> None:
    layout = OutputLayout.create(tmp_path, "doc")
    layout.paper_path.write_text("<!-- page: 1 -->\nAlpha", encoding="utf-8")
    layout.manifest_path.write_text(
        json.dumps({"document_id": "doc", "artifacts": {"paper_markdown": str(layout.paper_path)}}),
        encoding="utf-8",
    )

    artifacts = run_extraction(
        document_root=layout.root,
        backend=RecordingBackend(),
        extraction_profile="literature",
    )

    payload = json.loads(artifacts.structured_data.read_text(encoding="utf-8"))
    assert set(payload) >= {
        "title",
        "authors",
        "abstract",
        "methods",
        "datasets",
        "metrics",
        "results",
        "limitations",
        "tables",
        "figures",
        "equations",
    }

