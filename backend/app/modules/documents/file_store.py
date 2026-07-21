from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from uuid import uuid4

from app.core.config import BACKEND_ROOT, get_settings, resolve_backend_path

# Extension -> MIME type for every source format the ingestion pipeline
# understands. Keep in sync with the extractor dispatch in extraction.py.
SUPPORTED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class DocumentFileStore:
    """Owns document paths and filesystem operations for the document library."""

    @staticmethod
    def safe_filename(filename: str) -> str:
        cleaned = Path(filename).name.strip()
        extension = Path(cleaned).suffix.lower()
        if not cleaned or extension not in SUPPORTED_MIME_TYPES:
            supported = ", ".join(sorted(SUPPORTED_MIME_TYPES))
            raise ValueError(f"Unsupported file type. Supported formats: {supported}")
        return cleaned

    @staticmethod
    def mime_type_for(filename: str) -> str:
        extension = Path(filename).suffix.lower()
        return SUPPORTED_MIME_TYPES.get(extension, "application/octet-stream")

    @staticmethod
    def checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def relative_path(path: Path) -> str:
        return str(path.resolve().relative_to(BACKEND_ROOT.resolve()))

    def save(self, filename: str, content: bytes, document_id: str | None = None) -> Path:
        safe_name = self.safe_filename(filename)
        identifier = document_id or str(uuid4())
        folder = self._document_dir() / identifier
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe_name
        path.write_bytes(content)
        return path

    def copy(self, source_path: Path, document_id: str | None = None) -> Path:
        safe_name = self.safe_filename(source_path.name)
        identifier = document_id or str(uuid4())
        folder = self._document_dir() / identifier
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / safe_name
        shutil.copy2(source_path, target)
        return target

    def resolve(self, relative_path: str) -> Path:
        path = self.path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"Document file not found: {relative_path}")
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
        for root in self._document_roots():
            if root.exists():
                for extension in SUPPORTED_MIME_TYPES:
                    paths.extend(root.rglob(f"*{extension}"))
        return sorted(set(paths), key=lambda item: str(item).lower())

    @staticmethod
    def is_valid_content(filename: str, content: bytes) -> bool:
        extension = Path(filename).suffix.lower()
        if extension == ".pdf":
            return content.startswith(b"%PDF")
        if extension == ".docx":
            # .docx is a zip archive (OOXML); a real PDF/text file won't
            # start with the zip local-file-header magic bytes.
            return content.startswith(b"PK\x03\x04")
        if extension in (".txt", ".md"):
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                return False
            return b"\x00" not in content
        return False

    @staticmethod
    def _document_dir() -> Path:
        path = resolve_backend_path(get_settings().document_storage_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _legacy_document_dir() -> Path:
        return resolve_backend_path(get_settings().legacy_document_storage_dir)

    def _document_roots(self) -> list[Path]:
        document_dir = self._document_dir()
        legacy_document_dir = self._legacy_document_dir()
        roots = [document_dir]
        if legacy_document_dir.exists() and legacy_document_dir.resolve() != document_dir.resolve():
            roots.append(legacy_document_dir)
        return roots


document_file_store = DocumentFileStore()
