from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import inspect
import re

from src.config import Settings
from src.utils.file_utils import ensure_directory
from src.utils.markdown_utils import split_markdown_pages


@dataclass(slots=True)
class ResearchArtifacts:
    translated_markdown: Path | None = None
    structured_data: Path | None = None
    reading_notes: Path | None = None
    quality_report: Path | None = None


class PostprocessBackend(Protocol):
    backend_name: str
    model_name: str

    def health_check(self) -> dict[str, object]: ...

    def translate_document(
        self,
        markdown: str,
        target_language: str,
        glossary: str | None = None,
    ) -> str: ...

    def extract_structured_data(
        self,
        markdown: str,
        extraction_profile: str,
    ) -> dict[str, object]: ...

    def build_reading_notes(
        self,
        markdown: str,
        target_language: str,
    ) -> dict[str, object]: ...


class OpenAICompatiblePostprocessClient:
    def __init__(
        self,
        *,
        backend_name: str,
        base_url: str,
        model_name: str,
        api_key: str,
    ) -> None:
        self.backend_name = backend_name
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self._client: Any | None = None

    @classmethod
    def for_lmstudio(
        cls,
        *,
        base_url: str,
        model_name: str,
    ) -> "OpenAICompatiblePostprocessClient":
        return cls(
            backend_name="lmstudio",
            base_url=base_url,
            model_name=model_name,
            api_key="lm-studio",
        )

    @classmethod
    def for_deepseek(
        cls,
        *,
        base_url: str,
        model_name: str,
        api_key: str,
    ) -> "OpenAICompatiblePostprocessClient":
        return cls(
            backend_name="deepseek",
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
        )

    def _get_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Install the openai package before enabling the LM Studio postprocess backend."
            ) from exc
        if self._client is None:
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model_name,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        message = response.choices[0].message.content
        if not isinstance(message, str) or not message.strip():
            raise RuntimeError("LM Studio returned an empty response.")
        return message.strip()

    def health_check(self) -> dict[str, object]:
        client = self._get_client()
        models = client.models.list()
        model_ids = [model.id for model in getattr(models, "data", [])]
        return {
            "status": "ok",
            "backend": self.backend_name,
            "model": self.model_name,
            "available_models": model_ids,
        }

    def translate_document(
        self,
        markdown: str,
        target_language: str,
        glossary: str | None = None,
    ) -> str:
        glossary_instruction = (
            f"\nUse this glossary when translating terms:\n{glossary}\n"
            if glossary
            else ""
        )
        return self._complete(
            "You translate OCR markdown into faithful academic prose without removing page anchors.",
            (
                f"Translate the following OCR markdown into {target_language}. "
                "Keep markdown structure, keep page comments, and do not summarize.\n\n"
                f"{glossary_instruction}"
                f"{markdown}"
            ),
        )

    def extract_structured_data(
        self,
        markdown: str,
        extraction_profile: str,
    ) -> dict[str, object]:
        response = self._complete(
            "You extract machine-readable research metadata from OCR markdown.",
            _structured_extraction_prompt(markdown, extraction_profile),
        )
        return _load_json_response(response)

    def build_reading_notes(
        self,
        markdown: str,
        target_language: str,
    ) -> dict[str, object]:
        response = self._complete(
            "You create concise bilingual research reading notes in valid JSON.",
            (
                "Return valid JSON with keys summary, key_terms, open_questions, and action_items. "
                f"Use {target_language} for human-facing text.\n\n{markdown}"
            ),
        )
        return _load_json_response(response)


def _load_json_response(response: str) -> dict[str, object]:
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"LLM backend did not return valid JSON. Error: {exc}. Response preview: {cleaned[:200]}"
        ) from exc


def _call_translate(
    backend: PostprocessBackend,
    markdown: str,
    target_language: str,
    glossary: str | None,
) -> str:
    method = backend.translate_document
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        signature = None
    if signature is not None and "glossary" not in signature.parameters:
        return method(markdown, target_language)  # type: ignore[misc]
    return method(markdown, target_language, glossary)


def _quality_report(original_pages: dict[int, str], translated_pages: dict[int, str]) -> dict[str, object]:
    original_numbers = sorted(original_pages)
    translated_numbers = sorted(translated_pages)
    missing = [page for page in original_numbers if page not in translated_pages]
    empty = [
        page
        for page in translated_numbers
        if not translated_pages.get(page, "").strip()
    ]
    return {
        "page_count_match": len(original_numbers) == len(translated_numbers),
        "original_pages": original_numbers,
        "translated_pages": translated_numbers,
        "missing_translation_pages": missing,
        "empty_translation_pages": empty,
        "warnings": [
            warning
            for warning in [
                "page_count_mismatch" if len(original_numbers) != len(translated_numbers) else "",
                "missing_pages" if missing else "",
                "empty_pages" if empty else "",
            ]
            if warning
        ],
    }


def _structured_extraction_prompt(markdown: str, extraction_profile: str) -> str:
    return (
        "Return valid JSON only. Use exactly these top-level keys when possible: "
        "title, authors, abstract, methods, datasets, metrics, results, limitations, "
        "tables, figures, equations. "
        f"Extraction profile: {extraction_profile}.\n\n{markdown}"
    )


def _read_glossary(glossary_path: Path | None) -> str | None:
    if glossary_path is None or not glossary_path.exists():
        return None
    content = glossary_path.read_text(encoding="utf-8").strip()
    return content or None


