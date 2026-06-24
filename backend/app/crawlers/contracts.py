from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class TrustedSource:
    id: UUID
    name: str
    start_url: str
    allowed_domains: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass(frozen=True)
class DiscoveredDocument:
    source_id: UUID
    url: str
    title: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CrawlResult:
    source_id: UUID
    discovered_documents: list[DiscoveredDocument]
    pages_visited: int = 0
    errors: list[str] = field(default_factory=list)


class Crawler(Protocol):
    async def crawl(self, source: TrustedSource, max_pages: int) -> CrawlResult:
        """Discover candidate policy documents from a trusted source."""
