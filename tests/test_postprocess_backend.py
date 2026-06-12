from src.config import Settings
from src.services.postprocess_service import OpenAICompatiblePostprocessClient, build_postprocess_backend


def test_build_postprocess_backend_supports_deepseek() -> None:
    settings = Settings(
        llm_backend="deepseek",
        llm_model_name="deepseek-v4-flash",
        llm_api_key="secret",
        deepseek_base_url="https://api.deepseek.com",
    )

    backend = build_postprocess_backend(settings)

    assert isinstance(backend, OpenAICompatiblePostprocessClient)
    assert backend.backend_name == "deepseek"
    assert backend.base_url == "https://api.deepseek.com"
    assert backend.model_name == "deepseek-v4-flash"