def build_postprocess_backend(settings: Settings) -> PostprocessBackend | None:
    if settings.llm_backend == "disabled":
        return None
    if not settings.llm_model_name:
        raise RuntimeError("LLM_MODEL_NAME is required when LLM_BACKEND is enabled.")
    if settings.llm_backend == "lmstudio":
        return OpenAICompatiblePostprocessClient.for_lmstudio(
            base_url=settings.lmstudio_base_url,
            model_name=settings.llm_model_name,
        )
    if settings.llm_backend == "deepseek":
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is required when LLM_BACKEND=deepseek.")
        return OpenAICompatiblePostprocessClient.for_deepseek(
            base_url=settings.deepseek_base_url,
            model_name=settings.llm_model_name,
            api_key=settings.llm_api_key,
        )
    raise RuntimeError(f"Unsupported LLM backend: {settings.llm_backend}")


def run_translation(
    *,
    document_root: Path,
    backend: PostprocessBackend,
    target_language: str,
    glossary: str | None = None,
) -> ResearchArtifacts:
    paper_path = _postprocess_markdown_path(document_root)
    manifest_path = document_root / "manifest.json"
    if not paper_path.exists():
        raise FileNotFoundError(f"Missing OCR markdown: {paper_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    markdown = paper_path.read_text(encoding="utf-8")
    translated_path = document_root / f"translated.{target_language}.md"
    quality_path = document_root / "quality_report.json"

    original_pages = split_markdown_pages(markdown)
    translated_chunks: dict[int, str] = {}
    for page_number, page_markdown in original_pages.items():
        translated_chunks[page_number] = _call_translate(
            backend,
            f"<!-- page: {page_number} -->\n{page_markdown}",
            target_language,
            glossary,
        )

    translated_text = "\n\n".join(
        f"<!-- page: {page_number} -->\n{translated_chunks[page_number].strip()}"
        for page_number in sorted(translated_chunks)
    )
    translated_pages = split_markdown_pages(translated_text)
    report = _quality_report(original_pages, translated_pages)
    ensure_directory(document_root)
    translated_path.write_text(translated_text, encoding="utf-8")
    quality_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.setdefault("artifacts", {})
    artifacts.update(
        {
            "translated_markdown": str(translated_path),
            "quality_report": str(quality_path),
        }
    )
    manifest["postprocess_backend"] = backend.backend_name
    manifest["postprocess_model"] = backend.model_name
    manifest["target_language"] = target_language
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return ResearchArtifacts(translated_markdown=translated_path, quality_report=quality_path)


def run_extraction(
    *,
    document_root: Path,
    backend: PostprocessBackend,
    extraction_profile: str,
) -> ResearchArtifacts:
    paper_path = _postprocess_markdown_path(document_root)
    manifest_path = document_root / "manifest.json"
    if not paper_path.exists():
        raise FileNotFoundError(f"Missing OCR markdown: {paper_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    markdown = paper_path.read_text(encoding="utf-8")
    structured_path = document_root / "structured.json"
    structured_data = backend.extract_structured_data(markdown, extraction_profile)
    ensure_directory(document_root)
    structured_path.write_text(
        json.dumps(structured_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.setdefault("artifacts", {})
    artifacts["structured_data"] = str(structured_path)
    manifest["postprocess_backend"] = backend.backend_name
    manifest["postprocess_model"] = backend.model_name
    manifest["extraction_profile"] = extraction_profile
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return ResearchArtifacts(structured_data=structured_path)


def run_reading_notes(
    *,
    document_root: Path,
    backend: PostprocessBackend,
    target_language: str,
) -> ResearchArtifacts:
    paper_path = _postprocess_markdown_path(document_root)
    manifest_path = document_root / "manifest.json"
    if not paper_path.exists():
        raise FileNotFoundError(f"Missing OCR markdown: {paper_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    markdown = paper_path.read_text(encoding="utf-8")
    notes_path = document_root / "reading_notes.json"
    reading_notes = backend.build_reading_notes(markdown, target_language)
    ensure_directory(document_root)
    notes_path.write_text(
        json.dumps(reading_notes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.setdefault("artifacts", {})
    artifacts["reading_notes"] = str(notes_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return ResearchArtifacts(reading_notes=notes_path)


def run_postprocess(
    *,
    document_root: Path,
    backend: PostprocessBackend,
    target_language: str,
    extraction_profile: str,
    glossary_path: Path | None = None,
) -> ResearchArtifacts:
    paper_path = document_root / "paper.md"
    manifest_path = document_root / "manifest.json"
    if not paper_path.exists():
        raise FileNotFoundError(f"Missing OCR markdown: {paper_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    translation = run_translation(
        document_root=document_root,
        backend=backend,
        target_language=target_language,
        glossary=_read_glossary(glossary_path),
    )
    extraction = run_extraction(
        document_root=document_root,
        backend=backend,
        extraction_profile=extraction_profile,
    )
    notes = run_reading_notes(
        document_root=document_root,
        backend=backend,
        target_language=target_language,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["postprocess_backend"] = backend.backend_name
    manifest["postprocess_model"] = backend.model_name
    manifest["target_language"] = target_language
    manifest["extraction_profile"] = extraction_profile
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return ResearchArtifacts(
        translated_markdown=translation.translated_markdown,
        structured_data=extraction.structured_data,
        reading_notes=notes.reading_notes,
        quality_report=translation.quality_report,
    )


def _postprocess_markdown_path(document_root: Path) -> Path:
    reader_path = document_root / "reader.md"
    if reader_path.exists():
        return reader_path
    return document_root / "paper.md"
