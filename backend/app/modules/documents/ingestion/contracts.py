from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class UploadedDocument:
    document_id: UUID
    file_path: Path
    filename: str
    content_type: str | None = None


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class DocumentChunk:
    document_id: UUID
    chunk_index: int
    text: str
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class DocumentTextExtractor(Protocol):
    async def extract(self, document: UploadedDocument) -> list[ExtractedPage]:
        """Extract page-aware text from an uploaded document."""


class DocumentChunker(Protocol):
    def split(self, document_id: UUID, pages: list[ExtractedPage]) -> list[DocumentChunk]:
        """Split extracted text into retrieval chunks."""


class IngestionPipeline(Protocol):
    async def process(self, document: UploadedDocument) -> list[DocumentChunk]:
        """Run extraction, cleaning, chunking, and indexing."""
