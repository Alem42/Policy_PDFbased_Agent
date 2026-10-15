"""Fixed background workers poll PostgreSQL; pending tasks survive process death."""

import asyncio
import logging
from dataclasses import dataclass
from uuid import uuid4

from app.core.config import get_settings
from app.modules.documents.repositories.tasks import LostTaskLease, document_task_repository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueueState:
    status: str
    position: int | None = None
    task: dict | None = None


class DocumentProcessingQueue:
    STOP_DRAIN_TIMEOUT_SECONDS = 10

    def __init__(self, max_concurrent: int | None = None, *, repository=None, processor=None):
        self.max_concurrent = max_concurrent
        self.repository = repository or document_task_repository
        self.processor = processor
        self._workers: list[asyncio.Task] = []
        self._wakeup: asyncio.Event | None = None
        self._stopping = False
        self.instance_id = str(uuid4())

    async def start(self) -> None:
        if self._workers or not get_settings().database_enabled:
            return
        count = self.max_concurrent
        if count is None:
            count = get_settings().document_task_workers
        self._stopping = False
        self._wakeup = asyncio.Event()
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"document-worker-{index + 1}")
            for index in range(count)
        ]
        logger.info(
            "Durable document workers started: instance=%s count=%d", self.instance_id, count
        )

    async def stop(self) -> None:
        self._stopping = True
        self.notify()
        if not self._workers:
            return
        _, pending = await asyncio.wait(self._workers, timeout=self.STOP_DRAIN_TIMEOUT_SECONDS)
        for worker in pending:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        # No task is removed from PostgreSQL. Unfinished claims recover after lease expiry.

    def notify(self) -> None:
        if self._wakeup is not None:
            self._wakeup.set()

    async def enqueue(self, document_id: str, task_type: str = "ingest") -> QueueState:
        task = await asyncio.to_thread(self.repository.enqueue, document_id, task_type)
        self.notify()
        return QueueState("processing" if task["status"] == "running" else "queued", task=task)

    async def state(self, document_id: str) -> QueueState | None:
        task = await asyncio.to_thread(self.repository.for_document, document_id)
        if task is None:
            return None
        position = None
        if task["status"] == "queued":
            position = await asyncio.to_thread(self.repository.queue_position, task)
        status = "processing" if task["status"] == "running" else task["status"]
        return QueueState(status, position, task)

    async def _heartbeat(self, task: dict) -> None:
        while True:
            await asyncio.sleep(get_settings().document_task_heartbeat_seconds)
            try:
                if not await asyncio.to_thread(self.repository.heartbeat, task):
                    return
            except Exception:
                logger.exception("Task heartbeat failed: task=%s", task["id"])

    async def _worker(self, index: int) -> None:
        from app.modules.documents.service.pipeline import execute_document_task

        processor = self.processor or execute_document_task
        worker_id = f"{self.instance_id}:{index + 1}"
        while not self._stopping:
            try:
                task = await asyncio.to_thread(self.repository.claim, worker_id)
                if task is None:
                    self._wakeup.clear()
                    try:
                        await asyncio.wait_for(
                            self._wakeup.wait(), timeout=get_settings().document_task_poll_seconds
                        )
                    except TimeoutError:
                        pass
                    continue
                logger.info(
                    "Claimed document task: task=%s document=%s attempt=%d worker=%s",
                    task["id"],
                    task["document_id"],
                    task["attempts"],
                    worker_id,
                )
                heartbeat = asyncio.create_task(self._heartbeat(task))
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(processor, task),
                        timeout=get_settings().document_task_execution_timeout_seconds,
                    )
                except LostTaskLease:
                    logger.warning("Discarded stale document task attempt: %s", task["id"])
                except Exception as exc:
                    if isinstance(exc, TimeoutError) and not str(exc):
                        exc = TimeoutError(
                            "Document processing exceeded the configured execution time limit."
                        )
                    try:
                        await asyncio.to_thread(self.repository.fail, task, exc)
                        logger.warning(
                            "Document task attempt failed: task=%s error=%s", task["id"], exc
                        )
                    except LostTaskLease:
                        logger.warning("Failed attempt no longer owns task: %s", task["id"])
                finally:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Document worker polling failed: worker=%s", worker_id)
                await asyncio.sleep(get_settings().document_task_poll_seconds)


document_processing_queue = DocumentProcessingQueue()
