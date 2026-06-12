from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from src.utils.file_utils import ensure_directory


LOCAL_OWNER = "local"
SCHEMA_VERSION = 1


SCHEMA_VERSION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


SCHEMA_V1_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    owner TEXT NOT NULL DEFAULT 'local',
    status TEXT NOT NULL,
    manifest_path TEXT,
    pages_total INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT 'local',
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pages (
    document_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    owner TEXT NOT NULL DEFAULT 'local',
    status TEXT NOT NULL,
    image_path TEXT,
    markdown_path TEXT,
    raw_path TEXT,
    attempts INTEGER DEFAULT 0,
    elapsed_seconds REAL DEFAULT 0,
    error TEXT,
    PRIMARY KEY (document_id, page_number)
);
CREATE TABLE IF NOT EXISTS artifacts (
    document_id TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT 'local',
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    PRIMARY KEY (document_id, name)
);
CREATE TABLE IF NOT EXISTS corrections (
    document_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    owner TEXT NOT NULL DEFAULT 'local',
    corrected_markdown TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id, page_number, owner)
);
CREATE TABLE IF NOT EXISTS annotations (
    annotation_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    owner TEXT NOT NULL DEFAULT 'local',
    target_side TEXT NOT NULL,
    block_index INTEGER NOT NULL,
    quote_text TEXT NOT NULL,
    note_text TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT 'yellow',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class DocumentRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        ensure_directory(db_path.parent)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_VERSION_TABLE_SQL)
            current_version = conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM schema_version",
            ).fetchone()["version"]
            if int(current_version) < SCHEMA_VERSION:
                conn.executescript(SCHEMA_V1_SQL)
                conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def upsert_task(
        self,
        task_id: str,
        document_id: str,
        status: str,
        *,
        kind: str | None = None,
        error: str | None = None,
    ) -> None:
        task_kind = kind or task_id.split("-", 1)[0]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (task_id, document_id, owner, kind, status, error)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status=excluded.status,
                    error=excluded.error,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (task_id, document_id, LOCAL_OWNER, task_kind, status, error),
            )

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Unknown task: {task_id}")
        return dict(row)

    def latest_task_for_document(self, document_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE document_id=?
                ORDER BY
                    CASE WHEN status IN ('queued', 'running') THEN 0 ELSE 1 END,
                    updated_at DESC,
                    created_at DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
        return self._row(row)

    def active_task_for_document_kind(self, document_id: str, kind: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE document_id=? AND kind=? AND status IN ('queued', 'running')
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (document_id, kind),
            ).fetchone()
        return self._row(row)

    def upsert_manifest(self, manifest_path: Path) -> None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        document_id = str(manifest["document_id"])
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (document_id, owner, status, manifest_path, pages_total)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    status=excluded.status,
                    manifest_path=excluded.manifest_path,
                    pages_total=excluded.pages_total,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    document_id,
                    LOCAL_OWNER,
                    str(manifest.get("status", "unknown")),
                    str(manifest_path),
                    int(manifest.get("pages_total") or 0),
                ),
            )
            for name, path in dict(manifest.get("artifacts", {})).items():
                conn.execute(
                    """
                    INSERT INTO artifacts (document_id, owner, name, path)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(document_id, name) DO UPDATE SET path=excluded.path
                    """,
                    (document_id, LOCAL_OWNER, str(name), str(path)),
                )
            for page in list(manifest.get("page_results", [])):
                conn.execute(
                    """
                    INSERT INTO pages (
                        document_id, page_number, owner, status, image_path,
                        markdown_path, raw_path, attempts, elapsed_seconds, error
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(document_id, page_number) DO UPDATE SET
                        status=excluded.status,
                        image_path=excluded.image_path,
                        markdown_path=excluded.markdown_path,
                        raw_path=excluded.raw_path,
                        attempts=excluded.attempts,
                        elapsed_seconds=excluded.elapsed_seconds,
                        error=excluded.error
                    """,
                    (
                        document_id,
                        int(page["page_number"]),
                        LOCAL_OWNER,
                        str(page.get("status", "unknown")),
                        str(page.get("image_path") or ""),
                        str(page.get("markdown_path") or ""),
                        str(page.get("raw_path") or ""),
                        int(page.get("attempts") or 0),
                        float(page.get("elapsed_seconds") or 0),
                        page.get("error"),
                    ),
                )

    def list_documents(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY updated_at DESC",
            ).fetchall()
        return [dict(row) for row in rows]

    def get_document(self, document_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE document_id=?",
                (document_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Unknown document: {document_id}")
        return dict(row)

    def get_page(self, document_id: str, page_number: int) -> dict[str, Any]:
        self.get_document(document_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pages WHERE document_id=? AND page_number=?",
                (document_id, page_number),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Unknown page: {document_id} page {page_number}")
        return dict(row)

    def list_artifacts(self, document_id: str) -> dict[str, str]:
        self.get_document(document_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, path FROM artifacts WHERE document_id=?",
                (document_id,),
            ).fetchall()
        return {str(row["name"]): str(row["path"]) for row in rows}

    def delete_document(self, document_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT document_id FROM documents WHERE document_id=?",
                (document_id,),
            ).fetchone()
            if row is None:
                return False
            for table in ("annotations", "corrections", "pages", "artifacts", "tasks", "documents"):
                conn.execute(f"DELETE FROM {table} WHERE document_id=?", (document_id,))
        return True

    def create_annotation(
        self,
        *,
        document_id: str,
        page_number: int,
        target_side: str,
        block_index: int,
        quote_text: str,
        note_text: str,
        color: str,
    ) -> dict[str, Any]:
        self.get_document(document_id)
        annotation_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO annotations (
                    annotation_id, document_id, page_number, owner, target_side,
                    block_index, quote_text, note_text, color
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    annotation_id,
                    document_id,
                    page_number,
                    LOCAL_OWNER,
                    target_side,
                    block_index,
                    quote_text,
                    note_text,
                    color,
                ),
            )
        annotation = self.get_annotation(document_id, annotation_id)
        if annotation is None:
            raise FileNotFoundError(f"Unknown annotation: {annotation_id}")
        return annotation

    def list_annotations(self, document_id: str, page_number: int) -> list[dict[str, Any]]:
        self.get_document(document_id)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM annotations
                WHERE document_id=? AND page_number=?
                ORDER BY created_at ASC, annotation_id ASC
                """,
                (document_id, page_number),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_annotation(self, document_id: str, annotation_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM annotations
                WHERE document_id=? AND annotation_id=?
                """,
                (document_id, annotation_id),
            ).fetchone()
        return self._row(row)

    def update_annotation(
        self,
        document_id: str,
        annotation_id: str,
        *,
        note_text: str,
        color: str,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE annotations
                SET note_text=?, color=?, updated_at=CURRENT_TIMESTAMP
                WHERE document_id=? AND annotation_id=?
                """,
                (note_text, color, document_id, annotation_id),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Unknown annotation: {annotation_id}")
            row = conn.execute(
                """
                SELECT * FROM annotations
                WHERE document_id=? AND annotation_id=?
                """,
                (document_id, annotation_id),
            ).fetchone()
        annotation = self._row(row)
        if annotation is None:
            raise FileNotFoundError(f"Unknown annotation: {annotation_id}")
        return annotation

    def delete_annotation(self, document_id: str, annotation_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM annotations
                WHERE document_id=? AND annotation_id=?
                """,
                (document_id, annotation_id),
            )
        return cursor.rowcount > 0

    def save_correction(
        self,
        document_id: str,
        page_number: int,
        corrected_markdown: str,
    ) -> dict[str, Any]:
        self.get_page(document_id, page_number)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO corrections (document_id, page_number, owner, corrected_markdown)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(document_id, page_number, owner) DO UPDATE SET
                    corrected_markdown=excluded.corrected_markdown,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (document_id, page_number, LOCAL_OWNER, corrected_markdown),
            )
        return self.get_correction(document_id, page_number)

    def get_correction(
        self,
        document_id: str,
        page_number: int,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM corrections
                WHERE document_id=? AND page_number=? AND owner=?
                """,
                (document_id, page_number, LOCAL_OWNER),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT * FROM corrections
                    WHERE document_id=? AND page_number=?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (document_id, page_number),
                ).fetchone()
        return self._row(row)
