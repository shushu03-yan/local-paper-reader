from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.config import Settings
from src.services.ocr_service import build_ocr_client
from src.services.postprocess_service import build_postprocess_backend


SECRET_SETTING_NAMES = {"llm_api_key"}


def run_self_check(settings: Settings) -> dict[str, Any]:
    ocr_status: dict[str, Any]
    if settings.ocr_backend == "python-local":
        try:
            import paddle
            from paddleocr import PaddleOCRVL
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR self-check failed. Install paddleocr and paddlepaddle-gpu in the active environment."
            ) from exc
        ocr_status = {
            "status": "ok",
            "backend": "paddleocr-python",
            "model": "PaddleOCRVL",
            "pipeline_version": settings.paddleocr_pipeline_version,
            "paddle_version": paddle.__version__,
            "entrypoint": PaddleOCRVL.__name__,
        }
    else:
        client = build_ocr_client(settings)
        client.ensure_backend_available()
        ocr_status = {
            "status": "ok",
            "backend": client.backend_name,
            "model": client.model_name,
            "pipeline_version": client.pipeline_version,
            "base_url": getattr(client, "base_url", None),
        }

    llm_status: dict[str, Any]
    overall_status = "ok"
    try:
        backend = build_postprocess_backend(settings)
    except RuntimeError as exc:
        overall_status = "degraded"
        llm_status = {
            "status": "misconfigured",
            "backend": settings.llm_backend,
            "model": settings.llm_model_name,
            "error": str(exc),
        }
    else:
        if backend is None:
            llm_status = {"status": "disabled", "backend": "disabled"}
        else:
            try:
                llm_status = backend.health_check()
            except Exception as exc:  # noqa: BLE001
                overall_status = "degraded"
                llm_status = {
                    "status": "unavailable",
                    "backend": getattr(backend, "backend_name", settings.llm_backend),
                    "model": getattr(backend, "model_name", settings.llm_model_name),
                    "error": str(exc),
                }

    return {
        "status": overall_status,
        "settings": _serialize_settings_for_health(settings),
        "ocr_backend": ocr_status,
        "llm_backend": llm_status,
    }


def _serialize_settings_for_health(settings: Settings) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for key, value in asdict(settings).items():
        if key in SECRET_SETTING_NAMES:
            serialized[key] = _mask_secret(value)
        else:
            serialized[key] = str(value) if hasattr(value, "as_posix") else value
    return serialized


def _mask_secret(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return f"{text[:3]}****{text[-4:]}"
