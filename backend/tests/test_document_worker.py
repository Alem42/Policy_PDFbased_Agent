import asyncio
import os
import signal
import sys

import pytest

from app.modules.documents import worker


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals only")
def test_sigterm_stops_queue_and_closes_database(monkeypatch):
    calls = []

    class FakeQueue:
        def __init__(self, max_concurrent):
            calls.append(("init", max_concurrent))

        async def start(self):
            calls.append("start")
            os.kill(os.getpid(), signal.SIGTERM)

        async def stop(self):
            calls.append("stop")

    async def connect():
        calls.append("connect")

    async def disconnect():
        calls.append("disconnect")

    monkeypatch.setattr(worker, "DocumentProcessingQueue", FakeQueue)
    monkeypatch.setattr(worker.database, "connect", connect)
    monkeypatch.setattr(worker.database, "disconnect", disconnect)
    monkeypatch.setattr(worker, "validate_document_task_schema", lambda: None)
    monkeypatch.setattr(worker.get_settings(), "database_enabled", True)

    asyncio.run(asyncio.wait_for(worker.run(2), timeout=5))

    assert calls == ["connect", ("init", 2), "start", "stop", "disconnect"]
