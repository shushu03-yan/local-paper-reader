from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.api.service import DocumentService
from src.config import load_settings
from src.services.self_check import run_self_check


UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
DEFAULT_CORS_ORIGINS = ["http://127.0.0.1:8000", "http://localhost:8000"]


class UploadTooLargeError(ValueError):
    pass


class TranslateRequest(BaseModel):
    target_language: str = "zh-CN"
    glossary: str | None = None


class CorrectionRequest(BaseModel):
    corrected_markdown: str


class AnnotationCreateRequest(BaseModel):
    target_side: str
    block_index: int
    quote_text: str
    note_text: str
    color: str = "yellow"


class AnnotationUpdateRequest(BaseModel):
    note_text: str
    color: str = "yellow"


def create_app(
    document_service: DocumentService | None = None,
) -> FastAPI:
    if document_service is None:
        settings = load_settings()
        service = DocumentService(settings=settings)
    else:
        service = document_service
        service_settings = getattr(service, "settings", None)
        settings = service_settings if service_settings is not None else load_settings()
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ARG001
        try:
            yield
        finally:
            close = getattr(service, "close", None)
            if callable(close):
                close()

    app = FastAPI(
        title="Local Paper Reader",
        version="0.2.0",
        description="Local PaddleOCR-VL research reader with OCR pipeline and bilingual reading workflow.",
        lifespan=lifespan,
    )
    app.state.document_service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEFAULT_CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        content = (static_dir / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )

    @app.get("/health")
    def health() -> dict[str, object]:
        return run_self_check(settings)

    @app.get("/documents")
    def list_documents() -> dict[str, object]:
        return {"documents": service.list_documents()}

    @app.post("/documents", status_code=202)
    async def create_document(
        file: UploadFile = File(...),
    ) -> dict[str, object]:
        try:
            content = await _read_upload_content(file, max_bytes=settings.max_upload_bytes)
            return service.submit_document(file.filename or "upload.pdf", content)
        except UploadTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/documents/{document_id}")
    def get_document(document_id: str) -> dict[str, object]:
        try:
            return service.get_document(document_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/documents/{document_id}")
    def delete_document(document_id: str) -> dict[str, object]:
        try:
            return service.delete_document(document_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/documents/{document_id}/pages")
    def get_document_pages(document_id: str) -> dict[str, object]:
        try:
            return {"document_id": document_id, "pages": service.list_pages(document_id)}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/documents/{document_id}/artifacts")
    def get_document_artifacts(document_id: str) -> dict[str, object]:
        try:
            return {"document_id": document_id, "artifacts": service.list_artifacts(document_id)}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/documents/{document_id}/reader")
    def get_document_reader(document_id: str) -> dict[str, object]:
        try:
            return service.get_reader_view(document_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/documents/{document_id}/artifacts/{artifact_name}")
    def get_document_artifact_content(
        document_id: str,
        artifact_name: str,
    ) -> dict[str, object]:
        try:
            return service.read_artifact(document_id, artifact_name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/documents/{document_id}/translate", status_code=202)
    def translate_document(
        document_id: str,
        payload: TranslateRequest,
    ) -> dict[str, object]:
        try:
            return service.translate_document(
                document_id,
                payload.target_language,
                payload.glossary,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, object]:
        try:
            return service.get_task(task_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/documents/{document_id}/pages/{page_number}")
    def get_page_detail(
        document_id: str,
        page_number: int,
    ) -> dict[str, object]:
        try:
            return service.get_page_detail(document_id, page_number)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/documents/{document_id}/pages/{page_number}/annotations")
    def list_page_annotations(
        document_id: str,
        page_number: int,
    ) -> dict[str, object]:
        try:
            return {
                "document_id": document_id,
                "page_number": page_number,
                "annotations": service.list_page_annotations(document_id, page_number),
            }
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/documents/{document_id}/pages/{page_number}/annotations")
    def create_annotation(
        document_id: str,
        page_number: int,
        payload: AnnotationCreateRequest,
    ) -> dict[str, object]:
        try:
            return service.create_annotation(
                document_id,
                page_number,
                payload.target_side,
                payload.block_index,
                payload.quote_text,
                payload.note_text,
                payload.color,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/documents/{document_id}/annotations/{annotation_id}")
    def update_annotation(
        document_id: str,
        annotation_id: str,
        payload: AnnotationUpdateRequest,
    ) -> dict[str, object]:
        try:
            return service.update_annotation(
                document_id,
                annotation_id,
                payload.note_text,
                payload.color,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/documents/{document_id}/annotations/{annotation_id}")
    def delete_annotation(
        document_id: str,
        annotation_id: str,
    ) -> dict[str, object]:
        try:
            return service.delete_annotation(document_id, annotation_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/documents/{document_id}/pages/{page_number}/image")
    def get_page_image(
        document_id: str,
        page_number: int,
    ) -> FileResponse:
        try:
            return FileResponse(service.get_page_image_path(document_id, page_number))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/documents/{document_id}/assets/{asset_path:path}")
    def get_document_asset(
        document_id: str,
        asset_path: str,
    ) -> FileResponse:
        try:
            return FileResponse(service.get_document_asset_path(document_id, asset_path))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/documents/{document_id}/pages/{page_number}/corrections")
    def save_page_correction(
        document_id: str,
        page_number: int,
        payload: CorrectionRequest,
    ) -> dict[str, object]:
        try:
            return service.save_page_correction(
                document_id,
                page_number,
                payload.corrected_markdown,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/documents/{document_id}/extract", status_code=202)
    def extract_document(
        document_id: str,
    ) -> dict[str, object]:
        try:
            return service.extract_document(document_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


async def _read_upload_content(file: UploadFile, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(UPLOAD_READ_CHUNK_BYTES):
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLargeError(f"Uploaded file exceeds {max_bytes} bytes.")
        chunks.append(chunk)
    return b"".join(chunks)


app = create_app()
