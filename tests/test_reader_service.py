import json
from pathlib import Path

from src.api.service import build_reader_view
from src.services.ocr_pipeline import OutputLayout


def test_build_reader_view_pairs_original_and_translation_by_page(tmp_path: Path) -> None:
    layout = OutputLayout.create(tmp_path, "reader_doc")
    layout.paper_path.write_text(
        "\n".join(
            [
                "<!-- page: 1 -->",
                "# Title",
                "Alpha paragraph.",
                "",
                "<!-- page: 2 -->",
                "Beta paragraph.",
            ]
        ),
        encoding="utf-8",
    )
    translated_path = layout.root / "translated.zh-CN.md"
    translated_path.write_text(
        "\n".join(
            [
                "<!-- page: 1 -->",
                "# 标题",
                "第一段。",
                "",
                "<!-- page: 2 -->",
                "第二段。",
            ]
        ),
        encoding="utf-8",
    )
    layout.manifest_path.write_text(
        json.dumps(
            {
                "document_id": "reader_doc",
                "artifacts": {
                    "paper_markdown": str(layout.paper_path),
                    "translated_markdown": str(translated_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    reader = build_reader_view(layout.manifest_path)

    assert reader["document_id"] == "reader_doc"
    assert reader["translated_available"] is True
    assert len(reader["pages"]) == 2
    assert reader["pages"][0]["page_number"] == 1
    assert "Alpha paragraph." in reader["pages"][0]["original_markdown"]
    assert "第一段。" in reader["pages"][0]["translated_markdown"]
    assert reader["pages"][1]["page_number"] == 2
    assert "Beta paragraph." in reader["pages"][1]["original_markdown"]
    assert "第二段。" in reader["pages"][1]["translated_markdown"]
def test_build_reader_view_prefers_reader_markdown_and_keeps_original(tmp_path: Path) -> None:
    layout = OutputLayout.create(tmp_path, "reader_doc")
    reader_path = layout.root / "reader.md"
    layout.paper_path.write_text(
        "\n".join(
            [
                "<!-- page: 1 -->",
                "Read Online",
                "",
                "ABSTRACT: raw text.",
            ]
        ),
        encoding="utf-8",
    )
    reader_path.write_text(
        "\n".join(
            [
                "<!-- page: 1 -->",
                "ABSTRACT: clean text.",
            ]
        ),
        encoding="utf-8",
    )
    cleanup_report_path = layout.root / "reading_cleanup_report.json"
    cleanup_report_path.write_text('{"pages":[]}', encoding="utf-8")
    layout.manifest_path.write_text(
        json.dumps(
            {
                "document_id": "reader_doc",
                "artifacts": {
                    "paper_markdown": str(layout.paper_path),
                    "reader_markdown": str(reader_path),
                    "reading_cleanup_report": str(cleanup_report_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    reader = build_reader_view(layout.manifest_path)

    assert reader["pages"][0]["original_markdown"].startswith("Read Online")
    assert reader["pages"][0]["reader_markdown"] == "ABSTRACT: clean text."


def test_build_reader_view_generates_reader_markdown_for_legacy_manifest(tmp_path: Path) -> None:
    layout = OutputLayout.create(tmp_path, "legacy_doc")
    layout.paper_path.write_text(
        "\n".join(
            [
                "<!-- page: 1 -->",
                "Read Online",
                "",
                '<div style="text-align: center;"><img src="assets/page_001/icon.jpg" width="3%" /></div>',
                "",
                "ABSTRACT: clean me.",
            ]
        ),
        encoding="utf-8",
    )
    layout.manifest_path.write_text(
        json.dumps(
            {
                "document_id": "legacy_doc",
                "artifacts": {
                    "paper_markdown": str(layout.paper_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    reader = build_reader_view(layout.manifest_path)

    assert reader["pages"][0]["original_markdown"].startswith("Read Online")
    assert reader["pages"][0]["reader_markdown"] == "ABSTRACT: clean me."
    manifest = json.loads(layout.manifest_path.read_text(encoding="utf-8"))
    assert Path(manifest["artifacts"]["reader_markdown"]).exists()
    assert Path(manifest["artifacts"]["reading_cleanup_report"]).exists()
