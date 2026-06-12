from src.config import Settings
from src.services import self_check as self_check_module
from src.services.self_check import run_self_check


class FakeOCRClient:
    backend_name = "fake-ocr"
    model_name = "fake-ocr-model"
    pipeline_version = "v1.6"
    base_url = "http://127.0.0.1:6611/v1"

    def ensure_backend_available(self) -> None:
        return None


class FakeHealthyBackend:
    def health_check(self) -> dict[str, object]:
        return {
            "status": "ok",
            "backend": "deepseek",
            "model": "deepseek-v4-flash",
        }


class FakeUnavailableBackend:
    backend_name = "deepseek"
    model_name = "deepseek-v4-flash"

    def health_check(self) -> dict[str, object]:
        raise ConnectionError("network unavailable")


def _settings(**overrides: object) -> Settings:
    values = {
        "ocr_backend": "lmstudio",
        "lmstudio_ocr_model_name": "fake-ocr-model",
        "llm_backend": "disabled",
    }
    values.update(overrides)
    return Settings(**values)


def test_self_check_reports_disabled_llm(monkeypatch) -> None:
    monkeypatch.setattr(self_check_module, "build_ocr_client", lambda settings: FakeOCRClient())

    result = run_self_check(_settings())

    assert result["status"] == "ok"
    assert result["ocr_backend"]["status"] == "ok"
    assert result["llm_backend"] == {"status": "disabled", "backend": "disabled"}


def test_self_check_reports_misconfigured_deepseek_without_failing(monkeypatch) -> None:
    monkeypatch.setattr(self_check_module, "build_ocr_client", lambda settings: FakeOCRClient())

    result = run_self_check(
        _settings(
            llm_backend="deepseek",
            llm_model_name="deepseek-v4-flash",
            llm_api_key=None,
        )
    )

    assert result["status"] == "degraded"
    assert result["llm_backend"]["status"] == "misconfigured"
    assert result["llm_backend"]["backend"] == "deepseek"
    assert result["llm_backend"]["error"] == "LLM_API_KEY is required when LLM_BACKEND=deepseek."
    assert result["settings"]["llm_api_key"] is None


def test_self_check_uses_backend_health_check_when_llm_config_is_complete(monkeypatch) -> None:
    monkeypatch.setattr(self_check_module, "build_ocr_client", lambda settings: FakeOCRClient())
    monkeypatch.setattr(
        self_check_module,
        "build_postprocess_backend",
        lambda settings: FakeHealthyBackend(),
    )

    result = run_self_check(
        _settings(
            llm_backend="deepseek",
            llm_model_name="deepseek-v4-flash",
            llm_api_key="secret-key",
        )
    )

    assert result["status"] == "ok"
    assert result["llm_backend"]["status"] == "ok"
    assert result["settings"]["llm_api_key"] == "sec****-key"


def test_self_check_reports_unavailable_llm_backend_without_failing(monkeypatch) -> None:
    monkeypatch.setattr(self_check_module, "build_ocr_client", lambda settings: FakeOCRClient())
    monkeypatch.setattr(
        self_check_module,
        "build_postprocess_backend",
        lambda settings: FakeUnavailableBackend(),
    )

    result = run_self_check(
        _settings(
            llm_backend="deepseek",
            llm_model_name="deepseek-v4-flash",
            llm_api_key="secret-key",
        )
    )

    assert result["status"] == "degraded"
    assert result["llm_backend"]["status"] == "unavailable"
    assert result["llm_backend"]["backend"] == "deepseek"
    assert result["llm_backend"]["model"] == "deepseek-v4-flash"
    assert result["llm_backend"]["error"] == "network unavailable"
