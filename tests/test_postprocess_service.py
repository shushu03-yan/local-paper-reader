import json
from pathlib import Path

from src.services.ocr_pipeline import OutputLayout
from src.services.postprocess_service import ResearchArtifacts, run_postprocess


class FakePostprocessBackend:
    backend_name = "fake-lmstudio"
    model_name = "fake-model"

    def health_check(self) -> dict[str, object]:
        return {"status": "ok"}

    def translate_document(self, markdown: str, target_language: str) -> str:
        return f"[{target_language}]\n{markdown}"

    def extract_structured_data(
        self,
        markdown: str,
        extraction_profile: str,
    ) -> dict[str, object]:
        return {
            "profile": extraction_profile,
            "sections": ["title", "results"],
            "char_count": len(markdown),
        }

    def build_reading_notes(
        self,
        markdown: str,
        target_language: str,
    ) -> dict[str, object]:
        return {
            "language": target_language,
            "notes": ["Key finding", "Method detail"],
            "source_preview": markdown.splitlines()[0],
        }


def test_run_postprocess_writes_artifacts_and_updates_manifest(tmp_path: Path) -> None:
    layout = OutputLayout.create(tmp_path, "demo_doc")
    layout.paper_path.write_text("<!-- page: 1 -->\nHello world", encoding="utf-8")
    manifest_path = layout.manifest_path
    manifest_path.write_text(
        json.dumps(
            {
                "document_id": "demo_doc",
                "status": "completed",
                "artifacts": {
                    "paper_markdown": str(layout.paper_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    artifacts = run_postprocess(
        document_root=layout.root,
        backend=FakePostprocessBackend(),
        target_language="zh-CN",
        extraction_profile="literature",
    )

    assert artifacts == ResearchArtifacts(
        translated_markdown=layout.root / "translated.zh-CN.md",
        structured_data=layout.root / "structured.json",
        reading_notes=layout.root / "reading_notes.json",
        quality_report=layout.root / "quality_report.json",
    )
    translated = artifacts.translated_markdown.read_text(encoding="utf-8")
    assert translated.startswith("<!-- page: 1 -->")
    assert "[zh-CN]" in translated
    assert json.loads(artifacts.structured_data.read_text(encoding="utf-8"))["profile"] == "literature"
    assert json.loads(artifacts.reading_notes.read_text(encoding="utf-8"))["language"] == "zh-CN"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["postprocess_backend"] == "fake-lmstudio"
    assert manifest["target_language"] == "zh-CN"
    assert "translated_markdown" in manifest["artifacts"]
    assert "structured_data" in manifest["artifacts"]
    assert "reading_notes" in manifest["artifacts"]
