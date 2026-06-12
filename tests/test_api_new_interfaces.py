from fastapi.testclient import TestClient

from src.api.app import create_app


class FakeExpandedDocumentService:
    def list_documents(self) -> list[dict[str, object]]:
        return [{"document_id": "doc-1", "status": "completed"}]

    def get_task(self, task_id: str) -> dict[str, object]:
        return {"task_id": task_id, "document_id": "doc-1", "status": "completed"}

    def get_page_detail(self, document_id: str, page_number: int) -> dict[str, object]:
        return {
            "document_id": document_id,
            "page_number": page_number,
            "status": "completed",
            "original_markdown": "Alpha",
            "reader_markdown": "Alpha clean",
            "translated_markdown": "阿尔法",
            "corrected_markdown": None,
            "image_url": f"/documents/{document_id}/pages/{page_number}/image",
            "annotations": [
                {
                    "annotation_id": "ann-1",
                    "document_id": document_id,
                    "page_number": page_number,
                    "target_side": "translation",
                    "block_index": 0,
                    "quote_text": "阿尔法",
                    "note_text": "key term",
                    "color": "yellow",
                }
            ],
        }

    def save_page_correction(
        self,
        document_id: str,
        page_number: int,
        corrected_markdown: str,
    ) -> dict[str, object]:
        return {
            "document_id": document_id,
            "page_number": page_number,
            "corrected_markdown": corrected_markdown,
        }

    def extract_document(self, document_id: str) -> dict[str, object]:
        return {"task_id": f"extract-{document_id}", "document_id": document_id, "status": "queued"}

    def submit_document(self, filename: str, content: bytes) -> dict[str, object]:
        return {"task_id": "ocr-doc-1", "document_id": "doc-1", "status": "queued"}

    def get_document(self, document_id: str) -> dict[str, object]:
        return {"document_id": document_id, "status": "completed"}

    def list_pages(self, document_id: str) -> list[dict[str, object]]:
        return []

    def list_artifacts(self, document_id: str) -> dict[str, object]:
        return {}

    def get_reader_view(self, document_id: str) -> dict[str, object]:
        return {"document_id": document_id, "translated_available": False, "pages": []}

    def read_artifact(self, document_id: str, artifact_name: str) -> dict[str, object]:
        return {"artifact": artifact_name, "kind": "text", "content": ""}

    def translate_document(
        self,
        document_id: str,
        target_language: str,
        glossary: str | None = None,
    ) -> dict[str, object]:
        return {"task_id": f"translate-{document_id}", "document_id": document_id, "status": "queued"}

    def list_page_annotations(self, document_id: str, page_number: int) -> list[dict[str, object]]:
        return self.get_page_detail(document_id, page_number)["annotations"]

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
        return {
            "annotation_id": "ann-created",
            "document_id": document_id,
            "page_number": page_number,
            "target_side": target_side,
            "block_index": block_index,
            "quote_text": quote_text,
            "note_text": note_text,
            "color": color,
        }

    def update_annotation(
        self,
        document_id: str,
        annotation_id: str,
        note_text: str,
        color: str,
    ) -> dict[str, object]:
        return {
            "annotation_id": annotation_id,
            "document_id": document_id,
            "page_number": 1,
            "target_side": "translation",
            "block_index": 0,
            "quote_text": "阿尔法",
            "note_text": note_text,
            "color": color,
        }

    def delete_annotation(self, document_id: str, annotation_id: str) -> dict[str, object]:
        if annotation_id == "missing":
            raise FileNotFoundError("Unknown annotation: missing")
        return {"annotation_id": annotation_id, "status": "deleted"}


def test_expanded_api_routes_are_local_single_user_without_token() -> None:
    client = TestClient(create_app(document_service=FakeExpandedDocumentService()))

    assert client.get("/documents").json()["documents"][0]["document_id"] == "doc-1"
    assert client.get("/tasks/ocr-doc-1").json()["status"] == "completed"
    page = client.get("/documents/doc-1/pages/1").json()
    assert page["original_markdown"] == "Alpha"
    assert page["reader_markdown"] == "Alpha clean"
    assert page["annotations"][0]["annotation_id"] == "ann-1"
    correction = client.post(
        "/documents/doc-1/pages/1/corrections",
        json={"corrected_markdown": "fixed"},
    )
    assert correction.json()["corrected_markdown"] == "fixed"
    assert client.post("/documents/doc-1/extract").json()["status"] == "queued"


def test_annotation_api_routes_create_update_delete_and_404() -> None:
    client = TestClient(create_app(document_service=FakeExpandedDocumentService()))

    assert client.get("/documents/doc-1/pages/1/annotations").json()["annotations"][0]["note_text"] == "key term"

    created = client.post(
        "/documents/doc-1/pages/1/annotations",
        json={
            "target_side": "translation",
            "block_index": 0,
            "quote_text": "阿尔法",
            "note_text": "created note",
            "color": "yellow",
        },
    )
    assert created.status_code == 200
    assert created.json()["annotation_id"] == "ann-created"

    updated = client.put(
        "/documents/doc-1/annotations/ann-created",
        json={"note_text": "updated note", "color": "green"},
    )
    assert updated.status_code == 200
    assert updated.json()["note_text"] == "updated note"
    assert updated.json()["color"] == "green"

    deleted = client.delete("/documents/doc-1/annotations/ann-created")
    assert deleted.status_code == 200
    assert deleted.json() == {"annotation_id": "ann-created", "status": "deleted"}

    assert client.delete("/documents/doc-1/annotations/missing").status_code == 404
