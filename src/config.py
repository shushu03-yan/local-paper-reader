from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def _parse_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _coerce_int(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class Settings:
    ocr_backend: str = "python-local"
    paddleocr_pipeline_version: str = "v1.6"
    paddleocr_device: str | None = None
    paddleocr_engine: str | None = None
    lmstudio_ocr_base_url: str = "http://127.0.0.1:6611/v1"
    lmstudio_ocr_model_name: str | None = None
    pdf_render_dpi: int = 200
    max_concurrency: int = 1
    output_root: Path = Path("outputs")
    database_path: Path = Path("outputs/reader.sqlite3")
    log_level: str = "INFO"
    ocr_retries: int = 0
    max_upload_bytes: int = 100 * 1024 * 1024
    llm_backend: str = "disabled"
    lmstudio_base_url: str = "http://127.0.0.1:1234/v1"
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_model_name: str | None = None
    llm_api_key: str | None = None
    target_language: str = "zh-CN"
    extraction_profile: str = "literature"
    glossary_path: Path | None = None


def load_settings(
    env_path: Path | None = None,
    overrides: dict[str, object] | None = None,
) -> Settings:
    env_values = _parse_env_file(env_path or DEFAULT_ENV_PATH)
    process_env = os.environ
    overrides = overrides or {}

    def pick(key: str, default: object) -> object:
        override_value = overrides.get(key)
        if override_value is not None:
            return override_value
        if key in process_env and process_env[key].strip():
            return process_env[key]
        return env_values.get(key, default)

    output_root = Path(str(pick("OUTPUT_ROOT", "outputs")))
    database_path = Path(str(pick("DATABASE_PATH", output_root / "reader.sqlite3")))

    def pick_optional_str(key: str) -> str | None:
        value = pick(key, None)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    return Settings(
        ocr_backend=str(pick("OCR_BACKEND", "python-local")).strip().lower() or "python-local",
        paddleocr_pipeline_version=str(
            pick("PADDLEOCR_PIPELINE_VERSION", "v1.6")
        ),
        paddleocr_device=pick_optional_str("PADDLEOCR_DEVICE"),
        paddleocr_engine=pick_optional_str("PADDLEOCR_ENGINE"),
        lmstudio_ocr_base_url=str(
            pick("LMSTUDIO_OCR_BASE_URL", "http://127.0.0.1:6611/v1")
        ).strip(),
        lmstudio_ocr_model_name=pick_optional_str("LMSTUDIO_OCR_MODEL_NAME"),
        pdf_render_dpi=_coerce_int(
            pick("PDF_RENDER_DPI", 200),
            200,
        ),
        max_concurrency=max(1, _coerce_int(pick("MAX_CONCURRENCY", 1), 1)),
        output_root=output_root,
        database_path=database_path,
        log_level=str(pick("LOG_LEVEL", "INFO")).upper(),
        ocr_retries=max(0, _coerce_int(pick("OCR_RETRIES", 0), 0)),
        max_upload_bytes=max(
            1,
            _coerce_int(pick("MAX_UPLOAD_BYTES", 100 * 1024 * 1024), 100 * 1024 * 1024),
        ),
        llm_backend=str(pick("LLM_BACKEND", "disabled")).strip().lower() or "disabled",
        lmstudio_base_url=str(
            pick("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
        ).strip(),
        deepseek_base_url=str(
            pick("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        ).strip(),
        llm_model_name=pick_optional_str("LLM_MODEL_NAME"),
        llm_api_key=pick_optional_str("LLM_API_KEY"),
        target_language=str(pick("TARGET_LANGUAGE", "zh-CN")).strip() or "zh-CN",
        extraction_profile=str(
            pick("EXTRACTION_PROFILE", "literature")
        ).strip() or "literature",
        glossary_path=Path(str(pick("GLOSSARY_PATH", ""))).expanduser()
        if pick_optional_str("GLOSSARY_PATH")
        else None,
    )
