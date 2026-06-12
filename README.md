# local-paper-reader

> A local-first research paper reader built on PaddleOCR-VL for PDF OCR, bilingual reading, structured extraction, and manual correction.

English | [Chinese](README.zh-CN.md)

## Overview

`local-paper-reader` is a local tool for converting research PDFs into OCR-friendly Markdown and JSON, then reviewing, translating, extracting, and correcting the content page by page.

The repository is designed for local Windows usage. It does not target cloud deployment, multi-user serving, or production hardening.

## Features

- Local PDF processing and OCR with `PaddleOCR-VL`
- Page-level OCR output in Markdown
- Merged document outputs in `paper.md` and `paper.json`
- Optional LLM post-processing for translation, structured extraction, and reading notes
- Local FastAPI-based reader UI for page-by-page review
- Manual page correction support
- Local SQLite indexing for document and task metadata

## Workflow

```text
PDF
  -> page images
  -> PaddleOCR-VL
  -> page markdown
  -> merged markdown / json
  -> optional translation / extraction / notes
  -> local review and correction
```

## Repository Layout

```text
local-paper-reader/
  src/                  application code
  scripts/              CLI and local startup entrypoints
  tests/                unit and API tests
  examples/             public demo input and output
  .env.example          configuration template
  pyproject.toml        package metadata and pytest config
  requirements.txt      dependency pins
```

## Tested Environment

The current local development environment is:

- OS: Windows
- Environment manager: `conda`
- Environment name: `paddle_ocr_cli`
- Python: `3.10.20`
- CUDA: `12.4` (`nvcc 12.4.99`)
- PaddlePaddle GPU: `3.3.0`
- PaddleOCR: `3.6.0`
- PaddleX: `3.6.1`

Additional packages currently installed in the same environment:

- FastAPI: `0.136.3`
- Uvicorn: `0.49.0`
- python-multipart: `0.0.32`
- Pydantic: `2.13.4`
- PyMuPDF: `1.27.2.3`
- OpenAI Python SDK: `2.41.0`

Notes:

- Paddle reports `cuda_compiled=True`
- The validated runtime device is `gpu:0`
- GPU availability depends on the local CUDA, driver, and Paddle build matching correctly

## Installation

Activate the target environment first:

```powershell
conda activate paddle_ocr_cli
```

Then install project dependencies:

```powershell
python -m pip install -r requirements.txt
```

Optional editable install:

```powershell
python -m pip install -e .[dev]
```

## Configuration

Create a local `.env` from the template:

```powershell
Copy-Item .\.env.example .\.env
```

Core settings:

```env
OCR_BACKEND=python-local
PADDLEOCR_PIPELINE_VERSION=v1.6
PDF_RENDER_DPI=200
OUTPUT_ROOT=outputs
DATABASE_PATH=outputs/reader.sqlite3
LLM_BACKEND=disabled
TARGET_LANGUAGE=zh-CN
EXTRACTION_PROFILE=literature
```

Key configuration groups:

- OCR backend:
  `OCR_BACKEND`, `PADDLEOCR_PIPELINE_VERSION`, `PADDLEOCR_DEVICE`, `PADDLEOCR_ENGINE`
- Output and upload control:
  `OUTPUT_ROOT`, `DATABASE_PATH`, `MAX_UPLOAD_BYTES`
- Optional LLM post-processing:
  `LLM_BACKEND`, `LLM_MODEL_NAME`, `LLM_API_KEY`, backend base URLs

## Running the Project

Run the environment self-check:

```powershell
python .\scripts\process_pdf_cli.py --self-check
```

Start the local server:

```powershell
python .\scripts\run_server.py --host 127.0.0.1 --port 8000
```

Or use the helper script after activating the environment:

```powershell
.\scripts\start_local.ps1
```

Open:

[http://127.0.0.1:8000](http://127.0.0.1:8000)

## CLI Usage

Pure OCR:

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf
```

OCR with translation, extraction, and reading notes:

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf --translate --extract --reading-notes --target-language zh-CN
```

OCR with glossary-assisted translation:

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf --translate --glossary .\glossary.md
```

## Web API

Main endpoints:

- `POST /documents`
- `GET /documents`
- `GET /documents/{document_id}`
- `DELETE /documents/{document_id}`
- `GET /tasks/{task_id}`
- `GET /documents/{document_id}/reader`
- `GET /documents/{document_id}/pages/{page_number}`
- `POST /documents/{document_id}/pages/{page_number}/corrections`
- `POST /documents/{document_id}/translate`
- `POST /documents/{document_id}/extract`

## Output Structure

```text
outputs/
  reader.sqlite3
  <document_id>/
    source/original.pdf
    pages/page_001.png
    ocr_pages/page_001.md
    raw/page_001.txt
    corrections/page_001.md
    paper.md
    paper.json
    translated.zh-CN.md
    structured.json
    reading_notes.json
    quality_report.json
    manifest.json
    logs/run.log
```

## Tests

Run:

```powershell
python -m pytest -q
```

If the environment has temp/cache permission restrictions:

```powershell
python -m pytest -q --basetemp .\.tmp_pytest -o cache_dir=.\.tmp_pytest_cache
```

## Demo Files

The public release includes:

- `examples/demo.pdf`
- `examples/demo_output/paper.md`
- `examples/demo_output/reader.md`
- `examples/demo_output/manifest.json`

The demo manifest is sanitized. Local databases, logs, historical outputs, and absolute local paths are intentionally excluded.

## Privacy and Scope

This repository does not include:

- `.env`
- real API keys or tokens
- local SQLite databases
- historical `outputs/`
- private paper collections
- editor state, caches, or logs

The project is suitable as a local workflow tool or a starting point for further development. It is not intended as a production SaaS OCR service.
