from src.config import Settings
from src.services.ocr_service import LMStudioOCRClient, PaddleOCRLocalClient, build_ocr_client


def test_build_ocr_client_defaults_to_python_local() -> None:
    client = build_ocr_client(Settings())

    assert isinstance(client, PaddleOCRLocalClient)
    assert client.backend_name == "paddleocr-python"


def test_build_ocr_client_supports_lmstudio() -> None:
    settings = Settings(
        ocr_backend="lmstudio",
        lmstudio_ocr_base_url="http://192.168.43.16:6611/v1",
        lmstudio_ocr_model_name="paddleocr-vl-1.6",
    )

    client = build_ocr_client(settings)

    assert isinstance(client, LMStudioOCRClient)
    assert client.backend_name == "lmstudio-ocr"
    assert client.base_url == "http://192.168.43.16:6611/v1"
    assert client.model_name == "paddleocr-vl-1.6"
