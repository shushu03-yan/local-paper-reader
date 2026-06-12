from io import BytesIO

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import Settings


class FakeDocumentService:
    settings = Settings(
        ocr_backend="lmstudio",
        lmstudio_ocr_model_name="fake-ocr-model",
        llm_backend="disabled",
    )

    def list_documents(self) -> list[dict[str, object]]:
        return [{"document_id": "doc-1", "status": "completed"}]

    def submit_document(self, filename: str, content: bytes) -> dict[str, object]:
        assert filename == "paper.pdf"
        assert content.startswith(b"%PDF")
        return {
            "task_id": "task-1",
            "document_id": "doc-1",
            "status": "queued",
        }

    def get_document(self, document_id: str) -> dict[str, object]:
        return {
            "document_id": document_id,
            "status": "completed",
            "artifacts": {"paper_markdown": "outputs/doc-1/paper.md"},
        }

    def list_pages(self, document_id: str) -> list[dict[str, object]]:
        return [
            {"page_number": 1, "status": "completed"},
            {"page_number": 2, "status": "completed"},
        ]

    def list_artifacts(self, document_id: str) -> dict[str, object]:
        return {
            "paper_markdown": "outputs/doc-1/paper.md",
            "translated_markdown": "outputs/doc-1/translated.zh-CN.md",
            "source_pdf": "outputs/doc-1/source/original.pdf",
        }

    def translate_document(
        self,
        document_id: str,
        target_language: str,
        glossary: str | None = None,
    ) -> dict[str, object]:
        return {
            "document_id": document_id,
            "target_language": target_language,
            "status": "completed",
        }

    def get_reader_view(self, document_id: str) -> dict[str, object]:
        return {
            "document_id": document_id,
            "translated_available": True,
            "pages": [
                {
                    "page_number": 1,
                    "original_markdown": "# Original\nAlpha",
                    "translated_markdown": "# Translation\nAlpha CN",
                }
            ],
        }

    def read_artifact(self, document_id: str, artifact_name: str) -> dict[str, object]:
        if artifact_name == "source_pdf":
            return {
                "artifact": artifact_name,
                "kind": "binary",
                "path": "outputs/doc-1/source/original.pdf",
            }
        return {
            "artifact": artifact_name,
            "kind": "text",
            "content": "dummy",
        }

    def delete_document(self, document_id: str) -> dict[str, object]:
        return {"document_id": document_id, "status": "deleted"}


def test_api_routes_expose_document_workflow() -> None:
    client = TestClient(create_app(document_service=FakeDocumentService()))

    upload = BytesIO(b"%PDF-1.7 fake")
    response = client.post(
        "/documents",
        files={"file": ("paper.pdf", upload, "application/pdf")},
    )

    assert response.status_code == 202
    assert response.json()["task_id"] == "task-1"

    assert client.get("/documents/doc-1").json()["status"] == "completed"
    assert len(client.get("/documents/doc-1/pages").json()["pages"]) == 2
    assert "translated_markdown" in client.get("/documents/doc-1/artifacts").json()["artifacts"]
    assert client.get("/documents/doc-1/reader").json()["translated_available"] is True
    assert client.get("/documents/doc-1/artifacts/source_pdf").json()["kind"] == "binary"

    translate_response = client.post(
        "/documents/doc-1/translate",
        json={"target_language": "zh-CN"},
    )
    assert translate_response.status_code == 202
    assert translate_response.json()["target_language"] == "zh-CN"

    delete_response = client.delete("/documents/doc-1")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"document_id": "doc-1", "status": "deleted"}


def test_root_page_mentions_bilingual_reader() -> None:
    client = TestClient(create_app(document_service=FakeDocumentService()))

    response = client.get("/")

    assert response.status_code == 200
    assert "Local Paper Reader" in response.text
    assert "OCR 识别文本" in response.text
    assert "双语翻译对照" in response.text


def test_mathjax_chtml_font_is_served_from_static_vendor_assets() -> None:
    client = TestClient(create_app(document_service=FakeDocumentService()))

    response = client.get("/static/vendor/mathjax/output/chtml/fonts/woff-v2/MathJax_Main-Regular.woff")

    assert response.status_code == 200
    assert response.content.startswith(b"wOFF")


def test_health_returns_misconfigured_llm_status_without_500(monkeypatch) -> None:
    from src.services import self_check as self_check_module

    class FakeOCRClient:
        backend_name = "fake-ocr"
        model_name = "fake-ocr-model"
        pipeline_version = "v1.6"
        base_url = "http://127.0.0.1:6611/v1"

        def ensure_backend_available(self) -> None:
            return None

    service = FakeDocumentService()
    service.settings = Settings(
        ocr_backend="lmstudio",
        lmstudio_ocr_model_name="fake-ocr-model",
        llm_backend="deepseek",
        llm_model_name="deepseek-v4-flash",
        llm_api_key=None,
    )
    monkeypatch.setattr(self_check_module, "build_ocr_client", lambda settings: FakeOCRClient())
    client = TestClient(create_app(document_service=service))

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["llm_backend"]["status"] == "misconfigured"
