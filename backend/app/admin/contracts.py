from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from app.schemas.admin import CredibilityLevel, ProcessingStatus


@dataclass(frozen=True)
class AdminDocumentMetadata:
    title: str
    source_organisation: str
    policy_area: str
    source_url: str | None = None
    country_or_region: str | None = None
    published_year: int | None = None
    tags: list[str] = field(default_factory=list)
    credibility_level: CredibilityLevel = CredibilityLevel.UNKNOWN


class AdminDocumentService(Protocol):
    async def create_document(self, metadata: AdminDocumentMetadata) -> UUID:
        """Create a trusted document record."""

    async def update_metadata(self, document_id: UUID, metadata: AdminDocumentMetadata) -> None:
        """Update document metadata after admin review."""

    async def mark_processing_status(
        self,
        document_id: UUID,
        status: ProcessingStatus,
        message: str | None = None,
    ) -> None:
        """Update processing progress for a document."""
