import asyncio
import threading

from app.core.config import Settings
from app.modules.documents import processing_queue as module
from app.modules.documents.processing_queue import DocumentProcessingQueue


async def test_workers_limit_concurrency_per_process_and_leave_backlog(monkeypatch):
    settings = Settings(_env_file=None, database_enabled=True, document_task_poll_seconds=0.01)
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    release = threading.Event()
    lock = threading.Lock()
    tasks = [{"id": str(i), "document_id": str(i), "status": "queued"} for i in range(5)]
    started, finished = [], []
    first_three = asyncio.Event()
    all_finished = asyncio.Event()
    loop = asyncio.get_running_loop()

    class Repository:
        def claim(self, _worker):
            with lock:
                available = next((task for task in tasks if task["status"] == "queued"), None)
                if available:
                    available["status"] = "running"
                    available["attempts"] = 1
                    return available.copy()

        def heartbeat(self, _task):
            return True

        def fail(self, _task, error):
            raise AssertionError(error)

    def process(task):
        with lock:
            started.append(task["id"])
            if len(started) == 3:
                loop.call_soon_threadsafe(first_three.set)
        assert release.wait(timeout=5)
        with lock:
            tasks[int(task["id"])]["status"] = "succeeded"
            finished.append(task["id"])
            if len(finished) == 5:
                loop.call_soon_threadsafe(all_finished.set)

    queue = DocumentProcessingQueue(3, repository=Repository(), processor=process)
    await queue.start()
    try:
        await asyncio.wait_for(first_three.wait(), timeout=3)
        assert len(started) == 3
        assert sum(task["status"] == "queued" for task in tasks) == 2
        release.set()
        await asyncio.wait_for(all_finished.wait(), timeout=3)
        assert set(finished) == {str(i) for i in range(5)}
    finally:
        release.set()
        await queue.stop()


async def test_disabled_database_does_not_start_workers():
    queue = DocumentProcessingQueue()
    await queue.start()
    assert not queue._workers


async def test_execution_timeout_returns_logical_worker_slot(monkeypatch):
    settings = Settings(
        _env_file=None,
        database_enabled=True,
        document_task_poll_seconds=0.01,
        document_task_execution_timeout_seconds=1,
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    failed = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    errors = []

    class Repository:
        claimed = False

        def claim(self, _worker):
            if not self.claimed:
                self.claimed = True
                return {"id": "timeout-task", "document_id": "document", "attempts": 1}

        def heartbeat(self, _task):
            return True

        def fail(self, _task, error):
            errors.append(error)
            release.set()
            loop.call_soon_threadsafe(failed.set)

    queue = DocumentProcessingQueue(1, repository=Repository(), processor=lambda _: release.wait(3))
    await queue.start()
    try:
        await asyncio.wait_for(failed.wait(), timeout=2)
        assert isinstance(errors[0], TimeoutError)
        assert "execution time limit" in str(errors[0])
    finally:
        release.set()
        await queue.stop()
