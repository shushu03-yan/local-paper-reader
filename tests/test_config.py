from pathlib import Path

import src.config as config_module
from src.config import load_settings


def test_load_settings_reads_llm_defaults(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PADDLEOCR_PIPELINE_VERSION=v1.6",
                "OCR_BACKEND=lmstudio",
                "LMSTUDIO_OCR_BASE_URL=http://192.168.43.16:6611/v1",
                "LMSTUDIO_OCR_MODEL_NAME=paddleocr-vl-1.6",
                "LLM_BACKEND=lmstudio",
                "LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1",
                "LLM_MODEL_NAME=qwen2.5",
                "LLM_API_KEY=secret-key",
                "DEEPSEEK_BASE_URL=https://api.deepseek.com",
                "TARGET_LANGUAGE=zh-CN",
                "EXTRACTION_PROFILE=literature",
                "OCR_RETRIES=2",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(env_path=env_path)

    assert settings.llm_backend == "lmstudio"
    assert settings.ocr_backend == "lmstudio"
    assert settings.lmstudio_ocr_base_url == "http://192.168.43.16:6611/v1"
    assert settings.lmstudio_ocr_model_name == "paddleocr-vl-1.6"
    assert settings.lmstudio_base_url == "http://127.0.0.1:1234/v1"
    assert settings.llm_model_name == "qwen2.5"
    assert settings.llm_api_key == "secret-key"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.target_language == "zh-CN"
    assert settings.extraction_profile == "literature"
    assert settings.ocr_retries == 2


def test_load_settings_uses_safe_llm_defaults(tmp_path: Path) -> None:
    settings = load_settings(env_path=tmp_path / ".env")

    assert settings.llm_backend == "disabled"
    assert settings.ocr_backend == "python-local"
    assert settings.lmstudio_ocr_base_url == "http://127.0.0.1:6611/v1"
    assert settings.lmstudio_ocr_model_name is None
    assert settings.lmstudio_base_url == "http://127.0.0.1:1234/v1"
    assert settings.llm_model_name is None
    assert settings.llm_api_key is None
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.target_language == "zh-CN"
    assert settings.extraction_profile == "literature"
    assert settings.ocr_retries == 0


def test_load_settings_reads_process_environment(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "deepseek")
    monkeypatch.setenv("OCR_BACKEND", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_OCR_BASE_URL", "http://192.168.43.16:6611/v1")
    monkeypatch.setenv("LMSTUDIO_OCR_MODEL_NAME", "paddleocr-vl-1.6")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_MODEL_NAME", "deepseek-v4-flash")
    monkeypatch.setenv("LLM_API_KEY", "env-secret")

    settings = load_settings(env_path=Path("definitely-missing.env"))

    assert settings.ocr_backend == "lmstudio"
    assert settings.lmstudio_ocr_base_url == "http://192.168.43.16:6611/v1"
    assert settings.lmstudio_ocr_model_name == "paddleocr-vl-1.6"
    assert settings.llm_backend == "deepseek"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.llm_model_name == "deepseek-v4-flash"
    assert settings.llm_api_key == "env-secret"


def test_default_env_path_points_to_project_root() -> None:
    expected = Path(__file__).resolve().parents[1] / ".env"
    assert config_module.DEFAULT_ENV_PATH == expected
