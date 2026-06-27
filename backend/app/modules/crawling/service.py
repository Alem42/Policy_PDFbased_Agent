from datetime import UTC, datetime
from uuid import UUID

from app.core.config import get_settings
from app.modules.crawling.attachment_downloader import attachment_downloader
from app.modules.crawling.crawlers.selector import crawler_selector
from app.modules.crawling.incremental_sync import incremental_sync_service
from app.modules.crawling.repositories.job import crawl_job_repository
from app.modules.crawling.repositories.source import crawl_source_repository
from app.modules.crawling.schemas.document import IncrementalSyncStats
from app.modules.crawling.schemas.job import CrawlJobStatus


class CrawlService:
    async def run(self, crawl_job_id: UUID) -> None:
        crawl_job = await crawl_job_repository.get(crawl_job_id)
        if crawl_job is None:
            return
        crawl_source = await crawl_source_repository.get(crawl_job.crawl_source_id)
        if crawl_source is None:
            await crawl_job_repository.update(
                crawl_job_id,
                status=CrawlJobStatus.FAILED,
                message="Crawl source was deleted before the crawl job started",
                finished_at=True,
            )
            return

        primary = crawler_selector.primary(crawl_source)
        await crawl_job_repository.update(
            crawl_job_id,
            status=CrawlJobStatus.RUNNING,
            selected_crawler=primary.name,
            started_at=datetime.now(UTC),
        )

        settings = get_settings()
        if crawl_job.dry_run or not settings.crawling_enabled:
            reason = "dry-run requested" if crawl_job.dry_run else "CRAWLING_ENABLED=false"
            await crawl_job_repository.update(
                crawl_job_id,
                status=CrawlJobStatus.SKIPPED,
                message=f"Crawl plan created with '{primary.name}'; network skipped: {reason}",
                finished_at=True,
            )
            return

        attempts = [primary, *crawler_selector.fallbacks(crawl_source)]
        errors: list[str] = []
        for crawler in attempts:
            try:
                await crawl_job_repository.update(crawl_job_id, selected_crawler=crawler.name)
                if hasattr(crawler, "crawl_batches"):
                    completed = await self._run_batched_crawl(
                        crawl_job.id,
                        crawl_source,
                        crawler,
                    )
                    if completed:
                        return
                    errors.append(f"{crawler.name}: no documents returned")
                    continue

                result = await crawler.crawl(crawl_source)
                if result.documents:
                    download_errors = await attachment_downloader.download(
                        crawl_source,
                        result.documents,
                    )
                    result.errors.extend(f"asset download: {error}" for error in download_errors)
                    is_complete = self._is_complete(crawl_source.max_documents, result)
                    mark_missing = bool(
                        crawl_source.config.get("mark_missing_on_full_crawl", False)
                    )
                    stats = await incremental_sync_service.sync(
                        crawl_source.id,
                        result.documents,
                        crawl_job_id=crawl_job.id,
                        mark_missing=mark_missing,
                    )
                    await crawl_job_repository.update(
                        crawl_job_id,
                        status=CrawlJobStatus.COMPLETED,
                        pages_visited=result.pages_visited,
                        expected_documents=result.expected_documents,
                        pages_discovered=result.detail_urls_discovered,
                        pages_succeeded=len(result.documents),
                        pages_failed=len(result.errors),
                        documents_added=stats.added,
                        documents_updated=stats.updated,
                        documents_unchanged=stats.unchanged,
                        documents_missing=stats.missing,
                        is_complete=is_complete,
                        message=(
                            "Documents persisted and incrementally merged. "
                            f"Full-site complete: {is_complete}."
                        ),
                        finished_at=True,
                    )
                    return
                errors.extend(result.errors or [f"{crawler.name}: no documents returned"])
            except Exception as exc:
                errors.append(f"{crawler.name}: {exc}")

        await crawl_job_repository.update(
            crawl_job_id,
            status=CrawlJobStatus.FAILED,
            pages_failed=len(errors),
            message=" | ".join(errors),
            finished_at=True,
        )

    async def _run_batched_crawl(
        self,
        crawl_job_id: UUID,
        crawl_source,
        crawler,
    ) -> bool:
        stats_total = IncrementalSyncStats()
        total_documents = 0
        latest_result = None

        async for result in crawler.crawl_batches(crawl_source):
            latest_result = result
            if result.documents:
                download_errors = await attachment_downloader.download(
                    crawl_source,
                    result.documents,
                )
                result.errors.extend(f"asset download: {error}" for error in download_errors)
                stats = await incremental_sync_service.sync(
                    crawl_source.id,
                    result.documents,
                    crawl_job_id=crawl_job_id,
                    mark_missing=False,
                )
                stats_total.added += stats.added
                stats_total.updated += stats.updated
                stats_total.unchanged += stats.unchanged
                stats_total.missing += stats.missing
                total_documents += len(result.documents)

            await crawl_job_repository.update(
                crawl_job_id,
                status=CrawlJobStatus.RUNNING,
                pages_visited=result.pages_visited,
                expected_documents=result.expected_documents,
                pages_discovered=result.detail_urls_discovered,
                pages_succeeded=total_documents,
                pages_failed=len(result.errors),
                documents_added=stats_total.added,
                documents_updated=stats_total.updated,
                documents_unchanged=stats_total.unchanged,
                documents_missing=stats_total.missing,
                message=f"Crawl in progress. Persisted {total_documents} documents.",
            )

        if latest_result is None:
            return False
        if total_documents == 0:
            if latest_result.errors:
                raise RuntimeError(" | ".join(latest_result.errors))
            return False

        is_complete = self._is_complete(
            crawl_source.max_documents,
            latest_result,
            documents_count=total_documents,
        )
        await crawl_job_repository.update(
            crawl_job_id,
            status=CrawlJobStatus.COMPLETED,
            pages_visited=latest_result.pages_visited,
            expected_documents=latest_result.expected_documents,
            pages_discovered=latest_result.detail_urls_discovered,
            pages_succeeded=total_documents,
            pages_failed=len(latest_result.errors),
            documents_added=stats_total.added,
            documents_updated=stats_total.updated,
            documents_unchanged=stats_total.unchanged,
            documents_missing=stats_total.missing,
            is_complete=is_complete,
            message=(
                "Documents persisted in batches and incrementally merged. "
                f"Full-site complete: {is_complete}."
            ),
            finished_at=True,
        )
        return True

    @staticmethod
    def _is_complete(
        max_documents: int | None,
        result,
        documents_count: int | None = None,
    ) -> bool:
        if result.errors:
            return False
        count = len(result.documents) if documents_count is None else documents_count
        if result.expected_documents is not None:
            return (
                result.detail_urls_discovered >= result.expected_documents
                and count >= result.expected_documents
            )
        if max_documents is not None and count >= max_documents:
            return False
        return result.discovery_exhausted


crawl_service = CrawlService()
