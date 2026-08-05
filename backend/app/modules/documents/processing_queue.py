from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_CONCURRENT_DOCUMENT_JOBS = 3
DocumentProcessor = Callable[[str], None]


@dataclass(frozen=True)
class QueueState:
    status: str
    position: int | None = None


@dataclass(frozen=True)
class _QueueItem:
    document_id: str
    processor: DocumentProcessor


class DocumentProcessingQueue:
    """FIFO worker queue shared by every request handled by this app instance."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_DOCUMENT_JOBS) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        self.max_concurrent = max_concurrent
        self._queue: asyncio.Queue[_QueueItem] | None = None
        self._workers: list[asyncio.Task[None]] = []
        self._queued_ids: list[str] = []
        self._active_ids: set[str] = set()

    async def start(self) -> None:
        if self._workers:
            return
        self._queue = asyncio.Queue()
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"document-worker-{index + 1}")
            for index in range(self.max_concurrent)
        ]
        logger.info("Document processing queue started with %d workers", self.max_concurrent)

    # Give in-flight jobs a bounded grace period on shutdown; a single stuck
    # OCR job must not block application shutdown indefinitely.
    STOP_DRAIN_TIMEOUT_SECONDS = 30.0

    async def stop(self) -> None:
        if not self._workers:
            return
        try:
            await asyncio.wait_for(self.join(), timeout=self.STOP_DRAIN_TIMEOUT_SECONDS)
        except TimeoutError:
            logger.warning(
                "Document queue did not drain within %.0fs; cancelling workers with "
                "jobs still pending",
                self.STOP_DRAIN_TIMEOUT_SECONDS,
            )
        workers, self._workers = self._workers, []
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        self._queue = None
        self._queued_ids.clear()
        self._active_ids.clear()
        logger.info("Document processing queue stopped")

    async def enqueue(self, document_id: str, processor: DocumentProcessor) -> QueueState:
        if not self._workers or self._queue is None:
            await self.start()
        if document_id in self._active_ids:
            return QueueState(status="processing")
        if document_id in self._queued_ids:
            return QueueState(status="queued", position=self._queued_ids.index(document_id) + 1)

        self._queued_ids.append(document_id)
        await self._queue.put(_QueueItem(document_id=document_id, processor=processor))
        state = self.state(document_id) or QueueState(status="queued")
        logger.info(
            "Document %s entered processing queue (position=%s)",
            document_id,
            state.position,
        )
        return state

    def state(self, document_id: str) -> QueueState | None:
        if document_id in self._active_ids:
            return QueueState(status="processing")
        try:
            return QueueState(status="queued", position=self._queued_ids.index(document_id) + 1)
        except ValueError:
            return None

    async def join(self) -> None:
        if self._queue is not None:
            await self._queue.join()

    async def _worker(self, index: int) -> None:
        assert self._queue is not None
        while True:
            item = await self._queue.get()
            try:
                try:
                    self._queued_ids.remove(item.document_id)
                except ValueError:
                    pass
                self._active_ids.add(item.document_id)
                logger.info(
                    "Document worker %d started %s (%d/%d slots active)",
                    index + 1,
                    item.document_id,
                    len(self._active_ids),
                    self.max_concurrent,
                )
                await asyncio.to_thread(item.processor, item.document_id)
            except Exception:
                logger.exception("Queued document processing failed for %s", item.document_id)
            finally:
                self._active_ids.discard(item.document_id)
                self._queue.task_done()


document_processing_queue = DocumentProcessingQueue()
