import asyncio
import threading

from app.modules.documents.processing_queue import DocumentProcessingQueue


async def test_processing_queue_limits_global_concurrency_to_three() -> None:
    queue = DocumentProcessingQueue(max_concurrent=3)
    release = threading.Event()
    lock = threading.Lock()
    started: list[str] = []
    active = 0
    peak_active = 0

    def processor(document_id: str) -> None:
        nonlocal active, peak_active
        with lock:
            started.append(document_id)
            active += 1
            peak_active = max(peak_active, active)
        release.wait(timeout=5)
        with lock:
            active -= 1

    await queue.start()
    try:
        for index in range(5):
            await queue.enqueue(f"document-{index}", processor)

        for _ in range(100):
            with lock:
                if len(started) == 3:
                    break
            await asyncio.sleep(0.01)

        with lock:
            assert set(started) == {"document-0", "document-1", "document-2"}
            assert active == 3
            assert peak_active == 3
        assert queue.state("document-3").status == "queued"
        assert queue.state("document-3").position == 1
        assert queue.state("document-4").position == 2

        release.set()
        await asyncio.wait_for(queue.join(), timeout=5)

        assert queue.state("document-4") is None
        assert peak_active == 3
        assert set(started) == {
            "document-0",
            "document-1",
            "document-2",
            "document-3",
            "document-4",
        }
    finally:
        release.set()
        await queue.stop()
