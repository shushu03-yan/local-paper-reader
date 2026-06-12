import json
from pathlib import Path

import pytest

from src.services.repository import DocumentRepository


def test_repository_persists_documents_tasks_pages_artifacts_and_corrections(tmp_path: Path) -> None:
    db_path = tmp_path / "reader.sqlite3"
    repo = DocumentRepository(db_path)
    manifest_path = tmp_path / "doc-1" / "manifest.json"
    manifest_path.parent.mkdir()
    page_image = manifest_path.parent / "pages" / "page_001.png"
    page_markdown = manifest_path.parent / "ocr_pages" / "page_001.md"
    page_raw = manifest_path.parent / "raw" / "page_001.txt"
    page_image.parent.mkdir()
    page_markdown.parent.mkdir()
    page_raw.parent.mkdir()
    page_image.write_bytes(b"png")
    page_markdown.write_text("hello", encoding="utf-8")
    page_raw.write_text("hello", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "document_id": "doc-1",
                "status": "completed",
                "pages_total": 1,
                "created_by": "alice",
                "artifacts": {"paper_markdown": str(manifest_path.parent / "paper.md")},
                "page_results": [
                    {
                        "page_number": 1,
                        "image_path": str(page_image),
                        "markdown_path": str(page_markdown),
                        "raw_path": str(page_raw),
                        "status": "completed",
                        "attempts": 1,
                        "elapsed_seconds": 1.25,
                        "error": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    repo.upsert_task("ocr-doc-1", "doc-1", "queued")
    repo.upsert_manifest(manifest_path)
    repo.save_correction("doc-1", 1, "corrected text")

    reopened = DocumentRepository(db_path)

    assert reopened.get_task("ocr-doc-1")["status"] == "queued"
    assert reopened.list_documents()[0]["document_id"] == "doc-1"
    assert reopened.get_page("doc-1", 1)["markdown_path"] == str(page_markdown)
    assert reopened.list_artifacts("doc-1")["paper_markdown"].endswith("paper.md")
    assert reopened.get_correction("doc-1", 1)["corrected_markdown"] == "corrected text"


def test_repository_reads_legacy_corrections_saved_with_non_local_owner(tmp_path: Path) -> None:
    db_path = tmp_path / "reader.sqlite3"
    repo = DocumentRepository(db_path)
    manifest_path = tmp_path / "doc-legacy" / "manifest.json"
    manifest_path.parent.mkdir()
    page_image = manifest_path.parent / "pages" / "page_001.png"
    page_markdown = manifest_path.parent / "ocr_pages" / "page_001.md"
    page_raw = manifest_path.parent / "raw" / "page_001.txt"
    page_image.parent.mkdir()
    page_markdown.parent.mkdir()
    page_raw.parent.mkdir()
    page_image.write_bytes(b"png")
    page_markdown.write_text("hello", encoding="utf-8")
    page_raw.write_text("hello", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "document_id": "doc-legacy",
                "status": "completed",
                "pages_total": 1,
                "created_by": "alice",
                "artifacts": {"paper_markdown": str(manifest_path.parent / "paper.md")},
                "page_results": [
                    {
                        "page_number": 1,
                        "image_path": str(page_image),
                        "markdown_path": str(page_markdown),
                        "raw_path": str(page_raw),
                        "status": "completed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    repo.upsert_manifest(manifest_path)
    with repo._connect() as conn:
        conn.execute(
            """
            INSERT INTO corrections (document_id, page_number, owner, corrected_markdown)
            VALUES (?, ?, ?, ?)
            """,
            ("doc-legacy", 1, "alice", "legacy corrected text"),
        )

    assert repo.get_correction("doc-legacy", 1)["corrected_markdown"] == "legacy corrected text"


def test_repository_delete_document_removes_indexed_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "reader.sqlite3"
    repo = DocumentRepository(db_path)
    manifest_path = tmp_path / "doc-delete" / "manifest.json"
    manifest_path.parent.mkdir()
    page_image = manifest_path.parent / "pages" / "page_001.png"
    page_markdown = manifest_path.parent / "ocr_pages" / "page_001.md"
    page_raw = manifest_path.parent / "raw" / "page_001.txt"
    page_image.parent.mkdir()
    page_markdown.parent.mkdir()
    page_raw.parent.mkdir()
    page_image.write_bytes(b"png")
    page_markdown.write_text("hello", encoding="utf-8")
    page_raw.write_text("hello", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "document_id": "doc-delete",
                "status": "completed",
                "pages_total": 1,
                "artifacts": {"paper_markdown": str(manifest_path.parent / "paper.md")},
                "page_results": [
                    {
                        "page_number": 1,
                        "image_path": str(page_image),
                        "markdown_path": str(page_markdown),
                        "raw_path": str(page_raw),
                        "status": "completed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    repo.upsert_manifest(manifest_path)
    repo.upsert_task("ocr-doc-delete", "doc-delete", "completed")
    repo.save_correction("doc-delete", 1, "corrected text")

    deleted = repo.delete_document("doc-delete")

    assert deleted is True
    assert repo.list_documents() == []
    assert repo.get_correction("doc-delete", 1) is None
    with pytest.raises(FileNotFoundError):
        repo.get_document("doc-delete")
    with pytest.raises(FileNotFoundError):
        repo.get_task("ocr-doc-delete")


def test_repository_annotation_crud_and_document_delete_cascade(tmp_path: Path) -> None:
    db_path = tmp_path / "reader.sqlite3"
    repo = DocumentRepository(db_path)
    manifest_path = tmp_path / "doc-annotations" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "document_id": "doc-annotations",
                "status": "completed",
                "pages_total": 1,
                "artifacts": {},
                "page_results": [],
            }
        ),
        encoding="utf-8",
    )
    repo.upsert_manifest(manifest_path)

    created = repo.create_annotation(
        document_id="doc-annotations",
        page_number=1,
        target_side="translation",
        block_index=2,
        quote_text="important result",
        note_text="check this later",
        color="yellow",
    )

    assert created["annotation_id"]
    assert created["target_side"] == "translation"
    assert created["block_index"] == 2
    assert repo.list_annotations("doc-annotations", 1) == [created]

    updated = repo.update_annotation(
        "doc-annotations",
        str(created["annotation_id"]),
        note_text="updated note",
        color="green",
    )
    assert updated["note_text"] == "updated note"
    assert updated["color"] == "green"

    assert repo.delete_annotation("doc-annotations", str(created["annotation_id"])) is True
    assert repo.list_annotations("doc-annotations", 1) == []

    second = repo.create_annotation(
        document_id="doc-annotations",
        page_number=1,
        target_side="ocr",
        block_index=0,
        quote_text="Alpha",
        note_text="source note",
        color="blue",
    )
    assert repo.delete_document("doc-annotations") is True
    assert repo.get_annotation("doc-annotations", str(second["annotation_id"])) is None
