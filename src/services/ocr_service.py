from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import mkdtemp
from dataclasses import dataclass
from typing import Any, Callable

from src.config import Settings


@dataclass(slots=True)
class OCRPageContent:
    markdown: str
    asset_dir: Path | None = None


class PaddleOCRLocalClient:
    backend_name = "paddleocr-python"
    model_name = "PaddleOCRVL"

    def __init__(
        self,
        *,
        pipeline_version: str = "v1.6",
        device: str | None = None,
        engine: str | None = None,
        pipeline_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.pipeline_version = pipeline_version
        self.device = device
        self.engine = engine
        self._pipeline_factory = pipeline_factory
        self._pipeline: Any | None = None

    def ensure_backend_available(self) -> None:
        self._get_pipeline()

    def _build_pipeline(self) -> Any:
        try:
            from paddleocr import PaddleOCRVL
        except ImportError as exc:
            raise RuntimeError(
                "Install paddleocr and paddlepaddle before running OCR. "
                "Recommended packages: paddleocr[doc-parser]>=3.4.0 and a compatible paddlepaddle or paddlepaddle-gpu build."
            ) from exc

        kwargs: dict[str, Any] = {"pipeline_version": self.pipeline_version}
        if self.device:
            kwargs["device"] = self.device
        if self.engine:
            kwargs["engine"] = self.engine
        return PaddleOCRVL(**kwargs)

    def _get_pipeline(self) -> Any:
        if self._pipeline is None:
            if self._pipeline_factory is not None:
                try:
                    self._pipeline = self._pipeline_factory()
                except ImportError as exc:
                    raise RuntimeError(
                        "Install paddleocr and paddlepaddle before running OCR. "
                        "Recommended packages: paddleocr[doc-parser]>=3.4.0 and a compatible paddlepaddle or paddlepaddle-gpu build."
                    ) from exc
            else:
                self._pipeline = self._build_pipeline()
        return self._pipeline

    @staticmethod
    def _extract_markdown(result: Any) -> OCRPageContent | None:
        markdown = getattr(result, "markdown", None)
        if isinstance(markdown, str) and markdown.strip():
            return OCRPageContent(markdown=markdown.strip(), asset_dir=None)

        tmpdir = Path(mkdtemp(prefix="paddleocr_vl_md_"))
        save_to_markdown = getattr(result, "save_to_markdown", None)
        try:
            if callable(save_to_markdown):
                save_to_markdown(save_path=str(tmpdir))
                markdown_files = sorted(tmpdir.rglob("*.md"))
                if markdown_files:
                    content = markdown_files[0].read_text(encoding="utf-8").strip()
                    if content:
                        return OCRPageContent(markdown=content, asset_dir=tmpdir)
        except Exception:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None

    def ocr_image(self, image_path: Path) -> OCRPageContent:
        pipeline = self._get_pipeline()
        results = list(pipeline.predict(str(image_path)))
        if not results:
            raise RuntimeError(f"PaddleOCR returned no results for {image_path.name}")

        content = self._extract_markdown(results[0])
        if not content:
            raise RuntimeError(f"PaddleOCR result did not contain markdown for {image_path.name}")
        return content


class LMStudioOCRClient:
    backend_name = "lmstudio-ocr"

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        api_key: str = "lm-studio",
        pipeline_version: str = "v1.6",
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.pipeline_version = pipeline_version
        self.device = None
        self.engine = "llama-cpp-server"
        self._client_factory = client_factory
        self._openai_client: Any | None = None
        self._pipeline: PaddleOCRLocalClient | None = None

    def _get_client(self) -> Any:
        if self._client_factory is not None:
            if self._openai_client is None:
                self._openai_client = self._client_factory()
            return self._openai_client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the openai package before using LM Studio OCR.") from exc
        if self._openai_client is None:
            self._openai_client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._openai_client

    def ensure_backend_available(self) -> None:
        client = self._get_client()
        models = client.models.list()
        model_ids = [model.id for model in getattr(models, "data", [])]
        if self.model_name not in model_ids:
            raise RuntimeError(
                f"LM Studio OCR model '{self.model_name}' is not available. Found: {', '.join(model_ids) or 'none'}"
            )

    def _build_pipeline(self) -> Any:
        try:
            from paddleocr import PaddleOCRVL
        except ImportError as exc:
            raise RuntimeError(
                "Install paddleocr and paddlepaddle before using the LM Studio OCR backend."
            ) from exc
        return PaddleOCRVL(
            pipeline_version=self.pipeline_version,
            vl_rec_backend="llama-cpp-server",
            vl_rec_server_url=self.base_url,
        )

    def _get_pipeline_client(self) -> PaddleOCRLocalClient:
        if self._pipeline is None:
            self._pipeline = PaddleOCRLocalClient(
                pipeline_version=self.pipeline_version,
                engine=self.engine,
                pipeline_factory=self._build_pipeline,
            )
        return self._pipeline

    def ocr_image(self, image_path: Path) -> OCRPageContent:
        pipeline_client = self._get_pipeline_client()
        return pipeline_client.ocr_image(image_path)


def build_ocr_client(settings: Settings) -> PaddleOCRLocalClient | LMStudioOCRClient:
    if settings.ocr_backend == "python-local":
        return PaddleOCRLocalClient(
            pipeline_version=settings.paddleocr_pipeline_version,
            device=settings.paddleocr_device,
            engine=settings.paddleocr_engine,
        )
    if settings.ocr_backend == "lmstudio":
        if not settings.lmstudio_ocr_model_name:
            raise RuntimeError("LMSTUDIO_OCR_MODEL_NAME is required when OCR_BACKEND=lmstudio.")
        return LMStudioOCRClient(
            base_url=settings.lmstudio_ocr_base_url,
            model_name=settings.lmstudio_ocr_model_name,
            pipeline_version=settings.paddleocr_pipeline_version,
        )
    raise RuntimeError(f"Unsupported OCR backend: {settings.ocr_backend}")
