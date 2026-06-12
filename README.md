# local-paper-reader

> A local-first research paper reader built on PaddleOCR-VL for PDF OCR, bilingual reading, structured extraction, and manual correction.

English | [简体中文](README.zh-CN.md)

`local-paper-reader` is a local workflow tool for turning research PDFs into OCR-friendly Markdown and JSON, then reading, translating, correcting, and extracting structured information page by page.

This repository is organized for local use on Windows and was originally built around the author's own research workflow. It is not a cloud service and does not try to be a generic OCR platform.

## ✨ What It Does

- 📄 Upload or process PDF papers locally
- 🧠 Run `PaddleOCR-VL` on page images
- 📝 Merge page OCR into `paper.md` and `paper.json`
- 🌐 Run optional LLM post-processing for translation, extraction, and reading notes
- 🔎 Review page-level OCR results in a local web reader
- ✍️ Save manual corrections for page content
- 🗂️ Keep outputs indexed with SQLite for local browsing

## 🧭 Workflow

The core workflow looks like this:

`PDF -> page images -> PaddleOCR-VL -> page markdown -> merged markdown/json -> optional translation/extraction -> local review`

Typical outputs include:

- original PDF copy
- page PNGs
- page-level OCR markdown
- merged `paper.md`
- merged `paper.json`
- optional translated markdown
- optional structured extraction JSON
- optional reading notes JSON
- manifest and logs

## 🏠 Local-First Scope

This project is intentionally designed for local usage:

- it assumes OCR runs on the local machine
- it assumes outputs are stored on the local filesystem
- it does not include authentication, multi-user isolation, or production deployment logic
- it is best suited for personal or lab-level use

## ✅ Verified Local Environment

The project was verified on the author's local Windows setup with:

- OS: Windows
- Python environment manager: `conda`
- Conda environment name: `paddle_ocr_cli`
- Verified Python path:
  `C:\Users\25306\anaconda3\envs\paddle_ocr_cli\python.exe`

Useful environment checks:

```powershell
conda activate paddle_ocr_cli
python -m pip show paddleocr paddlepaddle-gpu paddlex fastapi
```

Important note:

- `paddlepaddle-gpu` depends on your local CUDA version, GPU, and driver stack
- if installation fails, resolve Paddle/PaddleOCR compatibility first, then come back to this project

## 📦 Repository Layout

```text
local-paper-reader/
  src/                  FastAPI app, services, config, utilities
  scripts/              CLI entrypoints and local startup helpers
  tests/                unit tests and API contract checks
  examples/             safe public demo input/output
  .env.example          configuration template
  pyproject.toml        package metadata and pytest settings
  requirements.txt      pinned dependencies
```

## 🔐 Privacy and Safety

This public package intentionally excludes:

- `.env`
- API keys or tokens
- local SQLite databases
- historical `outputs/`
- personal paper collections under `articles/`
- logs, caches, and editor state

If you use this repo as a starting point, keep your own `.env`, outputs, and papers outside version control.

## ⚙️ Installation

### 1. Create or activate your environment

```powershell
conda activate paddle_ocr_cli
```

If you do not already have a working Paddle environment, create one first, then install dependencies.

### 2. Install project dependencies

Use either:

```powershell
python -m pip install -r requirements.txt
```

or:

```powershell
python -m pip install -e .[dev]
```

## 🧪 Configuration

Copy the template:

```powershell
Copy-Item .\.env.example .\.env
```

Key settings:

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

### OCR-related settings

- `OCR_BACKEND=python-local`
  Use the local PaddleOCR Python backend
- `PADDLEOCR_PIPELINE_VERSION=v1.6`
  Matches the current OCR pipeline used by this project
- `PADDLEOCR_DEVICE=`
  Optional device override, such as `cpu`
- `PADDLEOCR_ENGINE=`
  Optional engine override

### Output settings

- `OUTPUT_ROOT=outputs`
  Where local artifacts are written
- `DATABASE_PATH=outputs/reader.sqlite3`
  SQLite index path
- `MAX_UPLOAD_BYTES=104857600`
  Upload limit for the web API

### Optional LLM post-processing

By default:

```env
LLM_BACKEND=disabled
```

You can enable:

- `lmstudio`
- `deepseek`

When enabling LLM features, you must also configure:

- `LLM_MODEL_NAME`
- `LLM_API_KEY` when required
- base URL values if you are not using the defaults

## 🚀 Running the Project

### Quick local start

The included startup helper lets you provide a Python executable explicitly:

```powershell
.\scripts\start_local.ps1 -Python "C:\Users\25306\anaconda3\envs\paddle_ocr_cli\python.exe"
```

### Manual startup

Run a self-check first:

```powershell
python .\scripts\process_pdf_cli.py --self-check
```

Then start the server:

```powershell
python .\scripts\run_server.py --host 127.0.0.1 --port 8000
```

Open:

[http://127.0.0.1:8000](http://127.0.0.1:8000)

## 💻 CLI Usage

### Pure OCR

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf
```

### OCR + translation + extraction + reading notes

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf --translate --extract --reading-notes --target-language zh-CN
```

### OCR with a glossary

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf --translate --glossary .\glossary.md
```

### Self-check only

```powershell
python .\scripts\process_pdf_cli.py --self-check
```

## 🌐 Web API

Important endpoints:

- `POST /documents` - upload a PDF and create an OCR task
- `GET /documents` - list indexed documents
- `GET /documents/{document_id}` - get document status
- `DELETE /documents/{document_id}` - delete document index and local output folder
- `GET /tasks/{task_id}` - get task status
- `GET /documents/{document_id}/reader` - get reader payload
- `GET /documents/{document_id}/pages/{page_number}` - get page-level OCR, translation, correction, and image metadata
- `POST /documents/{document_id}/pages/{page_number}/corrections` - save manual corrections
- `POST /documents/{document_id}/translate` - generate translation
- `POST /documents/{document_id}/extract` - generate structured extraction

## 🗃️ Output Structure

Typical output layout:

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

## 🧪 Tests

Run tests with:

```powershell
python -m pytest -q
```

If your environment has temp/cache permission issues, use:

```powershell
python -m pytest -q --basetemp .\.tmp_pytest -o cache_dir=.\.tmp_pytest_cache
```

Most tests do not require real PaddleOCR inference and are focused on the local service logic.

## 📁 Demo Files

This release includes a small public demo set:

- `examples/demo.pdf`
- `examples/demo_output/paper.md`
- `examples/demo_output/reader.md`
- `examples/demo_output/manifest.json`

Notes:

- the demo manifest is sanitized
- absolute local paths are removed
- databases, logs, and historical outputs are intentionally omitted
- image assets are not bundled in the demo output to keep the example lightweight

## ⚠️ Current Limitations

- local Windows workflow is the primary target
- no production deployment setup
- no background job recovery across process restarts
- OCR performance and stability depend heavily on the local Paddle environment
- large-file and multi-user service hardening are out of scope

## 🤝 Intended Use

This repository is suitable if you want to:

- adapt it for your own local paper-reading workflow
- extend it with more post-processing tools
- vibe-code on top of a working OCR reader foundation

It is not intended as a drop-in hosted SaaS template.
