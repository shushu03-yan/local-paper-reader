import json
from pathlib import Path

from src.api.service import read_artifact_payload


def test_read_artifact_payload_returns_binary_metadata_for_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "original.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 test")

    payload = read_artifact_payload("source_pdf", pdf_path)

    assert payload["artifact"] == "source_pdf"
    assert payload["kind"] == "binary"
    assert payload["path"] == str(pdf_path)


def test_read_artifact_payload_returns_json_content(tmp_path: Path) -> None:
    json_path = tmp_path / "structured.json"
    json_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    payload = read_artifact_payload("structured_data", json_path)

    assert payload["kind"] == "json"
    assert payload["content"] == {"ok": True}
