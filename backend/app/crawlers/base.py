from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.schemas.crawl_source import CrawlSourceRead


@dataclass(slots=True)
class CrawledDocument:
    url: str
    title: str | None = None
    markdown: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CrawlResult:
    crawler: str
    documents: list[CrawledDocument] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    pages_visited: int = 0
    detail_urls_discovered: int = 0
    expected_documents: int | None = None
    discovery_exhausted: bool = False


class BaseCrawler(ABC):
    name: str

    @abstractmethod
    async def crawl(self, crawl_source: CrawlSourceRead) -> CrawlResult:
        raise NotImplementedError
