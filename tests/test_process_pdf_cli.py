from pathlib import Path

import scripts.process_pdf_cli as cli


class FakeClient:
    def ensure_backend_available(self) -> None:
        return None


class FakePipeline:
    def __init__(self, **kwargs) -> None:
        pass

    def process(self, **kwargs) -> dict[str, object]:
        document_id = str(kwargs["document_id"])
        output_root = Path("outputs")
        document_root = output_root / document_id
        document_root.mkdir(parents=True, exist_ok=True)
        (document_root / "paper.md").write_text("<!-- page: 1 -->\nAlpha", encoding="utf-8")
        (document_root / "manifest.json").write_text(
            '{"document_id": "%s", "status": "completed", "artifacts": {}}' % document_id,
            encoding="utf-8",
        )
        return {
            "document_id": document_id,
            "status": "completed",
            "pages_total": 1,
            "pages_succeeded": 1,
            "pages_failed": 0,
        }


class FakeBackend:
    backend_name = "fake"
    model_name = "fake-model"


def _run_cli(tmp_path: Path, monkeypatch, args: list[str]) -> tuple[int, list[str]]:
    input_pdf = tmp_path / "paper.pdf"
    input_pdf.write_bytes(b"%PDF-1.7 fake")
    output_root = tmp_path / "outputs"
    calls: list[str] = []

    monkeypatch.setattr(cli, "build_ocr_client", lambda settings: FakeClient())
    monkeypatch.setattr(cli, "OCRPipeline", FakePipeline)
    monkeypatch.setattr(cli, "build_postprocess_backend", lambda settings: FakeBackend())
    monkeypatch.setattr(cli, "run_translation", lambda **kwargs: calls.append("translation"), raising=False)
    monkeypatch.setattr(cli, "run_extraction", lambda **kwargs: calls.append("extraction"), raising=False)
    monkeypatch.setattr(cli, "run_reading_notes", lambda **kwargs: calls.append("reading_notes"), raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "process_pdf_cli.py",
            str(input_pdf),
            "--output-dir",
            str(output_root),
            *args,
        ],
    )

    return cli.main(), calls


def test_cli_extract_flag_runs_only_extraction(tmp_path: Path, monkeypatch) -> None:
    exit_code, calls = _run_cli(tmp_path, monkeypatch, ["--extract"])

    assert exit_code == 0
    assert calls == ["extraction"]


def test_cli_translate_and_reading_notes_flags_run_only_selected_steps(tmp_path: Path, monkeypatch) -> None:
    exit_code, calls = _run_cli(tmp_path, monkeypatch, ["--translate", "--reading-notes"])

    assert exit_code == 0
    assert calls == ["translation", "reading_notes"]


def test_cli_self_check_prints_llm_status_and_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "run_self_check",
        lambda settings: {
            "status": "degraded",
            "ocr_backend": {
                "backend": "paddleocr-python",
                "model": "PaddleOCRVL",
                "pipeline_version": "v1.6",
                "paddle_version": "3.3.0",
            },
            "llm_backend": {
                "status": "misconfigured",
                "backend": "deepseek",
                "error": "LLM_API_KEY is required when LLM_BACKEND=deepseek.",
            },
        },
    )
    monkeypatch.setattr("sys.argv", ["process_pdf_cli.py", "--self-check"])

    exit_code = cli.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "status: degraded" in output
    assert "llm_backend: deepseek" in output
    assert "llm_status: misconfigured" in output
    assert "llm_error: LLM_API_KEY is required when LLM_BACKEND=deepseek." in output
