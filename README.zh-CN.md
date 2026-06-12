# local-paper-reader

> 一个基于 PaddleOCR-VL 的本地优先论文阅读工具，用于 PDF OCR、双语阅读、结构化抽取和人工校对。

[English](README.md) | 简体中文

`local-paper-reader` 是一个面向本地研究工作流的论文 PDF 处理工具。它可以把论文 PDF 转成适合阅读和后续处理的 Markdown / JSON，然后再做翻译、结构化抽取、阅读笔记和页级人工校正。

这个仓库主要面向 Windows 本地环境，最初就是围绕作者自己的日常科研阅读流程搭建的。它不是云服务，也不是一个通用 OCR 平台。

## 项目能做什么

- 本地上传或处理论文 PDF
- 使用 `PaddleOCR-VL` 对页面图片做 OCR
- 生成合并后的 `paper.md` 和 `paper.json`
- 可选接入 LLM 做翻译、结构化抽取、阅读笔记
- 在本地网页阅读器里逐页查看 OCR 结果
- 保存人工校正内容
- 使用 SQLite 建立本地索引，方便浏览和管理

## 工作流

核心处理流程：

`PDF -> page images -> PaddleOCR-VL -> page markdown -> merged markdown/json -> optional translation/extraction -> local review`

典型产物包括：

- 原始 PDF 副本
- 每页 PNG 图像
- 页级 OCR Markdown
- 合并后的 `paper.md`
- 合并后的 `paper.json`
- 可选的翻译 Markdown
- 可选的结构化抽取 JSON
- 可选的阅读笔记 JSON
- `manifest.json` 和日志

## 适用范围

这个项目是明确的本地优先工具：

- 默认 OCR 在本机运行
- 默认输出写入本地文件系统
- 不包含登录鉴权、多用户隔离或正式部署能力
- 更适合个人使用，或者小范围实验室内部使用

## 已验证的本地环境

作者本地验证环境：

- 操作系统：Windows
- Python 环境管理：`conda`
- conda 环境名：`paddle_ocr_cli`
- 已验证 Python 路径：
  `C:\Users\25306\anaconda3\envs\paddle_ocr_cli\python.exe`

可以先这样检查环境：

```powershell
conda activate paddle_ocr_cli
python -m pip show paddleocr paddlepaddle-gpu paddlex fastapi
```

请注意：

- `paddlepaddle-gpu` 强依赖你本机的 CUDA、显卡和驱动版本
- 如果 Paddle 环境本身装不起来，应先解决 Paddle / PaddleOCR 的兼容性，再回到这个项目

## 仓库结构

```text
local-paper-reader/
  src/                  FastAPI 应用、服务层、配置与工具函数
  scripts/              CLI 入口和本地启动脚本
  tests/                单元测试和接口契约测试
  examples/             可公开的演示输入 / 输出
  .env.example          配置模板
  pyproject.toml        包信息与 pytest 配置
  requirements.txt      固定依赖版本
```

## 隐私与安全

这个公开仓库刻意排除了以下内容：

- `.env`
- API key / token
- 本地 SQLite 数据库
- 历史 `outputs/`
- 私人的论文原文集合
- 日志、缓存、编辑器状态

如果你基于这个仓库继续开发，建议把你自己的 `.env`、输出目录和论文原文都放在版本控制之外。

## 安装方式

### 1. 激活环境

```powershell
conda activate paddle_ocr_cli
```

如果你还没有可用的 Paddle 环境，请先创建并确认 Paddle 相关依赖可正常导入，再安装本项目依赖。

### 2. 安装依赖

推荐任选一种方式：

```powershell
python -m pip install -r requirements.txt
```

或：

```powershell
python -m pip install -e .[dev]
```

## 配置说明

先复制模板：

```powershell
Copy-Item .\.env.example .\.env
```

常用配置：

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

### OCR 相关

- `OCR_BACKEND=python-local`
  使用本地 PaddleOCR Python 后端
- `PADDLEOCR_PIPELINE_VERSION=v1.6`
  与当前项目使用的 OCR pipeline 版本保持一致
