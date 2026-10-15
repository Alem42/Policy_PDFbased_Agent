from __future__ import annotations

import codecs
import hashlib
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.config import BACKEND_ROOT, get_settings, resolve_backend_path
from app.modules.documents.exceptions import UploadTooLargeError

# Extension -> MIME type for every source format the ingestion pipeline
# understands. Keep in sync with the extractor dispatch in extraction.py.
SUPPORTED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


@dataclass(frozen=True)
class StagedUpload:
    filename: str
    path: Path
    file_size: int
    checksum: str


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
    def normalized_content_hash(text: str) -> str:
        """Hash of whitespace-collapsed, lower-cased extracted text (L2 dedup).

        Unlike `checksum()` (exact bytes), this catches re-saved/reformatted
        copies of the same content — different file bytes, same words.
        """
        normalized = re.sub(r"\s+", " ", text).strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

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

    def stage_upload(
        self,
        filename: str,
        source: BinaryIO,
        *,
        max_bytes: int,
        chunk_bytes: int,
    ) -> StagedUpload:
        """Copy a spooled upload once with bounded buffers and incremental validation."""
        safe_name = self.safe_filename(filename)
        extension = Path(safe_name).suffix.lower()
        staging_dir = self._document_dir() / ".uploads"
        staging_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        file_size = 0
        prefix = b""
        decoder = codecs.getincrementaldecoder("utf-8")() if extension in {".txt", ".md"} else None
        temporary_path: Path | None = None
        invalid_content = f"{safe_name} does not look like a valid file of its type."
        try:
            with tempfile.NamedTemporaryFile(
                dir=staging_dir, suffix=".part", delete=False
            ) as destination:
                temporary_path = Path(destination.name)
                while chunk := source.read(chunk_bytes):
                    file_size += len(chunk)
                    if file_size > max_bytes:
                        raise UploadTooLargeError(max_bytes)
                    prefix = (prefix + chunk[:4])[:4] if len(prefix) < 4 else prefix
                    if decoder is not None:
                        if b"\x00" in chunk:
                            raise ValueError(invalid_content)
                        decoder.decode(chunk, final=False)
                    digest.update(chunk)
                    destination.write(chunk)
                if decoder is not None:
                    decoder.decode(b"", final=True)
                elif not self.is_valid_content(safe_name, prefix):
                    raise ValueError(invalid_content)
            return StagedUpload(safe_name, temporary_path, file_size, digest.hexdigest())
        except BaseException as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            if isinstance(exc, UnicodeDecodeError):
                raise ValueError(invalid_content) from exc
            raise

    def publish_upload(self, staged: StagedUpload, document_id: str) -> Path:
        """Move a completed upload atomically on the same storage filesystem."""
        folder = self._document_dir() / document_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / staged.filename
        try:
            staged.path.replace(path)
        except BaseException:
            folder.rmdir()
            raise
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
