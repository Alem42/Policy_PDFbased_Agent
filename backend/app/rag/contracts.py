from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from app.ingestion.contracts import DocumentChunk


@dataclass(frozen=True)
class RetrievalQuery:
    question: str
    document_ids: list[UUID] = field(default_factory=list)
    filters: dict[str, object] = field(default_factory=dict)
    top_k: int = 6


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    citations: list[RetrievedChunk]


class EmbeddingProvider(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Create embeddings for document chunks or queries."""


class Retriever(Protocol):
    async def retrieve(self, query: RetrievalQuery) -> list[RetrievedChunk]:
        """Return chunks scoped by selected documents and metadata."""


class AnswerGenerator(Protocol):
    async def generate(
        self,
        query: RetrievalQuery,
        chunks: list[RetrievedChunk],
    ) -> GeneratedAnswer:
        """Generate a source-grounded answer from retrieved chunks."""