- `PADDLEOCR_DEVICE=`
  可选，指定设备，例如 `cpu`
- `PADDLEOCR_ENGINE=`
  可选，指定底层引擎

### 输出相关

- `OUTPUT_ROOT=outputs`
  本地产物输出目录
- `DATABASE_PATH=outputs/reader.sqlite3`
  SQLite 索引数据库路径
- `MAX_UPLOAD_BYTES=104857600`
  Web 上传大小限制

### 可选的 LLM 后处理

默认配置为：

```env
LLM_BACKEND=disabled
```

如果你想开启翻译、抽取或阅读笔记，可以使用：

- `lmstudio`
- `deepseek`

开启后还需要补全：

- `LLM_MODEL_NAME`
- `LLM_API_KEY`（如果后端需要）
- 对应的 base URL（如果默认值不适合你的环境）

## 如何运行

### 快速启动

项目附带了一个本地启动脚本，你可以显式指定 Python：

```powershell
.\scripts\start_local.ps1 -Python "C:\Users\25306\anaconda3\envs\paddle_ocr_cli\python.exe"
```

### 手动启动

先做一次自检：

```powershell
python .\scripts\process_pdf_cli.py --self-check
```

再启动服务：

```powershell
python .\scripts\run_server.py --host 127.0.0.1 --port 8000
```

打开：

[http://127.0.0.1:8000](http://127.0.0.1:8000)

## CLI 用法

### 只做 OCR

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf
```

### OCR + 翻译 + 抽取 + 阅读笔记

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf --translate --extract --reading-notes --target-language zh-CN
```

### OCR + 术语表翻译

```powershell
python .\scripts\process_pdf_cli.py .\examples\demo.pdf --translate --glossary .\glossary.md
```

### 仅做环境自检

```powershell
python .\scripts\process_pdf_cli.py --self-check
```

## Web API

主要接口：

- `POST /documents`：上传 PDF 并创建 OCR 任务
- `GET /documents`：列出已索引文档
- `GET /documents/{document_id}`：查看文档状态
- `DELETE /documents/{document_id}`：删除文档索引和本地输出目录
- `GET /tasks/{task_id}`：查看任务状态
- `GET /documents/{document_id}/reader`：获取阅读器数据
- `GET /documents/{document_id}/pages/{page_number}`：获取页级 OCR / 翻译 / 校正 / 图像信息
- `POST /documents/{document_id}/pages/{page_number}/corrections`：保存人工校正
- `POST /documents/{document_id}/translate`：生成翻译
- `POST /documents/{document_id}/extract`：生成结构化抽取

## 输出目录结构

典型结构如下：

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

运行测试：

```powershell
python -m pytest -q
```

如果你的环境对临时目录 / cache 权限比较严格，可以这样跑：

```powershell
python -m pytest -q --basetemp .\.tmp_pytest -o cache_dir=.\.tmp_pytest_cache
```

多数测试并不需要真实触发 PaddleOCR 推理，重点覆盖的是本地服务逻辑和接口行为。

## 演示文件

公开包中包含一个小型演示集：

- `examples/demo.pdf`
- `examples/demo_output/paper.md`
- `examples/demo_output/reader.md`
- `examples/demo_output/manifest.json`

说明：

- `manifest.json` 已做脱敏处理
- 已去掉本地绝对路径
- 不包含数据库、日志和历史批量输出
- 为了减小体积，演示集没有附带页面图片资源

## 当前限制

- 当前主要面向 Windows 本地工作流
- 不包含正式生产部署方案
- 进程重启后的后台任务恢复能力还不完整
- OCR 的可用性和速度高度依赖本地 Paddle 环境
- 大文件、多用户和服务端加固不在当前目标范围内

## 适合谁使用

如果你想做下面这些事情，这个仓库比较适合：

- 改造成你自己的本地论文阅读流程
- 在 OCR 后面继续接更多后处理能力
- 基于现有项目继续二次开发或 vibe coding

如果你的目标是直接做一个线上 SaaS OCR 平台，这个仓库就不是面向那个方向设计的。
