"""Optional separate worker process: python -m app.modules.documents.worker --concurrency 3."""

import argparse
import asyncio
import logging
import signal

from app.core.config import get_settings
from app.core.database import database
from app.modules.documents.processing_queue import DocumentProcessingQueue
from app.modules.documents.schema import validate_document_task_schema


async def run(concurrency: int, *, warmup: bool = False) -> None:
    if not get_settings().database_enabled:
        raise RuntimeError("Worker requires DATABASE_ENABLED=true.")
    await database.connect()
    queue = DocumentProcessingQueue(max_concurrent=concurrency)
    try:
        await asyncio.to_thread(validate_document_task_schema)
        if warmup:
            from app.modules.embedding import service as embedding

            await asyncio.to_thread(embedding.embed_query, "Warm up policy document retrieval.")
        await queue.start()
        await _stop_signal().wait()
    finally:
        await queue.stop()
        await database.disconnect()


def _stop_signal() -> asyncio.Event:
    # `docker compose stop` sends SIGTERM; drain claims instead of dying mid-task.
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in ("SIGTERM", "SIGINT"):
        try:
            loop.add_signal_handler(getattr(signal, name), stopped.set)
        except (NotImplementedError, AttributeError):
            pass  # Windows: Ctrl+C still raises KeyboardInterrupt.
    return stopped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, choices=range(1, 17), default=3)
    parser.add_argument(
        "--warmup", action="store_true", help="Load the local model before claiming tasks"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(run(args.concurrency, warmup=args.warmup))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
