from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from uuid import uuid4

from app.core.config import BACKEND_ROOT, get_settings, resolve_backend_path


class DocumentFileStore:
    """Owns PDF paths and filesystem operations for the document library."""

    @staticmethod
    def safe_filename(filename: str) -> str:
        cleaned = Path(filename).name.strip()
        if not cleaned or not cleaned.lower().endswith(".pdf"):
            raise ValueError("Only PDF files are supported.")
        return cleaned

    @staticmethod
    def checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def relative_path(path: Path) -> str:
        return str(path.resolve().relative_to(BACKEND_ROOT.resolve()))

    def save(self, filename: str, content: bytes, document_id: str | None = None) -> Path:
        safe_name = self.safe_filename(filename)
        identifier = document_id or str(uuid4())
        folder = self._pdf_dir() / identifier
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe_name
        path.write_bytes(content)
        return path

    def copy(self, source_path: Path, document_id: str | None = None) -> Path:
        safe_name = self.safe_filename(source_path.name)
        identifier = document_id or str(uuid4())
        folder = self._pdf_dir() / identifier
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / safe_name
        shutil.copy2(source_path, target)
        return target

    def resolve(self, relative_path: str) -> Path:
        path = self.path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF file not found: {relative_path}")
        return path

    @staticmethod
    def path(relative_path: str) -> Path:
        return BACKEND_ROOT / relative_path

    @staticmethod
    def delete(path: Path) -> None:
        if not path.is_file():
            return
        path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass

    def discover(self) -> list[Path]:
        paths: list[Path] = []
        for root in self._pdf_roots():
            if root.exists():
                paths.extend(root.rglob("*.pdf"))
        return sorted(set(paths), key=lambda item: str(item).lower())

    @staticmethod
    def is_pdf(content: bytes) -> bool:
        return content.startswith(b"%PDF")

    @staticmethod
    def _pdf_dir() -> Path:
        path = resolve_backend_path(get_settings().document_storage_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _legacy_pdf_dir() -> Path:
        return resolve_backend_path(get_settings().legacy_document_storage_dir)

    def _pdf_roots(self) -> list[Path]:
        pdf_dir = self._pdf_dir()
        legacy_pdf_dir = self._legacy_pdf_dir()
        roots = [pdf_dir]
        if legacy_pdf_dir.exists() and legacy_pdf_dir.resolve() != pdf_dir.resolve():
            roots.append(legacy_pdf_dir)
        return roots


document_file_store = DocumentFileStore()
