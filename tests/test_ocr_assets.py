import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.service import DocumentService
from src.config import Settings
from src.services.ocr_pipeline import OCRPipeline
from src.services.ocr_service import OCRPageContent


class AssetOCRClient:
    backend_name = "fake"
    model_name = "fake-model"
    pipeline_version = "v1.6"
    device = None
    engine = None

    def ensure_backend_available(self) -> None:
        return None

    def ocr_image(self, image_path: Path) -> OCRPageContent:
        asset_dir = image_path.parent / "fake_assets"
        imgs_dir = asset_dir / "imgs"
        imgs_dir.mkdir(parents=True)
        (imgs_dir / "demo.jpg").write_bytes(b"fake-image")
        return OCRPageContent(
            markdown='<div><img src="imgs/demo.jpg" alt="Image" /></div>\n\n$$ x^2 $$',
            asset_dir=asset_dir,
        )


def test_pipeline_copies_ocr_assets_and_rewrites_markdown(tmp_path: Path) -> None:
    pdf_path = tmp_path / "tiny.pdf"
    pdf_path.write_bytes(b"%PDF fake")
    rendered_page = tmp_path / "page_001.png"
    rendered_page.write_bytes(b"png")

    pipeline = OCRPipeline(
        client=AssetOCRClient(),
        output_root=tmp_path / "outputs",
        logger=logging.getLogger("test-assets"),
    )
    layout_manifest = pipeline.process_rendered_pages(
        pdf_path=pdf_path,
        image_paths=[rendered_page],
        dpi=200,
        document_id="doc-assets",
        ocr_retries=0,
        resume=False,
    )
    doc_root = tmp_path / "outputs" / "doc-assets"

    markdown = (doc_root / "ocr_pages" / "page_001.md").read_text(encoding="utf-8")

    assert (doc_root / "assets" / "page_001" / "demo.jpg").read_bytes() == b"fake-image"
    assert 'src="assets/page_001/demo.jpg"' in markdown
    assert layout_manifest["artifacts"]["assets"] == str(doc_root / "assets")


def test_asset_api_serves_document_assets_and_blocks_path_traversal(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    doc_root = output_root / "doc"
    asset_path = doc_root / "assets" / "page_001" / "demo.jpg"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"fake-image")
    (doc_root / "manifest.json").write_text(
        '{"document_id":"doc","status":"completed","pages_total":0,"artifacts":{"assets":"'
        + str(doc_root / "assets").replace("\\", "\\\\")
        + '"},"page_results":[]}',
        encoding="utf-8",
    )
    settings = Settings(output_root=output_root, database_path=output_root / "reader.sqlite3")
    service = DocumentService(settings=settings, ocr_client_factory=lambda: AssetOCRClient())
    client = TestClient(create_app(document_service=service))

    ok = client.get("/documents/doc/assets/assets/page_001/demo.jpg")
    bad = client.get("/documents/doc/assets/../manifest.json")

    assert ok.status_code == 200
    assert ok.content == b"fake-image"
    assert bad.status_code == 404


def test_asset_path_resolution_rejects_prefix_sibling_and_parent_traversal(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    doc_root = output_root / "doc"
    asset_path = doc_root / "assets" / "page_001" / "demo.jpg"
    sibling_path = doc_root / "assets2" / "leak.txt"
    asset_path.parent.mkdir(parents=True)
    sibling_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"fake-image")
    sibling_path.write_text("leak", encoding="utf-8")
    (doc_root / "manifest.json").write_text(
        '{"document_id":"doc","status":"completed","pages_total":0,"artifacts":{"assets":"'
        + str(doc_root / "assets").replace("\\", "\\\\")
        + '"},"page_results":[]}',
        encoding="utf-8",
    )
    settings = Settings(output_root=output_root, database_path=output_root / "reader.sqlite3")
    service = DocumentService(settings=settings, ocr_client_factory=lambda: AssetOCRClient())

    assert service.get_document_asset_path("doc", "assets/page_001/demo.jpg") == asset_path.resolve()
    with pytest.raises(FileNotFoundError):
        service.get_document_asset_path("doc", "assets2/leak.txt")
    with pytest.raises(FileNotFoundError):
        service.get_document_asset_path("doc", "../doc/manifest.json")
