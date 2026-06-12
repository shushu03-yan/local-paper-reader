# local-paper-reader

> 一个基于 PaddleOCR-VL 的本地优先论文阅读工具，用于 PDF OCR、双语阅读、结构化抽取和人工校对。

[English](README.md) | 简体中文

## 项目简介

`local-paper-reader` 用于将研究论文 PDF 转换为适合后续处理的 Markdown 和 JSON，并提供逐页阅读、翻译、结构化抽取和人工校正能力。

这个仓库面向本地 Windows 环境使用，不以云部署、多用户服务或生产级加固为目标。

## 主要功能

- 使用 `PaddleOCR-VL` 在本地处理 PDF 并完成 OCR
- 生成页级 OCR Markdown
- 生成合并后的 `paper.md` 和 `paper.json`
- 可选接入 LLM 完成翻译、结构化抽取和阅读笔记
- 提供基于 FastAPI 的本地阅读器界面
- 支持页级人工校正
- 使用本地 SQLite 保存文档和任务索引

## 工作流

```text
PDF
  -> page images
  -> PaddleOCR-VL
  -> page markdown
  -> merged markdown / json
  -> optional translation / extraction / notes
  -> local review and correction
```

## 仓库结构

```text
local-paper-reader/
  src/                  应用代码
  scripts/              CLI 和本地启动脚本
  tests/                单元测试和接口测试
  examples/             公开演示输入和输出
  .env.example          配置模板
  pyproject.toml        包信息和 pytest 配置
  requirements.txt      依赖版本约束
```

## 已验证环境

当前本地开发环境为：

- 操作系统：Windows
- 环境管理器：`conda`
- 环境名：`paddle_ocr_cli`
- Python：`3.10.20`
- CUDA：`12.4`（`nvcc 12.4.99`）
- PaddlePaddle GPU：`3.3.0`
- PaddleOCR：`3.6.0`
- PaddleX：`3.6.1`

同一环境中的其他相关包版本：

- FastAPI：`0.136.3`
- Uvicorn：`0.49.0`
- python-multipart：`0.0.32`
- Pydantic：`2.13.4`
- PyMuPDF：`1.27.2.3`
- OpenAI Python SDK：`2.41.0`

补充说明：

- 当前 Paddle 环境报告 `cuda_compiled=True`
- 当前验证设备为 `gpu:0`
- GPU 是否可用，取决于本机 CUDA、驱动和 Paddle 安装是否匹配

## 安装

先激活目标环境：

```powershell
conda activate paddle_ocr_cli
```

再安装项目依赖：

```powershell
python -m pip install -r requirements.txt
```

如需可编辑安装：

```powershell
python -m pip install -e .[dev]
```

## 配置

从模板创建本地 `.env`：

```powershell
Copy-Item .\.env.example .\.env
```

核心配置项：

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

主要配置分组：

- OCR 后端：
  `OCR_BACKEND`、`PADDLEOCR_PIPELINE_VERSION`、`PADDLEOCR_DEVICE`、`PADDLEOCR_ENGINE`
- 输出与上传控制：
  `OUTPUT_ROOT`、`DATABASE_PATH`、`MAX_UPLOAD_BYTES`
- 可选 LLM 后处理：
  `LLM_BACKEND`、`LLM_MODEL_NAME`、`LLM_API_KEY`、各后端 base URL

## LLM 后处理说明

LLM 配置只用于 OCR 完成之后的后处理，不参与 PDF 渲染，也不参与基础 OCR 识别。

当前 LLM 能做的事情：

- 翻译
- 结构化抽取
- 阅读笔记

### 模式 1：只做 OCR，不做翻译

如果你只需要：

- PDF 转 OCR Markdown / JSON
- 本地逐页阅读
- 人工校正

那么保持：

```env
LLM_BACKEND=disabled
```

这个模式下可以直接运行：

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf
```

或者启动 Web 服务后正常上传 PDF。

### 模式 2：OCR 后继续做翻译 / 抽取 / 阅读笔记

如果你要使用翻译或其他 LLM 功能，就需要启用一个 LLM 后端，并指定模型。

#### 方案 A：LM Studio

示例配置：

```env
LLM_BACKEND=lmstudio
LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1
LLM_MODEL_NAME=<your-model-name>
TARGET_LANGUAGE=zh-CN
```

适用于你已经在本机用 LM Studio 跑起了一个兼容 OpenAI 接口的模型服务。

#### 方案 B：DeepSeek

示例配置：

```env
LLM_BACKEND=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_MODEL_NAME=<your-model-name>
LLM_API_KEY=<your-api-key>
TARGET_LANGUAGE=zh-CN
```

适用于你希望通过 DeepSeek API 来完成翻译和后处理。

### 如何触发翻译和其他 LLM 任务

CLI 示例：

只翻译：

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf --translate --target-language zh-CN
```

翻译并抽取：

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf --translate --extract --target-language zh-CN
```

翻译、抽取并生成阅读笔记：

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf --translate --extract --reading-notes --target-language zh-CN
```

Web / API 入口：

- `POST /documents/{document_id}/translate`
- `POST /documents/{document_id}/extract`

如果 `LLM_BACKEND=disabled`，这些后处理功能不会执行。

## 运行方式

先执行环境自检：

```powershell
python .\scripts\process_pdf_cli.py --self-check
```

启动本地服务：

```powershell
python .\scripts\run_server.py --host 127.0.0.1 --port 8000
```

或者在激活环境后直接运行启动脚本：

```powershell
.\scripts\start_local.ps1
```

打开：

[http://127.0.0.1:8000](http://127.0.0.1:8000)

## CLI 用法

仅执行 OCR：

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf
```

执行 OCR、翻译、抽取和阅读笔记：

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf --translate --extract --reading-notes --target-language zh-CN
```

使用术语表辅助翻译：

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf --translate --glossary .\glossary.md
```

## Web API

主要接口：

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

## 输出结构

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

## 测试

运行：

```powershell
python -m pytest -q
```

如果环境对临时目录或缓存权限有限制：

```powershell
python -m pytest -q --basetemp .\.tmp_pytest -o cache_dir=.\.tmp_pytest_cache
```

## 演示文件

公开版本包含：

- `examples/demo.pdf`
- `examples/demo_output/paper.md`
- `examples/demo_output/reader.md`
- `examples/demo_output/manifest.json`

演示用 `manifest.json` 已经过脱敏处理，不包含本地数据库、日志、历史输出或绝对路径。
