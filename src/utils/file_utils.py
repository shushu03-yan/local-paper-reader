from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify_filename(value: str) -> str:
    lowered = value.lower()
    sanitized = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return sanitized or "document"


def build_document_id(pdf_path: Path, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now()).strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{timestamp}_{slugify_filename(pdf_path.stem)}_{suffix}"
